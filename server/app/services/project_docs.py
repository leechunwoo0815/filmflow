"""项目文档模型（FR-25）：默认文档、canonical hash、字段级 diff、场景构建。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlmodel import Session, select

from ..errors import ApiError, ErrorCode
from ..models import DocRevision, ProjectDoc, Workflow

DOC_KINDS = ("script", "brief", "timeline", "profile", "delivery", "audio")
SCHEMAS = {
    "script": "filmflow.script/1",
    "brief": "filmflow.brief/1",
    "timeline": "filmflow.timeline/2",
    "profile": "filmflow.profile/1",
    "delivery": "filmflow.delivery/1",
    "audio": "filmflow.audio/1",
}


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(content) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[。！？；!?;])", text or "") if s.strip()]


def build_script_doc(text: str, title: str = "") -> dict:
    """把原文切成带字符区间的句子；不改写一个字。"""
    sentences, pos = [], 0
    for i, sent in enumerate(split_sentences(text)):
        start = text.find(sent, pos)
        if start < 0:
            start = pos
        end = start + len(sent)
        sentences.append({"id": f"L{i + 1:03d}", "text": sent, "source_span": [start, end]})
        pos = end
    return {"schema": SCHEMAS["script"], "title": title, "text": text, "sentences": sentences}


def _group_sentences(count: int, scenes: int) -> list[list[int]]:
    if count <= 0:
        return [[] for _ in range(scenes)]
    if count <= scenes:
        return [[i] if i < count else [] for i in range(scenes)]
    base, rem = divmod(count, scenes)
    groups, start = [], 0
    for i in range(scenes):
        take = base + (1 if i < rem else 0)
        groups.append(list(range(start, start + take)))
        start += take
    return groups


def build_timeline_doc(script: dict, profile: dict) -> dict:
    """由 script.doc + profile 生成确定性场景骨架；场景只带 source_span，不生成文案。"""
    sentences = script.get("sentences") or []
    fps = int(profile.get("fps") or 24)
    duration = float(profile.get("duration") or 0)
    if duration <= 0:
        chars = sum(len(s.get("text", "")) for s in sentences)
        duration = max(1.0, chars / 5.2) if chars else 3.0
    scene_count = min(6, max(1, len(sentences))) if sentences else 1
    groups = _group_sentences(len(sentences), scene_count)
    reads = [sum(len(sentences[j].get("text", "")) / 5.2 for j in g) if g else 0.0 for g in groups]
    weights = [max(0.8, r + 0.5) if g else 0.6 for g, r in zip(groups, reads)]
    total = sum(weights) or 1.0
    raw = [max(0.8, duration * w / total) for w in weights]
    factor = duration / sum(raw)
    durations = [round(d * factor, 3) for d in raw]
    durations[-1] = round(duration - sum(durations[:-1]), 3)
    scenes, events, clips, t = [], [], [], 0.0
    for i, group in enumerate(groups):
        start, end = round(t, 3), round(t + durations[i], 3)
        read = round(min(durations[i], max(0.8, reads[i])), 3)
        last_text_at = round(max(start, end - read), 3)
        scenes.append({
            "id": f"S{i + 1:02d}", "start": start, "end": end, "time_basis": "planned",
            "meaning": "", "operation": "", "source_span": group,
            "last_text_at": last_text_at, "read_seconds": read,
            "camera": "", "transition": "",
        })
        events.append({"id": f"E{i + 1:02d}", "scene_id": f"S{i + 1:02d}", "at": start,
                       "time_basis": "planned", "role": "scene_start", "allow_snap": False})
        clips.append({"sceneId": f"S{i + 1:02d}", "start": start, "end": end})
        t = end
    return {
        "schema": SCHEMAS["timeline"], "fps": fps, "duration": round(t, 3),
        "frames": round(t * fps), "scenes": scenes, "events": events,
        "tracks": [{"id": "V1", "type": "video", "clips": clips}],
        "layout": {"safeArea": {"w": 0.05, "h": 0.08}, "grid": {"cols": 12}},
    }


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def default_doc(session: Session, project_id: int, project_root: str, kind: str) -> dict:
    root = Path(project_root)
    if kind in ("timeline", "profile") and is_imported(session, project_id):
        task = _read_json(root / "card" / "task.json")
        if task:
            if kind == "timeline":
                return {"schema": SCHEMAS["timeline"], "fps": task.get("fps", 24),
                        "duration": (task.get("film") or {}).get("duration", 0),
                        "frames": (task.get("film") or {}).get("frames", 0),
                        "scenes": task.get("scenes", []), "events": task.get("events", []),
                        "tracks": []}
            return {"schema": SCHEMAS["profile"], "width": task.get("width", 1920),
                    "height": task.get("height", 1080), "fps": task.get("fps", 24),
                    "duration": (task.get("film") or {}).get("duration", 0),
                    "frames": (task.get("film") or {}).get("frames", 0)}
    if kind == "script":
        copy = root / "card" / "copy.txt"
        return build_script_doc(copy.read_text(encoding="utf-8") if copy.exists() else "")
    if kind == "profile":
        prof = _read_json(root / "project.profile.json")
        return {"schema": SCHEMAS["profile"], **prof}
    if kind == "timeline":
        script = get_doc(session, project_id, "script")
        script_content = script.content_json if script else default_doc(session, project_id, project_root, "script")
        profile_doc = get_doc(session, project_id, "profile")
        profile = profile_doc.content_json if profile_doc else default_doc(session, project_id, project_root, "profile")
        return build_timeline_doc(script_content, profile)
    return {"schema": SCHEMAS[kind], "content": {}}


def get_doc(session: Session, project_id: int, kind: str) -> ProjectDoc | None:
    return session.exec(select(ProjectDoc).where(
        ProjectDoc.project_id == project_id, ProjectDoc.kind == kind)).first()  # type: ignore[arg-type,union-attr]


def is_imported(session: Session, project_id: int) -> bool:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project_id)).first()  # type: ignore[arg-type,union-attr]
    return bool((((wf.graph_json or {}) if wf else {}).get("meta") or {}).get("imported"))


def doc_payload(session: Session, project_id: int, project_root: str, kind: str) -> dict:
    doc = get_doc(session, project_id, kind)
    imported = is_imported(session, project_id)
    if doc is None:
        content = default_doc(session, project_id, project_root, kind)
        return {"kind": kind, "version": 0, "hash": content_hash(content), "content": content,
                "initialized": False, "updated_at": None, "imported": imported}
    return {"kind": kind, "version": doc.version, "hash": doc.hash, "content": doc.content_json,
            "initialized": True, "updated_at": doc.updated_at.isoformat(), "imported": imported}


def validate_doc(kind: str, content: dict) -> None:
    if kind not in DOC_KINDS:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知文档类型：{kind}")
    if not isinstance(content, dict):
        raise ApiError(ErrorCode.E_DOC_SCHEMA, "文档内容必须是 JSON 对象")
    if content.get("schema") != SCHEMAS[kind]:
        raise ApiError(ErrorCode.E_DOC_SCHEMA,
                       f"schema 必须是 {SCHEMAS[kind]}，当前 {content.get('schema')}")
    if kind == "script":
        if not isinstance(content.get("text"), str) or not isinstance(content.get("sentences"), list):
            raise ApiError(ErrorCode.E_DOC_SCHEMA, "script 文档缺 text/sentences")
    if kind == "timeline":
        scenes = content.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ApiError(ErrorCode.E_DOC_SCHEMA, "timeline 文档 scenes 不能为空")
        ids = [s.get("id") for s in scenes]
        if len(ids) != len(set(ids)):
            raise ApiError(ErrorCode.E_DOC_SCHEMA, "timeline 场景 id 必须唯一")
        for i, s in enumerate(scenes):
            if not isinstance(s.get("start"), (int, float)) or not isinstance(s.get("end"), (int, float)):
                raise ApiError(ErrorCode.E_DOC_SCHEMA, f"timeline 场景 {i} 缺 start/end")
            if s["start"] >= s["end"]:
                raise ApiError(ErrorCode.E_DOC_SCHEMA, f"timeline 场景 {s.get('id')} start 必须小于 end")
            if i and s["start"] < scenes[i - 1]["end"] - 1e-6:
                raise ApiError(ErrorCode.E_DOC_SCHEMA, f"timeline 场景 {s.get('id')} 与上一场重叠")


def diff_docs(a, b, path: str = "$") -> list[dict]:
    """字段级 diff（足够 UI 展示与 409 冲突详情）。"""
    if type(a) is not type(b):
        return [{"path": path, "from": a, "to": b}]
    if isinstance(a, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append({"path": f"{path}.{key}", "from": None, "to": b[key]})
            elif key not in b:
                out.append({"path": f"{path}.{key}", "from": a[key], "to": None})
            else:
                out.extend(diff_docs(a[key], b[key], f"{path}.{key}"))
        return out
    if isinstance(a, list):
        out = []
        for i in range(max(len(a), len(b))):
            if i >= len(a):
                out.append({"path": f"{path}[{i}]", "from": None, "to": b[i]})
            elif i >= len(b):
                out.append({"path": f"{path}[{i}]", "from": a[i], "to": None})
            else:
                out.extend(diff_docs(a[i], b[i], f"{path}[{i}]"))
        return out
    return [] if a == b else [{"path": path, "from": a, "to": b}]


def _now():
    return datetime.now(timezone.utc)


def save_doc(session: Session, project_id: int, kind: str, content: dict,
             base_version: int, author: str = "local") -> tuple[ProjectDoc, list[dict]]:
    if kind == "script" and isinstance(content, dict):
        # script 的 sentences/source_span 由 text 唯一确定，服务端重建，避免前端漏更新
        content = build_script_doc(content.get("text", ""), content.get("title", ""))
    validate_doc(kind, content)
    doc = get_doc(session, project_id, kind)
    if doc is None:
        if int(base_version) != 0:
            raise ApiError(ErrorCode.E_DOC_CONFLICT, "文档尚未初始化，base_version 必须为 0",
                           status=409, details={"current_version": 0})
        doc = ProjectDoc(project_id=project_id, kind=kind, version=1,
                         content_json=content, hash=content_hash(content), author=author)
        session.add(doc)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise ApiError(ErrorCode.E_DOC_CONFLICT, "文档已被其他窗口创建，请刷新后重试", status=409)
        session.refresh(doc)
        diff = diff_docs({}, content)
        session.add(DocRevision(doc_id=doc.id, version=1, content_json=content,
                                diff_json=diff, author=author))
        session.commit()
        return doc, diff

    if int(base_version) != doc.version:
        raise ApiError(ErrorCode.E_DOC_CONFLICT, "文档版本冲突，请合并后重试", status=409,
                       details={"current_version": doc.version,
                                "current": doc.content_json,
                                "diff": diff_docs(doc.content_json, content)})
    new_version = doc.version + 1
    diff = diff_docs(doc.content_json, content)
    stmt = (update(ProjectDoc)
            .where(ProjectDoc.id == doc.id, ProjectDoc.version == base_version)
            .values(version=new_version, content_json=content, hash=content_hash(content),
                    author=author, updated_at=_now()))
    result = session.connection().execute(stmt)
    if result.rowcount != 1:
        session.rollback()
        current = get_doc(session, project_id, kind)
        raise ApiError(ErrorCode.E_DOC_CONFLICT, "文档版本冲突，请刷新后重试", status=409,
                       details={"current_version": current.version if current else 0,
                                "current": current.content_json if current else None,
                                "diff": diff_docs(current.content_json if current else {}, content)})
    session.add(DocRevision(doc_id=doc.id, version=new_version, content_json=content,
                            diff_json=diff, author=author))
    session.commit()
    session.expire_all()
    fresh = get_doc(session, project_id, kind)
    assert fresh is not None
    return fresh, diff


def list_versions(session: Session, doc: ProjectDoc) -> list[dict]:
    rows = session.exec(select(DocRevision).where(DocRevision.doc_id == doc.id)
                        .order_by(DocRevision.version.desc())).all()  # type: ignore[arg-type,union-attr]
    return [{"version": r.version, "hash": content_hash(r.content_json), "author": r.author,
             "created_at": r.created_at.isoformat(), "diff": r.diff_json} for r in rows]


def restore_doc(session: Session, project_id: int, kind: str, version: int,
                author: str = "local") -> tuple[ProjectDoc, list[dict]]:
    doc = get_doc(session, project_id, kind)
    if doc is None:
        raise ApiError(ErrorCode.E_NOT_FOUND, "文档不存在", status=404)
    rev = session.exec(select(DocRevision).where(
        DocRevision.doc_id == doc.id, DocRevision.version == version)).first()  # type: ignore[arg-type,union-attr]
    if rev is None:
        raise ApiError(ErrorCode.E_NOT_FOUND, f"版本 {version} 不存在", status=404)
    return save_doc(session, project_id, kind, rev.content_json, doc.version, author)


def version_diff(session: Session, doc: ProjectDoc, from_version: int, to_version: int) -> list[dict]:
    def content_at(v: int):
        if v == doc.version:
            return doc.content_json
        rev = session.exec(select(DocRevision).where(
            DocRevision.doc_id == doc.id, DocRevision.version == v)).first()  # type: ignore[arg-type,union-attr]
        return rev.content_json if rev else None

    a, b = content_at(from_version), content_at(to_version)
    if a is None or b is None:
        raise ApiError(ErrorCode.E_NOT_FOUND, "版本不存在", status=404)
    return diff_docs(a, b)
