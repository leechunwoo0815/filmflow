"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..errors import ApiError, ErrorCode, not_found
from ..models import (
    Artifact,
    Run,
    Workflow,
    table_dict,
)
from ..security import file_response
from ..services import delivery as delivery_svc
from ..services import jobs as jobs_svc
from ..services import project_docs as docs_svc
from ..services import qa as qa_svc
from ..services import render_profiles as profiles_svc
from . import deps
from .schemas import (
    DeliveryIn,
    QaFixIn,
    QaUndoIn,
    RenderProfileUpdateIn,
)

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/delivery", status_code=202)
async def project_delivery(project_id: int, payload: DeliveryIn,
                           session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    run_id = payload.runId if payload.runId is not None else payload.run_id
    job = delivery_svc.create_job(session, proj, run_id, payload.profile)
    asyncio.create_task(delivery_svc.run_delivery(job.id or 0))
    deps.audit(session, "delivery.create", f"project:{project_id}", after={"job": job.id})
    return {"jobId": job.id, "kind": job.kind, "status": job.status, "priority": job.priority}


@router.get("/projects/{project_id}/deliveries")
async def project_deliveries(project_id: int, session: Session = Depends(get_session)):
    deps._project_or_404(session, project_id)
    rows = jobs_svc.list_jobs(session, kind="delivery", limit=200)
    return {"items": [table_dict(j) for j in rows
                      if (j.payload_json or {}).get("projectId") == project_id]}


@router.get("/projects/{project_id}/deliveries/{run_id}")
async def project_delivery_detail(project_id: int, run_id: int,
                                  session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    outdir = Path(proj.root).resolve() / "out" / "deliveries" / str(run_id)
    if not outdir.exists():
        raise not_found("交付目录")
    def read(name: str) -> dict:
        p = outdir / name
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    names = ["master_16x9.mp4", "master_9x16.mp4", "captions.zh.srt",
             "cover_16x9.jpg", "cover_9x16.jpg", "manifest.json", "qc.json",
             "rights.json", "FilmFlow-delivery.zip"]
    return {"runId": run_id, "manifest": read("manifest.json"), "qc": read("qc.json"),
            "rights": read("rights.json"),
            "files": [{"name": n, "url": f"/api/projects/{project_id}/deliveries/{run_id}/{n}",
                       "bytes": (outdir / n).stat().st_size if (outdir / n).exists() else 0}
                      for n in names]}


@router.get("/projects/{project_id}/deliveries/{run_id}/{name}")
async def project_delivery_file(project_id: int, run_id: int, name: str,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    base = (Path(proj.root).resolve() / "out" / "deliveries" / str(run_id)).resolve()
    p = (base / name).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        raise not_found("交付文件")
    return file_response(p, download_name=name)


# ---------- 渲染档位（FR-24） ----------


@router.get("/projects/{project_id}/render-profile")
async def project_render_profile(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    imported = docs_svc.is_imported(session, project_id)
    return profiles_svc.resolve(proj.root, deps._project_profile(proj.root),
                                allow_low_final=imported)


@router.put("/projects/{project_id}/render-profile")
async def project_render_profile_update(project_id: int, payload: RenderProfileUpdateIn,
                                        session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    root = Path(proj.root).resolve()
    deps._require_workspace_root(root)
    imported = docs_svc.is_imported(session, project_id)
    body = payload.model_dump(exclude_none=True)
    resolved = profiles_svc.save(root, body, deps._project_profile(root),
                                 allow_low_final=imported)
    deps.audit(session, "render.profile", f"project:{project_id}",
          after={k: resolved[k] for k in ("draft", "review", "final")})
    return resolved


@router.get("/artifacts/{artifact_id}/file")
async def artifact_file(artifact_id: int, session: Session = Depends(get_session)):
    a = session.get(Artifact, artifact_id)
    if not a:
        raise not_found("artifact")
    p = Path(a.path)
    if not p.exists():
        raise not_found("产物文件")
    # P3：产物路径来自 DB；仍强制落在工作区白名单内（防 DB 被改后任意读）
    deps._require_workspace_root(p.resolve())
    return file_response(p)


# ---------- 门审批（T10/FR-8） ----------


@router.get("/projects/{project_id}/qa")
async def project_qa(project_id: int, runId: int | None = None,
                     session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return qa_svc.analyze(session, proj, runId)


@router.get("/runs/{run_id}/qa")
async def run_qa(run_id: int, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("Run")
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        raise not_found("Workflow")
    proj = deps._project_or_404(session, wf.project_id)
    return qa_svc.analyze(session, proj, run_id)


@router.post("/projects/{project_id}/qa/fix")
async def project_qa_fix(project_id: int, payload: QaFixIn,
                         session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    if docs_svc.is_imported(session, project_id):
        raise ApiError(ErrorCode.E_VALIDATION, "导入项目只读，不能应用 QA 修复", status=409)
    try:
        entry = qa_svc.apply_fix(session, proj, payload.issueId, payload.action,
                                 payload.payload, payload.runId)
    except ValueError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"E_QA_FIX: {e}", status=409)
    deps.audit(session, "qa.fix", f"{project_id}:{payload.issueId}",
          after={"action": payload.action, "result": entry.get("verified")})
    return {"fix": entry, "qa": qa_svc.analyze(
        session, proj, entry.get("runId"))}


@router.post("/projects/{project_id}/qa/undo")
async def project_qa_undo(project_id: int, payload: QaUndoIn,
                          session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    if docs_svc.is_imported(session, project_id):
        raise ApiError(ErrorCode.E_VALIDATION, "导入项目只读，不能撤销 QA 修复", status=409)
    try:
        entry = qa_svc.undo_fix(session, proj, payload.fixId)
    except ValueError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"E_QA_UNDO: {e}", status=409)
    deps.audit(session, "qa.undo", f"{project_id}:{payload.fixId}")
    return {"fix": entry, "qa": qa_svc.analyze(session, proj, entry.get("runId"))}


@router.get("/projects/{project_id}/qa/report")
async def project_qa_report(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return qa_svc.report(proj)


# ---------- 资产库（FR-36） ----------

