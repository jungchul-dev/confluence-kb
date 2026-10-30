"""테이블 정의 — docs/confluence_knowledge_app_design.md §4 와 같다.

documents  : 페이지·첨부 메타 (출처 표시·변경 감지·권한)
chunks     : 검색 단위 (본문 + 임베딩 + tsvector)
sync_state : 페이지별 마지막 동기화 버전
queries    : 질의 로그 (사용 청크·점수·응답 여부)
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Computed, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_key: Mapped[str] = mapped_column(String(64), nullable=False)
    page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attachment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 본문이면 NULL
    title: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)  # "공간 > 상위 > 제목"
    url: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="page")  # page | attachment
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # Confluence 수정일
    allowed_groups: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)  # ["*"] = 제한 없음
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    # 문서 단위 임베딩 — 제목 + 경로 접두를 뺀 본문 앞부분(DOC_EMBED_CHARS)으로 만든다. 클러스터링(분석) 전용.
    # 청크 임베딩은 경로 접두가 포함돼 있어 "어느 프로젝트인가"가 가장 강한 신호가 되므로 분석에는 쓰지 않는다.
    # 기존 데이터는 backend/migrate_doc_embeddings.py 로 채운다. NULL 이면 분석 API 가 청크 평균으로 대체한다.
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)

    __table_args__ = (
        UniqueConstraint("page_id", "attachment_id", name="uq_documents_page_attachment"),
        Index("idx_documents_space", "space_key"),
        Index("idx_documents_page", "page_id"),
        Index(
            "idx_documents_embedding", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


DOC_EMBED_CHARS = 1200  # 문서 임베딩에 넣는 본문 길이 (제목 제외)
TSV_CONFIG = "korean"  # textsearch_ko 가 만드는 텍스트 검색 설정. 질의 쪽(services/retrieval.py)도 같은 값을 쓴다
TSV_EXPRESSION = (
    f"setweight(to_tsvector('{TSV_CONFIG}', coalesce(substring(content from '^\\[([^\\n]*)\\]'), '')), 'A') || "
    f"setweight(to_tsvector('{TSV_CONFIG}', regexp_replace(content, '^\\[[^\\n]*\\]\\n?', '')), 'B')"
)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 경로 접두 포함
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=False)
    # 키워드 검색용. 한국어 형태소 분석기(textsearch_ko, 설정 'korean')로 조사·어미를 떼고 색인한다.
    # 청크 앞의 "[공간 > 상위 > 제목 > 섹션]" 접두는 A 가중치, 본문은 B 가중치로 분리해 제목·경로 검색은 살리고
    # 접두 토큰이 본문 점수에 섞이지 않게 한다. 식을 바꾸면 db/migrate_korean_tsv.sql 도 같이 바꾼다.
    tsv = mapped_column(TSVECTOR, Computed(TSV_EXPRESSION, persisted=True))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "idx_chunks_embedding", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class SyncState(Base):
    __tablename__ = "sync_state"

    page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    space_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_sync_state_space", "space_key"),)


class SyncRun(Base):
    """동기화 실행 1회 기록 (관리 화면의 상태 표시용)."""

    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_key: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # full | incremental
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")  # running | success | failed
    pages_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachments_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_sync_runs_started", text("started_at DESC")),)


class QueryLog(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_ids: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    top_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("idx_queries_created", text("created_at DESC")),)
