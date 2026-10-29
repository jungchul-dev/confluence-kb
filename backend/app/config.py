from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    """환경 변수 설정 (backend/.env). 항목 설명은 .env.example 참고."""

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_env: str = "development"
    cors_origins: List[str] = ["http://localhost:5174"]

    # Confluence
    confluence_base_url: str = ""
    confluence_auth: str = "basic"  # basic | bearer
    confluence_user: str = ""
    confluence_token: str = ""
    confluence_spaces: str = ""  # 쉼표 구분 공간 키
    attachment_exts: str = "pdf,docx,pptx,xlsx,md,txt"
    attachment_max_mb: int = 20
    pdf_ocr: bool = False

    # 모델 (OpenAI 호환 API)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_batch_size: int = 64

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_max_context_tokens: int = 12000  # 맥락에 넣을 청크 총량 상한(토큰 근사치)

    rerank_provider: str = "none"  # none | local
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_min_score: float = 0.3
    top_k_candidates: int = 50
    top_k_final: int = 5

    # 청킹
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 900
    chunk_overlap_ratio: float = 0.1

    # 권한
    user_id_header: str = "X-User-Id"
    user_groups_header: str = "X-User-Groups"
    dev_user_groups: str = "*"

    # 동기화
    sync_incremental_minutes: int = 30

    @property
    def space_keys(self) -> List[str]:
        return [s.strip() for s in self.confluence_spaces.split(",") if s.strip()]

    @property
    def attachment_ext_list(self) -> List[str]:
        return [s.strip().lower().lstrip(".") for s in self.attachment_exts.split(",") if s.strip()]


settings = Settings()
