"""GET /search — 검색 결과만 (답변 생성 없음). 열람·디버그용. GET /documents/{page_id} — 색인된 문서와 청크."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk, Document
from app.db.session import get_db
from app.permissions import CurrentUser, get_current_user
from app.services.rerank import rerank
from app.services.retrieval import hybrid_search

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=2000),
    k: int = Query(10, ge=1, le=50),
    space_key: Optional[str] = Query(None, description="특정 공간만 검색. 콤마로 여러 개 지정. 없으면 전체."),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    space_keys = [s.strip() for s in space_key.split(",") if s.strip()] if space_key else None
    candidates = await hybrid_search(db, q, user, space_keys=space_keys)
    top, passed = await rerank(q, candidates, top_k=max(k * 3, k))
    seen_docs = set()
    deduped = []
    for c in top:
        if c.document_id in seen_docs:
            continue
        seen_docs.add(c.document_id)
        deduped.append(c)
        if len(deduped) >= k:
            break
    return {
        "passed": passed,
        "results": [
            {
                "chunk_id": str(c.chunk_id), "document_id": str(c.document_id), "page_id": c.page_id, "attachment_id": c.attachment_id, "ordinal": c.ordinal,
                "heading": c.heading, "content": c.content, "title": c.title, "path": c.path, "url": c.url,
                "kind": c.kind, "file_name": c.file_name, "updated_at": c.updated_at.isoformat(),
                "vector_rank": c.vector_rank, "keyword_rank": c.keyword_rank,
                "rrf_score": round(c.rrf_score, 6), "rerank_score": None if c.rerank_score is None else round(c.rerank_score, 4),
            }
            for c in deduped
        ],
    }


@router.get("/documents/{page_id}")
async def get_document(
    page_id: str,
    attachment_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.page_id == page_id)
    stmt = stmt.where(Document.attachment_id == attachment_id) if attachment_id else stmt.where(Document.attachment_id.is_(None))
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="색인된 문서가 없습니다.")
    if not settings.skip_space_permissions and not user.sees_everything and "*" not in doc.allowed_groups and not set(doc.allowed_groups) & set(user.groups):
        raise HTTPException(status_code=403, detail="열람 권한이 없습니다.")
    chunks = (await db.execute(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal))).scalars().all()
    return {
        "id": str(doc.id), "space_key": doc.space_key, "page_id": doc.page_id, "attachment_id": doc.attachment_id,
        "title": doc.title, "path": doc.path, "url": doc.url, "kind": doc.kind, "file_name": doc.file_name,
        "version": doc.version, "updated_at": doc.updated_at.isoformat(), "indexed_at": doc.indexed_at.isoformat(),
        "allowed_groups": doc.allowed_groups,
        "chunks": [{"id": str(c.id), "ordinal": c.ordinal, "heading": c.heading, "content": c.content, "token_count": c.token_count} for c in chunks],
    }
