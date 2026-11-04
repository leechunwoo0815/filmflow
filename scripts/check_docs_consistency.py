"""判官 §六 #10：文档一致性守卫（把"版本/计数/口径"漂移变成会失败的检查）。

背景：判官 §五-4 指出 `foreign_keys` 在 HANDOFF 里一处说已开、四处说未开；此后每次改动
都要手工回头刷文档，一定会再漂。本脚本把可机检的部分钉住：

1. `EXECUTOR_VERSION`（代码里那份）== 文档里出现的所有版本号；
2. 迁移登记的 version 列表 == 文档里的 `[1,2,…]`；
3. `pytest --collect-only` 的用例数 == 文档声称的 passed 数（允许写成 `N passed` 或 `N passed + M skipped`）；
4. 生产库项目行数 == §7.4 的「DB N 个项目」；
5. `verify_p1_governance.py` 的实际步骤数 == §0.6.3 声称的「N 项」；
6. 一批已知**已经反了**的说法不许再出现（`foreign_keys 仍关闭`、`没有 DELETE /projects` 等）。

用法：`uv run --project server python scripts/check_docs_consistency.py`（只读，不写库）。
退出码非 0 = 有漂移，输出每条不一致的"文件:行 + 现值 vs 文档值"。
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.config import settings
from app.db import MIGRATIONS
from app.engine.cachekey import EXECUTOR_VERSION

DOCS = [ROOT / "HANDOFF.md", ROOT / "AGENTS.md", ROOT / "docs/process/r3_plan.md"]
# 带这些标记的行是历史沿革叙述（某次提交当时的版本、某天的验收），允许出现旧版本号；
# 文档约定：写历史值时不要贴 `EXECUTOR_VERSION=<版本>` 的现值句式，改用「当时」或中文数字描述。
HISTORIC = re.compile(r"当时|旧版|历史|→|[（(]20\d\d-")
BANNED = [
    ("foreign_keys 仍关闭", "FK 已开（db.py 的 PRAGMA），这句是反的"),
    ("**`foreign_keys` 仍关闭**", "同上"),
    ("foreign_keys=ON` 故意没开", "同上"),
    ("foreign_keys 暂不开启", "同上"),
    ("没有 `DELETE /projects/{id}` 端点", "B1 之后该端点存在且是唯一删除入口"),
    ("189 passed", "旧测试数"),
    ("201 passed", "旧测试数"),
    ("219 passed", "旧测试数"),
    ("236 passed", "旧测试数（B5/B6 之后已重测）"),
]


def collect_test_count() -> int:
    out = subprocess.run(["uv", "run", "pytest", "tests", "-q", "--collect-only"],
                         cwd=ROOT / "server", capture_output=True, text=True,
                         check=False)   # 取用例数，非零退出也要能读到 stderr 里的收集错误
    tail = (out.stdout or "").strip().splitlines()
    for line in reversed(tail):
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    raise SystemExit(f"没能从 pytest 输出里取到用例数：\n{out.stdout[-400:]}{out.stderr[-400:]}")


def db_projects() -> int:
    con = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    try:
        return int(con.execute("select count(*) from project").fetchone()[0])
    finally:
        con.close()


def governance_steps() -> int:
    src = (ROOT / "scripts/verify_p1_governance.py").read_text(encoding="utf-8")
    return len(set(re.findall(r'ok\(f?"(\d+[a-z]?)\s', src)))


def lines_with(path: Path, pattern: re.Pattern):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in pattern.finditer(line):
            yield n, line.strip(), m


def main() -> int:
    problems: list[str] = []
    n_tests = collect_test_count()
    n_steps = governance_steps()
    n_projects = db_projects()
    versions = sorted({m[0] for m in MIGRATIONS})
    print(f"现值：EXECUTOR={EXECUTOR_VERSION} · 迁移={versions} · "
          f"collected={n_tests} · governance={n_steps} 步 · DB={n_projects} 项目", flush=True)

    ver_re = re.compile(r"EXECUTOR_VERSION[^0-9]{0,12}(\d+\.\d+\.\d+)")
    for doc in DOCS:
        for n, line, m in lines_with(doc, ver_re):
            if m.group(1) != EXECUTOR_VERSION and not HISTORIC.search(line):
                problems.append(f"{doc.name}:{n} 版本号 {m.group(1)} ≠ 代码里的 {EXECUTOR_VERSION}")
        for n, line, m in lines_with(doc, re.compile(r"迁移登记[^\d]{0,10}\[([0-9,\s]+)\]")):
            got = [int(x) for x in m.group(1).replace(" ", "").split(",") if x]
            if got != versions:
                problems.append(f"{doc.name}:{n} 迁移登记 {got} ≠ 代码里的 {versions}")
        # 约定：文档里 `N passed` 只允许指**当前实测**；历史跑分写中文（如「273 项通过」）
        # 允许 `288 passed + 1 skipped`——环境门控的 skip（如 :8787 被占用）不该让守卫变红
        for n, line, m in lines_with(doc, re.compile(r"(\d+) passed(?: \+ (\d+) skipped)?")):
            claimed = int(m.group(1)) + int(m.group(2) or 0)
            if claimed != n_tests and not HISTORIC.search(line):
                problems.append(f"{doc.name}:{n} 测试数 {m.group(1)} passed"
                                f"{(' + ' + m.group(2) + ' skipped') if m.group(2) else ''}"
                                f" = {claimed} ≠ 实测 collected {n_tests}"
                                "（历史值请写成中文，别用 `N passed`）")
        for n, line, m in lines_with(doc, re.compile(r"(?:连查|复核)\s*\**(\d+) 项")):
            if int(m.group(1)) != n_steps:
                problems.append(f"{doc.name}:{n} 一键复核 {m.group(1)} 项 ≠ 脚本里的 {n_steps} 步")
        for n, line, m in lines_with(doc, re.compile(r"DB \**(\d+) 个项目")):
            if int(m.group(1)) != n_projects:
                problems.append(f"{doc.name}:{n} 「DB {m.group(1)} 个项目」≠ 生产库 {n_projects}")
        for phrase, why in BANNED:
            for n, line, _m in lines_with(doc, re.compile(re.escape(phrase))):
                # 守卫自己在说明"哪些说法已作废"时必然要复述它们，这类行豁免
                if "作废说法" in line or "封禁" in line or "黑名单" in line:
                    continue
                problems.append(f"{doc.name}:{n} 出现已作废说法「{phrase}」——{why}；行：{line[:90]}")

    if problems:
        print(f"\nFAIL: 文档漂移 {len(problems)} 处", flush=True)
        for p in problems:
            print("  -", p, flush=True)
        print("\n修文档就按上面的现值改；改了代码就回来重跑本脚本。", flush=True)
        return 1
    print("PASS: 文档与代码/库/脚本一致（版本、迁移、用例数、复核步数、项目数、作废说法）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
