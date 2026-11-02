"""Scene DSL canonical JSON 与 hash（编译确定性 / scene_hash）。"""
from __future__ import annotations

import hashlib
import json


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def scene_hash(program: dict, tokens_lock_sha: str, engine_sha: str,
               font_sha: str, profile: dict) -> str:
    return content_hash({
        "program": program,
        "tokens": tokens_lock_sha,
        "engine": engine_sha,
        "font": font_sha,
        "profile": profile,
    })
