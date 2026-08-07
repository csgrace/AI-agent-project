#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 启动后端 (FastAPI) ==="
cd "$SCRIPT_DIR/backend"
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload &

echo "=== 启动前端 (Vite) ==="
cd "$SCRIPT_DIR/frontend"
npm run dev &

wait
