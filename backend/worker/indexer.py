"""적재 — 문서(페이지/첨부) 단위 트랜잭션으로 기존 청크 삭제 → 새 청크 삽입 → sync_state 갱신.

중간에 실패하면 롤백되어 이전 청크가 남으므로 검색은 계속된다.
"""
import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DOC_EMBED_CHARS, Chunk, Document, SyncState
from app.services.embeddings import embed_texts
from worker.chunker import ChunkDraft

logger = logging.getLogger(__name__)


_PREFIX_LINE = re.compile(r"^\[[^\n]*\]\n?")


def document_embedding_text(title: str, chunk_contents: List[str]) -> str:
    """클러스터링용 문서 텍스트 — 제목 + 각 청크의 경로 접두 줄을 뺀 본문을 이어 붙여 앞 DOC_EMBED_CHARS 자."""
    body = "\n".join(_PREFIX_LINE.sub("", c).strip() for c in chunk_contents)
    body = re.sub(r"\n{2,}", "\n", body)
    return f"{title}\n{body[:DOC_EMBED_CHARS]}"


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
        h.update(b"\x00")
    return h.hexdigest()


async def upsert_document(
    db: AsyncSession, *, space_key: str, page_id: str, attachment_id: Optional[str], title: str, path: str, url: str,
    kind: str, file_name: Optional[str], version: int, c_hash: str, updated_at: datetime, allowed_groups: List[str],
    drafts: List[ChunkDraft],
) -> int:
    """문서 1건을 교체 적재하고 청크 수를 돌려준다. 청크가 없으면(빈 본문) 문서도 지운다."""
    stmt = select(Document).where(Document.page_id == page_id)
    stmt = stmt.where(Document.attachment_id == attachment_id) if attachment_id else stmt.where(Document.attachment_id.is_(None))
    doc = (await db.execute(stmt)).scalar_one_or_none()

    if not drafts:
        if doc:
            await db.delete(doc)
        return 0

    # 청크 임베딩 + 마지막 1개는 문서 임베딩(접두 없는 본문) — 한 번의 배치 호출로 처리한다
    vectors = await embed_texts([d.content for d in drafts] + [document_embedding_text(title, [d.content for d in drafts])])
    doc_vector = vectors.pop()

    if doc is None:
        doc = Document(space_key=space_key, page_id=page_id, attachment_id=attachment_id, title=title, path=path, url=url,
                       kind=kind, file_name=file_name, version=version, content_hash=c_hash, updated_at=updated_at,
                       allowed_groups=allowed_groups, embedding=doc_vector)
        db.add(doc)
        await db.flush()
    else:
        doc.space_key, doc.title, doc.path, doc.url, doc.kind, doc.file_name = space_key, title, path, url, kind, file_name
        doc.version, doc.content_hash, doc.updated_at, doc.allowed_groups = version, c_hash, updated_at, allowed_groups
        doc.indexed_at = datetime.now(updated_at.tzinfo)
        doc.embedding = doc_vector
        await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))

    for d, vec in zip(drafts, vectors):
        db.add(Chunk(document_id=doc.id, ordinal=d.ordinal, heading=d.heading, content=d.content, embedding=vec, token_count=d.token_count))
    return len(drafts)


async def delete_page(db: AsyncSession, page_id: str) -> int:
    """페이지와 그 첨부 문서를 모두 지운다 (청크는 FK CASCADE). 지운 문서 수를 돌려준다."""
    docs = (await db.execute(select(Document).where(Document.page_id == page_id))).scalars().all()
    for d in docs:
        await db.delete(d)
    await db.execute(delete(SyncState).where(SyncState.page_id == page_id))
    return len(docs)


async def delete_stale_attachments(db: AsyncSession, page_id: str, keep_attachment_ids: List[str]) -> int:
    """페이지에서 사라진 첨부의 문서를 지운다."""
    stmt = select(Document).where(Document.page_id == page_id, Document.attachment_id.isnot(None))
    if keep_attachment_ids:
        stmt = stmt.where(Document.attachment_id.notin_(keep_attachment_ids))
    docs = (await db.execute(stmt)).scalars().all()
    for d in docs:
        await db.delete(d)
    return len(docs)


async def get_sync_state(db: AsyncSession, page_id: str) -> Optional[SyncState]:
    return (await db.execute(select(SyncState).where(SyncState.page_id == page_id))).scalar_one_or_none()


async def set_sync_state(db: AsyncSession, page_id: str, space_key: str, version: int, c_hash: str, error: Optional[str]) -> None:
    row = await get_sync_state(db, page_id)
    if row is None:
        row = SyncState(page_id=page_id, space_key=space_key, version=version, content_hash=c_hash, error=error)
        db.add(row)
    else:
        row.space_key, row.version, row.content_hash, row.error = space_key, version, c_hash, error
        row.synced_at = datetime.now(datetime.now().astimezone().tzinfo)
    await db.flush()


async def known_page_ids(db: AsyncSession, space_key: str) -> List[str]:
    rows = (await db.execute(select(SyncState.page_id).where(SyncState.space_key == space_key))).scalars().all()
    return list(rows)


async def last_successful_sync(db: AsyncSession, space_key: str) -> Optional[datetime]:
    """증분 기준 시각 — 마지막으로 성공한 동기화 실행의 시작 시각."""
    row = (await db.execute(text(
        "SELECT started_at FROM sync_runs WHERE space_key = :s AND status = 'success' ORDER BY started_at DESC LIMIT 1"
    ), {"s": space_key})).first()
    return row[0] if row else None
