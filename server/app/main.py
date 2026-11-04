"""FilmFlow API 入口。开发：uvicorn app.main:app --port 7860；发布：挂载 web 静态导出。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api.routes import router
from .config import settings
from .db import init_db
from .errors import ErrorCode
from .security import LocalOriginMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .logs import get, setup_logging
    setup_logging()
    log = get("main")
    init_db()
    _daily_backup(log)
    # FR-29：清孤儿进程/旧 profile；恢复被 kill -9 中断的 Run Job
    from sqlmodel import Session

    from .db import engine
    from .engine import runengine
    from .services import jobs as jobs_svc
    clean = jobs_svc.cleanup_orphans()
    with Session(engine) as session:
        recovered = jobs_svc.recover(session)
        expired = jobs_svc.expire_parked(session)
    for run_id in recovered["requeued"]:
        runengine.start_run(run_id)
    log.info("startup cleanup=%s recovered=%s expiredParked=%s",
             clean, recovered, expired)
    yield


def _daily_backup(log) -> None:
    """P2-34：启动时做一次当日 SQLite 在线备份（sqlite3 backup API，WAL 安全），
    保留最近 10 份。替代"想起来才手工 cp"——手工备份曾是唯一的备份方式。"""
    import sqlite3
    from datetime import datetime

    src = sqlite3.connect(str(settings.db_path))
    try:
        backup_dir = settings.home / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        dst = backup_dir / f"filmflow-auto-{stamp}.db"
        if dst.exists():
            return
        dst_tmp = backup_dir / f".filmflow-auto-{stamp}.db.tmp"
        with sqlite3.connect(str(dst_tmp)) as out:
            src.backup(out)
        dst_tmp.replace(dst)
        olds = sorted(backup_dir.glob("filmflow-auto-*.db"))
        for old in olds[:-10]:
            old.unlink(missing_ok=True)
        log.info("daily backup written: %s", dst)
    except Exception as e:                # 备份失败不挡启动，但要留痕
        log.warning("daily backup failed: %s", e)
    finally:
        src.close()


app = FastAPI(title="FilmFlow", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/openapi.json")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
app.add_middleware(LocalOriginMiddleware)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(_request, exc: RequestValidationError):
    """请求模型校验失败也要走 ApiError 信封。

    FastAPI 默认把 detail 返回成数组，前端 web/src/lib/api.ts 读的是 detail.message/code/details，
    于是用户只看到一个裸 "422"、错误原因和 details 全丢（判官复核 P1）。
    """
    errors = [{"loc": [str(part) for part in (e.get("loc") or [])],
               "type": str(e.get("type") or ""), "msg": str(e.get("msg") or "")}
              for e in (exc.errors() or [])][:20]
    first = errors[0] if errors else {"loc": [], "msg": ""}
    field = ".".join(p for p in first["loc"][1:] if p not in ("body", "query", "path")) or "请求体"
    return JSONResponse(
        status_code=422,
        content={"detail": {
            "code": ErrorCode.E_VALIDATION,
            "message": f"请求参数不合法：{field} — {first['msg']}" if first["msg"]
                       else f"请求参数不合法：{field}",
            "details": {"errors": errors}}})


# 发布形态：挂载 Next 静态导出（tech-plan D4）
WEB_OUT = Path(__file__).resolve().parents[2] / "web" / "out"
if WEB_OUT.exists():
    app.mount("/_assets", StaticFiles(directory=WEB_OUT / "_next"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(WEB_OUT / "index.html")

    @app.get("/{path:path}")
    async def spa(path: str):
        cand = WEB_OUT / path
        if cand.is_file():
            return FileResponse(cand)
        return FileResponse(WEB_OUT / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
