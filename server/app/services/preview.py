"""PreviewService（FR-23）：单帧/片段/整片预览。

- F02 运行时：CDP 附加到同一个 Chrome 的临时 page（不新开浏览器）。
- F02 空闲时：按 chrome-queue 启动临时 Chrome，渲染完关闭。
- 预览只写 out/preview 与 ~/.filmflow/cache/preview，绝不写 out/frames/、不产生 Artifact/Approval。
- 门前预览统一加 PREVIEW 水印；缓存键含 scene/film hash + time + profile + 渲染器版本。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from ..config import detect_chrome, settings
from ..errors import ApiError, ErrorCode, not_found
from ..models import Artifact, Project, Run, Style, Workflow
from . import engines as engines_svc
from . import project_docs as docs_svc
from ..engine.cachekey import file_sha256
from ..engine.render_manifest import scene_hash
from ..engine.scene.canonical import content_hash
from ..engine.scene.compiler import compile_scene

RENDERER_VER = "preview-1.4.0"  # 单帧 PNG；片段 full-res JPEG→Lanczos
PREVIEW_PROFILES = {
    "draft": {"width": 960, "height": 540, "fps": 12, "crf": 28, "preset": "ultrafast"},
    "review": {"width": 1280, "height": 720, "fps": 24, "crf": 22, "preset": "fast"},
    "final": {"width": 1920, "height": 1080, "fps": 24, "crf": 17, "preset": "medium"},
}
CACHE_LIMIT_BYTES = 500 * 1024 * 1024
HTML_PATH = Path(__file__).resolve().parents[3] / "engines/riso/entry/film_spec.html"

_STILL_GEN: dict[tuple[int, str], int] = {}
_INTERACTIVE = 0
_PAGE_SEM = asyncio.Semaphore(2)
_STATS = {"hits": 0, "misses": 0, "renders": 0}
_JOBS: dict[str, "PreviewJob"] = {}


# ---------- 上下文 ----------

@dataclass
class PreviewContext:
    project_id: int
    root: Path
    profile: dict
    script: dict
    timeline: dict
    scenes: list[dict]
    transitions: list[dict]
    tokens: dict
    tokens_sha: str
    engine_id: str
    engine_sha: str
    font_css: str
    font_sha: str
    imported: bool
    run_id: int | None = None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_profile(profile: dict) -> dict:
    fps = int(profile.get("fps") or 24)
    duration = float(profile.get("duration") or 0)
    frames = int(profile.get("frames") or round(duration * fps))
    return {"width": int(profile.get("width") or 1920), "height": int(profile.get("height") or 1080),
            "fps": fps, "duration": duration, "frames": frames}


def _latest_run(session: Session, project_id: int) -> Run | None:
    wf = session.exec(select(Workflow).where(Workflow.project_id == project_id)).first()  # type: ignore[arg-type,union-attr]
    if not wf:
        return None
    return session.exec(select(Run).where(Run.workflow_id == wf.id)
                        .order_by(Run.id.desc())).first()  # type: ignore[arg-type,union-attr]


def _artifact(session: Session, run: Run | None, node_id: str, type_: str | None = None) -> Artifact | None:
    if run is None:
        return None
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == run.id, Artifact.node_id == node_id)).all()  # type: ignore[arg-type]
    for r in reversed(rows):
        if type_ and r.type != type_:
            continue
        if Path(r.path).exists():
            return r
    return None


def _artifact_json(session: Session, run: Run | None, node_id: str) -> dict:
    row = _artifact(session, run, node_id, "JSON")
    return _read_json(Path(row.path)) if row else {}


def _tokens_from_style(session: Session, root: Path) -> tuple[dict, str]:
    decision = _read_json(root / "card/style_decision.json")
    style = session.get(Style, decision.get("primary")) if decision.get("primary") else None
    if not style:
        return {}, ""
    visual = dict(style.tokens_json or {})
    tokens = {"visual": visual, "layout": {},
              "type_spec": {"family": "Noto Sans SC", "title_range": [72, 120],
                            "line_height": 1.35, "letter_spacing": 0}}
    return tokens, style.family


def _resolve_engine(session: Session, root: Path, build: dict) -> tuple[str, str]:
    engine_id = build.get("engine_id") or ""
    if not engine_id:
        decision = _read_json(root / "card/style_decision.json")
        style = session.get(Style, decision.get("primary")) if decision.get("primary") else None
        eng = engines_svc.engine_for_family(style.family) if style else None
        engine_id = (eng or {}).get("engine_id") or ""
    if not engine_id:
        raise ApiError(ErrorCode.E_ENGINE_UNAVAILABLE, "无法确定预览引擎（先选择主风格）")
    sha = build.get("sha256") or engines_svc.compute_pack_sha(engine_id)
    return engine_id, sha


def _transition_type(text) -> str:
    t = str(text or "")
    for key, value in (("硬切", "cut"), ("溶解", "dissolve"), ("擦", "wipe"), ("推", "push"),
                       ("滑", "paper-slide"), ("墨", "ink-bleed"), ("故障", "glitch"),
                       ("匹配", "match-shape")):
        if key in t:
            return value
    return "match-shape"


def _default_transitions(scenes: list[dict]) -> list[dict]:
    out = []
    for a, b in zip(scenes, scenes[1:]):
        start = float(b.get("start", 0))
        out.append({"from": a["id"], "to": b["id"], "at": start,
                    "atFrame": round(start * float(b.get("fps", 24) or 24)),
                    "type": _transition_type(b.get("transition")),
                    "duration": float(b.get("transition_duration", 0.5) or 0.5),
                    "direction": "left", "params": {},
                    "note": b.get("transition") or f"{a['id']}→{b['id']} 默认接缝"})
    return out


def resolve_context(session: Session, project_id: int) -> PreviewContext:
    project = session.get(Project, project_id)
    if not project:
        raise not_found("项目")
    root = Path(project.root).resolve()
    roots = [w.resolve() for w in settings.workspace_roots]
    if not any(root == w or root.is_relative_to(w) for w in roots):
        raise ApiError(ErrorCode.E_VALIDATION, f"项目根必须在白名单内：{settings.workspace_roots}")
    imported = docs_svc.is_imported(session, project_id)
    script = docs_svc.doc_payload(session, project_id, str(root), "script")["content"]
    timeline = docs_svc.doc_payload(session, project_id, str(root), "timeline")["content"]
    raw_profile = docs_svc.doc_payload(session, project_id, str(root), "profile")["content"]
    profile = _normalize_profile(raw_profile)
    scenes = [s for s in (timeline.get("scenes") or []) if s.get("id")]
    if not scenes:
        raise ApiError(ErrorCode.E_VALIDATION, "时间轴没有场景，无法预览")
    run = _latest_run(session, project_id)
    build = _artifact_json(session, run, "C01")
    tokens = _artifact_json(session, run, "C05")
    if not tokens:
        tokens = _read_json(root / "card/tokens.lock.json")
    if not tokens:
        tokens, _family = _tokens_from_style(session, root)
    engine_id, engine_sha = _resolve_engine(session, root, build)
    font_css = ""
    for rel in ("fonts/embed.css", "fonts/noto-sans-sc/embed.css"):
        p = root / rel
        if p.exists():
            font_css = p.read_text(encoding="utf-8", errors="replace")
            break
    if not font_css:
        c04 = _artifact(session, run, "C04", "CSS")
        if c04:
            font_css = Path(c04.path).read_text(encoding="utf-8", errors="replace")
    font_sha = ""
    c02 = _artifact(session, run, "C02", "TXT")
    if c02:
        font_sha = c02.sha256
    else:
        ttf = root / "fonts/src/NotoSansSC[wght].ttf"
        if ttf.exists():
            font_sha = file_sha256(str(ttf))
        elif font_css:
            font_sha = content_hash(font_css)
    return PreviewContext(
        project_id=project_id, root=root, profile=profile, script=script, timeline=timeline,
        scenes=scenes, transitions=_default_transitions(scenes), tokens=tokens,
        tokens_sha=content_hash(tokens), engine_id=engine_id, engine_sha=engine_sha,
        font_css=font_css, font_sha=font_sha, imported=imported,
        run_id=run.id if run else None)


# ---------- 程序 / payload ----------

def _scene_by_id(ctx: PreviewContext, scene_id: str) -> dict:
    for s in ctx.scenes:
        if s["id"] == scene_id:
            return s
    raise ApiError(ErrorCode.E_NOT_FOUND, f"场景 {scene_id} 不存在", status=404)


def _camera(scene: dict, profile: dict) -> dict:
    start, end = float(scene.get("start", 0)), float(scene.get("end", 0))
    return {"scene": scene["id"], "zoom": [[start, 1.0], [end, 1.03]],
            "pan": [[start, 0], [end, 0]],
            "anchor": [int(profile["width"]) / 2, int(profile["height"]) / 2],
            "note": scene.get("camera", "默认缓推 3%")}


def build_programs(ctx: PreviewContext, motion: bool, scene_id: str | None = None) -> list[dict]:
    picked = [s for s in ctx.scenes if scene_id is None or s["id"] == scene_id]
    out = []
    for s in picked:
        prog = compile_scene(s, ctx.script, ctx.tokens, ctx.profile,
                             camera=_camera(s, ctx.profile) if motion else None, motion=motion)
        out.append({"id": s["id"], "start": float(s.get("start", 0)),
                    "end": float(s.get("end", 0)), "program": prog})
    return out


def _programs_sha(programs: list[dict]) -> str:
    return content_hash([p["program"]["program_sha"] for p in programs])


def _output_profile(name: str) -> dict:
    prof = PREVIEW_PROFILES.get(name)
    if not prof:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知预览档位：{name}")
    return prof


def _clamp_time(scene: dict, t: float | None, fps: int) -> float:
    start, end = float(scene.get("start", 0)), float(scene.get("end", 0))
    if t is None:
        t = start + max(0.8, (end - start) * 0.5)
    return round(min(max(float(t), start), max(start, end - 1.0 / max(fps, 1))), 4)


# ---------- 水印 / 缓存 ----------

def resize_png(data: bytes, width: int, height: int) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.size == (width, height):
        return data
    img = img.resize((width, height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def finish_png(data: bytes, width: int, height: int, watermark: bool) -> bytes:
    return watermark_png(resize_png(data, width, height), watermark)


def _watermark_font(size: int):
    from PIL import ImageFont
    for p in (settings.cache_dir / "fonts/NotoSansSC[wght].ttf",
              Path.home() / "Library/Fonts/NotoSansSC[wght].ttf"):
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                break
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def watermark_png(data: bytes, enabled: bool = True, label: str = "PREVIEW") -> bytes:
    if not enabled:
        return data
    from PIL import Image, ImageDraw, PngImagePlugin
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    scale = max(0.5, img.width / 1920)
    size = max(14, int(30 * scale))
    font = _watermark_font(size)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    box = draw.textbbox((0, 0), label, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = max(6, int(12 * scale))
    margin = max(12, int(40 * scale))
    x = img.width - tw - margin - pad * 2
    y = margin
    draw.rounded_rectangle([x - pad, y - pad, x + tw + pad, y + th + pad],
                           radius=max(4, int(6 * scale)), fill=(0, 0, 0, 150))
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 235))
    out = Image.alpha_composite(img, overlay).convert("RGB")
    info = PngImagePlugin.PngInfo()
    info.add_text("ff_preview", "1")
    info.add_text("ff_renderer", RENDERER_VER)
    buf = io.BytesIO()
    out.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


class PreviewCache:
    def __init__(self, project_id: int, limit_bytes: int = CACHE_LIMIT_BYTES,
                 cache_root: Path | None = None):
        self.root = (cache_root or (settings.cache_dir / "preview")) / str(project_id)
        self.limit_bytes = limit_bytes

    def path(self, group: str, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", group)[:80] or "x"
        return self.root / safe / f"{key}.png"

    def get(self, group: str, key: str) -> bytes | None:
        p = self.path(group, key)
        try:
            data = p.read_bytes()
            p.touch()
            _STATS["hits"] += 1
            return data
        except OSError:
            _STATS["misses"] += 1
            return None

    def put(self, group: str, key: str, data: bytes) -> Path:
        p = self.path(group, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
        return p

    def evict(self) -> None:
        if not self.root.exists():
            return
        files = [(p.stat().st_mtime, p.stat().st_size, p) for p in self.root.rglob("*.png")]
        total = sum(f[1] for f in files)
        if total <= self.limit_bytes:
            return
        for _mtime, size, p in sorted(files):
            if total <= self.limit_bytes:
                break
            try:
                p.unlink()
                total -= size
            except OSError:
                pass

    def stats(self) -> dict:
        files = list(self.root.rglob("*.png")) if self.root.exists() else []
        return {"projectId": int(self.root.name), "files": len(files),
                "bytes": sum(p.stat().st_size for p in files),
                "limitBytes": self.limit_bytes, **_STATS}


# ---------- 渲染器（同一 Chrome / 临时 Chrome） ----------

def _cdp_ok(port: int = 9222) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.4) as r:
            return r.status == 200
    except Exception:
        return False


async def _wait_cdp(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_cdp_ok, port):
            return True
        await asyncio.sleep(0.15)
    return False


class PreviewRenderer:
    """一次预览渲染会话；attached=复用 F02 Chrome，否则独占 chrome-queue 启动临时 Chrome。"""

    def __init__(self, debug_port: int = 9222):
        self.debug_port = debug_port
        self._pw = None
        self._browser = None
        self._page = None
        self._attached = False
        self._held_lock = False
        self.mode = "owned"
        self.holder = f"preview:{uuid.uuid4().hex[:8]}"

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        from ..engine.runengine import LOCK_MANAGER
        f02_active = any(h.endswith(":F02") for h in LOCK_MANAGER.holders("chrome-queue"))
        self._pw = await async_playwright().start()
        try:
            if f02_active:
                if not await _wait_cdp(self.debug_port, 3.0):
                    raise ApiError(ErrorCode.E_PREVIEW_BUSY,
                                   "批量渲染中，预览稍后自动刷新",
                                   status=429, details={"retry_after_ms": 1500})
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{self.debug_port}")
                self._attached = True
                self.mode = "attached"
                contexts = self._browser.contexts
                ctx = contexts[0] if contexts else await self._browser.new_context()
            else:
                try:
                    await asyncio.wait_for(
                        LOCK_MANAGER.acquire("chrome-queue", self.holder), timeout=3.0)
                    self._held_lock = True
                except asyncio.TimeoutError:
                    raise ApiError(ErrorCode.E_PREVIEW_BUSY, "Chrome 忙，预览稍后自动刷新",
                                   status=429, details={"retry_after_ms": 1500})
                chrome = detect_chrome()
                if not chrome:
                    raise ApiError(ErrorCode.E_ENV_MISSING, "未找到 Chrome")
                self._browser = await self._pw.chromium.launch(
                    executable_path=chrome, headless=True,
                    args=["--enable-unsafe-swiftshader", "--disable-gpu", "--hide-scrollbars"])
                ctx = await self._browser.new_context(viewport={"width": 1920, "height": 1080})
            self._page = await ctx.new_page()
            await self._page.goto(HTML_PATH.as_uri() + "?mode=preview", timeout=8000)
            await self._page.wait_for_function("window.__FF_READY__ === true", timeout=5000)
            return self
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        try:
            if self._page is not None:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._browser is not None and not self._attached:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            pass
        if self._held_lock:
            from ..engine.runengine import LOCK_MANAGER
            LOCK_MANAGER.release("chrome-queue", self.holder)
            self._held_lock = False

    async def __aexit__(self, *exc):
        await self.close()

    async def init(self, payload: dict) -> dict:
        return await asyncio.wait_for(
            self._page.evaluate("p => window.__FF_PREVIEW_INIT__(p)", payload), timeout=8)

    async def frame(self, t: float) -> bytes:
        data_url = await asyncio.wait_for(
            self._page.evaluate("t => window.__FF_PREVIEW_FRAME__(t)", t), timeout=10)
        if not isinstance(data_url, str) or "," not in data_url:
            raise RuntimeError("预览页未返回 PNG")
        return base64.b64decode(data_url.split(",", 1)[1])

    async def frame_jpeg(self, t: float, quality: float = 0.98) -> bytes:
        data_url = await asyncio.wait_for(
            self._page.evaluate("arg => window.__FF_PREVIEW_FRAME_JPEG__(arg[0], arg[1])",
                                [t, quality]), timeout=10)
        if not isinstance(data_url, str) or "," not in data_url:
            raise RuntimeError("预览页未返回 JPEG")
        return base64.b64decode(data_url.split(",", 1)[1])

    async def render_one(self, payload: dict) -> bytes:
        await self.init(payload)
        return await self.frame(payload.get("t", 0))


def _payload(ctx: PreviewContext, programs: list[dict], transitions: list[dict],
             out: dict, t: float | None = None) -> dict:
    src_w = int(programs[0]["program"].get("canvas", {}).get("w") or ctx.profile["width"])
    return {"programs": programs, "transitions": transitions,
            "width": out["width"], "height": out["height"],
            "scale": round(out["width"] / max(src_w, 1), 6),
            "fontCss": ctx.font_css, "t": t}


# ---------- 单帧 ----------

@dataclass
class StillResult:
    png: bytes
    cached: bool
    ms: int
    scene_hash: str
    time: float
    width: int
    height: int
    chrome: str


def _still_key(scene_key: str, t: float, profile: str, out: dict, wm: bool) -> str:
    raw = f"{scene_key}|{t:.4f}|{profile}|{out['width']}x{out['height']}|{RENDERER_VER}|{int(wm)}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def render_still(session: Session, project_id: int, scene_id: str, t: float | None = None,
                       profile: str = "draft", watermark: bool = True,
                       debounce: bool = True) -> StillResult:
    t0 = time.monotonic()
    ctx = resolve_context(session, project_id)
    out = _output_profile(profile)
    scene = _scene_by_id(ctx, scene_id)
    at = _clamp_time(scene, t, ctx.profile["fps"])
    programs = build_programs(ctx, motion=False, scene_id=scene_id)
    shash = scene_hash(programs[0]["program"], ctx.tokens_sha, ctx.engine_sha,
                       ctx.font_sha, ctx.profile, [], scene_id)
    cache = PreviewCache(project_id)
    key = _still_key(shash, at, profile, out, watermark)
    hit = cache.get(shash, key)
    if hit is not None:
        return StillResult(hit, True, int((time.monotonic() - t0) * 1000),
                           shash, at, out["width"], out["height"], "cache")

    gen_key = (project_id, scene_id)
    gen = _STILL_GEN.get(gen_key, 0) + 1
    _STILL_GEN[gen_key] = gen
    if debounce:
        await asyncio.sleep(0.25)
    if _STILL_GEN.get(gen_key) != gen:
        raise ApiError(ErrorCode.E_PREVIEW_BUSY, "预览请求已被更新覆盖", status=429,
                       details={"superseded": True})
    payload = _payload(ctx, programs, [], out, at)
    # 单帧走 full-res → Lanczos：与 final 归一化后 SSIM≈1.0（网点相位不被降采样改变）
    payload.update({"width": ctx.profile["width"], "height": ctx.profile["height"], "scale": 1})
    global _INTERACTIVE
    chrome_mode = "owned"
    try:
        async with _PAGE_SEM:
            _INTERACTIVE += 1
            async with PreviewRenderer() as r:
                chrome_mode = r.mode
                raw = await r.render_one(payload)
    finally:
        _INTERACTIVE = max(0, _INTERACTIVE - 1)
    if _STILL_GEN.get(gen_key) != gen:
        raise ApiError(ErrorCode.E_PREVIEW_BUSY, "预览请求已被更新覆盖", status=429,
                       details={"superseded": True})
    png = await asyncio.to_thread(resize_png, raw, out["width"], out["height"])
    png = await asyncio.to_thread(watermark_png, png, watermark)
    cache.put(shash, key, png)
    await asyncio.to_thread(cache.evict)
    _STATS["renders"] += 1
    return StillResult(png, False, int((time.monotonic() - t0) * 1000),
                       shash, at, out["width"], out["height"], chrome_mode)


# ---------- Jobs（片段 / 整片） ----------

@dataclass
class PreviewJob:
    id: str
    project_id: int
    kind: str
    profile: str
    status: str = "queued"
    progress: float = 0.0
    eta: float | None = None
    error: str | None = None
    url: str | None = None
    path: str | None = None
    scene_id: str | None = None
    start: float | None = None
    end: float | None = None
    created: float = field(default_factory=time.time)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    frames: int = 0
    rendered: int = 0
    reused: int = 0
    chrome: str | None = None


def job_payload(job: PreviewJob) -> dict:
    return {"jobId": job.id, "kind": job.kind, "profile": job.profile,
            "status": job.status, "progress": round(job.progress, 4),
            "eta": round(job.eta, 1) if job.eta is not None else None,
            "error": job.error, "url": job.url, "sceneId": job.scene_id,
            "frames": job.frames, "rendered": job.rendered, "reused": job.reused,
            "chrome": job.chrome}


def get_job(job_id: str) -> PreviewJob:
    job = _JOBS.get(job_id)
    if not job:
        raise not_found("预览任务")
    return job


def cancel_job(job_id: str) -> dict:
    job = get_job(job_id)
    job.cancel_event.set()
    if job.status in ("queued", "running"):
        job.status = "canceled"
    return job_payload(job)


def _new_job(project_id: int, kind: str, profile: str, **kw) -> PreviewJob:
    job = PreviewJob(id=uuid.uuid4().hex[:12], project_id=project_id,
                     kind=kind, profile=profile, **kw)
    job.url = f"/api/preview/jobs/{job.id}/file"
    _JOBS[job.id] = job
    return job


def create_segment_job(session: Session, project_id: int, scene_id: str, start: float,
                       end: float, profile: str = "draft",
                       watermark: bool = True) -> PreviewJob:
    _output_profile(profile)
    ctx = resolve_context(session, project_id)
    scene = _scene_by_id(ctx, scene_id)
    if start < 0 or end > ctx.profile["duration"] + 1e-3 or end <= start:
        raise ApiError(ErrorCode.E_VALIDATION,
                       f"片段范围非法：{start}-{end}（片长 {ctx.profile['duration']}s）")
    job = _new_job(project_id, "segment", profile, scene_id=scene_id,
                   start=round(start, 3), end=round(end, 3))
    job.task = asyncio.create_task(_run_job(job, watermark))
    return job


def create_film_job(session: Session, project_id: int, profile: str = "draft",
                    watermark: bool = True) -> PreviewJob:
    _output_profile(profile)
    ctx = resolve_context(session, project_id)
    job = _new_job(project_id, "film", profile,
                   start=0.0, end=round(ctx.profile["duration"], 3))
    job.task = asyncio.create_task(_run_job(job, watermark))
    return job


async def _render_frames(job: PreviewJob, ctx: PreviewContext, programs: list[dict],
                         times: list[float], group: str, out: dict,
                         profile: str, watermark: bool) -> tuple[list[bytes], int]:
    cache = PreviewCache(job.project_id)
    pngs: list[bytes | None] = []
    missing: list[tuple[int, float]] = []
    reused = 0
    for i, t in enumerate(times):
        key = _still_key(group, t, profile, out, watermark)
        data = cache.get(group, key)
        if data is not None:
            pngs.append(data)
            reused += 1
        else:
            pngs.append(None)
            missing.append((i, t))
    if missing:
        # 与 final 同源：native 分辨率渲染，再 Lanczos 降采样（SSIM 归一化 ≥0.98）
        native = {"width": int(ctx.profile["width"]), "height": int(ctx.profile["height"])}
        payload = _payload(ctx, programs, ctx.transitions, native)
        async with PreviewRenderer() as r:
            job.chrome = r.mode
            await r.init(payload)
            for n, (i, t) in enumerate(missing):
                if job.cancel_event.is_set():
                    raise asyncio.CancelledError
                while _INTERACTIVE > 0:
                    await asyncio.sleep(0.03)
                async with _PAGE_SEM:
                    raw = await r.frame_jpeg(t, 0.98)
                data = await asyncio.to_thread(finish_png, raw, out["width"], out["height"], watermark)
                key = _still_key(group, t, profile, out, watermark)
                cache.put(group, key, data)
                pngs[i] = data
                job.rendered += 1
                done = reused + n + 1
                job.progress = done / max(len(times), 1)
                elapsed = time.time() - job.created
                job.eta = (elapsed / job.progress - elapsed) if job.progress > 0 else None
    await asyncio.to_thread(cache.evict)
    _STATS["renders"] += len(missing)
    if job.chrome is None:
        job.chrome = "cache"
    return [p for p in pngs if p is not None], reused


async def _ffmpeg_encode(frames_dir: Path, fps: int, out: Path, crf: int, preset: str,
                         cancel: asyncio.Event) -> None:
    from ..engine.runengine import LOCK_MANAGER
    holder = f"preview-ffmpeg:{uuid.uuid4().hex[:8]}"
    await LOCK_MANAGER.acquire("ffmpeg", holder)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.mp4")
        log = out.with_suffix(".ffmpeg.log")
        argv = ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "%06d.png"),
                "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
        # stderr 落文件，避免长片编码时管道写满导致死锁
        with log.open("wb") as err:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.DEVNULL, stderr=err)
            wait_task = asyncio.create_task(proc.wait())
            cancel_task = asyncio.create_task(cancel.wait())
            try:
                done, _pending = await asyncio.wait({wait_task, cancel_task},
                                                    return_when=asyncio.FIRST_COMPLETED)
            finally:
                cancel_task.cancel()
                if not wait_task.done():
                    wait_task.cancel()
        if cancel.is_set():
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
            raise asyncio.CancelledError
        if proc.returncode != 0:
            err_text = log.read_text(errors="replace")[-800:] if log.exists() else ""
            raise RuntimeError("预览编码失败：" + err_text)
        tmp.replace(out)
        log.unlink(missing_ok=True)
    finally:
        LOCK_MANAGER.release("ffmpeg", holder)


async def _run_job(job: PreviewJob, watermark: bool) -> None:
    from ..db import engine as db_engine
    tmpdir: Path | None = None
    try:
        if job.cancel_event.is_set():
            job.status = "canceled"
            return
        job.status = "running"
        with Session(db_engine) as session:
            ctx = resolve_context(session, job.project_id)
        out = _output_profile(job.profile)
        if job.kind == "segment":
            start = float(job.start or 0)
            end = float(job.end or 0)
            times = [round(start + i / out["fps"], 4)
                     for i in range(max(0, round((end - start) * out["fps"])))]
            group = content_hash({"kind": "segment", "programs": _programs_sha(
                build_programs(ctx, motion=True)), "transitions": ctx.transitions,
                "profile": ctx.profile, "engine": ctx.engine_sha, "tokens": ctx.tokens_sha,
                "font": ctx.font_sha})
        else:
            times = [round(i / out["fps"], 4)
                     for i in range(max(0, round(ctx.profile["duration"] * out["fps"])))]
            group = content_hash({"kind": "film", "programs": _programs_sha(
                build_programs(ctx, motion=True)), "transitions": ctx.transitions,
                "profile": ctx.profile, "engine": ctx.engine_sha, "tokens": ctx.tokens_sha,
                "font": ctx.font_sha})
        programs = build_programs(ctx, motion=True)
        job.frames = len(times)
        pngs, reused = await _render_frames(job, ctx, programs, times, group, out,
                                           job.profile, watermark)
        if len(pngs) != len(times):
            raise RuntimeError(f"预览帧缺失 {len(times) - len(pngs)}")
        job.reused = reused
        tmpdir = ctx.root / "out" / "preview" / f".tmp_{job.id}"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        tmpdir.mkdir(parents=True)
        for i, data in enumerate(pngs):
            (tmpdir / f"{i:06d}.png").write_bytes(data)
        name = (f"segment_{job.scene_id}_{job.start}_{job.end}_{job.profile}.mp4"
                if job.kind == "segment" else f"film_{job.profile}.mp4")
        out_path = ctx.root / "out" / "preview" / re.sub(r"[^0-9A-Za-z_.-]", "_", name)
        await _ffmpeg_encode(tmpdir, out["fps"], out_path, out["crf"], out["preset"],
                             job.cancel_event)
        shutil.rmtree(tmpdir, ignore_errors=True)
        job.path = str(out_path)
        job.status = "succeeded"
        job.progress = 1.0
        job.eta = 0.0
    except asyncio.CancelledError:
        job.status = "canceled"
    except Exception as e:
        job.status = "failed"
        job.error = str(e)[:800]
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
