"""FR-33 审片批注：帧锚定评论、回复/resolve、场景决议、导出导入、审片包。"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import uuid
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..atomicwrite import write_atomic
from ..errors import ApiError, ErrorCode

KINDS = {"rect", "arrow", "pen", "text"}
CATEGORIES = {"must", "suggest", "question"}
STATUSES = {"open", "resolved"}
DECISIONS = {"pass", "needs_changes"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def path(root: str | Path) -> Path:
    return Path(root) / "review" / "review.json"


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load(root: str | Path) -> dict:
    data = _read(path(root))
    if data.get("schema") != "filmflow.review/1":
        return {"schema": "filmflow.review/1", "comments": [],
                "decisions": {"scenes": {}, "overall": None}, "updatedAt": None}
    data.setdefault("comments", [])
    data.setdefault("decisions", {"scenes": {}, "overall": None})
    data["decisions"].setdefault("scenes", {})
    data["decisions"].setdefault("overall", None)
    return data


def save(root: str | Path, data: dict) -> dict:
    data = {**data, "schema": "filmflow.review/1", "updatedAt": _now()}
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, json.dumps(data, ensure_ascii=False, indent=1))
    return data


@contextmanager
def _mutation(root: str | Path):
    """B1/P2-08：读改写全程持 flock（review.json 旁的 .review.lock）。

    原子写只保证"不留半文件"，不保证不丢更新——两个并发客户端都 load v1 再各自
    save 时，后写的会覆盖先写的。flock 对**跨线程**（各开各的 fd）与**跨进程**
    都互斥；本模块的变更函数内部不再嵌套加锁（item 等读路径不锁），无自锁。
    """
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p.parent / ".review.lock", "a")  # noqa: SIM115 -- 跨 yield 持锁，不能 with
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def summary(root: str | Path) -> dict:
    data = load(root)
    comments = data["comments"]
    open_count = sum(1 for c in comments if c.get("status") == "open")
    by_scene: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for c in comments:
        if c.get("status") != "open":
            continue
        by_scene[str(c.get("sceneId") or "")] = by_scene.get(str(c.get("sceneId") or ""), 0) + 1
        by_category[str(c.get("category") or "suggest")] = \
            by_category.get(str(c.get("category") or "suggest"), 0) + 1
    return {"total": len(comments), "open": open_count, "resolved": len(comments) - open_count,
            "byScene": by_scene, "byCategory": by_category,
            "overall": data["decisions"].get("overall")}


def add(root: str | Path, payload: dict) -> dict:
    with _mutation(root):
        return _add(root, payload)


def _add(root: str | Path, payload: dict) -> dict:
    body = str(payload.get("body") or "").strip()
    if not body and not payload.get("geometry"):
        raise ApiError(ErrorCode.E_VALIDATION, "批注必须包含文字或图形")
    kind = str(payload.get("kind") or "text")
    category = str(payload.get("category") or "suggest")
    if kind not in KINDS:
        raise ApiError(ErrorCode.E_VALIDATION, f"批注类型必须是 {sorted(KINDS)}")
    if category not in CATEGORIES:
        raise ApiError(ErrorCode.E_VALIDATION, f"批注分类必须是 {sorted(CATEGORIES)}")
    try:
        frame = int(payload.get("frame") or 0)
        t = round(float(payload.get("time") or 0), 4)
    except (TypeError, ValueError):
        raise ApiError(ErrorCode.E_VALIDATION, "frame/time 必须是数字")
    if frame < 0 or t < 0:
        raise ApiError(ErrorCode.E_VALIDATION, "frame/time 不能为负")
    data = load(root)
    comment = {
        "id": uuid.uuid4().hex[:10],
        "frame": frame, "time": t,
        "sceneId": str(payload.get("sceneId") or ""),
        "layerId": str(payload.get("layerId") or ""),
        "kind": kind, "category": category, "status": "open",
        "author": str(payload.get("author") or "local"),
        "assignee": str(payload.get("assignee") or ""),
        "body": body,
        "geometry": payload.get("geometry") or {},
        "replies": [],
        "createdAt": _now(),
    }
    data["comments"].append(comment)
    save(root, data)
    return comment


def update(root: str | Path, comment_id: str, payload: dict) -> dict:
    with _mutation(root):
        return _update(root, comment_id, payload)


def _update(root: str | Path, comment_id: str, payload: dict) -> dict:
    data = load(root)
    comment = next((c for c in data["comments"] if c.get("id") == comment_id), None)
    if not comment:
        raise ApiError(ErrorCode.E_NOT_FOUND, "批注不存在", status=404)
    if "body" in payload:
        comment["body"] = str(payload["body"] or "")
    if "category" in payload:
        if payload["category"] not in CATEGORIES:
            raise ApiError(ErrorCode.E_VALIDATION, "批注分类非法")
        comment["category"] = payload["category"]
    if "status" in payload:
        if payload["status"] not in STATUSES:
            raise ApiError(ErrorCode.E_VALIDATION, "状态必须是 open/resolved")
        comment["status"] = payload["status"]
    if "assignee" in payload:
        comment["assignee"] = str(payload["assignee"] or "")
    if payload.get("reply"):
        comment["replies"].append({"id": uuid.uuid4().hex[:8],
                                   "author": str(payload.get("author") or "local"),
                                   "body": str(payload["reply"]), "createdAt": _now()})
    comment["updatedAt"] = _now()
    save(root, data)
    return comment


def decide(root: str | Path, payload: dict) -> dict:
    with _mutation(root):
        return _decide(root, payload)


def _decide(root: str | Path, payload: dict) -> dict:
    decision = str(payload.get("decision") or "")
    if decision not in DECISIONS and decision not in ("approved", "rejected"):
        raise ApiError(ErrorCode.E_VALIDATION, "决议必须是 pass/needs_changes（整片可用 approved/rejected）")
    data = load(root)
    scene_id = str(payload.get("sceneId") or "")
    entry = {"decision": decision, "author": str(payload.get("author") or "local"),
             "note": str(payload.get("note") or ""), "at": _now()}
    if scene_id:
        data["decisions"]["scenes"][scene_id] = entry
    else:
        data["decisions"]["overall"] = entry
    save(root, data)
    return data["decisions"]


def export_csv(root: str | Path) -> str:
    data = load(root)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "frame", "time", "sceneId", "layerId", "kind", "category",
                     "status", "author", "assignee", "body"])
    for c in data["comments"]:
        writer.writerow([c.get("id"), c.get("frame"), c.get("time"), c.get("sceneId"),
                         c.get("layerId"), c.get("kind"), c.get("category"), c.get("status"),
                         c.get("author"), c.get("assignee"), c.get("body")])
    return out.getvalue()


def import_json(root: str | Path, payload: dict) -> dict:
    with _mutation(root):
        return _import_json(root, payload)


def _import_json(root: str | Path, payload: dict) -> dict:
    incoming = payload.get("review") if isinstance(payload.get("review"), dict) else payload
    comments = incoming.get("comments") if isinstance(incoming, dict) else None
    if not isinstance(comments, list):
        raise ApiError(ErrorCode.E_VALIDATION, "导入文件缺少 comments 数组")
    data = load(root)
    existing = {c.get("id") for c in data["comments"]}
    added, skipped = 0, 0
    for c in comments:
        cid = str(c.get("id") or "")
        if cid and cid in existing:
            skipped += 1
            continue
        c["id"] = cid or uuid.uuid4().hex[:10]
        c.setdefault("status", "open")
        c.setdefault("replies", [])
        c.setdefault("geometry", {})
        c.setdefault("category", "suggest")
        c.setdefault("kind", "text")
        c.setdefault("author", "import")
        existing.add(c["id"])
        data["comments"].append(c)
        added += 1
    if isinstance(incoming.get("decisions"), dict):
        scenes = incoming["decisions"].get("scenes") or {}
        for sid, dec in scenes.items():
            if sid not in data["decisions"]["scenes"]:
                data["decisions"]["scenes"][sid] = dec
        if incoming["decisions"].get("overall") and not data["decisions"].get("overall"):
            data["decisions"]["overall"] = incoming["decisions"]["overall"]
    save(root, data)
    return {"added": added, "skipped": skipped, "total": len(data["comments"])}


def package(root: str | Path, video: Path, title: str = "") -> dict:
    if not video.exists():
        raise ApiError(ErrorCode.E_VALIDATION, f"审片视频不存在：{video}")
    data = load(root)
    out = Path(root) / "review" / "review-package.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    readme = (f"FilmFlow 审片包\n\n项目：{title or Path(root).name}\n"
              f"批注：{len(data['comments'])} 条\n\n"
              "1) 播放 review.mp4；\n"
              "2) 在 FilmFlow 审片页导入 review.json（按 id 去重）；\n"
              "3) 本包不依赖云端，不上传任何文件。\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(video, "review.mp4")
        z.writestr("review.json", json.dumps(data, ensure_ascii=False, indent=1))
        z.writestr("README.txt", readme)
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    return {"path": str(out), "sha256": sha, "bytes": out.stat().st_size,
            "comments": len(data["comments"])}
