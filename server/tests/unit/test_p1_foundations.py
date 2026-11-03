"""P1 基础治理：SQLite pragma、workspace roots 环境解析、A05 自动批准守卫、交付门禁。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.config import Settings
from app.db import engine
from app.engine import runengine
from app.services import delivery
from app.services import project_docs as docs


def test_workspace_roots_accept_plain_and_json(monkeypatch):
    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", "/tmp/filmflow-one")
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/filmflow-one")]

    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", '["/tmp/a", "/tmp/b"]')
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/a"), Path("/tmp/b")]

    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", "/tmp/a,/tmp/b")
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/a"), Path("/tmp/b")]


def test_sqlite_pragmas_are_configured():
    with engine.connect() as conn:
        assert str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
        assert int(conn.exec_driver_sql("PRAGMA synchronous").scalar()) == 1
        # P1-06 收尾：级联删除就位后外键强制开启
        assert int(conn.exec_driver_sql("PRAGMA foreign_keys").scalar()) == 1


def test_a05_auto_approve_requires_import_or_style_decision():
    # 没有 imported/style_decision 时，必须在访问 session 前返回；session=None 即验证守卫。
    runengine._auto_approve_a05(
        None, SimpleNamespace(id=1), SimpleNamespace(graph_json={"meta": {}}), {}, "/tmp")


# ---------- 交付门禁（F-DEL-1/2：快照文件硬校验 + script 一并比对） ----------

SNAP_SCHEMA = "filmflow.snapshot/1"


def _write_snapshot(tmp_path: Path, docs: dict) -> None:
    d = tmp_path / "runs" / "1" / "docs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "snapshot.json").write_text(
        json.dumps({"schema": SNAP_SCHEMA, "docs": docs}, ensure_ascii=False),
        encoding="utf-8")


def _doc(content: dict) -> dict:
    return {"version": 1, "hash": "x", "content": content}


class _FakeDoc:
    def __init__(self, content):
        self.content_json = content


def _seed_current(monkeypatch, current: dict[str, dict]):
    def get_doc(_session, _pid, kind):
        return _FakeDoc(current[kind]) if kind in current else None
    monkeypatch.setattr(delivery.docs_svc, "get_doc", get_doc)


def test_delivery_rejects_missing_snapshot_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(delivery.docs_svc, "get_doc", lambda *a: None)
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*快照"):
        delivery._ensure_run_documents_match(
            None, SimpleNamespace(id=1), tmp_path, 1)  # 没写快照文件


def test_delivery_rejects_broken_or_wrong_schema_snapshot(monkeypatch, tmp_path: Path):
    d = tmp_path / "runs" / "1" / "docs"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)
    (d / "snapshot.json").write_text(json.dumps({"schema": "filmflow.snapshot/9"}),
                                     encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_snapshot_without_timeline(monkeypatch, tmp_path: Path):
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script)})
    _seed_current(monkeypatch, {"script": script})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*timeline"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_timeline_drift(monkeypatch, tmp_path: Path):
    tl_snap = {"duration": 5.0}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(tl_snap)})
    _seed_current(monkeypatch, {"script": script, "timeline": {"duration": 5.5}})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_script_drift(monkeypatch, tmp_path: Path):
    """F-DEL-2：Run 后只改 script（不改 timeline）也必须拦——9:16/SRT/封面都用得到。"""
    tl = {"duration": 5.0}
    script_snap = {"title": "旧标题", "sentences": [{"text": "旧句子"}]}
    _write_snapshot(tmp_path, {"script": _doc(script_snap), "timeline": _doc(tl)})
    _seed_current(monkeypatch, {"script": {"title": "新标题", "sentences": [{"text": "新句子"}]},
                                "timeline": tl})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*script"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_profile_drift(monkeypatch, tmp_path: Path):
    tl = {"duration": 5.0}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(tl),
                               "profile": _doc({"fps": 24})})
    _seed_current(monkeypatch, {"script": script, "timeline": tl, "profile": {"fps": 30}})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*profile"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_accepts_matching_run_snapshot(monkeypatch, tmp_path: Path):
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)})
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    snap = delivery._ensure_run_documents_match(
        None, SimpleNamespace(id=1), tmp_path, 1)
    assert snap["schema"] == SNAP_SCHEMA


def test_delivery_title_prefers_snapshot_script(monkeypatch):
    """F-DEL-3：封面标题取快照 script；当前文档改成新标题也不影响本次交付。"""
    snap = {"docs": {"script": {"content": {"title": "快照标题",
                                            "sentences": [{"text": "旧句"}]}}}}

    class _Proj:
        id = 1
        root = "/tmp/whatever"

    def _boom(*_a):
        raise AssertionError("不应读取当前 script")
    monkeypatch.setattr(delivery.docs_svc, "doc_payload", _boom)
    assert delivery._title(None, _Proj(), snap) == "快照标题"


# ---------- P2-04 / P2-07：帧原子写与版本链上限 ----------

def test_frameserver_writes_frames_atomically(tmp_path: Path):
    """P2-04：/frame 落盘必须 tmp+replace——中途 kill 不留半张帧给 F03。"""
    import base64 as b64
    import urllib.request

    from app.engine.executors.pipeline import FrameServer

    root = tmp_path / "proj"
    (root / "out").mkdir(parents=True)
    png = b64.b64encode(b"\x89PNG\r\n\x1a\ntest").decode()
    # 8787 若被占用会复用既有服务（写别的 root）——先探测，占用则跳过断言 root 归属
    srv = FrameServer(str(root))
    srv.port = 8787
    try:
        srv.start()
    except OSError:
        pytest.skip("8787 已被占（另一进程 FrameServer），跨进程不互斥")
    try:
        body = ("data:image/png;base64," + png).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8787/frame?i=7", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
        f = root / "out" / "frames" / "0007.png"
        assert f.exists() and f.read_bytes() == b"\x89PNG\r\n\x1a\ntest"
        assert not list((root / "out" / "frames").glob("*.tmp")), "不得残留 .tmp"
    finally:
        srv.stop() if hasattr(srv, "stop") else None


def test_doc_revisions_capped_at_100(tmp_path: Path):
    """P2-07：连续保存 110 次，版本链只保留最近 100 条；版本号不受影响。"""
    from app.models import DocRevision
    from app.services.project_cleanup import delete_project

    root = tmp_path / "rev-cap"
    (root / "card").mkdir(parents=True)
    (root / "card" / "copy.txt").write_text("版本裁剪。", encoding="utf-8")
    with Session(engine) as session:
        from app.models import Project
        p = Project(name="rev-cap", root=str(root))
        session.add(p)
        session.commit()
        session.refresh(p)
        pid = p.id
        try:
            for i in range(110):
                docs.save_doc(session, pid, "script",
                              {"text": f"第 {i} 版内容。", "title": "t"}, i, "cap-test")
            doc = docs.get_doc(session, pid, "script")
            assert doc is not None and doc.version == 110
            n = len(session.exec(select(DocRevision).where(
                DocRevision.doc_id == doc.id)).all())
            assert n == 100, n
            # 最新版本仍在链上
            tops = docs.list_versions(session, doc)
            assert tops[0]["version"] == 110
        finally:
            session.rollback()
            delete_project(session, pid, remove_dir=False)
    import shutil
    shutil.rmtree(root, ignore_errors=True)
