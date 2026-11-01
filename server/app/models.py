"""SQLModel 数据模型 —— 规格 §8.1 的 15 张表。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    root: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class Draft(SQLModel, table=True):
    """向导草稿（规格 §3.2 drafts 作用域）。step: 1..5。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "未命名项目"
    step: int = 1
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    materialized_run_id: Optional[int] = None


class Style(SQLModel, table=True):
    id: str = Field(primary_key=True)                       # 如 O88 / L28
    collection: str = Field(index=True)                     # 来源集名（O_奥斯卡98部…）
    family: str = Field(index=True)                         # 语义族主族 slug
    sub_families_json: list = Field(default_factory=list, sa_column=Column(JSON))
    name: str
    path: str
    sha256: str = Field(index=True)
    bytes: int = 0
    lines: int = 0
    has_cover: bool = False
    tokens_status: str = Field(default="incomplete")        # complete | incomplete
    preview_status: str = Field(default="no_preview")       # cover | previs | no_preview | failed
    engine_status: str = Field(default="unavailable")       # available | unavailable
    search_text: str = ""
    license: str = ""
    available: bool = True                                  # 文件是否存在
    indexed_at: datetime = Field(default_factory=utcnow)
    # 解析出的 tokens（palette/texture/screen/motion/type/composition）
    tokens_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    missing_fields: list = Field(default_factory=list, sa_column=Column(JSON))
    labeled: bool = False                                   # 人工补标完成


class StylePreview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    style_id: str = Field(foreign_key="style.id", index=True)
    variant: str                                            # thumb | detail
    path: str
    sha256: str
    engine_sha: str
    renderer_ver: str
    created_at: datetime = Field(default_factory=utcnow)
    __table_args__ = (Index("ix_preview_unique", "style_id", "variant", "engine_sha", "renderer_ver"),)


class StylePick(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, foreign_key="project.id")
    draft_id: Optional[int] = Field(default=None, foreign_key="draft.id")
    run_id: Optional[int] = Field(default=None, foreign_key="run.id")
    primary_id: str
    alternates_json: list = Field(default_factory=list, sa_column=Column(JSON))
    per_scene_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str = ""
    author: str = "local"
    created_at: datetime = Field(default_factory=utcnow)


class Workflow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str = "main"
    version: int = 1
    graph_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    status: str = Field(default="idle", index=True)         # idle|running|succeeded|failed|canceled|needs_changes
    caps_json: list = Field(default_factory=lambda: ["read", "write_plan", "logic_check"], sa_column=Column(JSON))
    params_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    parent_run_id: Optional[int] = None


class NodeRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_id: str = Field(index=True)
    status: str = Field(default="idle", index=True)         # idle|queued|running|succeeded|failed|canceled|blocked|stale|disabled|skipped
    cache_key: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    params_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    progress: float = 0.0
    message: str = ""
    __table_args__ = (Index("ix_node_run_unique", "run_id", "node_id"),)


class Artifact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_run_id: Optional[int] = Field(default=None, foreign_key="noderun.id")
    node_id: str = ""
    type: str                                               # PNG|MP4|JSON|WOFF2|CSS|ZIP|WAV
    path: str
    sha256: str = Field(index=True)
    bytes: int = 0
    meta_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Metric(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_run_id: Optional[int] = None
    node_id: str = ""
    key: str = Field(index=True)
    value: float
    unit: str = ""


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, index=True)
    node_id: Optional[str] = None
    type: str = Field(index=True)
    at: datetime = Field(default_factory=utcnow)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Approval(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    gate_id: str = Field(index=True)
    decision: str                                           # approved | rejected | stale
    authority: str = ""                                     # 技能动作名（记录用）
    policy: str = "inherit"                                 # inherit | reapprove
    content_hash: str = ""
    author: str = "local"
    note: str = ""
    checklist_json: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str = "local"
    action: str
    target: str
    before_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    after_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    """异步任务（预演渲染等 drafts 作用域工作）。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str                                               # previs | import | label ...
    status: str = Field(default="queued", index=True)       # queued|running|succeeded|failed
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None


class WorkflowVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    version: int
    graph_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


TABLES: list[type[SQLModel]] = [
    Project, Draft, Style, StylePreview, StylePick, Workflow, Run, NodeRun,
    Artifact, Metric, Event, Approval, AuditLog, Job, WorkflowVersion,
]

def table_dict(model: Any) -> dict:
    """SQLModel → dict（datetime 转字符串）。"""
    out = {}
    for k in model.__fields__:
        v = getattr(model, k)
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return out
