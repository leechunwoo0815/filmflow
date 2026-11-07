"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from ..atomicwrite import write_atomic
from ..config import settings
from ..db import get_session
from ..engine import edges
from ..engine.fpscalc import frames_for, norm_fps
from ..errors import ApiError, ErrorCode, not_found
from ..models import (
    Draft,
    Project,
    Run,
    Style,
    StylePick,
    Template,
    Workflow,
    WorkflowVersion,
    table_dict,
)
from ..services import assets as assets_svc
from ..services import audio as audio_svc
from ..services import onboarding as onboarding_svc
from ..services import project_docs as docs_svc
from ..services import style_index as idx_svc
from ..services import templates as tpl_svc
from ..services import timeline_ops as tl_svc
from . import deps
from .schemas import (
    DraftCreateIn,
    DraftPatchIn,
    ExampleCloneIn,
    FromTemplateIn,
    ProjectCreateIn,
    ProjectImportIn,
    SceneTemplateApplyIn,
    SceneTemplateSaveIn,
    SeriesCreateIn,
    TemplateSaveIn,
    TemplateUpgradeIn,
    TemplateVersionIn,
)

router = APIRouter(prefix="/api")


@router.get("/projects")
async def projects_list(session: Session = Depends(get_session)):
    return {"items": [table_dict(p) for p in session.exec(select(Project)).all()]}


@router.post("/projects")
async def projects_create(payload: ProjectCreateIn, session: Session = Depends(get_session)):
    rp = Path(payload.root.strip()).resolve()
    deps._require_creatable_project_root(rp)
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
    deps.audit(session, "project.create", str(rp), after={"id": p.id})
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
async def projects_import(payload: ProjectImportIn, session: Session = Depends(get_session)):
    """导入参考项目：读 task.json → workflow + run + 初始状态（T06）。"""
    root = payload.root.strip()
    rp = Path(root).resolve()
    deps._require_creatable_project_root(rp)
    task_p = rp / "card" / "task.json"
    if not task_p.exists():
        raise ApiError(ErrorCode.E_VALIDATION, f"缺少 card/task.json：{rp}")
    created = await projects_create(ProjectCreateIn(name=payload.name or rp.name,
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
    deps.audit(session, "project.import", str(rp), after=graph["meta"])
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
async def drafts_create(payload: DraftCreateIn, session: Session = Depends(get_session)):
    d = Draft(name=payload.name, step=payload.step, payload_json=payload.payload)
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
async def drafts_patch(draft_id: int, body: DraftPatchIn,
                       session: Session = Depends(get_session)):
    d = session.get(Draft, draft_id)
    if not d:
        raise not_found("draft")
    patch = body.model_dump(exclude_unset=True)
    if patch.get("step") is not None:
        d.step = patch["step"]
    if patch.get("payload") is not None:
        d.payload_json = {**(d.payload_json or {}), **patch["payload"]}
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
    deps.audit(session, "draft.materialize", f"draft:{d.id}", after={"run_id": run.id, "primary": primary})
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
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
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
    deps.audit(session, "template.delete", template_id)
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
            _log.debug("swallowed exception in _materialize_saved_template (except Exception:)", exc_info=True)
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
async def project_save_template(project_id: int, payload: TemplateSaveIn,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    name = (payload.name or f"{proj.name} 模板").strip()[:80]
    if not name:
        raise ApiError(ErrorCode.E_VALIDATION, "模板名称不能为空")
    content = _project_template_content(session, project_id, payload.copy_text,
                                        payload.description)
    t = Template(kind="project", name=name, description=payload.description,
                 content_json=content)
    session.add(t)
    session.commit()
    session.refresh(t)
    deps.audit(session, "template.save", f"project:{project_id}", after={"template": t.id})
    return {"template": tpl_svc.saved_dto(t, with_content=True)}


@router.post("/templates/{template_id}/version")
async def template_new_version(template_id: str, payload: TemplateVersionIn,
                               session: Session = Depends(get_session)):
    if not template_id.startswith("saved:"):
        raise ApiError(ErrorCode.E_VALIDATION, "内置模板不能改版本")
    _, _content, saved, _ = _resolve_template(session, template_id)
    if not saved or saved.kind != "project":
        raise ApiError(ErrorCode.E_VALIDATION, "只有项目模板可保存新版本")
    project_id = payload.projectId
    content = _project_template_content(
        session, project_id, payload.copy_text,
        payload.description if payload.description is not None else saved.description)
    saved.content_json = content
    flag_modified(saved, "content_json")
    saved.version += 1
    saved.updated_at = datetime.now(UTC)
    if payload.name:
        saved.name = payload.name[:80]
    session.add(saved)
    session.commit()
    session.refresh(saved)
    deps.audit(session, "template.version", template_id,
          after={"version": saved.version, "project": project_id})
    return {"template": tpl_svc.saved_dto(saved, with_content=True)}


@router.post("/projects/{project_id}/scenes/{scene_id}/save-template")
async def project_save_scene_template(project_id: int, scene_id: str, payload: SceneTemplateSaveIn,
                                      session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    timeline = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    scene = next((s for s in timeline.get("scenes") or [] if s.get("id") == scene_id), None)
    if not scene:
        raise not_found("场景")
    name = (payload.name or f"{scene_id} 场景模板").strip()[:80]
    content = tpl_svc.scene_template_content(
        scene, keep_text=payload.keepText,
        description=payload.description, source_project_id=project_id)
    t = Template(kind="scene", name=name, description=payload.description,
                 content_json=content)
    session.add(t)
    session.commit()
    session.refresh(t)
    deps.audit(session, "template.scene.save", f"project:{project_id}:{scene_id}",
          after={"template": t.id})
    return {"template": tpl_svc.saved_dto(t, with_content=True)}


@router.post("/projects/{project_id}/timeline/scene-template")
async def project_apply_scene_template(project_id: int, payload: SceneTemplateApplyIn,
                                       session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    kind, content, saved, builtin = _resolve_template(session, payload.templateId)
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
    index = payload.index
    if payload.afterSceneId:
        ids = [s.get("id") for s in current["content"].get("scenes") or []]
        try:
            index = ids.index(payload.afterSceneId) + 1
        except ValueError:
            index = None
    try:
        new_content, meta = tl_svc.apply(current["content"], script, "add_scene",
                                         {"scene": scene, "index": index})
    except tl_svc.TimelineOpError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"{e.code}: {e.message}",
                       status=e.status, details=e.details)
    base = payload.baseVersion if payload.baseVersion is not None else current["version"]
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", new_content, base,
                                  payload.author)
    before = {s.get("id") for s in current["content"].get("scenes") or []}
    inserted = next((s.get("id") for s in new_content.get("scenes") or [] if s.get("id") not in before), "")
    deps.audit(session, "template.scene.apply", f"project:{project_id}",
          after={"template": payload.templateId, "sceneId": inserted})
    return {**docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "sceneId": inserted, "diff": diff, "validation": meta["validation"],
            "template": (f"saved:{saved.id}" if saved else payload.templateId)}


@router.get("/projects/{project_id}/template-lock")
async def project_template_lock(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return {"lock": tpl_svc.read_lock(proj.root)}


@router.get("/projects/{project_id}/template-diff")
async def project_template_diff(project_id: int, templateId: str,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    kind, content, saved, _ = _resolve_template(session, templateId)
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "升级只支持已保存的项目模板")
    profile = docs_svc.doc_payload(session, project_id, proj.root, "profile")["content"]
    timeline = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    return {"template": tpl_svc.saved_dto(saved), "lock": tpl_svc.read_lock(proj.root),
            "diff": tpl_svc.template_diff(profile, timeline, content)}


@router.post("/projects/{project_id}/template-upgrade")
async def project_template_upgrade(project_id: int, payload: TemplateUpgradeIn,
                                   session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    kind, content, saved, _ = _resolve_template(session, payload.templateId)
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "升级只支持已保存的项目模板")
    profile_doc = docs_svc.doc_payload(session, project_id, proj.root, "profile")
    timeline_doc = docs_svc.doc_payload(session, project_id, proj.root, "timeline")
    diff = tpl_svc.template_diff(profile_doc["content"], timeline_doc["content"], content)
    if not payload.confirm:
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
    deps.audit(session, "template.upgrade", f"project:{project_id}",
          after={"template": saved.id, "diff": diff})
    return {"applied": True, "diff": diff, "lock": lock}


@router.post("/series/from-template")
async def series_from_template(payload: SeriesCreateIn, session: Session = Depends(get_session)):
    template_id = payload.templateId
    kind, content, saved, _ = _resolve_template(session, template_id)
    if kind != "project" or not saved:
        raise ApiError(ErrorCode.E_VALIDATION, "系列只支持已保存的项目模板")
    items = payload.items
    if not isinstance(items, list) or not items:
        raise ApiError(ErrorCode.E_VALIDATION, "items 不能为空")
    if len(items) > 5:
        raise ApiError(ErrorCode.E_VALIDATION, "v1 系列最多 5 项；批量 CSV/队列属 R4 FR-46")
    prefix = payload.name or saved.name or "系列"
    results = []
    created: list[int] = []
    for i, item in enumerate(items):
        item = item if isinstance(item, dict) else {"copy": str(item)}
        vars = item.get("variables") or item.get("vars") or item
        name = str(item.get("name") or f"{prefix} {i + 1:02d}")
        try:
            r = await _materialize_saved_template(
                session, saved, vars if isinstance(vars, dict) else {}, name,
                item.get("copy"))
            created.append(int(r["project"]["id"]))
            results.append({"index": i, "ok": True, "name": name,
                            "project": r["project"], "run_id": r["run_id"],
                            "missingVariables": r.get("missingVariables")})
        except Exception as e:
            session.rollback()
            try:
                session.refresh(saved)
            except Exception:
                _log.debug("swallowed exception in series_from_template (except Exception:)", exc_info=True)
            results.append({"index": i, "ok": False, "name": name, "error": str(e)[:300]})
    # P2-20：系列要求"整批成立"。半途失败时把本批已建的项目回滚（取消在飞 Run 后
    # 级联删除），否则每次失败都留一批孤儿项目。回滚明细进响应，可审计。
    rolled_back: list[dict] = []
    if any(not r["ok"] for r in results) and created:
        from ..engine import runengine
        from ..services.project_cleanup import delete_project
        # 逐个取消该项目名下未终态 Run，再级联删除
        for pid in created:
            try:
                for rid in _run_ids_of_project(session, pid):
                    try:
                        runengine.cancel_run(rid)
                    except Exception:
                        _log.debug("series rollback cancel run=%s failed", rid, exc_info=True)
                delete_project(session, pid, remove_dir=True, force=True)
                rolled_back.append({"projectId": pid})
            except Exception as e:
                rolled_back.append({"projectId": pid, "error": str(e)[:200]})
                _log.warning("series rollback project=%s failed: %s", pid, e)
        # 失败项保留原样（带 error），成功项标记 rolledBack——failed/created 仍如实统计
        results = [{**r, "rolledBack": True} if r["ok"] else r for r in results]
    return {"template": f"saved:{saved.id}", "items": results,
            "created": sum(1 for r in results if r.get("ok") and not r.get("rolledBack")),
            "failed": sum(1 for r in results if not r.get("ok")),
            "rolledBack": rolled_back,
            "note": "v1 同步创建；整批成立，半途失败自动回滚已建项目；CSV 批量/队列属 R4 FR-46"}


def _run_ids_of_project(session: Session, project_id: int) -> list[int]:
    """项目名下所有 Run 的 id（系列回滚用）。"""
    wfs = session.exec(select(Workflow).where(Workflow.project_id == project_id)).all()
    ids = [w.id for w in wfs]
    return [r.id for r in session.exec(select(Run)).all() if r.workflow_id in ids]


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
async def project_from_template(payload: FromTemplateIn, session: Session = Depends(get_session)):
    template_id = payload.templateId
    if template_id.startswith("saved:"):
        kind, _content, saved, _ = _resolve_template(session, template_id)
        if kind != "project" or not saved:
            raise ApiError(ErrorCode.E_VALIDATION, "不是项目模板")
        return await _materialize_saved_template(
            session, saved, payload.variables,
            payload.name or saved.name, payload.copy_text)
    tpl = next((t for t in FIRST_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise not_found("模板")
    return await _materialize_first(
        session, name=payload.name or f"第一条片 · {tpl['title']}",
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
async def example_clone(example_id: str, payload: ExampleCloneIn | None = None,
                        session: Session = Depends(get_session)):
    item = onboarding_svc.example(example_id)
    if not item:
        raise not_found("示例")
    name = (payload.name if payload else "") or f"我的示例 · {item['title']}"
    result = await _materialize_first(
        session, name=name,
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

