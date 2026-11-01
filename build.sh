#!/bin/bash
# 发布形态：Next 静态导出 + FastAPI 单进程托管（tech-plan D4）
set -e
cd "$(dirname "$0")"
(cd web && EXPORT_MODE=1 pnpm build)   # 产出 web/out
(cd server && uv sync --frozen 2>/dev/null || uv sync)
echo "构建完成。启动：cd server && uv run uvicorn app.main:app --port 7860"
echo "（web/out 将由 FastAPI 自动挂载为单进程服务）"
