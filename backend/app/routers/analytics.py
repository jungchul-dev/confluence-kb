"""분석 — 유사 문서 추천과 주제 클러스터링. 임베딩을 검색 외 용도로 활용한다."""
import asyncio
import hashlib
import logging
import math
import re
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.permissions import CurrentUser, get_current_user
from app.services import answer as answer_svc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

_PERM = "(d.allowed_groups && CAST(:groups AS text[]) OR '*' = ANY(d.allowed_groups))"

_RELATED_SQL = text(f"""
    WITH src AS (
        SELECT AVG(c.embedding) AS emb
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.page_id = :page_id AND d.attachment_id IS NULL
    )
    SELECT d.id, d.title, d.path, d.url, d.kind, d.space_key, d.updated_at,
           MAX(1 - (c.embedding <=> (SELECT emb FROM src))) AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.page_id != :page_id AND {_PERM}
    GROUP BY d.id, d.title, d.path, d.url, d.kind, d.space_key, d.updated_at
    ORDER BY score DESC
    LIMIT :k
""")


@router.get("/documents/{page_id}/related")
async def get_related_documents(
    page_id: str,
    k: int = Query(5, ge=1, le=20),
    attachment_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주어진 문서와 임베딩 유사도가 높은 다른 문서 k개를 돌려준다."""
    if settings.skip_space_permissions or user.sees_everything:
        sql = text(str(_RELATED_SQL).replace(_PERM, "TRUE"))
        params = {"page_id": page_id, "k": k}
    else:
        sql = _RELATED_SQL
        params = {"page_id": page_id, "k": k, "groups": user.groups}

    rows = (await db.execute(sql, params)).fetchall()
    return {
        "page_id": page_id,
        "results": [
            {
                "document_id": str(r.id), "title": r.title, "path": r.path,
                "url": r.url, "kind": r.kind, "space_key": r.space_key,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "score": round(float(r.score or 0), 4),
            }
            for r in rows
        ],
    }


# 클러스터링 입력: 문서 임베딩(접두 없는 본문). 아직 없으면(마이그레이션 전) 청크 평균으로 대체한다.
_DOC_EMBEDDINGS_SQL = text(f"""
    SELECT d.id, d.page_id, d.title, d.path, d.url, d.space_key, d.kind, d.updated_at,
           COALESCE(d.embedding, AVG(c.embedding))::text AS emb,
           (d.embedding IS NULL) AS fallback
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE {_PERM}
    GROUP BY d.id, d.page_id, d.title, d.path, d.url, d.space_key, d.kind, d.updated_at, d.embedding
""")

_KEYWORD_MIN_LEN = 2
_KEYWORD_RE = re.compile(r"^[가-힣a-zA-Z][가-힣a-zA-Z0-9]*$")
_corpus_stat_cache: dict = {"at": 0.0, "total": 0, "stat": {}}


async def _corpus_term_stats(db: AsyncSession) -> tuple:
    """전체 청크의 (총 청크 수, 단어별 출현 청크 수). 본문(B 가중치)만 센다. 10분 캐시."""
    now = time.monotonic()
    if now - _corpus_stat_cache["at"] < 600 and _corpus_stat_cache["stat"]:
        return _corpus_stat_cache["total"], _corpus_stat_cache["stat"]
    total = (await db.execute(text("SELECT count(*) FROM chunks"))).scalar() or 1
    rows = (await db.execute(text("SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks', 'B')"))).fetchall()
    stat = {r.word: r.ndoc for r in rows}
    _corpus_stat_cache.update(at=now, total=total, stat=stat)
    return total, stat


async def _cluster_keywords(db: AsyncSession, doc_ids: List[str], total: int, corpus: dict, n: int = 5) -> List[str]:
    """클러스터 문서들의 본문 토큰 중 '이 클러스터에서는 흔하고 전체에서는 드문' 순 (TF-IDF). 불용어 목록 없이 IDF 로 거른다."""
    ids_sql = ",".join(f"''{uuid.UUID(i)}''" for i in doc_ids)  # uuid 검증 후 ts_stat 쿼리 문자열에 삽입
    n_chunks = (await db.execute(text("SELECT count(*) FROM chunks WHERE document_id = ANY(CAST(:ids AS uuid[]))"), {"ids": doc_ids})).scalar() or 1
    rows = (await db.execute(text(f"SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks WHERE document_id IN ({ids_sql})', 'B')"))).fetchall()
    scored = []
    for r in rows:
        w = r.word
        if len(w) < _KEYWORD_MIN_LEN or not _KEYWORD_RE.match(w):
            continue
        scored.append(((r.ndoc / n_chunks) * math.log(total / corpus.get(w, 1)), w))
    scored.sort(reverse=True)
    return [w for _, w in scored[:n]]


_LABEL_SYSTEM = """당신은 사내 문서 모음에 짧은 제목을 붙이는 사서입니다.
주어진 문서 묶음(클러스터)의 대표 문서 제목과 특징 단어를 보고, 이 묶음이 무엇에 관한 문서들인지 한국어 명사구로 제목을 짓습니다.
규칙: 6단어 이내, 따옴표·마침표·설명 없이 제목만 출력, 특정 문서 하나의 제목을 그대로 쓰지 말고 묶음 전체를 아우를 것,
특징 단어는 형태소 조각이라 불완전할 수 있으니 문맥으로 원래 단어를 추정할 것."""
_label_cache: dict = {}  # 문서 id 집합 해시 → 제목 (프로세스 수명 동안 유지, 같은 구성이면 재호출 없음)


def _strip_attachment_suffix(title: str) -> str:
    return re.sub(r"\s*—\s*.*$", "", title)


async def _llm_label(doc_ids: List[str], titles: List[str], keywords: List[str], doc_count: int) -> Optional[str]:
    key = hashlib.sha1("|".join(sorted(doc_ids)).encode()).hexdigest()
    if key in _label_cache:
        return _label_cache[key]
    user = (f"문서 수: {doc_count}\n특징 단어: {', '.join(keywords)}\n대표 문서 제목:\n" + "\n".join(f"- {t}" for t in titles) + "\n\n제목:")
    try:
        label = await answer_svc.chat(_LABEL_SYSTEM, user, temperature=0.1, max_tokens=60, timeout=25.0)
        label = label.strip().strip('"\'「」').splitlines()[0][:60] if label else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("cluster label llm failed: %s", e)
        return None
    if not label:
        return None
    _label_cache[key] = label
    return label


def _choose_k(x, requested: int, n: int) -> tuple:
    """k>0 이면 그대로. k=0 이면 2..min(20, n/5) 범위에서 실루엣 점수(코사인)가 가장 높은 k 를 고른다."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    if requested > 0:
        return min(requested, n), None, []
    hi = max(2, min(20, n // 5))
    tried = []
    best_k, best_s = 2, -1.0
    for k in range(2, hi + 1):
        labels = KMeans(n_clusters=k, random_state=42, n_init=4).fit_predict(x)
        score = float(silhouette_score(x, labels, metric="cosine", sample_size=min(n, 2000), random_state=42))
        tried.append({"k": k, "silhouette": round(score, 4)})
        if score > best_s:
            best_k, best_s = k, score
    return best_k, best_s, tried


@router.get("/admin/clusters")
async def get_clusters(
    k: int = Query(0, ge=0, le=50),
    llm: bool = Query(True, description="true 면 LLM 으로 클러스터 제목을 짓는다 (실패 시 키워드 제목)"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """문서 임베딩을 K-Means(코사인) 로 클러스터링해 주제 그룹을 돌려준다. k=0 이면 실루엣 점수로 자동 선택.
    각 클러스터에는 TF-IDF 키워드(label)와 중심에 가까운 대표 문서 5개가 붙는다."""
    try:
        import numpy as np
        from sklearn.cluster import KMeans
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="클러스터링에는 scikit-learn 이 필요합니다. pip install -r requirements-optional.txt",
        )

    if settings.skip_space_permissions or user.sees_everything:
        sql = text(str(_DOC_EMBEDDINGS_SQL).replace(_PERM, "TRUE"))
        params = {}
    else:
        sql = _DOC_EMBEDDINGS_SQL
        params = {"groups": user.groups}

    rows = (await db.execute(sql, params)).fetchall()
    n = len(rows)
    if n < 2:
        return {"clusters": [], "total_documents": n, "k": 0, "silhouette": None, "k_candidates": [], "docs_without_embedding": 0}

    def _parse_vec(raw):
        if isinstance(raw, str):
            return [float(v) for v in raw.strip("[]").split(",")]
        return list(raw)

    x = np.array([_parse_vec(r.emb) for r in rows], dtype=np.float32)
    # 길이를 1 로 맞추면 유클리드 K-Means 가 코사인 기준과 같아진다 (청크 평균 대체분은 길이가 제각각이라 특히 중요)
    x = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)
    fallback_count = sum(1 for r in rows if r.fallback)

    n_clusters, chosen_score, candidates = _choose_k(x, k, n)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(x)
    if chosen_score is None and n_clusters < n:
        from sklearn.metrics import silhouette_score
        chosen_score = float(silhouette_score(x, labels, metric="cosine", sample_size=min(n, 2000), random_state=42))

    clusters: dict = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(i)

    total_chunks, corpus = await _corpus_term_stats(db)

    def _doc(i):
        r = rows[i]
        return {"document_id": str(r.id), "title": r.title, "path": r.path, "url": r.url, "space_key": r.space_key, "kind": r.kind}

    result = []
    label_jobs = []
    for cid, indices in sorted(clusters.items(), key=lambda t: -len(t[1])):
        center = km.cluster_centers_[cid]
        by_dist = sorted(indices, key=lambda i: float(np.linalg.norm(x[i] - center)))
        # 대표 문서는 페이지 단위로 중복을 뺀다 (같은 페이지의 본문·첨부가 나란히 뽑히지 않게)
        rep, seen = [], set()
        for i in by_dist:
            if rows[i].page_id in seen:
                continue
            seen.add(rows[i].page_id)
            rep.append(i)
            if len(rep) >= 10:
                break
        doc_ids = [str(rows[i].id) for i in indices]
        keywords = await _cluster_keywords(db, doc_ids, total_chunks, corpus, n=10)
        keyword_label = " · ".join(keywords[:3]) if keywords else f"클러스터 {cid}"
        result.append({
            "cluster_id": cid,
            "doc_count": len(indices),
            "keywords": keywords,
            "label": keyword_label,
            "keyword_label": keyword_label,
            "label_source": "keywords",
            "representative_docs": [_doc(i) for i in rep[:5]],
            "all_docs": [_doc(i) for i in indices],
            "all_titles": [rows[i].title for i in indices],
        })
        if llm:
            titles = [_strip_attachment_suffix(rows[i].title) for i in rep]
            label_jobs.append(_llm_label(doc_ids, titles, keywords, len(indices)))

    if label_jobs:
        # 클러스터 수만큼 병렬 호출. 실패한 것은 키워드 제목을 유지한다
        labels = await asyncio.gather(*label_jobs, return_exceptions=True)
        for item, label in zip(result, labels):
            if isinstance(label, str) and label:
                item["label"], item["label_source"] = label, "llm"

    return {
        "clusters": result, "total_documents": n, "k": n_clusters,
        "silhouette": None if chosen_score is None else round(chosen_score, 4),
        "k_candidates": candidates, "docs_without_embedding": fallback_count,
    }
