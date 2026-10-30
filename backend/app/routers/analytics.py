"""분석 — 유사 문서 추천과 주제 클러스터링. 임베딩을 검색 외 용도로 활용한다."""
import logging
import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.permissions import CurrentUser, get_current_user

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


_DOC_EMBEDDINGS_SQL = text(f"""
    SELECT d.id, d.title, d.path, d.url, d.space_key, d.kind, d.updated_at,
           AVG(c.embedding)::text AS emb
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE {_PERM}
    GROUP BY d.id, d.title, d.path, d.url, d.space_key, d.kind, d.updated_at
""")


@router.get("/admin/clusters")
async def get_clusters(
    k: int = Query(0, ge=0, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """문서 임베딩을 K-Means 로 클러스터링해 주제 그룹을 돌려준다. k=0 이면 자동 선택."""
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
    if len(rows) < 2:
        return {"clusters": [], "total_documents": len(rows), "k": 0}

    import json

    def _parse_vec(raw):
        if isinstance(raw, str):
            return [float(x) for x in raw.strip('[]').split(',')]
        return list(raw)

    embeddings = np.array([_parse_vec(r.emb) for r in rows], dtype=np.float32)
    titles = [r.title for r in rows]

    n_clusters = k if k > 0 else max(2, min(int(math.sqrt(len(rows) / 2)), 20))
    n_clusters = min(n_clusters, len(rows))

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(embeddings)

    clusters: dict[int, list] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(i)

    result = []
    for cid, indices in sorted(clusters.items(), key=lambda x: -len(x[1])):
        dists = [float(np.linalg.norm(embeddings[i] - km.cluster_centers_[cid])) for i in indices]
        sorted_pairs = sorted(zip(indices, dists), key=lambda x: x[1])
        rep_indices = [i for i, _ in sorted_pairs[:5]]
        all_docs = [
            {
                "document_id": str(rows[i].id), "title": rows[i].title,
                "path": rows[i].path, "url": rows[i].url, "space_key": rows[i].space_key,
                "kind": rows[i].kind,
            }
            for i in indices
        ]
        result.append({
            "cluster_id": cid,
            "doc_count": len(indices),
            "representative_docs": [
                {
                    "document_id": str(rows[i].id), "title": rows[i].title,
                    "path": rows[i].path, "url": rows[i].url, "space_key": rows[i].space_key,
                    "kind": rows[i].kind,
                }
                for i in rep_indices
            ],
            "all_docs": all_docs,
            "all_titles": [titles[i] for i in indices],
        })

    return {"clusters": result, "total_documents": len(rows), "k": n_clusters}
