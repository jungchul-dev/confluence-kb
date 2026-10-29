#!/bin/bash
# 프론트 개발 서버 — TestFlow AI(5173)와 겹치지 않게 5174 (vite.config.js 에 고정, /api 는 8001 로 프록시)
set -e
cd "$(dirname "$0")"

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install --no-audit --no-fund
fi

echo "Starting confluence-kb frontend on http://localhost:5174"
npm run dev
