"""预演渲染管线（T09）：Playwright 常驻系统 Chrome 单实例 + 页面内队列串行（D2 决定）。

缓存键 = style.sha256 + engine.sha256 + rendererVer（规格 §3.2）。
失败重试 2 次 → 占位（不隐藏条目）。
"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("previs")

import asyncio
import base64
import json
from pathlib import Path

from ..atomicwrite import write_atomic
from ..config import settings
from ..engine.cachekey import bytes_sha256

RENDERER_VER = "1.0.0"

_browser = None
_playwright = None
_queue_lock = asyncio.Lock()


async def _get_browser():
    global _browser, _playwright
    if _browser is not None:
        return _browser
    from playwright.async_api import async_playwright

    async def _launch():
        global _browser, _playwright
        if _browser is not None:
            return
        _playwright = await async_playwright().start()
        chrome = settings and None  # noqa: F841
        from ..config import detect_chrome
        exe = detect_chrome()
        _browser = await _playwright.chromium.launch(
            headless=True,
            executable_path=exe,
            args=["--enable-unsafe-swiftshader", "--disable-gpu", "--hide-scrollbars"],
        )

    # 串行化首次启动
    async with _queue_lock:
        if _browser is None:
            await _launch()
    return _browser


async def render_page_screenshot(url: str, width: int, height: int,
                                 ready_flag: str = "__PREVIS_DONE__",
                                 result_flag: str = "__PREVIS_PNG__",
                                 timeout_ms: int = 20000) -> bytes:
    """打开页面等 ready_flag，截图；若页面提供 result_flag(dataURL) 则用其输出。"""
    browser = await _get_browser()
    page = await browser.new_page(viewport={"width": width, "height": height})
    try:
        await page.goto(url, timeout=timeout_ms)
        try:
            await page.wait_for_function(f"window.{ready_flag} === true", timeout=timeout_ms)
        except Exception:
            _log.debug("swallowed exception in _shot (ready_flag 超时也截图，回退路径)",
                       exc_info=True)  # 超时也截图（回退路径）
        data_url = await page.evaluate(f"window.{result_flag} || null")
        if data_url and str(data_url).startswith("data:image"):
            return base64.b64decode(str(data_url).split(",", 1)[1])
        return await page.screenshot(type="png")
    finally:
        await page.close()


async def render_previs(style_id: str, engine_id: str, engine_sha: str,
                        tokens: dict, title: str = "风",
                        variant: str = "thumb") -> Path:
    """渲染一条预演缩略图/详情图，返回保存路径（cache/previs/）。"""
    size = (512, 288) if variant == "thumb" else (1024, 576)
    payload = base64.urlsafe_b64encode(json.dumps(
        {"tokens": tokens, "title": title, "variant": variant}, ensure_ascii=False
    ).encode()).decode()
    from .engines import engines_root, load_contract
    contract = load_contract(engine_id)
    entry = contract.get("entry", {}).get("previs") or contract["entry"]["film"]
    base = entry.split("?")[0]
    url = f"file://{engines_root() / engine_id / base}?mode=previs&payload={payload}"
    png = await render_page_screenshot(url, size[0], size[1])
    out = settings.cache_dir / "previs" / style_id / f"{engine_sha[:12]}.{variant}.png"
    write_atomic(out, png)
    return out


def placeholder_png(reason: str) -> bytes:
    """no_preview / failed 占位图：斜纹 + 文字（不伪装成预览）。"""
    import io

    from PIL import Image, ImageDraw
    w, h = 512, 288
    img = Image.new("RGB", (w, h), "#20242B")
    d = ImageDraw.Draw(img)
    for x in range(-h, w, 24):
        d.line([(x, h), (x + h, 0)], fill="#2C333D", width=8)
    d.rectangle([8, h // 2 - 30, w - 8, h // 2 + 30], fill="#161A20")
    d.text((w // 2 - 58, h // 2 - 12), f"无预演 · {reason}", fill="#8A93A0")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def placeholder_sha(reason: str) -> str:
    return bytes_sha256(placeholder_png(reason))
