# Confluence 지식 활용 애플리케이션 — 구현 구성안

사내 Confluence(제안서·실행 기록)를 검색 가능한 지식베이스로 만들어 질의응답하는 애플리케이션의 구현 구성이다.
아키텍처 그림은 `docs/00.architecture.drawio`, 흐름별 상세는 `docs/01.ingest_confluence_to_db.drawio`(수집) · `02.ask_flow.drawio`(질문) · `03.search_flow.drawio`(검색) · `04.analytics_flow.drawio`(분석) 를 본다.

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
│       ├── export_zip.py           # 공간 내보내기(HTML) zip → 페이지·첨부 (API 불가 환경)
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
4. **청킹** — 헤딩(h1~h3) 단위로 자르고, 한 섹션이 길면 문단 경계에서 다시 나눈다(목표 600 · 최대 900 토큰 근사치). 같은 섹션이 여러 청크로 잘릴 때만 직전 청크의 마지막 문장(들)을 10% 길이만큼 앞에 겹쳐 붙이고, 섹션이 바뀌면 겹침을 넣지 않는다 (어절 조각이 섞이지 않게 문장 경계에서만 자른다). 각 청크 앞에 `공간 > 상위 페이지 > 페이지 제목 > 섹션` 경로를 붙인다. 첨부 청크는 `페이지 제목 > 첨부 파일명 > (슬라이드/시트/페이지 번호)` 를 붙인다.
5. **임베딩** — 청크를 묶어 배치 호출. 같은 배치에 문서 1건(제목 + 경로 접두를 뺀 본문 앞 1,200자)을 더 넣어 `documents.embedding` 도 함께 만든다(분석·유사 문서용). 실패 시 지수 백오프 재시도, 3회 실패는 `sync_state.error` 에 남기고 다음 페이지로 넘어간다.
6. **적재** — 문서(페이지 또는 첨부) 단위 트랜잭션으로 기존 청크 삭제 → 새 청크 삽입 → `sync_state` 갱신. 중간에 실패해도 이전 청크가 남아 검색은 계속된다. `chunks.tsv` 는 생성 컬럼이라 적재 시 PostgreSQL 이 한국어 형태소 분석(`textsearch_ko`, 설정 `korean`)으로 자동 계산한다. 경로 접두는 A, 본문은 B 가중치다.

**API 를 쓸 수 없을 때(공간 내보내기 적재)** — 보안정책으로 REST 호출이 막힌 환경에서는 브라우저로 받은 '공간 내보내기(HTML)' zip 을 `./sync.sh --source export --file 공간.zip --space KEY` 로 적재한다. `worker/export_zip.py` 가 zip 의 index.html 트리와 페이지 파일, `attachments/<페이지id>/` 를 읽어 API 와 같은 페이지·첨부 객체를 만들고, 이후 단계(파싱·청킹·임베딩·적재·변경 감지·삭제 정리)는 동일하다. 버전이 없어 본문 해시로만 변경을 감지하고, 수정일은 내보내기 생성 시각(footer), 권한은 `EXPORT_ALLOWED_GROUPS` 의 공간별 그룹을 쓴다. 증분은 없고 항상 전체 적재이며, 이전에 적재한 것보다 오래된 zip 은 거부한다(`--force` 로 무시). 페이지 단위 조회 제한이 중요한 공간은 XML 내보내기 지원이 필요하다(미구현).

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
  embedding     vector(1536),             -- 클러스터링용 문서 임베딩 (제목 + 접두 뺀 본문), hnsw 인덱스
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

### 4.1 자료 작성 테이블

요구사항으로 목차를 정하고 목차별 자료를 모은 뒤, 사람이 고른 자료로 목차별 초안을 만든다. 템플릿은 미리 등록하지 않고 작성 건마다 자료 선별 뒤에 붙인다(선택). 검색 인덱스(`documents`·`chunks`)는 고치지 않고 따로 둔다 — 업로드한 요구사항 문서가 일반 검색에 섞이지 않게 하기 위해서다.

```
templates           작성 건에 붙인 템플릿 1개 (양식 파일 file_bytes={{자리 표시}} docx·pptx · 참고 문서 ref_content=파싱 본문, 둘 중 하나 이상)
 └ template_sections 템플릿에서 뽑은 목차 (기록용)
drafts              작성 건 (doc_format=docx | pptx, overview=작성 개요(목적·대상·범위), template_id=NULL 이면 템플릿 없이 작성)
 ├ draft_sections   목차 (제안 목차 또는 템플릿 목차, title · query=찾을 내용 · guide=작성 지침 · placeholder) + 생성 결과(body · citations · version)
 ├ draft_files      요구사항 파일 (파싱 본문만)
 ├ draft_requirements 요구사항 항목 (section_id=배정 목차, embedding=chunks 와 같은 모델·차원, covered=누락 점검)
 └ draft_sources    목차별 후보·선별 자료 (origin: auto | manual | requirement, selected · pinned)
```

- `draft_sources` 는 `chunks.id` 를 참조하지 않는다. 재색인 때 청크를 지우고 다시 넣어 id 가 바뀌기 때문이다. 대신 `document_id`(ON DELETE SET NULL) + `heading`·`chunk_ordinal` + **내용 사본** + 고른 시점의 `content_hash` 를 저장한다. 원문이 바뀌면 해시 비교로 "원문 수정됨" 을 표시하고, 원문이 지워져도 사본으로 출처를 보여 준다.
- 작성 건을 지우면 하위 행은 모두 지워지고(CASCADE), 그 작성 건에만 붙어 있던 템플릿도 지운다.
- `seed_data.py --reset` 은 전체 테이블을 지우므로 이 테이블들도 비워진다.

### 4.2 자료 작성 흐름 (`app/services/drafting.py`, `app/routers/drafts.py`, 프론트 "자료 작성" 탭)

화면은 작성 건 목록 + 단계별 작성 다이얼로그(기본 정보 → 요구사항 → 템플릿 · 참고 문서 → 목차 · 자료 선별 → 작성 · 검토)다.

1. **기본 정보** — 문서 이름 · 문서 형식(docx 보고서 | pptx 발표 자료) · 작성 개요(목적 · 대상 · 범위)로 작성 건을 만든다. 이때 목차는 비어 있다.
2. **요구사항** — 파일을 수집 파서(`worker/parsers`)로 풀고, LLM 으로 항목(원문 번호 · 내용)을 뽑는다(실패하면 `SFR-001` · `3.2.1` 같은 번호 줄을 항목으로). 요구사항이 없으면 건너뛴다.
3. **템플릿 · 참고 문서 (선택)** — 올리면 저장만 하고, 목차는 다음 단계에서 만든다. ① 템플릿: 문서 형식과 같은 docx · pptx 의 `{{자리 표시}}` 가 목차 제목이 된다(자리 표시가 없는 docx 는 제목 스타일 문단). `{{문서명}}` `{{작성일}}` `{{참고자료}}` 는 예약어로, 목차가 아니라 내보낼 때 채운다. 템플릿이 올라가 있으면 문서 형식을 바꿀 수 없다. ② 참고 문서: 잘 쓴 비슷한 문서(pdf · docx · pptx · md · txt)를 파싱해 둔다. 소제목(페이지 · 시트 번호 같은 기계적 제목 제외, 2개 이상일 때)을 목차 제안의 바탕으로 쓰고, 생성할 때 목차와 같은 제목 또는 임베딩이 가장 가까운 부분(최대 1,000자)을 "형식 예시" 로 넣는다(사실은 옮기지 않도록 지시). 목차를 만든 뒤에 돌아와 바꾸면 [목차 다시 제안받기] 로 반영한다.
4. **목차 제안** — 목차 · 자료 선별로 처음 넘어갈 때 목차가 비어 있으면 LLM 이 이름 · 작성 개요 · 요구사항 · 템플릿 · 참고 문서를 함께 보고 목차(제목 · 찾을 내용 · 작성 지침)를 제안한다. 템플릿이 있으면 제목 · 순서 · 자리 표시는 템플릿 그대로 두고 찾을 내용 · 작성 지침만 채운다. 템플릿 없이 참고 문서만 있으면 그 소제목 구성을 바탕으로 개요 · 요구사항에 맞게 고친다. 둘 다 없으면 4~8개를 새로 짠다(실패하면 템플릿 → 참고 문서 소제목 → 일반 목차). 요구사항은 항목 임베딩과 목차(제목 + 찾을 내용 + 지침) 임베딩의 코사인으로 가장 가까운 목차에 배정한다. 목차는 화면에서 추가 · 삭제 · 순서 변경 · 수정하고, 다시 제안받을 수 있다. 다시 제안하면 **고른 자료는 가장 가까운 새 목차로 옮기고**(색인 때 저장한 `chunks.embedding` · `documents.embedding` 을 재사용, 고르지 않은 후보 · 생성 본문은 버림) 요구사항은 다시 배정한다.
5. **자료 수집** — 목차마다 `찾을 내용 + 배정된 요구사항(앞 3개) + 작성 개요 앞부분` 으로 기존 `hybrid_search` → `rerank` 를 돌려 상위 10개를 후보로, 그중 4개를 선택 상태로 넣는다. 찾는 공간은 화면 위쪽에서 고른 공간(비우면 전체)이다. 다시 모으면 선택하지 않은 자동 후보만 바뀐다.
6. **선별** — 체크(선택) · 고정(문서 통째로) · 삭제, 검색 결과에서 조각 또는 문서 전체를 직접 추가. 원문 해시가 바뀌면 "원문 수정됨", 원문이 지워지면 "원문 삭제됨" 을 표시한다.
7. **생성** — 목차 하나씩: 문서 형식(pptx 면 슬라이드용 개조식) + 작성 개요 + 앞 목차 요약(용어 · 수치 맞추기) + 작성 지침 + 요구사항 + 선택 자료(최대 약 9,000 토큰). 근거 없는 내용은 `[확인 필요: …]`, 출처는 `[n]`. 생성 후 LLM 으로 배정된 요구사항의 반영 여부(`covered`)와 근거(`coverage_note`)를 판정한다. 화면은 목차를 순서대로 하나씩 호출한다(앞 목차 결과가 다음 프롬프트에 들어가기 때문).
8. **내보내기** — `app/services/draft_export.py`. 목차별 출처 번호를 문서 전체 번호로 다시 매긴다. docx 양식이면 자리 표시 문단을 본문(문단 · 목록 · 표)으로 바꾸고, pptx 양식이면 자리 표시 텍스트 상자를 글자로 채운다(표는 `열 | 열` 줄). 양식 파일이 없으면 새로 만든다 — docx: 제목 → 개요 → 목차 → 참고 자료, pptx: 표지 → 작성 개요 → 목차별 슬라이드(### 소제목마다 한 장, 글머리표 8개 넘으면 나눔, 표는 따로 한 장) → 참고 자료. 같은 출처가 겹친 `[1][1]` 은 하나로 합친다.

파일 업로드는 multipart 대신 base64 JSON 으로 받는다(의존성 추가 없음, 상한 20MB). 작성 건(과 거기 붙인 템플릿)은 만든 사람(또는 전체 권한 사용자)만 본다. 자료 수집 · 직접 추가는 기존 권한 필터를 그대로 탄다.

## 5. 질의 파이프라인 (api-server)

`POST /ask { question }` 한 번에 아래가 순서대로 돈다. 목표 응답 시간은 5초 안.

1. **사용자 식별** — SSO 헤더(`X-User-Id`, `X-User-Groups`)에서 사용자 id 와 그룹을 얻는다. 개발 중에는 `DEV_USER_GROUPS` 를 쓴다.
1-1. **이어지는 질문 처리** — 요청의 `history`(이전 질문·답변)를 최근 `ASK_HISTORY_TURNS`(기본 5) 턴으로 자른다. 이력이 있으면 LLM 에게 마지막 질문을 "대화 없이도 뜻이 통하는 검색용 한 문장"으로 바꾸게 해(`search_query`, 예: "그건 얼마나 걸려?" → "운영 배포 승인에 얼마나 걸리나요?") 검색·리랭킹에 쓰고, 답변 프롬프트에는 이력 턴과 원문 질문을 넣는다. 재작성이 실패하면 원문으로 검색한다.
2. **하이브리드 검색** — 질문 임베딩으로 pgvector 코사인 상위 50 + `tsv @@ websearch_to_tsquery('korean')` 상위 50 을 받아 RRF(reciprocal rank fusion, 1/(60+순위))로 합치고 상위 50 후보를 남긴다. 키워드 쪽은 단어를 AND 로 묶어 찾고, 0건이면 OR 로 다시 찾는다(자연어 질문은 단어가 많아 AND 가 자주 비기 때문). 두 쿼리 모두 권한 필터를 포함한다. 코드명·사람 이름·약어 질문은 키워드 쪽이 잡아 준다. 벡터 검색은 항상 50개를 채우므로 후보는 사실상 항상 존재한다.
3. **리랭킹** — 합친 후보(최대 50)를 cross-encoder(`RERANK_PROVIDER=local` 또는 TEI 서버 `http`)로 질문 대비 채점해 상위 5 를 고른다. **1위 점수**가 하한(`RERANK_MIN_SCORE`, 초기값 0.3) 미만이면 생성 단계를 건너뛰고 "관련 문서를 찾지 못했다" 와 가장 가까운 후보 링크만 돌려준다. 1위가 하한을 넘으면 2위 이하는 점수와 상관없이 상위 5 전부가 맥락에 들어간다. `RERANK_PROVIDER=none` 이면 RRF 순서를 그대로 쓰고 하한 판정을 하지 않는다(후보가 있으면 항상 답한다).
4. **맥락 구성** — 같은 문서의 청크는 순서대로 붙이고, 문서별로 제목·경로·URL·수정일 헤더를 단다. 총 길이는 모델 한도의 60% 안으로 자른다. (선택) 상위 1개 문서는 MCP 나 REST 로 본문 전체를 받아 헤더 아래 섹션을 보강한다.
5. **답변 생성** — 시스템 프롬프트에 "제공된 문서에만 근거해 답하고, 각 문장 끝에 [n] 출처 번호를 달며, 문서에 없으면 모른다고 답하라" 를 둔다. 응답에는 본문, 출처 목록(제목·URL·수정일), 사용 청크 id 를 담는다.
6. **기록** — `queries` 에 질문·사용 청크·최고 점수·응답 여부를 남긴다.

### API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/ask` | `{ question, history[] }` → `{ answer, sources[], found, search_query, query_id }` (스트리밍은 `?stream=true`, meta 이벤트에 `search_query` 포함). 질문 탭은 대화 목록으로 보여주고 답변을 누르면 그 턴의 출처가 표시된다 |
| GET | `/search?q=&k=20` | 검색 결과만 (청크 · 벡터/키워드 순위 · RRF/리랭커 점수 · passed 플래그). k 최대 50. 열람·디버그용 |
| GET | `/documents/{page_id}` | 색인된 문서 메타와 청크 목록 |
| GET | `/related-documents?document_id=&k=5` | 문서 임베딩 코사인 유사도 기반 유사 문서 (검색 화면 상세 칸). `/documents/{page_id}/related` 는 페이지 id 로 같은 결과 |
| GET | `/admin/clusters?k=0&llm=true` | 문서 임베딩 K-Means 클러스터링 (k=0 이면 실루엣으로 자동, llm=true 면 LLM 제목, scikit-learn 필요) |
| GET · POST · PUT · DELETE | `/drafts`, `/drafts/{id}` | 작성 건 (목록에 요구사항 · 고른 자료 · 작성된 목차 수 포함) |
| POST · PUT · DELETE | `/drafts/{id}/outline`, `/drafts/{id}/sections[/{sid}]`, `/drafts/{id}/sections-order` | 목차 제안 · 추가 · 수정(본문 직접 수정 포함) · 삭제 · 순서 |
| POST · PUT · DELETE | `/drafts/{id}/files`, `/drafts/{id}/requirements[/{rid}]`, `/drafts/{id}/requirements/reassign` | 요구사항 파일 → 항목 추출 · 목차 배정 |
| POST · GET · PATCH · DELETE | `/drafts/{id}/collect`, `/drafts/{id}/sections/{sid}/sources`, `/drafts/{id}/sources/{src}` | 목차별 자료 수집 · 선별 · 직접 추가 |
| POST · DELETE | `/drafts/{id}/template/form`, `/drafts/{id}/template/reference` | 템플릿 · 참고 문서 올리기(저장만, 목차 제안 때 사용) · 지우기 |
| POST | `/drafts/{id}/sections/{sid}/generate` | 목차 하나 생성 + 요구사항 반영 점검 |
| GET | `/drafts/{id}/export` | 문서 형식(docx | pptx)으로 내려받기 (양식이 있으면 양식에 채움) |
| GET | `/admin/sync/status` | 공간별 마지막 동기화 시각·실패 건수 |
| POST | `/admin/sync/run` | 공간 지정 수동 동기화 (관리자) |

## 5.1 임베딩 활용 분석 (analytics)

검색 외에 임베딩을 활용하는 두 가지 분석 기능을 제공한다.

### 유사 문서 추천

`GET /related-documents?document_id=…&k=5` — 주어진 문서의 `documents.embedding`(제목 + 경로 접두를 뺀 본문)과 다른 문서의 같은 벡터 사이 코사인 유사도 상위 k개를 돌려준다. 문서 임베딩이 없으면 청크 평균으로 대체한다. 검색 화면에서 결과를 클릭하면 오른쪽 상세 칸에 유사도 % 와 함께 표시된다. 권한 필터는 검색과 동일하게 적용된다 (`SKIP_SPACE_PERMISSIONS=true` 면 무시).

### 주제 클러스터링

`GET /admin/clusters?k=0` — 문서 임베딩(`documents.embedding`: 제목 + 경로 접두를 뺀 본문 앞부분)을 길이 정규화한 뒤 K-Means(코사인 기준)로 클러스터링한다. 청크 임베딩 평균을 쓰면 경로 접두 때문에 프로젝트·공간별로 뭉치므로 쓰지 않는다 (문서 임베딩이 없으면 대체). `k=0` 이면 2~min(20, n/5) 범위에서 실루엣 점수가 가장 높은 k 를 고른다. 각 클러스터는 본문(B 가중치) TF-IDF 키워드 상위 10(`keywords`), 대표 문서(중심에 가까운 순, 같은 페이지의 본문·첨부 중복 제거, 5개), 전체 문서 목록을 반환한다. 제목(`label`)은 키워드 10개와 대표 문서 제목 10개를 LLM 에 넘겨 6단어 이내 명사구로 받으며(`llm=true`, 클러스터별 병렬 호출, 문서 id 집합 해시로 캐시), 실패하면 키워드 상위 3개를 이어 붙인 제목으로 대체하고 `label_source` 로 구분한다. 클러스터링에는 본문 임베딩만 쓰고 공간·제목 같은 메타데이터는 쓰지 않는다. 분석 탭은 원형 패킹 차트와 클러스터별 문서 목록(20건 페이징)으로 보여준다. `scikit-learn` 이 필요하며 (`requirements-optional.txt`), 설치되지 않으면 503 응답을 돌려준다.

## 6. 설정

환경 변수로 둔다.

| 키 | 예시 | 비고 |
|---|---|---|
| `CONFLUENCE_BASE_URL` | `https://xxx.atlassian.net/wiki` | Data Center 면 사내 URL |
| `CONFLUENCE_TOKEN` | API 토큰 | 읽기 전용 서비스 계정 |
| `CONFLUENCE_SPACES` | `PROJ,PLAN` | 수집 대상 공간 키 |
| `ATTACHMENT_EXTS` / `ATTACHMENT_MAX_MB` | `pdf,docx,pptx,xlsx` / `20` | |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | OpenAI 호환 URL / 모델 / 차원 | Ollama·vLLM 도 `/v1` 로 사용. 차원을 바꾸면 전체 재색인 |
| `LLM_BASE_URL` / `LLM_MODEL` | OpenAI 호환 URL / 모델 | Anthropic 은 `https://api.anthropic.com/v1` (호환 계층) |
| `RERANK_PROVIDER` / `RERANK_MODEL` / `RERANK_API_URL` | `none` · `local` · `http` | local 은 torch 필요, http 는 TEI `/rerank` |
| `SKIP_SPACE_PERMISSIONS` / `DEV_USER_GROUPS` | `false` / `*` | 검색 시 권한 필터 생략 / 개발용 그룹 |
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

## 10. 운영·개발 보조

- **테스트 데이터** — Confluence 없이 개발할 때는 `backend/seed_data.py` 로 페이지 200건 + 첨부 100건(제안·실행·DevOps·프라이빗 클라우드·네트워크, 공간 PROJ·DEVOPS·CLOUD·NET)을 실제 수집 파이프라인으로 적재한다. 첨부는 docx·pptx·xlsx·pdf·md·txt 바이너리를 실제로 만들어 파서를 거친다.
- **한국어 형태소 사전** — `db/user-dic/*.csv` 에 형태소 분석기가 조각내는 IT 용어(에스컬레이션, 쿠버네티스, 임베딩 등)를 등록한다. 이미지 재빌드 후 `UPDATE chunks SET content = content` 로 `tsv` 를 다시 계산한다.
- **기존 데이터 마이그레이션** — 새 환경은 `init.sql` + `create_all` 로 끝난다. 이 설계 이전에 색인한 데이터가 있으면 `db/migrate_korean_tsv.sql`(한국어 `tsv` 재생성)과 `backend/migrate_doc_embeddings.py`(문서 임베딩 채우기)를 한 번 실행한다. 임베딩 모델을 바꿨을 때는 전체 재색인이 맞다.
