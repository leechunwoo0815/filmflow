"""P1-23：高风险写端点的请求模型（第一批：项目/文档/时间轴/资产/QA）。

约定：字段默认值与服务层现有取键方式保持一致，避免模型化本身改变行为；
多态端点（timeline ops）只声明共同字段并保留 extra，其它键原样透传。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..services.audio import MAX_BYTES as _AUDIO_MAX_BYTES
from ..services.token_parser import HEX_RE


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
    checklist: list[Any] = Field(default_factory=list)


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


# ---------- P1-23 第三批：标注/导入/向导/模板/编排/音频/审片/Take ----------
# 判官 §三-10：写端点不许再收裸 dict。语义对齐原则——
# * **PATCH 语义**（服务层用 `if key in payload` 区分"没传"和"传了 null"）一律用
#   `model_dump(exclude_unset=True)` 交给服务，模型本身只声明类型，不改键存在性。
# * **透传语义**（服务读很多键，如批注/草稿 payload）保留 `extra="allow"`，
#   未声明的键原样下发，模型化本身不丢数据。
# * 长度上限是**边界防护**（大 body 先进内存再被服务层拒），不是业务规则；
#   业务规则仍留在服务层，好错误信息（400 E_VALIDATION + 中文理由）不变。

AUDIO_KINDS = Literal["voice", "music", "sfx"]
# 与服务层 audio.MAX_BYTES（落盘 200MB）同源：base64 上限 = 4/3·原始上限 + 前缀余量。
# 单测 test_request_models_batch3 会钉住这个换算，改 MAX_BYTES 不会让这里悄悄失真。
_AUDIO_B64_MAX = (4 * (_AUDIO_MAX_BYTES // 3)) + 4096


class LabelSubmitIn(BaseModel):
    """人工补标：这 6 个 token **会直接进着色器**（preview.py 把 tokens_json 当 visual 用），
    所以 palette 必须是 hex 色值、screen 必须是数值——历史上写进「高对比」这类自由文本
    会让 WebGL 编译期拿到 NaN，预览只剩一个 500。其它 token 是描述性标签。
    键存在性由 `model_dump(exclude_unset=True)` 保留（PATCH 语义）。"""

    model_config = ConfigDict(extra="allow")
    palette: list[str] | None = Field(default=None, max_length=8)
    texture: list[str] | None = Field(default=None, max_length=12)
    screen: dict[str, float] | None = None
    motion: dict[str, Any] | None = None
    type: list[str] | None = Field(default=None, max_length=12)
    composition: list[str] | None = Field(default=None, max_length=12)
    family: str = ""
    labeled: bool | None = None

    @field_validator("palette")
    @classmethod
    def _palette_must_be_hex(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out = []
        for item in v:
            s = str(item).strip()
            if not HEX_RE.fullmatch(s):
                raise ValueError("调色必须是 #RGB 或 #RRGGBB 十六进制色值")
            out.append(s)
        return out


class ProjectImportIn(BaseModel):
    root: str = Field(min_length=1, max_length=600)
    name: str = Field(default="", max_length=120)


class DraftCreateIn(BaseModel):
    name: str = Field(default="未命名项目", max_length=120)
    step: int = Field(default=1, ge=1, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)


class DraftPatchIn(BaseModel):
    step: int | None = Field(default=None, ge=1, le=5)
    payload: dict[str, Any] | None = None


class TemplateSaveIn(BaseModel):
    name: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=500)
    copy_text: str | None = Field(default=None, max_length=20000, alias="copy")


class TemplateVersionIn(BaseModel):
    projectId: int = Field(ge=1)
    name: str = Field(default="", max_length=80)
    description: str | None = Field(default=None, max_length=500)
    copy_text: str | None = Field(default=None, max_length=20000, alias="copy")


class SceneTemplateSaveIn(BaseModel):
    name: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=500)
    keepText: bool = False


class SceneTemplateApplyIn(BaseModel):
    templateId: str = Field(min_length=1, max_length=120)
    index: int | None = Field(default=None, ge=0)
    afterSceneId: str | None = Field(default=None, max_length=60)
    baseVersion: int | None = None
    author: str = Field(default="scene-template", max_length=60)


class TemplateUpgradeIn(BaseModel):
    templateId: str = Field(min_length=1, max_length=120)
    confirm: bool = False


class SeriesCreateIn(BaseModel):
    """items 允许字符串或对象（服务层归一）；空/超过 5 项的业务规则留在服务层，
    因为那里能给出「批量 CSV 属 R4 FR-46」这种可解释理由。"""

    templateId: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=120)
    items: list[Any] = Field(default_factory=list)


class FromTemplateIn(BaseModel):
    templateId: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=120)
    variables: dict[str, Any] = Field(default_factory=dict)
    copy_text: str | None = Field(default=None, max_length=20000, alias="copy")


class ExampleCloneIn(BaseModel):
    name: str = Field(default="", max_length=120)


class WorkflowCreateIn(BaseModel):
    projectId: int = Field(ge=1)
    graph: dict[str, Any] = Field(default_factory=dict)


class WorkflowPutIn(BaseModel):
    graph: dict[str, Any] | None = None


class RunCreateIn(BaseModel):
    workflowId: int = Field(ge=1)
    params: dict[str, Any] = Field(default_factory=dict)


class FontCheckIn(BaseModel):
    text: str = Field(default="", max_length=20000)


class AudioUploadIn(BaseModel):
    """口播/音乐上传：后缀与大小在服务层已校验，这里补**入口**上限，
    免得 10GB base64 先解进内存再被 200MB 规则拒。"""

    filename: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=1, max_length=_AUDIO_B64_MAX)
    kind: AUDIO_KINDS = "voice"
    sceneId: str = Field(default="", max_length=60)
    name: str = Field(default="", max_length=120)


class AudioPrimaryIn(BaseModel):
    takeId: str = Field(min_length=1, max_length=40)


class AudioScenePrimaryIn(BaseModel):
    sceneId: str = Field(min_length=1, max_length=60)
    takeId: str = Field(default="", max_length=40)


class AudioProcessIn(BaseModel):
    """处理开关：`extra="forbid"`——拼错的效果键（如 pitch）不再被静默忽略。"""

    model_config = ConfigDict(extra="forbid")
    highpass: bool = False
    denoise: bool = False
    deesser: bool = False
    eq: bool = False
    trim: bool = False
    normalize: bool = False


class AudioMarkersIn(BaseModel):
    markers: list[dict[str, Any]] = Field(default_factory=list)
    onsets: list[dict[str, Any]] | None = None


class ReviewCommentAddIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    body: str = Field(default="", max_length=4000)
    kind: str = Field(default="text", max_length=20)
    category: str = Field(default="suggest", max_length=20)
    frame: int = Field(default=0, ge=0)
    time: float = Field(default=0, ge=0)
    sceneId: str = Field(default="", max_length=60)
    layerId: str = Field(default="", max_length=60)
    author: str = Field(default="local", max_length=60)
    assignee: str = Field(default="", max_length=60)
    geometry: dict[str, Any] = Field(default_factory=dict)


class ReviewCommentPatchIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    body: str | None = None
    category: str | None = None
    status: str | None = None
    assignee: str | None = None
    reply: str | None = None
    author: str | None = None


class ReviewDecideIn(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    sceneId: str = Field(default="", max_length=60)
    author: str = Field(default="local", max_length=60)
    note: str = Field(default="", max_length=2000)


class ReviewImportIn(BaseModel):
    """审片 JSON 导入：既接受 `{review:{comments:[…]}}` 也接受裸 `{comments:[…]}`，
    故保留 extra。comments 的结构校验在 review_comments.import_json（逐条计数）。"""

    model_config = ConfigDict(extra="allow")
    review: dict[str, Any] | None = None


class ReviewPackageIn(BaseModel):
    videoId: int | None = Field(default=None, ge=1)


class StillsViewedIn(BaseModel):
    """D03「已查看」登记：键名双写（scene/sceneId、time/t），值形状由前端决定。"""

    model_config = ConfigDict(extra="allow")
    scene: str | None = None
    sceneId: str | None = None
    time: float | None = None
    t: float | None = None
    region: Any = None
    zoom: Any = None
    at: str | None = None


class TakeUpdateIn(BaseModel):
    name: str | None = None
    score: int | None = None
    note: str | None = None
    hidden: bool | None = None


class TakeBranchIn(BaseModel):
    author: str = Field(default="take-branch", max_length=60)


class AdoptSceneIn(BaseModel):
    sceneId: str = Field(min_length=1, max_length=60)


class TimelineRebuildIn(BaseModel):
    base_version: int | None = None
    author: str = Field(default="local", max_length=60)
