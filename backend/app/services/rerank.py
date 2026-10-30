"""리랭킹 — 후보(최대 TOP_K_CANDIDATES)를 질문 대비 채점해 TOP_K_FINAL 개를 고른다.

RERANK_PROVIDER
  none  : RRF 순서를 그대로 쓴다. rerank_score 는 RRF 점수를 0~1 로 정규화한 값 (하한 판정은 건너뛴다)
  local : sentence-transformers CrossEncoder (requirements-optional.txt). 모델은 첫 호출 때 로드한다
  http  : 외부 TEI(Text Embeddings Inference) 서버의 /rerank API 를 호출한다 (RERANK_API_URL)
"""
import asyncio
import logging
from typing import List, Optional, Tuple

import httpx

from app.config import settings
from app.services.retrieval import Candidate

logger = logging.getLogger(__name__)

_model = None
_model_lock = asyncio.Lock()


async def _load_local_model():
    global _model
    if _model is not None:
        return _model
    async with _model_lock:
        if _model is None:
            try:
                from sentence_transformers import CrossEncoder  # type: ignore
            except ImportError as e:  # noqa: BLE001
                raise RuntimeError(
                    "RERANK_PROVIDER=local 이지만 sentence-transformers 가 없습니다. "
                    "pip install -r requirements-optional.txt 또는 RERANK_PROVIDER=none"
                ) from e
            logger.info("loading cross-encoder %s", settings.rerank_model)
            _model = await asyncio.get_event_loop().run_in_executor(None, lambda: CrossEncoder(settings.rerank_model))
    return _model


async def rerank(question: str, candidates: List[Candidate], *, top_k: Optional[int] = None) -> Tuple[List[Candidate], bool]:
    """(상위 top_k 후보, 하한 통과 여부) 를 돌려준다. 후보가 없으면 ([], False)."""
    top_k = top_k or settings.top_k_final
    if not candidates:
        return [], False

    if settings.rerank_provider == "local":
        model = await _load_local_model()
        pairs = [(question, c.content) for c in candidates]
        scores = await asyncio.get_event_loop().run_in_executor(None, lambda: model.predict(pairs))
        for c, s in zip(candidates, scores):
            c.rerank_score = float(s)
        ranked = sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)
        top = ranked[:top_k]
        passed = (top[0].rerank_score or 0.0) >= settings.rerank_min_score
        return top, passed

    if settings.rerank_provider == "http":
        return await _rerank_http(question, candidates, top_k)

    # none: RRF 점수 정규화 (최고점 = 1.0). 하한 판정은 하지 않는다 — 후보가 있으면 답한다
    best = max(c.rrf_score for c in candidates) or 1.0
    for c in candidates:
        c.rerank_score = c.rrf_score / best
    return candidates[:top_k], True


async def _rerank_http(
    question: str, candidates: List[Candidate], top_k: int
) -> Tuple[List[Candidate], bool]:
    """TEI /rerank API 로 후보를 채점해 (상위 top_k, 하한 통과 여부) 를 돌려준다."""
    if not settings.rerank_api_url:
        raise RuntimeError(
            "RERANK_PROVIDER=http 이지만 RERANK_API_URL 이 비어 있습니다. "
            "TEI 서버 베이스 URL 을 설정하세요 (예: http://rerank:8080)"
        )
    url = settings.rerank_api_url.rstrip("/") + "/rerank"
    headers = {"Content-Type": "application/json"}
    if settings.rerank_api_key:
        headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
    payload = {"query": question, "texts": [c.content for c in candidates]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        results = resp.json()  # [{"index": int, "score": float}, ...] — score 내림차순

    for r in results:
        candidates[r["index"]].rerank_score = float(r["score"])
    ranked = sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)
    top = ranked[:top_k]
    passed = (top[0].rerank_score or 0.0) >= settings.rerank_min_score
    return top, passed
