"""FilmFlow API 入口。开发：uvicorn app.main:app --port 7860；发布：挂载 web 静态导出。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FilmFlow", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/openapi.json")
app.include_router(router)


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
