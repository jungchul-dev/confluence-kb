"""동기화 워커 진입점.

  python -m worker.run_sync --mode full                 # 설정의 전체 공간, 전체 순회 (+ 삭제 페이지 정리)
  python -m worker.run_sync --mode incremental          # 마지막 성공 이후 수정분만
  python -m worker.run_sync --spaces PROJ,PLAN --loop   # SYNC_INCREMENTAL_MINUTES 간격으로 반복 (운영은 cron 권장)

초기 적재와 증분은 같은 함수(sync_space)가 처리하고 차이는 조회 조건뿐이다. 페이지마다:
  버전·해시 비교 → 본문 파싱·청킹·임베딩·적재 → 첨부 목록 조회 → 허용 첨부 다운로드·파싱·적재 → sync_state 갱신
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.config import settings
from app.db.models import SyncRun
from app.db.session import AsyncSessionLocal, ensure_schema
from worker import indexer
from worker.chunker import chunk_sections
from worker.confluence_client import ConfluenceAttachment, ConfluenceClient, ConfluencePage
from worker.parsers.html_page import parse_storage_html
from worker.parsers.registry import is_allowed, parse_attachment

logger = logging.getLogger("worker")


def _page_path(page: ConfluencePage) -> str:
    return " > ".join([page.space_key] + [a for a in page.ancestors if a] + [page.title])


def _groups_for(page: ConfluencePage, space_groups: List[str]) -> List[str]:
    return page.read_groups if page.read_groups else space_groups


async def _index_page_body(db, page: ConfluencePage, groups: List[str], c_hash: str) -> int:
    sections = parse_storage_html(page.storage_html)
    drafts = chunk_sections(sections, _page_path(page))
    return await indexer.upsert_document(
        db, space_key=page.space_key, page_id=page.id, attachment_id=None, title=page.title, path=_page_path(page),
        url=page.url, kind="page", file_name=None, version=page.version, c_hash=c_hash, updated_at=page.updated_at,
        allowed_groups=groups, drafts=drafts,
    )


async def _index_attachment(db, client: ConfluenceClient, page: ConfluencePage, att: ConfluenceAttachment, groups: List[str]) -> int:
    data = await client.download_attachment(att)
    sections = parse_attachment(att.file_name, data)
    path = f"{_page_path(page)} > {att.file_name}"
    drafts = chunk_sections(sections, path)
    c_hash = indexer.content_hash(att.file_name, str(att.version), str(len(data)))
    return await indexer.upsert_document(
        db, space_key=page.space_key, page_id=page.id, attachment_id=att.id, title=f"{page.title} — {att.file_name}", path=path,
        url=att.url or page.url, kind="attachment", file_name=att.file_name, version=att.version, c_hash=c_hash,
        updated_at=att.updated_at, allowed_groups=groups, drafts=drafts,
    )


async def sync_page(client: ConfluenceClient, page: ConfluencePage, space_groups: List[str], run: SyncRun) -> None:
    """페이지 1건 + 첨부. 각 문서는 자체 트랜잭션. 실패는 sync_state.error 에 남기고 다음으로 넘어간다."""
    groups = _groups_for(page, space_groups)
    body_hash = indexer.content_hash(page.title, _page_path(page), page.storage_html, ",".join(sorted(groups)))
    async with AsyncSessionLocal() as db:
        state = await indexer.get_sync_state(db, page.id)
        unchanged = state is not None and state.version == page.version and state.content_hash == body_hash and state.error is None

    run.pages_seen += 1
    try:
        if not unchanged:
            async with AsyncSessionLocal() as db:
                n = await _index_page_body(db, page, groups, body_hash)
                await db.commit()
            run.pages_indexed += 1
            logger.info("[%s] page %s '%s' v%d -> %d chunks", page.space_key, page.id, page.title, page.version, n)

        # 첨부: 바뀐 것만 다시 받는다 (버전 비교는 documents.version)
        attachments = await client.list_attachments(page.id)
        keep: List[str] = []
        for att in attachments:
            if not is_allowed(att.file_name, att.size):
                continue
            keep.append(att.id)
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.db.models import Document
                existing = (await db.execute(select(Document).where(Document.page_id == page.id, Document.attachment_id == att.id))).scalar_one_or_none()
                same = existing is not None and existing.version == att.version and existing.allowed_groups == groups
                if same and unchanged:
                    continue
                try:
                    n = await _index_attachment(db, client, page, att, groups)
                    await db.commit()
                    run.attachments_indexed += 1
                    logger.info("[%s]   attachment '%s' v%d -> %d chunks", page.space_key, att.file_name, att.version, n)
                except Exception as e:  # noqa: BLE001
                    await db.rollback()
                    run.errors += 1
                    logger.warning("[%s]   attachment '%s' failed: %s", page.space_key, att.file_name, e)
        async with AsyncSessionLocal() as db:
            removed = await indexer.delete_stale_attachments(db, page.id, keep)
            await indexer.set_sync_state(db, page.id, page.space_key, page.version, body_hash, None)
            await db.commit()
            if removed:
                logger.info("[%s]   removed %d stale attachment docs", page.space_key, removed)
    except Exception as e:  # noqa: BLE001
        run.errors += 1
        logger.error("[%s] page %s failed: %s", page.space_key, page.id, e, exc_info=True)
        async with AsyncSessionLocal() as db:
            await indexer.set_sync_state(db, page.id, page.space_key, page.version, body_hash, str(e)[:2000])
            await db.commit()


async def sync_space(client: ConfluenceClient, space_key: str, mode: str) -> SyncRun:
    async with AsyncSessionLocal() as db:
        run = SyncRun(space_key=space_key, mode=mode)
        db.add(run)
        await db.commit()
        await db.refresh(run)
        since: Optional[datetime] = None
        if mode == "incremental":
            since = await indexer.last_successful_sync(db, space_key)
    logger.info("[%s] sync start mode=%s since=%s", space_key, mode, since)

    try:
        space_groups = await client.space_read_groups(space_key)
        async for page in client.iter_pages(space_key, modified_since=since):
            await sync_page(client, page, space_groups, run)

        if mode == "full":
            # 삭제·보관된 페이지 정리: Confluence 에 없는데 sync_state 에 남은 것
            live = set(await client.list_page_ids(space_key))
            async with AsyncSessionLocal() as db:
                known = await indexer.known_page_ids(db, space_key)
                for pid in known:
                    if pid not in live:
                        await indexer.delete_page(db, pid)
                        run.pages_deleted += 1
                await db.commit()
        run.status = "success"
    except Exception as e:  # noqa: BLE001
        run.status = "failed"
        run.message = str(e)[:2000]
        logger.error("[%s] sync failed: %s", space_key, e, exc_info=True)

    run.finished_at = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await db.merge(run)
        await db.commit()
    logger.info("[%s] sync %s: seen=%d indexed=%d attachments=%d deleted=%d errors=%d",
                space_key, run.status, run.pages_seen, run.pages_indexed, run.attachments_indexed, run.pages_deleted, run.errors)
    return run


async def sync_spaces(spaces: List[str], mode: str) -> List[SyncRun]:
    await ensure_schema()
    runs: List[SyncRun] = []
    async with ConfluenceClient() as client:
        for key in spaces:
            runs.append(await sync_space(client, key, mode))
    return runs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="confluence-kb sync worker")
    ap.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    ap.add_argument("--spaces", default="", help="쉼표 구분 공간 키 (기본: CONFLUENCE_SPACES)")
    ap.add_argument("--loop", action="store_true", help="SYNC_INCREMENTAL_MINUTES 간격으로 반복 실행")
    args = ap.parse_args()
    spaces = [s.strip() for s in args.spaces.split(",") if s.strip()] or settings.space_keys
    if not spaces:
        ap.error("수집 대상 공간이 없습니다 (--spaces 또는 CONFLUENCE_SPACES)")

    async def runner():
        while True:
            await sync_spaces(spaces, args.mode)
            if not args.loop:
                break
            await asyncio.sleep(settings.sync_incremental_minutes * 60)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
