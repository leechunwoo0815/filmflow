"""FR-38 Take 元数据：命名/评分/备注/当前、软删除。"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..atomicwrite import write_atomic
from ..errors import ApiError, ErrorCode


def _now() -> str:
    return datetime.now(UTC).isoformat()


def path(root: str | Path) -> Path:
    return Path(root) / "card" / "takes.json"


def load(root: str | Path) -> dict:
    try:
        data = json.loads(path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("schema") != "filmflow.takes/1":
        data = {"schema": "filmflow.takes/1", "currentRunId": None, "items": {}}
    data.setdefault("items", {})
    return data


def save(root: str | Path, data: dict) -> dict:
    data = {**data, "schema": "filmflow.takes/1", "updatedAt": _now()}
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, json.dumps(data, ensure_ascii=False, indent=1))
    return data


def current_run(root: str | Path) -> int | None:
    value = load(root).get("currentRunId")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def item(root: str | Path, run_id: int) -> dict:
    data = load(root)
    raw = data["items"].get(str(run_id)) or {}
    return {"runId": run_id, "name": raw.get("name") or f"Take {run_id}",
            "score": raw.get("score"), "note": raw.get("note") or "",
            "hidden": bool(raw.get("hidden")), "current": data.get("currentRunId") == run_id}


def update(root: str | Path, run_id: int, payload: dict) -> dict:
    data = load(root)
    raw = data["items"].setdefault(str(run_id), {})
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ApiError(ErrorCode.E_VALIDATION, "Take 名称不能为空")
        raw["name"] = name[:80]
    if "score" in payload:
        if payload["score"] in (None, ""):
            raw["score"] = None
        else:
            try:
                score = int(payload["score"])
            except (TypeError, ValueError):
                raise ApiError(ErrorCode.E_VALIDATION, "评分必须是 0..5")
            if not 0 <= score <= 5:
                raise ApiError(ErrorCode.E_VALIDATION, "评分必须是 0..5")
            raw["score"] = score
    if "note" in payload:
        raw["note"] = str(payload["note"] or "")[:1000]
    if "hidden" in payload:
        if payload["hidden"] and data.get("currentRunId") == run_id:
            raise ApiError(ErrorCode.E_VALIDATION, "当前 Take 不能删除", status=409)
        raw["hidden"] = bool(payload["hidden"])
    save(root, data)
    return item(root, run_id)


def promote(root: str | Path, run_id: int) -> dict:
    data = load(root)
    data["currentRunId"] = run_id
    raw = data["items"].setdefault(str(run_id), {})
    raw["hidden"] = False
    save(root, data)
    out = Path(root) / "out"
    out.mkdir(parents=True, exist_ok=True)
    write_atomic(out / "CURRENT.json", json.dumps({
        "schema": "filmflow.current/1", "runId": run_id, "promotedAt": _now(),
        "name": raw.get("name") or f"Take {run_id}",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"currentRunId": run_id, "take": item(root, run_id)}


def delete(root: str | Path, run_id: int) -> dict:
    data = load(root)
    if data.get("currentRunId") == run_id:
        raise ApiError(ErrorCode.E_VALIDATION, "当前 Take 不能删除；先提升另一个 Take", status=409)
    raw = data["items"].setdefault(str(run_id), {})
    raw["hidden"] = True
    save(root, data)
    return item(root, run_id)
