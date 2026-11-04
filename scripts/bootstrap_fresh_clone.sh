#!/usr/bin/env bash
# P1-21：干净机器 fresh-clone 自检/接线（2026-11-05 首版）。
#
# 只做**检查与提示**，不联网下载任何东西（硬约束：不引入需要联网构建的依赖）。
# 缺什么就按 E_ENV_MISSING 的口径报出来，并给出本机怎么补的命令；全部就绪时
# 打印可以直接跑的验收命令。退出码：0=就绪；1=有缺失（逐条列出）。
#
# 用法：bash scripts/bootstrap_fresh_clone.sh
set -u
cd "$(dirname "$0")/.."

fail=0
ok()   { printf "  ✓ %s\n" "$1"; }
miss() { printf "  ✗ %s\n" "$1"; fail=1; }

echo "== 1. 基础工具 =="
command -v uv >/dev/null 2>&1 && ok "uv $(uv --version 2>/dev/null | head -1)" \
  || miss "uv 未安装（brew install uv）"
command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | cut -c1-40)" \
  || miss "ffmpeg 未安装（brew install ffmpeg）"
PY=$(uv run --project server python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
[ "$PY" = "3.13" ] && ok "python 3.13（uv 托管）" || miss "server 需要 python 3.13，实际 ${PY:-未检出}"

echo "== 2. Chrome（渲染链唯一浏览器，系统 Chrome 而非 playwright 内置）=="
CHROME=""
for p in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
  [ -x "$p" ] && CHROME="$p" && break
done
[ -n "$CHROME" ] && ok "$CHROME" || miss "系统 Chrome 未找到（server/app/config.detect_chrome 依赖它）"

echo "== 3. 341 风格库（库外置不入 git）=="
LIB=$(cat vendor/style-library.path 2>/dev/null)
if [ -n "$LIB" ] && [ -d "$LIB" ]; then
  n=$(find "$LIB/风格提示词" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  ok "${LIB}（风格提示词目录 ${n} 项）"
  [ "$n" = "341" ] || miss "风格提示词应为 341 个，实际 ${n}（库不完整）"
  uv run --project server python vendor/fy-code-animation/scripts/doctor.py --root "$LIB" >/dev/null 2>&1 \
    && ok "doctor.py 自检通过" || miss "doctor.py 自检未通过（python3 vendor/fy-code-animation/scripts/doctor.py --root \"$LIB\"）"
else
  miss "vendor/style-library.path 指向的目录不存在：${LIB:-未设置}（把库放到该路径或改三个登记处，见 vendor/README.md §2）"
fi

echo "== 4. rumor-39s 参考片（46/46 回归基线，仓库外）=="
RUMOR=$(uv run --project server python -c "
import sys; sys.path.insert(0, 'scripts'); sys.path.insert(0, 'server')
try:
    from smoke_m1 import rumor_root; print(rumor_root())
except SystemExit as e:
    print(e); sys.exit(1)
" 2>/dev/null) && [ -d "$RUMOR" ] && ok "$RUMOR" \
  || miss "rumor-39s 未找到（设 FILMFLOW_RUMOR_ROOT 或把参考片放工作区旁）"

echo "== 5. golden 原帧锚（已入 git，随 clone 就位）=="
for d in fixtures/golden/5s fixtures/golden/15s fixtures/golden/40s; do
  c=$(ls "$d"/baseline_original/*.png 2>/dev/null | wc -l | tr -d ' ')
  [ "$c" -ge 6 ] && ok "$d baseline_original $c 帧" || miss "$d 缺原帧锚（$c < 6）"
done

echo "== 6. 本地数据目录（首次运行自动创建）=="
uv run --project server python -c "import sys; sys.path.insert(0, 'server'); from app.config import settings; settings.ensure_dirs(); print(settings.home)" >/dev/null 2>&1 \
  && ok "~/.filmflow 就绪" || miss "~/.filmflow 初始化失败"

echo
if [ "$fail" = "0" ]; then
  echo "READY。建议的验收顺序（HANDOFF §0.2）："
  echo "  ./dev.sh"
  echo "  cd server && uv run pytest tests -q"
  echo "  uv run --project server python scripts/smoke_m1.py"
  echo "  uv run --project server python scripts/golden_run.py --project 5s --resolution original"
else
  echo "NOT READY：先补齐上面标 ✗ 的项（全部是本机资源，不需要联网下载依赖）。"
fi
exit "$fail"
