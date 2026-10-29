"""Confluence REST 클라이언트 — 페이지·첨부·버전·권한 조회와 첨부 다운로드.

Cloud: Basic(이메일:API 토큰), Data Center: Bearer(PAT). 둘 다 /rest/api 의 v1 엔드포인트를 쓴다.
호출 제한(429)과 일시 오류(5xx)는 지수 백오프로 재시도한다.
"""
import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PAGE_EXPAND = "body.storage,version,ancestors,space,restrictions.read.restrictions.group,restrictions.read.restrictions.user,history.lastUpdated"


@dataclass
class ConfluencePage:
    id: str
    space_key: str
    title: str
    version: int
    updated_at: datetime
    storage_html: str
    ancestors: List[str]  # 상위 페이지 제목 (루트부터)
    url: str
    read_groups: List[str]  # 비어 있으면 제한 없음
    raw: dict = field(default_factory=dict)


@dataclass
class ConfluenceAttachment:
    id: str
    page_id: str
    file_name: str
    media_type: str
    size: int
    version: int
    updated_at: datetime
    download_path: str  # 상대 경로 (/download/attachments/...)
    url: str


def _parse_dt(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Data Center: 2024-01-02T03:04:05.000+09:00 형식
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


class ConfluenceClient:
    def __init__(self, base_url: Optional[str] = None, *, timeout: float = 60.0):
        self.base_url = (base_url or settings.confluence_base_url).rstrip("/")
        if not self.base_url:
            raise RuntimeError("CONFLUENCE_BASE_URL 이 비어 있습니다.")
        headers = {"Accept": "application/json"}
        if settings.confluence_auth == "bearer":
            headers["Authorization"] = f"Bearer {settings.confluence_token}"
        else:
            cred = base64.b64encode(f"{settings.confluence_user}:{settings.confluence_token}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def _get(self, path: str, params: Optional[dict] = None, *, retries: int = 4) -> httpx.Response:
        delay = 2.0
        for attempt in range(retries + 1):
            res = await self._client.get(path, params=params)
            if res.status_code == 429 or res.status_code >= 500:
                if attempt >= retries:
                    res.raise_for_status()
                retry_after = res.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                logger.warning("confluence %s -> %s, retry in %.0fs", path, res.status_code, wait)
                await asyncio.sleep(wait)
                delay *= 2
                continue
            res.raise_for_status()
            return res
        raise RuntimeError("unreachable")

    # ── 페이지 ────────────────────────────────────────────────────────────────

    def _to_page(self, data: dict) -> ConfluencePage:
        groups = []
        try:
            for g in data["restrictions"]["read"]["restrictions"]["group"]["results"]:
                groups.append(g.get("name") or g.get("id") or "")
        except KeyError:
            pass
        last = (data.get("history") or {}).get("lastUpdated") or {}
        web = (data.get("_links") or {}).get("webui") or ""
        return ConfluencePage(
            id=str(data["id"]),
            space_key=(data.get("space") or {}).get("key", ""),
            title=data.get("title", ""),
            version=int((data.get("version") or {}).get("number", 0)),
            updated_at=_parse_dt(last.get("when") or (data.get("version") or {}).get("when")),
            storage_html=((data.get("body") or {}).get("storage") or {}).get("value", ""),
            ancestors=[a.get("title", "") for a in data.get("ancestors") or []],
            url=self.base_url + web,
            read_groups=[g for g in groups if g],
            raw=data,
        )

    async def iter_pages(self, space_key: str, *, modified_since: Optional[datetime] = None, page_size: int = 50) -> AsyncIterator[ConfluencePage]:
        """공간의 페이지를 CQL 로 순회한다. modified_since 가 있으면 그 이후 수정분만 (증분)."""
        cql = f'space = "{space_key}" AND type = page'
        if modified_since:
            cql += f' AND lastmodified >= "{modified_since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")}"'
        cql += " ORDER BY lastmodified ASC"
        start = 0
        while True:
            res = await self._get("/rest/api/content/search", {"cql": cql, "expand": PAGE_EXPAND, "limit": page_size, "start": start})
            data = res.json()
            results = data.get("results") or []
            for item in results:
                yield self._to_page(item)
            if len(results) < page_size or not (data.get("_links") or {}).get("next"):
                break
            start += page_size

    async def list_page_ids(self, space_key: str, *, page_size: int = 200) -> List[str]:
        """삭제 감지용 — 공간에 현재 존재하는 페이지 id 전체."""
        ids: List[str] = []
        start = 0
        while True:
            res = await self._get("/rest/api/content", {"spaceKey": space_key, "type": "page", "status": "current", "limit": page_size, "start": start})
            data = res.json()
            results = data.get("results") or []
            ids.extend(str(r["id"]) for r in results)
            if len(results) < page_size:
                break
            start += page_size
        return ids

    async def get_page(self, page_id: str) -> ConfluencePage:
        res = await self._get(f"/rest/api/content/{page_id}", {"expand": PAGE_EXPAND})
        return self._to_page(res.json())

    # ── 첨부 ─────────────────────────────────────────────────────────────────

    async def list_attachments(self, page_id: str, *, page_size: int = 100) -> List[ConfluenceAttachment]:
        out: List[ConfluenceAttachment] = []
        start = 0
        while True:
            res = await self._get(f"/rest/api/content/{page_id}/child/attachment", {"expand": "version", "limit": page_size, "start": start})
            data = res.json()
            results = data.get("results") or []
            for a in results:
                ext = (a.get("extensions") or {})
                links = a.get("_links") or {}
                out.append(ConfluenceAttachment(
                    id=str(a["id"]), page_id=page_id, file_name=a.get("title", ""),
                    media_type=ext.get("mediaType", "") or a.get("metadata", {}).get("mediaType", ""),
                    size=int(ext.get("fileSize", 0) or 0),
                    version=int((a.get("version") or {}).get("number", 0)),
                    updated_at=_parse_dt((a.get("version") or {}).get("when")),
                    download_path=links.get("download", ""),
                    url=self.base_url + (links.get("webui") or ""),
                ))
            if len(results) < page_size:
                break
            start += page_size
        return out

    async def download_attachment(self, att: ConfluenceAttachment) -> bytes:
        path = att.download_path
        if not path:
            raise RuntimeError(f"첨부 다운로드 경로가 없습니다: {att.file_name}")
        res = await self._get(path if path.startswith("/") else "/" + path)
        return res.content

    # ── 공간 권한 ─────────────────────────────────────────────────────────────

    async def space_read_groups(self, space_key: str) -> List[str]:
        """공간을 읽을 수 있는 그룹. 조회 실패(권한 부족·DC 버전 차이)면 ['*'] 로 두고 경고만 남긴다."""
        try:
            res = await self._get(f"/rest/api/space/{space_key}", {"expand": "permissions"})
            groups: Dict[str, bool] = {}
            for p in (res.json().get("permissions") or []):
                op = (p.get("operation") or {})
                if op.get("operation") != "read":
                    continue
                subj = (p.get("subjects") or {}).get("group") or {}
                for g in subj.get("results") or []:
                    name = g.get("name") or g.get("id")
                    if name:
                        groups[name] = True
            return list(groups) or ["*"]
        except Exception as e:  # noqa: BLE001
            logger.warning("space permissions unavailable for %s (%s); treating as unrestricted", space_key, e)
            return ["*"]
