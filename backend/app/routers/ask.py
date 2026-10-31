"""POST /ask — 질문 → 하이브리드 검색 → 리랭킹 → 맥락 구성 → 답변 생성 → 질의 로그."""
import json
import logging
import uuid
from time import monotonic
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import QueryLog
from app.db.session import AsyncSessionLocal, get_db
from app.permissions import CurrentUser, get_current_user
from app.services import answer as answer_svc
from app.services.context import build_context
from app.services.rerank import rerank
from app.services.retrieval import hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ask", tags=["ask"])


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field("", max_length=20000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: List[HistoryTurn] = Field(default_factory=list, description="이전 대화 (오래된 것부터). 서버가 ASK_HISTORY_TURNS 턴으로 자른다")
    space_key: Optional[List[str]] = Field(None, description="특정 공간만 검색. 없으면 전체.")


class SourceOut(BaseModel):
    index: int
    document_id: str
    title: str
    path: str
    url: str
    kind: str
    file_name: str
    updated_at: str
    score: float
    chunk_ids: List[str]


class AskResponse(BaseModel):
    query_id: str
    found: bool
    search_query: str  # 실제 검색에 쓴 문장 (이어지는 질문이면 이전 대화를 반영해 재작성한 것)
    answer: str
    sources: List[SourceOut]
    top_score: Optional[float] = None
    latency_ms: int


async def _log_query(user: CurrentUser, question: str, chunk_ids: List[uuid.UUID], top: Optional[float], answered: bool, started: float) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        row = QueryLog(user_id=user.id, question=question, chunk_ids=chunk_ids, top_score=top, answered=answered,
                       latency_ms=int((monotonic() - started) * 1000))
        db.add(row)
        await db.commit()
        return row.id


async def _retrieve(db: AsyncSession, search_query: str, user: CurrentUser, space_keys: Optional[List[str]] = None):
    candidates = await hybrid_search(db, search_query, user, space_keys=space_keys)
    top, passed = await rerank(search_query, candidates)
    docs, context = build_context(top)
    top_score = top[0].rerank_score if top else None
    return top, passed, docs, context, top_score


@router.post("", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    stream: bool = Query(False, description="true 면 SSE 로 답변 조각을 스트리밍"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = monotonic()
    question = payload.question.strip()
    history = [h.model_dump() for h in payload.history]
    # 이어지는 질문("그건 누가 승인해?")은 이전 대화를 반영한 독립 문장으로 바꿔 검색한다. 답변 프롬프트에는 원문 질문을 쓴다
    search_query = await answer_svc.rewrite_query(question, history) if history else question
    try:
        top, passed, docs, context, top_score = await _retrieve(db, search_query, user, payload.space_key)
    except Exception as e:  # noqa: BLE001
        logger.error("retrieval failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"검색 단계 실패: {e}")

    sources = answer_svc.sources_payload(docs)
    chunk_ids = [c.chunk_id for c in top]

    if not passed or not docs:
        query_id = await _log_query(user, question, chunk_ids, top_score, False, started)
        body = AskResponse(query_id=str(query_id), found=False, search_query=search_query, answer=answer_svc.NOT_FOUND_MESSAGE,
                           sources=sources, top_score=top_score, latency_ms=int((monotonic() - started) * 1000))
        if not stream:
            return body
        async def not_found_gen():
            yield f"event: meta\ndata: {json.dumps(body.model_dump(), ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        return StreamingResponse(not_found_gen(), media_type="text/event-stream")

    if not stream:
        try:
            text = await answer_svc.generate_answer(question, context, history)
        except Exception as e:  # noqa: BLE001
            logger.error("answer generation failed: %s", e, exc_info=True)
            raise HTTPException(status_code=502, detail=f"답변 생성 실패: {e}")
        query_id = await _log_query(user, question, chunk_ids, top_score, True, started)
        return AskResponse(query_id=str(query_id), found=True, search_query=search_query, answer=text, sources=sources, top_score=top_score,
                           latency_ms=int((monotonic() - started) * 1000))

    async def gen():
        # 먼저 출처(meta)를 보내 UI 가 답변 조각을 받는 동안 출처를 그릴 수 있게 한다
        meta = {"found": True, "sources": sources, "top_score": top_score, "search_query": search_query}
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        try:
            async for delta in answer_svc.stream_answer(question, context, history):
                yield f"event: delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
            query_id = await _log_query(user, question, chunk_ids, top_score, True, started)
            yield f"event: done\ndata: {json.dumps({'query_id': str(query_id), 'latency_ms': int((monotonic() - started) * 1000)})}\n\n"
        except Exception as e:  # noqa: BLE001
            logger.error("answer stream failed: %s", e, exc_info=True)
            yield f"event: error\ndata: {json.dumps({'detail': f'답변 생성 실패: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{query_id}")
async def get_query(query_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(QueryLog).where(QueryLog.id == query_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="질의 기록을 찾을 수 없습니다.")
    return {
        "id": str(row.id), "question": row.question, "chunk_ids": [str(c) for c in row.chunk_ids],
        "top_score": row.top_score, "answered": row.answered, "latency_ms": row.latency_ms,
        "created_at": row.created_at.isoformat(),
    }
