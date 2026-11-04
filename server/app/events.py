"""事件总线：SSE 订阅者广播 + 按 Run 落 JSONL（规格 §7.9）。"""
from __future__ import annotations

from .logs import get as _get_log

_log = _get_log("events")

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from .config import settings
from .db import engine
from .models import Event

_subscribers: dict[int, set[asyncio.Queue]] = {}
_global_subs: set[asyncio.Queue] = set()


def _jsonl_path(run_id: int) -> Path:
    d = settings.logs_dir / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d / "events.jsonl"


def emit(event_type: str, run_id: int | None = None, node_id: str | None = None, **payload) -> None:
    """发事件：内存广播（不阻塞）+ JSONL + DB。DB 写入延迟到调用方会话外执行。"""
    record = {
        "type": event_type,
        "run_id": run_id,
        "node_id": node_id,
        "at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    line = json.dumps(record, ensure_ascii=False)
    if run_id is not None:
        try:
            with _jsonl_path(run_id).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    # DB 持久化（fire and forget，用独立连接避免会话竞争）
    try:
        with engine.begin() as conn:
            conn.execute(
                Event.__table__.insert().values(
                    run_id=run_id, node_id=node_id, type=event_type,
                    payload_json=payload, at=datetime.now(UTC),
                )
            )
    except Exception:
        _log.debug("swallowed exception in emit (except Exception:)", exc_info=True)
    q_item = json.dumps({"event": event_type, **payload, "run_id": run_id, "node_id": node_id}, ensure_ascii=False, default=str)
    for q in list(_subscribers.get(run_id or 0, set())) + list(_global_subs):
        try:
            q.put_nowait(q_item)
        except asyncio.QueueFull:
            pass


def subscribe(run_id: int | None) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    if run_id is None:
        _global_subs.add(q)
    else:
        _subscribers.setdefault(run_id, set()).add(q)
    return q


def unsubscribe(run_id: int | None, q: asyncio.Queue) -> None:
    if run_id is None:
        _global_subs.discard(q)
    else:
        _subscribers.get(run_id, set()).discard(q)
