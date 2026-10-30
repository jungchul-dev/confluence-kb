# Confluence 지식 활용 애플리케이션 — 구현 구성안

사내 Confluence(제안서·실행 기록)를 검색 가능한 지식베이스로 만들어 질의응답하는 애플리케이션의 구현 구성이다.
아키텍처 그림은 `docs/confluence_knowledge_architecture.drawio` 를 본다.

## 1. 전체 구성

하나의 PostgreSQL 을 공유하는 두 개의 프로세스와 하나의 UI 로 구성한다.

| 구성 요소 | 형태 | 역할 |
|---|---|---|
| **sync-worker** | 배치 프로세스 (스케줄 실행) | Confluence 에서 페이지·첨부를 받아 파싱 → 청킹 → 임베딩 → DB 적재. 초기 적재와 증분 동기화를 같은 코드로 처리 |
| **api-server** | FastAPI 웹 서버 | 질문을 받아 하이브리드 검색 → 리랭킹 → 답변 생성. 권한 필터와 출처 표시를 담당 |
| **web-ui** | React SPA | 질문 입력, 답변·출처 표시, 검색 결과 열람 |
| **PostgreSQL + pgvector** | DB | 청크(본문·임베딩·메타), 전문검색 인덱스, 동기화 상태 |

외부 의존: Confluence REST API(수집), 임베딩 모델 API, 리랭커(로컬 cross-encoder 또는 API), 답변용 LLM API, 사내 SSO(사용자 식별·그룹).

## 2. 디렉터리 구조

```
confluence-kb/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 진입점
│   │   ├── config.py               # 환경 변수 (Confluence URL/토큰, 모델, 임계값)
│   │   ├── db/
│   │   │   ├── models.py           # 테이블 정의 (아래 4절)
│   │   │   └── session.py
│   │   ├── routers/
│   │   │   ├── ask.py              # POST /ask, GET /ask/{id}
│   │   │   ├── search.py           # GET /search (검색만, 디버그·열람용)
│   │   │   ├── analytics.py        # GET /documents/{id}/related, GET /admin/clusters
│   │   │   └── admin.py            # 동기화 상태·수동 실행
│   │   ├── services/
│   │   │   ├── retrieval.py        # 하이브리드 검색 + 권한 필터
│   │   │   ├── rerank.py           # cross-encoder 리랭킹 + 점수 하한
│   │   │   ├── context.py          # 같은 페이지 묶기, 길이 제한, (선택) 원문 보강
│   │   │   ├── answer.py           # LLM 호출, 출처·수정일 주입, 미발견 응답
│   │   │   └── embeddings.py       # 임베딩 호출 (배치, 재시도)
│   │   └── permissions.py          # SSO 사용자 → Confluence 그룹 매핑
│   └── worker/
│       ├── run_sync.py             # 진입점: 공간 목록 순회
│       ├── confluence_client.py    # REST 호출 (페이지·첨부·버전·권한), 호출 제한 대응
│       ├── parsers/
│       │   ├── html_page.py        # 본문 HTML → 텍스트 (표·매크로 처리)
│       │   ├── office.py           # docx/pptx/xlsx
│       │   ├── pdf.py              # PDF (+ 스캔본 OCR)
│       │   └── registry.py         # 확장자 → 파서 매핑, 허용 목록·크기 상한
│       ├── chunker.py              # 헤딩 단위 분할 + 경로 접두
│       └── indexer.py              # 청크 upsert, 삭제 페이지 정리, 상태 갱신
├── frontend/                       # React (질문/답변/출처 열람)
└── deploy/                         # 컨테이너 정의, 스케줄 설정
```

TestFlow AI 의 `services/rag.py`(pgvector 검색), `services/rerank.py`(cross-encoder), `services/llm_dispatch.py`(모델 호출)는 그대로 옮겨 쓸 수 있다.

## 3. 수집 파이프라인 (sync-worker)

실행 주기는 야간 1회 전체 공간 순회 + 업무 시간 30분 간격 변경분 조회를 기본으로 한다. 둘 다 같은 함수가 처리하고, 차이는 조회 조건뿐이다.

1. **대상 결정** — 설정된 공간 키 목록을 순회. 증분 모드에서는 CQL `lastmodified >= 마지막 성공 시각` 으로 바뀐 페이지만 가져온다.
2. **변경 감지** — 페이지 `version.number` 와 본문 해시를 `sync_state` 와 비교. 같으면 건너뛴다. 삭제·보관된 페이지는 목록에서 빠지므로, 전체 순회 때 `sync_state` 에만 남은 페이지의 청크를 지운다.
3. **파싱** — 본문은 storage 형식 HTML 을 받아 표는 행 단위 문장으로 펴고, 매크로는 종류별 규칙(상태·결정·코드 블록 등)으로 텍스트화한다. 첨부는 허용 확장자(pdf, docx, pptx, xlsx, md, txt)와 크기 상한(예: 20MB) 안에서만 내려받아 텍스트를 뽑는다. 같은 파일의 여러 버전은 최신만 쓴다.
4. **청킹** — 헤딩(h1~h3) 단위로 자르고, 한 섹션이 길면 문단 경계에서 다시 나눈다(목표 400~800 토큰, 겹침 10%). 각 청크 앞에 `공간 > 상위 페이지 > 페이지 제목 > 섹션` 경로를 붙인다. 첨부 청크는 `페이지 제목 > 첨부 파일명 > (슬라이드/시트/페이지 번호)` 를 붙인다.
5. **임베딩** — 청크를 묶어 배치 호출. 실패 시 지수 백오프 재시도, 3회 실패는 `sync_state.error` 에 남기고 다음 페이지로 넘어간다.
6. **적재** — 페이지 단위 트랜잭션으로 기존 청크 삭제 → 새 청크 삽입 → `sync_state` 갱신. 중간에 실패해도 이전 청크가 남아 검색은 계속된다.

권한은 페이지의 조회 제한(`restrictions`)과 공간 권한을 읽어 "읽을 수 있는 그룹 목록"으로 정규화해 청크마다 저장한다. 제한이 없는 페이지는 공간 기본 그룹을 쓴다.

## 4. 데이터 모델

```sql
-- 페이지·첨부 메타 (출처 표시와 변경 감지용)
documents (
  id            uuid primary key,
  space_key     text not null,
  page_id       text not null,            -- Confluence 페이지 id
  attachment_id text,                     -- 첨부면 값 있음, 본문이면 null
  title         text not null,
  path          text not null,            -- "공간 > 상위 > 제목"
  url           text not null,
  version       int  not null,
  content_hash  text not null,
  updated_at    timestamptz not null,     -- Confluence 수정일
  allowed_groups text[] not null,         -- 열람 가능 그룹
  unique (page_id, attachment_id)
)

-- 검색 단위
chunks (
  id          uuid primary key,
  document_id uuid references documents(id) on delete cascade,
  ordinal     int  not null,              -- 문서 내 순서
  heading     text,
  content     text not null,              -- 경로 접두 포함 본문
  embedding   vector(1536) not null,
  tsv         tsvector generated always as (                 -- 한국어 형태소 분석(textsearch_ko 'korean'), 접두 A·본문 B 가중치
                setweight(to_tsvector('korean', <경로 접두>), 'A') || setweight(to_tsvector('korean', <본문>), 'B')) stored,
  token_count int not null
)
-- 인덱스: hnsw (embedding vector_cosine_ops), gin (tsv), btree (document_id)

-- 동기화 상태
sync_state (
  page_id        text primary key,
  space_key      text not null,
  version        int  not null,
  content_hash   text not null,
  synced_at      timestamptz not null,
  error          text
)

-- 질의 로그 (개선·장애 분석용, 본문은 저장하지 않음)
queries (
  id          uuid primary key,
  user_id     text not null,
  question    text not null,
  chunk_ids   uuid[] not null,            -- 최종 사용 청크
  top_score   real,                       -- 리랭커 최고 점수
  answered    boolean not null,           -- 미발견 응답이면 false
  created_at  timestamptz not null
)
```

권한 필터는 `documents.allowed_groups && :user_groups` 조건으로 검색 쿼리 안에서 건다. 검색 후 걸러내면 상위 k 가 줄어들어 품질이 흔들린다.

## 5. 질의 파이프라인 (api-server)

`POST /ask { question }` 한 번에 아래가 순서대로 돈다. 목표 응답 시간은 5초 안.

1. **사용자 식별** — SSO 헤더에서 사용자 id 와 그룹을 얻는다. 그룹은 캐시(5분)한다.
2. **하이브리드 검색** — 질문 임베딩으로 pgvector 코사인 상위 30 + `tsv @@ plainto_tsquery` 상위 30 을 받아 RRF(reciprocal rank fusion)로 합친다. 두 쿼리 모두 권한 필터를 포함한다. 코드명·사람 이름·약어 질문은 키워드 쪽이 잡아 준다.
3. **리랭킹** — 합친 후보(최대 50)를 cross-encoder 로 질문 대비 채점해 상위 5 를 고른다. 최고 점수가 하한(초기값 0.3, 운영하며 조정) 미만이면 생성 단계를 건너뛰고 "관련 문서를 찾지 못했다" 와 가장 가까운 후보 링크만 돌려준다.
4. **맥락 구성** — 같은 문서의 청크는 순서대로 붙이고, 문서별로 제목·경로·URL·수정일 헤더를 단다. 총 길이는 모델 한도의 60% 안으로 자른다. (선택) 상위 1개 문서는 MCP 나 REST 로 본문 전체를 받아 헤더 아래 섹션을 보강한다.
5. **답변 생성** — 시스템 프롬프트에 "제공된 문서에만 근거해 답하고, 각 문장 끝에 [n] 출처 번호를 달며, 문서에 없으면 모른다고 답하라" 를 둔다. 응답에는 본문, 출처 목록(제목·URL·수정일), 사용 청크 id 를 담는다.
6. **기록** — `queries` 에 질문·사용 청크·최고 점수·응답 여부를 남긴다.

### API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/ask` | 질문 → `{ answer, sources[], found, query_id }` (스트리밍은 `?stream=true`) |
| GET | `/search?q=` | 검색 결과만 (청크·점수·문서). 열람·디버그용 |
| GET | `/documents/{page_id}` | 색인된 문서 메타와 청크 목록 |
| GET | `/documents/{page_id}/related?k=5` | 임베딩 유사도 기반 유사 문서 추천 (검색 결과 펼침 시 표시) |
| GET | `/admin/clusters?k=0` | 문서 임베딩 K-Means 클러스터링 (k=0 자동 선택, scikit-learn 필요) |
| GET | `/admin/sync/status` | 공간별 마지막 동기화 시각·실패 건수 |
| POST | `/admin/sync/run` | 공간 지정 수동 동기화 (관리자) |

## 5.1 임베딩 활용 분석 (analytics)

검색 외에 임베딩을 활용하는 두 가지 분석 기능을 제공한다.

### 유사 문서 추천

`GET /documents/{page_id}/related?k=5` — 주어진 문서의 청크 임베딩 평균을 구하고, 다른 문서의 청크 중 코사인 유사도가 가장 높은 상위 k개를 돌려준다. 검색 화면에서 결과를 펼치면 유사 문서가 함께 표시된다. 권한 필터는 검색과 동일하게 적용된다 (`SKIP_SPACE_PERMISSIONS=true` 면 무시).

### 주제 클러스터링

`GET /admin/clusters?k=0` — 문서별 평균 임베딩으로 K-Means 클러스터링을 수행해 주제 그룹을 나눈다. `k=0` 이면 `sqrt(문서수/2)` 로 자동 선택한다. 각 클러스터는 대표 문서(중심에 가장 가까운 5개)와 전체 문서 수를 반환한다. 분석 탭에서 클러스터별 문서 목록을 시각화한다. `scikit-learn` 이 필요하며 (`requirements-optional.txt`), 설치되지 않으면 503 응답을 돌려준다.

## 6. 설정

환경 변수로 둔다.

| 키 | 예시 | 비고 |
|---|---|---|
| `CONFLUENCE_BASE_URL` | `https://xxx.atlassian.net/wiki` | Data Center 면 사내 URL |
| `CONFLUENCE_TOKEN` | API 토큰 | 읽기 전용 서비스 계정 |
| `CONFLUENCE_SPACES` | `PROJ,PLAN` | 수집 대상 공간 키 |
| `ATTACHMENT_EXTS` / `ATTACHMENT_MAX_MB` | `pdf,docx,pptx,xlsx` / `20` | |
| `EMBEDDING_MODEL` / `LLM_MODEL` / `RERANK_MODEL` | | |
| `RERANK_MIN_SCORE` | `0.3` | 미발견 판정 하한 |
| `TOP_K_CANDIDATES` / `TOP_K_FINAL` | `50` / `5` | |
| `SYNC_FULL_CRON` / `SYNC_INCREMENTAL_MINUTES` | `0 2 * * *` / `30` | |

## 7. 배포

- 컨테이너 3개: `api-server`, `web-ui`(정적 파일, nginx), `sync-worker`(스케줄러가 주기 실행). DB 는 기존 PostgreSQL 에 pgvector 확장만 추가.
- 리랭커를 로컬 cross-encoder 로 돌리면 `api-server` 에 CPU 2코어 이상이 필요하다. 응답 지연이 문제면 리랭커 API 로 바꾼다.
- 사내망 밖의 LLM API 를 쓰는 경우, 보내는 내용은 "질문 + 선택된 청크"뿐이라는 점과 보존 정책을 보안 검토에 올린다.

## 8. 단계별 구축 범위

| 단계 | 범위 | 완료 기준 |
|---|---|---|
| 1차 | 공간 1개, 본문만, 전체 동기화 야간 1회, 검색 + 답변 | 질문 20개를 던졌을 때 담당자가 "맞다"고 보는 답이 15개 이상 |
| 2차 | 첨부파일(pdf·pptx·docx·xlsx), 증분 동기화, 권한 필터 | 제한 페이지가 권한 없는 사용자 검색에 나오지 않음 |
| 3차 | 공간 확대, 원문 보강, 질의 로그 기반 개선 | 응답 5초 이내, 미발견 비율 추적 |
| 4차 | 임베딩 활용 분석 — 유사 문서 추천, 주제 클러스터링 | 검색 결과에서 유사 문서 확인, 클러스터별 주제 파악 |

## 9. 처음부터 정해 두면 좋은 것

- 서비스 계정의 Confluence 권한 범위(모든 공간 읽기인지, 지정 공간만인지)와 SSO 그룹과 Confluence 그룹의 매핑 방식.
- 임베딩 모델을 바꾸면 전체 재색인이 필요하므로 모델 선택은 1차 전에 확정한다. `chunks.embedding` 차원도 그때 고정된다.
- 질의 로그에 질문 원문을 남길지 여부(개인정보·보안 검토 대상).
