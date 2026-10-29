#!/bin/bash
# API 서버 — TestFlow AI(8000)와 겹치지 않게 8001 을 쓴다.
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "Installing dependencies..."
pip install -r requirements.txt -q

echo "Starting confluence-kb API on http://localhost:8001"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
