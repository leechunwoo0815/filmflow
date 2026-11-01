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


def get_session():
    with Session(engine) as session:
        yield session
