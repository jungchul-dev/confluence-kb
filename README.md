# confluence-kb

사내 Confluence(제안서·실행 기록)를 검색 가능한 지식베이스로 만들어 근거 있는 답변을 돌려주는 애플리케이션.
설계는 `../testflow-ai/docs/confluence_knowledge_app_design.md`, 구성도는 `../testflow-ai/docs/confluence_knowledge_architecture.drawio` 를 본다.

## 구성과 포트

TestFlow AI(5173 / 8000 / 5432)와 같은 머신에서 함께 띄울 수 있도록 포트·컨테이너 이름·볼륨을 모두 다르게 둔다.

| 구성 요소 | 포트 | 실행 |
|---|---|---|
| `frontend/` React + Vite | **5174** | `cd frontend && ./run.sh` |
| `backend/app` FastAPI API 서버 | **8001** | `cd backend && ./run.sh` |
| `backend/worker` 동기화 워커 | - | `cd backend && ./sync.sh --mode full` |
| `db/` PostgreSQL 16 + pgvector (Docker) | **5433** | `cd db && ./run.sh` (컨테이너 `confluence-kb-postgres`, 볼륨 `confluence-kb-pgdata`) |

## 처음 띄우기

```bash
# 1) DB
cd db && ./run.sh            # 이미지 빌드 + 컨테이너 기동 (--reset: 볼륨 삭제 후 새로)

# 2) 백엔드 설정
cd ../backend
cp .env.example .env         # Confluence URL/토큰, 수집 공간, 모델 API 를 채운다
./run.sh                     # venv 생성 + 의존성 설치 + 8001 기동 (테이블은 기동 시 자동 생성)

# 3) 초기 적재
./sync.sh --mode full        # 설정한 공간 전체를 가져와 색인 (첫 실행은 시간이 걸린다)

# 4) 프론트
cd ../frontend && ./run.sh   # npm install + 개발 서버, http://localhost:5174
```

API 문서: http://localhost:8001/docs

## 동작 개요

- **수집** `worker/run_sync.py` — 공간을 순회하며 페이지 버전·해시를 `sync_state` 와 비교해 바뀐 것만 처리한다. 본문은 헤딩 단위로 청킹하고(`worker/chunker.py`), 허용 확장자의 첨부(pdf·docx·pptx·xlsx·md·txt)는 내려받아 텍스트로 풀어 같은 테이블에 넣는다. 페이지 조회 제한은 `documents.allowed_groups` 로 저장한다.
- **질의** `POST /api/v1/ask` — pgvector 코사인 + tsvector 키워드를 RRF 로 합친 하이브리드 검색(권한 필터 포함) → 리랭킹 → 같은 문서 청크 묶기 → LLM 답변. 답변에는 `[n]` 출처와 수정일이 붙고, 후보가 없으면 "못 찾음"으로 응답한다. `?stream=true` 면 SSE.
- **관리** `GET /api/v1/admin/sync/status`, `POST /api/v1/admin/sync/run` — 공간별 상태와 수동 동기화. 프론트 "동기화" 탭.

## 설정 요약 (`backend/.env`)

| 키 | 설명 |
|---|---|
| `CONFLUENCE_BASE_URL`, `CONFLUENCE_AUTH`, `CONFLUENCE_USER`, `CONFLUENCE_TOKEN` | Cloud 는 `basic`(이메일+API 토큰), Data Center 는 `bearer`(PAT) |
| `CONFLUENCE_SPACES` | 수집 대상 공간 키, 쉼표 구분 |
| `ATTACHMENT_EXTS`, `ATTACHMENT_MAX_MB`, `PDF_OCR` | 첨부 허용 확장자·크기 상한·스캔 PDF OCR 여부 |
| `EMBEDDING_*`, `LLM_*` | OpenAI 호환 API(OpenAI, Ollama `/v1`, vLLM). `EMBEDDING_DIM` 을 바꾸면 전체 재색인 필요 |
| `RERANK_PROVIDER` | `none`(RRF 순서 그대로), `local`(cross-encoder, `requirements-optional.txt` 설치) 또는 `http`(외부 TEI 서버, `RERANK_API_URL`·`RERANK_API_KEY` 설정) |
| `RERANK_MIN_SCORE`, `TOP_K_CANDIDATES`, `TOP_K_FINAL` | 미발견 판정 하한, 1차 후보 수, 최종 청크 수 |
| `USER_ID_HEADER`, `USER_GROUPS_HEADER`, `DEV_USER_GROUPS` | SSO 프록시가 넣는 헤더 이름. 개발 중엔 `DEV_USER_GROUPS=*` 로 전체 열람 |

## 운영 메모

- 증분 동기화는 cron 으로 `./sync.sh --mode incremental` 을 30분마다, 전체 동기화(삭제 페이지 정리 포함)는 야간 1회 `--mode full` 을 권장한다. 단일 프로세스로 돌리려면 `--loop`. 예시는 `deploy/README.md`.
- 임베딩 모델을 바꾸면 `db/run.sh --reset` 후 전체 동기화로 재색인한다.
- `RERANK_PROVIDER=local` 은 torch 를 끌어오므로 서버에 CPU 2코어 이상이 필요하다. 느리면 `none` 으로 두고 운영하다가 붙인다. 별도 bge-reranker TEI 서버가 있다면 `http` 로 두고 `RERANK_API_URL` 만 가리키면 된다(torch 불필요).
- 프론트는 개발 중 `localStorage.userId` / `userGroups` 를 헤더로 보낸다. 운영에서는 SSO 리버스 프록시가 같은 헤더를 넣어야 한다.

## 디렉터리

```
backend/app/     FastAPI (routers: ask · search · admin / services: retrieval · rerank · context · answer · embeddings)
backend/worker/  동기화 워커 (confluence_client · parsers · chunker · indexer · run_sync)
frontend/src/    React (views: Ask · Search · Sync)
db/              Dockerfile · init.sql · run.sh
deploy/          컨테이너·cron 예시
```
