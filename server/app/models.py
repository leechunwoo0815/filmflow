"""SQLModel 数据模型 —— 规格 §8.1 的 15 张表 + R2/R3 扩展的 6 张
（StylePreview/WorkflowVersion/ProjectDoc/DocRevision/SchemaMigration/SceneState），
共 21 个 `table=True` 类。"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    root: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class Draft(SQLModel, table=True):
    """向导草稿（规格 §3.2 drafts 作用域）。step: 1..5。"""
    id: int | None = Field(default=None, primary_key=True)
    name: str = "未命名项目"
    step: int = 1
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    materialized_run_id: int | None = None


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
    id: int | None = Field(default=None, primary_key=True)
    style_id: str = Field(foreign_key="style.id", index=True)
    variant: str                                            # thumb | detail
    path: str
    sha256: str
    engine_sha: str
    renderer_ver: str
    created_at: datetime = Field(default_factory=utcnow)
    __table_args__ = (Index("ix_preview_unique", "style_id", "variant", "engine_sha", "renderer_ver"),)


class StylePick(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(default=None, foreign_key="project.id")
    draft_id: int | None = Field(default=None, foreign_key="draft.id")
    run_id: int | None = Field(default=None, foreign_key="run.id")
    primary_id: str
    alternates_json: list = Field(default_factory=list, sa_column=Column(JSON))
    per_scene_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str = ""
    author: str = "local"
    created_at: datetime = Field(default_factory=utcnow)


class Workflow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str = "main"
    version: int = 1
    graph_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    status: str = Field(default="idle", index=True)         # idle|running|succeeded|failed|canceled|needs_changes
    caps_json: list = Field(default_factory=lambda: ["read", "write_plan", "logic_check"], sa_column=Column(JSON))
    params_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    parent_run_id: int | None = None
    snapshot_sha: str = ""      # runs/<id>/docs/snapshot.json 的 sha256（交付门禁的库内封印）


class NodeRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_id: str = Field(index=True)
    status: str = Field(default="idle", index=True)         # idle|queued|running|succeeded|failed|canceled|blocked|stale|disabled|skipped
    cache_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    params_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    progress: float = 0.0
    message: str = ""
    __table_args__ = (Index("ix_node_run_unique", "run_id", "node_id"),)


class Artifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_run_id: int | None = Field(default=None, foreign_key="noderun.id")
    node_id: str = ""
    type: str                                               # PNG|MP4|JSON|WOFF2|CSS|ZIP|WAV
    path: str
    sha256: str = Field(index=True)
    bytes: int = 0
    meta_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Asset(SQLModel, table=True):
    """R3.0 FR-36 资产库：全局/项目作用域、sha 去重、使用处由 timeline 扫描。"""
    id: int | None = Field(default=None, primary_key=True)
    scope: str = Field(index=True)                          # global | project
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)
    kind: str = Field(index=True)                           # image | audio | font | video
    path: str
    sha256: str = Field(index=True)
    bytes: int = 0
    meta_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    tags_json: list = Field(default_factory=list, sa_column=Column(JSON))
    license_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    __table_args__ = (Index("ix_asset_scope_sha", "scope", "project_id", "sha256"),)


class Template(SQLModel, table=True):
    """FR-37 项目/场景模板；content_json 带版本化快照，项目用 template.lock.json 锁定。"""
    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)                           # project | scene
    name: str
    description: str = ""
    content_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Metric(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    node_run_id: int | None = None
    node_id: str = ""
    key: str = Field(index=True)
    value: float
    unit: str = ""


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, index=True)
    node_id: str | None = None
    type: str = Field(index=True)
    at: datetime = Field(default_factory=utcnow)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Approval(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
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
    id: int | None = Field(default=None, primary_key=True)
    actor: str = "local"
    action: str
    target: str
    before_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    after_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    """持久化异步任务（FR-29）：run / preview_segment / preview_film。"""
    id: int | None = Field(default=None, primary_key=True)
    kind: str                                               # run | preview_segment | preview_film
    status: str = Field(default="queued", index=True)       # queued|leased|running|succeeded|failed|canceled|retry_wait
    priority: int = Field(default=40, index=True)           # preview 100 / interactive 80 / batch 40 / delivery 20
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    run_id: int | None = Field(default=None, foreign_key="run.id", index=True)
    parent_id: int | None = None
    attempts: int = 0
    max_attempts: int = 3
    lease_until: datetime | None = None
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    cancel_requested: bool = False
    progress: float = 0.0
    eta: float | None = None
    error_code: str = ""
    error_msg: str = ""
    lease_owner: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class WorkflowVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    version: int
    graph_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class ProjectDoc(SQLModel, table=True):
    """可编辑文档事实源；Run 启动时快照到 runs/<id>/docs/（FR-25）。"""
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    kind: str = Field(index=True)                        # script|brief|timeline|profile|delivery|audio
    version: int = 1
    content_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    hash: str = ""
    author: str = "local"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    __table_args__ = (Index("ix_project_doc_unique", "project_id", "kind", unique=True),)


class DocRevision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="projectdoc.id", index=True)
    version: int
    content_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    diff_json: list = Field(default_factory=list, sa_column=Column(JSON))
    author: str = "local"
    created_at: datetime = Field(default_factory=utcnow)


class SchemaMigration(SQLModel, table=True):
    version: int = Field(primary_key=True)
    applied_at: datetime = Field(default_factory=utcnow)


class SceneState(SQLModel, table=True):
    """场景级渲染状态（FR-22）：F02 写，F03 聚合 QA。"""
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    scene_id: str = Field(index=True)
    hash: str = ""
    status: str = Field(default="idle", index=True)
    frame_start: int = 0
    frame_end: int = 0
    ms: int = 0
    qa_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    __table_args__ = (Index("ix_scene_state_unique", "run_id", "scene_id", unique=True),)


TABLES: list[type[SQLModel]] = [
    Project, Draft, Style, StylePreview, StylePick, Workflow, Run, NodeRun,
    Artifact, Asset, Template, Metric, Event, Approval, AuditLog, Job, WorkflowVersion,
    ProjectDoc, DocRevision, SchemaMigration, SceneState,
]

def table_dict(model: Any) -> dict:
    """SQLModel → dict（datetime 转字符串）。"""
    out = {}
    for k in model.__fields__:
        v = getattr(model, k)
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return out
