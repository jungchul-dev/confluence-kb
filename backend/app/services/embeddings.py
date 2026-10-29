"""임베딩 호출 — OpenAI 호환 /embeddings (OpenAI, Ollama /v1, vLLM 등). 배치 + 지수 백오프 재시도."""
import asyncio
import logging
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if settings.embedding_api_key:
        h["Authorization"] = f"Bearer {settings.embedding_api_key}"
    return h


async def embed_texts(texts: List[str], *, retries: int = 3) -> List[List[float]]:
    """텍스트 목록을 임베딩한다. 배치 크기는 EMBEDDING_BATCH_SIZE, 실패는 최대 retries 회 재시도."""
    if not texts:
        return []
    out: List[List[float]] = []
    url = settings.embedding_base_url.rstrip("/") + "/embeddings"
    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(texts), settings.embedding_batch_size):
            batch = texts[i:i + settings.embedding_batch_size]
            delay = 2.0
            for attempt in range(retries + 1):
                try:
                    res = await client.post(url, headers=_headers(), json={"model": settings.embedding_model, "input": batch})
                    res.raise_for_status()
                    data = res.json()["data"]
                    data.sort(key=lambda d: d.get("index", 0))
                    vectors = [d["embedding"] for d in data]
                    if any(len(v) != settings.embedding_dim for v in vectors):
                        raise EmbeddingError(
                            f"임베딩 차원이 설정({settings.embedding_dim})과 다릅니다: {len(vectors[0])}. EMBEDDING_DIM 을 맞추고 재색인하세요."
                        )
                    out.extend(vectors)
                    break
                except EmbeddingError:
                    raise
                except Exception as e:  # noqa: BLE001
                    if attempt >= retries:
                        raise EmbeddingError(f"임베딩 호출 실패: {e}") from e
                    logger.warning("embedding batch failed (attempt %d): %s", attempt + 1, e)
                    await asyncio.sleep(delay)
                    delay *= 2
    return out


async def embed_query(text: str) -> List[float]:
    return (await embed_texts([text]))[0]
