#!/bin/bash
# FilmFlow 开发态：双进程（tech-plan §1.1）—— uvicorn :7860 + next dev :3000
set -e
cd "$(dirname "$0")"
# 本机产品不许打电话回家：Next dev 默认会向 Vercel 遥测端点发数据（实测 `lsof -p <node pid>` 里
# 有一条 104.16.x:443 的 ESTABLISHED）。FR-41 判据③"进程无外部请求"要能对整个工作台成立，
# 所以这里连同 next.config.mjs 的 telemetry.enabled=false 一起关掉。
export NEXT_TELEMETRY_DISABLED=1
(cd server && exec uv run uvicorn app.main:app --host 127.0.0.1 --port 7860) &
API_PID=$!
(cd web && exec pnpm dev) &
WEB_PID=$!
trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
echo "API  → http://127.0.0.1:7860/api/docs"
echo "Web  → http://127.0.0.1:3000"
# macOS 自带 bash 3.2 不支持 wait -n；轮询到任一子进程退出（trap 负责清理另一个）
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
