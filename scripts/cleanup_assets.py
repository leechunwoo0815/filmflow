"""B5/P2-17：资产孤儿报告/清理（默认只报告，`--confirm` 才动手）。

孤儿 = 磁盘上有、库（Asset 表 sha）里没有的资产文件；死行 = 库里有、磁盘上没有的行。
两类都只**报告**，`--confirm` 才删（库行删除属破坏性库写，先备份
`~/.filmflow/filmflow.db` → `~/filmflow-backup-<stamp>.db`，前后出计数对照）。

用法：
  uv run --project server python scripts/cleanup_assets.py            # 只报告
  uv run --project server python scripts/cleanup_assets.py --confirm  # 报告 + 清理
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.config import settings
from app.db import engine
from app.models import Asset
from sqlmodel import Session, select


def sha_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="真的删（缺省只报告）")
    args = ap.parse_args()

    paths: set[str] = set()
    shas: set[str] = set()
    rows_before = 0
    with Session(engine) as session:
        for a in session.exec(select(Asset)).all():
            paths.add(str(a.path))
            shas.add(a.sha256)
            rows_before += 1

    assets_root = Path(settings.assets_dir)
    disk_files = sorted(p for p in assets_root.rglob("*")
                        if p.is_file() and not p.name.startswith("."))
    orphan_files = [p for p in disk_files if sha_of(p) not in shas]
    dead_rows = sorted(p for p in paths if not Path(p).exists())

    print(f"库内资产行：{rows_before}；磁盘文件：{len(disk_files)}")
    print(f"孤儿文件（磁盘有/库 sha 无）：{len(orphan_files)}")
    for p in orphan_files[:20]:
        print(f"  - {p} ({p.stat().st_size}B)")
    print(f"死行（库有/磁盘无）：{len(dead_rows)}")
    for p in dead_rows[:20]:
        print(f"  - {p}")

    if not args.confirm:
        print("报告模式（未删任何东西）。加 --confirm 执行清理。")
        return 0

    freed = 0
    for p in orphan_files:
        freed += p.stat().st_size
        p.unlink()
    rows_after = rows_before
    if dead_rows:
        backup = Path.home() / f"filmflow-backup-{time.strftime('%Y%m%d-%H%M%S')}.db"
        shutil.copy2(Path.home() / ".filmflow" / "filmflow.db", backup)
        print(f"库行清理前备份：{backup}（{backup.stat().st_size}B）")
        with Session(engine) as session:
            for a in session.exec(select(Asset)).all():
                if not Path(a.path).exists():
                    session.delete(a)
            session.commit()
        with Session(engine) as session:
            rows_after = len(session.exec(select(Asset)).all())
    print(f"清理完成：删孤儿文件 {len(orphan_files)} 个（{freed}B）；"
          f"资产行 {rows_before}→{rows_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
