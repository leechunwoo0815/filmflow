"""P1-06：项目删除服务——级联清库 + 磁盘目录，供 API 与故障补偿共用。

此前删项目只能走 scripts/_acceptance.py 的 DB 直删（没有 DELETE /projects/{id}），
`foreign_keys` 也因此一直不敢开。这里提供唯一入口：
- 先按 SQLModel.metadata.sorted_tables 的 FK 依赖序清 project_id/run_id 关联行；
- 再删 Project 行；
- 最后删磁盘目录（必须在 workspace 白名单内，防路径穿越）。
`dry_run=True` 只报告将删什么，不改任何状态（cleanup_projects.py --dry-run 也走这里）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlmodel import select
from sqlmodel import Session, SQLModel

from ..config import settings
from ..errors import ApiError, ErrorCode
from ..models import Project, ProjectDoc, Run, Workflow


def _tables_for(session: Session, project_id: int) -> tuple[list[int], list[tuple]]:
    """返回 (run_ids, [(table, where列, 值列表)])，按依赖序（子表在前）。"""
    wf_ids = [w.id for w in session.exec(select(Workflow).where(
        Workflow.project_id == project_id)).all()]
    run_ids = [r.id for r in session.exec(select(Run).where(
        Run.workflow_id.in_(wf_ids))).all()] if wf_ids else []
    doc_ids = [d.id for d in session.exec(select(ProjectDoc).where(
        ProjectDoc.project_id == project_id)).all()]
    plan: list[tuple] = []
    for table in reversed(SQLModel.metadata.sorted_tables):  # 先子后父
        cols = {c.name for c in table.columns}
        if table.name == "project":
            continue
        if "project_id" in cols:
            plan.append((table, "project_id", [project_id]))
        elif "run_id" in cols and run_ids:
            plan.append((table, "run_id", run_ids))
        elif "workflow_id" in cols and wf_ids:
            plan.append((table, "workflow_id", wf_ids))
        elif "doc_id" in cols and doc_ids:
            # docrevision 只按 doc_id 挂在 projectdoc 下
            plan.append((table, "doc_id", doc_ids))
    return run_ids, plan


def plan_delete(session: Session, project_id: int) -> dict:
    """只报告：将删哪些表的多少行、目录在哪、是否在白名单内。"""
    project = session.get(Project, project_id)
    if not project:
        raise ApiError(ErrorCode.E_NOT_FOUND, "项目不存在", status=404)
    run_ids, plan = _tables_for(session, project_id)
    root = Path(project.root or "")
    allowed = any(root == Path(p) or root.is_relative_to(Path(p))
                  for p in settings.workspace_roots)
    tables = []
    for table, col, values in plan:
        count = len(session.exec(select(table).where(
            getattr(table.c, col).in_(values))).all())  # type: ignore[attr-defined]
        if count:
            tables.append({"table": table.name, "by": col, "rows": count})
    return {"projectId": project_id, "name": project.name, "root": str(root),
            "runs": len(run_ids), "tables": tables,
            "rootWhitelisted": allowed, "demoProtected": project.name in _DEMO_NAMES}


_DEMO_NAMES = {"一条消息被转发往往不是因为-1", "FR37模板演示-1", "r3-demo-20261103-1",
               "trace-x"}


def delete_project(session: Session, project_id: int, *, remove_dir: bool = True,
                   confirm_demo: bool = False) -> dict:
    """级联删除项目所有库行与磁盘目录；演示项目必须显式 confirm_demo=True 才允许删。"""
    report = plan_delete(session, project_id)
    if report["demoProtected"] and not confirm_demo:
        raise ApiError(ErrorCode.E_VALIDATION,
                       f"项目 {report['name']} 在演示保护名单；确认无误请带 confirm_demo=true", status=409)
    project = session.get(Project, project_id)
    if not project:
        raise ApiError(ErrorCode.E_NOT_FOUND, "项目不存在", status=404)
    run_ids, plan = _tables_for(session, project_id)
    for table, col, values in plan:
        session.exec(sa_delete(table).where(
            getattr(table.c, col).in_(values)))  # type: ignore[attr-defined]
    from ..models import AuditLog
    session.add(AuditLog(action="project.delete", target=str(project_id),
                         after_json={"name": project.name, "runs": len(run_ids),
                                     "tables": [t["table"] for t in report["tables"]]}))
    session.delete(project)
    session.commit()
    removed_dir = False
    root = Path(project.root or "")
    if remove_dir and str(root) and root.exists():
        if not report["rootWhitelisted"]:
            raise ApiError(ErrorCode.E_VALIDATION,
                           f"项目目录不在白名单内，已删库行但保留目录：{root}")
        shutil.rmtree(root, ignore_errors=False)
        removed_dir = True
    return {"deleted": project_id, "name": report["name"], "runs": len(run_ids),
            "tables": report["tables"], "dirRemoved": removed_dir,
            "dir": str(root)}
