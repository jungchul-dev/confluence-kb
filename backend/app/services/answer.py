"""답변 생성 — OpenAI 호환 /chat/completions. 제공된 문서에만 근거하고 [n] 출처를 달게 한다."""
import json
import logging
from typing import AsyncIterator, List

import httpx

from app.config import settings
from app.services.context import SourceDoc

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 사내 Confluence 문서를 근거로 답하는 어시스턴트입니다.
규칙:
1. 아래 '참고 문서'에 있는 내용으로만 답합니다. 문서에 없는 내용은 추측하지 말고 "문서에서 확인되지 않습니다"라고 말합니다.
2. 근거가 되는 문장 끝에 참고 문서 번호를 [1], [2] 형식으로 붙입니다.
3. 문서끼리 내용이 다르면 수정일이 최근인 문서를 우선하되, 차이가 있다는 점을 밝힙니다.
4. 한국어로, 간결하게, 필요한 경우 목록을 씁니다."""

NOT_FOUND_MESSAGE = "관련 문서를 찾지 못했습니다. 질문을 바꾸거나 아래 비슷한 문서를 확인해 보세요."


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        h["Authorization"] = f"Bearer {settings.llm_api_key}"
    return h


def _messages(question: str, context: str) -> List[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"참고 문서:\n\n{context}\n\n질문: {question}"},
    ]


async def chat(system: str, user: str, *, temperature: float = 0.1, max_tokens: int = 200, timeout: float = 30.0) -> str:
    """범용 단발 호출 (답변 생성 외 용도: 클러스터 이름 짓기 등). 같은 OpenAI 호환 설정을 쓴다."""
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(url, headers=_headers(), json={
            "model": settings.llm_model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        res.raise_for_status()
        return (res.json()["choices"][0]["message"]["content"] or "").strip()


async def generate_answer(question: str, context: str) -> str:
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(url, headers=_headers(), json={
            "model": settings.llm_model, "messages": _messages(question, context), "temperature": 0.1,
        })
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


async def stream_answer(question: str, context: str) -> AsyncIterator[str]:
    """SSE 스트리밍 — 텍스트 조각을 순서대로 낸다."""
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, headers=_headers(), json={
            "model": settings.llm_model, "messages": _messages(question, context), "temperature": 0.1, "stream": True,
        }) as res:
            res.raise_for_status()
            async for line in res.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0]["delta"].get("content")
                except Exception:  # noqa: BLE001
                    continue
                if delta:
                    yield delta


def sources_payload(docs: List[SourceDoc]) -> List[dict]:
    return [
        {
            "index": d.index, "document_id": d.document_id, "title": d.title, "path": d.path, "url": d.url,
            "kind": d.kind, "file_name": d.file_name, "updated_at": d.updated_at, "score": round(d.score, 4),
            "chunk_ids": [str(c.chunk_id) for c in d.chunks],
        }
        for d in docs
    ]
