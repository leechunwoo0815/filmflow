"""数据库会话与建表；schema 迁移登记在 MIGRATIONS。
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .models import TABLES

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=20, max_overflow=40, pool_pre_ping=True, pool_recycle=1800,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """SQLite 连接级配置：WAL + 常规同步。

    外键强制需先补齐级联/删除顺序，暂不在本轮开启，避免把既有清理路径变成运行期故障。
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


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


def _add_columns_on(conn, table: str, columns: dict[str, str]) -> None:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        return
    existing = {r[1] for r in rows}
    for name, ddl in columns.items():
        if name not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate_job_columns(conn) -> None:
    _add_columns_on(conn, "job", _JOB_COLUMNS)


def _noop(conn) -> None:
    """已由 create_all 建表的历史版本，仅登记占位。"""


# 迁移登记处：version 单调递增，函数必须幂等（重跑安全）。
# 新加列/改表请在此追加一条，并在 server/tests/unit/test_migrations.py 补断言。
MIGRATIONS: list[tuple[int, str, Callable]] = [
    (1, "基线：project/workflow/run/noderun", _noop),
    (2, "文档与快照：projectdoc/docrevision/approval", _noop),
    (3, "job 持久队列列补齐", _migrate_job_columns),
]


def apply_migrations(migrations: list[tuple[int, str, Callable]], eng) -> list[int]:
    """按 version 升序执行未登记的迁移，返回本次应用的 version 列表。"""
    from .models import SchemaMigration
    applied: list[int] = []
    with Session(eng) as session:
        for version, _name, fn in sorted(migrations, key=lambda m: m[0]):
            if session.get(SchemaMigration, version) is not None:
                continue
            with eng.begin() as conn:
                fn(conn)
            session.add(SchemaMigration(version=version))
            session.commit()
            applied.append(version)
    return applied


def init_db() -> None:
    settings.ensure_dirs()
    # FTS5 trigram 虚表在 styles 表之后由 style_index 服务确保创建
    SQLModel.metadata.create_all(engine)
    apply_migrations(MIGRATIONS, engine)


def get_session():
    with Session(engine) as session:
        yield session
