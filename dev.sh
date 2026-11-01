#!/bin/bash
# FilmFlow 开发态：双进程（tech-plan §1.1）—— uvicorn :7860 + next dev :3000
set -e
cd "$(dirname "$0")"
(cd server && exec uv run uvicorn app.main:app --host 127.0.0.1 --port 7860) &
API_PID=$!
(cd web && exec pnpm dev) &
WEB_PID=$!
trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
echo "API  → http://127.0.0.1:7860/api/docs"
echo "Web  → http://127.0.0.1:3000"
wait -n
