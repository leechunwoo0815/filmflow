"""API 路由聚合器（P3 #2 拆分，台账轮 20）：7 个域 router + 公共 deps。

本文件把 7 个域 router 的路由对象平铺进聚合器（FastAPI 0.162 嵌套 include 不解析，
见下注释）并再导出既有测试的导入面；
所有 handler 都在 routes_<域>.py 里，公共 helper 在 deps.py（monkeypatch 请打 deps 的名字）。
"""
from fastapi import APIRouter

from . import deps  # noqa: F401 -- 再导出
from .deps import (  # noqa: F401 -- 再导出（既有测试从这里 import/patch）
    _project_or_404,
    _project_profile,
    _require_creatable_project_root,
    _require_workspace_root,
    _review_viewed,
    _style_dto,
    audit,
)
from .routes_assets import (  # noqa: F401 -- 再导出（既有测试直调）
    assets_replace,
)
from .routes_assets import router as assets_router
from .routes_delivery import router as delivery_router
from .routes_docs import project_take_branch  # noqa: F401 -- 再导出（既有测试直调）
from .routes_docs import router as docs_router
from .routes_projects import (  # noqa: F401 -- 再导出（既有测试直调）
    _finish_saved_template_materialize,
    _materialize_saved_template,
    _resolve_template,
    _run_ids_of_project,
    series_from_template,
)
from .routes_projects import router as projects_router
from .routes_runs import (  # noqa: F401 -- 再导出（既有测试直调）
    _gate_precheck,
    gates_pending,
    run_retry,
)
from .routes_runs import router as runs_router
from .routes_styles import router as styles_router
from .routes_system import router as system_router
from .schemas import TakeBranchIn  # noqa: F401 -- 再导出（既有测试经 routes 访问）

router = APIRouter()
# FastAPI 0.162 的 include_router 是惰性 _IncludedRouter，且 app 层不解析嵌套（实测
# app.include_router(聚合器) 后全部 404）——直接把子 router 的路由对象平铺进聚合器，
# 子路由已带 /api 前缀，等价于拆分前的单文件结构。

for _child in (system_router, styles_router, projects_router, runs_router, delivery_router, assets_router, docs_router):
    router.routes.extend(_child.routes)
