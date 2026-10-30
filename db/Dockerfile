# confluence-kb 전용 PostgreSQL 이미지 — pgvector + 한국어 형태소 분석기(textsearch_ko)
#
# 키워드 검색(tsvector)에 한국어 형태소 분석을 쓰기 위해 mecab-ko · mecab-ko-dic · textsearch_ko 를 소스 빌드한다.
# 빌드 도구는 builder 스테이지에만 두고, 최종 이미지에는 라이브러리·사전·확장 파일만 복사한다.
# 확장은 db/init.sql 의 CREATE EXTENSION textsearch_ko 로 켜지며 텍스트 검색 설정 이름은 'korean' 이다.
# (TestFlow AI 의 Apache AGE 는 쓰지 않는다)

ARG PG_MAJOR=16
ARG MECAB_KO_VERSION=0.996-ko-0.9.2
ARG MECAB_KO_DIC_VERSION=2.1.1-20180720
ARG TEXTSEARCH_KO_REPO=https://github.com/i0seph/textsearch_ko.git

# ── builder ──────────────────────────────────────────────────────────────────
FROM pgvector/pgvector:pg16 AS builder
ARG PG_MAJOR
ARG MECAB_KO_VERSION
ARG MECAB_KO_DIC_VERSION
ARG TEXTSEARCH_KO_REPO

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git wget ca-certificates automake autoconf libtool pkg-config \
      postgresql-server-dev-${PG_MAJOR} \
    && rm -rf /var/lib/apt/lists/*

# mecab-ko (mecab 0.996 한국어 패치판) → /usr/local
RUN cd /tmp \
    && wget -q https://bitbucket.org/eunjeon/mecab-ko/downloads/mecab-${MECAB_KO_VERSION}.tar.gz \
    && tar xzf mecab-${MECAB_KO_VERSION}.tar.gz && cd mecab-${MECAB_KO_VERSION} \
    && ./configure --prefix=/usr/local --with-charset=utf8 \
    && make -j"$(nproc)" && make install && ldconfig

# mecab-ko-dic (사전) → /usr/local/lib/mecab/dic/mecab-ko-dic
RUN cd /tmp \
    && wget -q https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-${MECAB_KO_DIC_VERSION}.tar.gz \
    && tar xzf mecab-ko-dic-${MECAB_KO_DIC_VERSION}.tar.gz && cd mecab-ko-dic-${MECAB_KO_DIC_VERSION} \
    && ./autogen.sh && ./configure --prefix=/usr/local --with-mecab-config=/usr/local/bin/mecab-config \
    && make -j"$(nproc)" && make install \
    && sed -i 's|^dicdir.*|dicdir = /usr/local/lib/mecab/dic/mecab-ko-dic|' /usr/local/etc/mecabrc

# textsearch_ko (PostgreSQL 확장) → ts_mecab_ko.so + textsearch_ko.control/--1.0.sql
RUN cd /tmp && git clone --depth 1 ${TEXTSEARCH_KO_REPO} textsearch_ko && cd textsearch_ko \
    && PATH=/usr/local/bin:/usr/lib/postgresql/${PG_MAJOR}/bin:$PATH make USE_PGXS=1 install \
    && git log -1 --format='%H %cd' > /usr/local/share/textsearch_ko.commit

# ── 최종 이미지 ───────────────────────────────────────────────────────────────
FROM pgvector/pgvector:pg16
ARG PG_MAJOR

COPY --from=builder /usr/local/lib/libmecab.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/mecab /usr/local/lib/mecab
COPY --from=builder /usr/local/etc/mecabrc /usr/local/etc/mecabrc
COPY --from=builder /usr/local/bin/mecab /usr/local/bin/mecab
COPY --from=builder /usr/local/share/textsearch_ko.commit /usr/local/share/textsearch_ko.commit
COPY --from=builder /usr/lib/postgresql/${PG_MAJOR}/lib/ts_mecab_ko.so /usr/lib/postgresql/${PG_MAJOR}/lib/
COPY --from=builder /usr/share/postgresql/${PG_MAJOR}/extension/textsearch_ko* /usr/share/postgresql/${PG_MAJOR}/extension/

RUN ldconfig && echo '형태소 분석기 동작 확인' | mecab -O wakati
