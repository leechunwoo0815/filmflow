"""P1-23：高风险写端点的请求模型（第一批：项目/文档/时间轴/资产/QA）。

约定：字段默认值与服务层现有取键方式保持一致，避免模型化本身改变行为；
多态端点（timeline ops）只声明共同字段并保留 extra，其它键原样透传。
"""
from __future__ import annotations

from typing import Any, Literal, Optional

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
    baseVersion: Optional[int] = None


class AssetImportIn(BaseModel):
    scope: Literal["global", "project"] = "global"
    projectId: Optional[int] = None
    filename: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=1)
    kind: str = ""
    name: str = ""
    tags: list[str] = Field(default_factory=list)
    license: dict[str, Any] = Field(default_factory=dict)
    author: str = ""


class AssetUpdateIn(BaseModel):
    name: Optional[str] = None
    tags: Optional[list[str]] = None
    license: Optional[dict[str, Any]] = None
    archived: Optional[bool] = None


class AssetReplaceIn(BaseModel):
    assetId: int = Field(ge=1)


class QaFixIn(BaseModel):
    issueId: str = Field(min_length=1)
    action: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)
    runId: Optional[int] = None


class QaUndoIn(BaseModel):
    fixId: str = Field(min_length=1)
