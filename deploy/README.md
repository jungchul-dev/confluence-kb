# 배포 메모

## 컨테이너

| 컨테이너 | 내용 | 포트 |
|---|---|---|
| `confluence-kb-postgres` | `db/Dockerfile` (pgvector/pgvector:pg16) | 5433→5432 |
| `confluence-kb-api` | `backend/` — `uvicorn app.main:app --host 0.0.0.0 --port 8001` | 8001 |
| `confluence-kb-web` | `frontend/dist` 를 nginx 로 서빙, `/api` 를 api 로 프록시 | 5174 |
| `confluence-kb-sync` | `backend/` — `python -m worker.run_sync --mode incremental --loop` (또는 호스트 cron) | - |

## cron 예시 (호스트에서 워커 실행)

```
*/30 * * * *  cd /opt/confluence-kb/backend && ./sync.sh --mode incremental >> /var/log/confluence-kb/sync.log 2>&1
0 2 * * *     cd /opt/confluence-kb/backend && ./sync.sh --mode full        >> /var/log/confluence-kb/sync.log 2>&1
```

## nginx (web → api 프록시, SSO 헤더 전달)

```
location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header X-User-Id     $sso_user;      # SSO 모듈이 채우는 변수
    proxy_set_header X-User-Groups $sso_groups;
    proxy_buffering off;                           # SSE 스트리밍
}
```
