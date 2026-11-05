"""lint 棘轮（A3）：三个口径的总数与黑名单规则对照 docs/reports/lint-baseline.json。

- serverCwd   = `cd server && ruff check .`
- repoRootCwd = 仓库根 `ruff check .`（scripts/ 不继承 server 的 line-length=110）
- ciScope     = `ruff check server scripts`（= .github/workflows/ci.yml 的 lint 步口径）

**只许降不许涨**；上调基线必须先修代码并在台账给理由。verify_p1_governance 第 17 项
与 CI 的 lint 步共用本脚本（CI 直接跑它，首跑即绿且有守卫意义——原 ci.yml 的
`ruff check server scripts` 裸跑在 387 个存量上必然红，2026-11-06 B8 实测发现并改）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUFF = ROOT / "server" / ".venv" / "bin" / "ruff"


def counts(cwd: Path, target: str = ".") -> dict:
    proc = subprocess.run([str(RUFF), "check", *target.split(), "--output-format", "json"],
                          cwd=str(cwd), capture_output=True, text=True, check=False)
    items = json.loads(proc.stdout or "[]")
    agg: dict = {"total": len(items)}
    for it in items:
        agg[it["code"]] = agg.get(it["code"], 0) + 1
    return agg


def main() -> int:
    baseline = json.loads((ROOT / "docs" / "reports" / "lint-baseline.json")
                          .read_text(encoding="utf-8"))
    scopes = [("serverCwd", ROOT / "server", "."),
              ("repoRootCwd", ROOT, "."),
              ("ciScope", ROOT, "server scripts")]
    fail = False
    for label, cwd, target in scopes:
        if label not in baseline:
            continue
        cur = counts(cwd, target)
        limits = baseline[label]
        for key, limit in sorted(limits.items()):
            got = cur.get(key, 0)
            mark = "✓" if got <= limit else "✗"
            if got > limit:
                fail = True
                print(f"✗ {label}.{key}={got} > 棘轮 {limit}——涨了就修代码，不许抬基线")
            else:
                print(f"{mark} {label}.{key}={got}/{limit}")
    if fail:
        return 1
    print("PASS: lint 棘轮三口径全部在基线内（只许降不许涨）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
