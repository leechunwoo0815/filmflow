"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import json
from pathlib import Path

from sqlmodel import Session

from ..config import settings
from ..engine.fpscalc import frames_for, norm_fps
from ..errors import ApiError, ErrorCode, not_found
from ..models import (
    AuditLog,
    Project,
    Run,
    Style,
    Workflow,
)
from ..services import project_docs as docs_svc


def audit(session: Session, action: str, target: str, before=None, after=None):
    session.add(AuditLog(action=action, target=target, before_json=before or {}, after_json=after or {}))
    session.commit()


# ---------- 环境 / 引擎 / 库 ----------

def _style_dto(r: Style) -> dict:
    return {"id": r.id, "name": r.name, "collection": r.collection, "family": r.family,
            "sub_families": r.sub_families_json, "tokens_status": r.tokens_status,
            "preview_status": r.preview_status, "engine_status": r.engine_status,
            "has_cover": r.has_cover, "available": r.available, "labeled": r.labeled,
            "missing_fields": r.missing_fields, "tokens": r.tokens_json,
            "sha256": r.sha256, "path": r.path}

def _require_workspace_root(rp: Path) -> None:
    roots = [w.resolve() for w in settings.workspace_roots]
    if not any(rp == w or rp.is_relative_to(w) for w in roots):
        raise ApiError(ErrorCode.E_VALIDATION, f"项目根必须在白名单内：{settings.workspace_roots}")

def _require_creatable_project_root(rp: Path) -> None:
    """登记项目时的目录策略：必须是白名单真子目录，且不能是 git 仓库根。

    否则 POST /projects 可以登记白名单根本身，再经 DELETE /projects/{id} 递归删掉仓库与全部项目。
    """
    from ..services import project_cleanup as cleanup_svc
    _require_workspace_root(rp)
    ok, reason = cleanup_svc.dir_policy(rp)
    if not ok:
        raise ApiError(ErrorCode.E_VALIDATION, f"不能作为项目根：{reason}", status=400)

def _project_or_404(session: Session, project_id: int) -> Project:
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("项目")
    return proj

def _review_scene_ids(session: Session, run: Run, project_root: str) -> list[str]:
    task_p = Path(project_root) / "runs" / str(run.id) / "docs" / "task.json"
    if not task_p.exists():
        task_p = Path(project_root) / "card" / "task.json"
    try:
        task = json.loads(task_p.read_text(encoding="utf-8-sig")) if task_p.exists() else {}
    except (OSError, json.JSONDecodeError):
        task = {}
    scenes = [str(s["id"]) for s in (task.get("scenes") or []) if s.get("id")]
    if scenes:
        return scenes
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        return []
    tl = docs_svc.doc_payload(session, wf.project_id, project_root, "timeline")
    return [str(s["id"]) for s in (tl.get("content", {}).get("scenes") or []) if s.get("id")]

def _review_viewed(session: Session, run: Run, project_root: str) -> tuple[list[dict], list[str], list[str]]:
    vp = Path(project_root) / "card" / "viewed.json"
    try:
        data = json.loads(vp.read_text(encoding="utf-8")) if vp.exists() else {}
    except json.JSONDecodeError:
        data = {}
    entries = data.get("regions", [])
    scenes = _review_scene_ids(session, run, project_root)
    viewed = sorted({str(x.get("scene")) for x in entries if x.get("scene")})
    missing = [s for s in scenes if s not in viewed]
    return entries, viewed, missing

def _project_profile(root: str | Path) -> dict:
    p = Path(root) / "project.profile.json"
    try:
        prof = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        prof = {}
    fps = norm_fps(prof.get("fps") or 24)  # P1-12
    duration = float(prof.get("duration") or 0)
    return {"width": int(prof.get("width") or 1920), "height": int(prof.get("height") or 1080),
            "fps": fps, "duration": duration,
            "frames": int(prof.get("frames") or frames_for(duration, fps))}
