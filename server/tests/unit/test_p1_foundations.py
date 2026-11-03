"""P1 基础治理：SQLite pragma、workspace roots 环境解析、A05 自动批准守卫。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.db import engine
from app.engine import runengine
from app.services import delivery


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


def test_a05_auto_approve_requires_import_or_style_decision():
    # 没有 imported/style_decision 时，必须在访问 session 前返回；session=None 即验证守卫。
    runengine._auto_approve_a05(
        None, SimpleNamespace(id=1), SimpleNamespace(graph_json={"meta": {}}), {}, "/tmp")


def test_delivery_rejects_current_timeline_drift(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(delivery, "ensure_run_snapshot",
                        lambda *_: {"docs": {"timeline": {"content": {"duration": 5.0}}}})
    monkeypatch.setattr(delivery.docs_svc, "doc_payload",
                        lambda *_: {"content": {"duration": 5.5}})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_accepts_matching_run_snapshot(monkeypatch, tmp_path: Path):
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    monkeypatch.setattr(delivery, "ensure_run_snapshot",
                        lambda *_: {"docs": {"timeline": {"content": timeline}}})
    monkeypatch.setattr(delivery.docs_svc, "doc_payload", lambda *_: {"content": timeline})
    delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)
