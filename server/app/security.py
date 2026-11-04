"""本地开发边界：拒绝非本机 Host 与跨源写请求；文件响应只按白名单内联。"""
from __future__ import annotations

from pathlib import Path

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


# 可以安全内联的后缀 → 显式 Content-Type（绝不让 Starlette 按后缀嗅探出可执行文档）
INLINE_MEDIA: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".json": "application/json", ".css": "text/css; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
    ".srt": "text/plain; charset=utf-8", ".vtt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    # SVG 既是图片又可能带 <script>：保留 image/svg+xml（时间轴要能用），
    # 靠响应上的 CSP sandbox 让"直接打开这份 SVG"不执行脚本。
    ".svg": "image/svg+xml",
}

# 同源内联即被浏览器当文档解析/执行的后缀：一律落盘，不渲染
EXECUTABLE_SUFFIXES = frozenset({".html", ".htm", ".xhtml", ".xml", ".js", ".mjs"})

# `default-src 'none'` 关掉外链，`sandbox` 让 SVG/文档形态里的内联脚本不执行
FILE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
}


def file_response(path: Path, *, download_name: str | None = None):
    """按白名单出 Content-Type；可执行文档形态与未知后缀一律 attachment 下载。

    存储型脚本面的根因是"响应类型由文件后缀猜"：只要 `x.html`/未知后缀能被浏览器当文档解析，
    上传内容里的 `<script>` 就跑在 UI 源上。白名单之外强制 `application/octet-stream`
    + `Content-Disposition: attachment`，SVG 则靠 CSP sandbox 失去脚本执行能力。
    """
    from fastapi.responses import FileResponse

    suffix = path.suffix.lower()
    headers = dict(FILE_HEADERS)
    name = download_name or path.name
    media = INLINE_MEDIA.get(suffix)
    if suffix in EXECUTABLE_SUFFIXES or media is None:
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return FileResponse(path, media_type="application/octet-stream", headers=headers)
    headers["Content-Disposition"] = f'inline; filename="{name}"'
    return FileResponse(path, media_type=media, headers=headers)


# ---------- F01 帧服务（:8787）响应策略 ----------

# 数据根目录（项目文件、上传资产）里绝不该出现的"文档/脚本"形态：直接 404。
# /engine 例外——渲染器要跑引擎自己的 HTML+JS，给它加 sandbox 会直接把出片打挂。
FRAMESERVER_DATA_PREFIXES = ("/project/", "/global-assets/")
FRAMESERVER_DENY_SUFFIXES = frozenset({".html", ".htm", ".xhtml", ".xml", ".js", ".mjs"})


def frameserver_denied(url_path: str) -> bool:
    """帧服务是否拒绝该路径（数据根目录下的 HTML/JS 同源直开=存储型脚本执行）。"""
    p = (url_path or "").split("?", 1)[0].lower()
    if not p.startswith(FRAMESERVER_DATA_PREFIXES):
        return False
    return Path(p).suffix in FRAMESERVER_DENY_SUFFIXES


def frameserver_headers(url_path: str) -> dict[str, str]:
    """帧服务响应头：数据根目录加 nosniff + CSP sandbox，引擎目录只加 nosniff。"""
    p = (url_path or "").split("?", 1)[0].lower()
    headers = {"X-Content-Type-Options": "nosniff"}
    if p.startswith(FRAMESERVER_DATA_PREFIXES):
        headers["Content-Security-Policy"] = ("default-src 'none'; style-src 'unsafe-inline'; sandbox")
    return headers


