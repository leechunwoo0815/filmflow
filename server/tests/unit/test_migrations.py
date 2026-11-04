"""P1-07：schema 迁移登记处——按版本升序执行、只执行一次、能给旧表补列。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import MIGRATIONS, _add_columns_on, apply_migrations
from app.models import SchemaMigration


@pytest.fixture()
def tmp_engine(tmp_path: Path):
    eng = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


def test_registry_is_ordered_and_applies_once(tmp_engine):
    versions = [v for v, _name, _fn in MIGRATIONS]
    assert versions == sorted(versions), "迁移版本必须单调递增"
    assert len(set(versions)) == len(versions), "迁移版本不能重复"
    assert apply_migrations(MIGRATIONS, tmp_engine) == versions
    assert apply_migrations(MIGRATIONS, tmp_engine) == []
    with Session(tmp_engine) as session:
        recorded = {m.version for m in session.exec(select(SchemaMigration)).all()}
    assert recorded == set(versions)


def test_migration_adds_missing_column_idempotently(tmp_engine):
    with tmp_engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE widget (id INTEGER PRIMARY KEY)")
    calls: list[int] = []

    def add_label(conn) -> None:
        calls.append(1)
        _add_columns_on(conn, "widget", {"label": "TEXT DEFAULT ''"})

    assert apply_migrations([(10, "widget.label", add_label)], tmp_engine) == [10]
    assert apply_migrations([(10, "widget.label", add_label)], tmp_engine) == []
    assert len(calls) == 1, "同一版本不得重复执行"
    with tmp_engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(widget)").fetchall()}
    assert "label" in cols


def test_job_table_has_queue_columns_after_migrations(tmp_engine):
    apply_migrations(MIGRATIONS, tmp_engine)
    with tmp_engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(job)").fetchall()}
    assert {"priority", "lease_until", "heartbeat_at", "cancel_requested", "error_code"} <= cols


def test_p2_09_unique_indexes_are_really_unique(tmp_engine):
    """P2-09：三个名字带 unique 的索引必须真是 UNIQUE（迁移 5 在旧库上重建）。"""
    apply_migrations(MIGRATIONS, tmp_engine)
    with tmp_engine.begin() as conn:
        for name in ("ix_preview_unique", "ix_node_run_unique", "ix_asset_scope_sha"):
            row = conn.exec_driver_sql(f"PRAGMA index_info({name})").fetchall()
            assert row, f"{name} 不存在"
    from app.models import NodeRun
    with Session(tmp_engine) as session:
        session.add(NodeRun(run_id=501, node_id="A01", status="idle"))
        session.commit()
        session.add(NodeRun(run_id=501, node_id="A01", status="idle"))
        try:
            session.commit()
            raise AssertionError("noderun 的 (run_id,node_id) 唯一索引没有生效")
        except Exception as e:
            assert "UNIQUE" in str(e).upper(), e
            session.rollback()
