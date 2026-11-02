"""数据库会话与建表。"""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .models import TABLES

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=20, max_overflow=40, pool_pre_ping=True, pool_recycle=1800,
)


def init_db() -> None:
    settings.ensure_dirs()
    # FTS5 trigram 虚表在 styles 表之后由 style_index 服务确保创建
    SQLModel.metadata.create_all(engine)
    _migrate_job_table()
    _record_schema_versions()


_JOB_COLUMNS = {
    "priority": "INTEGER DEFAULT 40",
    "run_id": "INTEGER",
    "parent_id": "INTEGER",
    "attempts": "INTEGER DEFAULT 0",
    "max_attempts": "INTEGER DEFAULT 3",
    "lease_until": "DATETIME",
    "heartbeat_at": "DATETIME",
    "started_at": "DATETIME",
    "updated_at": "DATETIME",
    "cancel_requested": "INTEGER DEFAULT 0",
    "progress": "REAL DEFAULT 0",
    "eta": "REAL",
    "error_code": "TEXT DEFAULT ''",
    "error_msg": "TEXT DEFAULT ''",
    "lease_owner": "TEXT DEFAULT ''",
}


def _migrate_job_table() -> None:
    """SQLite 幂等 ALTER：create_all 不会给旧 job 表补列（schema v3）。"""
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(job)").fetchall()
        if not rows:
            return
        cols = {r[1] for r in rows}
        for name, ddl in _JOB_COLUMNS.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE job ADD COLUMN {name} {ddl}")


def _record_schema_versions() -> None:
    """幂等记录已应用的 schema 版本；后续 ALTER 迁移在此追加。"""
    from .models import SchemaMigration
    with Session(engine) as session:
        for version in (1, 2, 3):
            if session.get(SchemaMigration, version) is None:
                session.add(SchemaMigration(version=version))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
