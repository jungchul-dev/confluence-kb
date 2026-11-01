"""자료 작성 API — 작성 건 · 요구사항 · 목차 · 자료 수집/선별 · 템플릿(선택) · 목차별 생성 · 내보내기.

파일은 multipart 대신 base64 JSON 으로 받는다 (python-multipart 의존성을 늘리지 않기 위해서. 상한 20MB).
템플릿은 미리 등록하지 않고 작성 건마다 자료 선별 뒤에 붙인다(선택). 작성 건은 만든 사람(또는 전체 권한 사용자)만 볼 수 있다.
"""
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    Document, Draft, DraftFile, DraftReference, DraftRequirement, DraftSection, DraftSource, Template,
)
from app.db.session import get_db
from app.permissions import CurrentUser, get_current_user
from app.services import draft_export, drafting

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drafts"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc)


def _decode(data_base64: str) -> bytes:
    try:
        data = base64.b64decode(data_base64.split(",", 1)[-1], validate=False)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="파일 내용을 읽을 수 없습니다 (base64).")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 20MB 를 넘습니다.")
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    return data


class SectionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    query: str = Field("", max_length=2000)
    guide: str = Field("", max_length=4000)


def _tsection_out(s) -> dict:
    return {"id": str(s.id), "ordinal": s.ordinal, "title": s.title, "query": s.query, "guide": s.guide,
            "space_keys": list(s.space_keys or []), "placeholder": s.placeholder}


# ───────── 작성 건 ─────────

class DraftCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    doc_format: str = Field("docx", pattern="^(docx|pptx)$")
    overview: str = Field("", max_length=8000)  # 작성 개요 (목적 · 대상 · 범위)


class DraftUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=300)
    doc_format: Optional[str] = Field(None, pattern="^(docx|pptx)$")
    overview: Optional[str] = Field(None, max_length=8000)


class DraftSectionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    query: Optional[str] = Field(None, max_length=2000)
    guide: Optional[str] = Field(None, max_length=4000)
    space_keys: Optional[List[str]] = None
    body: Optional[str] = None


async def _get_draft(db: AsyncSession, draft_id: uuid.UUID, user: CurrentUser) -> Draft:
    d = (await db.execute(select(Draft).where(Draft.id == draft_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="작성 건을 찾을 수 없습니다.")
    if d.owner_id != user.id and not user.sees_everything:
        raise HTTPException(status_code=403, detail="이 작성 건에 접근할 수 없습니다.")
    return d


async def _get_section(db: AsyncSession, draft: Draft, section_id: uuid.UUID) -> DraftSection:
    s = (await db.execute(select(DraftSection).where(DraftSection.id == section_id, DraftSection.draft_id == draft.id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="목차를 찾을 수 없습니다.")
    return s


def _draft_out(d: Draft, template: Optional[Template] = None) -> dict:
    return {"id": str(d.id), "name": d.name, "template_id": str(d.template_id) if d.template_id else None,
            "template_name": template.name if template else None, "doc_format": d.doc_format,
            "template_form": template.file_name if template and template.file_bytes else None,
"overview": d.overview, "owner_id": d.owner_id,
            "created_at": d.created_at.isoformat() if d.created_at else None, "updated_at": d.updated_at.isoformat() if d.updated_at else None}


def _dsection_out(s: DraftSection, counts: dict, req_counts: dict) -> dict:
    total, selected = counts.get(s.id, (0, 0))
    reqs, covered, uncovered = req_counts.get(s.id, (0, 0, 0))
    return {**_tsection_out(s), "body": s.body, "citations": s.citations or [], "version": s.version,
            "generated_at": s.generated_at.isoformat() if s.generated_at else None,
            "source_count": total, "selected_count": selected, "requirement_count": reqs,
            "covered_count": covered, "uncovered_count": uncovered}


def _req_out(r: DraftRequirement) -> dict:
    return {"id": str(r.id), "ordinal": r.ordinal, "code": r.code, "content": r.content,
            "section_id": str(r.section_id) if r.section_id else None, "file_id": str(r.file_id) if r.file_id else None,
            "covered": r.covered, "coverage_note": r.coverage_note}


async def _draft_detail(db: AsyncSession, d: Draft) -> dict:
    sections = (await db.execute(select(DraftSection).where(DraftSection.draft_id == d.id).order_by(DraftSection.ordinal))).scalars().all()
    src_rows = (await db.execute(select(DraftSource.section_id, DraftSource.selected).where(DraftSource.draft_id == d.id))).all()
    counts: dict = {}
    for sid, sel in src_rows:
        t, s = counts.get(sid, (0, 0))
        counts[sid] = (t + 1, s + (1 if sel else 0))
    reqs = (await db.execute(select(DraftRequirement).where(DraftRequirement.draft_id == d.id).order_by(DraftRequirement.ordinal))).scalars().all()
    req_counts: dict = {}
    for r in reqs:
        if r.section_id:
            n, c, u = req_counts.get(r.section_id, (0, 0, 0))
            req_counts[r.section_id] = (n + 1, c + (1 if r.covered is True else 0), u + (1 if r.covered is False else 0))
    files = (await db.execute(select(DraftFile).where(DraftFile.draft_id == d.id).order_by(DraftFile.uploaded_at))).scalars().all()
    t = None
    if d.template_id:
        t = (await db.execute(select(Template).where(Template.id == d.template_id))).scalar_one_or_none()
    refs = (await db.execute(select(DraftReference).where(DraftReference.draft_id == d.id).order_by(DraftReference.uploaded_at))).scalars().all()
    return {
        **_draft_out(d, t),
        "references": [{"id": str(r.id), "file_name": r.file_name, "chars": len(r.content),
                        "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None} for r in refs],
        "sections": [_dsection_out(s, counts, req_counts) for s in sections],
        "requirements": [_req_out(r) for r in reqs],
        "files": [{"id": str(f.id), "file_name": f.file_name, "size_bytes": f.size_bytes, "chars": len(f.content),
                   "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None} for f in files],
    }


@router.get("/drafts")
async def list_drafts(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """목록용 진행 현황(요구사항 · 고른 자료 · 작성된 목차 수)을 함께 준다."""
    stmt = select(Draft, Template).outerjoin(Template, Template.id == Draft.template_id).order_by(Draft.updated_at.desc())
    if not user.sees_everything:
        stmt = stmt.where(Draft.owner_id == user.id)
    rows = (await db.execute(stmt)).all()
    ids = [d.id for d, _ in rows]
    reqs, srcs, secs = {}, {}, {}
    if ids:
        reqs = dict((await db.execute(select(DraftRequirement.draft_id, func.count()).where(DraftRequirement.draft_id.in_(ids)).group_by(DraftRequirement.draft_id))).all())
        srcs = dict((await db.execute(select(DraftSource.draft_id, func.count()).where(DraftSource.draft_id.in_(ids), DraftSource.selected.is_(True)).group_by(DraftSource.draft_id))).all())
        for did, total, written in (await db.execute(
            select(DraftSection.draft_id, func.count(), func.count(DraftSection.body)).where(DraftSection.draft_id.in_(ids)).group_by(DraftSection.draft_id)
        )).all():
            secs[did] = (total, written)
    return {"drafts": [{**_draft_out(d, t), "requirement_count": reqs.get(d.id, 0), "selected_count": srcs.get(d.id, 0),
                        "section_count": secs.get(d.id, (0, 0))[0], "written_count": secs.get(d.id, (0, 0))[1]} for d, t in rows]}


@router.post("/drafts")
async def create_draft(payload: DraftCreate, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """목차는 비워 두고 만든다. 요구사항을 올린 뒤 목차 제안(/outline) 으로 채운다."""
    d = Draft(name=payload.name, overview=payload.overview, doc_format=payload.doc_format, owner_id=user.id)
    db.add(d)
    await db.commit()
    return await _draft_detail(db, d)


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _draft_detail(db, await _get_draft(db, draft_id, user))


@router.put("/drafts/{draft_id}")
async def update_draft(draft_id: uuid.UUID, payload: DraftUpdate, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    if payload.doc_format and payload.doc_format != d.doc_format and d.template_id:
        t = (await db.execute(select(Template).where(Template.id == d.template_id))).scalar_one_or_none()
        if t and t.file_bytes:
            raise HTTPException(status_code=400, detail=f"{t.file_name} 템플릿이 올라가 있어 문서 형식을 바꿀 수 없습니다. 템플릿 단계에서 지운 뒤 바꾸세요.")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


@router.delete("/drafts/{draft_id}", status_code=204)
async def delete_draft(draft_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    tid = d.template_id
    await db.delete(d)
    await db.flush()
    if tid:
        await _drop_template_if_unused(db, tid)
    await db.commit()
    return Response(status_code=204)


@router.put("/drafts/{draft_id}/sections/{section_id}")
async def update_draft_section(draft_id: uuid.UUID, section_id: uuid.UUID, payload: DraftSectionUpdate,
                               user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    s = await _get_section(db, d, section_id)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


class OutlineRequest(BaseModel):
    replace: bool = Field(False, description="이미 목차가 있어도 새로 제안해 바꾼다")


class SectionOrder(BaseModel):
    ids: List[uuid.UUID]


async def _sections(db: AsyncSession, d: Draft) -> List[DraftSection]:
    return list((await db.execute(select(DraftSection).where(DraftSection.draft_id == d.id).order_by(DraftSection.ordinal))).scalars().all())


@router.post("/drafts/{draft_id}/outline")
async def propose_outline(draft_id: uuid.UUID, payload: OutlineRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """작성 개요 · 요구사항 · 템플릿(자리 표시) · 참고 문서(소제목)를 함께 보고 목차를 제안하고, 요구사항을 새 목차에 배정한다.
    다시 제안하면 고른 자료는 가장 가까운 새 목차로 옮긴다."""
    d = await _get_draft(db, draft_id, user)
    if await _sections(db, d) and not payload.replace:
        raise HTTPException(status_code=409, detail="이미 목차가 있습니다.")
    reqs = (await db.execute(select(DraftRequirement).where(DraftRequirement.draft_id == d.id).order_by(DraftRequirement.ordinal))).scalars().all()
    fixed = None
    t = (await db.execute(select(Template).where(Template.id == d.template_id))).scalar_one_or_none() if d.template_id else None
    if t and t.file_bytes:
        try:
            fixed = drafting.outline_from_file(t.file_name or f"template.{d.doc_format}", t.file_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning("template outline failed, ignoring template: %s", e)
    refs = (await db.execute(select(DraftReference).where(DraftReference.draft_id == d.id).order_by(DraftReference.uploaded_at))).scalars().all()
    references = [(r.file_name, items_) for r in refs if (items_ := drafting.outline_from_reference(r.content))]
    items = await drafting.propose_outline(d, list(reqs), fixed=fixed, references=references or None)
    try:
        await drafting.replace_outline(db, d, items)
    except Exception as e:  # noqa: BLE001
        logger.error("outline replace failed: %s", e, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"목차를 만들지 못했습니다: {e}")
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


@router.post("/drafts/{draft_id}/sections")
async def add_section(draft_id: uuid.UUID, payload: SectionIn, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    n = len(await _sections(db, d))
    db.add(DraftSection(draft_id=d.id, ordinal=n, title=payload.title, query=payload.query or drafting._strip_number(payload.title),
                        guide=payload.guide, space_keys=[]))
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


@router.delete("/drafts/{draft_id}/sections/{section_id}")
async def delete_section(draft_id: uuid.UUID, section_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """목차와 그 목차의 자료를 지운다. 배정된 요구사항은 미배정이 된다."""
    d = await _get_draft(db, draft_id, user)
    s = await _get_section(db, d, section_id)
    await db.execute(DraftRequirement.__table__.update().where(DraftRequirement.section_id == s.id).values(section_id=None))
    await db.delete(s)
    await db.flush()
    for i, x in enumerate(await _sections(db, d)):
        x.ordinal = i
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


@router.put("/drafts/{draft_id}/sections-order")
async def reorder_sections(draft_id: uuid.UUID, payload: SectionOrder, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    by_id = {s.id: s for s in await _sections(db, d)}
    if set(payload.ids) != set(by_id):
        raise HTTPException(status_code=400, detail="목차 목록이 맞지 않습니다. 새로 고친 뒤 다시 하세요.")
    for i, sid in enumerate(payload.ids):
        by_id[sid].ordinal = i
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


# ───────── 요구사항 ─────────

class FileUpload(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=300)
    data_base64: str


class RequirementUpdate(BaseModel):
    section_id: Optional[uuid.UUID] = None
    content: Optional[str] = Field(None, min_length=1, max_length=4000)


class RequirementCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    code: Optional[str] = Field(None, max_length=64)
    section_id: Optional[uuid.UUID] = None


@router.post("/drafts/{draft_id}/files")
async def upload_requirement_file(draft_id: uuid.UUID, payload: FileUpload, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """요구사항 파일 → 본문 파싱 → 항목 추출(LLM) → 임베딩 → 가장 가까운 목차에 배정."""
    d = await _get_draft(db, draft_id, user)
    data = _decode(payload.data_base64)
    try:
        text = drafting.parse_upload(payload.file_name, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.warning("requirement file parse failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"파일을 읽지 못했습니다: {e}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="파일에서 글자를 찾지 못했습니다 (스캔 PDF 라면 OCR 이 필요합니다).")
    f = DraftFile(draft_id=d.id, file_name=payload.file_name, size_bytes=len(data), content=text)
    db.add(f)
    await db.flush()
    items = await drafting.extract_requirements(text)
    start = (await db.execute(select(func.coalesce(func.max(DraftRequirement.ordinal), -1)).where(DraftRequirement.draft_id == d.id))).scalar() + 1
    for i, it in enumerate(items):
        db.add(DraftRequirement(draft_id=d.id, file_id=f.id, ordinal=start + i, code=it["code"], content=it["content"]))
    await db.flush()
    try:
        await drafting.assign_requirements(db, d)
    except Exception as e:  # noqa: BLE001
        logger.warning("requirement assignment failed: %s", e, exc_info=True)
    d.updated_at = _now()
    await db.commit()
    return {**(await _draft_detail(db, d)), "extracted": len(items)}


@router.delete("/drafts/{draft_id}/files/{file_id}", status_code=204)
async def delete_requirement_file(draft_id: uuid.UUID, file_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """파일과 그 파일에서 뽑은 요구사항 항목을 함께 지운다."""
    d = await _get_draft(db, draft_id, user)
    await db.execute(delete(DraftRequirement).where(DraftRequirement.draft_id == d.id, DraftRequirement.file_id == file_id))
    await db.execute(delete(DraftFile).where(DraftFile.draft_id == d.id, DraftFile.id == file_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/drafts/{draft_id}/requirements")
async def add_requirement(draft_id: uuid.UUID, payload: RequirementCreate, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    start = (await db.execute(select(func.coalesce(func.max(DraftRequirement.ordinal), -1)).where(DraftRequirement.draft_id == d.id))).scalar() + 1
    db.add(DraftRequirement(draft_id=d.id, ordinal=start, code=payload.code, content=payload.content, section_id=payload.section_id))
    await db.flush()
    if payload.section_id is None:
        await drafting.assign_requirements(db, d)  # 목차가 아직 없으면 배정하지 않고 둔다
    await db.commit()
    return await _draft_detail(db, d)


@router.put("/drafts/{draft_id}/requirements/{req_id}")
async def update_requirement(draft_id: uuid.UUID, req_id: uuid.UUID, payload: RequirementUpdate,
                             user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    r = (await db.execute(select(DraftRequirement).where(DraftRequirement.id == req_id, DraftRequirement.draft_id == d.id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="요구사항을 찾을 수 없습니다.")
    data = payload.model_dump(exclude_unset=True)
    if "section_id" in data:
        if data["section_id"] is not None:
            await _get_section(db, d, data["section_id"])
        r.section_id = data["section_id"]
        r.covered, r.coverage_note = None, None
    if data.get("content"):
        r.content, r.embedding, r.covered, r.coverage_note = data["content"], None, None, None
    await db.commit()
    return await _draft_detail(db, d)


@router.delete("/drafts/{draft_id}/requirements/{req_id}", status_code=204)
async def delete_requirement(draft_id: uuid.UUID, req_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    await db.execute(delete(DraftRequirement).where(DraftRequirement.id == req_id, DraftRequirement.draft_id == d.id))
    await db.commit()
    return Response(status_code=204)


@router.post("/drafts/{draft_id}/requirements/reassign")
async def reassign_requirements(draft_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """목차를 고친 뒤 요구사항 배정을 처음부터 다시 한다."""
    d = await _get_draft(db, draft_id, user)
    await drafting.assign_requirements(db, d, only_unassigned=False)
    await db.commit()
    return await _draft_detail(db, d)


# ───────── 자료 수집 · 선별 ─────────

class CollectRequest(BaseModel):
    section_id: Optional[uuid.UUID] = Field(None, description="없으면 모든 목차")
    space_keys: List[str] = Field(default_factory=list, description="화면에서 고른 공간. 비우면 전체")


class SourceUpdate(BaseModel):
    selected: Optional[bool] = None
    pinned: Optional[bool] = None


class SourceAdd(BaseModel):
    chunk_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None


def _source_out(s: DraftSource, current_hash: Optional[str], doc_exists: bool) -> dict:
    return {
        "id": str(s.id), "section_id": str(s.section_id), "origin": s.origin,
        "document_id": str(s.document_id) if s.document_id else None, "title": s.doc_title, "path": s.doc_path, "url": s.doc_url,
        "heading": s.heading, "chunk_ordinal": s.chunk_ordinal, "content": s.content, "score": s.score,
        "selected": s.selected, "pinned": s.pinned, "created_at": s.created_at.isoformat() if s.created_at else None,
        "kind": "reference" if s.reference_part_id else "confluence",  # reference = 올린 참고 문서의 부분
        # 원문 상태: ok | changed(고른 뒤 원문이 수정됨) | deleted(원문 삭제됨). 참고 문서는 원문이 컨플루언스에 없으므로 늘 ok
        "source_state": "ok" if s.reference_part_id else "deleted" if not doc_exists else ("changed" if s.content_hash and current_hash and s.content_hash != current_hash else "ok"),
    }


@router.post("/drafts/{draft_id}/collect")
async def collect(draft_id: uuid.UUID, payload: CollectRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    if payload.section_id:
        sections = [await _get_section(db, d, payload.section_id)]
    else:
        sections = list((await db.execute(select(DraftSection).where(DraftSection.draft_id == d.id).order_by(DraftSection.ordinal))).scalars().all())
    added = 0
    try:
        for s in sections:
            added += await drafting.collect_section(db, d, s, user, payload.space_keys or None)
    except Exception as e:  # noqa: BLE001
        logger.error("collect failed: %s", e, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"자료 수집 실패: {e}")
    d.updated_at = _now()
    await db.commit()
    return {**(await _draft_detail(db, d)), "added": added}


@router.get("/drafts/{draft_id}/sections/{section_id}/sources")
async def list_sources(draft_id: uuid.UUID, section_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    s = await _get_section(db, d, section_id)
    rows = (await db.execute(
        select(DraftSource).where(DraftSource.section_id == s.id)
        .order_by(DraftSource.selected.desc(), DraftSource.pinned.desc(), DraftSource.score.desc().nulls_last(), DraftSource.created_at)
    )).scalars().all()
    ids = {r.document_id for r in rows if r.document_id}
    hashes = dict((await db.execute(select(Document.id, Document.content_hash).where(Document.id.in_(list(ids))))).all()) if ids else {}
    return {"sources": [_source_out(r, hashes.get(r.document_id), r.document_id in hashes) for r in rows]}


@router.patch("/drafts/{draft_id}/sources/{source_id}")
async def update_source(draft_id: uuid.UUID, source_id: uuid.UUID, payload: SourceUpdate, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    s = (await db.execute(select(DraftSource).where(DraftSource.id == source_id, DraftSource.draft_id == d.id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    if payload.selected is not None:
        s.selected = payload.selected
    if payload.pinned is not None:
        s.pinned = payload.pinned
        if payload.pinned:
            s.selected = True
    await db.commit()
    return {"id": str(s.id), "selected": s.selected, "pinned": s.pinned}


@router.delete("/drafts/{draft_id}/sources/{source_id}", status_code=204)
async def delete_source(draft_id: uuid.UUID, source_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _get_draft(db, draft_id, user)
    await db.execute(delete(DraftSource).where(DraftSource.id == source_id, DraftSource.draft_id == d.id))
    await db.commit()
    return Response(status_code=204)


@router.post("/drafts/{draft_id}/sections/{section_id}/sources")
async def add_source(draft_id: uuid.UUID, section_id: uuid.UUID, payload: SourceAdd, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """검색 결과의 조각(chunk_id) 또는 문서 전체(document_id) 를 직접 넣는다."""
    if not payload.chunk_id and not payload.document_id:
        raise HTTPException(status_code=400, detail="chunk_id 또는 document_id 가 필요합니다.")
    d = await _get_draft(db, draft_id, user)
    s = await _get_section(db, d, section_id)
    try:
        src = await drafting.add_manual_source(db, d, s, chunk_id=payload.chunk_id, document_id=payload.document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    doc = (await db.execute(select(Document).where(Document.id == src.document_id))).scalar_one()
    if not drafting.user_can_read(doc, user, settings.skip_space_permissions):
        await db.rollback()
        raise HTTPException(status_code=403, detail="열람 권한이 없는 문서입니다.")
    await db.commit()
    return _source_out(src, doc.content_hash, True)


# ───────── 템플릿 · 참고 문서 (선택) ─────────
# 요구사항 다음, 목차를 만들기 전에 올린다. 올리면 저장만 하고, 목차 제안(/outline) · 생성 때 쓴다.
# - 템플릿(작성 건당 1개, templates 1행, docx · pptx · 문서 형식과 같아야 함): {{자리 표시}} 가 목차 제목이 되고, 내보낼 때 이 파일에 채운다
# - 참고 문서(작성 건당 최대 5개, draft_references): 컨플루언스에 없는 내용. 소제목별 부분이 자료 모으기 때 사내 문서와 함께 후보가 된다

class FileIn(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=300)
    data_base64: str


async def _drop_template_if_unused(db: AsyncSession, template_id) -> None:
    used = (await db.execute(select(func.count()).select_from(Draft).where(Draft.template_id == template_id))).scalar()
    if not used:
        await db.execute(delete(Template).where(Template.id == template_id))


async def _finish(db: AsyncSession, d: Draft, result: Optional[dict] = None) -> dict:
    d.updated_at = _now()
    await db.commit()
    return {**(await _draft_detail(db, d)), **(result or {})}


@router.post("/drafts/{draft_id}/template")
async def upload_template(draft_id: uuid.UUID, payload: FileIn, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """템플릿 — 자리 표시(없으면 docx 제목 스타일)가 목차 제목이 된다. 다시 올리면 바꾼다. 목차는 /outline 에서 만든다."""
    d = await _get_draft(db, draft_id, user)
    ext = payload.file_name.rsplit(".", 1)[-1].lower() if "." in payload.file_name else ""
    if ext != d.doc_format:
        raise HTTPException(status_code=400, detail=f"문서 형식이 {d.doc_format} 이므로 템플릿도 .{d.doc_format} 이어야 합니다.")
    data = _decode(payload.data_base64)
    try:
        items = drafting.outline_from_file(payload.file_name, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.warning("template parse failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"템플릿 파일을 읽지 못했습니다: {e}")
    t = (await db.execute(select(Template).where(Template.id == d.template_id))).scalar_one_or_none() if d.template_id else None
    if t is None:
        t = Template(name=payload.file_name, source_kind="form", created_by=user.id)
        db.add(t)
        await db.flush()
        d.template_id = t.id
    t.name, t.file_name, t.file_bytes, t.updated_at = payload.file_name, payload.file_name, data, _now()
    t.description = f"자리 표시 {sum(1 for i in items if i.placeholder)}개" if any(i.placeholder for i in items) else "제목 스타일에서 목차 추출"
    return await _finish(db, d, {"outline_items": len(items)})


@router.delete("/drafts/{draft_id}/template")
async def remove_template(draft_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """템플릿을 지운다. 목차 · 자료 · 본문은 그대로 두고, 내보낼 때 새 파일로 만든다."""
    d = await _get_draft(db, draft_id, user)
    tid = d.template_id
    d.template_id = None
    await db.flush()
    if tid:
        await _drop_template_if_unused(db, tid)
    return await _finish(db, d)


@router.post("/drafts/{draft_id}/references")
async def upload_reference(draft_id: uuid.UUID, payload: FileIn, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """참고 문서 추가 (최대 5개). 소제목 단위로 나눠 임베딩까지 저장해 둔다(문서가 길면 조금 걸린다). 다음 자료 모으기부터 후보에 들어간다."""
    d = await _get_draft(db, draft_id, user)
    n = (await db.execute(select(func.count()).select_from(DraftReference).where(DraftReference.draft_id == d.id))).scalar()
    if n >= drafting.MAX_REFERENCES:
        raise HTTPException(status_code=400, detail=f"참고 문서는 {drafting.MAX_REFERENCES}개까지 올릴 수 있습니다. 하나를 지운 뒤 올리세요.")
    data = _decode(payload.data_base64)
    try:
        text = drafting.parse_upload(payload.file_name, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.warning("reference parse failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"참고 문서를 읽지 못했습니다: {e}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="참고 문서에서 글자를 찾지 못했습니다 (스캔 PDF 라면 OCR 이 필요합니다).")
    ref = DraftReference(draft_id=d.id, file_name=payload.file_name, content=text)
    db.add(ref)
    await db.flush()
    parts = await drafting.build_reference_parts(db, ref)
    return await _finish(db, d, {"reference_parts": parts, "outline_items": len(drafting.outline_from_reference(text))})


@router.delete("/drafts/{draft_id}/references/{reference_id}")
async def remove_reference(draft_id: uuid.UUID, reference_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """참고 문서를 지운다. 부분 · 임베딩과 거기서 온 자료 후보도 함께 지워진다(CASCADE). 목차 · 본문은 그대로 둔다."""
    d = await _get_draft(db, draft_id, user)
    await db.execute(delete(DraftReference).where(DraftReference.id == reference_id, DraftReference.draft_id == d.id))
    return await _finish(db, d)


# ───────── 생성 · 내보내기 ─────────

@router.post("/drafts/{draft_id}/sections/{section_id}/generate")
async def generate(draft_id: uuid.UUID, section_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """목차 하나를 생성한다. 화면은 목차를 하나씩 호출해 진행 상황을 보여 준다."""
    d = await _get_draft(db, draft_id, user)
    s = await _get_section(db, d, section_id)
    try:
        await drafting.generate_section(db, d, s)
    except Exception as e:  # noqa: BLE001
        logger.error("generation failed: %s", e, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"생성 실패: {e}")
    d.updated_at = _now()
    await db.commit()
    return await _draft_detail(db, d)


@router.get("/drafts/{draft_id}/export")
async def export(draft_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """문서 형식(docx | pptx)으로 내보낸다. 양식 파일이 있으면 그 파일에 채우고, 없으면 새로 만든다."""
    d = await _get_draft(db, draft_id, user)
    sections = list((await db.execute(select(DraftSection).where(DraftSection.draft_id == d.id).order_by(DraftSection.ordinal))).scalars().all())
    t = (await db.execute(select(Template).where(Template.id == d.template_id))).scalar_one_or_none() if d.template_id else None
    tbytes = t.file_bytes if t and t.file_bytes else None
    is_pptx = d.doc_format == "pptx"
    try:
        if is_pptx:
            data = draft_export.export_pptx(d, sections, tbytes) if tbytes else draft_export.export_pptx_new(d, sections)
        else:
            data = draft_export.export_docx(d, sections, tbytes)
    except Exception as e:  # noqa: BLE001
        logger.error("export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"내보내기 실패: {e}")
    ext = "pptx" if is_pptx else "docx"
    mime = ("application/vnd.openxmlformats-officedocument.presentationml.presentation" if is_pptx
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    fname = quote(f"{d.name}.{ext}")
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})
