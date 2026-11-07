"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from ..atomicwrite import write_atomic
from ..db import get_session
from ..engine import edges
from ..engine import runengine as re_mod
from ..engine.cachekey import gate_content_hash
from ..engine.invalidation import impact_preview
from ..engine.snapshot import snapshot_doc_drift
from ..errors import ApiError, ErrorCode, not_found
from ..events import emit
from ..models import (
    Approval,
    Artifact,
    Metric,
    NodeRun,
    Project,
    Run,
    Workflow,
    WorkflowVersion,
    table_dict,
)
from ..services import preview as preview_svc
from ..services import render_profiles as profiles_svc
from ..services import review_comments as review_svc
from . import deps
from .schemas import (
    GateDecideIn,
    PreviewFilmIn,
    PreviewSegmentIn,
    PreviewStillIn,
    RunCreateIn,
    RunPromoteIn,
    WorkflowCreateIn,
    WorkflowPutIn,
)

router = APIRouter(prefix="/api")


@router.post("/workflows")
async def workflows_create(payload: WorkflowCreateIn, session: Session = Depends(get_session)):
    deps._project_or_404(session, payload.projectId)  # 外键已开，但缺项目要给 404 而不是 500
    wf = Workflow(project_id=payload.projectId, graph_json=payload.graph)
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return table_dict(wf)


@router.get("/workflows/{workflow_id}")
async def workflow_get(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise not_found("workflow")
    return {**table_dict(wf), "nodes": edges.N, "edges": edges.EDGES, "topology": edges.TOPOLOGY}


@router.put("/workflows/{workflow_id}")
async def workflow_put(workflow_id: int, payload: WorkflowPutIn,
                       session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise not_found("workflow")
    wf.version += 1
    if payload.graph is not None:
        wf.graph_json = payload.graph
    flag_modified(wf, "graph_json")
    session.add(wf)
    session.add(WorkflowVersion(workflow_id=wf.id, version=wf.version, graph_json=wf.graph_json))
    session.commit()
    return table_dict(wf)


@router.post("/runs")
async def runs_create(payload: RunCreateIn, session: Session = Depends(get_session)):
    wf = session.get(Workflow, payload.workflowId)
    if not wf:
        raise not_found("workflow")
    run = Run(workflow_id=wf.id, params_snapshot=payload.params)
    session.add(run)
    session.commit()
    session.refresh(run)
    return table_dict(run)


@router.get("/projects/{project_id}/runs")
async def project_runs(project_id: int, session: Session = Depends(get_session)):
    wfs = session.exec(select(Workflow).where(Workflow.project_id == project_id)).all()
    ids = [w.id for w in wfs]
    rows = session.exec(select(Run)).all()
    return {"items": [table_dict(r) for r in rows if r.workflow_id in ids]}


@router.get("/runs/{run_id}")
async def run_get(run_id: int, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    return table_dict(run)


@router.get("/runs/{run_id}/graph")
async def run_graph(run_id: int, session: Session = Depends(get_session)):
    """画布数据：46 节点 + 边 + 各节点状态/进度/产物缩略。"""
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    states = {r.node_id: r for r in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()}
    wf = session.get(Workflow, run.workflow_id)
    nodes = []
    for nid, n in edges.N.items():
        st = states.get(nid)
        arts = session.exec(select(Artifact).where(
            Artifact.run_id == run_id, Artifact.node_id == nid)).all()
        nodes.append({"id": nid, "title": n["title"], "stage": nid[0], "executor": n["executor"],
                      "gate": n["gate"], "locks": n["locks"],
                      "status": st.status if st else "idle", "progress": st.progress if st else 0,
                      "message": st.message if st else "",
                      "position": (wf.graph_json or {}).get("positions", {}).get(nid, {"x": 0, "y": 0}),
                      "artifacts": [{"id": a.id, "type": a.type, "sha": a.sha256[:12]} for a in arts[:4]]})
    return {"run": table_dict(run), "nodes": nodes, "edges": edges.EDGES,
            "stages": edges.STAGE_TITLES, "caps": run.caps_json}


@router.post("/runs/{run_id}/start")
async def run_start(run_id: int, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    re_mod.start_run(run_id)
    return {"ok": True, "status": "running"}


@router.post("/runs/{run_id}/step")
async def run_step(run_id: int):
    return await re_mod.step_run(run_id)


@router.post("/runs/{run_id}/cancel")
async def run_cancel(run_id: int):
    re_mod.cancel_run(run_id)
    return {"ok": True}


@router.post("/runs/{run_id}/retry")
async def run_retry(run_id: int, session: Session = Depends(get_session)):
    """只重跑失败节点（规格 §7.4）。

    P0-5：重试沿用本 Run 的文档快照，所以文档改过之后重试只会重渲**旧内容**
    （QA 扩场景的 0.5s 就这么被吃掉过）。漂移即 409，让调用方去开新 Run。
    """
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    wf = session.get(Workflow, run.workflow_id)
    proj = session.get(Project, wf.project_id) if wf else None
    drift = snapshot_doc_drift(session, run, proj.root) if proj else {}
    if drift:
        raise ApiError(ErrorCode.E_RUN_SNAPSHOT_STALE,
                       "本 Run 的快照与当前文档不一致，重试只会重渲旧内容——请开新 Run",
                       status=409, details={"runId": run_id, "drift": drift})
    rows = session.exec(select(NodeRun).where(NodeRun.run_id == run_id, NodeRun.status == "failed")).all()  # type: ignore[arg-type]
    for r in rows:
        r.status = "idle"
        session.add(r)
    session.commit()
    re_mod.start_run(run_id)
    return {"requeued": len(rows)}


@router.post("/runs/{run_id}/resume")
async def run_resume(run_id: int):
    return await re_mod.resume_run(run_id)


@router.get("/runs/{run_id}/impact")
async def run_impact(run_id: int, nodeId: str, patch: str = "{}", session: Session = Depends(get_session)):
    """dry-run 失效预览（规格 §7.5：不得执行后才告知）。"""
    run = session.get(Run, run_id)
    wf = session.get(Workflow, run.workflow_id)
    graph = wf.graph_json or {}
    params_by = {nid: (graph.get("params", {}) or {}).get(nid, {}) for nid in edges.N}
    hashes_by: dict[str, dict[str, str]] = {}
    states = {r.node_id: r for r in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()}
    proj_root = re_mod._project_root(session, run)
    for nid in edges.N:
        hashes_by[nid] = re_mod._upstream_hashes(session, run_id, nid, states, proj_root)
    gate_hashes = {gid: gate_content_hash(gid, params_by[gid], hashes_by[gid])
                   for gid in edges.N if edges.N[gid]["gate"] == "human"}
    try:
        p = json.loads(patch)
    except json.JSONDecodeError:
        p = {}
    return impact_preview(nodeId, p, params_by, hashes_by, gate_hashes)


@router.get("/runs/{run_id}/nodes")
async def run_nodes(run_id: int, session: Session = Depends(get_session)):
    return {"items": [table_dict(r) for r in session.exec(
        select(NodeRun).where(NodeRun.run_id == run_id)).all()]}


@router.get("/runs/{run_id}/metrics")
async def run_metrics(run_id: int, session: Session = Depends(get_session)):
    return {"items": [table_dict(m) for m in session.exec(
        select(Metric).where(Metric.run_id == run_id)).all()]}


@router.get("/runs/{run_id}/artifacts")
async def run_artifacts(run_id: int, session: Session = Depends(get_session)):
    return {"items": [table_dict(a) for a in session.exec(
        select(Artifact).where(Artifact.run_id == run_id)).all()]}


@router.get("/runs/{run_id}/render-manifest")
async def run_render_manifest(run_id: int, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    root = re_mod._project_root(session, run)
    p = Path(root) / "renders/final/manifest.json"
    if not p.exists():
        raise not_found("render manifest")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- 预览（FR-23） ----------


@router.post("/projects/{project_id}/preview/still")
async def project_preview_still(project_id: int, payload: PreviewStillIn,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    scene_id = str(payload.sceneId or payload.scene_id or "")
    if not scene_id:
        raise ApiError(ErrorCode.E_VALIDATION, "sceneId 必填")
    res = await preview_svc.render_still(
        session, project_id, scene_id,
        t=payload.time,
        profile=payload.profile,
        watermark=payload.watermark,
        debounce=payload.debounce,
        motion=payload.motion)
    return Response(content=res.png, media_type="image/png", headers={
        "X-Preview-Cache": "hit" if res.cached else "miss",
        "X-Preview-Ms": str(res.ms),
        "X-Preview-Scene-Hash": res.scene_hash[:16],
        "X-Preview-Watermark": "1" if payload.watermark else "0",
        "X-Preview-Chrome": res.chrome,
    })


@router.post("/projects/{project_id}/preview/segment", status_code=202)
async def project_preview_segment(project_id: int, payload: PreviewSegmentIn,
                                  session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    scene_id = str(payload.sceneId or payload.scene_id or "")
    if not scene_id:
        raise ApiError(ErrorCode.E_VALIDATION, "sceneId 必填")
    job = preview_svc.create_segment_job(
        session, project_id, scene_id, payload.start, payload.end,
        profile=payload.profile,
        watermark=payload.watermark)
    deps.audit(session, "preview.segment", f"project:{project_id}",
          after={"job": job.id, "scene": scene_id, "start": job.start, "end": job.end})
    return preview_svc.job_payload(job)


@router.post("/projects/{project_id}/preview/film", status_code=202)
async def project_preview_film(project_id: int, payload: PreviewFilmIn,
                               session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    job = preview_svc.create_film_job(
        session, project_id, profile=payload.profile,
        watermark=payload.watermark)
    deps.audit(session, "preview.film", f"project:{project_id}",
          after={"job": job.id, "profile": job.profile})
    return preview_svc.job_payload(job)


@router.get("/preview/jobs/{job_id}")
async def preview_job_status(job_id: str):
    return preview_svc.job_payload(preview_svc.get_job(job_id))


@router.delete("/preview/jobs/{job_id}")
async def preview_job_cancel(job_id: str):
    return preview_svc.cancel_job(job_id)


@router.get("/preview/jobs/{job_id}/file")
async def preview_job_file(job_id: str, session: Session = Depends(get_session)):
    job = preview_svc.get_job(job_id)
    if job.status != "succeeded" or not job.path:
        raise ApiError(ErrorCode.E_CONFLICT, f"预览任务未完成：{job.status}", status=409)
    proj = deps._project_or_404(session, job.project_id)
    base = (Path(proj.root).resolve() / "out" / "preview")
    p = Path(job.path).resolve()
    if not p.is_relative_to(base) or not p.exists():
        raise not_found("预览文件")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


@router.get("/projects/{project_id}/preview/cache")
async def project_preview_cache(project_id: int, session: Session = Depends(get_session)):
    deps._project_or_404(session, project_id)
    return preview_svc.PreviewCache(project_id).stats()


# ---------- 交付 v1（FR-28） ----------


@router.post("/gates/{gate_id}/decide")
async def gate_decide(gate_id: str, payload: GateDecideIn,
                      session: Session = Depends(get_session)):
    run_id = int(payload.run_id or payload.runId or 0)
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    if gate_id not in edges.N or edges.N[gate_id]["gate"] != "human":
        raise ApiError(ErrorCode.E_VALIDATION, f"{gate_id} 不是人工门")
    # 门前置 ①：上游必须全部完成——失败/跳过的上游不得签字（规格 §16）
    states = {r.node_id: r for r in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()}
    for up, ty in edges.UPSTREAM[gate_id].items():
        if ty in ("data", "trigger"):
            up_st = states.get(up)
            if not up_st or up_st.status not in ("succeeded", "cached"):
                raise ApiError(ErrorCode.E_VALIDATION,
                               f"门 {gate_id} 的上游 {up} 未完成（{up_st.status if up_st else 'missing'}），不能签字")
    decision = payload.decision  # 模型层已约束 approved/rejected
    if gate_id == "G07" and decision == "approved":
        wf = session.get(Workflow, run.workflow_id)
        imported = bool(((((wf.graph_json or {}) if wf else {}).get("meta")) or {}).get("imported"))
        root = re_mod._project_root(session, run)
        profiles_svc.ensure_final_ready(session, run, root, imported, deps._project_profile(root))
    # 门前置校验（如 D03 ≥3 区域）
    precheck = _gate_precheck(session, run_id, gate_id)
    if precheck and decision == "approved":
        raise ApiError(ErrorCode.E_VALIDATION, f"批准前置未满足：{precheck}")
    # 不通过必须填意见
    if decision == "rejected" and not payload.note.strip():
        raise ApiError(ErrorCode.E_VALIDATION, "驳回必须填写意见（规格 §7.5）")
    params_by = {}
    states = {r.node_id: r for r in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()}
    proj_root = re_mod._project_root(session, run)
    ch = gate_content_hash(gate_id, params_by.get(gate_id, {}),
                           re_mod._upstream_hashes(session, run_id, gate_id, states, proj_root))
    # 重批相同内容不产生新失效：已存在同 hash approved → 保留 decided_at
    existing = session.exec(select(Approval).where(
        Approval.run_id == run_id, Approval.gate_id == gate_id,
        Approval.decision == "approved", Approval.content_hash == ch)).first()  # type: ignore[arg-type]
    if existing and decision == "approved":
        return {"ok": True, "unchanged": True, "decided_at": str(existing.created_at)}
    policy = "reapprove" if gate_id == "G07" else "inherit"
    a = Approval(run_id=run_id, gate_id=gate_id, decision=decision, policy=policy,
                 content_hash=ch, author=payload.author,
                 note=payload.note, checklist_json=payload.checklist)
    session.add(a)
    session.commit()
    # 解除阻塞：门 NodeRun → succeeded（批准）或保持 blocked（驳回）
    st = session.exec(select(NodeRun).where(
        NodeRun.run_id == run_id, NodeRun.node_id == gate_id)).first()  # type: ignore[arg-type]
    if st:
        if decision != "approved":
            st.status = "blocked"
        elif edges.N[gate_id]["executor"] in ("gate", "still-view"):
            st.status = "succeeded"
        else:
            # G07 等有真实执行体的门：批准后回 idle，让调度器执行 package，不能跳过执行
            st.status = "idle"
        session.add(st)
        if decision == "approved":
            run.caps_json = __import__("app.engine.caps", fromlist=["caps_after_approval"]).caps_after_approval(
                run.caps_json or [], gate_id)
            session.add(run)
        session.commit()
    emit("gate.decided", run_id, gate_id, decision=decision)
    deps.audit(session, "gate.decide", f"{run_id}:{gate_id}",
          after={"decision": decision, "note": payload.note})
    if decision == "approved":
        re_mod.start_run(run_id)   # 调度循环在等门时退出；批准即重启
    return {"ok": True, "decision": decision, "content_hash": ch[:12]}


def _gate_precheck(session: Session, run_id: int, gate_id: str) -> str | None:
    if gate_id in ("D03", "D05"):
        run = session.get(Run, run_id)
        root = re_mod._project_root(session, run)
        wf = session.get(Workflow, run.workflow_id)
        imported = bool(((((wf.graph_json or {}) if wf else {}).get("meta")) or {}).get("imported"))
        entries, viewed, missing = deps._review_viewed(session, run, root)
        if gate_id == "D03":
            if imported:
                if len(entries) < 3:
                    return f"已查看 {len(entries)} 个区域 < 3"
            elif missing:
                return f"未查看场景：{', '.join(missing)}（每个场景至少看 1 张）"
        elif not imported and missing:
            return f"静帧未看全：{', '.join(missing)}"
    return None


@router.get("/gates/{run_id}/pending")
async def gates_pending(run_id: int, session: Session = Depends(get_session)):
    """当前等待批准的门 + 其 checklist。"""
    run = session.get(Run, run_id)
    if not run:
        # 未知 Run 是 404 而不是 AttributeError 冒到 500：与 /runs/{id}/report、/runs/{id}/retry 同一口径
        raise not_found("run")
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        raise not_found("workflow")
    states = {r.node_id: r for r in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()}
    proj_root = re_mod._project_root(session, run)
    graph = wf.graph_json or {}
    out = []
    terminal = ("succeeded", "cached")
    for gid in edges.HUMAN_GATES:
        st = states.get(gid)
        if not st or st.status in terminal:
            continue
        # 只列出「真正在等」的门：data/trigger 上游全部完成
        if any((s := states.get(up)) is None or s.status not in terminal
               for up, ty in edges.UPSTREAM[gid].items() if ty in ("data", "trigger")):
            continue
        ch = gate_content_hash(gid, (graph.get("params", {}) or {}).get(gid, {}),
                               re_mod._upstream_hashes(session, run_id, gid, states, proj_root))
        ok, stale = re_mod._gate_valid(session, run, gid, ch)
        if ok:
            continue
        task_p = Path(proj_root) / "card" / "task.json"
        checklist = []
        if task_p.exists():
            t = json.loads(task_p.read_text(encoding="utf-8-sig"))
            checklist = [f"{s['id']}: {s.get('meaning') or '（未填 meaning）'}" for s in t.get("scenes", [])]
        item = {"gate": gid, "title": edges.N[gid]["title"], "stale": stale,
                "checklist": checklist or [f"{edges.N[gid]['title']} 检查项"]}
        if gid in ("D05", "E07", "F06", "G07"):
            item["comments"] = review_svc.summary(proj_root)
        if gid in ("D03", "D05"):
            entries, viewed, missing = deps._review_viewed(session, run, proj_root)
            item["review"] = {"sceneCount": len(set(viewed) | set(missing)),
                              "viewed": viewed, "missing": missing,
                              "entries": len(entries)}
            if gid == "D05":
                rows = session.exec(select(Artifact).where(
                    Artifact.run_id == run_id, Artifact.node_id == "D02")).all()  # type: ignore[arg-type]
                stills = []
                contact = None
                for a in rows:
                    meta = a.meta_json or {}
                    if a.type != "PNG":
                        continue
                    if meta.get("contact_sheet"):
                        contact = {"artifact": a.id, "url": f"/api/artifacts/{a.id}/file",
                                   "sha256": a.sha256, "scenes": meta.get("scenes") or []}
                    elif meta.get("profile") == "review":
                        stills.append({"scene": meta.get("scene"), "t": meta.get("t"),
                                       "artifact": a.id, "sha256": a.sha256,
                                       "url": f"/api/artifacts/{a.id}/file"})
                diff = {}
                dr = session.exec(select(Artifact).where(
                    Artifact.run_id == run_id, Artifact.node_id == "D04")).all()  # type: ignore[arg-type]
                for a in dr:
                    if (a.meta_json or {}).get("name") == "review_diff.json":
                        try:
                            diff = json.loads(Path(a.path).read_text(encoding="utf-8"))
                        except Exception:
                            diff = {}
                item["review"].update({"stills": stills, "contactSheet": contact, "diff": diff})
        # 批准前置与 decide 用**同一个函数**算出来再随门给出：UI 只负责显示，
        # 不另写一套判据（否则判据分叉，用户点下去只收到一句 400）。
        item["precheck"] = _gate_precheck(session, run_id, gid)
        out.append(item)
    return {"items": out}


# ---------- QA 修复建议（FR-39） ----------


@router.post("/runs/{run_id}/promote")
async def run_promote(run_id: int, payload: RunPromoteIn,
                      session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    wf = session.get(Workflow, run.workflow_id)
    proj = session.get(Project, wf.project_id)  # type: ignore[arg-type]
    marker = Path(proj.root) / "out" / "CURRENT"
    write_atomic(marker, json.dumps({"run_id": run_id,
                                     "take": payload.takeName or f"take-{run_id}"}))
    deps.audit(session, "run.promote", f"run:{run_id}", after={"take": payload.takeName or ""})
    return {"ok": True}


@router.get("/runs/{run_id}/report")
async def run_report(run_id: int, session: Session = Depends(get_session)):
    """Run 报告（含指标、审批、哈希；规格 §7.9）。"""
    run = session.get(Run, run_id)
    if run is None:
        raise not_found("run")
    arts = session.exec(select(Artifact).where(Artifact.run_id == run_id)).all()  # type: ignore[arg-type]
    apps = session.exec(select(Approval).where(Approval.run_id == run_id)).all()  # type: ignore[arg-type]
    metrics = session.exec(select(Metric).where(Metric.run_id == run_id)).all()  # type: ignore[arg-type]
    nodes = session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()  # type: ignore[arg-type]
    return {"run": table_dict(run),
            "artifacts": [table_dict(a) for a in arts],
            "approvals": [table_dict(a) for a in apps],
            "metrics": [table_dict(m) for m in metrics],
            "nodes": [table_dict(n) for n in nodes]}


# ---------- FR-40 通知中心（本地 JSON、flock、(kind,ref) 去重） ----------

