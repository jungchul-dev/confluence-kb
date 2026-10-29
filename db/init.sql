-- confluence-kb 초기화: 확장만 만든다. 테이블은 애플리케이션(SQLAlchemy create_all)이 만든다.
CREATE EXTENSION IF NOT EXISTS vector;    -- 임베딩 (pgvector)
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 부분 일치 보조 (제목·코드명)
