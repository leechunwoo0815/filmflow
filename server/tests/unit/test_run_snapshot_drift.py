"""P0-5 剩下的那半：文档漂移后，`POST /runs/{id}/retry` 必须拒绝而不是重渲旧内容。

FR-25 规定"运行中编辑不改变本次 Run"，所以 `ensure_run_snapshot` 会一直复用
`runs/<id>/docs/snapshot.json`。QA 扩场景只改文档 → 重试同一个 Run 时，
执行器读到的还是旧时长（专家 P0-5 第 2 点：`retry_run` 复用旧快照，时间轴类修复不生效）。
渲染级证据在 `tests/integration/test_qa_extend_scene_render.py`；这里锁服务层判据。
"""
from __future__ import annotations

import asyncio
import contextlib
import shutil
import sys
from pathlib import Path

import pytest
from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))
from app.api import routes as routes_mod
from app.db import engine
from app.engine.snapshot import ensure_run_snapshot, snapshot_doc_drift
from app.errors import ApiError
from app.models import Project, Run, Workflow
from app.services import project_docs as docs


def _project(tmp_path: Path, name: str = "drift"):
    root = tmp_path / name
    (root / "card").mkdir(parents=True, exist_ok=True)
    (root / "card" / "copy.txt").write_text("第一句。第二句。", encoding="utf-8")
    with Session(engine) as s:
        p = Project(name=name, root=str(root))
        s.add(p); s.commit(); s.refresh(p)
        wf = Workflow(project_id=p.id, graph_json={"meta": {}, "nodes": [], "edges": []})
        s.add(wf); s.commit(); s.refresh(wf)
        run = Run(workflow_id=wf.id)
        s.add(run); s.commit(); s.refresh(run)
        return p.id or 0, run.id or 0, str(root)


def _cleanup(pid: int, root: str):
    from app.services.project_cleanup import delete_project
    with Session(engine) as s, contextlib.suppress(Exception):   # 收尾：删不掉也不该盖掉断言
        delete_project(s, pid, remove_dir=False)
    shutil.rmtree(root, ignore_errors=True)


def test_no_drift_right_after_snapshot(tmp_path):
    pid, rid, root = _project(tmp_path)
    try:
        with Session(engine) as s:
            run = s.get(Run, rid)
            snap = ensure_run_snapshot(s, run, root)
            assert snap["docs"], "快照里应该有文档"
            assert snapshot_doc_drift(s, run, root) == {}
    finally:
        _cleanup(pid, root)


def test_drift_reports_the_changed_doc_kind(tmp_path):
    pid, rid, root = _project(tmp_path)
    try:
        with Session(engine) as s:
            run = s.get(Run, rid)
            ensure_run_snapshot(s, run, root)
            tl = docs.get_doc(s, pid, "timeline")
            before = tl.version          # save_doc 会就地刷新同一行，版本要先存下来
            content = dict(tl.content_json)
            content["scenes"][0]["text"] = "改过的文案。"
            docs.save_doc(s, pid, "timeline", content, base_version=before, author="test")
            drift = snapshot_doc_drift(s, run, root)
            assert set(drift) == {"timeline"}, drift
            assert drift["timeline"]["runHash"] != drift["timeline"]["currentHash"]
            assert drift["timeline"]["runVersion"] == before
            assert drift["timeline"]["currentVersion"] == before + 1
    finally:
        _cleanup(pid, root)


def test_run_retry_refuses_stale_snapshot(tmp_path):
    pid, rid, root = _project(tmp_path)
    try:
        with Session(engine) as s:
            ensure_run_snapshot(s, s.get(Run, rid), root)
            tl = docs.get_doc(s, pid, "timeline")
            content = dict(tl.content_json)
            content["scenes"][0]["text"] = "扩过之后的文案。"
            docs.save_doc(s, pid, "timeline", content, base_version=tl.version, author="test")
            with pytest.raises(ApiError) as ei:
                asyncio.run(routes_mod.run_retry(rid, session=s))
            assert ei.value.status_code == 409
            detail = ei.value.detail
            assert detail["code"] == "E_RUN_SNAPSHOT_STALE"
            assert "timeline" in detail["details"]["drift"]
            assert "新 Run" in detail["message"]
    finally:
        _cleanup(pid, root)


def test_run_retry_404_for_unknown_run():
    with Session(engine) as s:
        with pytest.raises(ApiError) as ei:
            asyncio.run(routes_mod.run_retry(999999, session=s))
        assert ei.value.status_code == 404


def test_missing_snapshot_is_not_drift(tmp_path):
    """没起过的 Run 没有快照文件：重试会现场建快照，不该被误判成漂移。"""
    pid, rid, root = _project(tmp_path)
    try:
        with Session(engine) as s:
            assert snapshot_doc_drift(s, s.get(Run, rid), root) == {}
    finally:
        _cleanup(pid, root)
