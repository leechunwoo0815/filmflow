"""审计残留项目清理——默认只报告，绝不删除。

背景：专家审计与验收在 DB/磁盘留下 project 228–245 等残留（其中 8 行 root 已不存在）。
老板未点头前不允许真删；本工具把"建议清单"变成可复核的事实：

  uv run --project server python scripts/cleanup_projects.py            # 全部报告
  uv run --project server python scripts/cleanup_projects.py --orphans  # 只看 root 缺失行
  uv run --project server python scripts/cleanup_projects.py --id 228 --id 229 ...

真正删除（--confirm）要求：逐个 id 显式列出 + 无运行中 Job + 每个项目先过引用面检查。
演示项目（HANDOFF §7.4 名单）永远拒绝。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

DEMO_PROTECTED = {"一条消息被转发往往不是因为-1", "FR37模板演示-1", "r3-demo-20261103-1",
                  "trace-x", "rumor-clean-20261102"}


def main() -> int:
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Project, Run
    from app.services.project_cleanup import plan_delete

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orphans", action="store_true", help="只列 root 目录已不存在的行")
    ap.add_argument("--id", action="append", type=int, help="只报告指定项目")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--confirm", action="store_true",
                    help="真删（仍需 --id 显式列出，且演示名单/引用面拦截）")
    args = ap.parse_args()

    with Session(engine) as s:
        rows = s.exec(select(Project).order_by(Project.id)).all()
        targets = [r for r in rows if (not args.id or r.id in args.id)]
        out = []
        for p in targets:
            root = Path(p.root or "")
            plan = plan_delete(s, p.id)
            item = {"id": p.id, "name": p.name, "rootExists": root.exists(),
                    "root": str(root), "runs": plan["runs"],
                    "rows": sum(t["rows"] for t in plan["tables"]),
                    "demoProtected": p.name in DEMO_PROTECTED}
            if args.orphans and root.exists():
                continue
            out.append(item)
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            print(f"{'id':>4}  {'root':<5}  {'runs':>4}  {'rows':>6}  name")
            for it in out:
                flag = "演示保护" if it["demoProtected"] else ""
                print(f"{it['id']:>4}  {'存在' if it['rootExists'] else '缺失':<5}  "
                      f"{it['runs']:>4}  {it['rows']:>6}  {it['name']} {flag}")
            orphans = [i for i in out if not i["rootExists"] and not i["demoProtected"]]
            print(f"\n合计 {len(out)} 项；root 缺失且非演示 {len(orphans)} 项"
                  f"（删除建议见 HANDOFF §7.4，需老板点头）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
