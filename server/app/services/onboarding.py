"""FR-31 新手引导：本地标题候选与只读示例目录（无在线模型）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "examples"
_SENTENCE = re.compile(r"[。！？!?；;\n]+")
_CLAUSE = re.compile(r"[，,、：:]+")


def _clip(text: str, limit: int = 14) -> str:
    text = (text or "").strip(" \t\r\n，,。.！!？?；;：:、")
    text = re.sub(r"[。！？!?；;]+", "，", text)
    text = re.sub(r"，{2,}", "，", text).strip("，")
    if len(text) > limit:
        text = text[:limit].rstrip("，,。.！!？?；;：:、") + "…"
    return text


def title_candidates(copy: str) -> list[str]:
    """从用户文案本地切出 3 个候选标题，不调用任何模型。"""
    text = re.sub(r"\s+", "", copy or "")
    sentences = [s for s in _SENTENCE.split(text) if s]
    clauses = [s for s in _CLAUSE.split(text) if s]
    out: list[str] = []

    def add(value: str, limit: int = 14) -> None:
        clipped = _clip(value, limit)
        if clipped and clipped not in out:
            out.append(clipped)

    if sentences:
        add(sentences[0])
        if len(sentences) > 1:
            add(sentences[-1])
    if len(out) < 2 and len(clauses) > 1:
        add(clauses[-1])
    if len(clauses) >= 2:
        add(f"{_clip(clauses[0], 8)}，{_clip(clauses[1], 6)}")
    for value in sentences + clauses:
        add(value, 12)
    add("我的第一条片")
    add("15 秒短片")
    add("未命名短片")
    return out[:3]


def load_examples() -> list[dict]:
    """示例源在 fixtures/examples（只读），不会写回。"""
    try:
        data = json.loads((EXAMPLES_DIR / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = []
    for item in data.get("items", []):
        if not item.get("id") or not item.get("copy"):
            continue
        items.append({**item, "readonly": True})
    return items


def example(example_id: str) -> dict | None:
    return next((x for x in load_examples() if x["id"] == example_id), None)


def example_profile(item: dict) -> dict:
    seconds = float(item.get("seconds") or 15.0)
    profile = dict(item.get("profile") or {})
    profile.setdefault("width", 1920)
    profile.setdefault("height", 1080)
    profile.setdefault("fps", 24)
    profile["duration"] = seconds
    profile["frames"] = round(seconds * profile["fps"])
    return profile
