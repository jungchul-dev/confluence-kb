# docs/slide — 데이터 처리 흐름 설명 슬라이드

Confluence KB 가 문서를 어떻게 저장하고 질문에 답하는지를 SVG 애니메이션 다이어그램으로 설명하는 HTML 덱.
화면 캡처 없이 다이어그램이 메인 콘텐츠이고, 모든 장표가 같은 예시(문서 「PROJ > 제안서 > 스마트팩토리 MES 구축 제안」, 질문 「장애 나면 누구한테 에스컬레이션해?」)를 따라간다.
리랭커(bge-reranker-v2-m3, `RERANK_PROVIDER=http`)가 있는 구성을 기준으로 설명한다.

| 파일 | 설명 |
|---|---|
| `index.html` | 덱 본체. 다이어그램 빌더 + 슬라이드 데이터(`SLIDES`) + 렌더/내비게이션 |
| `style.css` | 스타일 (TestFlow AI 데모와 같은 톤) |
| `fonts/` | Pretendard Variable · JetBrains Mono (woff2) |
| `build.sh` | 폰트를 base64 로 인라인하고 압축해 단일 파일 `ConfluenceKB-DataFlow.html` 을 만든다 |

## 장표 구성 (10장)

AI 를 모르는 사람도 따라올 수 있게 장표마다 그림 하나, 비유 한 줄("쉽게 말하면"), 한글 처리 한두 줄만 둔다.

1. 표지 · 목차
2. 한눈에 보기 — 미리 정리해 두기 / 질문하면
3. 문서 나누기 (청킹) — 소제목마다 자르기 → 문장 끝에서 다시 자르기 → 꼬리표
4. 숫자로 바꾸기 (임베딩) — 글을 '뜻 지도' 위 위치로
5. 저장하기 (DB 구성) — 조각 한 줄에 들어가는 것, 문서 정보 1 : 조각 여러 개
6. 저장소에 더한 도구 (PostgreSQL 확장) — pgvector · 형태소 분석기 · IT 용어 사전과 각각 좋아진 점
7. 찾기 (리트리벌) — 뜻으로 찾기 + 단어로 찾기 → 합치기
8. 다시 고르기 (리랭킹) — 재채점 모델로 상위 5개, 관련 없으면 "못 찾음"
9. 답하기 — 고른 글 + 약속 → AI → 출처 달린 답변
10. 주제별로 묶기 (클러스터링) — 문서 지도 → 가까운 것끼리 묶기 → 이름 붙이기, 비슷한 문서 추천

## 보기 · 조작

```bash
cd docs/slide && python3 -m http.server 8080   # http://localhost:8080  (file:// 로 열어도 된다)
```

- `→` / `←` / `Space` 이동, `R` 현재 장표 애니메이션 재생, `N` 발표자 노트, `F` 전체 화면, `Home` / `End`
- 다이어그램 클릭 → 크게 보기 (Esc 닫기)
- `index.html?static#3` 처럼 `?static` 을 붙이면 애니메이션 없이 완성 상태로 그린다 (PDF 인쇄 · 캡처용)

## 단일 파일로 배포

```bash
./build.sh                       # → ConfluenceKB-DataFlow.html (약 2.9MB, 폰트 포함, 오프라인 가능)
./build.sh /tmp/덱.html          # 출력 경로 지정
```

## 수정 방법

- 장표 내용은 `index.html` 의 `SLIDES` 배열. `easy`(쉽게 말하면) · `ko`(한글은 이렇게) · `notes`(발표자 노트) · `diagram`(노드·엣지).
- 다이어그램 노드 종류는 `index.html` 맨 위 주석에 있다 (기본 · text · rows · bars · chips · doc · panel). `[[강조]]`=노드 색, `{{강조}}`=주황.
- 엣지는 `from`/`to` 와 `fromSide`/`toSide`/`via` 로 경로를, `label`·`lx`·`ly` 로 라벨 위치를 정한다. `t` 는 등장 순서(초 단위 배수).
- 뷰박스는 1380 × 730. 텍스트가 박스를 넘치면 `?static` 으로 캡처해 확인한다.
