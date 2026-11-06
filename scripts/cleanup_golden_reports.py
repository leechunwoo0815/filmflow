"""H5：golden 报告的保留策略（只留最近 N 份，被裁的进 .trash 并**留哈希**）。

为什么不是 gitignore/LFS：锚点与报告都是**证据**，不能不进版本库；但整批 1080p 静帧 +
每批视觉改动都新增一份带哈希的报告，`.git` 从 63M 涨到 69M 是实测（H5 的发现）。
本脚本把"保留多少"变成显式决定，而不是放任目录无限增长。

三条不可商量的性质：
1. **只裁 `docs/reports/golden/*.json`，绝不碰 `fixtures/golden/*/baseline_original/`**
   ——后者是回归锚本身（入 git 的 6×3 张原帧），删它等于删回归基线。
2. **删除是移动，不是 unlink**：被裁的报告进仓库根 `.trash/golden-reports/`。
   这样"证据消失"永远有一个可以反悔的地方。（老板的磁盘纪律也要求先可逆再清理。）
3. **`index.json` 必须留下被裁条目的哈希与 reason**：以后任何一次"报告怎么没了"的追问，
   都能对上一个 sha——没有哈希的删除等于没发生过的掩盖。

用法：
    uv run --project server python scripts/cleanup_golden_reports.py            # 只报告
    uv run --project server python scripts/cleanup_golden_reports.py --apply     # 真裁（移动到 .trash）
    uv run --project server python scripts/cleanup_golden_reports.py --keep 20    # 覆盖保留数
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "docs" / "reports" / "golden"
INDEX = REPORT_DIR / "index.json"
TRASH = ROOT / ".trash" / "golden-reports"
DEFAULT_KEEP = 20
SCHEMA = "filmflow.golden-index/1"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load_index() -> dict:
    if not INDEX.exists():
        return {"schema": SCHEMA, "items": [], "pruned": []}
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    idx.setdefault("pruned", [])
    return idx


def _report_files() -> list[Path]:
    return sorted(p for p in REPORT_DIR.glob("*.json") if p.name != "index.json")


def _at_of(idx: dict, name: str) -> str:
    for it in idx["items"]:
        if it.get("reportFile") == name:
            return str(it.get("at") or "")
    return ""


def plan(keep: int) -> tuple[list[Path], list[Path]]:
    """返回 (保留, 待裁)。排序按 index 的 `at`（UTC ISO，字典序即时间序），
    index 里没有的孤儿报告按文件 mtime 补——**孤儿也要被计入，不然裁剪会变成"只裁有记录的"**。
    """
    idx = _load_index()
    files = _report_files()
    keyed = []
    for p in files:
        at = _at_of(idx, p.name)
        stamp = at or datetime.fromtimestamp(p.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        keyed.append((stamp, p))
    keyed.sort(reverse=True)                       # 新→旧
    return [p for _, p in keyed[:keep]], [p for _, p in keyed[keep:]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"保留最近多少份（默认 {DEFAULT_KEEP}）")
    ap.add_argument("--apply", action="store_true", help="真裁：移动到 .trash 并登记哈希")
    ap.add_argument("--reason", default="", help="裁剪理由（进 index.pruned，与 golden --update 同一口径）")
    args = ap.parse_args()
    if args.keep < 1:
        raise SystemExit("--keep 至少为 1：证据台账不许被裁空")

    keep, doomed = plan(args.keep)
    total_bytes = sum(p.stat().st_size for p in doomed)
    print(f"报告总数 {len(keep) + len(doomed)} · 保留 {len(keep)}（keep={args.keep}）· "
          f"待裁 {len(doomed)}（约 {total_bytes / 1024:.1f} KiB）")
    for p in doomed[:5]:
        print(f"  待裁：{p.name}")
    if not doomed:
        print("无需裁剪（未超过保留数）")
        return 0
    if not args.apply:
        print("（报告模式；加 --apply 才动手，动手也只是移动到 .trash）")
        return 0

    TRASH.mkdir(parents=True, exist_ok=True)
    idx = _load_index()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    moved = []
    for p in doomed:
        dest = TRASH / p.name
        if dest.exists():                            # 同名不覆盖：加时间戳，保持每次裁剪都可追溯
            dest = TRASH / f"{p.stem}.{now.replace(':', '-').replace('-', '')}{p.suffix}"
        shutil.move(str(p), str(dest))               # 移动而非删除：反悔窗口
        idx["pruned"].append({"reportFile": p.name, "sha256": _sha(dest), "at": now,
                              "movedTo": str(dest.relative_to(ROOT)),
                              "reason": args.reason or "超过保留数 N，按时间倒序裁掉旧份"})
        moved.append(p.name)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已移动 {len(moved)} 份到 {TRASH.relative_to(ROOT)}/，index.json.pruned 记录 {len(moved)} 条哈希")
    for n in moved:
        print(f"  · {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
