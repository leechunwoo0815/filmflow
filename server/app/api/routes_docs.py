"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import json
from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session, select

from ..atomicwrite import write_atomic
from ..db import get_session
from ..engine.fpscalc import norm_fps
from ..errors import ApiError, ErrorCode, not_found
from ..models import (
    Artifact,
    Asset,
    Project,
    Run,
    Workflow,
)
from ..security import file_response
from ..services import project_docs as docs_svc
from ..services import review_comments as review_svc
from ..services import takes as takes_svc
from ..services import timeline_ops as tl_svc
from . import deps
from .schemas import (
    AdoptSceneIn,
    DocRestoreIn,
    DocSaveIn,
    ReviewCommentAddIn,
    ReviewCommentPatchIn,
    ReviewDecideIn,
    ReviewImportIn,
    ReviewPackageIn,
    StillsViewedIn,
    TakeBranchIn,
    TakeUpdateIn,
    TaskPutIn,
    TimelineOpIn,
    TimelineRebuildIn,
)

router = APIRouter(prefix="/api")


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
    proj = deps._project_or_404(session, project_id)
    data = review_svc.load(proj.root)
    return {**data, "summary": review_svc.summary(proj.root),
            "videos": _review_videos(session, project_id)}


@router.post("/projects/{project_id}/review/comments")
async def review_comment_add(project_id: int, payload: ReviewCommentAddIn,
                             session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    comment = review_svc.add(proj.root, payload.model_dump())
    deps.audit(session, "review.comment", f"{proj.root}:{comment['id']}",
          after={"frame": comment["frame"], "scene": comment["sceneId"]})
    return comment


@router.patch("/projects/{project_id}/review/comments/{comment_id}")
async def review_comment_update(project_id: int, comment_id: str, payload: ReviewCommentPatchIn,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    comment = review_svc.update(proj.root, comment_id, payload.model_dump(exclude_unset=True))
    deps.audit(session, "review.update", f"{proj.root}:{comment_id}",
          after={"status": comment.get("status")})
    return comment


@router.post("/projects/{project_id}/review/decisions")
async def review_decide(project_id: int, payload: ReviewDecideIn,
                        session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    decisions = review_svc.decide(proj.root, payload.model_dump())
    deps.audit(session, "review.decision", proj.root,
          after={"scene": payload.sceneId, "decision": payload.decision})
    return decisions


@router.get("/projects/{project_id}/review/videos")
async def review_videos(project_id: int, session: Session = Depends(get_session)):
    deps._project_or_404(session, project_id)
    return {"items": _review_videos(session, project_id)}


@router.get("/projects/{project_id}/review/export")
async def review_export(project_id: int, format: str = "json",
                        session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    if format == "csv":
        text = review_svc.export_csv(proj.root)
        return Response(content=text, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="review.csv"'})
    data = review_svc.load(proj.root)
    return JSONResponse(content=data, headers={
        "Content-Disposition": 'attachment; filename="review.json"'})


@router.post("/projects/{project_id}/review/import")
async def review_import(project_id: int, payload: ReviewImportIn,
                        session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    result = review_svc.import_json(proj.root, payload.model_dump())
    deps.audit(session, "review.import", proj.root, after=result)
    return result


@router.post("/projects/{project_id}/review/package")
async def review_package(project_id: int, payload: ReviewPackageIn | None = None,
                         session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    artifact, _url = _review_pick_video(session, project_id,
                                        payload.videoId if payload else None)
    result = review_svc.package(proj.root, Path(artifact.path), proj.name)
    deps.audit(session, "review.package", proj.root, after=result)
    return {**result, "download": f"/api/projects/{project_id}/review/package"}


@router.get("/projects/{project_id}/review/package")
async def review_package_file(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    p = Path(proj.root) / "review" / "review-package.zip"
    if not p.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "审片包尚未生成", status=404)
    return file_response(p, download_name=f"{proj.name}-review-package.zip")


# ---------- 静帧查看记录（D03 前置） ----------


@router.post("/projects/{project_id}/stills/viewed")
async def stills_viewed(project_id: int, payload: StillsViewedIn,
                        session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise not_found("project")
    sent = payload.model_dump(exclude_unset=True)
    entry = {k: sent[k] for k in ("scene", "sceneId", "time", "t", "region", "zoom", "at")
             if k in sent}
    if "sceneId" in entry and "scene" not in entry:
        entry["scene"] = entry.pop("sceneId")
    if "t" in entry and "time" not in entry:
        entry["time"] = entry.pop("t")
    vp = Path(proj.root) / "card" / "viewed.json"
    data = json.loads(vp.read_text()) if vp.exists() else {"regions": []}
    data.setdefault("regions", []).append(entry)
    write_atomic(vp, json.dumps(data, ensure_ascii=False))
    deps.audit(session, "stills.viewed", proj.root, after=entry)
    run = session.exec(select(Run).where(Run.workflow_id.in_(
        select(Workflow.id).where(Workflow.project_id == project_id))).order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]
    viewed, missing = [], []
    if run:
        _entries, viewed, missing = deps._review_viewed(session, run, proj.root)
    return {"regions": len(data["regions"]), "scenes": viewed, "missing": missing}


@router.get("/projects/{project_id}/stills/viewed")
async def stills_viewed_get(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    run = session.exec(select(Run).where(Run.workflow_id.in_(
        select(Workflow.id).where(Workflow.project_id == project_id))).order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]
    if not run:
        return {"entries": [], "scenes": [], "missing": []}
    entries, viewed, missing = deps._review_viewed(session, run, proj.root)
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
    deps.audit(session, "task.save", proj.root, after={"phase": phase, "scenes": len(task.get("scenes", []))})
    return {"ok": True, "path": str(tp)}


# ---------- 文档模型（FR-25） ----------


def _doc_impact(kind: str) -> dict:
    from ..engine.edges import N, data_descendants
    source = {"script": "A01", "timeline": "B02", "profile": "B04"}.get(kind)
    nodes = sorted(data_descendants(source)) if source else []
    return {"source": source, "nodes": nodes,
            "gates": [n for n in nodes if N[n]["gate"] == "human"]}


@router.get("/projects/{project_id}/docs")
async def project_docs_list(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return {"items": [docs_svc.doc_payload(session, project_id, proj.root, kind)
                      for kind in docs_svc.DOC_KINDS]}


@router.get("/projects/{project_id}/docs/{kind}")
async def project_doc_get(project_id: int, kind: str, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    if kind not in docs_svc.DOC_KINDS:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知文档类型：{kind}")
    return docs_svc.doc_payload(session, project_id, proj.root, kind)


@router.put("/projects/{project_id}/docs/{kind}")
async def project_doc_put(project_id: int, kind: str, payload: DocSaveIn,
                          session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    doc, diff = docs_svc.save_doc(session, project_id, kind, payload.content,
                                  payload.base_version, payload.author)
    deps.audit(session, "doc.save", f"{project_id}:{kind}",
          after={"version": doc.version, "diff": diff[:50]})
    return {**docs_svc.doc_payload(session, project_id, proj.root, kind),
            "diff": diff, "impact": _doc_impact(kind)}


@router.get("/projects/{project_id}/docs/{kind}/versions")
async def project_doc_versions(project_id: int, kind: str, session: Session = Depends(get_session)):
    deps._project_or_404(session, project_id)
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
    proj = deps._project_or_404(session, project_id)
    doc, diff = docs_svc.restore_doc(session, project_id, kind, payload.version, payload.author)
    deps.audit(session, "doc.restore", f"{project_id}:{kind}",
          after={"version": doc.version, "restored_from": payload.version})
    return {**docs_svc.doc_payload(session, project_id, proj.root, kind),
            "diff": diff, "impact": _doc_impact(kind)}


@router.post("/projects/{project_id}/timeline/ops")
async def project_timeline_ops(project_id: int, payload: TimelineOpIn,
                               session: Session = Depends(get_session)):
    """FR-32：时间轴操作（乐观锁 + 读时/相机校验）。"""
    proj = deps._project_or_404(session, project_id)
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
    deps.audit(session, f"timeline.{op}", f"{project_id}:timeline",
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
    proj = deps._project_or_404(session, project_id)
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
    proj = deps._project_or_404(session, project_id)
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
async def project_take_update(project_id: int, run_id: int, payload: TakeUpdateIn,
                              session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    take = takes_svc.update(proj.root, run_id, payload.model_dump(exclude_unset=True))
    deps.audit(session, "take.update", f"{project_id}:run:{run_id}", after=take)
    return take


@router.post("/projects/{project_id}/takes/{run_id}/promote")
async def project_take_promote(project_id: int, run_id: int,
                               session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    result = takes_svc.promote(proj.root, run_id)
    deps.audit(session, "take.promote", f"{project_id}:run:{run_id}", after=result)
    return result


@router.delete("/projects/{project_id}/takes/{run_id}")
async def project_take_delete(project_id: int, run_id: int,
                              session: Session = Depends(get_session)):
    proj, _ = _take_run(session, project_id, run_id)
    take = takes_svc.delete(proj.root, run_id)
    deps.audit(session, "take.delete", f"{project_id}:run:{run_id}", after=take)
    return take


@router.post("/projects/{project_id}/takes/{run_id}/branch")
async def project_take_branch(project_id: int, run_id: int, payload: TakeBranchIn | None = None,
                              session: Session = Depends(get_session)):
    proj, source = _take_run(session, project_id, run_id)
    script, timeline, profile = _take_source_docs(session, proj, source)
    if not timeline.get("scenes"):
        raise ApiError(ErrorCode.E_VALIDATION, "该 Take 没有可复制的 timeline 快照", status=409)
    author = payload.author if payload else "take-branch"
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
                _log.debug("swallowed exception in project_take_branch (except Exception:)", exc_info=True)
        raise
    deps.audit(session, "take.branch", f"{project_id}:run:{run_id}",
          after={"newRunId": new_run.id, "parentRunId": source.id})
    return {"runId": new_run.id, "parentRunId": source.id}


@router.post("/projects/{project_id}/takes/{run_id}/adopt-scene")
async def project_take_adopt_scene(project_id: int, run_id: int, payload: AdoptSceneIn,
                                   session: Session = Depends(get_session)):
    proj, source = _take_run(session, project_id, run_id)
    scene_id = payload.sceneId
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
    deps.audit(session, "take.adopt_scene", f"{project_id}:run:{run_id}:{scene_id}",
          after={"version": doc.version})
    return {"sceneId": scene_id, "sourceRunId": run_id, "text": text,
            **docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "diff": diff, "validation": validation}


@router.post("/projects/{project_id}/docs/timeline/rebuild")
async def project_timeline_rebuild(project_id: int, payload: TimelineRebuildIn,
                                   session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    script = docs_svc.get_doc(session, project_id, "script")
    script_content = script.content_json if script else docs_svc.default_doc(
        session, project_id, proj.root, "script")
    profile = docs_svc.get_doc(session, project_id, "profile")
    profile_content = profile.content_json if profile else docs_svc.default_doc(
        session, project_id, proj.root, "profile")
    content = docs_svc.build_timeline_doc(script_content, profile_content)
    current = docs_svc.get_doc(session, project_id, "timeline")
    base = (payload.base_version if payload.base_version is not None
            else (current.version if current else 0))
    doc, diff = docs_svc.save_doc(session, project_id, "timeline", content, base,
                                  payload.author)
    deps.audit(session, "doc.rebuild", f"{project_id}:timeline", after={"version": doc.version})
    return {**docs_svc.doc_payload(session, project_id, proj.root, "timeline"),
            "diff": diff, "impact": _doc_impact("timeline")}


@router.get("/projects/{project_id}/docs/{kind}/diff")
async def project_doc_diff(project_id: int, kind: str, from_version: int, to_version: int,
                           session: Session = Depends(get_session)):
    deps._project_or_404(session, project_id)
    doc = docs_svc.get_doc(session, project_id, kind)
    if doc is None:
        raise ApiError(ErrorCode.E_NOT_FOUND, "文档不存在", status=404)
    return {"kind": kind, "from": from_version, "to": to_version,
            "diff": docs_svc.version_diff(session, doc, from_version, to_version)}


# ---------- jobs / audit / 事件 ----------

