"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from ..db import engine, get_session
from ..engine import runengine as re_mod
from ..errors import ApiError, ErrorCode, not_found
from ..events import subscribe, unsubscribe
from ..models import (
    AuditLog,
    Job,
    Style,
    table_dict,
)
from ..services import engines as engines_svc
from ..services import environment as env_svc
from ..services import jobs as jobs_svc
from ..services import preview as preview_svc
from ..services import recommend as rec_svc
from . import deps
from .schemas import (
    LabelSubmitIn,
)

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"ok": True, "app": "FilmFlow", "version": "0.1.0"}


@router.get("/environment")
async def environment():
    try:
        return {**env_svc.assert_environment(), "ok": True}
    except ApiError as e:
        return {"ok": False, **e.detail}


@router.get("/engines")
async def engines_list():
    return {"engines": engines_svc.list_engines(), "matrix": engines_svc.family_engine_matrix()}


@router.post("/engines/{engine_id}/validate")
async def engines_validate(engine_id: str):
    engines_svc.load_contract(engine_id)   # 调用本身即校验（缺合同会抛）
    return {"engine_id": engine_id, "valid": True, "sha256": engines_svc.compute_pack_sha(engine_id)}


@router.get("/styles/random")
async def styles_random(seed: int = 0, session: Session = Depends(get_session)):
    return rec_svc.random_explainable(session, seed)


@router.get("/recommend")
async def recommend(script: str = "", seed: int = 0, constraints: str = "",
                    session: Session = Depends(get_session)):
    c = json.loads(constraints) if constraints else None
    return {"items": rec_svc.recommend(session, script, None, c, seed)}


# ---------- 补标队列（T13） ----------


@router.get("/labels/queue")
async def label_queue(session: Session = Depends(get_session)):
    rows = session.exec(select(Style)).all()
    q = [deps._style_dto(r) for r in rows if r.tokens_status != "complete" and not r.id.startswith("EX")]
    return {"total": len(q), "items": q}


@router.post("/labels/{style_id}")
async def label_submit(style_id: str, payload: LabelSubmitIn,
                       session: Session = Depends(get_session)):
    """人工补标：补 6 字段 + 语义族 → 解锁。"""
    st = session.get(Style, style_id)
    if not st:
        raise not_found("风格")
    body = payload.model_dump(exclude_unset=True)
    tokens = st.tokens_json or {}
    for k in ("palette", "texture", "screen", "motion", "type", "composition"):
        if k in body:
            tokens[k] = body[k]
    st.tokens_json = tokens
    flag_modified(st, "tokens_json")  # JSON 列原地改不标脏 → 补标会静默丢失
    st.missing_fields = [k for k in ("palette", "texture", "screen", "motion", "type", "composition")
                         if not tokens.get(k)]
    if body.get("family"):
        st.family = body["family"]
        from ..services import engines as eng
        st.engine_status = "available" if eng.engine_for_family(st.family) else "unavailable"
    st.labeled = bool(body.get("labeled", True))
    st.tokens_status = "complete" if not st.missing_fields else "incomplete"
    session.add(st)
    session.commit()
    deps.audit(session, "label.submit", style_id, after={"fields": list(body.keys())})
    return deps._style_dto(st)


# ---------- 项目 / 导入 ----------


@router.get("/jobs")
async def jobs_list(status: str | None = None, kind: str | None = None,
                    limit: int = 200, session: Session = Depends(get_session)):
    return {"items": [table_dict(j) for j in jobs_svc.list_jobs(session, status, kind, limit)]}


@router.get("/queue")
async def queue_summary(session: Session = Depends(get_session)):
    return jobs_svc.queue_summary(session)


@router.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    if j.kind == "run" and j.run_id:
        re_mod.cancel_run(j.run_id)
    elif j.kind.startswith("preview_"):
        pj = preview_svc.find_by_db_job(job_id)
        if pj:
            preview_svc.cancel_job(pj.id)
        else:
            jobs_svc.finish_job(session, job_id, "canceled", error_code="E_PREVIEW_CANCELED")
    else:
        jobs_svc.cancel_requested(session, job_id)
    session.expire_all()
    return table_dict(session.get(Job, job_id))


@router.post("/jobs/{job_id}/retry")
async def job_retry(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    if j.kind != "run" or not j.run_id:
        raise ApiError(ErrorCode.E_CONFLICT, "只有 Run job 支持重试", status=409)
    if j.status not in ("failed", "canceled"):
        raise ApiError(ErrorCode.E_CONFLICT, f"job 状态 {j.status} 不可重试", status=409)
    result = await re_mod.resume_run(j.run_id)
    with Session(engine) as s2:
        latest = jobs_svc.latest_run_job(s2, j.run_id)
    return {"runId": j.run_id, "requeued": result["requeued"],
            "jobId": latest.id if latest else None}


@router.get("/jobs/{job_id}")
async def job_get(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if not j:
        raise not_found("job")
    return table_dict(j)


@router.get("/audit")
async def audit_list(limit: int = 200, offset: int = 0,
                     session: Session = Depends(get_session)):
    # P2：limit 下推 SQL（此前全表 .all() 再内存切片；审计表会随使用无限增长）
    rows = session.exec(select(AuditLog).order_by(AuditLog.id.desc())
                        .offset(max(0, offset)).limit(max(0, min(limit, 1000))))  # type: ignore[arg-type]
    return {"items": [table_dict(r) for r in rows.all()]}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, request: Request):
    """SSE：唯一实时通道（规格 §9.1）。"""
    q = subscribe(run_id)

    async def gen():
        try:
            yield {"event": "connected", "data": json.dumps({"run_id": run_id})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": "message", "data": item}
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            unsubscribe(run_id, q)

    return EventSourceResponse(gen())


# ---------- 提升为当前 / 报告导出（M4 前置） ----------


@router.get("/notifications")
async def notifications_list():
    """通知列表（最近 50 条 + 未读数）。无推送无邮件，前端轮询。"""
    from ..services import notifications as notify_svc
    return notify_svc.load()


@router.post("/notifications/{notification_id}/read")
async def notification_read(notification_id: str):
    from ..services import notifications as notify_svc
    if not notify_svc.mark_read(notification_id):
        raise not_found("notification")
    return {"read": notification_id}


@router.post("/notifications/read-all")
async def notifications_read_all():
    from ..services import notifications as notify_svc
    return {"marked": notify_svc.mark_all_read()}


# ---------- FR-41 本地规则式创作辅助（纯本地规则，无外部请求） ----------

from pydantic import BaseModel as _BaseModel
from pydantic import Field as _Field


class SuggestIn(_BaseModel):
    text: str = _Field(min_length=1, max_length=5000)


@router.post("/projects/{project_id}/suggest")
async def suggest_scenes(project_id: int, payload: SuggestIn):
    """粘贴文案 → 断句 + 4–6 场建议（每场带理由/组件/镜头/读时校验）。草稿层：不改原文。"""
    from ..services import authoring
    _ = project_id          # 建议只依赖文本；挂在项目下是为了落草稿层与权限口径
    return authoring.suggest(payload.text)


@router.post("/authoring/suggest")
async def suggest_scenes_free(payload: SuggestIn):
    """同一份建议引擎的**无项目**入口（FR-41 前端要它）。

    为什么要有第二个入口：向导第 1 步用户还没有项目——`/projects/{id}/suggest` 在这里没有 id 可给。
    与其让前端骗一个 id 过去，或让建议引擎分叉成两份实现，不如两个路由指向同一个
    `authoring.suggest()`：规则表、断句口径、读时校验只有一份真源。
    """
    from ..services import authoring
    return authoring.suggest(payload.text)


@router.get("/authoring/rules")
async def authoring_rules():
    """规则表导出（PRD 行为 6：可导出）。"""
    from ..services import authoring
    return {"schema": "filmflow.authoring-rules/1",
            "readCps": authoring.READ_CPS,
            "breakHints": list(authoring.BREAK_HINTS),
            "componentHints": [{"keyword": k, "component": c}
                               for k, c in authoring.COMPONENT_HINTS],
            "cameraPresets": authoring.CAMERA_PRESETS,
            "targetScenes": authoring.TARGET_SCENES}

