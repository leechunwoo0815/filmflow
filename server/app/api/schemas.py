"""P1-23：高风险写端点的请求模型（第一批：项目/文档/时间轴/资产/QA）。

约定：字段默认值与服务层现有取键方式保持一致，避免模型化本身改变行为；
多态端点（timeline ops）只声明共同字段并保留 extra，其它键原样透传。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    root: str = Field(min_length=1)


class DocSaveIn(BaseModel):
    content: dict[str, Any] = Field(default_factory=dict)
    base_version: int = 0
    author: str = "local"


class DocRestoreIn(BaseModel):
    version: int = Field(default=0, ge=0)
    author: str = "local"


class TimelineOpIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    op: str = Field(min_length=1, max_length=40)
    baseVersion: int | None = None


class AssetImportIn(BaseModel):
    scope: Literal["global", "project"] = "global"
    projectId: int | None = None
    filename: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=1)
    kind: str = ""
    name: str = ""
    tags: list[str] = Field(default_factory=list)
    license: dict[str, Any] = Field(default_factory=dict)
    author: str = ""


class AssetUpdateIn(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    license: dict[str, Any] | None = None
    archived: bool | None = None


class AssetReplaceIn(BaseModel):
    assetId: int = Field(ge=1)


class QaFixIn(BaseModel):
    issueId: str = Field(min_length=1)
    action: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)
    runId: int | None = None


class QaUndoIn(BaseModel):
    fixId: str = Field(min_length=1)


# ---------- P1-23 第二批：交付/预览/门禁/升档/任务卡/音频写端点 ----------

class PreviewStillIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    sceneId: str | None = None
    scene_id: str | None = None  # 旧客户端蛇形别名，保持兼容
    time: float | None = None
    profile: str = "draft"
    watermark: bool = True
    debounce: bool = True
    motion: bool = False


class PreviewSegmentIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    sceneId: str | None = None
    scene_id: str | None = None
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    profile: str = "draft"
    watermark: bool = True


class PreviewFilmIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    profile: str = "draft"
    watermark: bool = True


class DeliveryIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    runId: int | None = None
    run_id: int | None = None
    profile: str = "final"


class GateDecideIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    runId: int | None = None
    run_id: int | None = None  # 既有客户端两种键名都发
    decision: Literal["approved", "rejected"]
    note: str = ""
    author: str = "local"


class RunPromoteIn(BaseModel):
    takeName: str | None = None


class RenderProfileUpdateIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    profiles: dict[str, Any] | None = None


class TaskPutIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    task: dict[str, Any] = Field(default_factory=dict)
    author: str = "local"


class AudioLicenseSaveIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str = ""
    license: str = ""
    authorized: bool | None = None
    expires: str | None = None
    note: str = ""


class AudioMixSaveIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    preset: str | None = None
    targetLufs: float | None = None
    stems: dict[str, float] | None = None


class AudioAlignmentSaveIn(BaseModel):
    segments: list[dict[str, Any]] = Field(default_factory=list)
    author: str = "local"
