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
    # H6：BLE001（`except Exception` 盲捕）除了"不许涨"，还要**每批下降**。
    # 只钉不涨的棘轮会允许它一辈子停在原地，而盲捕恰恰是最贵的一类：出问题时最难定位
    # （P2-30 那批 except:pass 的同类），渲染链与交付门禁里的每一次吞异常都可能把
    # "其实失败了"读成"其实成功了"。所以目标值单独成块、单独断言。
    targets = baseline.get("BLE001target") or {}
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
        t = targets.get(label)
        if t is not None:
            got = cur.get("BLE001", 0)
            if got > int(t):
                fail = True
                print(f"✗ {label}.BLE001={got} > 下降目标 {t}——收窄成具体异常类型（每批 -5 是既定节奏）")
            else:
                print(f"✓ {label}.BLE001 下降目标 {t}（现 {got}）")
    if fail:
        return 1
    print("PASS: lint 棘轮三口径全部在基线内（只许降不许涨），BLE001 达到下降目标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
