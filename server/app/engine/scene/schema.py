"""Scene DSL v1 校验：编译期给字段路径，不静默降级。"""
from __future__ import annotations

from .canonical import canonical
from .components import COMPONENT_NAMES, validate_props

SCENE_SCHEMA = "filmflow.scene/1"
LAYER_TYPES = {"text", "shape", "image", "group", "component"}
TRANSITIONS = {"cut", "match-shape", "paper-slide", "wipe", "dissolve",
               "ink-bleed", "glitch", "push"}
FORBIDDEN = ("eval(", "new Function", "fetch(", "Date.now(", "Math.random(")


def validate_program(program: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(program, dict):
        return ["program 必须是对象"]
    if program.get("schema") != SCENE_SCHEMA:
        errors.append(f"schema 必须是 {SCENE_SCHEMA}")
    if not program.get("id"):
        errors.append("id 必填")
    if not isinstance(program.get("duration"), (int, float)) or program.get("duration", 0) <= 0:
        errors.append("duration 必须 >0")
    canvas = program.get("canvas") or {}
    if not canvas.get("w") or not canvas.get("h"):
        errors.append("canvas.w/h 必填")
    if not canvas.get("fps"):
        errors.append("canvas.fps 必填")
    layers = program.get("layers")
    if not isinstance(layers, list) or not layers:
        errors.append("layers 不能为空")
        layers = []
    if len(layers) > 200:
        errors.append("layers 超过 200")
    ids: set[str] = set()
    for i, layer in enumerate(layers):
        lid = layer.get("id")
        if not lid:
            errors.append(f"layers[{i}].id 必填")
        elif lid in ids:
            errors.append(f"layers[{i}].id 重复：{lid}")
        ids.add(lid)
        if layer.get("type") not in LAYER_TYPES:
            errors.append(f"layers[{i}].type 非法：{layer.get('type')}")
        if not isinstance(layer.get("z", 0), (int, float)):
            errors.append(f"layers[{i}].z 必须是数字")
        if layer.get("type") == "text":
            content = layer.get("content")
            if not isinstance(content, str) or not content.strip():
                errors.append(f"layers[{i}].content 必填")
            elif len(content) > 2000:
                errors.append(f"layers[{i}].content 超过 2000 字")
        if layer.get("type") == "component":
            name = layer.get("component")
            if name not in COMPONENT_NAMES:
                errors.append(f"layers[{i}].component 未知：{name}")
            else:
                errors.extend(f"layers[{i}].{e}" for e in validate_props(name, layer.get("props") or {}))
        if layer.get("type") == "image":
            if not layer.get("src"):
                errors.append(f"layers[{i}].src 必填")
            box = layer.get("box")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                errors.append(f"layers[{i}].box 必须是 [x,y,w,h]")
            if layer.get("fit") not in (None, "cover", "contain"):
                errors.append(f"layers[{i}].fit 非法：{layer.get('fit')}")
            opacity = layer.get("opacity", 1)
            if not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
                errors.append(f"layers[{i}].opacity 必须在 0..1")
    trans = program.get("transitions") or {}
    for key in ("in", "out"):
        t = trans.get(key) or {}
        if t.get("type") and t["type"] not in TRANSITIONS:
            errors.append(f"transitions.{key}.type 非法：{t['type']}")
    body = canonical(program)
    for token in FORBIDDEN:
        if token in body:
            errors.append(f"program 含禁止项：{token}")
    return errors
