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
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None
    sources: List[str] = field(default_factory=list)  # ["vector", "keyword"]


_SELECT_COLS = """
    c.id AS chunk_id, c.document_id, c.ordinal, c.heading, c.content,
    d.title, d.path, d.url, d.kind, d.file_name, d.updated_at
"""

# 권한: 사용자 그룹과 교집합이 있거나 제한 없는 문서('*')
_PERM = "(d.allowed_groups && CAST(:groups AS text[]) OR '*' = ANY(d.allowed_groups))"

_VECTOR_SQL = text(f"""
    SELECT {_SELECT_COLS}, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE {_PERM}
    ORDER BY c.embedding <=> CAST(:qvec AS vector)
    LIMIT :k
""")

_KEYWORD_SQL = text(f"""
    SELECT {_SELECT_COLS}, ts_rank_cd(c.tsv, q) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id,
         plainto_tsquery('simple', :q) q
    WHERE c.tsv @@ q AND {_PERM}
    ORDER BY score DESC
    LIMIT :k
""")


def _row_to_candidate(row) -> Candidate:
    return Candidate(
        chunk_id=row.chunk_id, document_id=row.document_id, ordinal=row.ordinal, heading=row.heading,
        content=row.content, title=row.title, path=row.path, url=row.url, kind=row.kind,
        file_name=row.file_name, updated_at=row.updated_at,
    )


async def hybrid_search(
    db: AsyncSession, question: str, user: CurrentUser, *, k: Optional[int] = None, rrf_k: int = 60,
) -> List[Candidate]:
    """벡터·키워드 각각 k 개를 받아 RRF(1/(rrf_k+rank))로 합친 뒤 점수순으로 돌려준다 (최대 k 개)."""
    k = k or settings.top_k_candidates
    qvec = await embed_query(question)
    vec_param = "[" + ",".join(f"{v:.7f}" for v in qvec) + "]"

    if user.sees_everything:
        # 관리자·개발 모드: 권한 조건을 빼고 전체를 검색한다
        vector_sql = text(str(_VECTOR_SQL).replace(_PERM, "TRUE"))
        keyword_sql = text(str(_KEYWORD_SQL).replace(_PERM, "TRUE"))
        params_v = {"qvec": vec_param, "k": k}
        params_k = {"q": question, "k": k}
    else:
        vector_sql, keyword_sql = _VECTOR_SQL, _KEYWORD_SQL
        params_v = {"qvec": vec_param, "k": k, "groups": user.groups}
        params_k = {"q": question, "k": k, "groups": user.groups}

    merged: Dict[uuid.UUID, Candidate] = {}

    vres = await db.execute(vector_sql, params_v)
    for rank, row in enumerate(vres.fetchall(), start=1):
        c = merged.setdefault(row.chunk_id, _row_to_candidate(row))
        c.vector_rank = rank
        c.sources.append("vector")
        c.rrf_score += 1.0 / (rrf_k + rank)

    kres = await db.execute(keyword_sql, params_k)
    for rank, row in enumerate(kres.fetchall(), start=1):
        c = merged.setdefault(row.chunk_id, _row_to_candidate(row))
        c.keyword_rank = rank
        c.sources.append("keyword")
        c.rrf_score += 1.0 / (rrf_k + rank)

    ranked = sorted(merged.values(), key=lambda c: c.rrf_score, reverse=True)
    return ranked[:k]
