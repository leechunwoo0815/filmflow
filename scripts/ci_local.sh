#!/usr/bin/env bash
# B8/P1-20 首版；H9（2026-11-06）改成与 **双 job** 一一对应的五步。
#
# 与 .github/workflows/ci.yml 的对应关系：
#   1 ≈ 两个 job 的 lint 步：`ruff check server scripts` 裸跑在存量上必然红（B8 实测 387），
#       改跑 scripts/lint_ratchet.py（与治理第 17 项同一份棘轮，只许降不许涨）
#   2 = ci-lean 的 pytest 步，**并且本机就把 ffmpeg 藏起来**（PATH 只留系统目录 +
#       用 uv 的绝对路径），这样"未标记却依赖环境"的用例在本机就红，不必等 CI
#   3 = ci-env 的 pytest 步（真环境：ffmpeg/风格库/字体都在），本机口径等价
#   4 = web 类型检查（CI 用 pnpm，本机 node_modules 已在，直接 npx）
#   5 = 文档守卫（CI 刻意不含——依赖生产库与运行中的服务；本机增跑）
#
# 用法：bash scripts/ci_local.sh
set -e
cd "$(dirname "$0")/.."

UV_BIN="$(command -v uv)"
LEAN_PATH=/usr/bin:/bin:/usr/sbin:/sbin

echo "== 1/5 ruff 棘轮（serverCwd / repoRootCwd / ciScope 三口径）=="
uv run --project server python scripts/lint_ratchet.py

echo "== 2/5 ci-lean 口径：PATH=$LEAN_PATH（无 ffmpeg）+ 风格库指向不存在 + deselect 环境依赖 =="
# uv 必须用绝对路径：PATH 里已经没有它了。FILMFLOW_STYLE_LIBRARY_ROOT 指到不存在的目录，
# 复刻 runner「341 风格库不入 git」这件事。
(cd server && env PATH="$LEAN_PATH" FILMFLOW_STYLE_LIBRARY_ROOT=/nonexistent-library "$UV_BIN" run \
  pytest tests/unit tests/bdd -q \
  -m "not requires_ffmpeg and not requires_chrome and not requires_style_library and not requires_system_font and not requires_cached_font")

echo "== 3/5 ci-env 口径：真环境跑 unit + bdd（缺环境时 --allow-missing-env 可见 skip）=="
(cd server && uv run pytest tests/unit tests/bdd -q -rs --allow-missing-env)

echo "== 4/5 web tsc --noEmit =="
(cd web && npx tsc --noEmit)

echo "== 5/5 文档守卫（CI 刻意不含，本机增跑）=="
uv run --project server python scripts/check_docs_consistency.py

echo "ci_local: 五步全部通过"
