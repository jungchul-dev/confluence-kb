"""답변 생성 — OpenAI 호환 /chat/completions. 제공된 문서에만 근거하고 [n] 출처를 달게 한다."""
import json
import logging
from typing import AsyncIterator, List, Optional

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


def trim_history(history: Optional[List[dict]], turns: Optional[int] = None) -> List[dict]:
    """이전 대화를 최근 N턴(질문+답변 쌍)으로 자른다. role 은 user/assistant 만 남긴다."""
    turns = settings.ask_history_turns if turns is None else turns
    clean = [{"role": h["role"], "content": str(h.get("content") or "").strip()}
             for h in (history or []) if h.get("role") in ("user", "assistant") and str(h.get("content") or "").strip()]
    return clean[-(turns * 2):] if turns > 0 else []


def _messages(question: str, context: str, history: Optional[List[dict]] = None) -> List[dict]:
    """시스템 프롬프트 + 이전 대화(최근 N턴) + 이번 질문(참고 문서 포함). 참고 문서는 이번 질문에만 붙인다."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs += trim_history(history)
    msgs.append({"role": "user", "content": f"참고 문서:\n\n{context}\n\n질문: {question}"})
    return msgs


REWRITE_PROMPT = """이전 대화를 참고해 사용자의 마지막 질문을, 대화 없이도 뜻이 통하는 '검색용 한 문장'으로 바꿉니다.
규칙: 대명사·생략된 주어("그건", "거기서", "위의")를 이전 대화의 구체적인 대상으로 치환할 것. 질문이 이미 독립적이면 그대로 둘 것.
답변하지 말고 바뀐 질문 한 문장만 출력할 것. 한국어로."""


async def rewrite_query(question: str, history: Optional[List[dict]]) -> str:
    """이어지는 질문을 독립 질문으로 바꿔 검색에 쓴다. 이력이 없거나 호출이 실패하면 원문을 돌려준다."""
    hist = trim_history(history)
    if not hist:
        return question
    convo = "\n".join(f"{'사용자' if h['role'] == 'user' else '어시스턴트'}: {h['content'][:600]}" for h in hist)
    try:
        out = await chat(REWRITE_PROMPT, f"이전 대화:\n{convo}\n\n마지막 질문: {question}\n\n검색용 질문:", temperature=0.1, max_tokens=120, timeout=20.0)
        out = out.strip().strip('"\'').splitlines()[0].strip() if out else ""
        return out if 3 <= len(out) <= 500 else question
    except Exception as e:  # noqa: BLE001
        logger.warning("query rewrite failed, using original: %s", e)
        return question


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


async def generate_answer(question: str, context: str, history: Optional[List[dict]] = None) -> str:
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(url, headers=_headers(), json={
            "model": settings.llm_model, "messages": _messages(question, context, history), "temperature": 0.1,
        })
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


async def stream_answer(question: str, context: str, history: Optional[List[dict]] = None) -> AsyncIterator[str]:
    """SSE 스트리밍 — 텍스트 조각을 순서대로 낸다."""
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, headers=_headers(), json={
            "model": settings.llm_model, "messages": _messages(question, context, history), "temperature": 0.1, "stream": True,
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
