"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session, select

from ..config import settings
from ..db import engine, get_session
from ..engine import edges
from ..engine import runengine as re_mod
from ..engine.cachekey import gate_content_hash
from ..engine.invalidation import impact_preview
from ..errors import ApiError, ErrorCode, not_found
from ..events import emit, subscribe, unsubscribe
from ..models import (Approval, Artifact, AuditLog, Draft, Job, Metric, NodeRun, Project,
                      Run, Style, StylePick, Workflow, WorkflowVersion, table_dict)
from ..services import environment as env_svc
from ..services import engines as engines_svc
from ..services import recommend as rec_svc
from ..services import style_index as idx_svc

router = APIRouter(prefix="/api")


def audit(session: Session, action: str, target: str, before=None, after=None):
    session.add(AuditLog(action=action, target=target, before_json=before or {}, after_json=after or {}))
    session.commit()


# ---------- 环境 / 引擎 / 库 ----------

@router.get("/health")
async def health():
    return {"ok": True, "app": "FilmFlow", "version": "0.1.0"}


@router.get("/environment")
async def environment():
    try:
        return {**env_svc.assert_environment(), "ok": True}
    except ApiError as e:
        return {"ok": False, **e.detail}


@router.get("/engines")
async def engines_list():
    return {"engines": engines_svc.list_engines(), "matrix": engines_svc.family_engine_matrix()}


@router.post("/engines/{engine_id}/validate")
async def engines_validate(engine_id: str):
    c = engines_svc.load_contract(engine_id)
    return {"engine_id": engine_id, "valid": True, "sha256": engines_svc.compute_pack_sha(engine_id)}


@router.post("/library/index")
async def library_index():
    report = idx_svc.scan_library()
    audit(Session(engine), "library.index", report["index_path"], after=report)
    return report


@router.get("/library/status")
async def library_status():
    return idx_svc.library_status()


@router.get("/styles")
async def styles_list(q: str = "", family: str = "", collection: str = "", chips: str = "",
                      limit: int = 60, cursor: int = 0, session: Session = Depends(get_session)):
    """搜索（FTS5 trigram 中文子串）+ 筛选 chips（规格 §3.2）。"""
    chips_set = set(c for c in chips.split(",") if c)
    from ..services.search import search_styles
    if q:
        items = search_styles(session, q, limit=400)
        if collection:
            items = [r for r in items if r.collection == collection]
        if family:
            items = [r for r in items if r.family == family or family in (r.sub_families_json or [])]
    else:
        items = [r for r in session.exec(select(Style)).all() if not r.id.startswith("EX")]
        if collection:
            items = [r for r in items if r.collection == collection]
        if family:
            items = [r for r in items if r.family == family or family in (r.sub_families_json or [])]
    if "可生产" in chips_set:
        items = [r for r in items if r.tokens_status == "complete" and r.engine_status == "available"]
    if "中文友好" in chips_set:
        items = [r for r in items if _zh_friendly(r)]
    if "低饱和" in chips_set:
        items = [r for r in items if _saturation(r) < 0.45]
    if "高密度" in chips_set:
        items = [r for r in items if "高密度" in r.search_text or "满版" in (r.tokens_json or {}).get("composition", [])]
    if "动态强" in chips_set:
        items = [r for r in items if (r.tokens_json or {}).get("motion", {}).get("pacing") in ("fast", "medium")]
    if "可印刷" in chips_set:
        items = [r for r in items if r.family in ("print", "collage")]
    if "≤3版" in chips_set or "<=3版" in chips_set:
        items = [r for r in items if r.family not in ("print", "collage") or len((r.tokens_json or {}).get("palette", [])) <= 3]
    total = len(items)
    items = items[cursor:cursor + limit]
    return {"total": total, "next_cursor": cursor + limit if cursor + limit < total else None,
            "items": [_style_dto(r) for r in items]}


def _fts_search(q: str) -> list[str] | None:
    try:
        with engine.connect() as conn:
            raw = conn.connection.driver_connection if hasattr(conn.connection, "driver_connection") else conn.connection
            rows = raw.execute("SELECT style_id FROM styles_fts WHERE styles_fts MATCH ? ORDER BY rank LIMIT 200", (q,)).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return None


def _zh_friendly(r: Style) -> bool:
    t = " ".join((r.tokens_json or {}).get("type") or [])
    return any(w in t for w in ("黑体", "宋体", "900", "Noto", "中文")) or any("\u4e00" <= ch <= "\u9fff" for ch in r.name)


def _saturation(r: Style) -> float:
    """从 palette hex 估饱和度均值（0-1）。"""
    import colorsys
    pal = (r.tokens_json or {}).get("palette") or []
    if not pal:
        return 0.0
    vals = []
    for h in pal[:5]:
        try:
            hx = h.lstrip("#")
            if len(hx) == 3:
                hx = "".join(c * 2 for c in hx)
            rr, gg, bb = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
            vals.append(colorsys.rgb_to_hsv(rr, gg, bb)[1])
        except Exception:
            continue
    return sum(vals) / len(vals) if vals else 0.0


def _style_dto(r: Style) -> dict:
    return {"id": r.id, "name": r.name, "collection": r.collection, "family": r.family,
            "sub_families": r.sub_families_json, "tokens_status": r.tokens_status,
            "preview_status": r.preview_status, "engine_status": r.engine_status,
            "has_cover": r.has_cover, "available": r.available, "labeled": r.labeled,
            "missing_fields": r.missing_fields, "tokens": r.tokens_json,
            "sha256": r.sha256, "path": r.path}


@router.get("/styles/{style_id}")
async def style_detail(style_id: str, session: Session = Depends(get_session)):
    r = session.get(Style, style_id)
    if not r:
        raise not_found("风格")
    return _style_dto(r)


@router.get("/styles/{style_id}/preview")
async def style_preview(style_id: str, variant: str = "thumb"):
    from sqlmodel import select
    from ..models import StylePreview
    with Session(engine) as session:
        rows = session.exec(select(StylePreview).where(
            StylePreview.style_id == style_id, StylePreview.variant == variant)).all()
        if rows:
            p = Path(rows[-1].path)
            if p.exists():
                from fastapi.responses import FileResponse
                return FileResponse(p, media_type="image/png")
    from ..services import previs as pv
    reason = "待补标" if (session.get(Style, style_id) or Style()).tokens_status != "complete" else "failed"
    from fastapi.responses import Response
    return Response(content=pv.placeholder_png(reason), media_type="image/png")


@router.get("/styles/{style_id}/similar")
async def styles_similar(style_id: str, session: Session = Depends(get_session)):
    return {"items": rec_svc.similar(session, style_id)}


@router.get("/styles/random")
async def styles_random(seed: int = 0, session: Session = Depends(get_session)):
    return rec_svc.random_explainable(session, seed)


@router.get("/recommend")
async def recommend(script: str = "", seed: int = 0, constraints: str = "",
                    session: Session = Depends(get_session)):
    c = json.loads(constraints) if constraints else None
    return {"items": rec_svc.recommend(session, script, None, c, seed)}


# ---------- 补标队列（T13） ----------

@router.get("/labels/queue")
async def label_queue(session: Session = Depends(get_session)):
    rows = session.exec(select(Style)).all()
    q = [_style_dto(r) for r in rows if r.tokens_status != "complete" and not r.id.startswith("EX")]
    return {"total": len(q), "items": q}


@router.post("/labels/{style_id}")
async def label_submit(style_id: str, payload: dict, session: Session = Depends(get_session)):
    """人工补标：补 6 字段 + 语义族 → 解锁。"""
    st = session.get(Style, style_id)
    if not st:
        raise not_found("风格")
    tokens = st.tokens_json or {}
    for k in ("palette", "texture", "screen", "motion", "type", "composition"):
        if k in payload:
            tokens[k] = payload[k]
    st.tokens_json = tokens
    st.missing_fields = [k for k in ("palette", "texture", "screen", "motion", "type", "composition")
                         if not tokens.get(k)]
    if payload.get("family"):
        st.family = payload["family"]
        from ..services import engines as eng
        st.engine_status = "available" if eng.engine_for_family(st.family) else "unavailable"
    st.labeled = bool(payload.get("labeled", True))
    st.tokens_status = "complete" if not st.missing_fields else "incomplete"
    session.add(st)
    session.commit()
    audit(session, "label.submit", style_id, after={"fields": list(payload.keys())})
    return _style_dto(st)


# ---------- 项目 / 导入 ----------

@router.get("/projects")
async def projects_list(session: Session = Depends(get_session)):
    return {"items": [table_dict(p) for p in session.exec(select(Project)).all()]}


@router.post("/projects")
async def projects_create(payload: dict, session: Session = Depends(get_session)):
    name, root = payload.get("name", "").strip(), payload.get("root", "").strip()
    if not name or not root:
        raise ApiError(ErrorCode.E_VALIDATION, "name/root 必填")
    rp = Path(root).resolve()
    if not any(str(rp).startswith(str(w.resolve())) for w in settings.workspace_roots):
        raise ApiError(ErrorCode.E_VALIDATION, f"项目根必须在白名单内：{settings.workspace_roots}")
    if not rp.is_dir():
        raise ApiError(ErrorCode.E_VALIDATION, f"目录不存在：{rp}")
    p = session.exec(select(Project).where(Project.root == str(rp))).first()  # type: ignore[arg-type,union-attr]
    if p is None:
        p = Project(name=name, root=str(rp))
        session.add(p)
        session.commit()
        session.refresh(p)
    wf = _ensure_workflow(session, p)
    run = _ensure_run(session, wf)
    audit(session, "project.create", root, after={"id": p.id})
    return {"project": table_dict(p), "workflow_id": wf.id, "run_id": run.id}


@router.post("/projects/import")
async def projects_import(payload: dict, session: Session = Depends(get_session)):
    """导入参考项目：读 task.json → workflow + run + 初始状态（T06）。"""
    root = payload.get("root", "").strip()
    rp = Path(root).resolve()
    task_p = rp / "card" / "task.json"
    if not task_p.exists():
        raise ApiError(ErrorCode.E_VALIDATION, f"缺少 card/task.json：{rp}")
    created = await projects_create({"name": payload.get("name") or rp.name, "root": str(rp)}, session)
    proj = session.get(Project, created["project"]["id"])
    task = json.loads(task_p.read_text(encoding="utf-8-sig"))
    wf = session.get(Workflow, created["workflow_id"])
    graph = wf.graph_json or {}
    graph["meta"] = {"imported": True, "phase": task.get("phase"), "task_summary": {
        "scenes": len(task.get("scenes", [])), "events": len(task.get("events", [])),
        "fps": task.get("fps"), "frames": task.get("film", {}).get("frames")}}
    graph["params"] = graph.get("params", {})
    graph["params"]["B06"] = {"mode": "import"}
    graph["params"]["B02"] = {"mode": "import"}
    graph["params"]["B03"] = {"mode": "import"}
    graph["params"]["C01"] = {"engine_id": "riso"}   # 导入项目：参考片即 riso
    stills_frames = (task.get("stills") or {}).get("frames") or []
    if isinstance(stills_frames, list) and stills_frames:
        graph["params"]["D02"] = {"scenes": [f.get("id") for f in stills_frames
                                             if isinstance(f, dict) and f.get("id")][:3]}
    wf.graph_json = graph
    session.add(wf)
    session.commit()
    # 导入隐含 A05（风格已内嵌于 task.json）：携带批准 + decision 落盘
    run = session.get(Run, created["run_id"])
    import hashlib
    ch = hashlib.sha256(task_p.read_bytes()).hexdigest()
    (rp / "card").mkdir(parents=True, exist_ok=True)
    (rp / "card" / "style_decision.json").write_text(json.dumps({
        "primary": "imported:" + rp.name, "alternates": [], "reason": "导入项目继承原风格",
        "author": "local", "decided_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(), "index_sha": ""},
        ensure_ascii=False, indent=1), encoding="utf-8")
    session.commit()
    audit(session, "project.import", str(rp), after=graph["meta"])
    return created


def _ensure_workflow(session: Session, project: Project) -> Workflow:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project.id)).first()
    if wf:
        return wf
    positions = _default_positions()
    wf = Workflow(project_id=project.id, graph_json={"positions": positions, "params": {}, "meta": {}})
    session.add(wf)
    session.commit()
    session.refresh(wf)
    session.add(WorkflowVersion(workflow_id=wf.id, version=1, graph_json=wf.graph_json))
    session.commit()
    return wf


def _default_positions() -> dict:
    """46 节点默认画布坐标（按阶段分行）。"""
    xs: dict[str, int] = {}
    counters: dict[str, int] = {}
    for nid in edges.TOPOLOGY:
        stage = nid[0]
        counters[stage] = counters.get(stage, 0) + 1
        xs[nid] = counters[stage]
    return {nid: {"x": (xs[nid] - 1) % 8 * 210 + 40, "y": edges.STAGES.index(nid[0]) * 170 + 40}
            for nid in edges.N}


def _ensure_run(session: Session, wf: Workflow) -> Run:
    run = session.exec(select(Run).where(Run.workflow_id == wf.id).order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]
    if run:
        return run
    run = Run(workflow_id=wf.id, status="idle")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.get("/projects/{project_id}/workflows")
async def project_workflows(project_id: int, session: Session = Depends(get_session)):
    return {"items": [table_dict(w) for w in session.exec(
        select(Workflow).where(Workflow.project_id == project_id)).all()]}


# ---------- drafts（T05） ----------

@router.post("/drafts")
async def drafts_create(payload: dict, session: Session = Depends(get_session)):
    d = Draft(name=payload.get("name", "未命名项目"), step=int(payload.get("step", 1)),
              payload_json=payload.get("payload", {}))
    session.add(d)
    session.commit()
    session.refresh(d)
    return table_dict(d)


@router.get("/drafts/{draft_id}")
async def drafts_get(draft_id: int, session: Session = Depends(get_session)):
    d = session.get(Draft, draft_id)
    if not d:
        raise not_found("draft")
    return table_dict(d)


@router.patch("/drafts/{draft_id}")
async def drafts_patch(draft_id: int, payload: dict, session: Session = Depends(get_session)):
    d = session.get(Draft, draft_id)
    if not d:
        raise not_found("draft")
    if "step" in payload:
        d.step = int(payload["step"])
    if "payload" in payload:
        merged = {**(d.payload_json or {}), **payload["payload"]}
        d.payload_json = merged
    session.add(d)
    session.commit()
    session.refresh(d)
    return table_dict(d)


@router.post("/drafts/{draft_id}/materialize")
async def drafts_materialize(draft_id: int, session: Session = Depends(get_session)):
    """向导第 5 步：draft → project + workflow + run；带 A05 批准（规格 §3.2）。"""
    d = session.get(Draft, draft_id)
    if not d:
        raise not_found("draft")
    payload = d.payload_json or {}
    pick = payload.get("pick") or {}
    primary = pick.get("primary")
    if not primary:
        raise ApiError(ErrorCode.E_VALIDATION, "未选择主风格（第 3 步）")
    st = session.get(Style, primary)
    if not st:
        raise not_found("主风格")
    if st.tokens_status != "complete" or st.engine_status != "available":
        raise ApiError(ErrorCode.E_ENGINE_UNAVAILABLE,
                       f"主风格 {primary} 不可生产（tokens={st.tokens_status}, engine={st.engine_status}）")
    created = await projects_create({"name": d.name, "root": payload.get("root") or str(_default_project_root(d.name))},
                                    session)
    proj = session.get(Project, created["project"]["id"])
    wf = session.get(Workflow, created["workflow_id"])
    graph = wf.graph_json or {}
    graph["meta"]["style_decision"] = pick
    graph["params"]["A01"] = {"path": str(Path(proj.root) / "card" / "copy.txt")}
    graph["params"]["A02"] = {"brief": payload.get("brief", {})}
    graph["params"]["A04"] = {"script": (payload.get("copy") or "")[:4000], "brief": payload.get("brief", {})}
    wf.graph_json = graph
    session.add(wf)
    # style_decision.json 落盘 + A05 批准记录（materialize 带 A05 批准）
    proj_dir = Path(proj.root)
    (proj_dir / "card").mkdir(parents=True, exist_ok=True)
    decision = {"primary": primary, "alternates": pick.get("alternates", []),
                "reason": pick.get("reason", ""), "author": "local",
                "decided_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "index_sha": idx_svc.library_status().get("index_sha", "")}
    (proj_dir / "card" / "style_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=1), encoding="utf-8")
    # copy 落盘
    if payload.get("copy"):
        (proj_dir / "card" / "copy.txt").write_text(payload["copy"], encoding="utf-8")
    # profile 落盘（规格 §1：常数来自 profile）
    from ..models import table_dict as td
    profile = payload.get("profile") or {"width": 1920, "height": 1080, "fps": 24,
                                         "duration": payload.get("duration", 39.5)}
    profile.setdefault("frames", round(profile.get("duration", 39.5) * profile.get("fps", 24)))
    (proj_dir / "project.profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    session.add(StylePick(project_id=proj.id, draft_id=d.id, primary_id=primary,
                          alternates_json=pick.get("alternates", []), reason=pick.get("reason", "")))
    # A05 批准由 RunEngine 在 A04 完成后自动携带（哈希与上游一致，避免假 stale）
    d.materialized_run_id = run.id
    session.add(d)
    session.commit()
    audit(session, "draft.materialize", f"draft:{d.id}", after={"run_id": run.id, "primary": primary})
    return {"run_id": run.id, "workflow_id": wf.id, "project": table_dict(proj)}


def _default_project_root(name: str) -> Path:
    base = settings.workspace_roots[0] / "filmflow-projects"
    base.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "project"
    n = 1
    while (base / f"{safe}-{n}").exists():
        n += 1
    return base / f"{safe}-{n}"


# ---------- workflow / runs ----------

@router.post("/workflows")
async def workflows_create(payload: dict, session: Session = Depends(get_session)):
    wf = Workflow(project_id=payload["projectId"], graph_json=payload.get("graph", {}))
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
async def workflow_put(workflow_id: int, payload: dict, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise not_found("workflow")
    wf.version += 1
    wf.graph_json = payload.get("graph", wf.graph_json)
    session.add(wf)
    session.add(WorkflowVersion(workflow_id=wf.id, version=wf.version, graph_json=wf.graph_json))
    session.commit()
    return table_dict(wf)


@router.post("/runs")
async def runs_create(payload: dict, session: Session = Depends(get_session)):
    wf = session.get(Workflow, payload["workflowId"])
    if not wf:
        raise not_found("workflow")
    run = Run(workflow_id=wf.id, params_snapshot=payload.get("params", {}))
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
    """只重跑失败节点（规格 §7.4）。"""
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


@router.get("/artifacts/{artifact_id}/file")
async def artifact_file(artifact_id: int, session: Session = Depends(get_session)):
    a = session.get(Artifact, artifact_id)
    if not a:
        raise not_found("artifact")
    p = Path(a.path)
    if not p.exists():
        raise not_found("产物文件")
    from fastapi.responses import FileResponse
    return FileResponse(p)


# ---------- 门审批（T10/FR-8） ----------

@router.post("/gates/{gate_id}/decide")
async def gate_decide(gate_id: str, payload: dict, session: Session = Depends(get_session)):
    run_id = int(payload.get("run_id") or payload.get("runId") or 0)
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
    decision = payload.get("decision")
    if decision not in ("approved", "rejected"):
        raise ApiError(ErrorCode.E_VALIDATION, "decision 必须是 approved/rejected")
    # 门前置校验（如 D03 ≥3 区域）
    precheck = _gate_precheck(session, run_id, gate_id)
    if precheck and decision == "approved":
        raise ApiError(ErrorCode.E_VALIDATION, f"批准前置未满足：{precheck}")
    # 不通过必须填意见
    if decision == "rejected" and not (payload.get("note") or "").strip():
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
                 content_hash=ch, author=payload.get("author", "local"),
                 note=payload.get("note", ""), checklist_json=payload.get("checklist", []))
    session.add(a)
    session.commit()
    # 解除阻塞：门 NodeRun → succeeded（批准）或保持 blocked（驳回）
    st = session.exec(select(NodeRun).where(
        NodeRun.run_id == run_id, NodeRun.node_id == gate_id)).first()  # type: ignore[arg-type]
    if st:
        st.status = "succeeded" if decision == "approved" else "blocked"
        session.add(st)
        if decision == "approved":
            run.caps_json = __import__("app.engine.caps", fromlist=["caps_after_approval"]).caps_after_approval(
                run.caps_json or [], gate_id)
            session.add(run)
        session.commit()
    emit("gate.decided", run_id, gate_id, decision=decision)
    audit(session, "gate.decide", f"{run_id}:{gate_id}", after={"decision": decision, "note": payload.get("note", "")})
    if decision == "approved":
        re_mod.start_run(run_id)   # 调度循环在等门时退出；批准即重启
    return {"ok": True, "decision": decision, "content_hash": ch[:12]}


def _gate_precheck(session: Session, run_id: int, gate_id: str) -> str | None:
    if gate_id == "D03":
        from ..engine.executors.pipeline import _project_file  # type: ignore
        run = session.get(Run, run_id)
        v = re_mod._project_root(session, run)
        vp = Path(v) / "card" / "viewed.json"
        if not vp.exists():
            return "尚无静帧查看记录（至少查看 3 个区域）"
        regions = json.loads(vp.read_text()).get("regions", [])
        if len(regions) < 3:
            return f"已查看 {len(regions)} 个区域 < 3"
    return None


@router.get("/gates/{run_id}/pending")
async def gates_pending(run_id: int, session: Session = Depends(get_session)):
    """当前等待批准的门 + 其 checklist。"""
    run = session.get(Run, run_id)
    wf = session.get(Workflow, run.workflow_id)
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
        out.append({"gate": gid, "title": edges.N[gid]["title"], "stale": stale,
                    "checklist": checklist or [f"{edges.N[gid]['title']} 检查项"]})
    return {"items": out}


# ---------- 静帧查看记录（D03 前置） ----------

@router.post("/projects/{project_id}/stills/viewed")
async def stills_viewed(project_id: int, payload: dict, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    vp = Path(proj.root) / "card" / "viewed.json"
    vp.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(vp.read_text()) if vp.exists() else {"regions": []}
    data["regions"].append(payload)
    vp.write_text(json.dumps(data, ensure_ascii=False))
    audit(session, "stills.viewed", proj.root, after=payload)
    return {"regions": len(data["regions"])}


# ---------- 任务卡编辑器 API（T11） ----------

@router.post("/projects/{project_id}/validate")
async def task_validate(project_id: int, session: Session = Depends(get_session)):
    """运行 vendored validate_task.py（编辑器校验按钮与 B07 同一验证器）。"""
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    tp = Path(proj.root) / "card" / "task.json"
    if not tp.exists():
        raise ApiError(ErrorCode.E_VALIDATION, "card/task.json 不存在：先编辑或导入")
    tool = Path(__file__).resolve().parents[2] / "tools" / "validate_task.py"
    import subprocess
    r = subprocess.run(["python3", str(tool), str(tp)], capture_output=True, text=True, timeout=60)
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise ApiError(ErrorCode.E_VALIDATION, "validator 输出异常：" + r.stderr[-300:])
    return report


@router.get("/projects/{project_id}/task")
async def task_get(project_id: int, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    tp = Path(proj.root) / "card" / "task.json"
    if not tp.exists():
        return {"exists": False, "task": None}
    return {"exists": True, "task": json.loads(tp.read_text(encoding="utf-8-sig"))}


@router.put("/projects/{project_id}/task")
async def task_put(project_id: int, payload: dict, session: Session = Depends(get_session)):
    """保存任务卡（编辑器手填/导入）。phase 与 caps 一致性检查（E_PHASE_MISMATCH）。"""
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    task = payload.get("task") or {}
    phase = task.get("phase", "card")
    allowed = {"card": {"read", "write_plan", "logic_check"},
               "still": {"read", "write_plan", "logic_check", "render_still"},
               "audition": {"read", "write_plan", "logic_check", "generate_local_music", "analyze_audio"},
               "final": {"read", "write_plan", "logic_check", "render_still", "render_video",
                         "generate_local_music", "analyze_audio"}}
    actions = set(task.get("actions", []))
    if not actions <= allowed.get(phase, set()):
        raise ApiError(ErrorCode.E_PHASE_MISMATCH,
                       f"phase={phase} 的 actions {actions - allowed.get(phase, set())} 超出白名单")
    tp = Path(proj.root) / "card" / "task.json"
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    audit(session, "task.save", proj.root, after={"phase": phase, "scenes": len(task.get("scenes", []))})
    return {"ok": True, "path": str(tp)}


# ---------- jobs / audit / 事件 ----------

@router.get("/jobs/{job_id}")
async def job_get(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    return table_dict(j)


@router.get("/audit")
async def audit_list(limit: int = 200, session: Session = Depends(get_session)):
    rows = session.exec(select(AuditLog).order_by(AuditLog.id.desc())).all()  # type: ignore[arg-type]
    return {"items": [table_dict(r) for r in rows[:limit]]}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, request: Request):
    """SSE：唯一实时通道（规格 §9.1）。"""
    q = subscribe(run_id)

    async def gen():
        try:
            yield {"event": "connected", "data": json.dumps({"run_id": run_id})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": "message", "data": item}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            unsubscribe(run_id, q)

    return EventSourceResponse(gen())


# ---------- 提升为当前 / 报告导出（M4 前置） ----------

@router.post("/runs/{run_id}/promote")
async def run_promote(run_id: int, payload: dict, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("run")
    wf = session.get(Workflow, run.workflow_id)
    proj = session.get(Project, wf.project_id)  # type: ignore[arg-type]
    marker = Path(proj.root) / "out" / "CURRENT"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"run_id": run_id, "take": payload.get("takeName", f"take-{run_id}")}))
    audit(session, "run.promote", f"run:{run_id}", after={"take": payload.get("takeName", "")})
    return {"ok": True}


@router.get("/runs/{run_id}/report")
async def run_report(run_id: int, session: Session = Depends(get_session)):
    """Run 报告（含指标、审批、哈希；规格 §7.9）。"""
    run = session.get(Run, run_id)
    arts = session.exec(select(Artifact).where(Artifact.run_id == run_id)).all()  # type: ignore[arg-type]
    apps = session.exec(select(Approval).where(Approval.run_id == run_id)).all()  # type: ignore[arg-type]
    metrics = session.exec(select(Metric).where(Metric.run_id == run_id)).all()  # type: ignore[arg-type]
    nodes = session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()  # type: ignore[arg-type]
    return {"run": table_dict(run),
            "artifacts": [table_dict(a) for a in arts],
            "approvals": [table_dict(a) for a in apps],
            "metrics": [table_dict(m) for m in metrics],
            "nodes": [table_dict(n) for n in nodes]}
