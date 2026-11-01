"""테이블 정의 — docs/confluence_knowledge_app_design.md §4 와 같다.

documents  : 페이지·첨부 메타 (출처 표시·변경 감지·권한)
chunks     : 검색 단위 (본문 + 임베딩 + tsvector)
sync_state : 페이지별 마지막 동기화 버전
queries    : 질의 로그 (사용 청크·점수·응답 여부)

자료 작성(요구사항 → 목차 · 선별 → (선택) 템플릿 → 생성) — 위 검색 테이블과 분리해 둔다
templates          : 작성 건에 붙인 템플릿 (양식 파일 1개). 미리 등록하지 않고 작성 중에 올린다
draft_references   : 작성 건에 올린 참고 문서 (컨플루언스에 없는 내용, 최대 5개, 파싱 본문)
draft_reference_parts : 참고 문서의 소제목별 부분 + 임베딩 (올릴 때 한 번 계산, 자료 모으기 때 사내 문서와 함께 후보로 찾는다)
template_sections  : 템플릿에서 뽑은 목차 (기록용 — 작성 건 목차는 draft_sections)
drafts             : 작성 건 (이름 · 작성 개요 · 붙인 템플릿)
draft_sections     : 작성 건의 목차 (제안 목차 또는 템플릿 목차) + 생성 결과
draft_files        : 작성 건에 올린 요구사항 파일 (파싱 본문)
draft_requirements : 요구사항 파일에서 뽑은 항목 (목차 배정 · 임베딩)
draft_sources      : 목차별 후보·선별 자료 (조각 내용 사본)
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Computed, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
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


# ───────── 자료 작성 ─────────
# 검색 인덱스(documents · chunks)와 섞지 않는다. 업로드한 요구사항 문서가 일반 검색(/ask · /search)에 나오면 안 되기 때문이다.
# 선별 자료는 chunks.id 를 참조하지 않는다. 재색인 때 청크를 지우고 새로 넣어 id 가 바뀌므로(worker/indexer.py),
# document_id(SET NULL) + heading · ordinal + 내용 사본 + 그때의 content_hash 로 저장한다.


class Template(Base):
    """작성 건에 붙인 템플릿 (작성 건당 1개, 양식 파일). 참고 문서는 draft_references 에 따로 둔다."""

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # 화면 표시용 (올린 파일 이름)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="form")  # form
    # 양식 파일: {{자리 표시}} 가 들어간 docx · pptx 원본. 목차가 되고, 내보낼 때 이 파일에 본문을 채운다
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_bytes: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TemplateSection(Base):
    __tablename__ = "template_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)  # "4. 장애 대응 체계"
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 찾을 내용 (검색 질의)
    guide: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 작성 지침 (형식 · 분량 · 꼭 넣을 것)
    space_keys: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)  # 빈 배열 = 전체 공간
    placeholder: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 템플릿 파일의 {{자리 표시}} 이름

    __table_args__ = (Index("idx_template_sections_template", "template_id", "ordinal"),)


class Draft(Base):
    """작성 건 1개. 목차는 작성 개요 · 요구사항으로 제안받고, 템플릿을 붙이면 템플릿 목차로 바뀐다 (template_id = NULL 이면 템플릿 없이 작성)."""

    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # "3분기 운영 보고서"
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    doc_format: Mapped[str] = mapped_column(String(8), nullable=False, default="docx", server_default="docx")  # docx | pptx (만들 문서 형식)
    overview: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 작성 개요 — 목적 · 대상 · 범위 (검색 질의와 생성 프롬프트에 덧붙인다)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="collecting")  # 쓰지 않음 (화면에서 상태를 관리하지 않는다). 기존 DB 호환용
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("idx_drafts_owner", "owner_id", text("updated_at DESC")),)


class DraftSection(Base):
    __tablename__ = "draft_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    template_section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template_sections.id", ondelete="SET NULL"), nullable=True
    )
    # 제안 목차 또는 템플릿 목차 — 작성 건에서 따로 고칠 수 있다
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    guide: Mapped[str] = mapped_column(Text, nullable=False, default="")
    space_keys: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    placeholder: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 생성 결과 (최신 1개). citations = [{"n": 1, "source_id": "...", "title": "...", "url": "..."}]
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citations: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 생성할 때마다 +1
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_draft_sections_draft", "draft_id", "ordinal"),)


class DraftFile(Base):
    """작성 건에 올린 요구사항 파일 (요청서 · 과업지시서 등). 파싱한 본문만 보관하고 검색 인덱스에는 넣지 않는다."""

    __tablename__ = "draft_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 파싱한 본문 (worker/parsers 재사용)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("idx_draft_files_draft", "draft_id"),)


class DraftRequirement(Base):
    """요구사항 파일에서 뽑은 항목 1개. 목차에 배정해 그 목차의 검색 질의에 덧붙이고, 생성 후 누락 점검에 쓴다."""

    __tablename__ = "draft_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_files.id", ondelete="SET NULL"), nullable=True
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_sections.id", ondelete="SET NULL"), nullable=True
    )  # 배정된 목차 (NULL = 미배정)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 원문 번호 (예: SFR-001)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # chunks 와 같은 모델 · 차원이어야 사내 문서와 바로 비교할 수 있다. 행 수가 적어 벡터 인덱스는 두지 않는다
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    covered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # 생성 결과가 다뤘는지 (점검 전 NULL)
    coverage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 판정 근거 · 빠진 점 한 문장

    __table_args__ = (Index("idx_draft_requirements_draft", "draft_id", "ordinal"),)


class DraftSource(Base):
    """목차별 후보 · 선별 자료 1건. 자동 수집 후보도 남겨 두고 selected 로 고른 것만 생성에 쓴다."""

    __tablename__ = "draft_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_sections.id", ondelete="CASCADE"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")  # auto | manual | requirement
    # 원문 위치 — 문서가 지워지면 document_id 만 NULL 이 되고 아래 사본으로 출처를 계속 보여 준다
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    draft_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_files.id", ondelete="CASCADE"), nullable=True
    )  # origin=requirement 일 때
    # 참고 문서(컨플루언스에 없는 내용)의 부분에서 온 자료. 참고 문서를 지우면 자료도 함께 지워진다
    reference_part_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_reference_parts.id", ondelete="CASCADE"), nullable=True
    )
    doc_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    doc_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    doc_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    heading: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_ordinal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # NULL = 문서 전체
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 고른 시점의 내용 사본
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 고른 시점의 documents.content_hash
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 리랭크 점수 (auto)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 문서 통째로 고정
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_draft_sources_section", "section_id", "selected"),
        Index("idx_draft_sources_document", "document_id"),
    )


class DraftReference(Base):
    """작성 건에 올린 참고 문서 (컨플루언스에 없는 내용을 담은 문서, 작성 건당 최대 5개). 원본은 버리고 파싱 본문만 둔다.
    소제목 단위 부분(draft_reference_parts)이 자료 모으기 때 사내 문서 조각과 함께 후보가 되고, 체크하면 본문의 근거(출처 [n])로 쓴다.
    양식(형식)은 템플릿이 맡는다."""

    __tablename__ = "draft_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")  # "## 소제목" 이 붙은 파싱 본문
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("idx_draft_references_draft", "draft_id", "uploaded_at"),)


class DraftReferencePart(Base):
    """참고 문서의 소제목 단위 부분 = 자료 후보 1건. 임베딩을 올릴 때 한 번만 계산해 두고, 자료 모으기 때 저장된 벡터로 가까운 부분을 찾는다
    (로컬 임베딩 서버는 여러 글을 한꺼번에 보내면 매우 느리므로 모을 때마다 계산하지 않는다)."""

    __tablename__ = "draft_reference_parts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_references.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)  # 소제목 줄 포함, 최대 1,500자
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)

    __table_args__ = (Index("idx_draft_reference_parts_ref", "reference_id", "ordinal"),)
