"""本地开发边界：拒绝非本机 Host 与跨源写请求。"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ALLOWED_ORIGINS = frozenset({
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:7860",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:7860",
})


class LocalOriginMiddleware(BaseHTTPMiddleware):
    """浏览器跨源写请求直接拒绝；无 Origin 的本地 CLI/代理请求放行。"""

    async def dispatch(self, request: Request, call_next):
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin not in ALLOWED_ORIGINS:
                return JSONResponse(
                    {"detail": {"code": "E_ORIGIN_DENIED",
                                "message": "跨源写请求已拒绝（仅允许本机 UI）"}},
                    status_code=403,
                )
        return await call_next(request)
