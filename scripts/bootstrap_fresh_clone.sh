#!/usr/bin/env bash
# P1-21：干净机器 fresh-clone 自检/接线（2026-11-05 首版；H4 加 --require-all/--check-only，2026-11-06）。
#
# 只做**检查与提示**，不联网下载任何东西（硬约束：不引入需要联网构建的依赖）。
# 缺什么就按 E_ENV_MISSING 的口径逐条点名，并给出本机怎么补的命令。
#
# 退出码：
#   --require-all（默认，本机口径）：0=全部就绪；1=有缺失。**这才是"READY"这个词被允许出现的条件**。
#   --check-only（CI 口径）：恒 0，但仍逐条打印 ✗ 与 E_ENV_MISSING——Linux runner 上没有 macOS
#     系统 Chrome / 系统字体是本项目的**已知事实**，不是回归；让它在 CI 里红只会把真信号埋掉。
#     CI 要的是"缺哪些、为什么"这份清单进 job summary，而不是一个必然红的步骤。
#
# 为什么这两个模式必须分开：首版只有"报告 + exit 1"，于是文档里"fresh-clone 真闭"和
# runner 上"必然不闭"同时为真——措辞比证据强（复审 H4 抓到的就是这一条）。
set -u
cd "$(dirname "$0")/.."

MODE=require-all
case "${1:-}" in
  --require-all) MODE=require-all ;;
  --check-only) MODE=check-only ;;
  "") ;;
  *) echo "用法：$0 [--require-all|--check-only]" >&2; exit 2 ;;
esac

fail=0
misses=""
ok()   { printf "  ✓ %s\n" "$1"; }
miss() { printf "  ✗ E_ENV_MISSING: %s\n" "$1"; fail=1; misses="${misses}E_ENV_MISSING: $1"$'\n'; }

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
  exit 0
fi

echo "缺失清单（E_ENV_MISSING 逐条）："
printf "%s" "$misses"
echo "补法：uv/ffmpeg 用 brew；Chrome 装系统版；风格库与 rumor-39s 在仓库外（见 vendor/README.md §2）；"
echo "原帧锚随 git 就位，缺它说明 clone 不完整。"

if [ "$MODE" = "check-only" ]; then
  echo "（--check-only：本机口径不算失败——上面这些在 CI/Linux runner 上是**已知缺失**，"
  echo "  报告进 summary，不红。要拿 READY 结论请用 --require-all 在目标机器上跑。）"
  exit 0
fi
echo "NOT READY（--require-all）：先补齐上面标 ✗ 的项（全部是本机资源，不需要联网下载依赖）。"
exit 1
