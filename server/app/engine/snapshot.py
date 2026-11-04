"""Run 启动文档快照：执行器只读 runs/<id>/docs/，运行中编辑不改变本次 Run（FR-25）。"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from ..atomicwrite import write_atomic
from .cachekey import file_sha256
from ..models import ProjectDoc, Run, Workflow
from ..services.project_docs import build_script_doc, build_timeline_doc, content_hash
from ..services.render_profiles import resolve as resolve_render_profiles

SNAPSHOT_SCHEMA = "filmflow.snapshot/1"


def snapshot_dir(project_root: str, run_id: int) -> Path:
    return Path(project_root) / "runs" / str(run_id) / "docs"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def snapshot_doc_drift(session: Session, run: Run, project_root: str) -> dict[str, dict]:
    """快照内文档哈希 vs 当前库内文档哈希；非空即"文档已改，本 Run 的快照是旧的"。

    P0-5：`POST /runs/{id}/retry` 只重跑失败节点、沿用 `runs/<id>/docs/snapshot.json`，
    所以 QA 扩场景这类时间轴修复对重试**不生效**（渲出来还是旧时长）。调用方据此 fail-closed。
    """
    snap_path = snapshot_dir(project_root, run.id) / "snapshot.json"
    snap = _read_json(snap_path) if snap_path.exists() else {}
    if snap.get("schema") != SNAPSHOT_SCHEMA:
        return {}
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        return {}
    current = {d.kind: d for d in session.exec(select(ProjectDoc).where(
        ProjectDoc.project_id == wf.project_id)).all()}  # type: ignore[arg-type,union-attr]
    drift: dict[str, dict] = {}
    for kind, entry in (snap.get("docs") or {}).items():
        row = current.get(kind)
        run_hash, cur_hash = str(entry.get("hash") or ""), str(row.hash if row else "")
        if run_hash and cur_hash and run_hash != cur_hash:
            drift[kind] = {"runHash": run_hash, "currentHash": cur_hash,
                           "runVersion": entry.get("version"),
                           "currentVersion": row.version if row else None}
    return drift


def ensure_run_snapshot(session: Session, run: Run, project_root: str) -> dict:
    run_dir = snapshot_dir(project_root, run.id)
    snap_path = run_dir / "snapshot.json"
    if snap_path.exists():
        snap = _read_json(snap_path)
        if snap.get("schema") == SNAPSHOT_SCHEMA:
            return snap
    run_dir.mkdir(parents=True, exist_ok=True)
    wf = session.get(Workflow, run.workflow_id)
    imported = bool((((wf.graph_json or {}) if wf else {}).get("meta") or {}).get("imported"))
    docs: dict[str, dict] = {}
    if wf:
        for d in session.exec(select(ProjectDoc).where(ProjectDoc.project_id == wf.project_id)).all():  # type: ignore[arg-type]
            docs[d.kind] = {"version": d.version, "hash": d.hash, "content": d.content_json}
    profile: dict = {}
    if "profile" in docs:
        profile = {k: v for k, v in docs["profile"]["content"].items() if k != "schema"}
    else:
        profile = _read_json(Path(project_root) / "project.profile.json")
    if "script" not in docs:
        copy = Path(project_root) / "card" / "copy.txt"
        if copy.exists():
            script = build_script_doc(copy.read_text(encoding="utf-8"))
            docs["script"] = {"version": 0, "hash": content_hash(script), "content": script}
    if imported:
        task_path = Path(project_root) / "card" / "task.json"
        if task_path.exists():
            task = _read_json(task_path)
            write_atomic(run_dir / "task.json", json.dumps(task, ensure_ascii=False, indent=1))
            docs["task"] = {"version": 0, "hash": content_hash(task), "content": task}
            if not profile:
                profile = {"width": task.get("width", 1920), "height": task.get("height", 1080),
                           "fps": task.get("fps", 24),
                           "duration": (task.get("film") or {}).get("duration", 0),
                           "frames": (task.get("film") or {}).get("frames", 0)}
    else:
        if "timeline" not in docs and "script" in docs:
            timeline = build_timeline_doc(docs["script"]["content"], profile)
            docs["timeline"] = {"version": 0, "hash": content_hash(timeline), "content": timeline}
            # 旧项目首次快照补持久化 timeline：之后改文案不重建时间轴，保证增量只脏目标场景
            if wf and not session.exec(select(ProjectDoc).where(
                    ProjectDoc.project_id == wf.project_id,
                    ProjectDoc.kind == "timeline")).first():  # type: ignore[arg-type,union-attr]
                row = ProjectDoc(project_id=wf.project_id, kind="timeline", version=1,
                                 content_json=timeline, hash=content_hash(timeline),
                                 author="snapshot")
                session.add(row)
                session.commit()
                session.refresh(row)
                docs["timeline"] = {"version": 1, "hash": row.hash, "content": timeline}
        for kind in ("script", "timeline"):
            if kind in docs:
                write_atomic(run_dir / f"{kind}.doc.json",
                             json.dumps(docs[kind]["content"], ensure_ascii=False, indent=1))
    render_profiles = resolve_render_profiles(project_root, profile, allow_low_final=imported)
    snapshot = {
        "schema": SNAPSHOT_SCHEMA, "run_id": run.id, "imported": imported,
        "profile": profile, "render_profiles": render_profiles, "docs": docs,
        "created_at": datetime.now(UTC).isoformat(),
    }
    snapshot["doc_snapshot_sha"] = content_hash({
        "docs": docs, "profile": profile, "render_profiles": render_profiles,
        "imported": imported,
    })
    write_atomic(snap_path, json.dumps(snapshot, ensure_ascii=False, indent=1))
    # 库内封印：交付时按文件 sha 校验，复制/替换旧快照文件不再能骗过门禁（判官 #4 后半）
    run.snapshot_sha = file_sha256(str(snap_path))
    session.add(run)
    session.commit()
    return snapshot
