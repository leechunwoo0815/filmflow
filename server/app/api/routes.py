"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from ..atomicwrite import write_atomic
from ..config import settings
from ..db import engine, get_session
from ..engine import edges
from ..engine import runengine as re_mod
from ..engine.cachekey import gate_content_hash
from ..engine.fpscalc import frames_for, norm_fps
from ..engine.invalidation import impact_preview
from ..errors import ApiError, ErrorCode, not_found
from ..events import emit, subscribe, unsubscribe
from ..models import (
    Approval,
    Artifact,
    Asset,
    AuditLog,
    Draft,
    Job,
    Metric,
    NodeRun,
    Project,
    ProjectDoc,
    Run,
    Style,
    StylePick,
    Template,
    Workflow,
    WorkflowVersion,
    table_dict,
)
from ..security import file_response
from ..services import assets as assets_svc
from ..services import audio as audio_svc
from ..services import delivery as delivery_svc
from ..services import engines as engines_svc
from ..services import environment as env_svc
from ..services import jobs as jobs_svc
from ..services import onboarding as onboarding_svc
from ..services import preview as preview_svc
from ..services import project_docs as docs_svc
from ..services import qa as qa_svc
from ..services import recommend as rec_svc
from ..services import render_profiles as profiles_svc
from ..services import review_comments as review_svc
from ..services import style_index as idx_svc
from ..services import takes as takes_svc
from ..services import templates as tpl_svc
from ..services import timeline_ops as tl_svc
from .schemas import (
    AssetImportIn,
    AssetReplaceIn,
    AssetUpdateIn,
    AudioAlignmentSaveIn,
    AudioLicenseSaveIn,
    AudioMixSaveIn,
    DeliveryIn,
    DocRestoreIn,
    DocSaveIn,
    GateDecideIn,
    PreviewFilmIn,
    PreviewSegmentIn,
    PreviewStillIn,
    ProjectCreateIn,
    QaFixIn,
    QaUndoIn,
    RenderProfileUpdateIn,
    RunPromoteIn,
    TaskPutIn,
    TimelineOpIn,
)

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
    with Session(engine) as s:
        audit(s, "library.index", report["index_path"], after=report)
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
    from fastapi.responses import FileResponse, Response
    from sqlmodel import select

    from ..models import StylePreview
    with Session(engine) as session:
        st = session.get(Style, style_id)
        # ① 预演缓存优先
        rows = session.exec(select(StylePreview).where(
            StylePreview.style_id == style_id, StylePreview.variant == variant)).all()
        for r in reversed(rows):
            p = Path(r.path)
            if p.exists():
                return FileResponse(p, media_type="image/png")
        # ② 自带封面（规格 §3.2：193 条封面直接展示）——同目录同名 jpg / covers/
        if st and st.has_cover:
            md = Path(st.path)
            for cand in (md.with_suffix(".jpg"), md.with_suffix(".jpeg"),
                         md.parent / "covers" / f"{md.stem}.jpg"):
                if cand.exists():
                    return FileResponse(cand, media_type="image/jpeg")
    # ③ 占位（不伪装）
    from ..services import previs as pv
    with Session(engine) as session:
        st2 = session.get(Style, style_id)
        reason = "待补标" if (st2 and st2.tokens_status != "complete") else "无预演"
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


@router.post("/projects")
async def projects_create(payload: ProjectCreateIn, session: Session = Depends(get_session)):
    rp = Path(payload.root.strip()).resolve()
    _require_creatable_project_root(rp)
    if not rp.is_dir():
        raise ApiError(ErrorCode.E_VALIDATION, f"目录不存在：{rp}")
    p = session.exec(select(Project).where(Project.root == str(rp))).first()  # type: ignore[arg-type,union-attr]
    if p is None:
        p = Project(name=payload.name.strip(), root=str(rp))
        session.add(p)
        session.commit()
        session.refresh(p)
    wf = _ensure_workflow(session, p)
    run = _ensure_run(session, wf)
    audit(session, "project.create", str(rp), after={"id": p.id})
    return {"project": table_dict(p), "workflow_id": wf.id, "run_id": run.id}


@router.delete("/projects/{project_id}")
async def projects_delete(project_id: int, confirm: bool = False, remove_dir: bool = True,
                          confirm_name: str = "", force: bool = False,
                          session: Session = Depends(get_session)):
    """P1-06：删除项目（级联清库 + 目录）。

    confirm=false 时只回删除计划；保护名单（rumor 回归基线、演示项目）必须回显 confirm_name；
    目录策略不合规时一律拒绝；有在飞作业时需显式 force=true（崩溃遗留作业无法自证已死），
    全部校验都在动数据之前完成，force 会记入审计。
    """
    from ..services import project_cleanup as cleanup_svc
    if not confirm:
        return {"warning": "这是级联删除，重发请求并带 confirm=true 才会执行",
                **cleanup_svc.plan_delete(session, project_id)}
    return cleanup_svc.delete_project(session, project_id, remove_dir=remove_dir,
                                      confirm_name=confirm_name, force=force)


@router.post("/projects/import")
async def projects_import(payload: dict, session: Session = Depends(get_session)):
    """导入参考项目：读 task.json → workflow + run + 初始状态（T06）。"""
    root = payload.get("root", "").strip()
    rp = Path(root).resolve()
    _require_creatable_project_root(rp)
    task_p = rp / "card" / "task.json"
    if not task_p.exists():
        raise ApiError(ErrorCode.E_VALIDATION, f"缺少 card/task.json：{rp}")
    created = await projects_create(ProjectCreateIn(name=payload.get("name") or rp.name,
                                                      root=str(rp)), session)
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
    flag_modified(wf, "graph_json")
    session.add(wf)
    session.commit()
    # 导入隐含 A05（风格已内嵌于 task.json）：携带批准 + decision 落盘
    run = session.get(Run, created["run_id"])
    import hashlib
    ch = hashlib.sha256(task_p.read_bytes()).hexdigest()
    write_atomic(rp / "card" / "style_decision.json", json.dumps({
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
    project_name = (d.name or "").strip()
    brief_title = str((payload.get("brief") or {}).get("title") or "").strip()
    if brief_title and project_name in ("", "向导草稿"):
        project_name = brief_title
    created = await projects_create(ProjectCreateIn(
        name=project_name or "第一条片",
        root=payload.get("root") or str(_default_project_root(project_name or "第一条片"))), session)
    proj = session.get(Project, created["project"]["id"])
    wf = session.get(Workflow, created["workflow_id"])
    graph = wf.graph_json or {}
    graph["meta"]["style_decision"] = pick
    graph["params"]["A01"] = {"path": str(Path(proj.root) / "card" / "copy.txt")}
    graph["params"]["A02"] = {"brief": payload.get("brief", {})}
    graph["params"]["A04"] = {"script": (payload.get("copy") or "")[:4000], "brief": payload.get("brief", {})}
    wf.graph_json = graph
    flag_modified(wf, "graph_json")
    session.add(wf)
    # style_decision.json 落盘 + A05 批准记录（materialize 带 A05 批准）
    proj_dir = Path(proj.root)
    (proj_dir / "card").mkdir(parents=True, exist_ok=True)
    decision = {"primary": primary, "alternates": pick.get("alternates", []),
                "reason": pick.get("reason", ""), "author": "local",
                "decided_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "index_sha": idx_svc.library_status().get("index_sha", "")}
    write_atomic(proj_dir / "card" / "style_decision.json",
                 json.dumps(decision, ensure_ascii=False, indent=1))
    # copy 落盘
    if payload.get("copy"):
        write_atomic(proj_dir / "card" / "copy.txt", payload["copy"])
    # profile 落盘（规格 §1：常数来自 profile）
    profile = payload.get("profile") or {"width": 1920, "height": 1080, "fps": 24,
                                         "duration": payload.get("duration", 39.5)}
    profile.setdefault("frames", round(profile.get("duration", 39.5) * profile.get("fps", 24)))
    write_atomic(proj_dir / "project.profile.json", json.dumps(profile, ensure_ascii=False, indent=1))
    placeholder = payload.get("audioPlaceholder")
    if isinstance(placeholder, dict) and placeholder.get("kind"):
        audio_svc.save_placeholder(
            proj.root, str(placeholder["kind"]),
            float(placeholder.get("duration") or profile.get("duration") or 0),
            str(placeholder.get("source") or ""))
    # 初始化文档事实源：timeline 一旦落库，改文案不会重建时间轴（增量只脏目标场景）
    from ..services.project_docs import build_script_doc, build_timeline_doc
    profile_content = {"schema": docs_svc.SCHEMAS["profile"], **profile}
    script_doc = docs_svc.get_doc(session, proj.id, "script")
    if script_doc is None and payload.get("copy"):
        script_content = build_script_doc(payload["copy"],
                                          (payload.get("brief") or {}).get("title") or d.name)
        script_doc, _ = docs_svc.save_doc(session, proj.id, "script", script_content, 0, "materialize")
    if docs_svc.get_doc(session, proj.id, "profile") is None:
        docs_svc.save_doc(session, proj.id, "profile", profile_content, 0, "materialize")
    if script_doc is not None and docs_svc.get_doc(session, proj.id, "timeline") is None:
        timeline = build_timeline_doc(script_doc.content_json, profile_content)
        docs_svc.save_doc(session, proj.id, "timeline", timeline, 0, "materialize")
    run = session.get(Run, created["run_id"])
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
    d = base / f"{safe}-{n}"
    d.mkdir(parents=True, exist_ok=True)   # 默认根必须真实创建（projects_create 校验目录存在）
    return d


# ---------- 新手模板（FR-31） ----------

FIRST_TEMPLATES = [
    {"id": "voice15", "title": "口播 15 秒", "seconds": 15,
     "description": "一个观点 + 三个短句，适合口播开场。",
     "copy": "一句话说清观点。用三个例子说明。最后给一个行动建议。",
     "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 15.0},
     "style_family": "print", "audioPlaceholder": "voice"},
    {"id": "opinion30", "title": "观点 30 秒", "seconds": 30,
     "description": "提出问题、给出证据、收束观点。",
     "copy": "先说一个反常识判断。再给两个可验证的证据。把证据翻译成观众能记住的话。最后落到一个具体行动。",
     "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 30.0},
     "style_family": "print", "audioPlaceholder": "voice"},
    {"id": "product40", "title": "产品 40 秒", "seconds": 40,
     "description": "痛点、方案、证据、行动，五场完整短片。",
     "copy": "先说用户每天遇到的麻烦。指出旧方案为什么失效。给出你的方案与关键差异。用一个真实结果证明。最后告诉用户下一步做什么。",
     "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 40.0},
     "style_family": "print", "audioPlaceholder": "voice"},
]


def _saved_templates(session: Session, kind: str = "") -> list[Template]:
    stmt = select(Template)
    if kind:
        stmt = stmt.where(Template.kind == kind)
    return session.exec(stmt.order_by(Template.id.desc())).all()  # type: ignore[arg-type]


def _resolve_template(session: Session, template_id: str) -> tuple[str, dict, Template | None, dict | None]:
    if template_id.startswith("saved:"):
        try:
            tid = int(template_id.split(":", 1)[1])
        except ValueError:
            raise not_found("模板")
        t = session.get(Template, tid)
        if not t:
            raise not_found("模板")
        return t.kind, t.content_json or {}, t, None
    if template_id.startswith("builtin:scene-"):
        item = next((x for x in tpl_svc.BUILTIN_SCENE_TEMPLATES if x["id"] == template_id), None)
        if not item:
            raise not_found("场景模板")
        content = {k: v for k, v in item.items() if k not in ("id", "name", "kind", "description")}
        return "scene", content, None, item
    item = next((x for x in FIRST_TEMPLATES if x["id"] == template_id), None)
    if item:
        return "project", item, None, item
    raise not_found("模板")


def _latest_style(session: Session, project_id: int) -> tuple[StylePick | None, Style | None]:
    pick = session.exec(select(StylePick).where(
        StylePick.project_id == project_id).order_by(StylePick.id.desc())).first()  # type: ignore[arg-type,union-attr]
    style = session.get(Style, pick.primary_id) if pick and pick.primary_id else None
    return pick, style


def _project_template_content(session: Session, project_id: int, copy,
                              description: str = "") -> dict:
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    profile = docs_svc.doc_payload(session, project_id, proj.root, "profile")["content"]
    timeline = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    script = docs_svc.doc_payload(session, project_id, proj.root, "script")["content"]
    delivery = docs_svc.doc_payload(session, project_id, proj.root, "delivery")["content"]
    pick, style = _latest_style(session, project_id)
    if copy is None:
        copy = script.get("text", "")
    return tpl_svc.project_template_content(
        profile=profile, timeline=timeline, style_id=(pick.primary_id if pick else ""),
        style_family=(style.family if style else "print"), delivery=delivery,
        copy=str(copy or ""), description=description, source_project_id=project_id)


@router.get("/templates")
async def templates_list(kind: str = "", session: Session = Depends(get_session)):
    items: list[dict] = []
    if kind in ("", "project"):
        items.extend([{**t, "kind": "project", "saved": False, "version": 0}
                      for t in FIRST_TEMPLATES])
        items.extend(tpl_svc.saved_dto(t) for t in _saved_templates(session, "project"))
    if kind in ("scene", "all"):
        items.extend(tpl_svc.builtin_scene_dto(x) for x in tpl_svc.BUILTIN_SCENE_TEMPLATES)
        items.extend(tpl_svc.saved_dto(t) for t in _saved_templates(session, "scene"))
    return {"items": items}


@router.get("/templates/{template_id}")
async def template_get(template_id: str, session: Session = Depends(get_session)):
    kind, content, saved, builtin = _resolve_template(session, template_id)
    if saved:
        return {"template": tpl_svc.saved_dto(saved, with_content=True)}
    if kind == "scene":
        return {"template": tpl_svc.builtin_scene_dto(builtin or {})}
    return {"template": {**builtin, "kind": "project", "saved": False, "version": 0,
                         "content": content}}


@router.delete("/templates/{template_id}")
async def template_delete(template_id: str, session: Session = Depends(get_session)):
    if not template_id.startswith("saved:"):
        raise ApiError(ErrorCode.E_VALIDATION, "内置模板不能删除")
    _, content, saved, _ = _resolve_template(session, template_id)
    if not saved:
        raise not_found("模板")
    session.delete(saved)
    session.commit()
    audit(session, "template.delete", template_id)
    return {"deleted": saved.id}


async def _materialize_saved_template(session: Session, tpl: Template, variables: dict,
                                      name: str, copy_override: str | None = None) -> dict:
    content = tpl.content_json or {}
    vars = {str(k): v for k, v in (variables or {}).items()}
    copy_src = copy_override if copy_override is not None else str(content.get("copy") or "")
    copy, missing_copy = tpl_svc.substitute(copy_src, vars)
    profile_src, missing_profile = tpl_svc.substitute(content.get("profile") or {}, vars)
    content_sub, missing_content = tpl_svc.substitute(content, vars)
    profile = {k: v for k, v in profile_src.items() if k != "schema"}
    profile.setdefault("width", 1920)
    profile.setdefault("height", 1080)
    profile.setdefault("fps", 24)
    result = await _materialize_first(
        session, name=name, copy=str(copy), profile=profile,
        family=str(content.get("style_family") or "print"), title=name,
        source=f"{tpl.id}", style_id=str(content.get("style_id") or ""))
    pid = int(result["project"]["id"])
    proj = session.get(Project, pid)
    if not proj:
        raise not_found("项目")
    # P1-09：项目行出现后的任何失败（资产/文档/锁）都必须清掉半成品，不留孤儿项目
    try:
        return await _finish_saved_template_materialize(
            session, tpl, content, content_sub, profile, pid, proj, result,
            missing_copy, missing_profile, missing_content, name)
    except Exception:
        from ..services.project_cleanup import delete_project
        try:
            delete_project(session, pid, remove_dir=True)
        except Exception:
            pass
        raise


async def _finish_saved_template_materialize(session, tpl, content, content_sub, profile,
                                             pid, proj, result,
                                             missing_copy, missing_profile, missing_content,
                                             name) -> dict:
    proj = session.get(Project, pid) if proj is None else proj
    assets_svc.ensure_asset_shas(session, content.get("sourceProjectId"), proj.root,
                                 content.get("assetShas") or [])
    current_profile = docs_svc.doc_payload(session, pid, proj.root, "profile")
    script = docs_svc.doc_payload(session, pid, proj.root, "script")["content"]
    timeline = tpl_svc.build_timeline_from_content(content_sub, script, profile)
    profile_doc = {"schema": docs_svc.SCHEMAS["profile"], **profile,
                   "duration": timeline["duration"], "frames": timeline["frames"]}
    docs_svc.save_doc(session, pid, "profile", profile_doc, current_profile["version"],
                      "template")
    current_tl = docs_svc.doc_payload(session, pid, proj.root, "timeline")
    docs_svc.save_doc(session, pid, "timeline", timeline, current_tl["version"], "template")
    delivery = content_sub.get("delivery") or {}
    if delivery.get("schema") == docs_svc.SCHEMAS["delivery"]:
        current_delivery = docs_svc.doc_payload(session, pid, proj.root, "delivery")
        docs_svc.save_doc(session, pid, "delivery", delivery,
                          current_delivery["version"], "template")
    lock = tpl_svc.write_lock(proj.root, tpl.id or 0, tpl.version, content.get("variables"))
    missing = sorted(set(missing_copy) | set(missing_profile) | set(missing_content))
    result.update({"template": f"saved:{tpl.id}", "templateId": tpl.id,
                   "templateVersion": tpl.version, "missingVariables": missing,
                   "lock": lock, "name": name})
    return result


@router.post("/projects/{project_id}/save-template")
async def project_save_template(project_id: int, payload: dict,
                                session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    name = str(payload.get("name") or f"{proj.name} 模板").strip()[:80]
    if not name:
        raise ApiError(ErrorCode.E_VALIDATION, "模板名称不能为空")
    content = _project_template_content(session, project_id, payload.get("copy"),
                                        str(payload.get("description") or ""))
    t = Template(kind="project", name=name, description=str(payload.get("description") or ""),
                 content_json=content)
    session.add(t)
    session.commit()
    session.refresh(t)
    audit(session, "template.save", f"project:{project_id}", after={"template": t.id})
    return {"template": tpl_svc.saved_dto(t, with_content=True)}


@router.post("/templates/{template_id}/version")
async def template_new_version(template_id: str, payload: dict,
                               session: Session = Depends(get_session)):
    if not template_id.startswith("saved:"):
        raise ApiError(ErrorCode.E_VALIDATION, "内置模板不能改版本")
    _, _content, saved, _ = _resolve_template(session, template_id)
    if not saved or saved.kind != "project":
        raise ApiError(ErrorCode.E_VALIDATION, "只有项目模板可保存新版本")
    project_id = int(payload.get("projectId") or 0)
    content = _project_template_content(session, project_id, payload.get("copy"),
                                        str(payload.get("description") or saved.description))
    saved.content_json = content
    flag_modified(saved, "content_json")
    saved.version += 1
    saved.updated_at = datetime.now(UTC)
    if payload.get("name"):
        saved.name = str(payload["name"])[:80]
    session.add(saved)
    session.commit()
    session.refresh(saved)
    audit(session, "template.version", template_id,
          after={"version": saved.version, "project": project_id})
    return {"template": tpl_svc.saved_dto(saved, with_content=True)}


@router.post("/projects/{project_id}/scenes/{scene_id}/save-template")
async def project_save_scene_template(project_id: int, scene_id: str, payload: dict,
                                      session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    timeline = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    scene = next((s for s in timeline.get("scenes") or [] if s.get("id") == scene_id), None)
    if not scene:
        raise not_found("场景")
    name = str(payload.get("name") or f"{scene_id} 场景模板").strip()[:80]
    content = tpl_svc.scene_template_content(
        scene, keep_text=bool(payload.get("keepText")),
        description=str(payload.get("description") or ""), source_project_id=project_id)
    t = Template(kind="scene", name=name, description=str(payload.get("description") or ""),
                 content_json=content)
    session.add(t)
    session.commit()
    session.refresh(t)
    audit(session, "template.scene.save", f"project:{project_id}:{scene_id}",
          after={"template": t.id})
    return {"template": tpl_svc.saved_dto(t, with_content=True)}


@router.post("/projects/{project_id}/timeline/scene-template")
async def project_apply_scene_template(project_id: int, payload: dict,
                                       session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    kind, content, saved, builtin = _resolve_template(session, str(payload.get("templateId") or ""))
    if kind != "scene":
        raise ApiError(ErrorCode.E_VALIDATION, "不是场景模板")
    scene = deepcopy(content)
    for key in ("schema", "description", "id", "name", "kind"):
        scene.pop(key, None)
    scene["duration"] = float(scene.get("duration") or 2.5)
    scene.setdefault("text", "新场景。")
    assets_svc.ensure_asset_shas(session, content.get("sourceProjectId"), proj.root,
                                 content.get("assetShas") or [])
    current = docs_svc.doc_payload(session, project_id, proj.root, "timeline")
    script = docs_svc.doc_payload(session, project_id, proj.root, "script")["content"]
    index = payload.get("index")
    if payload.get("afterSceneId"):
        ids = [s.get("id") for s in current["content"].get("scenes") or []]
        try:
            index = ids.index(str(payload["afterSceneId"])) + 1
        except ValueError:
            index = None
    try:
        new_content, meta = tl_svc.apply(current["content"], script, "add_scene",
                                         {"scene": scene, "index": index})
    except tl_svc.TimelineOpError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"{e.code}: {e.message}",
                       status=e.status, details=e.details)
    base = int(payload.get("baseVersion") if payload.get("baseVersion") is not None
               else current["version"])
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", new_content, base,
                                  payload.get("author", "scene-template"))
    before = {s.get("id") for s in current["content"].get("scenes") or []}
    inserted = next((s.get("id") for s in new_content.get("scenes") or [] if s.get("id") not in before), "")
    audit(session, "template.scene.apply", f"project:{project_id}",
          after={"template": payload.get("templateId"), "sceneId": inserted})
    return {**docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "sceneId": inserted, "diff": diff, "validation": meta["validation"],
            "template": (f"saved:{saved.id}" if saved else str(payload.get("templateId")))}


@router.get("/projects/{project_id}/template-lock")
async def project_template_lock(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return {"lock": tpl_svc.read_lock(proj.root)}


@router.get("/projects/{project_id}/template-diff")
async def project_template_diff(project_id: int, templateId: str,
                                session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    kind, content, saved, _ = _resolve_template(session, templateId)
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "升级只支持已保存的项目模板")
    profile = docs_svc.doc_payload(session, project_id, proj.root, "profile")["content"]
    timeline = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    return {"template": tpl_svc.saved_dto(saved), "lock": tpl_svc.read_lock(proj.root),
            "diff": tpl_svc.template_diff(profile, timeline, content)}


@router.post("/projects/{project_id}/template-upgrade")
async def project_template_upgrade(project_id: int, payload: dict,
                                   session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    kind, content, saved, _ = _resolve_template(session, str(payload.get("templateId") or ""))
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "升级只支持已保存的项目模板")
    profile_doc = docs_svc.doc_payload(session, project_id, proj.root, "profile")
    timeline_doc = docs_svc.doc_payload(session, project_id, proj.root, "timeline")
    diff = tpl_svc.template_diff(profile_doc["content"], timeline_doc["content"], content)
    if not payload.get("confirm"):
        return {"applied": False, "diff": diff, "lock": tpl_svc.read_lock(proj.root)}
    assets_svc.ensure_asset_shas(session, content.get("sourceProjectId"), proj.root,
                                 content.get("assetShas") or [])
    script = docs_svc.doc_payload(session, project_id, proj.root, "script")["content"]
    new_timeline, prof_overlay = tpl_svc.overlay_template(timeline_doc["content"], content, script)
    new_profile = {**profile_doc["content"], **prof_overlay,
                   "duration": new_timeline["duration"], "frames": new_timeline["frames"],
                   "schema": docs_svc.SCHEMAS["profile"]}
    docs_svc.save_doc(session, project_id, "profile", new_profile, profile_doc["version"],
                      "template-upgrade")
    docs_svc.save_doc(session, project_id, "timeline", new_timeline, timeline_doc["version"],
                      "template-upgrade")
    lock = tpl_svc.write_lock(proj.root, saved.id or 0, saved.version,
                              content.get("variables"))
    audit(session, "template.upgrade", f"project:{project_id}",
          after={"template": saved.id, "diff": diff})
    return {"applied": True, "diff": diff, "lock": lock}


@router.post("/series/from-template")
async def series_from_template(payload: dict, session: Session = Depends(get_session)):
    template_id = str(payload.get("templateId") or "")
    kind, content, saved, _ = _resolve_template(session, template_id)
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "系列只支持已保存的项目模板")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ApiError(ErrorCode.E_VALIDATION, "items 不能为空")
    if len(items) > 5:
        raise ApiError(ErrorCode.E_VALIDATION, "v1 系列最多 5 项；批量 CSV/队列属 R4 FR-46")
    prefix = str(payload.get("name") or saved.name or "系列")
    results = []
    for i, item in enumerate(items):
        item = item if isinstance(item, dict) else {"copy": str(item)}
        vars = item.get("variables") or item.get("vars") or item
        name = str(item.get("name") or f"{prefix} {i + 1:02d}")
        try:
            r = await _materialize_saved_template(
                session, saved, vars if isinstance(vars, dict) else {}, name,
                item.get("copy"))
            results.append({"index": i, "ok": True, "name": name,
                            "project": r["project"], "run_id": r["run_id"],
                            "missingVariables": r.get("missingVariables")})
        except Exception as e:
            session.rollback()
            try:
                session.refresh(saved)
            except Exception:
                pass
            results.append({"index": i, "ok": False, "name": name, "error": str(e)[:300]})
    return {"template": f"saved:{saved.id}", "items": results,
            "created": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "note": "v1 同步创建；CSV 批量/队列/批量 zip 属 R4 FR-46，未实现"}


def _first_available_style(session: Session, family: str) -> Style:
    st = session.exec(select(Style).where(
        Style.family == family, Style.engine_status == "available",
        Style.tokens_status == "complete")).first()  # type: ignore[arg-type,union-attr]
    if not st:
        st = session.exec(select(Style).where(Style.family == family)).first()  # type: ignore[arg-type,union-attr]
    if not st:
        raise ApiError(ErrorCode.E_STYLE_INCOMPLETE, f"没有可用的 {family} 风格")
    return st


async def _materialize_first(session: Session, *, name: str, copy: str, profile: dict,
                             family: str, title: str, source: str,
                             placeholder: str = "voice", style_id: str = "") -> dict:
    """模板/示例共用：建草稿 → 项目 → 文档/占位 → Run。"""
    st = session.get(Style, style_id) if style_id else None
    if st is None or not st.available or st.tokens_status != "complete":
        st = _first_available_style(session, family)
    root = _default_project_root(name)
    profile = dict(profile)
    profile["fps"] = norm_fps(profile["fps"])  # P1-12
    profile.setdefault("frames", frames_for(profile["duration"], profile["fps"]))
    d = Draft(name=name, step=5, payload_json={
        "root": str(root), "copy": copy, "profile": profile,
        "pick": {"primary": st.id, "alternates": [], "reason": f"新手模板 {source}"},
        "brief": {"title": title},
        "audioPlaceholder": {"kind": placeholder, "duration": float(profile["duration"]),
                             "source": source},
    })
    session.add(d)
    session.commit()
    session.refresh(d)
    result = await drafts_materialize(d.id or 0, session)
    result["template"] = source
    return result


@router.post("/projects/from-template")
async def project_from_template(payload: dict, session: Session = Depends(get_session)):
    template_id = str(payload.get("templateId") or "")
    if template_id.startswith("saved:"):
        kind, _content, saved, _ = _resolve_template(session, template_id)
        if kind != "project" or not saved:
            raise ApiError(ErrorCode.E_VALIDATION, "不是项目模板")
        return await _materialize_saved_template(
            session, saved, payload.get("variables") or {},
            str(payload.get("name") or saved.name), payload.get("copy"))
    tpl = next((t for t in FIRST_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise not_found("模板")
    return await _materialize_first(
        session, name=str(payload.get("name") or f"第一条片 · {tpl['title']}"),
        copy=tpl["copy"], profile=tpl["profile"], family=tpl.get("style_family") or "print",
        title=tpl["title"], source=tpl["id"],
        placeholder=tpl.get("audioPlaceholder") or "voice")


# ---------- 只读示例项目（FR-31） ----------

@router.get("/examples")
async def examples_list():
    items = [{k: v for k, v in x.items() if k != "copy"} | {"copyPreview": x["copy"][:120]}
             for x in onboarding_svc.load_examples()]
    return {"items": items}


@router.post("/examples/{example_id}/clone")
async def example_clone(example_id: str, payload: dict | None = None,
                        session: Session = Depends(get_session)):
    item = onboarding_svc.example(example_id)
    if not item:
        raise not_found("示例")
    payload = payload or {}
    result = await _materialize_first(
        session, name=str(payload.get("name") or f"我的示例 · {item['title']}"),
        copy=item["copy"], profile=onboarding_svc.example_profile(item),
        family=str(item.get("family") or "print"),
        title=str(item.get("titleText") or item["title"]), source=item["id"],
        placeholder=str(item.get("audioPlaceholder") or "voice"))
    result["example"] = item["id"]
    return result


@router.get("/wizard/titles")
async def wizard_titles(copy: str = ""):
    return {"items": onboarding_svc.title_candidates(copy), "source": "local"}


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
    flag_modified(wf, "graph_json")
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
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
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
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    scene_id = str(payload.sceneId or payload.scene_id or "")
    if not scene_id:
        raise ApiError(ErrorCode.E_VALIDATION, "sceneId 必填")
    job = preview_svc.create_segment_job(
        session, project_id, scene_id, payload.start, payload.end,
        profile=payload.profile,
        watermark=payload.watermark)
    audit(session, "preview.segment", f"project:{project_id}",
          after={"job": job.id, "scene": scene_id, "start": job.start, "end": job.end})
    return preview_svc.job_payload(job)


@router.post("/projects/{project_id}/preview/film", status_code=202)
async def project_preview_film(project_id: int, payload: PreviewFilmIn,
                               session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    job = preview_svc.create_film_job(
        session, project_id, profile=payload.profile,
        watermark=payload.watermark)
    audit(session, "preview.film", f"project:{project_id}",
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
    proj = _project_or_404(session, job.project_id)
    base = (Path(proj.root).resolve() / "out" / "preview")
    p = Path(job.path).resolve()
    if not p.is_relative_to(base) or not p.exists():
        raise not_found("预览文件")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


@router.get("/projects/{project_id}/preview/cache")
async def project_preview_cache(project_id: int, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    return preview_svc.PreviewCache(project_id).stats()


# ---------- 交付 v1（FR-28） ----------

@router.post("/projects/{project_id}/delivery", status_code=202)
async def project_delivery(project_id: int, payload: DeliveryIn,
                           session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    run_id = payload.runId if payload.runId is not None else payload.run_id
    job = delivery_svc.create_job(session, proj, run_id, payload.profile)
    asyncio.create_task(delivery_svc.run_delivery(job.id or 0))
    audit(session, "delivery.create", f"project:{project_id}", after={"job": job.id})
    return {"jobId": job.id, "kind": job.kind, "status": job.status, "priority": job.priority}


@router.get("/projects/{project_id}/deliveries")
async def project_deliveries(project_id: int, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    rows = jobs_svc.list_jobs(session, kind="delivery", limit=200)
    return {"items": [table_dict(j) for j in rows
                      if (j.payload_json or {}).get("projectId") == project_id]}


@router.get("/projects/{project_id}/deliveries/{run_id}")
async def project_delivery_detail(project_id: int, run_id: int,
                                  session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
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
    proj = _project_or_404(session, project_id)
    base = (Path(proj.root).resolve() / "out" / "deliveries" / str(run_id)).resolve()
    p = (base / name).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        raise not_found("交付文件")
    return file_response(p, download_name=name)


# ---------- 渲染档位（FR-24） ----------

@router.get("/projects/{project_id}/render-profile")
async def project_render_profile(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    imported = docs_svc.is_imported(session, project_id)
    return profiles_svc.resolve(proj.root, _project_profile(proj.root),
                                allow_low_final=imported)


@router.put("/projects/{project_id}/render-profile")
async def project_render_profile_update(project_id: int, payload: RenderProfileUpdateIn,
                                        session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    root = Path(proj.root).resolve()
    _require_workspace_root(root)
    imported = docs_svc.is_imported(session, project_id)
    body = payload.model_dump(exclude_none=True)
    resolved = profiles_svc.save(root, body, _project_profile(root),
                                 allow_low_final=imported)
    audit(session, "render.profile", f"project:{project_id}",
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
    _require_workspace_root(p.resolve())
    return file_response(p)


# ---------- 门审批（T10/FR-8） ----------

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
        profiles_svc.ensure_final_ready(session, run, root, imported, _project_profile(root))
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
    audit(session, "gate.decide", f"{run_id}:{gate_id}",
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
        entries, viewed, missing = _review_viewed(session, run, root)
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
        item = {"gate": gid, "title": edges.N[gid]["title"], "stale": stale,
                "checklist": checklist or [f"{edges.N[gid]['title']} 检查项"]}
        if gid in ("D05", "E07", "F06", "G07"):
            item["comments"] = review_svc.summary(proj_root)
        if gid in ("D03", "D05"):
            entries, viewed, missing = _review_viewed(session, run, proj_root)
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
        out.append(item)
    return {"items": out}


# ---------- QA 修复建议（FR-39） ----------

@router.get("/projects/{project_id}/qa")
async def project_qa(project_id: int, runId: int | None = None,
                     session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return qa_svc.analyze(session, proj, runId)


@router.get("/runs/{run_id}/qa")
async def run_qa(run_id: int, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if not run:
        raise not_found("Run")
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        raise not_found("Workflow")
    proj = _project_or_404(session, wf.project_id)
    return qa_svc.analyze(session, proj, run_id)


@router.post("/projects/{project_id}/qa/fix")
async def project_qa_fix(project_id: int, payload: QaFixIn,
                         session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    if docs_svc.is_imported(session, project_id):
        raise ApiError(ErrorCode.E_VALIDATION, "导入项目只读，不能应用 QA 修复", status=409)
    try:
        entry = qa_svc.apply_fix(session, proj, payload.issueId, payload.action,
                                 payload.payload, payload.runId)
    except ValueError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"E_QA_FIX: {e}", status=409)
    audit(session, "qa.fix", f"{project_id}:{payload.issueId}",
          after={"action": payload.action, "result": entry.get("verified")})
    return {"fix": entry, "qa": qa_svc.analyze(
        session, proj, entry.get("runId"))}


@router.post("/projects/{project_id}/qa/undo")
async def project_qa_undo(project_id: int, payload: QaUndoIn,
                          session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    if docs_svc.is_imported(session, project_id):
        raise ApiError(ErrorCode.E_VALIDATION, "导入项目只读，不能撤销 QA 修复", status=409)
    try:
        entry = qa_svc.undo_fix(session, proj, payload.fixId)
    except ValueError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"E_QA_UNDO: {e}", status=409)
    audit(session, "qa.undo", f"{project_id}:{payload.fixId}")
    return {"fix": entry, "qa": qa_svc.analyze(session, proj, entry.get("runId"))}


@router.get("/projects/{project_id}/qa/report")
async def project_qa_report(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return qa_svc.report(proj)


# ---------- 资产库（FR-36） ----------

def _asset_project(session: Session, project_id: int | None) -> Project | None:
    if not project_id:
        return None
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    return proj


@router.get("/assets")
async def assets_list(scope: str = "global", projectId: int | None = None,
                      kind: str = "", q: str = "", includeArchived: bool = False,
                      session: Session = Depends(get_session)):
    if scope not in ("global", "project"):
        raise ApiError(ErrorCode.E_VALIDATION, "scope 必须是 global/project")
    if scope == "project":
        _asset_project(session, projectId)
    items = assets_svc.list_assets(session, scope, projectId, kind, q, includeArchived)
    return {"items": items, "scope": scope, "projectId": projectId}


@router.post("/assets")
async def assets_import(payload: AssetImportIn, session: Session = Depends(get_session)):
    scope = payload.scope
    proj = _asset_project(session, payload.projectId) if scope == "project" else None
    asset, deduped = await asyncio.to_thread(
        assets_svc.import_asset, session, scope, proj.root if proj else None,
        payload.filename, payload.data, payload.kind, payload.name,
        payload.tags, payload.license, payload.author)
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    audit(session, "asset.import", f"{scope}:{asset.id}",
          after={"sha256": asset.sha256, "kind": asset.kind, "deduped": deduped})
    return {"asset": assets_svc.asset_dto(asset, usages), "deduped": deduped}


@router.get("/assets/{asset_id}")
async def assets_get(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    return {"asset": assets_svc.asset_dto(asset, usages)}


@router.patch("/assets/{asset_id}")
async def assets_update(asset_id: int, payload: AssetUpdateIn,
                        session: Session = Depends(get_session)):
    body = {k: v for k, v in payload.model_dump().items() if v is not None}
    asset = await asyncio.to_thread(assets_svc.update_asset, session, asset_id, body)
    audit(session, "asset.update", str(asset_id),
          after={"name": (asset.meta_json or {}).get("name"), "archived": asset.archived})
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    return {"asset": assets_svc.asset_dto(asset, usages)}


@router.delete("/assets/{asset_id}")
async def assets_delete(asset_id: int, force: bool = False,
                        session: Session = Depends(get_session)):
    result = await asyncio.to_thread(assets_svc.delete_asset, session, asset_id, force)
    audit(session, "asset.delete", str(asset_id), after=result)
    return result


@router.get("/assets/{asset_id}/file")
async def assets_file(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    p = Path(asset.path)
    if not p.exists():
        raise ApiError(ErrorCode.E_ASSET_MISSING, "资产文件缺失", status=404)
    # P3：SVG 可携带 <script>，同源直开=存储型脚本执行；白名单 Content-Type + CSP sandbox + nosniff
    return file_response(p, download_name=p.name)


@router.get("/assets/{asset_id}/thumb")
async def assets_thumb(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    p = assets_svc._thumb_path(asset)
    if not p:
        raise ApiError(ErrorCode.E_NOT_FOUND, "缩略图不存在", status=404)
    return file_response(p)


@router.get("/assets/{asset_id}/waveform")
async def assets_waveform(asset_id: int, w: int = 2000,
                          session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    if asset.kind != "audio":
        raise ApiError(ErrorCode.E_ASSET_KIND, "只有音频资产有波形")
    data = await asyncio.to_thread(assets_svc.waveform, asset.path, w)
    return {**data, "assetId": asset_id, "duration": (asset.meta_json or {}).get("duration", 0)}


@router.post("/assets/{asset_id}/font-check")
async def assets_font_check(asset_id: int, payload: dict,
                            session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    if asset.kind != "font":
        raise ApiError(ErrorCode.E_ASSET_KIND, "只有字体资产可做覆盖检查")
    return await asyncio.to_thread(assets_svc.font_coverage, asset.path,
                                   str(payload.get("text") or ""))


@router.post("/assets/{asset_id}/replace")
async def assets_replace(asset_id: int, payload: AssetReplaceIn,
                         session: Session = Depends(get_session)):
    old = assets_svc.get_asset(session, asset_id)
    new = assets_svc.get_asset(session, payload.assetId)
    if old.kind != new.kind:
        raise ApiError(ErrorCode.E_ASSET_KIND, "替换资产必须同类型")
    if old.id == new.id:
        raise ApiError(ErrorCode.E_VALIDATION, "新旧资产相同")
    if old.scope == "global" and new.scope != "global":
        raise ApiError(ErrorCode.E_ASSET_KIND, "全局资产只能替换为全局资产")
    if old.scope == "project" and new.scope == "project" and new.project_id != old.project_id:
        raise ApiError(ErrorCode.E_ASSET_KIND, "项目资产不能替换为其他项目资产")
    usages = assets_svc.scan_usages(
        session, sha=old.sha256,
        project_ids=[old.project_id] if old.scope == "project" else None).get(old.sha256, [])
    target_ids = sorted({u["projectId"] for u in usages if u.get("projectId")}) if old.scope == "global" else \
        ([old.project_id] if old.project_id else [])
    changed_projects = []
    before_docs: list[tuple[int, dict, int]] = []  # (pid, 保存前内容, 保存前版本)
    try:
        for pid in target_ids:
            doc = session.exec(select(ProjectDoc).where(
                ProjectDoc.project_id == pid, ProjectDoc.kind == "timeline")).first()  # type: ignore[arg-type]
            if not doc:
                continue
            content = json.loads(json.dumps(doc.content_json or {}))
            scenes = assets_svc.replace_doc_refs(content, old.sha256, new.sha256)
            if not scenes:
                continue
            before_docs.append((pid, json.loads(json.dumps(doc.content_json or {})),
                                doc.version))
            saved, diff = docs_svc.save_doc(session, pid, "timeline", content, doc.version,
                                            "asset-replace")
            changed_projects.append({"projectId": pid, "version": saved.version,
                                     "scenes": scenes, "diff": diff[:50]})
    except Exception:
        # P1-09：多项目替换中途失败 → 倒序把已改项目回滚（base 用当前行版本）
        for pid, content_before, _version_before in reversed(before_docs):
            try:
                row = session.exec(select(ProjectDoc).where(
                    ProjectDoc.project_id == pid, ProjectDoc.kind == "timeline")).first()
                docs_svc.save_doc(session, pid, "timeline", content_before,
                                  row.version if row else 0, "asset-replace-rollback")
            except Exception:
                pass
        raise
    untouched = {}
    for u in usages:
        if u.get("source") in ("template", "run", "doc"):
            untouched[u["source"]] = untouched.get(u["source"], 0) + 1
    audit(session, "asset.replace", str(asset_id),
          after={"with": new.id, "projects": changed_projects, "untouched": untouched})
    return {"old": assets_svc.asset_dto(old, usages),
            "new": assets_svc.asset_dto(new, []),
            "projects": changed_projects,
            "untouched": untouched,
            "affectedScenes": sorted({s for p in changed_projects for s in p["scenes"]})}


# ---------- 音频工作台（FR-27） ----------

@router.get("/projects/{project_id}/audio")
async def project_audio(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    manifest = audio_svc.load_manifest(proj.root)
    lic = audio_svc.load_license(proj.root)
    ok, why = audio_svc.license_ok(lic)
    primary = audio_svc.primary_take(proj.root)
    return {"takes": manifest["takes"], "primary": primary,
            "scenePrimary": manifest.get("scenePrimary") or {},
            "alignment": audio_svc.load_alignment(proj.root),
            "license": lic, "licenseOk": ok, "licenseReason": why,
            "mix": audio_svc.load_mix(proj.root),
            "markers": audio_svc.load_markers(proj.root),
            "placeholder": audio_svc.load_placeholder(proj.root)}


@router.post("/projects/{project_id}/audio/upload")
async def project_audio_upload(project_id: int, payload: dict,
                               session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    take = await asyncio.to_thread(
        audio_svc.import_take, proj.root, str(payload.get("filename") or "take.wav"),
        str(payload.get("data") or ""), str(payload.get("kind") or "voice"),
        str(payload.get("sceneId") or ""), str(payload.get("name") or ""))
    audit(session, "audio.upload", proj.root, after={"take": take["id"], "kind": take["kind"]})
    return {"take": take, "primary": audio_svc.primary_take(proj.root)}


@router.post("/projects/{project_id}/audio/primary")
async def project_audio_primary(project_id: int, payload: dict,
                                session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    take = audio_svc.set_primary(proj.root, str(payload.get("takeId") or ""))
    audit(session, "audio.primary", proj.root, after={"take": take["id"]})
    return {"primary": take}


@router.post("/projects/{project_id}/audio/scene-primary")
async def audio_scene_primary(project_id: int, payload: dict,
                              session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    scene_id = str(payload.get("sceneId") or "")
    take_id = str(payload.get("takeId") or "")
    if not scene_id:
        raise ApiError(ErrorCode.E_VALIDATION, "sceneId 必填")
    result = (audio_svc.clear_scene_primary(proj.root, scene_id) if not take_id
              else audio_svc.set_scene_primary(proj.root, scene_id, take_id))
    audit(session, "audio.scene_primary", proj.root, after=result)
    return result


@router.post("/projects/{project_id}/audio/takes/{take_id}/process")
async def audio_process_take(project_id: int, take_id: str, payload: dict | None = None,
                             session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    take = await asyncio.to_thread(audio_svc.process_take, proj.root, take_id, payload or {})
    audit(session, "audio.process", proj.root, after={"take": take_id,
          "processing": take.get("processing")})
    return {"take": take}


@router.get("/projects/{project_id}/audio/takes/{take_id}/file")
async def audio_take_file(project_id: int, take_id: str, processed: bool = False,
                          session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    p = audio_svc.take_path(proj.root, take_id, processed=processed)
    return file_response(p)


@router.post("/projects/{project_id}/audio/concat")
async def audio_concat_preview(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    tl = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    profile = docs_svc.doc_payload(session, project_id, proj.root, "profile")["content"]
    out = Path(proj.root) / "card" / "audio" / "preview_concat.wav"
    result = await asyncio.to_thread(
        audio_svc.concat_voice, proj.root, tl.get("scenes") or [],
        float(profile.get("duration") or 0), out)
    if not result:
        raise ApiError(ErrorCode.E_VALIDATION, "还没有场景 Take；先在 Take 上点“设为场景”", status=409)
    return {**result, "url": f"/api/projects/{project_id}/audio/concat/file"}


@router.get("/projects/{project_id}/audio/concat/file")
async def audio_concat_file(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    p = Path(proj.root) / "card" / "audio" / "preview_concat.wav"
    if not p.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "拼接预览尚未生成", status=404)
    return file_response(p, download_name="concat-preview.wav")


@router.get("/projects/{project_id}/audio/onset")
async def audio_onset(project_id: int, takeId: str, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    onsets = await asyncio.to_thread(audio_svc.detect_onsets, proj.root, takeId)
    return {"takeId": takeId, "onsets": onsets, "count": len(onsets)}


@router.get("/projects/{project_id}/audio/markers")
async def audio_markers_get(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return audio_svc.load_markers(proj.root)


@router.post("/projects/{project_id}/audio/markers")
async def audio_markers_save(project_id: int, payload: dict,
                             session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    data = audio_svc.save_markers(proj.root, payload.get("markers") or [],
                                  payload.get("onsets") or [])
    audit(session, "audio.markers", proj.root, after={"markers": len(data["markers"])})
    return data


@router.get("/projects/{project_id}/audio/mix")
async def audio_mix_get(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return audio_svc.load_mix(proj.root)


@router.post("/projects/{project_id}/audio/mix")
async def audio_mix_save(project_id: int, payload: AudioMixSaveIn,
                         session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    data = audio_svc.save_mix(proj.root, payload.model_dump(exclude_none=True))
    audit(session, "audio.mix", proj.root, after=data)
    return data


@router.get("/projects/{project_id}/audio/waveform")
async def project_audio_waveform(project_id: int, takeId: str, w: int = 2000,
                                 session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    return await asyncio.to_thread(audio_svc.waveform, proj.root, takeId, w)


@router.get("/projects/{project_id}/audio/alignment")
async def project_audio_alignment(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return audio_svc.load_alignment(proj.root)


@router.post("/projects/{project_id}/audio/alignment")
async def project_audio_alignment_save(project_id: int, payload: AudioAlignmentSaveIn,
                                       session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    data = audio_svc.save_alignment(proj.root, payload.segments, payload.author)
    audit(session, "audio.alignment", proj.root, after={"segments": len(data["segments"])})
    return data


@router.get("/projects/{project_id}/audio/license")
async def project_audio_license(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    lic = audio_svc.load_license(proj.root)
    ok, why = audio_svc.license_ok(lic)
    return {"license": lic, "ok": ok, "reason": why}


@router.post("/projects/{project_id}/audio/license")
async def project_audio_license_save(project_id: int, payload: AudioLicenseSaveIn,
                                     session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    _require_workspace_root(Path(proj.root).resolve())
    lic = audio_svc.save_license(proj.root, payload.model_dump())
    audit(session, "audio.license", proj.root, after=lic)
    return {"license": lic, "ok": True, "reason": ""}


# ---------- FR-33 审片批注 ----------

def _review_videos(session: Session, project_id: int) -> list[dict]:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project_id)).first()  # type: ignore[arg-type,union-attr]
    if not wf:
        return []
    runs = session.exec(select(Run).where(Run.workflow_id == wf.id)
                        .order_by(Run.id.desc())).all()  # type: ignore[arg-type]
    labels = {"E05": "review 代理", "F04": "final 成片", "G07": "master"}
    out, seen = [], set()
    for run in runs[:8]:
        rows = session.exec(select(Artifact).where(
            Artifact.run_id == run.id, Artifact.type == "MP4")).all()  # type: ignore[arg-type]
        for a in rows:
            if a.node_id not in labels or not Path(a.path).exists() or a.id in seen:
                continue
            seen.add(a.id)
            out.append({"id": a.id, "node": a.node_id, "label": labels[a.node_id],
                        "runId": run.id, "sha256": a.sha256,
                        "bytes": Path(a.path).stat().st_size,
                        "url": f"/api/artifacts/{a.id}/file"})
    return out


def _review_pick_video(session: Session, project_id: int, video_id: int | None) -> tuple[Artifact, str]:
    rows = _review_videos(session, project_id)
    if video_id:
        row = next((x for x in rows if x["id"] == video_id), None)
        if row:
            return session.get(Artifact, video_id), row["url"]  # type: ignore[return-value]
        raise ApiError(ErrorCode.E_NOT_FOUND, "审片视频不属于该项目", status=404)
    preferred = next((x for x in rows if x["node"] == "E05"), None) or \
        next((x for x in rows if x["node"] == "F04"), None) or \
        next((x for x in rows if x["node"] == "G07"), None)
    if not preferred:
        raise ApiError(ErrorCode.E_VALIDATION, "项目还没有可审的 MP4（先跑 E05/F04）", status=409)
    return session.get(Artifact, preferred["id"]), preferred["url"]  # type: ignore[return-value]


@router.get("/projects/{project_id}/review")
async def project_review(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    data = review_svc.load(proj.root)
    return {**data, "summary": review_svc.summary(proj.root),
            "videos": _review_videos(session, project_id)}


@router.post("/projects/{project_id}/review/comments")
async def review_comment_add(project_id: int, payload: dict,
                             session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    comment = review_svc.add(proj.root, payload)
    audit(session, "review.comment", f"{proj.root}:{comment['id']}",
          after={"frame": comment["frame"], "scene": comment["sceneId"]})
    return comment


@router.patch("/projects/{project_id}/review/comments/{comment_id}")
async def review_comment_update(project_id: int, comment_id: str, payload: dict,
                                session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    comment = review_svc.update(proj.root, comment_id, payload)
    audit(session, "review.update", f"{proj.root}:{comment_id}",
          after={"status": comment.get("status")})
    return comment


@router.post("/projects/{project_id}/review/decisions")
async def review_decide(project_id: int, payload: dict,
                        session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    decisions = review_svc.decide(proj.root, payload)
    audit(session, "review.decision", proj.root,
          after={"scene": payload.get("sceneId"), "decision": payload.get("decision")})
    return decisions


@router.get("/projects/{project_id}/review/videos")
async def review_videos(project_id: int, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    return {"items": _review_videos(session, project_id)}


@router.get("/projects/{project_id}/review/export")
async def review_export(project_id: int, format: str = "json",
                        session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    if format == "csv":
        text = review_svc.export_csv(proj.root)
        return Response(content=text, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="review.csv"'})
    data = review_svc.load(proj.root)
    return JSONResponse(content=data, headers={
        "Content-Disposition": 'attachment; filename="review.json"'})


@router.post("/projects/{project_id}/review/import")
async def review_import(project_id: int, payload: dict,
                        session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    result = review_svc.import_json(proj.root, payload)
    audit(session, "review.import", proj.root, after=result)
    return result


@router.post("/projects/{project_id}/review/package")
async def review_package(project_id: int, payload: dict | None = None,
                         session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    payload = payload or {}
    artifact, _url = _review_pick_video(session, project_id,
                                        int(payload["videoId"]) if payload.get("videoId") else None)
    result = review_svc.package(proj.root, Path(artifact.path), proj.name)
    audit(session, "review.package", proj.root, after=result)
    return {**result, "download": f"/api/projects/{project_id}/review/package"}


@router.get("/projects/{project_id}/review/package")
async def review_package_file(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    p = Path(proj.root) / "review" / "review-package.zip"
    if not p.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "审片包尚未生成", status=404)
    return file_response(p, download_name=f"{proj.name}-review-package.zip")


# ---------- 静帧查看记录（D03 前置） ----------

@router.post("/projects/{project_id}/stills/viewed")
async def stills_viewed(project_id: int, payload: dict, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    entry = {k: payload[k] for k in ("scene", "sceneId", "time", "t", "region", "zoom", "at")
             if k in payload}
    if "sceneId" in entry and "scene" not in entry:
        entry["scene"] = entry.pop("sceneId")
    if "t" in entry and "time" not in entry:
        entry["time"] = entry.pop("t")
    vp = Path(proj.root) / "card" / "viewed.json"
    data = json.loads(vp.read_text()) if vp.exists() else {"regions": []}
    data.setdefault("regions", []).append(entry)
    write_atomic(vp, json.dumps(data, ensure_ascii=False))
    audit(session, "stills.viewed", proj.root, after=entry)
    run = session.exec(select(Run).where(Run.workflow_id.in_(
        select(Workflow.id).where(Workflow.project_id == project_id))).order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]
    viewed, missing = [], []
    if run:
        _entries, viewed, missing = _review_viewed(session, run, proj.root)
    return {"regions": len(data["regions"]), "scenes": viewed, "missing": missing}


@router.get("/projects/{project_id}/stills/viewed")
async def stills_viewed_get(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    run = session.exec(select(Run).where(Run.workflow_id.in_(
        select(Workflow.id).where(Workflow.project_id == project_id))).order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]
    if not run:
        return {"entries": [], "scenes": [], "missing": []}
    entries, viewed, missing = _review_viewed(session, run, proj.root)
    return {"entries": entries, "scenes": viewed, "missing": missing}


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
async def task_put(project_id: int, payload: TaskPutIn,
                   session: Session = Depends(get_session)):
    """保存任务卡（仅 imported 项目可写）。新项目请通过文档 API 编辑。"""
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    wfs = session.exec(select(Workflow).where(Workflow.project_id == project_id)).all()
    imported = any((((w.graph_json or {}).get("meta") or {}).get("imported")) for w in wfs)
    if not imported:
        raise ApiError(ErrorCode.E_DOC_READONLY,
                       "新项目的 card/task.json 是只读快照；请编辑 script/timeline 文档", status=409)
    task = payload.task or {}
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
    write_atomic(tp, json.dumps(task, ensure_ascii=False, indent=1))
    audit(session, "task.save", proj.root, after={"phase": phase, "scenes": len(task.get("scenes", []))})
    return {"ok": True, "path": str(tp)}


# ---------- 文档模型（FR-25） ----------

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


def _doc_impact(kind: str) -> dict:
    from ..engine.edges import N, data_descendants
    source = {"script": "A01", "timeline": "B02", "profile": "B04"}.get(kind)
    nodes = sorted(data_descendants(source)) if source else []
    return {"source": source, "nodes": nodes,
            "gates": [n for n in nodes if N[n]["gate"] == "human"]}


@router.get("/projects/{project_id}/docs")
async def project_docs_list(project_id: int, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    return {"items": [docs_svc.doc_payload(session, project_id, proj.root, kind)
                      for kind in docs_svc.DOC_KINDS]}


@router.get("/projects/{project_id}/docs/{kind}")
async def project_doc_get(project_id: int, kind: str, session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    if kind not in docs_svc.DOC_KINDS:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知文档类型：{kind}")
    return docs_svc.doc_payload(session, project_id, proj.root, kind)


@router.put("/projects/{project_id}/docs/{kind}")
async def project_doc_put(project_id: int, kind: str, payload: DocSaveIn,
                          session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    doc, diff = docs_svc.save_doc(session, project_id, kind, payload.content,
                                  payload.base_version, payload.author)
    audit(session, "doc.save", f"{project_id}:{kind}",
          after={"version": doc.version, "diff": diff[:50]})
    return {**docs_svc.doc_payload(session, project_id, proj.root, kind),
            "diff": diff, "impact": _doc_impact(kind)}


@router.get("/projects/{project_id}/docs/{kind}/versions")
async def project_doc_versions(project_id: int, kind: str, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    if kind not in docs_svc.DOC_KINDS:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知文档类型：{kind}")
    doc = docs_svc.get_doc(session, project_id, kind)
    if doc is None:
        return {"kind": kind, "current_version": 0, "items": [], "truncated": False}
    items = docs_svc.list_versions(session, doc)
    # 版本链有上限（保留 v1 + 最新 99 条）；被裁掉的中间历史必须可见，别假装链完整
    return {"kind": kind, "current_version": doc.version, "items": items,
            "truncated": len(items) < doc.version, "keptFirst": docs_svc.FIRST_REVISION_KEPT}


@router.post("/projects/{project_id}/docs/{kind}/restore")
async def project_doc_restore(project_id: int, kind: str, payload: DocRestoreIn,
                              session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    doc, diff = docs_svc.restore_doc(session, project_id, kind, payload.version, payload.author)
    audit(session, "doc.restore", f"{project_id}:{kind}",
          after={"version": doc.version, "restored_from": payload.version})
    return {**docs_svc.doc_payload(session, project_id, proj.root, kind),
            "diff": diff, "impact": _doc_impact(kind)}


@router.post("/projects/{project_id}/timeline/ops")
async def project_timeline_ops(project_id: int, payload: TimelineOpIn,
                               session: Session = Depends(get_session)):
    """FR-32：时间轴操作（乐观锁 + 读时/相机校验）。"""
    proj = _project_or_404(session, project_id)
    body = payload.model_dump()
    current = docs_svc.doc_payload(session, project_id, proj.root, "timeline")
    base = int(body["baseVersion"] if body.get("baseVersion") is not None
               else current["version"])
    script = docs_svc.doc_payload(session, project_id, proj.root, "script")["content"]
    op = body["op"]
    if op in ("add_image", "add_sfx", "set_font"):
        sha = str(body.get("assetSha") or "")
        expected = {"add_image": "image", "add_sfx": "audio", "set_font": "font"}[op]
        asset = session.exec(select(Asset).where(Asset.sha256 == sha)).first() if sha else None
        if asset and asset.kind != expected:
            raise ApiError(ErrorCode.E_ASSET_KIND,
                           f"资产 {asset.id} 是 {asset.kind}，不能用于 {expected}", status=409)
    try:
        content, meta = tl_svc.apply(current["content"], script, op, body)
    except tl_svc.TimelineOpError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"{e.code}: {e.message}",
                       status=e.status, details=e.details)
    except (TypeError, ValueError) as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"E_TIMELINE_OP: {e}", status=400)
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", content, base,
                                  str(body.get("author") or "timeline"))
    audit(session, f"timeline.{op}", f"{project_id}:timeline",
          after={"version": doc.version, "scene": body.get("sceneId")})
    return {**docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "op": op, "diff": diff, "impact": _doc_impact("timeline"),
            "validation": meta["validation"]}


def _take_runs(session: Session, project_id: int) -> list[Run]:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project_id)).first()  # type: ignore[arg-type,union-attr]
    if not wf:
        return []
    return session.exec(select(Run).where(Run.workflow_id == wf.id)
                        .order_by(Run.id.desc())).all()  # type: ignore[arg-type]


def _take_run(session: Session, project_id: int, run_id: int) -> tuple[Project, Run]:
    proj = _project_or_404(session, project_id)
    run = session.get(Run, run_id)
    if not run or run.workflow_id not in {w.id for w in session.exec(
            select(Workflow).where(Workflow.project_id == project_id)).all()}:
        raise ApiError(ErrorCode.E_NOT_FOUND, "Take/Run 不属于该项目", status=404)
    return proj, run


def _take_still(session: Session, run_id: int) -> dict | None:
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == run_id, Artifact.node_id == "D02", Artifact.type == "PNG")).all()  # type: ignore[arg-type]
    for a in rows:
        if (a.meta_json or {}).get("profile") == "review" and Path(a.path).exists():
            return {"artifact": a.id, "url": f"/api/artifacts/{a.id}/file"}
    return None


def _take_source_docs(session: Session, proj: Project, run: Run) -> tuple[dict, dict, dict]:
    """Run 快照 docs → (script, timeline, profile)；imported 回退 task/copy。"""
    root = Path(proj.root)
    docs = root / "runs" / str(run.id) / "docs"
    def _read(name: str) -> dict:
        p = docs / name
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    snapshot = _read("snapshot.json")
    script = _read("script.doc.json")
    timeline = _read("timeline.doc.json")
    task = _read("task.json")
    if not task:
        try:
            task = json.loads((root / "card" / "task.json").read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            task = {}
    if not script:
        copy = ""
        try:
            copy = (root / "card" / "copy.txt").read_text(encoding="utf-8")
        except OSError:
            pass
        if not copy and task.get("scenes"):
            copy = "".join(str(sc.get("meaning") or "") for sc in task["scenes"])
        script = docs_svc.build_script_doc(copy) if copy else {}
    if not timeline and task.get("scenes"):
        fps = norm_fps(task.get("fps") or 24)  # P1-12
        scenes = task["scenes"]
        timeline = {
            "schema": docs_svc.SCHEMAS["timeline"], "fps": fps,
            "duration": float((task.get("film") or {}).get("duration") or
                              (scenes[-1].get("end") if scenes else 0)),
            "frames": int((task.get("film") or {}).get("frames") or 0),
            "scenes": scenes, "events": task.get("events") or [], "tracks": [],
        }
    profile = snapshot.get("profile") or {}
    if not profile:
        try:
            profile = json.loads((root / "project.profile.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            profile = {}
    return script, timeline, profile


@router.get("/projects/{project_id}/takes")
async def project_takes(project_id: int, includeHidden: bool = False,
                        session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    videos = _review_videos(session, project_id)
    out = []
    for run in _take_runs(session, project_id):
        meta = takes_svc.item(proj.root, run.id or 0)
        if meta["hidden"] and not includeHidden:
            continue
        out.append({**meta, "status": run.status,
                    "createdAt": str(run.started_at or run.finished_at or ""),
                    "parentRunId": run.parent_run_id,
                    "videos": [v for v in videos if v["runId"] == run.id],
                    "still": _take_still(session, run.id or 0)})
    out.sort(key=lambda x: (x["score"] is not None, x["score"] or 0, x["runId"]), reverse=True)
    return {"currentRunId": takes_svc.current_run(proj.root), "items": out}


@router.patch("/projects/{project_id}/takes/{run_id}")
async def project_take_update(project_id: int, run_id: int, payload: dict,
                              session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    take = takes_svc.update(proj.root, run_id, payload)
    audit(session, "take.update", f"{project_id}:run:{run_id}", after=take)
    return take


@router.post("/projects/{project_id}/takes/{run_id}/promote")
async def project_take_promote(project_id: int, run_id: int,
                               session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    result = takes_svc.promote(proj.root, run_id)
    audit(session, "take.promote", f"{project_id}:run:{run_id}", after=result)
    return result


@router.delete("/projects/{project_id}/takes/{run_id}")
async def project_take_delete(project_id: int, run_id: int,
                              session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    take = takes_svc.delete(proj.root, run_id)
    audit(session, "take.delete", f"{project_id}:run:{run_id}", after=take)
    return take


@router.post("/projects/{project_id}/takes/{run_id}/branch")
async def project_take_branch(project_id: int, run_id: int, payload: dict | None = None,
                              session: Session = Depends(get_session)):
    proj, source = _take_run(session, project_id, run_id)
    script, timeline, profile = _take_source_docs(session, proj, source)
    if not timeline.get("scenes"):
        raise ApiError(ErrorCode.E_VALIDATION, "该 Take 没有可复制的 timeline 快照", status=409)
    author = payload.get("author", "take-branch") if payload else "take-branch"
    saved_docs: list[tuple[str, dict, int]] = []  # (kind, 保存前内容, 保存前版本)
    try:
        if script.get("text"):
            current = docs_svc.get_doc(session, project_id, "script")
            if current is not None:
                saved_docs.append(("script", deepcopy(current.content_json or {}),
                                   current.version))
            docs_svc.save_doc(session, project_id, "script", script,
                              current.version if current else 0, author)
        current_tl = docs_svc.get_doc(session, project_id, "timeline")
        tl_svc.normalize(timeline, script)
        if current_tl is not None:
            saved_docs.append(("timeline", deepcopy(current_tl.content_json or {}),
                               current_tl.version))
        docs_svc.save_doc(session, project_id, "timeline", timeline,
                          current_tl.version if current_tl else 0, author)
        if profile:
            current_pf = docs_svc.get_doc(session, project_id, "profile")
            if current_pf is not None:
                saved_docs.append(("profile", deepcopy(current_pf.content_json or {}),
                                   current_pf.version))
            docs_svc.save_doc(session, project_id, "profile",
                              {"schema": docs_svc.SCHEMAS["profile"], **profile},
                              current_pf.version if current_pf else 0, author)
        new_run = Run(workflow_id=source.workflow_id, parent_run_id=source.id)
        session.add(new_run)
        session.commit()
        session.refresh(new_run)
    except Exception:
        # P1-09：Run 没建成就回滚已保存的文档（倒序补偿），不留半分支。
        # base_version 用当前行版本（补偿时行号已被前推，用 before 版本会 E_DOC_CONFLICT）。
        for kind, content_before, _version_before in reversed(saved_docs):
            try:
                row = docs_svc.get_doc(session, project_id, kind)
                docs_svc.save_doc(session, project_id, kind, content_before,
                                  row.version if row else 0, "take-branch-rollback")
            except Exception:
                pass
        raise
    audit(session, "take.branch", f"{project_id}:run:{run_id}",
          after={"newRunId": new_run.id, "parentRunId": source.id})
    return {"runId": new_run.id, "parentRunId": source.id}


@router.post("/projects/{project_id}/takes/{run_id}/adopt-scene")
async def project_take_adopt_scene(project_id: int, run_id: int, payload: dict,
                                   session: Session = Depends(get_session)):
    proj, source = _take_run(session, project_id, run_id)
    scene_id = str(payload.get("sceneId") or "")
    if not scene_id:
        raise ApiError(ErrorCode.E_VALIDATION, "sceneId 必填")
    source_script, source_timeline, _profile = _take_source_docs(session, proj, source)
    source_scene = next((s for s in source_timeline.get("scenes", []) if s.get("id") == scene_id), None)
    if not source_scene:
        raise ApiError(ErrorCode.E_NOT_FOUND, f"源 Take 没有场景 {scene_id}", status=404)
    from ..engine.scene.compiler import scene_text
    target = docs_svc.doc_payload(session, project_id, proj.root, "timeline")
    target_script = docs_svc.doc_payload(session, project_id, proj.root, "script")["content"]
    scene = next((s for s in target["content"].get("scenes", []) if s.get("id") == scene_id), None)
    if not scene:
        raise ApiError(ErrorCode.E_NOT_FOUND, f"当前项目没有场景 {scene_id}", status=404)
    text = scene_text(source_scene, source_script)
    if not text:
        raise ApiError(ErrorCode.E_VALIDATION, "源场景没有可采纳的文字", status=409)
    scene["text"] = text
    scene["source_span"] = []
    scene["meaning"] = source_scene.get("meaning") or scene.get("meaning") or ""
    scene["operation"] = source_scene.get("operation") or scene.get("operation") or ""
    for key in ("camera", "camera_keyframes", "camera_anchor"):
        if key in source_scene:
            scene[key] = source_scene[key]
    tl_svc.normalize(target["content"], target_script)
    validation = tl_svc.validate(target["content"], target_script)
    if not validation["ok"]:
        raise ApiError(ErrorCode.E_VALIDATION, validation["errors"][0]["message"],
                       status=409, details={"validation": validation})
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", target["content"],
                                  target["version"], "take-adopt")
    audit(session, "take.adopt_scene", f"{project_id}:run:{run_id}:{scene_id}",
          after={"version": doc.version})
    return {"sceneId": scene_id, "sourceRunId": run_id, "text": text,
            **docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "diff": diff, "validation": validation}


@router.post("/projects/{project_id}/docs/timeline/rebuild")
async def project_timeline_rebuild(project_id: int, payload: dict,
                                   session: Session = Depends(get_session)):
    proj = _project_or_404(session, project_id)
    script = docs_svc.get_doc(session, project_id, "script")
    script_content = script.content_json if script else docs_svc.default_doc(
        session, project_id, proj.root, "script")
    profile = docs_svc.get_doc(session, project_id, "profile")
    profile_content = profile.content_json if profile else docs_svc.default_doc(
        session, project_id, proj.root, "profile")
    content = docs_svc.build_timeline_doc(script_content, profile_content)
    current = docs_svc.get_doc(session, project_id, "timeline")
    base = int(payload.get("base_version", current.version if current else 0))
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", content, base,
                                  payload.get("author", "local"))
    audit(session, "doc.rebuild", f"{project_id}:timeline", after={"version": doc.version})
    return {**docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "diff": diff, "impact": _doc_impact("timeline")}


@router.get("/projects/{project_id}/docs/{kind}/diff")
async def project_doc_diff(project_id: int, kind: str, from_version: int, to_version: int,
                           session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    doc = docs_svc.get_doc(session, project_id, kind)
    if doc is None:
        raise ApiError(ErrorCode.E_NOT_FOUND, "文档不存在", status=404)
    return {"kind": kind, "from": from_version, "to": to_version,
            "diff": docs_svc.version_diff(session, doc, from_version, to_version)}


# ---------- jobs / audit / 事件 ----------

@router.get("/jobs")
async def jobs_list(status: str | None = None, kind: str | None = None,
                    limit: int = 200, session: Session = Depends(get_session)):
    return {"items": [table_dict(j) for j in jobs_svc.list_jobs(session, status, kind, limit)]}


@router.get("/queue")
async def queue_summary(session: Session = Depends(get_session)):
    return jobs_svc.queue_summary(session)


@router.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    if j.kind == "run" and j.run_id:
        re_mod.cancel_run(j.run_id)
    elif j.kind.startswith("preview_"):
        pj = preview_svc.find_by_db_job(job_id)
        if pj:
            preview_svc.cancel_job(pj.id)
        else:
            jobs_svc.finish_job(session, job_id, "canceled", error_code="E_PREVIEW_CANCELED")
    else:
        jobs_svc.cancel_requested(session, job_id)
    session.expire_all()
    return table_dict(session.get(Job, job_id))


@router.post("/jobs/{job_id}/retry")
async def job_retry(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    if j.kind != "run" or not j.run_id:
        raise ApiError(ErrorCode.E_CONFLICT, "只有 Run job 支持重试", status=409)
    if j.status not in ("failed", "canceled"):
        raise ApiError(ErrorCode.E_CONFLICT, f"job 状态 {j.status} 不可重试", status=409)
    result = await re_mod.resume_run(j.run_id)
    with Session(engine) as s2:
        latest = jobs_svc.latest_run_job(s2, j.run_id)
    return {"runId": j.run_id, "requeued": result["requeued"],
            "jobId": latest.id if latest else None}


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
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            unsubscribe(run_id, q)

    return EventSourceResponse(gen())


# ---------- 提升为当前 / 报告导出（M4 前置） ----------

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
    audit(session, "run.promote", f"run:{run_id}", after={"take": payload.takeName or ""})
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
