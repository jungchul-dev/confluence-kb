-- confluence-kb 초기화: 확장만 만든다. 테이블은 애플리케이션(SQLAlchemy create_all)이 만든다.
-- 이 파일은 볼륨이 새로 만들어질 때만 실행된다. 기존 볼륨에 확장을 추가하려면 db/migrate_korean_tsv.sql 을 본다.
CREATE EXTENSION IF NOT EXISTS vector;         -- 임베딩 (pgvector)
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- 부분 일치 보조 (제목·코드명)
CREATE EXTENSION IF NOT EXISTS textsearch_ko;  -- 한국어 형태소 분석 (텍스트 검색 설정 'korean', mecab-ko 기반)
