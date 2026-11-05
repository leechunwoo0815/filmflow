"""FR-40（R3.5）：通知中心——本地 JSON 存储、flock 防并发、(kind, ref) 去重、已读。

通知在 Run 生命周期产生（成功/失败/门待批），存储 `~/.filmflow/notifications.json`
（全局、flock 串行，同 B1 的防丢更新口径）。前端轮询 GET /api/notifications。

不推送、不邮件（PRD §FR-40 行为 5：离线可用）。
"""
from __future__ import annotations

import fcntl
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..atomicwrite import write_atomic
from ..config import settings

SCHEMA = "filmflow.notifications/1"
MAX_KEEP = 200          # 超出丢弃最旧的已读；未读永不因容量丢弃


def _path() -> Path:
    return Path(settings.home) / "notifications.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def _mutation():
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p.parent / ".notifications.lock", "a")  # noqa: SIM115 -- 跨 yield 持锁
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _load_raw() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("schema") != SCHEMA:
        data = {"schema": SCHEMA, "items": []}
    return data


def load() -> dict:
    data = _load_raw()
    unread = sum(1 for x in data["items"] if not x.get("readAt"))
    return {"schema": SCHEMA, "items": data["items"][-50:], "unread": unread}


def notify(kind: str, ref: str, title: str, detail: str = "",
           link: str | None = None, action: dict | None = None) -> dict | None:
    """发一条通知；(kind, ref) 去重——同引用未读期间不重复（PRD：通知不重复）。

    返回新建的通知（重复时 None）。
    """
    with _mutation():
        data = _load_raw()
        for x in data["items"]:
            if x["kind"] == kind and x["ref"] == ref and not x.get("readAt"):
                return None
        item = {"id": uuid.uuid4().hex[:10], "kind": kind, "ref": ref, "title": title,
                "detail": detail, "link": link, "action": action or {},
                "createdAt": _now(), "readAt": None}
        data["items"].append(item)
        _trim(data)
        write_atomic(_path(), json.dumps(data, ensure_ascii=False, indent=1))
        return item


def _trim(data: dict) -> None:
    items = data["items"]
    if len(items) <= MAX_KEEP:
        return
    read_idx = [i for i, x in enumerate(items) if x.get("readAt")]
    drop = set(read_idx[:len(items) - MAX_KEEP])
    if len(items) - MAX_KEEP > len(read_idx):
        raise RuntimeError("通知容量溢出且未读过多——不应发生（MAX_KEEP=200）")
    data["items"] = [x for i, x in enumerate(items) if i not in drop]


def mark_read(notification_id: str) -> bool:
    with _mutation():
        data = _load_raw()
        for x in data["items"]:
            if x["id"] == notification_id and not x.get("readAt"):
                x["readAt"] = _now()
                write_atomic(_path(), json.dumps(data, ensure_ascii=False, indent=1))
                return True
        return False


def mark_all_read() -> int:
    with _mutation():
        data = _load_raw()
        n = 0
        for x in data["items"]:
            if not x.get("readAt"):
                x["readAt"] = _now()
                n += 1
        if n:
            write_atomic(_path(), json.dumps(data, ensure_ascii=False, indent=1))
        return n


def run_finished(run_id: int, project_name: str, ok: bool, detail: str = "") -> dict | None:
    """Run 终态通知（runengine 终态时调用）：成功/失败各一条，失败带修复入口。"""
    return notify(
        "run_failed" if not ok else "run_succeeded",
        f"run:{run_id}",
        f"「{project_name}」Run {run_id} {'失败' if not ok else '完成'}",
        detail or ("" if ok else "打开画布查看失败节点"),
        link=f"/canvas?projectId=&runId={run_id}" if not ok else f"/canvas?projectId=&runId={run_id}",
        action=None if ok else {"kind": "open_canvas", "runId": run_id},
    )


def gate_pending(run_id: int, gate: str, project_name: str) -> dict | None:
    """人工门待批通知：同 (run, gate) 未读期间去重。"""
    return notify("gate_pending", f"gate:{run_id}:{gate}",
                  f"「{project_name}」{gate} 待批",
                  detail="打开画布签门", link=f"/canvas?projectId=&runId={run_id}",
                  action={"kind": "open_gate", "runId": run_id, "gate": gate})
