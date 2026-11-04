"""FR-37 模板/系列：项目模板、场景模板、变量替换与模板锁。"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from ..engine.fpscalc import frames_for, norm_fps
from ..models import Template
from . import assets

from ..atomicwrite import write_atomic

PROJECT_SCHEMA = "filmflow.project-template/1"
SCENE_SCHEMA = "filmflow.scene-template/1"
VAR_RE = re.compile(r"{{\s*([A-Za-z0-9_-]+)\s*}}")
LOCK_REL = "card/template.lock.json"


def _camera(duration: float, zoom0: float, zoom1: float, x1: float = 0.0) -> dict:
    return {"anchor": [960, 540], "keyframes": [
        {"t": 0.0, "zoom": zoom0, "x": 0, "y": 0, "rotate": 0, "ease": "linear"},
        {"t": round(max(0.5, duration), 3), "zoom": zoom1, "x": x1, "y": 0,
         "rotate": 0, "ease": "easeInOut"},
    ]}


BUILTIN_SCENE_TEMPLATES: list[dict] = [
    {"id": "builtin:scene-title", "name": "标题", "kind": "scene", "duration": 2.5,
     "description": "一个大标题，锁定机位。", "text": "一句话标题。",
     "meaning": "标题/主张", "operation": "标题占满画面，留白给下一场",
     "camera": "锁定", "camera_keyframes": _camera(2.5, 1.0, 1.02)["keyframes"],
     "camera_anchor": [960, 540], "transition": "cut", "transition_duration": 0.5,
     "layers": [], "audio_layers": []},
    {"id": "builtin:scene-argument", "name": "论点", "kind": "scene", "duration": 4.0,
     "description": "先给判断，再补一句解释。", "text": "先给一个判断。",
     "meaning": "核心论点", "operation": "缓推，强调判断句",
     "camera": "缓推", "camera_keyframes": _camera(4.0, 1.0, 1.08)["keyframes"],
     "camera_anchor": [960, 540], "transition": "dissolve", "transition_duration": 0.5,
     "layers": [], "audio_layers": []},
    {"id": "builtin:scene-evidence", "name": "证据", "kind": "scene", "duration": 5.0,
     "description": "一条可验证的证据，横移展示。", "text": "证据一。",
     "meaning": "证据/数据", "operation": "横移，把证据放在画面中心",
     "camera": "横移", "camera_keyframes": _camera(5.0, 1.03, 1.03, 60)["keyframes"],
     "camera_anchor": [960, 540], "transition": "push", "transition_duration": 0.5,
     "layers": [], "audio_layers": []},
    {"id": "builtin:scene-conclusion", "name": "结论", "kind": "scene", "duration": 3.0,
     "description": "收束到一句观众能记住的话。", "text": "所以，结论是。",
     "meaning": "结论", "operation": "缓拉，留呼吸",
     "camera": "缓拉", "camera_keyframes": _camera(3.0, 1.08, 1.0)["keyframes"],
     "camera_anchor": [960, 540], "transition": "dissolve", "transition_duration": 0.5,
     "layers": [], "audio_layers": []},
    {"id": "builtin:scene-cta", "name": "行动", "kind": "scene", "duration": 3.0,
     "description": "告诉观众下一步做什么。", "text": "下一步，行动。",
     "meaning": "CTA", "operation": "锁定收尾，给行动指令",
     "camera": "锁定", "camera_keyframes": _camera(3.0, 1.0, 1.0)["keyframes"],
     "camera_anchor": [960, 540], "transition": "cut", "transition_duration": 0.5,
     "layers": [], "audio_layers": []},
]
BUILTIN_SCENE_BY_ID = {x["id"]: x for x in BUILTIN_SCENE_TEMPLATES}


def substitute(value, variables: dict | None):
    """递归替换 {{var}}；返回 (新值, 缺失变量集合)。"""
    variables = variables or {}
    missing: set[str] = set()

    def rec(v):
        if isinstance(v, str):
            def repl(m):
                key = m.group(1)
                if key not in variables:
                    missing.add(key)
                    return m.group(0)
                return str(variables[key])
            return VAR_RE.sub(repl, v)
        if isinstance(v, list):
            return [rec(x) for x in v]
        if isinstance(v, dict):
            return {k: rec(x) for k, x in v.items()}
        return v

    return rec(value), sorted(missing)


def extract_variables(value) -> list[str]:
    found: set[str] = set()

    def rec(v):
        if isinstance(v, str):
            found.update(VAR_RE.findall(v))
        elif isinstance(v, list):
            for x in v:
                rec(x)
        elif isinstance(v, dict):
            for x in v.values():
                rec(x)

    rec(value)
    return sorted(found)


def collect_asset_shas(timeline: dict) -> list[str]:
    return sorted({sha for sha, _field, _path in assets.walk_refs(timeline)})


def project_template_content(*, profile: dict, timeline: dict, style_id: str = "",
                             style_family: str = "print", delivery: dict | None,
                             copy: str = "", description: str = "",
                             source_project_id: int = 0) -> dict:
    scenes = []
    total = 0.0
    for s in timeline.get("scenes") or []:
        dur = round(float(s.get("end", 0)) - float(s.get("start", 0)), 3)
        if dur <= 0:
            continue
        total += dur
        item = {"duration": dur, "id": s.get("id")}
        for key in ("meaning", "operation", "camera", "camera_keyframes", "camera_anchor",
                    "transition", "transition_duration", "layers", "audio_layers", "fontSha",
                    "text_scale"):
            if s.get(key) not in (None, "", [], {}):
                item[key] = deepcopy(s[key])
        scenes.append(item)
    prof = dict(profile)
    if total > 0:
        prof["duration"] = round(total, 3)
        prof["frames"] = frames_for(total, norm_fps(prof.get("fps") or 24))
    content = {"schema": PROJECT_SCHEMA, "description": description,
               "profile": prof, "style_id": style_id, "style_family": style_family,
               "delivery": deepcopy(delivery or {}), "copy": copy,
               "sourceProjectId": source_project_id,
               "assetShas": collect_asset_shas(timeline),
               "timeline": {"fps": norm_fps(timeline.get("fps") or prof.get("fps") or 24),
                            "layout": deepcopy(timeline.get("layout") or {}),
                            "scenes": scenes}}
    content["variables"] = extract_variables({"copy": copy, "timeline": content["timeline"]})
    return content


def scene_template_content(scene: dict, *, keep_text: bool = False,
                           description: str = "", source_project_id: int = 0) -> dict:
    dur = round(float(scene.get("end", 0)) - float(scene.get("start", 0)), 3)
    content = {"schema": SCENE_SCHEMA, "description": description,
               "sourceProjectId": source_project_id,
               "assetShas": collect_asset_shas({"scenes": [scene]}),
               "duration": max(0.5, dur), "text": scene.get("text", "") if keep_text else "新场景。",
               "meaning": scene.get("meaning", ""), "operation": scene.get("operation", ""),
               "camera": scene.get("camera", ""), "transition": scene.get("transition", "cut"),
               "transition_duration": scene.get("transition_duration", 0.5)}
    for key in ("camera_keyframes", "camera_anchor", "layers", "audio_layers", "fontSha",
                "text_scale"):
        if scene.get(key) not in (None, [], {}):
            content[key] = deepcopy(scene[key])
    return content


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


def build_timeline_from_content(content: dict, script: dict, profile: dict) -> dict:
    """把保存的模板套到新文案上：保留场景结构/相机/图层，文本交给 script。"""
    from . import timeline_ops as tl
    tpl = content.get("timeline") or {}
    tpl_scenes = [s for s in (tpl.get("scenes") or []) if s.get("duration")]
    if not tpl_scenes:
        from .project_docs import build_timeline_doc
        return build_timeline_doc(script, profile)
    sentences = script.get("sentences") or []
    groups = _group_sentences(len(sentences), len(tpl_scenes))
    scenes, t = [], 0.0
    for i, ts in enumerate(tpl_scenes):
        dur = round(max(0.5, float(ts.get("duration") or 0)), 3)
        scene = {"id": f"S{i + 1:02d}", "start": round(t, 3), "end": round(t + dur, 3),
                 "time_basis": "planned", "source_span": groups[i],
                 "meaning": ts.get("meaning", ""), "operation": ts.get("operation", ""),
                 "camera": ts.get("camera", ""), "transition": ts.get("transition", ""),
                 "read_seconds": dur, "last_text_at": round(t + dur, 3)}
        for key in ("camera_keyframes", "camera_anchor", "transition_duration",
                    "layers", "audio_layers", "fontSha", "text_scale"):
            if ts.get(key) not in (None, "", [], {}):
                scene[key] = deepcopy(ts[key])
        scenes.append(scene)
        t += dur
    doc = {"schema": "filmflow.timeline/2",
           "fps": norm_fps(tpl.get("fps") or profile.get("fps") or 24),
           "duration": round(t, 3),
           "frames": frames_for(t, norm_fps(profile.get("fps") or 24)),
           "scenes": scenes, "events": [], "tracks": [],
           "layout": deepcopy(tpl.get("layout") or {"safeArea": {"w": 0.05, "h": 0.08},
                                                    "grid": {"cols": 12}})}
    tl.normalize(doc, script)
    return doc


def overlay_template(current_timeline: dict, content: dict,
                     script: dict | None = None) -> tuple[dict, dict]:
    """升级：只覆盖模板里的视觉结构，保留当前文本/时长/场景 id。"""
    from . import timeline_ops as tl
    doc = deepcopy(current_timeline)
    tpl_scenes = content.get("timeline", {}).get("scenes") or []
    for scene, ts in zip(doc.get("scenes") or [], tpl_scenes):
        for key in ("camera", "camera_keyframes", "camera_anchor", "transition",
                    "transition_duration", "layers", "audio_layers", "fontSha", "operation",
                    "text_scale"):
            if key in ts:
                scene[key] = deepcopy(ts[key])
            elif key in ("layers", "audio_layers", "fontSha", "camera_keyframes",
                         "camera_anchor", "transition_duration"):
                scene.pop(key, None)
    prof = {}
    tpl_profile = content.get("profile") or {}
    for key in ("width", "height", "fps"):
        if tpl_profile.get(key) is not None:
            prof[key] = tpl_profile[key]
    tl.normalize(doc, script or {"sentences": []})
    return doc, prof


def template_diff(current_profile: dict, current_timeline: dict, content: dict) -> dict:
    tpl_profile = content.get("profile") or {}
    fields = {}
    for key in ("width", "height", "fps", "duration"):
        if current_profile.get(key) != tpl_profile.get(key):
            fields[key] = {"current": current_profile.get(key), "template": tpl_profile.get(key)}
    scenes_now = len(current_timeline.get("scenes") or [])
    scenes_tpl = len(content.get("timeline", {}).get("scenes") or [])
    return {"profile": fields, "sceneCount": {"current": scenes_now, "template": scenes_tpl},
            "sceneCountDelta": scenes_tpl - scenes_now,
            "styleId": content.get("style_id", ""),
            "note": "升级只覆盖已有场景的相机/转场/图层/字体/SFX；不自动增删场景、不改文案。"}


def lock_path(root: str | Path) -> Path:
    return Path(root) / LOCK_REL


def read_lock(root: str | Path) -> dict:
    p = lock_path(root)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_lock(root: str | Path, template_id: int, version: int,
               variables: list[str] | None = None) -> dict:
    data = {"schema": "filmflow.template-lock/1", "templateId": template_id,
            "version": int(version), "variables": variables or [],
            "appliedAt": datetime.now(UTC).isoformat()}
    p = lock_path(root)
    write_atomic(p, json.dumps(data, ensure_ascii=False, indent=1))
    return data


def next_scene_id(scenes: list[dict]) -> str:
    used = {str(s.get("id")) for s in scenes}
    n = len(scenes) + 1
    while f"S{n:02d}" in used:
        n += 1
    return f"S{n:02d}"


def saved_dto(t: Template, with_content: bool = False) -> dict:
    content = t.content_json or {}
    base = {"id": f"saved:{t.id}", "templateId": t.id, "kind": t.kind,
            "title": t.name, "name": t.name, "description": t.description or content.get("description", ""),
            "version": t.version, "saved": True,
            "variables": content.get("variables") or extract_variables(content)}
    if t.kind == "project":
        prof = content.get("profile") or {}
        base.update({"seconds": float(prof.get("duration") or 0), "profile": prof,
                     "copy": content.get("copy", ""), "style_id": content.get("style_id", ""),
                     "style_family": content.get("style_family", "print"),
                     "sceneCount": len(content.get("timeline", {}).get("scenes") or [])})
    else:
        base.update({"seconds": float(content.get("duration") or 0),
                     "text": content.get("text", ""), "scene": content})
    if with_content:
        base["content"] = content
    return base


def builtin_scene_dto(item: dict) -> dict:
    return {"id": item["id"], "templateId": None, "kind": "scene", "title": item["name"],
            "name": item["name"], "description": item.get("description", ""),
            "seconds": float(item.get("duration") or 0), "saved": False,
            "text": item.get("text", ""), "scene": {k: deepcopy(v) for k, v in item.items()
                                                    if k not in ("id", "name", "kind", "description")}}
