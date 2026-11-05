"""P1-06 / 判官 P0-1：项目删除服务——先校验再动数据，级联清库 + 磁盘目录。

删除是不可逆动作，这里把顺序和边界定死：
1. 任何删除前，`plan_delete` 必须整体通过（项目存在、目录策略、保护名单、无在飞作业）；
2. 库行删除在**单个事务**内完成，失败即回滚，不留"库没了目录还在"的半死态；
3. 目录删除只在库删成功后进行，失败作为结构化结果返回而不是抛错；
4. 目录策略：必须是白名单条目的**真子目录**（不允许白名单根本身，也不允许仓库根这类含 `.git` 的目录）；
5. 保护名单（演示与 rumor 回归基线）必须回显项目名 `confirm_name` 才允许删，仅靠布尔参数不足以自证。
"""
from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlmodel import Session, SQLModel, select

from ..config import settings
from ..errors import ApiError, ErrorCode
from ..models import AuditLog, Job, Project, ProjectDoc, Run, Workflow

# 回归与演示资产：删掉就毁掉可复核基线，必须回显名字才能删
_PROTECTED_PREFIXES = ("rumor",)
# A5（2026-11-06）裁定：golden-5s 保留——golden_run 仍按 `golden-5s-*` 命名自建自删，
# 按名保护能防其它脚本误碰在跑/残留的黄金项目；不是陈旧名单（216/223 那两个 id
# 才是，已从 _acceptance.DEMO_PROJECTS 移除）。
_PROTECTED_NAMES = {"一条消息被转发往往不是因为-1", "FR37 模板演示", "FR37模板演示-1",
                    "r3-demo-20261103", "r3-demo-20261103-1", "trace-x",
                    "r3-camera", "r3-audio-v2", "r2_5-delivery", "r2_5-delivery40",
                    "golden-5s", "r2_5-audio"}

_ACTIVE_JOB_STATUSES = ("queued", "leased", "running", "retry_wait")
# 心跳/开始时间在此窗口内才算"真在飞"；崩溃遗留的 retry_wait/running 行不该永久锁住删除
_LIVE_WINDOW = timedelta(seconds=120)


def _job_is_live(job, now: datetime) -> bool:
    """判活只看心跳/开始时间：启动恢复会把僵尸作业反复 bump updated_at（生产库现存 11 条
    retry_wait 且 heartbeat 停在 1–2 天前），用 updated_at 会把它们误判为在飞。"""
    stamp = job.heartbeat_at or job.started_at
    if stamp is None:
        return True          # 刚入队、还没心跳：按在飞处理
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return (now - stamp) <= _LIVE_WINDOW


def is_protected(name: str) -> bool:
    """保护判定：验收项目也叫 r2_5-delivery-277 这类名字，所以演示名只按**精确匹配**，
    只有 rumor 前缀（rumor-39s / rumor-clean-20261102）按前缀匹配。"""
    n = (name or "").strip()
    return n in _PROTECTED_NAMES or any(n.lower().startswith(p) for p in _PROTECTED_PREFIXES)


def dir_policy(root: str | Path) -> tuple[bool, str]:
    """目录必须可安全删除：白名单真子目录、深度≥1、不是 git 仓库根。"""
    rp = Path(root or "").resolve()
    if not str(root or "").strip():
        return False, "项目根为空"
    roots = [Path(w).resolve() for w in settings.workspace_roots]
    hit = next((w for w in roots if rp == w or rp.is_relative_to(w)), None)
    if hit is None:
        return False, f"项目根不在白名单内：{rp}"
    if rp == hit:
        return False, f"项目根就是白名单根，禁止按项目删除：{rp}"
    if len(rp.parts) - len(hit.parts) < 1:
        return False, f"项目根深度不足，疑似白名单根本身：{rp}"
    if (rp / ".git").exists():
        return False, f"项目根是 git 仓库，禁止按项目删除：{rp}"
    return True, ""


def _relations(session: Session, project_id: int) -> dict:
    wf_ids = [w.id for w in session.exec(select(Workflow).where(
        Workflow.project_id == project_id)).all()]
    run_ids = [r.id for r in session.exec(select(Run).where(
        Run.workflow_id.in_(wf_ids))).all()] if wf_ids else []
    doc_ids = [d.id for d in session.exec(select(ProjectDoc).where(
        ProjectDoc.project_id == project_id)).all()]
    return {"wf_ids": wf_ids, "run_ids": run_ids, "doc_ids": doc_ids}


def _delete_plan(session: Session, rel: dict, project_id: int) -> list[tuple]:
    plan: list[tuple] = []
    for table in reversed(SQLModel.metadata.sorted_tables):  # 先子后父
        cols = {c.name for c in table.columns}
        if table.name == "project":
            continue
        if "project_id" in cols:
            plan.append((table, "project_id", [project_id]))
        elif "run_id" in cols and rel["run_ids"]:
            plan.append((table, "run_id", rel["run_ids"]))
        elif "workflow_id" in cols and rel["wf_ids"]:
            plan.append((table, "workflow_id", rel["wf_ids"]))
        elif "doc_id" in cols and rel["doc_ids"]:
            plan.append((table, "doc_id", rel["doc_ids"]))
    return plan


def _inflight(session: Session, project_id: int, rel: dict) -> list[str]:
    """只拦"真在飞"的作业：Chrome/ffmpeg 仍在往项目目录写时不允许删除。

    Run.status=="running" 单独不作为阻塞条件——崩溃后的残留态由启动恢复处理，
    真正的写入者是持有租约/心跳的作业。
    """
    now = datetime.now(UTC)
    busy: list[str] = []
    for job in session.exec(select(Job).where(Job.status.in_(_ACTIVE_JOB_STATUSES))).all():  # type: ignore[arg-type]
        if job.run_id not in rel["run_ids"] and (job.payload_json or {}).get("projectId") != project_id:
            continue
        if _job_is_live(job, now):
            busy.append(f"job {job.id} {job.kind} status={job.status}")
    return busy


def plan_delete(session: Session, project_id: int) -> dict:
    """只报告将删什么，不改任何状态；删除前必须先过这里的校验。"""
    project = session.get(Project, project_id)
    if not project:
        raise ApiError(ErrorCode.E_NOT_FOUND, "项目不存在", status=404)
    rel = _relations(session, project_id)
    root = Path(project.root or "").resolve()
    dir_ok, dir_reason = dir_policy(project.root or "")
    busy = _inflight(session, project_id, rel)
    tables = []
    for table, col, values in _delete_plan(session, rel, project_id):
        count = len(session.exec(select(table).where(
            getattr(table.c, col).in_(values))).all())  # type: ignore[attr-defined]
        if count:
            tables.append({"table": table.name, "by": col, "rows": count})
    protected = is_protected(project.name)
    return {"projectId": project_id, "name": project.name, "root": str(root),
            "runs": len(rel["run_ids"]), "tables": tables,
            "dirDeletable": dir_ok, "dirReason": dir_reason,
            "protected": protected, "confirmNameRequired": protected,
            "inflight": busy, "runningRuns": [r.id for r in session.exec(
                select(Run).where(Run.id.in_(rel["run_ids"]),
                                   Run.status == "running")).all()] if rel["run_ids"] else [],
            "dirBlockers": ([] if dir_ok else [dir_reason]),
            "blockers": ([] if dir_ok else [dir_reason]) +
                        (["保护名单：需 confirm_name 回显项目名"] if protected else []) +
                        [f"仍有在飞作业：{b}" for b in busy]}


def delete_project(session: Session, project_id: int, *, remove_dir: bool = True,
                   confirm_name: str = "", force: bool = False) -> dict:
    """级联删除项目库行与目录；所有校验在动数据前完成，库删除单事务。"""
    project = session.get(Project, project_id)
    if not project:
        raise ApiError(ErrorCode.E_NOT_FOUND, "项目不存在", status=404)
    report = plan_delete(session, project_id)
    # 只删库行（remove_dir=False：测试与验收脚手架的清理路径）时，目录策略不适用
    blockers = [b for b in report["blockers"] if remove_dir or b not in report["dirBlockers"]]
    forced_inflight = force and any("在飞" in b for b in blockers)
    if forced_inflight:
        blockers = [b for b in blockers if "在飞" not in b]
    if report["protected"] and (confirm_name or "").strip() == (project.name or "").strip():
        blockers = [b for b in blockers if "保护名单" not in b]
    if blockers:
        hint = "；保护名单项目需把 confirm_name 设为项目名" if report["protected"] else ""
        raise ApiError(ErrorCode.E_VALIDATION,
                       f"删除被拒绝（项目 {project.name}）：" + "；".join(blockers) + hint,
                       status=409)
    rel = _relations(session, project_id)
    plan = _delete_plan(session, rel, project_id)
    audit_row = AuditLog(action="project.delete", target=str(project_id),
                         after_json={"name": project.name, "runs": len(rel["run_ids"]),
                                     "tables": [t["table"] for t in report["tables"]],
                                     "dirRemoved": bool(remove_dir),
                                     "forcedInflight": bool(forced_inflight)})
    try:
        for table, col, values in plan:
            session.exec(sa_delete(table).where(
                getattr(table.c, col).in_(values)))  # type: ignore[attr-defined]
        session.delete(project)
        session.add(audit_row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    result = {"deleted": project_id, "name": report["name"], "runs": len(rel["run_ids"]),
              "tables": report["tables"], "dirRemoved": False, "dir": report["root"]}
    if remove_dir:
        root = Path(report["root"])
        if root.exists():
            try:
                shutil.rmtree(root)
                result["dirRemoved"] = True
            except OSError as e:
                # 库已删，目录失败只报告不抛错：可重试（目录还在，行已清）
                result["dirError"] = str(e)
    return result
