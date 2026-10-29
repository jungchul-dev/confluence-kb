#!/bin/bash
# 동기화 워커 수동 실행: ./sync.sh [--mode full|incremental] [--spaces PROJ,PLAN] [--loop]
set -e
cd "$(dirname "$0")"
source venv/bin/activate
python -m worker.run_sync "$@"
