"""a11y 棘轮（P2-15 的量化基线，老板 2026-11-06 点头新增 eslint/jsx-a11y/typescript-eslint）。

为什么要有它：P2-15 之前只能靠"数一数 aria 出现几次"（现值 1）来申报，
那种口径既抓不住回潮，也抓不住新增。这里把 eslint-plugin-jsx-a11y 的结果钉进
`docs/reports/lint-baseline.json` 的 `a11y` 段——**只许降不许涨**，任何 error 直接红。

用法：
  python3 scripts/lint_a11y.py              # 与基线比对，超了 exit 1
  python3 scripts/lint_a11y.py --update     # 修完之后下调基线（写回 JSON）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
BASELINE = ROOT / "docs" / "reports" / "lint-baseline.json"


def _run_eslint() -> tuple[int, int, int, dict[str, int]]:
    """跑 eslint（JSON formatter），返回 (exit, errors, warnings, 每条规则计数)。"""
    proc = subprocess.run(
        ["pnpm", "exec", "eslint", "src", "-f", "json"],
        cwd=str(WEB), capture_output=True, text=True, check=False, timeout=600,
    )
    if not proc.stdout.strip():
        print(proc.stderr[-2000:])
        raise SystemExit("eslint 没有产出 JSON——先看上面的 stderr")
    data = json.loads(proc.stdout)
    # 只数带 ruleId 的消息：`noInlineConfig` 会为每条历史内联指令产生一条 ruleId=null 的
    # 非 fatal 提示（本机实测 9 条），那是配置噪声不是 a11y 缺陷；但 ruleId=null 且 fatal
    # 的必须算——那是真解析错误。
    errors = warnings = 0
    per_rule: dict[str, int] = {}
    for f in data:
        for m in f["messages"]:
            rid = m.get("ruleId")
            if not rid:
                if m.get("fatal"):
                    errors += 1
                    per_rule["<fatal>"] = per_rule.get("<fatal>", 0) + 1
                else:
                    continue
                continue
            if m["severity"] == 2:
                errors += 1
            else:
                warnings += 1
            per_rule[str(rid)] = per_rule.get(str(rid), 0) + 1
    return proc.returncode, errors, warnings, per_rule


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="把基线下调到当前实测值（修完才用）")
    args = ap.parse_args()

    code, errors, warnings, per_rule = _run_eslint()
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    a11y = base.get("a11y") or {}
    allow_warn = int(a11y.get("warn", -1))
    top = sorted(per_rule.items(), key=lambda x: -x[1])[:6]

    print(f"eslint exit={code} · error={errors} · warn={warnings}"
          f"（基线 warn≤{allow_warn}）")
    for rule, n in top:
        print(f"  {rule:44s} {n}")

    if args.update:
        base["a11y"] = {"warn": warnings, "error": 0,
                        "note": "2026-11-06 建立；P2-15 棘轮，只许降不许涨；降了要 --update 写回"}
        BASELINE.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"基线已下调/建立：warn≤{warnings}")
        return 0

    if errors:
        print(f"FAIL: a11y 有 {errors} 个 error（本配置把所有规则设为 warn，出 error 说明有解析问题）")
        return 1
    if allow_warn < 0:
        print("FAIL: 基线里没有 a11y 段——先跑 `python3 scripts/lint_a11y.py --update` 建立它")
        return 1
    if warnings > allow_warn:
        print(f"FAIL: a11y warn 涨了 {allow_warn} → {warnings}"
              "（P2-15 棘轮只许降；确实要抬高基线，先在台账写理由）")
        return 1
    if warnings < allow_warn:
        print(f"提示: 已降到 {warnings} < {allow_warn}，记得 --update 把收益钉住")
    print("PASS: a11y 棘轮达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
