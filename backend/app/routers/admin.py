"""관리 — 동기화 상태 조회와 수동 실행. 실행은 백그라운드 태스크로 돌고 sync_runs 에 기록된다."""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Document, SyncRun, SyncState
from app.db.session import get_db
from app.permissions import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_running_lock = asyncio.Lock()


class SyncRunRequest(BaseModel):
    spaces: Optional[List[str]] = None  # 없으면 설정의 전체 공간
    mode: str = "incremental"  # full | incremental


def _run_dict(r: SyncRun) -> dict:
    return {
        "id": str(r.id), "space_key": r.space_key, "mode": r.mode, "status": r.status,
        "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "pages_seen": r.pages_seen, "pages_indexed": r.pages_indexed, "pages_deleted": r.pages_deleted,
        "attachments_indexed": r.attachments_indexed, "errors": r.errors, "message": r.message,
    }


@router.get("/spaces")
async def list_spaces(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Document.space_key, func.count()).group_by(Document.space_key).order_by(Document.space_key))).all()
    return [{"space_key": r[0], "doc_count": r[1]} for r in rows]


@router.get("/sync/status")
async def sync_status(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """공간별 문서 수·마지막 동기화·실패 건수 + 최근 실행 20건."""
    spaces = []
    for key in settings.space_keys:
        docs = (await db.execute(select(func.count()).select_from(Document).where(Document.space_key == key))).scalar_one()
        pages = (await db.execute(select(func.count()).select_from(Document).where(Document.space_key == key, Document.kind == "page"))).scalar_one()
        attachments = (await db.execute(select(func.count()).select_from(Document).where(Document.space_key == key, Document.kind == "attachment"))).scalar_one()
        errors = (await db.execute(select(func.count()).select_from(SyncState).where(SyncState.space_key == key, SyncState.error.isnot(None)))).scalar_one()
        last = (await db.execute(select(func.max(SyncState.synced_at)).where(SyncState.space_key == key))).scalar_one()
        spaces.append({"space_key": key, "documents": docs, "pages": pages, "attachments": attachments, "errors": errors, "last_synced_at": last.isoformat() if last else None})
    runs = (await db.execute(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(20))).scalars().all()
    return {"spaces": spaces, "runs": [_run_dict(r) for r in runs], "running": _running_lock.locked()}


@router.get("/sync/errors")
async def sync_errors(limit: int = Query(50, ge=1, le=500), user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SyncState).where(SyncState.error.isnot(None)).order_by(SyncState.synced_at.desc()).limit(limit))).scalars().all()
    return [{"page_id": r.page_id, "space_key": r.space_key, "version": r.version, "synced_at": r.synced_at.isoformat(), "error": r.error} for r in rows]


@router.post("/sync/run", status_code=202)
async def sync_run(payload: SyncRunRequest, background: BackgroundTasks, user: CurrentUser = Depends(get_current_user)):
    """수동 동기화. 이미 도는 중이면 409."""
    if payload.mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode 는 full 또는 incremental 이어야 합니다.")
    if _running_lock.locked():
        raise HTTPException(status_code=409, detail="동기화가 이미 실행 중입니다.")
    spaces = payload.spaces or settings.space_keys
    if not spaces:
        raise HTTPException(status_code=400, detail="수집 대상 공간이 없습니다 (CONFLUENCE_SPACES).")

    async def job():
        from worker.run_sync import sync_spaces
        async with _running_lock:
            try:
                await sync_spaces(spaces, payload.mode)
            except Exception as e:  # noqa: BLE001
                logger.error("manual sync failed: %s", e, exc_info=True)

    background.add_task(job)
    return {"accepted": True, "spaces": spaces, "mode": payload.mode}
