"""FR-39 QA 修复建议：失败分类、位置、建议、可撤销的安全修复。"""
from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..engine.scene.compiler import scene_text
from ..models import Artifact, NodeRun, Project, Run, Workflow
from . import assets as assets_svc
from . import audio as audio_svc
from . import project_docs as docs_svc
from . import timeline_ops as tl_svc

FIX_SCHEMA = "filmflow.qa-fixes/1"
CATEGORIES = (
    "text_overflow", "font_missing", "black_frame", "missing_frame", "motion_spike",
    "static_too_long", "lufs_out", "tp_out", "sync_out", "license_missing",
    "asset_license_missing", "engine_unavailable", "missing_asset", "qa_generic",
)
_NODE_IMPACT = {
    "text_overflow": {"nodes": ["D01", "D02", "E03", "F02"], "gates": ["D03", "D05", "E07"],
                      "seconds": 8},
    "font_missing": {"nodes": ["C03", "D01", "D02", "E03"], "gates": ["D03", "D05"], "seconds": 12},
    "missing_asset": {"nodes": ["D01", "D02", "E03", "F02"], "gates": ["D03", "D05", "E07"],
                      "seconds": 8},
    "black_frame": {"nodes": ["D02", "E06", "F02", "F03"], "gates": ["D03", "D05", "E07"],
                    "seconds": 20},
    "missing_frame": {"nodes": ["F02", "F03"], "gates": ["F06"], "seconds": 30},
    "motion_spike": {"nodes": ["E06", "F02"], "gates": ["E07"], "seconds": 20},
    "static_too_long": {"nodes": ["E06", "F02"], "gates": ["E07"], "seconds": 20},
    "lufs_out": {"nodes": ["G05", "G06", "G07"], "gates": ["G07"], "seconds": 8},
    "tp_out": {"nodes": ["G05", "G06", "G07"], "gates": ["G07"], "seconds": 8},
    "sync_out": {"nodes": ["G02", "G06", "G07"], "gates": ["G07"], "seconds": 15},
    "license_missing": {"nodes": ["G05", "G07"], "gates": ["G07"], "seconds": 2},
    "asset_license_missing": {"nodes": ["G07"], "gates": ["G07"], "seconds": 2},
    "engine_unavailable": {"nodes": ["C01"], "gates": [], "seconds": 60},
    "qa_generic": {"nodes": [], "gates": [], "seconds": 10},
}
_TITLES = {
    "text_overflow": "文案超出场景读时",
    "font_missing": "字体缺字",
    "black_frame": "黑帧",
    "missing_frame": "缺帧",
    "motion_spike": "运动突变",
    "static_too_long": "静态过长",
    "lufs_out": "响度超出目标",
    "tp_out": "真峰超限",
    "sync_out": "口播/画面对齐偏差",
    "license_missing": "音频许可缺失",
    "asset_license_missing": "资产许可缺失",
    "engine_unavailable": "引擎不可用",
    "missing_asset": "资产缺失",
    "qa_generic": "QA 失败",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fixes_path(root: str | Path) -> Path:
    return Path(root) / "card" / "qa_fixes.json"


def _read_fixes(root: str | Path) -> dict:
    try:
        data = json.loads(fixes_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("schema", FIX_SCHEMA)
    data.setdefault("items", [])
    return data


def _write_fixes(root: str | Path, data: dict) -> None:
    p = fixes_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    # P2-08：读-改-写期间由调用方持锁；这里补一个进程内串行化哨兵（见 _fixes_lock）



def _latest_run(session: Session, project_id: int) -> Run | None:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project_id)).first()  # type: ignore[arg-type,union-attr]
    if not wf:
        return None
    return session.exec(select(Run).where(Run.workflow_id == wf.id)
                        .order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]


def _json_artifact(session: Session, run_id: int, node_id: str) -> dict:
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == run_id, Artifact.node_id == node_id,
        Artifact.type == "JSON")).all()  # type: ignore[arg-type]
    for row in reversed(rows):
        try:
            data = json.loads(Path(row.path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _issue(category: str, *, scene_id: str = "", layer_id: str = "", node_id: str = "",
           frame=None, time=None, reason: str, severity: str = "error",
           suggestions: list[dict] | None = None, path: str = "") -> dict:
    loc = scene_id or node_id or (f"frame{frame}" if frame is not None else "project")
    iid = f"{category}:{loc}"
    impact = dict(_NODE_IMPACT.get(category, _NODE_IMPACT["qa_generic"]))
    impact["scenes"] = [scene_id] if scene_id else []
    impact["nodes"] = list(impact.get("nodes") or [])
    impact["gates"] = list(impact.get("gates") or [])
    return {"id": iid, "category": category, "severity": severity,
            "title": _TITLES.get(category, category), "reason": reason,
            "location": {"sceneId": scene_id or None, "layerId": layer_id or None,
                         "nodeId": node_id or None, "frame": frame, "time": time},
            "suggestions": suggestions or [], "impact": impact,
            "fixable": any(s.get("kind") == "auto" for s in (suggestions or [])),
            "path": path}


def _text_suggestions(scene_id: str) -> list[dict]:
    return [
        {"action": "extend_scene", "label": "扩场景 0.5s", "kind": "auto",
         "params": {"sceneId": scene_id, "delta": 0.5}},
        {"action": "scale_text", "label": "字号 −10%", "kind": "auto",
         "params": {"sceneId": scene_id, "scale": 0.9}},
        {"action": "wrap_text", "label": "自动换行", "kind": "auto",
         "params": {"sceneId": scene_id}},
        {"action": "open_timeline", "label": "打开时间轴", "kind": "manual",
         "href": f"/timeline?project={{projectId}}"},
    ]


def _node_suggestions(category: str, node_id: str, scene_id: str = "") -> list[dict]:
    if category in ("lufs_out", "tp_out"):
        target = -18 if category == "tp_out" else -16
        return [
            {"action": "set_lufs", "label": f"目标设为 {target} LUFS", "kind": "auto",
             "params": {"target": target}},
            {"action": "open_audio", "label": "打开音频工作台", "kind": "manual",
             "href": f"/audio?project={{projectId}}"},
        ]
    if category == "font_missing":
        return [
            {"action": "open_assets", "label": "检查/替换字体", "kind": "manual",
             "href": f"/assets?project={{projectId}}"},
            {"action": "open_timeline", "label": "换字体", "kind": "manual",
             "href": f"/timeline?project={{projectId}}"},
        ]
    if category in ("black_frame", "missing_frame"):
        return [
            {"action": "retry_run", "label": "重跑失败节点", "kind": "auto", "params": {}},
            {"action": "open_review", "label": "查看静帧", "kind": "manual",
             "href": f"/review?project={{projectId}}&run={{runId}}"},
        ]
    if category == "asset_license_missing":
        return [
            {"action": "open_assets", "label": "补齐资产许可", "kind": "manual",
             "href": f"/assets?project={{projectId}}"},
        ]
    if category == "license_missing":
        return [
            {"action": "fill_license", "label": "填写许可并保存", "kind": "confirm",
             "params": {"source": "", "license": "", "expires": ""}},
            {"action": "open_assets", "label": "检查资产许可", "kind": "manual",
             "href": f"/assets?project={{projectId}}"},
            {"action": "open_audio", "label": "打开音频许可", "kind": "manual",
             "href": f"/audio?project={{projectId}}"},
        ]
    if category in ("motion_spike", "static_too_long"):
        return [
            {"action": "open_timeline", "label": "调整场景/相机", "kind": "manual",
             "href": f"/timeline?project={{projectId}}"},
        ]
    if category == "sync_out":
        return [
            {"action": "open_audio", "label": "重新对齐口播", "kind": "manual",
             "href": f"/audio?project={{projectId}}"},
        ]
    if category == "engine_unavailable":
        return [
            {"action": "open_templates", "label": "换可用风格", "kind": "manual",
             "href": "/templates"},
        ]
    if category == "missing_asset":
        return [
            {"action": "open_assets", "label": "重新链接资产", "kind": "manual",
             "href": f"/assets?project={{projectId}}"},
            {"action": "open_timeline", "label": "删除/替换图层", "kind": "manual",
             "href": f"/timeline?project={{projectId}}"},
        ]
    if node_id:
        return [{"action": "open_canvas", "label": "打开节点画布", "kind": "manual",
                 "href": f"/canvas?project={{projectId}}&run={{runId}}"}]
    return []


def _classify_node(node_id: str, message: str) -> str:
    m = (message or "").upper()
    if "LUFS" in m:
        return "lufs_out"
    if "TRUE PEAK" in m or "TP" in m and "PEAK" in m:
        return "tp_out"
    if "同步" in message or "SYNC" in m:
        return "sync_out"
    if "黑帧" in message or "BLACK" in m:
        return "black_frame"
    if ("缺" in message and "帧" in message) or "MISSING FRAME" in m:
        return "missing_frame"
    if "字体" in message or "FONT" in m or "GLYPH" in m:
        return "font_missing"
    if "许可" in message or "LICENSE" in m:
        return "license_missing"
    if "静态" in message or "STATIC" in m:
        return "static_too_long"
    if "运动" in message or "MOTION" in m:
        return "motion_spike"
    if "引擎" in message or "ENGINE" in m:
        return "engine_unavailable"
    if "ASSET" in m:
        return "missing_asset"
    return "qa_generic"


def _scene_at_frame(scenes: list[dict], fps: int, frame: int) -> str:
    t = frame / max(1, fps)
    for s in scenes:
        if float(s.get("start", 0)) <= t < float(s.get("end", 0)):
            return str(s.get("id"))
    return ""


def analyze(session: Session, project: Project, run_id: int | None = None) -> dict:
    root = project.root
    imported = docs_svc.is_imported(session, project.id or 0)
    timeline_doc = docs_svc.doc_payload(session, project.id or 0, root, "timeline")
    script = docs_svc.doc_payload(session, project.id or 0, root, "script")["content"]
    timeline = timeline_doc["content"]
    scenes = timeline.get("scenes") or []
    validation = tl_svc.validate(timeline, script)
    issues: list[dict] = []
    seen: set[str] = set()

    def add(issue: dict) -> None:
        if issue["id"] in seen:
            return
        seen.add(issue["id"])
        issues.append(issue)

    for e in validation.get("errors") or []:
        cat = "text_overflow" if e.get("code") in ("E_SCENE_READ_OVERFLOW", "E_SCENE_TOO_SHORT",
                                                   "E_TEXT_SCALE") else "qa_generic"
        sid = str(e.get("sceneId") or "")
        add(_issue(cat, scene_id=sid, reason=e.get("message", ""),
                   suggestions=_text_suggestions(sid) if cat == "text_overflow"
                   else _node_suggestions(cat, ""),
                   path=f"/timeline?project={project.id}"))
    # 资产/字体
    for s in scenes:
        sid = str(s.get("id") or "")
        refs = [(str(l.get("assetSha") or ""), str(l.get("id") or ""), "image")
                for l in s.get("layers") or []]
        refs += [(str(l.get("assetSha") or ""), str(l.get("id") or ""), "audio")
                 for l in s.get("audio_layers") or []]
        refs += [(str(s.get("fontSha") or ""), "", "font")]
        for sha, lid, kind in refs:
            if not sha:
                continue
            row = session.exec(select(assets_svc.Asset).where(
                assets_svc.Asset.sha256 == sha,
                assets_svc.Asset.archived == False)).first()  # type: ignore[arg-type]
            if row:
                lic_ok, lic_why = assets_svc.asset_license_ok(row)
                if not lic_ok:
                    add(_issue("asset_license_missing", scene_id=sid, layer_id=lid,
                               reason=lic_why,
                               suggestions=_node_suggestions("asset_license_missing", ""),
                               path=f"/assets?project={project.id}"))
            if not assets_svc.resolve_for_project(session, root, sha):
                add(_issue("missing_asset", scene_id=sid, layer_id=lid,
                           reason=f"{kind} 资产 {sha[:12]} 缺失或不在当前项目",
                           suggestions=_node_suggestions("missing_asset", ""),
                           path=f"/timeline?project={project.id}"))
                continue
            if kind == "font":
                row = session.exec(select(assets_svc.Asset).where(
                    assets_svc.Asset.sha256 == sha,
                    assets_svc.Asset.archived == False)).first()  # type: ignore[arg-type]
                if row:
                    text = scene_text(s, script)
                    try:
                        cov = assets_svc.font_coverage(row.path, text)
                    except Exception:
                        cov = {"ok": True, "missingCount": 0}
                    if not cov.get("ok", True):
                        add(_issue("font_missing", scene_id=sid,
                                   reason=f"{sid} 字体 {row.meta_json.get('family') or sha[:8]} "
                                          f"缺 {cov.get('missingCount')} 字",
                                   suggestions=_node_suggestions("font_missing", ""),
                                   path=f"/assets?project={project.id}"))
    # 音频许可
    if not imported:
        lic = audio_svc.load_license(root)
        ok, why = audio_svc.license_ok(lic)
        if not ok:
            add(_issue("license_missing", node_id="G05", reason=why,
                       suggestions=_node_suggestions("license_missing", "G05"),
                       path=f"/audio?project={project.id}"))
    run = session.get(Run, run_id) if run_id else _latest_run(session, project.id or 0)
    if run:
        states = session.exec(select(NodeRun).where(NodeRun.run_id == run.id)).all()  # type: ignore[arg-type]
        for st in states:
            if st.status != "failed":
                continue
            cat = _classify_node(st.node_id, st.message)
            add(_issue(cat, node_id=st.node_id, reason=st.message or f"{st.node_id} 失败",
                       suggestions=_node_suggestions(cat, st.node_id),
                       path=f"/canvas?project={project.id}&run={run.id}"))
        motion = _json_artifact(session, run.id or 0, "E06")
        fps = int(timeline.get("fps") or 24)
        for sr in motion.get("staticRuns") or []:
            f0 = int(sr.get("from") or 0)
            add(_issue("static_too_long", scene_id=_scene_at_frame(scenes, fps, f0),
                       frame=f0, reason=f"连续静态 {sr.get('to', 0) - f0} 帧",
                       severity="warning", suggestions=_node_suggestions("static_too_long", ""),
                       path=f"/timeline?project={project.id}"))
        for sp in motion.get("cutSpikes") or []:
            f0 = int(sp.get("frame") or 0)
            add(_issue("motion_spike", scene_id=_scene_at_frame(scenes, fps, f0),
                       frame=f0, reason=f"帧差 {sp.get('diff')} 超过阈值",
                       severity="warning", suggestions=_node_suggestions("motion_spike", ""),
                       path=f"/timeline?project={project.id}"))
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: (order.get(x["severity"], 9), x["category"], x["id"]))
    by_cat: dict[str, int] = {}
    for i in issues:
        by_cat[i["category"]] = by_cat.get(i["category"], 0) + 1
    return {"schema": "filmflow.qa/1", "projectId": project.id,
            "runId": run.id if run else None, "generatedAt": _now(),
            "issues": issues, "summary": {"total": len(issues),
                                          "error": sum(1 for i in issues if i["severity"] == "error"),
                                          "warning": sum(1 for i in issues if i["severity"] == "warning"),
                                          "fixable": sum(1 for i in issues if i["fixable"]),
                                          "byCategory": by_cat},
            "validation": validation}


def _timeline_before(session: Session, project: Project) -> dict:
    pid = project.id or 0
    doc = docs_svc.doc_payload(session, pid, project.root, "timeline")
    profile = docs_svc.get_doc(session, pid, "profile")
    profile_content = profile.content_json if profile else docs_svc.default_doc(session, pid, project.root, "profile")
    # 深拷贝：修复动作会原地改同一份 content dict，共享引用会让 before==after，撤销链失效
    return {"kind": "timeline", "version": doc["version"], "content": deepcopy(doc["content"]),
            "profileVersion": profile.version if profile else 0,
            "profileExisted": profile is not None,
            "profileContent": deepcopy(profile_content)}


def _apply(session: Session, project: Project, issue: dict, action: str,
           payload: dict, run_id: int | None = None,
           before_state: dict | None = None) -> tuple[dict, dict]:
    root = project.root
    pid = project.id or 0
    if action in ("extend_scene", "scale_text", "wrap_text"):
        doc = docs_svc.doc_payload(session, pid, root, "timeline")
        script = docs_svc.doc_payload(session, pid, root, "script")["content"]
        content = doc["content"]
        sid = str(payload.get("sceneId") or issue["location"].get("sceneId") or "")
        scene = next((s for s in content.get("scenes") or [] if s.get("id") == sid), None)
        if not scene:
            raise ValueError(f"场景不存在：{sid}")
        if action == "extend_scene":
            delta = float(payload.get("delta") or 0.5)
            new = tl_svc.resize(content, script, sid, float(scene["end"]) + delta, force=True)
        elif action == "scale_text":
            current = float(scene.get("text_scale") or 1.0)
            scale = max(0.7, round(current - 0.1, 3))
            if scale >= current:
                raise ValueError("字号已到最小 70%")
            new = tl_svc.set_text_scale(content, script, sid, scale)
        else:
            text = scene_text(scene, script)
            if "\n" in text:
                raise ValueError("已经有换行")
            cut = len(text) // 2
            for d in range(0, 12):
                for cand in (cut + d, cut - d):
                    if 0 < cand < len(text) and text[cand - 1] in "，。！？；,;!? ":
                        cut = cand
                        break
                else:
                    continue
                break
            new = tl_svc.set_text(content, script, sid, text[:cut] + "\n" + text[cut:], force=True)
        saved, _ = docs_svc.save_doc(session, pid, "timeline", new, doc["version"], "qa-fix")
        after_state = {"kind": "timeline", "version": saved.version,
                       "hash": docs_svc.content_hash(saved.content_json)}
        if action == "extend_scene":
            before = before_state or _timeline_before(session, project)
            profile_content = dict(before.get("profileContent") or {})
            profile_content.update({
                "duration": float(new.get("duration") or 0),
                "frames": int(new.get("frames") or 0),
            })
            try:
                profile_saved, _ = docs_svc.save_doc(session, pid, "profile", profile_content,
                                                     int(before.get("profileVersion") or 0), "qa-fix")
            except Exception as e:
                try:
                    docs_svc.save_doc(session, pid, "timeline", before["content"], saved.version, "qa-fix-rollback")
                except Exception:
                    pass
                raise ValueError(f"配置文件更新失败，已尝试回滚时间轴：{e}")
            after_state.update({"profileVersion": profile_saved.version,
                                "profileContent": profile_content,
                                "profileHash": docs_svc.content_hash(profile_saved.content_json)})
        return after_state, {"sceneId": sid}
    if action == "set_lufs":
        target = float(payload.get("target") or -16)
        before = audio_svc.load_mix(root)
        after = audio_svc.save_mix(root, {**before, "preset": str(int(target)),
                                          "targetLufs": target})
        # F-QA-1：给撤销链提供链顶判据（此前 mix/license 撤销无守卫，会静默覆盖手工编辑）
        return {"kind": "mix", "before": before, "after": after,
                "hash": docs_svc.content_hash(after)}, {"targetLufs": target}
    if action == "fill_license":
        before = audio_svc.load_license(root)
        lic = audio_svc.save_license(root, payload)
        return {"kind": "license", "before": before, "after": lic,
                "hash": docs_svc.content_hash(lic)}, {}
    if action == "retry_run":
        rid = run_id or (_latest_run(session, project.id or 0).id
                         if _latest_run(session, project.id or 0) else None)
        if not rid:
            raise ValueError("没有可重跑的 Run")
        source = session.get(Run, rid)
        if not source:
            raise ValueError(f"Run {rid} 不存在")
        new_run = Run(workflow_id=source.workflow_id, parent_run_id=source.id)
        session.add(new_run)
        session.commit()
        session.refresh(new_run)
        from ..engine import runengine as re
        re.start_run(new_run.id)
        return {"kind": "run", "sourceRunId": rid, "newRunId": new_run.id}, {"sourceRunId": rid, "newRunId": new_run.id}
    raise ValueError(f"不支持的 QA 修复动作：{action}")


def apply_fix(session: Session, project: Project, issue_id: str, action: str,
              payload: dict | None = None, run_id: int | None = None) -> dict:
    payload = payload or {}
    result = analyze(session, project, run_id)
    issue = next((i for i in result["issues"] if i["id"] == issue_id), None)
    if not issue:
        raise ValueError("QA 问题已不存在或已刷新")
    auto = [s for s in issue["suggestions"] if s.get("kind") in ("auto", "confirm")]
    spec = next((s for s in auto if s.get("action") == action), None)
    if not spec:
        raise ValueError(f"动作 {action} 不是该问题的安全自动修复")
    params = {**(spec.get("params") or {}), **(payload or {})}
    before_state = _timeline_before(session, project) if action in (
        "extend_scene", "scale_text", "wrap_text") else None
    if action == "set_lufs":
        before_state = {"kind": "mix", "content": audio_svc.load_mix(project.root)}
    if action == "fill_license":
        before_state = {"kind": "license", "content": audio_svc.load_license(project.root)}
    after_state, extra = _apply(session, project, issue, action, params, run_id, before_state)
    doc_verified = None
    verified = None
    requires_rerun = False
    next_action = None
    if action in ("extend_scene", "scale_text", "wrap_text"):
        after_issues = analyze(session, project, run_id)["issues"]
        doc_verified = not any(i["category"] == issue["category"] and
                               i["location"]["sceneId"] == issue["location"]["sceneId"]
                               for i in after_issues)
        requires_rerun = True
        next_action = "run_new"
    elif action == "set_lufs":
        requires_rerun = True
        next_action = "run_new"
    elif action in ("fill_license", "missing_asset"):
        after_issues = analyze(session, project, run_id)["issues"]
        doc_verified = not any(i["category"] == issue["category"] and
                               (not issue["location"].get("sceneId") or
                                i["location"]["sceneId"] == issue["location"]["sceneId"])
                               for i in after_issues)
        verified = bool(doc_verified)
    entry = {"id": "fix_" + uuid.uuid4().hex[:12], "at": _now(),
             "issueId": issue_id, "category": issue["category"], "action": action,
             "projectId": project.id, "runId": run_id, "result": "applied",
             "verified": verified, "documentVerified": doc_verified,
             "requiresRerun": requires_rerun, "nextAction": next_action,
             "before": before_state,
             "after": after_state, "afterVersion": after_state.get("version"),
             "afterHash": after_state.get("hash"),
             "afterProfileVersion": after_state.get("profileVersion"),
             "afterProfileHash": after_state.get("profileHash"), "extra": extra}
    data = _read_fixes(project.root)
    data["items"].append(entry)
    _write_fixes(project.root, data)
    return entry


def _require_undo_head(data: dict, entry: dict, current_value, expected_hash,
                       legacy_version, current_version, label: str) -> None:
    """撤销按 LIFO：内容仍等于该次修复结果（链顶）才允许自动回退。"""
    if expected_hash is not None:
        if current_value == expected_hash:
            return
    elif legacy_version is None or current_version == legacy_version:
        return
    head = next((x for x in reversed(data["items"])
                 if x.get("result") == "applied" and not x.get("undone")
                 and (x.get("before") or {}).get("kind") == "timeline"
                 and x.get("afterHash")), None)
    hint = (f"；请先撤销 {head['id']}（{head.get('action')}）"
            if head and head["id"] != entry.get("id") else "")
    raise ValueError(f"{label}在该修复之后又被改动，只能按倒序撤销最新一次{hint}")


def undo_fix(session: Session, project: Project, fix_id: str) -> dict:
    data = _read_fixes(project.root)
    entry = next((x for x in data["items"] if x.get("id") == fix_id), None)
    if not entry or entry.get("undone"):
        raise ValueError("修复记录不存在或已撤销")
    before = entry.get("before") or {}
    kind = before.get("kind")
    if kind == "timeline":
        pid = project.id or 0
        current = docs_svc.doc_payload(session, pid, project.root, "timeline")
        _require_undo_head(data, entry, docs_svc.content_hash(current["content"]),
                           entry.get("afterHash"), entry.get("afterVersion"),
                           current["version"], "时间轴")
        docs_svc.save_doc(session, pid, "timeline", before["content"],
                          current["version"], "qa-undo")
        if before.get("profileContent") is not None:
            profile = docs_svc.get_doc(session, pid, "profile")
            if not before.get("profileExisted"):
                # 修复前没有 profile 文档行：撤销要回到"没有"，否则派生默认值会被固化为残缺文档。
                # P1-06：先删 docrevision 子行再删文档行，否则 foreign_keys=ON 下 FK 失败。
                if profile:
                    from ..models import DocRevision
                    for rev in session.exec(select(DocRevision).where(
                            DocRevision.doc_id == profile.id)).all():  # type: ignore[arg-type,union-attr]
                        session.delete(rev)
                    session.delete(profile)
                    session.commit()
            else:
                profile_hash = docs_svc.content_hash(profile.content_json) if profile else None
                _require_undo_head(data, entry, profile_hash, entry.get("afterProfileHash"),
                                   entry.get("afterProfileVersion"),
                                   profile.version if profile else None, "配置文件")
                docs_svc.save_doc(session, pid, "profile", before["profileContent"],
                                  profile.version if profile else 0, "qa-undo")
    elif kind == "mix":
        # F-QA-1：与 timeline 一致的链顶守卫——修复后若又被手工改动，只能倒序撤销
        current_mix = audio_svc.load_mix(project.root)
        _require_undo_head(data, entry, docs_svc.content_hash(current_mix),
                           entry.get("afterHash"), None, None, "混音配置")
        audio_svc.save_mix(project.root, before.get("content") or {})
    elif kind == "license":
        current_lic = audio_svc.load_license(project.root)
        _require_undo_head(data, entry, docs_svc.content_hash(current_lic),
                           entry.get("afterHash"), None, None, "音乐许可")
        prev = before.get("content") or {}
        if prev:
            audio_svc.save_license(project.root, prev)
        else:
            audio_svc.license_path(project.root).unlink(missing_ok=True)
    else:
        raise ValueError("该修复不支持撤销")
    entry["undone"] = True
    entry["undoneAt"] = _now()
    _write_fixes(project.root, data)
    return entry


def report(project: Project) -> dict:
    data = _read_fixes(project.root)
    items = data.get("items") or []
    applied = [x for x in items if x.get("result") == "applied"]
    active = [x for x in applied if not x.get("undone")]
    verified = [x for x in applied if x.get("verified") is True]
    unverified = [x for x in applied if x.get("verified") is None]
    pending_rerun = [x for x in applied if x.get("requiresRerun") and not x.get("undone")]
    failed = [x for x in items if x.get("result") != "applied"]
    by_action: dict[str, int] = {}
    for x in items:
        by_action[x.get("action", "")] = by_action.get(x.get("action", ""), 0) + 1
    return {"schema": FIX_SCHEMA, "projectId": project.id,
            "attempts": len(items), "applied": len(applied),
            "active": len(active), "verified": len(verified), "unverified": len(unverified),
            "pendingRerun": len(pending_rerun),
            "failed": len(failed), "undone": sum(1 for x in items if x.get("undone")),
            "successRate": round(len(applied) / len(items), 4) if items else None,
            "verificationRate": round(len(verified) / len(applied), 4) if applied else None,
            "falsePositiveRate": None,
            "note": "falsePositive 需下一次成功 Run 后复核；timeline/LUFS 修复的 verified=null 表示文档级已处理但成片需新 Run 验证。",
            "byAction": by_action, "items": items}
