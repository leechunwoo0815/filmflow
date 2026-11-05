#!/usr/bin/env bash
# B8/P1-20：CI 四步的本地等价执行（push 未批、Actions 从未真跑——本脚本证明 CI 语义）。
#
# 步骤与 .github/workflows/ci.yml 一一对应：
#   1. ruff —— CI 原写法 `ruff check server scripts` 裸跑在存量上必然红（B8 实测 387），
#      改跑 scripts/lint_ratchet.py（与治理第 17 项同一份棘轮，只许降不许涨）
#   2. pytest unit + bdd（CI 同口径：tests/unit tests/bdd）
#   3. web 类型检查（tsc --noEmit；CI 用 pnpm，本机 node_modules 已在，直接 npx）
#   4. 文档守卫（CI 刻意不含——依赖生产库与运行中的服务；本机跑，作第 4 步）
#
# 用法：bash scripts/ci_local.sh
set -e
cd "$(dirname "$0")/.."

echo "== 1/4 ruff 棘轮（serverCwd / repoRootCwd / ciScope 三口径）=="
uv run --project server python scripts/lint_ratchet.py

echo "== 2/4 pytest unit + bdd =="
(cd server && uv run pytest tests/unit tests/bdd -q)

echo "== 3/4 web tsc --noEmit =="
(cd web && npx tsc --noEmit)

echo "== 4/4 文档守卫（CI 刻意不含，本机增跑）=="
uv run --project server python scripts/check_docs_consistency.py

echo "ci_local: 四步全部通过"
