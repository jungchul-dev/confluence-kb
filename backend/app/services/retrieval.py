"""하이브리드 검색 — pgvector 코사인 상위 k + tsvector 키워드 상위 k 를 RRF 로 합친다.

두 쿼리 모두 권한 필터를 포함한다 (검색 후 걸러내면 상위 k 가 줄어 품질이 흔들린다).
반환 Candidate 는 리랭킹(services/rerank.py)과 맥락 구성(services/context.py)이 그대로 쓴다.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import TSV_CONFIG
from app.permissions import CurrentUser
from app.services.embeddings import embed_query


@dataclass
class Candidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    ordinal: int
    heading: Optional[str]
    content: str
    title: str
    path: str
    url: str
    kind: str
    file_name: Optional[str]
    updated_at: datetime
    page_id: str = ""
    attachment_id: Optional[str] = None
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None
    sources: List[str] = field(default_factory=list)  # ["vector", "keyword"]


_SELECT_COLS = """
    c.id AS chunk_id, c.document_id, c.ordinal, c.heading, c.content,
    d.title, d.path, d.url, d.kind, d.file_name, d.updated_at, d.page_id, d.attachment_id
"""

# 권한: 사용자 그룹과 교집합이 있거나 제한 없는 문서('*')
_PERM = "(d.allowed_groups && CAST(:groups AS text[]) OR '*' = ANY(d.allowed_groups))"
_SPACE = "d.space_key = ANY(CAST(:space_keys AS text[]))"

_VECTOR_SQL = text(f"""
    SELECT {_SELECT_COLS}, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE {_PERM} AND {_SPACE}
    ORDER BY c.embedding <=> CAST(:qvec AS vector)
    LIMIT :k
""")

_KEYWORD_SQL = text(f"""
    SELECT {_SELECT_COLS}, ts_rank_cd(c.tsv, q) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id,
         websearch_to_tsquery('{TSV_CONFIG}', :q) q
    WHERE c.tsv @@ q AND {_PERM} AND {_SPACE}
    ORDER BY score DESC
    LIMIT :k
""")

_KEYWORD_OR_SQL = text(f"""
    SELECT {_SELECT_COLS}, ts_rank_cd(c.tsv, qq.q) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id,
         (SELECT CAST(replace(CAST(websearch_to_tsquery('{TSV_CONFIG}', :q) AS text), ' & ', ' | ') AS tsquery) AS q) qq
    WHERE c.tsv @@ qq.q AND {_PERM} AND {_SPACE}
    ORDER BY score DESC
    LIMIT :k
""")


def _row_to_candidate(row) -> Candidate:
    return Candidate(
        chunk_id=row.chunk_id, document_id=row.document_id, ordinal=row.ordinal, heading=row.heading,
        content=row.content, title=row.title, path=row.path, url=row.url, kind=row.kind,
        file_name=row.file_name, updated_at=row.updated_at, page_id=row.page_id, attachment_id=row.attachment_id,
    )


async def hybrid_search(
    db: AsyncSession, question: str, user: CurrentUser, *, k: Optional[int] = None, rrf_k: int = 60, space_keys: Optional[List[str]] = None,
) -> List[Candidate]:
    """벡터·키워드 각각 k 개를 받아 RRF(1/(rrf_k+rank))로 합친 뒤 점수순으로 돌려준다 (최대 k 개). space_keys 가 있으면 해당 공간만."""
    k = k or settings.top_k_candidates
    qvec = await embed_query(question)
    vec_param = "[" + ",".join(f"{v:.7f}" for v in qvec) + "]"

    vector_sql = str(_VECTOR_SQL)
    keyword_sql = str(_KEYWORD_SQL)
    keyword_or_sql = str(_KEYWORD_OR_SQL)
    if user.sees_everything or settings.skip_space_permissions:
        vector_sql = vector_sql.replace(_PERM, "TRUE")
        keyword_sql = keyword_sql.replace(_PERM, "TRUE")
        keyword_or_sql = keyword_or_sql.replace(_PERM, "TRUE")
    if not space_keys:
        vector_sql = vector_sql.replace(_SPACE, "TRUE")
        keyword_sql = keyword_sql.replace(_SPACE, "TRUE")
        keyword_or_sql = keyword_or_sql.replace(_SPACE, "TRUE")

    params_v = {"qvec": vec_param, "k": k}
    params_k = {"q": question, "k": k}
    if not (user.sees_everything or settings.skip_space_permissions):
        params_v["groups"] = user.groups
        params_k["groups"] = user.groups
    if space_keys:
        params_v["space_keys"] = space_keys
        params_k["space_keys"] = space_keys

    merged: Dict[uuid.UUID, Candidate] = {}

    vres = await db.execute(text(vector_sql), params_v)
    for rank, row in enumerate(vres.fetchall(), start=1):
        c = merged.setdefault(row.chunk_id, _row_to_candidate(row))
        c.vector_rank = rank
        c.sources.append("vector")
        c.rrf_score += 1.0 / (rrf_k + rank)

    krows = (await db.execute(text(keyword_sql), params_k)).fetchall()
    if not krows:
        krows = (await db.execute(text(keyword_or_sql), params_k)).fetchall()
    for rank, row in enumerate(krows, start=1):
        c = merged.setdefault(row.chunk_id, _row_to_candidate(row))
        c.keyword_rank = rank
        c.sources.append("keyword")
        c.rrf_score += 1.0 / (rrf_k + rank)

    ranked = sorted(merged.values(), key=lambda c: c.rrf_score, reverse=True)
    return ranked[:k]
