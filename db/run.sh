#!/usr/bin/env bash
# confluence-kb PostgreSQL 컨테이너 — TestFlow AI(testflow-postgres:5432)와 이름·볼륨·포트를 모두 다르게 둔다.
set -euo pipefail

CONTAINER=confluence-kb-postgres
VOLUME=confluence-kb-pgdata
IMAGE=confluence-kb-postgres:pg16
PORT=5433
DB=confluence_kb
DB_USER=postgres
DB_PASSWORD=password

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RESET=0

for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    -h|--help)
      cat <<USAGE
Usage: ./run.sh [--reset]

  --reset   Drop existing volume to start with an empty database.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if sudo docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "[*] Stopping existing container: ${CONTAINER}"
  sudo docker stop "${CONTAINER}" >/dev/null 2>&1 || true
  sudo docker rm "${CONTAINER}" >/dev/null 2>&1 || true
fi

if [ "${RESET}" -eq 1 ]; then
  if sudo docker volume ls --format '{{.Name}}' | grep -q "^${VOLUME}$"; then
    echo "[*] Removing volume: ${VOLUME}"
    sudo docker volume rm "${VOLUME}" >/dev/null
  fi
fi

echo "[*] Building image: ${IMAGE} (pgvector)"
BUILD_ARGS=()
[ -n "${http_proxy:-}" ]  && BUILD_ARGS+=(--build-arg http_proxy="$http_proxy")
[ -n "${https_proxy:-}" ] && BUILD_ARGS+=(--build-arg https_proxy="$https_proxy")
[ -n "${HTTP_PROXY:-}" ]  && BUILD_ARGS+=(--build-arg HTTP_PROXY="$HTTP_PROXY")
[ -n "${HTTPS_PROXY:-}" ] && BUILD_ARGS+=(--build-arg HTTPS_PROXY="$HTTPS_PROXY")
[ -n "${no_proxy:-}" ]    && BUILD_ARGS+=(--build-arg no_proxy="$no_proxy")
[ -n "${NO_PROXY:-}" ]    && BUILD_ARGS+=(--build-arg NO_PROXY="$NO_PROXY")
sudo docker build "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}" -t "${IMAGE}" "${SCRIPT_DIR}"

echo "[*] Starting ${CONTAINER} on port ${PORT}"
sudo docker run -d \
  --name "${CONTAINER}" \
  --restart unless-stopped \
  -e POSTGRES_USER="${DB_USER}" \
  -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
  -e POSTGRES_DB="${DB}" \
  -p "${PORT}:5432" \
  -v "${VOLUME}:/var/lib/postgresql/data" \
  -v "${SCRIPT_DIR}/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  "${IMAGE}" >/dev/null

echo "[*] Waiting for postgres to accept connections..."
for i in $(seq 1 30); do
  if sudo docker exec "${CONTAINER}" pg_isready -U "${DB_USER}" -d "${DB}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [ "${i}" -eq 30 ]; then
    echo "[!] postgres did not become ready in time" >&2
    sudo docker logs "${CONTAINER}" --tail 50 >&2
    exit 1
  fi
done
sleep 3

VECTOR_VERSION=$(sudo docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB}" -tAc \
  "SELECT extversion FROM pg_extension WHERE extname='vector';")
if [ -z "${VECTOR_VERSION}" ]; then
  echo "[!] pgvector extension not found" >&2
  exit 1
fi

echo ""
echo "[OK] postgres ready (pgvector ${VECTOR_VERSION})"
echo "     DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:${PORT}/${DB}"
