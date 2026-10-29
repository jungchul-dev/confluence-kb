# confluence-kb 전용 PostgreSQL 이미지 — pgvector 만 필요 (TestFlow AI 의 Apache AGE 는 쓰지 않는다)
FROM pgvector/pgvector:pg16

# 한국어 형태소 분석기는 두지 않고 simple 사전 + pg_trgm 로 키워드 검색을 보완한다 (pg_trgm 은 contrib 에 포함)
