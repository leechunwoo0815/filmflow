"""审计残留项目清理——默认只报告，绝不删除。

背景：专家审计与验收在 DB/磁盘留下 project 228–245 等残留（其中 8 行 root 已不存在）。
老板未点头前不允许真删；本工具把"建议清单"变成可复核的事实：

  uv run --project server python scripts/cleanup_projects.py            # 全部报告
  uv run --project server python scripts/cleanup_projects.py --orphans  # 只看 root 缺失行
  uv run --project server python scripts/cleanup_projects.py --id 228 --id 229 ...
  uv run --project server python scripts/cleanup_projects.py --stale-drafts            # 僵尸草稿报告
  uv run --project server python scripts/cleanup_projects.py --stale-drafts --confirm  # 真删
  uv run --project server python scripts/cleanup_projects.py --stale-jobs --hours 72   # parked 作业报告

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


def _counts(s) -> dict[str, int]:
    from app.models import Draft, Job, Project, Run
    from sqlmodel import select

    return {"project": len(s.exec(select(Project)).all()),
            "run": len(s.exec(select(Run)).all()),
            "draft": len(s.exec(select(Draft)).all()),
            "job": len(s.exec(select(Job)).all())}


def _stale_drafts(s) -> list:
    """向导草稿里 root 已不存在的行：materialize 不删草稿，验收脚本跑一次就留一枚。"""
    from app.models import Draft
    from sqlmodel import select

    out = []
    for d in s.exec(select(Draft)).all():
        root = str((d.payload_json or {}).get("root") or "")
        if root and not Path(root).is_dir():
            out.append((d, root))
    return out


def orphan_dirs(s) -> list[Path]:
    """H3：`filmflow-projects/` 下**没有任何 Project 行指向**的目录（反向孤儿）。

    `_stale_drafts` 查的是"行在、目录没了"，这一条查的是相反方向——目录还在、行已经没了，
    实测漏过 65MB 的 `r3-camera-260`（B7 camera 脚本没自删，删行/删目录的顺序让它活成了孤儿）。
    `.acceptance` 是验收脚本的工作区，由 `check_no_demo_writes` 单独管残留，这里排除。
    """
    from app.config import settings
    from app.models import Project
    from sqlmodel import select

    base = Path(settings.workspace_roots[0]) / "filmflow-projects"
    if not base.is_dir():
        return []
    known = {str(Path(p.root or "").resolve()) for p in s.exec(select(Project)).all()}
    out = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name == ".acceptance":
            continue
        if str(d.resolve()) not in known:
            out.append(d)
    return out


def hygiene_counts(s) -> dict[str, object]:
    """治理第 18 项的唯一真源：僵尸 draft 与孤儿目录各多少（两边不许各写一份判据）。"""
    stale = _stale_drafts(s)
    orphans = orphan_dirs(s)
    return {"zombieDrafts": len(stale), "orphanDirs": len(orphans),
            "zombieIds": [int(d.id) for d, _ in stale],
            "orphanNames": [d.name for d in orphans]}


def _parked_jobs(s, hours: int) -> list:
    from datetime import UTC, datetime, timedelta

    from app.models import Job
    from sqlmodel import select

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    out = []
    for j in s.exec(select(Job).where(Job.status == "retry_wait")).all():
        stamp = j.heartbeat_at or j.started_at or j.updated_at or j.created_at
        if stamp is None:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        if stamp <= cutoff:
            out.append((j, stamp))
    return out


def main() -> int:
    from app.db import engine
    from app.models import Project
    from app.services.project_cleanup import plan_delete
    from sqlmodel import Session, select

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orphans", action="store_true", help="只列 root 目录已不存在的行")
    ap.add_argument("--id", action="append", type=int, help="只报告指定项目")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--stale-drafts", action="store_true",
                    help="报告/回收 root 已不存在的向导草稿（僵尸 draft）")
    ap.add_argument("--stale-jobs", action="store_true",
                    help="报告/回收停太久的 parked 作业（retry_wait）")
    ap.add_argument("--hours", type=int, default=72, help="parked 作业过期阈值（默认 72h）")
    ap.add_argument("--confirm", action="store_true",
                    help="真删（项目仍需 --id 显式列出，且演示名单/引用面拦截）")
    args = ap.parse_args()

    with Session(engine) as s:
        if args.stale_drafts or args.stale_jobs:
            before = _counts(s)
            if args.stale_drafts:
                stale = _stale_drafts(s)
                print(f"僵尸 draft（root 已不存在）：{len(stale)} 条")
                for d, root in stale[:10]:
                    print(f"  #{d.id} step={d.step} name={d.name!r} root={root}")
                if len(stale) > 10:
                    print(f"  …其余 {len(stale) - 10} 条同型")
                if args.confirm and stale:
                    for d, _root in stale:
                        s.delete(d)
                    s.commit()
                    print(f"已删除 {len(stale)} 条")
            if args.stale_jobs:
                parked = _parked_jobs(s, args.hours)
                print(f"parked 作业（retry_wait，心跳 > {args.hours}h）：{len(parked)} 条")
                for j, stamp in parked:
                    print(f"  job#{j.id} run={j.run_id} 心跳 {stamp:%Y-%m-%d %H:%M} "
                          f"error={j.error_code}")
                if args.confirm and parked:
                    from app.services.jobs import expire_parked
                    expired = expire_parked(s, args.hours)
                    print(f"已按 E_JOB_EXPIRED 收成 canceled：{expired}")
            if args.confirm:
                print(f"计数 {before} → {_counts(s)}")
            else:
                print("（只报告；加 --confirm 才动手）")
            return 0

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
