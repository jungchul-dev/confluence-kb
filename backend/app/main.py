"""confluence-kb API 서버 — 포트 8001 (TestFlow AI 는 8000)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine, ensure_schema
from app.routers import admin, analytics, ask, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()
    logger.info("schema ready; spaces=%s rerank=%s", settings.space_keys, settings.rerank_provider)
    yield
    await engine.dispose()


app = FastAPI(title="confluence-kb", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(ask.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health")
async def health():
    return {
        "status": "ok", "embedding_model": settings.embedding_model, "embedding_dim": settings.embedding_dim,
        "llm_model": settings.llm_model, "rerank_provider": settings.rerank_provider, "spaces": settings.space_keys,
    }
