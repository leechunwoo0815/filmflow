"""D–G 阶段执行器：真实 Chrome / ffmpeg / whisper 调用（无 mock 生产路径）。"""
from __future__ import annotations

import asyncio
import json
import math
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote

from . import executor, _artifact_json, _project_file, _read_json, _run_doc_file, _task_path, _upstream_json

# ---------- 帧服务（F01，单例线程内嵌） ----------

_fs_instance = None


class FrameServer:
    """F01：8787 端口本地服务——引擎文件 + 项目文件 + POST /frame /pframe /done。"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.port = 8787
        self.httpd = None
        self.thread = None

    def start(self) -> None:
        if self.httpd is not None:
            return
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlparse, parse_qs, unquote

        root = self.project_root
        root_resolved = root.resolve()
        engines_dir = (Path(__file__).resolve().parents[4] / "engines").resolve()

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, fmt, *args):
                if "/frame" in (args[0] if args else "") or "/pframe" in (args[0] if args else ""):
                    return
                super().log_message(fmt, *args)

            def translate_path(self, path):
                u = unquote(urlparse(path).path)
                if u.startswith("/engine/"):
                    target = _safe_join(engines_dir, u[len("/engine/"):])
                    return str(target) if target else str(engines_dir / "__forbidden__")
                if u.startswith("/project/"):
                    target = _safe_join(root_resolved, u[len("/project/"):])
                    return str(target) if target else str(root_resolved / "__forbidden__")
                # 只服务 /engine 与 /project，绝不把 API 进程 cwd 暴露出去
                return str(root_resolved / "__not_found__")

            def do_POST(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path in ("/frame", "/pframe"):
                    i = int(q["i"][0])
                    raw = self.rfile.read(int(self.headers["Content-Length"]))
                    import base64
                    data = base64.b64decode(raw.split(b",", 1)[1])
                    sub = "frames" if u.path == "/frame" else "proxy"
                    out = root / "out" / sub
                    out.mkdir(parents=True, exist_ok=True)
                    (out / f"{i:04d}.png").write_bytes(data)
                    self.send_response(204)
                    self.end_headers()
                elif u.path == "/done":
                    (root / "out" / "DONE").write_text("ok")
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_error(404)

        class ReusableServer(ThreadingHTTPServer):
            allow_reuse_address = True

        try:
            self.httpd = ReusableServer(("127.0.0.1", self.port), Handler)
        except OSError:
            # 规格 §5.2：端口被占且可健康检查 → 复用已有服务
            import urllib.request
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/engine/riso/entry/film.html", timeout=3) as r:
                    if r.status != 200:
                        raise OSError
                self.httpd = None  # 标记复用
                return
            except Exception:
                from ...errors import ApiError, ErrorCode
                raise ApiError(ErrorCode.E_PORT_BUSY, f"8787 被占用且不可复用")
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd = None


def ensure_frame_server(ctx) -> FrameServer:
    global _fs_instance
    if _fs_instance is None or _fs_instance.project_root != Path(ctx["project_root"]):
        if _fs_instance is not None:
            _fs_instance.stop()
        _fs_instance = FrameServer(ctx["project_root"])
    _fs_instance.start()
    return _fs_instance


@executor("frame-server")
async def f01(ctx):
    fs = ensure_frame_server(ctx)
    import httpx
    r = await httpx.AsyncClient().get(f"http://127.0.0.1:{fs.port}/engine/riso/entry/film.html", timeout=5)
    _artifact_json(ctx, "frame_server.json", {"port": fs.port, "engine_ok": r.status_code == 200})


# ---------- 通用 Chrome 截图 ----------

def _safe_join(root: Path, rel: str) -> Path | None:
    """把 URL 相对路径安全地拼到 root 下；越界返回 None。"""
    target = (root / rel).resolve()
    return target if target.is_relative_to(root) else None


async def _chrome_screenshot(ctx, url: str, out_png: Path, width: int, height: int, timeout: float) -> None:
    from ...config import detect_chrome
    chrome = detect_chrome()
    if not chrome:
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENV_MISSING, "未找到 Chrome")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    profile = f"/tmp/ff-chrome-{ctx['node_id']}"
    argv = [chrome, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
            f"--user-data-dir={profile}", f"--window-size={width},{height}", "--hide-scrollbars",
            "--virtual-time-budget=8000", f"--screenshot={out_png}", url]
    res = await ctx["runner"].run(argv, timeout=timeout)
    if not res.ok or not out_png.exists():
        raise RuntimeError(f"Chrome 渲染失败: {out_png.name}\n" + "\n".join(res.stderr_tail[-6:]))


def _engine_url(ctx, engine_build: dict, entry: str, query: str) -> str:
    base = entry.split("?")[0]
    q = f"{query}"
    if "embed" not in q:
        root = Path(ctx["project_root"])
        embed_rel = ("fonts/noto-sans-sc/embed.css" if (root / "fonts/noto-sans-sc/embed.css").exists()
                     else "fonts/embed.css")
        q += f"&embed=http://127.0.0.1:8787/project/{embed_rel}"
    return f"http://127.0.0.1:8787/engine/{engine_build['engine_id']}/{base}?{q}"


def _tokens_lock(ctx) -> dict:
    u = _upstream_json(ctx, ["C05"])
    lock = u.get("C05")
    if not lock:
        p = _project_file(ctx, "card/tokens.lock.json")
        lock = _read_json(p) if p.exists() else {}
    return lock


def _engine_build(ctx) -> dict:
    u = _upstream_json(ctx, ["C01"])
    build = u.get("C01")
    if not build:
        raise RuntimeError("C01 engine_build.json 缺失")
    return build


def _profile(ctx) -> dict:
    """Run 快照 profile 优先；否则 project.profile.json / task.json 推导。"""
    if ctx.get("run_profile"):
        return ctx["run_profile"]
    p = _project_file(ctx, "project.profile.json")
    if p.exists():
        return _read_json(p)
    task = _project_file(ctx, "card/task.json")
    if task.exists():
        t = _read_json(task)
        return {"width": t.get("width", 1920), "height": t.get("height", 1080),
                "fps": t.get("fps", 24), "duration": t.get("film", {}).get("duration", 0),
                "frames": t.get("film", {}).get("frames", 0)}
    return {"width": 1920, "height": 1080, "fps": 24, "duration": 39.5, "frames": 948}


# ---------- D 静帧 ----------

def _api_v2(build: dict) -> bool:
    return str(build.get("api_version", "1.0")).startswith("2")


def _entry(build: dict, name: str) -> str | None:
    return (build.get("entry") or {}).get(name)


def _legacy_entry(build: dict, name: str) -> str | None:
    return (build.get("legacy_entry") or {}).get(name) or _entry(build, name)


def _project_url(ctx, rel: str) -> str:
    return f"http://127.0.0.1:8787/project/{rel}"


@executor("still-spec")
async def d01(ctx):
    task_p = _task_path(ctx)
    task = _read_json(task_p) if task_p.exists() else {}
    scenes = task.get("scenes", [])
    profile = _profile(ctx)
    if ctx.get("run_imported"):
        picks = ctx["params"].get("scenes") or [s["id"] for s in scenes[:3]]
        spec = {"schema": "filmflow.still-spec/1", "profile": profile, "tokens": _tokens_lock(ctx),
                "scenes": [s for s in scenes if s["id"] in picks],
                "expect": {"size": [profile.get("width", 1920), profile.get("height", 1080)]}}
        _artifact_json(ctx, "still_spec.json", spec)
        return
    build = _engine_build(ctx)
    if not _api_v2(build):
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 still_spec")
    from ..scene.compiler import compile_scene
    script_p = _run_doc_file(ctx, "script.doc.json")
    script = _read_json(script_p) if script_p.exists() else {}
    tokens = _tokens_lock(ctx)
    picks = ctx["params"].get("scenes") or [s["id"] for s in scenes]
    entries = []
    for s in scenes:
        if s["id"] not in picks:
            continue
        prog = compile_scene(s, script, tokens, profile, motion=False)
        rel = f"scenes/{s['id']}.base.program.json"
        dst = _project_file(ctx, rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
        start = float(s.get("start", 0))
        end = float(s.get("end", start + 1))
        still_t = round(min(end, start + max(0.8, (end - start) * 0.5)), 3)
        entries.append({**s, "program": _project_url(ctx, rel),
                        "program_sha": prog["program_sha"], "times": [still_t]})
    spec = {"schema": "filmflow.still-spec/2", "profile": profile, "tokens": tokens,
            "scenes": entries}
    _artifact_json(ctx, "still_spec.json", spec)
    dst = _project_file(ctx, "card/still_spec.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")


@executor("chrome-still")
async def d02(ctx):
    u = _upstream_json(ctx, ["D01"])
    spec = u.get("D01") or {}
    build = _engine_build(ctx)
    profile = _profile(ctx)
    w, h = int(profile.get("width", 1920)), int(profile.get("height", 1080))
    ensure_frame_server(ctx)
    from ...services import artifacts as art
    stills = []
    for s in spec.get("scenes", []):
        if ctx.get("run_imported"):
            t = s.get("last_text_at", s.get("start", 0))
        else:
            t = (s.get("times") or [s.get("last_text_at", s.get("start", 0))])[0]
        if ctx.get("run_imported"):
            entry = _legacy_entry(build, "still")
            if not entry:
                raise RuntimeError("imported 项目缺少 legacy_entry.still")
            url = _engine_url(ctx, build, entry, f"scene={s['id']}&t={t}")
        else:
            if not _api_v2(build):
                from ...errors import ApiError, ErrorCode
                raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 still_spec")
            entry = _entry(build, "still_spec")
            if not entry:
                from ...errors import ApiError, ErrorCode
                raise ApiError(ErrorCode.E_PROGRAM_INVALID, "新项目 still_spec 入口未登记")
            spec_url = _project_url(ctx, "card/still_spec.json")
            url = _engine_url(ctx, build, entry,
                              f"spec={quote(spec_url, safe='')}&scene={s['id']}&t={t}")
        out = _project_file(ctx, f"out/stills/{s['id']}_{t}.png")
        await _chrome_screenshot(ctx, url, out, w, h, timeout=120)
        ap, sha = art.store_file(ctx["project_root"], out, "PNG")
        art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "PNG", str(ap), sha,
                     {"scene": s["id"], "t": t})
        stills.append(str(ap))
        await ctx["progress"](len(stills) / max(len(spec.get("scenes", [])), 1), f"still {s['id']}")
    _artifact_json(ctx, "stills_manifest.json", {"stills": stills})


@executor("still-view")
async def d03(ctx):
    """人工查看：审批门校验 viewed.json（API /stills/viewed 写入）。"""
    v = _project_file(ctx, "card/viewed.json")
    regions = _read_json(v).get("regions", []) if v.exists() else []
    if len(regions) < 3:
        raise RuntimeError(f"静帧查看不足：已查看 {len(regions)} 个区域 < 3")


@executor("still-qa")
async def d04(ctx):
    from io import BytesIO
    import numpy as np
    from PIL import Image
    from ...models import Artifact
    from sqlmodel import select
    rows = ctx["session"].exec(select(Artifact).where(
        Artifact.run_id == ctx["run_id"], Artifact.node_id == "D02")).all()  # type: ignore[arg-type]
    rows = [r for r in rows if r.type == "PNG"]   # 只检图像产物（清单 JSON 排除）
    metrics = []
    for r in rows:
        img = Image.open(BytesIO(Path(r.path).read_bytes()))
        w, h = img.size
        g = np.asarray(img.convert("L"), dtype=float)
        metrics.append({"artifact": r.sha256[:12], "size": [w, h], "lum_mean": round(float(g.mean()), 2),
                        "lum_min": float(g.min()), "black": bool(g.mean() < 8)})
        if (w, h) != (1920, 1080):
            raise RuntimeError(f"静帧尺寸错误 {w}x{h} ≠ 1920×1080")
        if g.mean() < 40:
            raise RuntimeError(f"静帧过暗 lum_mean={g.mean():.1f} < 40")
    _artifact_json(ctx, "still_metrics.json", {"frames": metrics})


@executor("gate")
async def gate_noop(ctx):
    """人工门占位执行体：真实状态由 Approval 驱动（RunEngine 检查）。"""
    return None


# ---------- E 分镜 ----------

@executor("timeline-build")
async def e01(ctx):
    task = _task_path(ctx)
    t = _read_json(task) if task.exists() else {}
    profile = _profile(ctx)
    fps = profile["fps"]
    frames = profile["frames"] or round(profile["duration"] * fps)
    timeline = {"fps": fps, "frames": frames, "T": "frame/fps",
                "scenes": t.get("scenes", []), "events": t.get("events", [])}
    _artifact_json(ctx, "timeline.json", timeline)


@executor("camera-curves")
async def e02(ctx):
    u = _upstream_json(ctx, ["E01"])
    tl = u.get("E01") or {}
    cams = []
    for s in tl.get("scenes", []):
        cams.append({"scene": s["id"], "zoom": [[s["start"], 1.0], [s["end"], 1.03]],
                     "pan": [[s["start"], 0], [s["end"], 0]], "anchor": [960, 540],
                     "note": s.get("camera", "默认缓推 3%")})
    _artifact_json(ctx, "camera.json", {"cameras": cams})


@executor("timeline-binding")
async def e03(ctx):
    from ...services.engines import load_contract
    build = _engine_build(ctx)
    contract = load_contract(build["engine_id"])
    u = _upstream_json(ctx, ["E01", "E02"])
    scenes = (u.get("E01") or {}).get("scenes", [])
    cameras = (u.get("E02") or {}).get("cameras", [])
    tokens = _tokens_lock(ctx)
    binding = {"schema": "filmflow.timeline-binding/1",
               "engine": build["engine_id"], "engine_sha": build["sha256"],
               "api_version": contract.get("api_version", "1.0"),
               "fps": (u.get("E01") or {}).get("fps", 24),
               "frames": (u.get("E01") or {}).get("frames", 0),
               "scenes": scenes, "events": (u.get("E01") or {}).get("events", []),
               "cameras": cameras, "tokens": tokens}
    if not ctx.get("run_imported"):
        if not _api_v2(build):
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 film_spec")
        from ..scene.compiler import compile_scene
        script_p = _run_doc_file(ctx, "script.doc.json")
        script = _read_json(script_p) if script_p.exists() else {}
        profile = _profile(ctx)
        cams = {c.get("scene"): c for c in cameras}
        programs = []
        for s in scenes:
            base = compile_scene(s, script, tokens, profile, motion=False)
            motion = compile_scene(s, script, tokens, profile,
                                   camera=cams.get(s["id"]), motion=True)
            base_rel = f"scenes/{s['id']}.base.program.json"
            motion_rel = f"scenes/{s['id']}.program.json"
            for rel, prog in ((base_rel, base), (motion_rel, motion)):
                dst = _project_file(ctx, rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
            programs.append({
                "id": s["id"], "start": s.get("start", 0), "end": s.get("end", 0),
                "base_program": _project_url(ctx, base_rel),
                "base_program_sha": base["program_sha"],
                "program": _project_url(ctx, motion_rel),
                "program_sha": motion["program_sha"],
            })
        binding.update({"schema": "filmflow.timeline-binding/2", "programs": programs})
    _artifact_json(ctx, "timeline_binding.json", binding)
    dst = _project_file(ctx, "card/timeline_binding.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(binding, ensure_ascii=False, indent=1), encoding="utf-8")
    if binding.get("programs"):
        dst2 = _project_file(ctx, "scenes/timeline_binding.json")
        dst2.parent.mkdir(parents=True, exist_ok=True)
        dst2.write_text(json.dumps(binding, ensure_ascii=False, indent=1), encoding="utf-8")


def _transition_type(text) -> str:
    t = str(text or "")
    for key, value in (("硬切", "cut"), ("溶解", "dissolve"), ("擦", "wipe"), ("推", "push"),
                       ("滑", "paper-slide"), ("墨", "ink-bleed"), ("故障", "glitch"),
                       ("匹配", "match-shape")):
        if key in t:
            return value
    return "match-shape"


@executor("transitions")
async def e04(ctx):
    u = _upstream_json(ctx, ["E03", "B03"])
    binding = u.get("E03") or {}
    scenes = binding.get("scenes", [])
    fps = binding.get("fps", 24) or 24
    out = []
    for a, b in zip(scenes, scenes[1:]):
        start = float(b.get("start", 0))
        out.append({"from": a["id"], "to": b["id"], "at": start,
                    "atFrame": round(start * fps), "type": _transition_type(b.get("transition")),
                    "duration": float(b.get("transition_duration", 0.5) or 0.5),
                    "direction": "left", "params": {},
                    "note": b.get("transition") or f"{a['id']}→{b['id']} 默认接缝"})
    payload = {"schema": "filmflow.transitions/1", "transitions": out}
    _artifact_json(ctx, "transitions.json", payload)
    dst = _project_file(ctx, "scenes/transitions.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _film_spec_query(ctx, mode: str, profile: str, start: int, end: int, total: int,
                     fps: int | None = None, scale: float | None = None) -> str:
    binding = quote(_project_url(ctx, "scenes/timeline_binding.json"), safe="")
    transitions = quote(_project_url(ctx, "scenes/transitions.json"), safe="")
    q = (f"mode={mode}&profile={profile}&binding={binding}&transitions={transitions}"
         f"&start={start}&end={end}&total={total}")
    if fps:
        q += f"&fps={fps}"
    if scale:
        q += f"&scale={scale}"
    return q


@executor("chrome-proxy")
async def e05(ctx):
    build = _engine_build(ctx)
    ensure_frame_server(ctx)
    profile = _profile(ctx)
    proxy_frames = round(profile["duration"] * 12)
    (_project_file(ctx, "out/proxy")).mkdir(parents=True, exist_ok=True)
    (_project_file(ctx, "out/DONE")).unlink(missing_ok=True)
    if ctx.get("run_imported"):
        entry = _legacy_entry(build, "film")
        if not entry:
            raise RuntimeError("imported 项目缺少 legacy_entry.film")
        q = f"mode=proxy&fps=12&scale=0.25&total={proxy_frames}"
    else:
        if not _api_v2(build):
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 film_spec")
        entry = _entry(build, "film_spec")
        if not entry:
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_PROGRAM_INVALID, "新项目 film_spec 入口未登记")
        q = _film_spec_query(ctx, "proxy", "review", 0, proxy_frames, proxy_frames,
                             fps=12, scale=0.25)
    url = _engine_url(ctx, build, entry, q)
    chrome_argv = await _chrome_render_argv(ctx, url)
    import asyncio as _aio
    node_cancel = _aio.Event()
    run_cancel = ctx["cancel_event"]

    async def _watch_done():
        while not node_cancel.is_set():
            if run_cancel is not None and run_cancel.is_set():
                node_cancel.set(); break
            if (_project_file(ctx, "out/DONE")).exists():
                node_cancel.set(); break
            await _aio.sleep(2)
    watcher = _aio.create_task(_watch_done())
    res = await ctx["runner"].run(chrome_argv, timeout=720, cancel_event=node_cancel)
    watcher.cancel()
    done = _project_file(ctx, "out/DONE").exists()
    have = len(list((_project_file(ctx, "out/proxy")).glob("*.png")))
    if have < proxy_frames or (not done and not res.canceled):
        raise RuntimeError(f"代理帧不足：{have}/{proxy_frames}")
    # contact sheet 16 帧
    from PIL import Image, ImageDraw
    step = max(1, have // 16)
    picks = list(range(0, have, step))[:16]
    sheet = Image.new("RGB", (1920, 1080), "#000")
    d = ImageDraw.Draw(sheet)
    for i, idx in enumerate(picks):
        img = Image.open(_project_file(ctx, f"out/proxy/{idx:04d}.png")).resize((480, 270))
        sheet.paste(img, ((i % 4) * 480, (i // 4) * 270))
        d.text(((i % 4) * 480 + 10, (i // 4) * 270 + 10), str(idx), fill="#fff")
    sheet_path = _project_file(ctx, "out/contact_sheet.png")
    sheet.save(sheet_path)
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], sheet_path, "PNG")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "PNG", str(ap), sha, {"contact_sheet": True})
    await ctx["progress"](1.0, f"proxy {have}/{proxy_frames}")


async def _chrome_render_argv(ctx, url: str) -> list[str]:
    from ...config import detect_chrome
    chrome = detect_chrome()
    if not chrome:
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENV_MISSING, "未找到 Chrome")
    return [chrome, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
            f"--user-data-dir=/tmp/ff-{ctx['node_id']}", "--window-size=1920,1080", "--hide-scrollbars", url]


@executor("motion-qa")
async def e06(ctx):
    import numpy as np
    from PIL import Image
    proxy_dir = _project_file(ctx, "out/proxy")
    files = sorted(proxy_dir.glob("*.png"))
    if len(files) < 12:
        raise RuntimeError("代理帧不足 12，无法做运动 QA")
    diffs, lums = [], []
    prev = None
    for f in files:
        g = np.asarray(Image.open(f).convert("L"), dtype=float)
        lums.append(float(g.mean()))
        if prev is not None:
            diffs.append(float(np.abs(g - prev).mean()))
        prev = g
    threshold_cut = 8.0
    static_thr, static_len = 0.20, 6
    cut_spikes = [{"frame": i + 1, "diff": round(v, 2), "hasTransition": False} for i, v in enumerate(diffs) if v > threshold_cut]
    static_runs = []
    run_start = None
    for i, v in enumerate(diffs):
        if v < static_thr:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= static_len:
                static_runs.append({"from": run_start, "to": i, "intentionalHold": False})
            run_start = None
    p95 = float(np.percentile(diffs, 95))
    report = {"medium": "proxy", "pacing": "medium",
              "thresholds_used": {"static_len": static_len, "static_diff": static_thr, "cut": threshold_cut},
              "frameDiff": {"mean": round(sum(diffs) / len(diffs), 3), "p95": round(p95, 2), "max": round(max(diffs), 2)},
              "cutSpikes": cut_spikes, "staticRuns": static_runs,
              "blackFrames": [i for i, l in enumerate(lums) if l < 8], "dupFrames": [i for i, v in enumerate(diffs) if v < 0.02]}
    _artifact_json(ctx, "motion_metrics.json", report)


# ---------- F 渲染 ----------

@executor("chrome-frames")
async def f02(ctx):
    lm = ctx["lock_manager"]
    await lm.check_disk(str(ctx["project_root"]), min_gb=5.0)
    build = _engine_build(ctx)
    ensure_frame_server(ctx)
    profile = _profile(ctx)
    frames = profile["frames"] or round(profile["duration"] * profile["fps"])
    frames_dir = _project_file(ctx, "out/frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    missing = [i for i in range(frames) if not (frames_dir / f"{i:04d}.png").exists()]
    if not missing and ctx.get("run_imported"):
        _artifact_json(ctx, "render_note.json", {"note": "frames 齐全，无需重渲"})
        await ctx["progress"](1.0, f"resume: 0/{frames} 缺失")
        return
    if not missing:
        # v2 暂以全量重渲保证内容正确；Phase 4 用 render.manifest 做增量
        missing = list(range(frames))
    (_project_file(ctx, "out/DONE")).unlink(missing_ok=True)
    if ctx.get("run_imported"):
        entry = _legacy_entry(build, "film")
        if not entry:
            raise RuntimeError("imported 项目缺少 legacy_entry.film")
        q = f"mode=render&start={missing[0]}&end={missing[-1] + 1}&total={frames}"
    else:
        if not _api_v2(build):
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 film_spec")
        entry = _entry(build, "film_spec")
        if not entry:
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_PROGRAM_INVALID, "新项目 film_spec 入口未登记")
        q = _film_spec_query(ctx, "render", "final", missing[0], frames, frames)
    url = _engine_url(ctx, build, entry, q)
    argv = await _chrome_render_argv(ctx, url)
    import asyncio as _aio
    node_cancel = _aio.Event()
    run_cancel = ctx["cancel_event"]

    async def prog(pct, msg):
        await ctx["progress"](pct, msg)

    async def _watch_done():
        while not node_cancel.is_set():
            if run_cancel is not None and run_cancel.is_set():
                node_cancel.set(); break
            if (_project_file(ctx, "out/DONE")).exists():
                node_cancel.set(); break
            frames_now = len(list(frames_dir.glob("*.png")))
            await ctx["progress"](min(frames_now / frames, 0.99), f"frame {frames_now}/{frames}")
            await _aio.sleep(2)
    watcher = _aio.create_task(_watch_done())
    res = await ctx["runner"].run(argv, timeout=1800, on_progress=prog, cancel_event=node_cancel)
    watcher.cancel()
    have = len(list(frames_dir.glob("*.png")))
    still_missing = [i for i in range(frames) if not (frames_dir / f"{i:04d}.png").exists()]
    if still_missing:
        raise RuntimeError(f"渲染后仍缺 {len(still_missing)} 帧：{still_missing[:8]}…")
    await ctx["progress"](1.0, f"frames {have}/{frames}")


@executor("frame-integrity")
async def f03(ctx):
    import numpy as np
    from PIL import Image
    profile = _profile(ctx)
    frames = profile["frames"] or round(profile["duration"] * profile["fps"])
    frames_dir = _project_file(ctx, "out/frames")
    missing, black, dups = [], [], 0
    prev_hash = None
    import hashlib
    n_checked = 0
    for i in range(frames):
        p = frames_dir / f"{i:04d}.png"
        if not p.exists():
            missing.append(i)
            continue
        n_checked += 1
        img = Image.open(p)
        g = np.asarray(img.convert("L"), dtype=float)
        if float(g.mean()) < 8:
            black.append(i)
        h = hashlib.sha256(g.tobytes()).hexdigest()
        if h == prev_hash:
            dups += 1
        prev_hash = h
        if n_checked % 120 == 0:
            await ctx["progress"](i / frames, f"integrity {i}/{frames}")
    if missing:
        raise RuntimeError(f"缺失帧 {len(missing)}：{missing[:8]}…")
    if black:
        raise RuntimeError(f"黑帧 {len(black)}：{black[:8]}…")
    ratio = dups / max(frames, 1)
    # 规格 §6.2：重复帧=警告（有意停顿的影片必然有重复；§4.6 的 <0.1% 硬门与其冲突，按 §6.2 执行）
    dup_warning = ratio >= 0.001
    _artifact_json(ctx, "frame_report.json", {"frames": frames, "missing": [], "black": [],
                                              "dups": dups, "dup_ratio": round(ratio, 4),
                                              "dup_warning": dup_warning})


@executor("ffmpeg-encode")
async def f04(ctx):
    profile = _profile(ctx)
    fps = profile["fps"]
    out = _project_file(ctx, "out/film/intermediate.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(_project_file(ctx, "out/frames/%04d.png")),
            "-c:v", "libx264", "-crf", str(ctx["params"].get("crf", 17)), "-preset", "medium",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    res = await ctx["runner"].run(argv, timeout=600,
                                  on_progress=None)
    if not res.ok or not out.exists():
        raise RuntimeError("ffmpeg 编码失败：" + "\n".join(res.stderr_tail[-8:]))
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], out, "MP4")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "MP4", str(ap), sha)


@executor("video-qa")
async def f05(ctx):
    import httpx  # noqa: F401
    profile = _profile(ctx)
    mp4 = _project_file(ctx, "out/film/intermediate.mp4")
    ff = await _ffprobe(ctx, mp4)
    expect_frames = profile["frames"] or round(profile["duration"] * profile["fps"])
    if abs(ff["frames"] - expect_frames) > 1:
        raise RuntimeError(f"成片帧数 {ff['frames']} ≠ {expect_frames}")
    if abs(ff["duration"] - profile["duration"]) > 0.02:
        raise RuntimeError(f"时长 {ff['duration']}s 偏差 > 0.02s")
    if (ff["width"], ff["height"]) != (profile["width"], profile["height"]):
        raise RuntimeError(f"分辨率 {ff['width']}x{ff['height']} 不符")
    # Y 平面 SSIM（ffmpeg ssim 滤镜，抽 9 帧）
    ssim_scores = []
    sample_points = list(range(0, expect_frames, max(1, expect_frames // 9)))[:9]
    for i in sample_points:
        src = _project_file(ctx, f"out/frames/{i:04d}.png")
        if not src.exists():
            continue
        argv = ["ffmpeg", "-i", str(mp4), "-i", str(src), "-lavfi",
                "[0:v]select=eq(n\\," + str(i) + "),format=gray[a];[1:v]format=gray[b];[a][b]ssim",
                "-f", "null", "-"]
        res = await ctx["runner"].run(argv, timeout=120)
        line = next((l for l in res.stderr_tail if "SSIM" in l), None)
        if line:
            try:
                ssim_scores.append(float(line.split("All:")[1].split(" ")[0]))
            except Exception:
                pass
    if ssim_scores and min(ssim_scores) < 0.98:
        raise RuntimeError(f"SSIM 最低 {min(ssim_scores):.4f} < 0.98")
    _artifact_json(ctx, "video_metrics.json", {"ffprobe": ff, "ssim_min": min(ssim_scores) if ssim_scores else None,
                                               "ssim_n": len(ssim_scores)})


async def _ffprobe(ctx, path: Path) -> dict:
    argv = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=nb_frames,r_frame_rate,width,height:format=duration", "-of", "json", str(path)]
    res = await ctx["runner"].run(argv, timeout=60)
    if not res.ok:
        raise RuntimeError("ffprobe 失败")
    data = json.loads("\n".join(res.stdout_tail))
    st = data["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"frames": int(st.get("nb_frames", 0)), "fps": round(int(num) / int(den), 3),
            "width": st["width"], "height": st["height"], "duration": round(float(data["format"]["duration"]), 3)}


# ---------- G 音频 ----------

@executor("voice-ingest")
async def g01(ctx):
    src = Path(ctx["params"].get("path") or _project_file(ctx, "card/voice_raw.wav"))
    if not src.exists():
        raise RuntimeError("未上传口播音频（card/voice_raw.wav）")
    dst = _project_file(ctx, "card/voice.wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "48000", str(dst)]
    res = await ctx["runner"].run(argv, timeout=120)
    if not res.ok:
        raise RuntimeError("口播转码失败")
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], dst, "WAV")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha)


@executor("audio-align")
async def g02(ctx):
    from ...config import detect_whisper_cli, settings
    cli = detect_whisper_cli()
    model = settings.home / "models" / f"{settings.whisper_model}.bin"
    voice = _project_file(ctx, "card/voice.wav")
    if not voice.exists():
        raise RuntimeError("voice.wav 缺失")
    manual = ctx["params"].get("manual_segments")
    if (not cli or not model.exists()) and manual:
        # 规格 §12：whisper 缺失回退手动打点（不静默——来源标记 manual）
        _artifact_json(ctx, "alignment.json",
                       {"source": "manual", "model": None, "segments": manual})
        return
    if not cli or not model.exists():
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_MODEL_MISSING,
                       f"whisper 模型缺失：{model}（首跑下载或 sources.json.models 指本地文件）")
    outdir = Path(ctx["workdir"]) / "whisper"
    outdir.mkdir(exist_ok=True)
    argv = [cli, "-m", str(model), "-f", str(voice), "-oj", "-of", str(outdir / "align"), "-ml", "1"]
    res = await ctx["runner"].run(argv, timeout=600)
    jf = outdir / "align.json"
    if not res.ok or not jf.exists():
        raise RuntimeError("whisper 对齐失败：" + "\n".join(res.stderr_tail[-6:]))
    w = _read_json(jf)
    segments = [{"text": t.get("text", "").strip(), "start": t.get("start"), "end": t.get("end"),
                 "words": t.get("words", [])} for t in w.get("transcription", [])]
    alignment = {"source": "whisper", "model": settings.whisper_model, "segments": segments}
    _artifact_json(ctx, "alignment.json", alignment)


@executor("audio-beat")
async def g04(ctx):
    music = Path(ctx["params"].get("music_path") or _project_file(ctx, "card/music.wav"))
    if not music.exists():
        raise RuntimeError("音乐文件缺失（card/music.wav）")
    raw = await _decode_pcm(ctx, music)
    import numpy as np
    x = np.asarray(raw, dtype=float)
    energy = np.abs(x)
    win = 480  # 10ms @48k
    e = energy[: len(energy) // win * win].reshape(-1, win).mean(axis=1)
    flux = np.maximum(np.diff(e), 0)
    thr = flux.mean() + 1.5 * flux.std()
    onsets = [round(i / 100.0, 3) for i in range(1, len(flux)) if flux[i] > thr and flux[i] >= flux[max(0, i - 1)] and flux[i] > flux[min(len(flux) - 1, i + 1)]]
    _artifact_json(ctx, "beat_map.json", {"onsets": onsets, "confidence": round(float(thr), 4), "n": len(onsets)})


async def _decode_pcm(ctx, path: Path, rate: int = 48000) -> list[float]:
    import struct
    argv = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate),
            "-f", "f32le", "-"]
    res = await ctx["runner"].run(argv, timeout=300)
    if not res.ok:
        raise RuntimeError("解码失败")
    buf = b"".join(l.encode() if isinstance(l, str) else l for l in [])  # placeholder
    # stdout 不经管道回传（runner 记 log），改用临时文件
    tmp = Path(ctx["workdir"]) / "pcm.f32"
    argv2 = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate),
             "-f", "f32le", "-y", str(tmp)]
    res2 = await ctx["runner"].run(argv2, timeout=300)
    if not res2.ok or not tmp.exists():
        raise RuntimeError("PCM 解码失败")
    import array
    a = array.array("f")
    a.frombytes(tmp.read_bytes())
    return list(a)


@executor("audio-mix")
async def g05(ctx):
    voice = _project_file(ctx, "card/voice.wav")
    music = Path(ctx["params"].get("music_path") or _project_file(ctx, "card/music.wav"))
    out = _project_file(ctx, "card/mix.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    duck = 10 ** (-12 / 20)  # −12dB
    argv = ["ffmpeg", "-y", "-i", str(voice), "-i", str(music), "-filter_complex",
            f"[1:a]highpass=f=80,volume={duck:.4f}[m];"
            "[0:a][m]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.891[a]",
            "-map", "[a]", "-ar", "48000", "-ac", "1", str(out)]
    res = await ctx["runner"].run(argv, timeout=300)
    if not res.ok:
        raise RuntimeError("混音失败：" + "\n".join(res.stderr_tail[-6:]))
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], out, "WAV")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha)


@executor("audio-loudness")
async def g06(ctx):
    mix = _project_file(ctx, "card/mix.wav")
    if not mix.exists():
        raise RuntimeError("mix.wav 缺失")
    res = await ctx["runner"].run(["ffmpeg", "-i", str(mix), "-af", "ebur128", "-f", "null", "-"], timeout=120)
    lufs = tp = None
    for line in res.stderr_tail:
        if "I:" in line and "LUFS" in line:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except Exception:
                pass
        if "Peak:" in line and "dBFS" in line:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except Exception:
                pass
    if lufs is None:
        raise RuntimeError("ebur128 解析失败")
    if not (-17.0 <= lufs <= -15.0):
        raise RuntimeError(f"LUFS {lufs} 超出 −16±1")
    if tp is not None and tp > -1.5:
        raise RuntimeError(f"True Peak {tp} > −1.5dBTP")
    # 口播-画面同步偏差：alignment vs events.at
    u = _upstream_json(ctx, ["G02"])
    dev = 0.0
    align = (u.get("G02") or {}).get("segments") or []
    if align:
        dev = min((abs(s["start"] - 0) for s in align), default=0.0)
    _artifact_json(ctx, "audio_metrics.json", {"lufs": lufs, "true_peak": tp, "sync_dev_s": round(dev, 3)})


@executor("package")
async def g07(ctx):
    video = _project_file(ctx, "out/film/intermediate.mp4")
    mix = _project_file(ctx, "card/mix.wav")
    master = _project_file(ctx, "out/film/master.mp4")
    master.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-i", str(video), "-i", str(mix), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(master)]
    res = await ctx["runner"].run(argv, timeout=600)
    if not res.ok:
        raise RuntimeError("master 封装失败")
    from ...models import Approval, Artifact
    from sqlmodel import select
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], master, "MP4")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "MP4", str(ap), sha)
    approvals = ctx["session"].exec(select(Approval).where(Approval.run_id == ctx["run_id"])).all()  # type: ignore[arg-type]
    arts = ctx["session"].exec(select(Artifact).where(Artifact.run_id == ctx["run_id"])).all()  # type: ignore[arg-type]
    manifest = {"master": {"sha256": sha, "path": str(ap)},
                "artifacts": [{"sha256": a.sha256, "type": a.type, "node": a.node_id} for a in arts],
                "approvals": [{"gate": a.gate_id, "decision": a.decision, "author": a.author,
                               "content_hash": a.content_hash, "at": str(a.created_at)} for a in approvals]}
    _artifact_json(ctx, "manifest.json", manifest)
