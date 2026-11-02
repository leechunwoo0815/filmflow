"""scene-kit 12 组件 schema（Python 侧权威；JS 实现见 engines/riso/assets/scene-kit.js）。"""
from __future__ import annotations

from copy import deepcopy

COMPONENTS: dict[str, dict] = {
    "paper-card": {
        "props": {"x": 80, "y": 100, "w": 1760, "h": 880, "radius": 8,
                  "paper": "#F4EEE2", "ink": "#3D5588", "grain": 0.08},
        "required": ["x", "y", "w", "h"],
    },
    "headline": {
        "props": {"text": "标题", "x": 160, "y": 520, "size": 132, "weight": 900,
                  "color": "#F4EEE2", "align": "left", "maxWidth": 1600},
        "required": ["text", "x", "y"],
    },
    "body-block": {
        "props": {"lines": ["正文"], "x": 160, "y": 620, "size": 44, "lineHeight": 1.5,
                  "color": "#F4EEE2", "maxWidth": 1600},
        "required": ["lines", "x", "y"],
    },
    "stamp": {
        "props": {"text": "已核", "x": 1500, "y": 760, "size": 72, "rotate": -8,
                  "color": "#FF665E"},
        "required": ["text", "x", "y"],
    },
    "arrow-grow": {
        "props": {"x1": 160, "y1": 760, "x2": 1200, "y2": 760, "width": 12,
                  "progress": 1.0, "color": "#FF665E"},
        "required": ["x1", "y1", "x2", "y2"],
    },
    "hand-pointer": {
        "props": {"x": 1400, "y": 700, "scale": 1.0, "rotate": -0.2, "color": "#FF665E"},
        "required": ["x", "y"],
    },
    "roller": {
        "props": {"x": 200, "y": 820, "w": 900, "h": 42, "progress": 0.6, "color": "#FFB511"},
        "required": ["x", "y", "w"],
    },
    "halftone-field": {
        "props": {"x": 120, "y": 140, "w": 1680, "h": 800, "period": 18,
                  "density": 0.35, "color": "#3D5588"},
        "required": ["x", "y", "w", "h"],
    },
    "registration-cross": {
        "props": {"x": 1768, "y": 128, "size": 1.0, "color": "#3D5588"},
        "required": ["x", "y"],
    },
    "evidence-card": {
        "props": {"x": 300, "y": 520, "count": 5, "stagger": 0.45, "w": 320, "h": 120,
                  "paper": "#F4EEE2", "ink": "#3D5588"},
        "required": ["x", "y"],
    },
    "chart-bar": {
        "props": {"x": 300, "y": 500, "w": 900, "h": 320, "values": [0.3, 0.6, 0.9],
                  "labels": [], "color": "#FF665E"},
        "required": ["x", "y", "values"],
    },
    "count-up": {
        "props": {"x": 500, "y": 700, "value": 100, "suffix": "%", "size": 160,
                  "duration": 1.2, "color": "#FF665E"},
        "required": ["x", "y", "value"],
    },
}

COMPONENT_NAMES = tuple(COMPONENTS)


def default_props(name: str) -> dict:
    if name not in COMPONENTS:
        raise KeyError(name)
    return deepcopy(COMPONENTS[name]["props"])


def validate_props(name: str, props: dict) -> list[str]:
    if name not in COMPONENTS:
        return [f"未知组件：{name}"]
    spec = COMPONENTS[name]
    errors = [f"{name} 缺 props.{k}" for k in spec.get("required", []) if k not in (props or {})]
    for k, default in spec["props"].items():
        if k in (props or {}):
            v = props[k]
            if isinstance(default, (int, float)) and not isinstance(v, (int, float)):
                errors.append(f"{name}.{k} 必须是数字")
            if isinstance(default, list) and not isinstance(v, list):
                errors.append(f"{name}.{k} 必须是数组")
            if isinstance(default, str) and not isinstance(v, str):
                errors.append(f"{name}.{k} 必须是字符串")
    return errors
