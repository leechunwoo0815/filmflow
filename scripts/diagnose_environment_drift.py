"""H10：渲染环境漂移的**诊断**与重锚流程（老板 2026-11-06 明确选"漂移即诊断"，不是硬失败）。

要解决的问题很具体：SSIM 掉的时候，光看报告分不清是"代码回归"还是"环境变了"
（Chrome 自动升级、ffmpeg 换版、字体换文件、风格库改内容都会改像素）。
以前这一步靠人肉读 golden 报告里的 `environment` 块对比，等于没有防线。

三个设计决定，都不是审美选择：
1. **漂移时 exit 0**。这是老板选的口径：环境升级是日常，把它做成门禁会把整夜自主循环直接锁死，
   而锁死之后没有防线比有防线更糟。诊断的输出必须**自带下一步动作**（重锚命令），
   这才是这条防线真正的价值所在。
2. **判据与 `golden_run._environment` 同源**（同一个函数产生当前指纹），
   不然"守卫说的环境"和"报告里的环境"会变成两套话——这类分叉在本仓库已经出现过多次。
3. **重锚的理由要与当时真实环境互证**（`corroborate`）：
   凡是理由里说"因为环境/版本变了"的记录，锚点序列里那一次必须**真的**能看到环境差异。
   没有差异却说环境变了 = 拿"环境漂了"当掩盖回归的借口，这条断言专门拦它。

用法：
    uv run --project server python scripts/diagnose_environment_drift.py            # 人读
    uv run --project server python scripts/diagnose_environment_drift.py --quiet     # 只在漂移时输出
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

REPORT_DIR = ROOT / "docs" / "reports" / "golden"
INDEX = REPORT_DIR / "index.json"

# 报告里没有的键（历史报告字段比现在少）不参与漂移判定，单独列出
ENV_KEYS = ("executorVersion", "rendererVersion", "chrome", "ffmpeg",
            "fontSha256", "styleLibraryStatsSha256", "fpscalcSha256", "os", "python")
# 两类声称必须分开——这条区分来自实测，不是文字洁癖：
# 真实那条 B3 重锚理由写的是 `EXECUTOR 2.17.0 / RENDERER preview-2.1.0`，
# 那是**代码升版**（环境没变、像素按设计变），不是"环境变了"。
# 混成一条正则的话，互证会去要求 Chrome/ffmpeg 前后不同，永远对不上 → 把正确行为判成违规。
ENV_CLAIM_RE = re.compile(r"环境|Chrome|ffmpeg|字体|风格库|系统升级|brew", re.IGNORECASE)
CODE_CLAIM_RE = re.compile(r"EXECUTOR|RENDERER|升版|版本", re.IGNORECASE)
_CODE_KEYS = ("executorVersion", "rendererVersion")


def current_environment() -> dict:
    """当前环境指纹——直接复用 golden_run 的那一份实现（单一真源）。"""
    from app.config import settings
    from golden_run import _environment

    return _environment(Path(settings.home))


def anchor_environment(project: str | None = None) -> tuple[dict, str]:
    """最近一次锚定的报告及其文件名。优先 index（有序台账），回落到目录里最新的报告文件。"""
    names: list[str] = []
    if INDEX.exists():
        items = json.loads(INDEX.read_text(encoding="utf-8")).get("items") or []
        if project:
            items = [i for i in items if i.get("project") == project]
        for it in sorted(items, key=lambda i: str(i.get("at") or ""), reverse=True):
            if it.get("reportFile"):
                names.append(it["reportFile"])
    if not names:
        cand = sorted((REPORT_DIR / project).glob("*.json") if project else REPORT_DIR.glob("*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        names = [p.name for p in cand if p.name != "index.json"]
    for n in names:
        p = REPORT_DIR / n
        if not p.exists():
            continue
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        env = rep.get("environment") or {}
        if env:
            return env, n
    return {}, ""


def diff_environment(current: dict, anchor: dict) -> tuple[list[tuple[str, str, str]], list[str]]:
    """返回 (漂移项 [(键, 锚点值, 现值)], 锚点里没记录的键)。

    锚点缺某键（历史报告字段少）不算漂移——那是**信息不足**，把它当漂移会在每次升级
    脚本后炸出一片假红；把它明写出来，人才知道这一项这次没法比。
    """
    drifted, unknown = [], []
    for key in ENV_KEYS:
        new = current.get(key)
        if key not in anchor:
            unknown.append(key)
            continue
        old = anchor.get(key)
        if (old or "") != (new or ""):
            drifted.append((key, str(old), str(new)))
    return drifted, unknown


def reanchor_command(project: str = "5s") -> str:
    return (f"uv run --project server python scripts/golden_run.py --project {project} "
            f"--resolution original --update --reason \"<为什么环境变了、为什么新锚是对的>\"")


def reason_claims_environment(reason: str) -> bool:
    return bool(ENV_CLAIM_RE.search(reason or ""))


def reason_claims_code_change(reason: str) -> bool:
    return bool(CODE_CLAIM_RE.search(reason or ""))


def corroborate(history: list[dict], env_by_at: list[tuple[str, dict]], *,
                strict_from: str = "2026-11-06T05:00:00Z") -> tuple[list[str], list[str]]:
    """重锚理由 ↔ 当时真实指纹互证。返回 **(问题, 无法验证)**。

    `history` = `baseline*.json` 的 `updateHistory`；`env_by_at` = 同一批记录自带的
    (at, environment) 序列（也可以来自 index.json 的条目）。

    两类各自验各自的：
    - 代码类（写了 `EXECUTOR/RENDERER` 升版）→ 紧邻两次锚点的 `executorVersion`/`rendererVersion`
      **必须真的变了**。写了升版而版本没变，就是拿版本号给一次没有依据的重锚背书。
    - 环境类（Chrome/ffmpeg/字体/风格库…）→ 非代码键必须有差异。

    `strict_from` 之前的记录只进"无法验证"，不算问题：H10 之前留下的历史记录旁边没有对照锚点，
    拿今天的规则追认会把真实历史判成违规。这条豁免写进签名，而不是悄悄放宽断言。
    """
    problems: list[str] = []
    unverifiable: list[str] = []
    ordered = sorted(env_by_at, key=lambda x: str(x[0]))
    for entry in history:
        reason = str(entry.get("reason") or "")
        env_claim, code_claim = reason_claims_environment(reason), reason_claims_code_change(reason)
        if not (env_claim or code_claim):
            continue
        at = str(entry.get("at") or "")
        before = [e for a, e in ordered if a < at]
        after = [e for a, e in ordered if a >= at and e is not entry.get("environment")]
        if not before or not after:
            bucket = problems if at >= strict_from else unverifiable
            kind = "环境" if env_claim else "代码"
            bucket.append(f"@{at} 声称{kind}变化，但锚点序列前后不足以对照（前 {len(before)} 后 {len(after)}）")
            continue
        last_before, first_after = before[-1], after[0]
        if code_claim:
            keys = [k for k in _CODE_KEYS if k in last_before and k in first_after]
            if keys and all((last_before.get(k) or "") == (first_after.get(k) or "") for k in keys):
                problems.append(f"@{at} 的理由写了升版（{reason[:52]}…），但紧邻两次锚点的 "
                                f"{'/'.join(keys)} 都没变——要么这次重锚没有依据，要么指纹没记全")
        if env_claim:
            keys = [k for k in ENV_KEYS if k not in _CODE_KEYS and k in last_before and k in first_after]
            if keys and all((last_before.get(k) or "") == (first_after.get(k) or "") for k in keys):
                problems.append(f"@{at} 的理由说环境变了（{reason[:52]}…），但紧邻两次锚点的环境项逐项相同"
                                "——要么补真实指纹，要么这条理由不成立")
    return problems, unverifiable


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="5s", choices=["5s", "15s", "40s"])
    ap.add_argument("--quiet", action="store_true", help="只在检出漂移时输出")
    args = ap.parse_args()

    cur = current_environment()
    anchor, name = anchor_environment(args.project)
    if not anchor:
        print(f"DRIFT-SKIP: 找不到 {args.project} 的历史报告环境块——首次运行或报告目录为空，谈不上漂移")
        return 0
    drifted, unknown = diff_environment(cur, anchor)
    if not drifted and args.quiet:
        return 0

    print(f"环境指纹对照（锚点：{name}）")
    for key in ENV_KEYS:
        if key in unknown:
            print(f"  ? {key}: 锚点报告里没有这一项（不参与判定，现值 {cur.get(key)}）")
            continue
        hit = next((d for d in drifted if d[0] == key), None)
        if hit:
            print(f"  ⚠ 漂移 {key}: {hit[1][:60]} → {hit[2][:60]}")
        else:
            print(f"  ✓ {key}: {str(cur.get(key))[:60]} 一致")
    if drifted:
        print(f"\n检出 {len(drifted)} 项漂移。SSIM 若同时下降，先按重锚流程办，别直接改代码去凑数字：")
        print(f"  {reanchor_command(args.project)}")
        print("  （理由要写清哪一项变了、为什么新锚是对的；`--update` 无 `--reason` 会被拒。）")
        print("注意：本诊断**不是门禁**（老板 2026-11-06 选定「漂移即诊断」），所以它照常返回 0。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
