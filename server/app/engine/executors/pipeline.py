"""D–G 阶段执行器：真实 Chrome / ffmpeg / whisper 调用（无 mock 生产路径）。"""
from __future__ import annotations

from ...logs import get as _get_log

_log = _get_log("pipeline")

import asyncio
import json
import threading
from pathlib import Path
from urllib.parse import quote

from ...atomicwrite import write_atomic
from ..fpscalc import fps_rational, frames_for
from ..fpscalc import norm_fps as _norm_fps
from ..scene.transitions import transition_type as _transition_type
from . import (
    _artifact_json,
    _project_file,
    _read_json,
    _run_doc_file,
    _task_path,
    _upstream_file,
    _upstream_json,
    executor,
)

# ---------- 帧服务（F01，单例线程内嵌） ----------

_fs_instance = None


class FrameServer:
    """F01：帧服务（默认 8787，`FILMFLOW_FRAME_PORT` 可覆盖）——引擎文件 + 项目文件 + POST /frame /pframe /done。"""

    def __init__(self, project_root: str):
        from ...config import settings
        self.project_root = Path(project_root)
        self.port = settings.frame_port
        self.httpd = None
        self.thread = None

    def start(self) -> None:
        if self.httpd is not None:
            return
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs, unquote, urlparse

        root = self.project_root
        root_resolved = root.resolve()
        engines_dir = (Path(__file__).resolve().parents[4] / "engines").resolve()

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, fmt, *args):
                msg = fmt % args if args else fmt
                if "/frame" in msg or "/pframe" in msg:
                    return
                super().log_message(fmt, *args)

            def _needs_token(self, u) -> bool:
                """P2-32：token 只护**数据面**——项目/全局资产文件与帧上传。

                /engine/ 的页面与脚本是入库的公开引擎代码（另有 CSP sandbox 头），
                不设闸：进程内随机 token 会随重启轮换，长命 Chrome 的缓存页/旧
                cookie 会让相对路径的引擎脚本 403 → 静帧全黑（2026-11-05 实测的
                D04 过暗回归）。A2（2026-11-06）：数据面凭据从 `?tok=`（会进访问
                日志/浏览器历史，且曾被持久化进 artifact JSON）改为 **fetch
                `X-FilmFlow-Token` header**；引擎页用 URL `#fragment` 携带 token
                （fragment 永不出现在任何 HTTP 请求/日志里，Chrome 缓存按无
                fragment 的 URL 键控 → 缓存页 + 新 hash 照样拿到新 token）。
                """
                p = u.path
                if p.startswith("/project/") or p.startswith("/global-assets/"):
                    return True
                return False

            def _authorized(self, u) -> bool:
                import hmac

                from ...config import settings
                got = self.headers.get("X-FilmFlow-Token", "")
                return hmac.compare_digest(got, settings.frame_token)

            def end_headers(self):
                from ...security import frameserver_headers
                for k, v in frameserver_headers(self.path).items():
                    self.send_header(k, v)
                super().end_headers()

            def do_GET(self):
                u = urlparse(self.path)
                if self._needs_token(u) and not self._authorized(u):
                    self.send_error(403)
                    return
                super().do_GET()

            def do_HEAD(self):
                u = urlparse(self.path)
                if self._needs_token(u) and not self._authorized(u):
                    self.send_error(403)
                    return
                super().do_HEAD()

            def translate_path(self, path):
                from ...security import frameserver_denied
                u = unquote(urlparse(path).path)
                if frameserver_denied(u):
                    # 上传资产/项目文件里的 HTML/JS 不许作为文档在同源执行
                    return str(root_resolved / "__forbidden__")
                if u.startswith("/engine/"):
                    target = _safe_join(engines_dir, u[len("/engine/"):])
                    return str(target) if target else str(engines_dir / "__forbidden__")
                if u.startswith("/project/"):
                    target = _safe_join(root_resolved, u[len("/project/"):])
                    return str(target) if target else str(root_resolved / "__forbidden__")
                if u.startswith("/global-assets/"):
                    from ...config import settings
                    target = _safe_join(settings.assets_dir.resolve(), u[len("/global-assets/"):])
                    return str(target) if target else str(settings.assets_dir / "__forbidden__")
                # 只服务 /engine、/project 与 /global-assets，绝不把 API 进程 cwd 暴露出去
                return str(root_resolved / "__not_found__")

            def do_POST(self):
                u = urlparse(self.path)
                if not self._authorized(u):
                    self.send_error(403)
                    return
                q = parse_qs(u.query)
                if u.path in ("/frame", "/pframe"):
                    i = int(q["i"][0])
                    raw = self.rfile.read(int(self.headers["Content-Length"]))
                    import base64
                    data = base64.b64decode(raw.split(b",", 1)[1])
                    sub = "frames" if u.path == "/frame" else "proxy"
                    # P2-04：原子写——中途 kill 只会留下 .tmp，F03 永远看不到半张帧
                    out = root / "out" / sub
                    out.mkdir(parents=True, exist_ok=True)
                    write_atomic(out / f"{i:04d}.png", data)
                    self.send_response(204)
                    self.end_headers()
                elif u.path == "/done":
                    write_atomic(root / "out" / "DONE", "ok")
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_error(404)

        class ReusableServer(ThreadingHTTPServer):
            allow_reuse_address = True

        try:
            self.httpd = ReusableServer(("127.0.0.1", self.port), Handler)
        except OSError:
            # 规格 §5.2：端口被占且可健康检查 → 复用已有服务。
            # P2-32：探针必须带本进程 token——403 说明占端口的是**另一个进程**的
            # 帧服务（token 不同），复用它会让引擎取到别的项目根的 program（曾实测
            # 产出黑帧/毒帧），fail-closed 拒绝启动。A2：token 走 header（引擎页
            # 本身是 /engine/ 公开面，探针打它即可，URL 不携带凭据）。
            import urllib.request

            from ...config import settings
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/engine/riso/entry/film.html",
                    headers={"X-FilmFlow-Token": settings.frame_token})
                with urllib.request.urlopen(req, timeout=3) as r:
                    if r.status != 200:
                        raise OSError
                self.httpd = None  # 标记复用
                return
            except Exception:
                from ...errors import ApiError, ErrorCode
                raise ApiError(ErrorCode.E_PORT_BUSY, f"{self.port} 被占用且不可复用")
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
    # trust_env=False：NO_PROXY 带 IPv6 条目（[::1],::1——dev 进程环境实况）时，
    # httpx 解析代理环境变量直接抛 InvalidURL("Invalid port: ':1]'")（2026-11-05
    # 专家复核实测），F01 因此整链必挂。仅本机 127.0.0.1 永无代理语义，全仓其余
    # client 均已显式关闭，此处补齐。
    r = await httpx.AsyncClient(trust_env=False).get(
        f"http://127.0.0.1:{fs.port}/engine/riso/entry/film.html", timeout=5)
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
    profile = f"/tmp/ff-chrome-{ctx['node_id']}-{ctx['run_id']}"
    argv = [chrome, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
            f"--user-data-dir={profile}", f"--window-size={width},{height}", "--hide-scrollbars",
            "--virtual-time-budget=8000", f"--screenshot={out_png}", url]
    res = await ctx["runner"].run(argv, timeout=timeout)
    if not res.ok or not out_png.exists():
        raise RuntimeError(f"Chrome 渲染失败: {out_png.name}\n" + "\n".join(res.stderr_tail[-6:]))


def _engine_url(ctx, engine_build: dict, entry: str, query: str) -> str:
    from ...config import settings
    base = entry.split("?")[0]
    q = f"{query}"
    if "embed" not in q:
        root = Path(ctx["project_root"])
        embed_rel = ("fonts/noto-sans-sc/embed.css" if (root / "fonts/noto-sans-sc/embed.css").exists()
                     else "fonts/embed.css")
        # A2：embed 传**相对路径**（token-free）——引擎页 fetch 后注入 <style>
        # （embed css 是 data:URL 自包含的，<link> 带不了 header 所以弃用）
        q += f"&embed=/project/{embed_rel}"
    # A2：token 只走 #fragment——fragment 不进任何 HTTP 请求/日志/服务器侧记录；
    # Chrome 缓存按无 fragment 的 URL 键控，缓存页照样从新 hash 读到轮换后的新 token
    return (f"http://127.0.0.1:{settings.frame_port}"
            f"/engine/{engine_build['engine_id']}/{base}?{q}#tok={settings.frame_token}")


def _project_url(ctx, rel: str) -> str:
    from ...config import settings
    # A2：不再把 token 拼进 URL（此前 ?tok= 会被持久化进 artifact JSON）；
    # 消费方（引擎页 fetch）统一带 X-FilmFlow-Token header
    return f"http://127.0.0.1:{settings.frame_port}/project/{rel}"


def _asset_resolver(ctx):
    from ...services import assets as asset_svc
    return asset_svc.resolver_for_project(ctx["session"], ctx["project_root"])


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


def _profiles(ctx) -> dict:
    """Run 快照档位优先；旧快照回退项目 render.profile.json / 默认值。"""
    from ...services.render_profiles import resolve
    prof = ctx.get("run_render_profiles") or {}
    if prof.get("draft") and prof.get("review") and prof.get("final"):
        return prof
    return resolve(ctx["project_root"], _profile(ctx), allow_low_final=bool(ctx.get("run_imported")))


# ---------- D 静帧 ----------

def _api_v2(build: dict) -> bool:
    return str(build.get("api_version", "1.0")).startswith("2")


def _entry(build: dict, name: str) -> str | None:
    return (build.get("entry") or {}).get(name)


def _legacy_entry(build: dict, name: str) -> str | None:
    return (build.get("legacy_entry") or {}).get(name) or _entry(build, name)


def _still_times(start: float, end: float) -> list[float]:
    dur = max(0.0, end - start)
    fractions = (0.2, 0.35, 0.5, 0.65, 0.8, 0.95) if dur >= 8.0 else (0.5,)
    return sorted({round(min(end, start + max(0.8, dur * f)), 3) for f in fractions})


def _contact_sheet_picks(items: list[tuple], limit: int = 16) -> list[tuple]:
    by_scene: dict[str, list[tuple]] = {}
    for it in items:
        by_scene.setdefault(it[0], []).append(it)
    picks = [by_scene[sid][0] for sid in sorted(by_scene)]
    for it in items:
        if len(picks) >= limit:
            break
        if it not in picks:
            picks.append(it)
    return picks[:limit]


def _make_contact_sheet(ctx, items: list[tuple[str, float, str, str]]) -> dict:
    """FR-26：16 宫格 contact sheet（含全部场景，最多 16 张 review 静帧）。"""
    if not items:
        return {}
    picks = _contact_sheet_picks(items)
    from PIL import Image, ImageDraw, ImageFont
    sheet = Image.new("RGB", (1920, 1080), "#111")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=20)
    except Exception:
        font = ImageFont.load_default()
    for i, (sid, t, path, _sha) in enumerate(picks):
        img = Image.open(path).convert("RGB")
        img.thumbnail((480, 270), Image.LANCZOS)
        x, y = (i % 4) * 480, (i // 4) * 270
        sheet.paste(img, (x + (480 - img.width) // 2, y + (270 - img.height) // 2))
        label = f"{sid} @{t:.1f}s"
        draw.rectangle([x, y, x + 180, y + 30], fill=(0, 0, 0))
        draw.text((x + 8, y + 5), label, fill="#fff", font=font)
    from ...services import artifacts as art
    out = _project_file(ctx, "out/stills/contact_sheet.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    ap, sha = art.store_file(ctx["project_root"], out, "PNG")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "PNG",
                 str(ap), sha, {"contact_sheet": True,
                                "scenes": sorted({p[0] for p in picks}),
                                "count": len(picks)})
    return {"path": str(ap), "sha256": sha, "scenes": sorted({p[0] for p in picks}),
            "count": len(picks)}


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
        prog = compile_scene(s, script, tokens, profile, motion=False,
                             asset_resolver=_asset_resolver(ctx))
        rel = f"scenes/{s['id']}.base.program.json"
        dst = _project_file(ctx, rel)
        write_atomic(dst, json.dumps(prog, ensure_ascii=False, indent=1))
        start = float(s.get("start", 0))
        end = float(s.get("end", start + 1))
        # 长场景 ≥6 张关键静帧；短场景一张中段帧（FR-26）
        times = _still_times(start, end)
        entries.append({**s, "program": _project_url(ctx, rel),
                        "program_sha": prog["program_sha"], "times": times})
    spec = {"schema": "filmflow.still-spec/2", "profile": profile, "tokens": tokens,
            "scenes": entries}
    _artifact_json(ctx, "still_spec.json", spec)
    dst = _project_file(ctx, "card/still_spec.json")
    write_atomic(dst, json.dumps(spec, ensure_ascii=False, indent=1))


@executor("chrome-still")
async def d02(ctx):
    u = _upstream_json(ctx, ["D01"])
    spec = u.get("D01") or {}
    build = _engine_build(ctx)
    profile = _profile(ctx)
    w, h = int(profile.get("width", 1920)), int(profile.get("height", 1080))
    ensure_frame_server(ctx)
    from ...services import artifacts as art
    profiles = _profiles(ctx)
    stills: list[str] = []
    review_items: list[tuple[str, float, str, str]] = []
    artifacts_by_key: dict[tuple[str, float, str], dict] = {}
    imported = bool(ctx.get("run_imported"))
    if imported:
        total = max(len(spec.get("scenes", [])), 1)
    else:
        total = max(sum(len(s.get("times") or [0]) for s in spec.get("scenes", [])) * 2, 1)
    done = 0
    for s in spec.get("scenes", []):
        times = [s.get("last_text_at", s.get("start", 0))] if imported else \
            (s.get("times") or [s.get("last_text_at", s.get("start", 0))])
        for t in times:
            if imported:
                entry = _legacy_entry(build, "still")
                if not entry:
                    raise RuntimeError("imported 项目缺少 legacy_entry.still")
                url = _engine_url(ctx, build, entry, f"scene={s['id']}&t={t}")
                out = _project_file(ctx, f"out/stills/{s['id']}_{t}.png")
                await _chrome_screenshot(ctx, url, out, w, h, timeout=120)
                ap, sha = art.store_file(ctx["project_root"], out, "PNG")
                art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "PNG",
                             str(ap), sha, {"scene": s["id"], "t": t, "profile": "legacy"})
                stills.append(str(ap))
                review_items.append((s["id"], float(t), str(ap), sha))
                artifacts_by_key[(s["id"], float(t), "legacy")] = {"path": str(ap), "sha256": sha}
                done += 1
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
                native = _project_file(ctx, f"out/stills/{s['id']}_{t}_native.png")
                await _chrome_screenshot(ctx, url, native, w, h, timeout=120)
                from PIL import Image
                img = Image.open(native)
                for pname in ("review", "draft"):
                    spec_p = profiles[pname]
                    dst = _project_file(ctx, f"out/stills/{s['id']}_{t}_{pname}.png")
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    img.resize((int(spec_p["width"]), int(spec_p["height"])), Image.LANCZOS).save(dst)
                    ap, sha = art.store_file(ctx["project_root"], dst, "PNG")
                    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"],
                                 "PNG", str(ap), sha,
                                 {"scene": s["id"], "t": t, "profile": pname,
                                  "width": int(spec_p["width"]), "height": int(spec_p["height"])})
                    stills.append(str(ap))
                    artifacts_by_key[(s["id"], float(t), pname)] = {"path": str(ap), "sha256": sha}
                    if pname == "review":
                        review_items.append((s["id"], float(t), str(ap), sha))
                    done += 1
                native.unlink(missing_ok=True)
            await ctx["progress"](done / total, f"still {s['id']}@{t}")

    scenes_manifest: dict[str, list[dict]] = {}
    for sid, t, ap, sha in review_items:
        scenes_manifest.setdefault(sid, []).append({
            "t": t, "review": {"path": ap, "sha256": sha},
            "draft": artifacts_by_key.get((sid, t, "draft")),
            "legacy": artifacts_by_key.get((sid, t, "legacy"))})
    contact = _make_contact_sheet(ctx, review_items)
    manifest = {
        "schema": "filmflow.stills-manifest/1", "stills": stills,
        "profiles": {k: profiles[k] for k in ("review", "draft")},
        "scenes": scenes_manifest, "contact_sheet": contact,
        "scene_count": len(scenes_manifest),
        "still_count": len(review_items)}
    _artifact_json(ctx, "stills_manifest.json", manifest)
    dst = _project_file(ctx, "card/stills_manifest.json")
    write_atomic(dst, json.dumps(manifest, ensure_ascii=False, indent=1))


def _task_scene_ids(ctx) -> list[str]:
    task_p = _task_path(ctx)
    task = _read_json(task_p) if task_p.exists() else {}
    scenes = task.get("scenes") or []
    if not scenes:
        tl = _run_doc_file(ctx, "timeline.doc.json")
        scenes = (_read_json(tl).get("scenes") or []) if tl.exists() else []
    return [s["id"] for s in scenes if s.get("id")]


@executor("still-view")
async def d03(ctx):
    """人工查看：新项目逐场至少 1 张；imported 保持 ≥3 区域。"""
    v = _project_file(ctx, "card/viewed.json")
    data = _read_json(v) if v.exists() else {}
    regions = data.get("regions", [])
    if ctx.get("run_imported"):
        if len(regions) < 3:
            raise RuntimeError(f"静帧查看不足：已查看 {len(regions)} 个区域 < 3")
        return
    scenes = _task_scene_ids(ctx)
    viewed = {str(x.get("scene")) for x in regions if x.get("scene")}
    missing = [s for s in scenes if s not in viewed]
    if missing:
        raise RuntimeError(f"静帧查看缺场景：{missing}（每个场景至少看 1 张）")


@executor("still-qa")
async def d04(ctx):
    from io import BytesIO

    import numpy as np
    from PIL import Image
    from sqlmodel import select

    from ...models import Artifact
    profiles = _profiles(ctx)
    base = _profile(ctx)
    rows = ctx["session"].exec(select(Artifact).where(
        Artifact.run_id == ctx["run_id"], Artifact.node_id == "D02")).all()  # type: ignore[arg-type]
    rows = [r for r in rows if r.type == "PNG"
            and not (r.meta_json or {}).get("contact_sheet")]   # 图像产物，排除 contact sheet
    metrics = []
    seen: dict[str, set[str]] = {"review": set(), "draft": set(), "legacy": set()}
    current_review: dict[str, list[str]] = {}
    for r in rows:
        meta = r.meta_json or {}
        pname = meta.get("profile") or "legacy"
        spec = profiles.get(pname) if pname in ("review", "draft") else base
        expected = (int(spec.get("width", 1920)), int(spec.get("height", 1080)))
        img = Image.open(BytesIO(Path(r.path).read_bytes()))
        w, h = img.size
        g = np.asarray(img.convert("L"), dtype=float)
        metrics.append({"artifact": r.sha256[:12], "profile": pname, "scene": meta.get("scene"),
                        "size": [w, h], "expected": list(expected),
                        "lum_mean": round(float(g.mean()), 2),
                        "lum_min": float(g.min()), "black": bool(g.mean() < 8)})
        if (w, h) != expected:
            raise RuntimeError(f"静帧尺寸错误 {w}x{h} ≠ {expected[0]}×{expected[1]}（{pname}）")
        if g.mean() < 40:
            raise RuntimeError(f"静帧过暗 lum_mean={g.mean():.1f} < 40")
        if meta.get("scene"):
            seen.setdefault(pname, set()).add(str(meta["scene"]))
        if pname == "review" and meta.get("scene"):
            current_review.setdefault(str(meta["scene"]), []).append(r.sha256)
    for scene in current_review:
        current_review[scene].sort()
    if not ctx.get("run_imported"):
        task = (_upstream_json(ctx, ["B06"]).get("B06") or {})
        scenes = [s.get("id") for s in (task.get("scenes") or []) if s.get("id")]
        for pname in ("review", "draft"):
            missing = sorted(set(scenes) - seen.get(pname, set()))
            if missing:
                raise RuntimeError(f"D02 {pname} 静帧缺场景：{missing}")
    _artifact_json(ctx, "still_metrics.json", {
        "frames": metrics, "coverage": {k: sorted(v) for k, v in seen.items()},
        "profiles": {k: profiles[k] for k in ("review", "draft", "final")}})

    # FR-26：与上一版 D05 静帧 diff（按场景汇总 sha 集合）
    from ...models import Run, Workflow
    run = ctx["session"].get(Run, ctx["run_id"])
    wf = ctx["session"].get(Workflow, run.workflow_id) if run else None
    prev_run = ctx["session"].exec(select(Run).where(
        Run.workflow_id == (wf.id if wf else -1), Run.id < ctx["run_id"])
        .order_by(Run.id.desc())).first() if wf else None  # type: ignore[arg-type,union-attr]
    prev_review: dict[str, list[str]] = {}
    if prev_run:
        prev_rows = ctx["session"].exec(select(Artifact).where(
            Artifact.run_id == prev_run.id, Artifact.node_id == "D02")).all()  # type: ignore[arg-type]
        for r in prev_rows:
            meta = r.meta_json or {}
            if r.type == "PNG" and meta.get("profile") == "review" and meta.get("scene"):
                prev_review.setdefault(str(meta["scene"]), []).append(r.sha256)
        for scene in prev_review:
            prev_review[scene].sort()
    diff = []
    for scene in sorted(set(current_review) | set(prev_review)):
        cur, old = current_review.get(scene), prev_review.get(scene)
        status = ("added" if not old else "removed" if not cur
                  else "unchanged" if cur == old else "changed")
        diff.append({"scene": scene, "status": status,
                     "current": cur, "previous": old})
    _artifact_json(ctx, "review_diff.json", {
        "schema": "filmflow.review-diff/1", "runId": ctx["run_id"],
        "previousRunId": prev_run.id if prev_run else None, "scenes": diff,
        "changed": [d["scene"] for d in diff if d["status"] != "unchanged"]})


@executor("gate")
async def gate_noop(ctx):
    """人工门占位执行体：真实状态由 Approval 驱动（RunEngine 检查）。"""
    return


# ---------- E 分镜 ----------

@executor("timeline-build")
async def e01(ctx):
    task = _task_path(ctx)
    t = _read_json(task) if task.exists() else {}
    profile = _profile(ctx)
    fps = _norm_fps(profile["fps"])
    frames = profile["frames"] or frames_for(profile["duration"], fps)
    timeline = {"fps": fps, "frames": frames, "T": "frame/fps",
                "scenes": t.get("scenes", []), "events": t.get("events", [])}
    _artifact_json(ctx, "timeline.json", timeline)


@executor("camera-curves")
async def e02(ctx):
    u = _upstream_json(ctx, ["E01"])
    tl = u.get("E01") or {}
    cams = []
    for s in tl.get("scenes", []):
        if s.get("camera_keyframes"):
            cams.append({"scene": s["id"], "keyframes": s["camera_keyframes"],
                         "anchor": s.get("camera_anchor") or [960, 540],
                         "note": s.get("camera", "自定义关键帧")})
        else:
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
            base = compile_scene(s, script, tokens, profile, motion=False,
                                 asset_resolver=_asset_resolver(ctx))
            motion = compile_scene(s, script, tokens, profile,
                                   camera=cams.get(s["id"]), motion=True,
                                   asset_resolver=_asset_resolver(ctx))
            base_rel = f"scenes/{s['id']}.base.program.json"
            motion_rel = f"scenes/{s['id']}.program.json"
            for rel, prog in ((base_rel, base), (motion_rel, motion)):
                dst = _project_file(ctx, rel)
                write_atomic(dst, json.dumps(prog, ensure_ascii=False, indent=1))
            programs.append({
                "id": s["id"], "start": s.get("start", 0), "end": s.get("end", 0),
                "base_program": _project_url(ctx, base_rel),
                "base_program_sha": base["program_sha"],
                "program": _project_url(ctx, motion_rel),
                "program_sha": motion["program_sha"],
                "base_program_inline": base, "program_inline": motion,
            })
        binding.update({"schema": "filmflow.timeline-binding/2", "programs": programs})
    _artifact_json(ctx, "timeline_binding.json", binding)
    dst = _project_file(ctx, "card/timeline_binding.json")
    write_atomic(dst, json.dumps(binding, ensure_ascii=False, indent=1))
    if binding.get("programs"):
        dst2 = _project_file(ctx, "scenes/timeline_binding.json")
        write_atomic(dst2, json.dumps(binding, ensure_ascii=False, indent=1))


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
    write_atomic(dst, json.dumps(payload, ensure_ascii=False, indent=1))


def _film_spec_query(ctx, mode: str, profile: str, start: int, end: int, total: int,
                     fps: int | None = None, scale: float | None = None,
                     out_w: int | None = None, out_h: int | None = None,
                     proxy_fps: int | None = None) -> str:
    binding = quote(_project_url(ctx, "scenes/timeline_binding.json"), safe="")
    transitions = quote(_project_url(ctx, "scenes/transitions.json"), safe="")
    q = (f"mode={mode}&profile={profile}&binding={binding}&transitions={transitions}"
         f"&start={start}&end={end}&total={total}")
    if fps:
        q += f"&fps={fps}"
    if scale:
        q += f"&scale={scale}"
    if out_w:
        q += f"&outW={out_w}"
    if out_h:
        q += f"&outH={out_h}"
    if proxy_fps:
        q += f"&proxy_fps={proxy_fps}"
    return q


@executor("chrome-proxy")
async def e05(ctx):
    build = _engine_build(ctx)
    ensure_frame_server(ctx)
    profile = _profile(ctx)
    profiles = _profiles(ctx)
    review = profiles["review"]
    proxy_frames = frames_for(profile["duration"], review["fps"])
    proxy_dir = _project_file(ctx, "out/proxy")
    proxy_dir.mkdir(parents=True, exist_ok=True)
    for p in proxy_dir.glob("*.png"):
        p.unlink(missing_ok=True)
    (_project_file(ctx, "out/DONE")).unlink(missing_ok=True)
    if ctx.get("run_imported"):
        entry = _legacy_entry(build, "film")
        if not entry:
            raise RuntimeError("imported 项目缺少 legacy_entry.film")
        proxy_frames = frames_for(profile["duration"], 12)
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
                             fps=_norm_fps(review["fps"]), out_w=int(review["width"]),
                             out_h=int(review["height"]), proxy_fps=_norm_fps(review["fps"]))
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


async def _chrome_render_argv(ctx, url: str, debug_port: int | None = None) -> list[str]:
    from ...config import detect_chrome
    chrome = detect_chrome()
    if not chrome:
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENV_MISSING, "未找到 Chrome")
    argv = [chrome, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
            f"--user-data-dir=/tmp/ff-{ctx['node_id']}-{ctx['run_id']}", "--window-size=1920,1080", "--hide-scrollbars"]
    if debug_port:
        argv += [f"--remote-debugging-port={debug_port}", "--remote-debugging-address=127.0.0.1"]
    return argv + [url]


@executor("motion-qa")
async def e06(ctx):
    import numpy as np
    from PIL import Image
    profiles = _profiles(ctx)
    review = profiles["review"]
    legacy = bool(ctx.get("run_imported"))
    fps = 12 if legacy else _norm_fps(review["fps"])
    profile_label = "legacy" if legacy else "review"
    policy = {"missing": True, "black": True, "dups": True, "motion": True,
              "sync": True, "ssim": False, "lufs": False}
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
    static_thr, static_len = 0.20, max(1, round(0.5 * fps))
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
    report = {"medium": "proxy", "profile": profile_label, "fps": fps,
              "policy": policy, "pacing": "medium",
              "thresholds_used": {"static_len": static_len, "static_diff": static_thr, "cut": threshold_cut},
              "frameDiff": {"mean": round(sum(diffs) / len(diffs), 3), "p95": round(p95, 2), "max": round(max(diffs), 2)},
              "cutSpikes": cut_spikes, "staticRuns": static_runs,
              "blackFrames": [i for i, l in enumerate(lums) if l < 8], "dupFrames": [i for i, v in enumerate(diffs) if v < 0.02]}
    _artifact_json(ctx, "motion_metrics.json", report)


# ---------- F 渲染 ----------

def _artifact_sha(ctx, node_id: str) -> str:
    from sqlmodel import select

    from ...models import Artifact
    rows = ctx["session"].exec(select(Artifact).where(
        Artifact.run_id == ctx["run_id"], Artifact.node_id == node_id)).all()  # type: ignore[arg-type]
    return ";".join(sorted(a.sha256 for a in rows))


async def _run_chrome_range(ctx, url: str, frames_dir: Path, start: int, end: int, frames: int) -> int:
    import asyncio as _aio
    import time as _time
    (_project_file(ctx, "out/DONE")).unlink(missing_ok=True)
    # F02 暴露 CDP 9222：PreviewService 在同一个 Chrome 的临时 page 出预览，不新开浏览器
    argv = await _chrome_render_argv(ctx, url, debug_port=9222 if ctx["node_id"] == "F02" else None)
    node_cancel = _aio.Event()
    run_cancel = ctx["cancel_event"]
    t0 = _time.monotonic()

    async def prog(pct, msg):
        await ctx["progress"](pct, msg)

    async def _watch_done():
        while not node_cancel.is_set():
            try:
                if run_cancel is not None and run_cancel.is_set():
                    node_cancel.set(); break
                if (_project_file(ctx, "out/DONE")).exists():
                    node_cancel.set(); break
                frames_now = len(list(frames_dir.glob("*.png")))
                await ctx["progress"](min(frames_now / max(frames, 1), 0.99),
                                      f"frame {frames_now}/{frames}")
            except Exception:
                # 进度落库失败不能让 watcher 死掉；下一轮继续检查 DONE
                _log.debug("swallowed exception in _watch_done (except Exception:)", exc_info=True)
            await _aio.sleep(2)
    watcher = _aio.create_task(_watch_done())
    await ctx["runner"].run(argv, timeout=1800, on_progress=prog, cancel_event=node_cancel)
    watcher.cancel()
    missing = [i for i in range(start, end) if not (frames_dir / f"{i:04d}.png").exists()]
    if missing:
        raise RuntimeError(f"range {start}-{end} 缺 {len(missing)} 帧：{missing[:8]}…")
    return int((_time.monotonic() - t0) * 1000)


def _write_manifest(ctx, manifest: dict, artifact: bool = False) -> None:
    dst = _project_file(ctx, "renders/final/manifest.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(dst, json.dumps(manifest, ensure_ascii=False, indent=1))
    if artifact:
        _artifact_json(ctx, "render_manifest.json", manifest)


def _upsert_scene_state(ctx, scene: dict, status: str, ms: int = 0) -> None:
    from sqlmodel import select

    from ...models import SceneState
    row = ctx["session"].exec(select(SceneState).where(
        SceneState.run_id == ctx["run_id"], SceneState.scene_id == scene["id"])).first()  # type: ignore[arg-type]
    if row is None:
        row = SceneState(run_id=ctx["run_id"], scene_id=scene["id"])
    row.hash = scene.get("hash", "")
    row.status = status
    row.frame_start = scene["range"][0]
    row.frame_end = scene["range"][1]
    row.ms = ms
    ctx["session"].add(row)
    ctx["session"].commit()


async def _f02_legacy(ctx, build: dict, profile: dict, frames: int, frames_dir: Path) -> None:
    missing = [i for i in range(frames) if not (frames_dir / f"{i:04d}.png").exists()]
    if not missing:
        _artifact_json(ctx, "render_note.json", {"note": "frames 齐全，无需重渲"})
        await ctx["progress"](1.0, f"resume: 0/{frames} 缺失")
        return
    entry = _legacy_entry(build, "film")
    if not entry:
        raise RuntimeError("imported 项目缺少 legacy_entry.film")
    q = f"mode=render&start={missing[0]}&end={frames}&total={frames}"
    url = _engine_url(ctx, build, entry, q)
    await _run_chrome_range(ctx, url, frames_dir, missing[0], frames, frames)
    await ctx["progress"](1.0, f"frames {frames}/{frames}")


async def _f02_v2(ctx, build: dict, profile: dict, frames: int, frames_dir: Path) -> None:
    from ..render_manifest import build_manifest, build_plan, dirty_ranges, plan_dirty
    final_spec = _profiles(ctx)["final"]
    up = _upstream_json(ctx, ["E03", "E04"])
    binding = up.get("E03") or {}
    if not binding.get("programs"):
        binding_p = _project_file(ctx, "scenes/timeline_binding.json")
        binding = _read_json(binding_p) if binding_p.exists() else {}
    if not binding.get("programs"):
        raise RuntimeError("E_PROGRAM_INVALID: binding.programs 为空")
    transitions = (up.get("E04") or {}).get("transitions") or []
    if not transitions:
        trans_p = _project_file(ctx, "scenes/transitions.json")
        transitions = (_read_json(trans_p).get("transitions") or []) if trans_p.exists() else []
    programs = {}
    for p in binding["programs"]:
        prog_p = _project_file(ctx, f"scenes/{p['id']}.program.json")
        if prog_p.exists():
            programs[p["id"]] = _read_json(prog_p)
        elif p.get("program_inline"):
            programs[p["id"]] = p["program_inline"]
            write_atomic(prog_p, json.dumps(p["program_inline"], ensure_ascii=False, indent=1))
        else:
            raise RuntimeError(f"E_PROGRAM_INVALID: 缺 program {p['id']}")
    # font_sha 用 C02 源字体：C04 子集 CSS 随文案变化，会把所有场景误标脏
    plan = build_plan(binding.get("scenes", []), programs, transitions, profile,
                      _artifact_sha(ctx, "C05"), build["sha256"], _artifact_sha(ctx, "C02"))
    prev_p = _project_file(ctx, "renders/final/manifest.json")
    prev = _read_json(prev_p) if prev_p.exists() else None
    plan = plan_dirty(plan, prev, "final", profile)
    if ctx["params"].get("force_full"):
        for s in plan:
            s["status"] = "dirty"
    for s in plan:
        ext_start = max(0, s["range"][0] - s["overlap"])
        ext_end = min(frames, s["range"][1] + s["overlap"])
        if any(not (frames_dir / f"{i:04d}.png").exists() for i in range(ext_start, ext_end)):
            s["status"] = "dirty"
    for p in frames_dir.glob("*.png"):
        try:
            idx = int(p.stem)
        except ValueError:
            continue
        if idx >= frames:
            p.unlink()
    ranges = dirty_ranges(plan, frames)
    if not ranges:
        manifest = build_manifest(ctx["run_id"], "final", profile, plan, [], final_spec)
        _write_manifest(ctx, manifest, artifact=True)
        for s in plan:
            _upsert_scene_state(ctx, s, "done", s.get("ms", 0))
        await ctx["progress"](1.0, f"reuse {manifest['reusedFrames']}/{frames}")
        return
    completed: list[tuple[int, int, int]] = []
    failures: list[tuple[int, int, str]] = []
    for start, end in ranges:
        url = _engine_url(ctx, build, _entry(build, "film_spec"),
                          _film_spec_query(ctx, "render", "final", start, end, frames))
        try:
            ms = await _run_chrome_range(ctx, url, frames_dir, start, end, frames)
            completed.append((start, end, ms))
        except Exception as e:
            failures.append((start, end, str(e)[:300]))
        for s in plan:
            ext_start = max(0, s["range"][0] - s["overlap"])
            ext_end = min(frames, s["range"][1] + s["overlap"])
            if all((frames_dir / f"{i:04d}.png").exists() for i in range(ext_start, ext_end)):
                s["status"] = "done"
                s["ms"] = sum(ms for a, b, ms in completed if not (b <= ext_start or a >= ext_end))
        manifest = build_manifest(ctx["run_id"], "final", profile, plan, completed, final_spec)
        _write_manifest(ctx, manifest)
        for s in plan:
            _upsert_scene_state(ctx, s, s["status"], s.get("ms", 0))
    if failures:
        for s in plan:
            if s["status"] != "done":
                _upsert_scene_state(ctx, s, "failed", s.get("ms", 0))
        raise RuntimeError("E_SCENE_FAILED: " + "; ".join(f"{a}-{b}: {e}" for a, b, e in failures))
    manifest = build_manifest(ctx["run_id"], "final", profile, plan, completed, final_spec)
    _write_manifest(ctx, manifest, artifact=True)
    for s in plan:
        _upsert_scene_state(ctx, s, s["status"], s.get("ms", 0))
    await ctx["progress"](1.0, f"rendered {manifest['renderedFrames']} reused {manifest['reusedFrames']}/{frames}")


@executor("chrome-frames")
async def f02(ctx):
    lm = ctx["lock_manager"]
    await lm.check_disk(str(ctx["project_root"]), min_gb=5.0)
    build = _engine_build(ctx)
    ensure_frame_server(ctx)
    profile = _profile(ctx)
    frames = profile["frames"] or frames_for(profile["duration"], profile["fps"])
    frames_dir = _project_file(ctx, "out/frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    if ctx.get("run_imported"):
        await _f02_legacy(ctx, build, profile, frames, frames_dir)
        return
    if not _api_v2(build):
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED, "新项目缺少 Contract v2 film_spec")
    if not _entry(build, "film_spec"):
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_PROGRAM_INVALID, "新项目 film_spec 入口未登记")
    await _f02_v2(ctx, build, profile, frames, frames_dir)


@executor("frame-integrity")
async def f03(ctx):
    import numpy as np
    from PIL import Image

    from ...services.render_profiles import qa_policy
    profile = _profile(ctx)
    frames = profile["frames"] or round(profile["duration"] * profile["fps"])
    frames_dir = _project_file(ctx, "out/frames")
    manifest_p = _project_file(ctx, "renders/final/manifest.json")
    manifest = _read_json(manifest_p) if manifest_p.exists() else {}
    profile_name = manifest.get("profile") or "final"
    policy = qa_policy(profile_name)
    scenes = manifest.get("scenes") or []
    scene_by_frame = {}
    stats = {}
    for s in scenes:
        rng = s.get("range") or [0, 0]
        stats[s["id"]] = {"id": s["id"], "hash": s.get("hash", ""), "range": rng,
                          "missing": 0, "black": 0, "dups": 0}
        for i in range(int(rng[0]), int(rng[1])):
            scene_by_frame[i] = s["id"]
    missing, black, dups = [], [], 0
    prev_hash = None
    import hashlib
    n_checked = 0
    for i in range(frames):
        p = frames_dir / f"{i:04d}.png"
        sid = scene_by_frame.get(i)
        if not p.exists():
            missing.append(i)
            if sid and sid in stats:
                stats[sid]["missing"] += 1
            continue
        n_checked += 1
        img = Image.open(p)
        g = np.asarray(img.convert("L"), dtype=float)
        if float(g.mean()) < 8:
            black.append(i)
            if sid and sid in stats:
                stats[sid]["black"] += 1
        h = hashlib.sha256(g.tobytes()).hexdigest()
        if policy["dups"] and h == prev_hash:
            dups += 1
            if sid and sid in stats:
                stats[sid]["dups"] += 1
        prev_hash = h
        if n_checked % 120 == 0:
            await ctx["progress"](i / frames, f"integrity {i}/{frames}")
    scene_report = []
    for s in stats.values():
        s["status"] = "failed" if (s["missing"] or s["black"]) else "done"
        scene_report.append(s)
    if scenes:
        from sqlmodel import select

        from ...models import SceneState
        for s in scene_report:
            row = ctx["session"].exec(select(SceneState).where(
                SceneState.run_id == ctx["run_id"], SceneState.scene_id == s["id"])).first()  # type: ignore[arg-type]
            if row:
                row.status = s["status"]
                row.qa_json = s
                ctx["session"].add(row)
        ctx["session"].commit()
    # 报告先落盘再抛错：失败路径也必须留下证据（此前 raise 在写报告之前，
    # F03 一失败 frame_report.json 就不存在——被旧测试的恒真断言掩盖到 2026-11-05）。
    ratio = dups / max(frames, 1)
    # 规格 §6.2：重复帧=警告（有意停顿的影片必然有重复；§4.6 的 <0.1% 硬门与其冲突，按 §6.2 执行）
    dup_warning = ratio >= 0.001
    _artifact_json(ctx, "frame_report.json", {"frames": frames, "profile": profile_name,
                                              "policy": policy, "missing": missing,
                                              "black": black, "dups": dups,
                                              "dup_ratio": round(ratio, 4),
                                              "dup_warning": dup_warning,
                                              "scene_report": scene_report})
    if missing:
        scene_ids = sorted({scene_by_frame[i] for i in missing if i in scene_by_frame})
        raise RuntimeError(f"缺失帧 {len(missing)}：{missing[:8]}…（场景 {scene_ids}）")
    if black:
        scene_ids = sorted({scene_by_frame[i] for i in black if i in scene_by_frame})
        raise RuntimeError(f"黑帧 {len(black)}：{black[:8]}…（场景 {scene_ids}）")


@executor("ffmpeg-encode")
async def f04(ctx):
    profile = _profile(ctx)
    final = _profiles(ctx)["final"]
    fps = profile["fps"]
    out = _project_file(ctx, "out/film/intermediate.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-framerate", fps_rational(fps), "-i", str(_project_file(ctx, "out/frames/%04d.png")),
            "-c:v", "libx264", "-crf", str(ctx["params"].get("crf", final["crf"])),
            "-preset", str(ctx["params"].get("preset", final["preset"])),
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

    from ...models import Run
    from ...services.render_profiles import ensure_final_ready
    profile = _profile(ctx)
    if not ctx.get("run_imported"):
        run = ctx["session"].get(Run, ctx["run_id"])
        ensure_final_ready(ctx["session"], run, ctx["project_root"], False, profile)
    # F04 可能跨项目缓存命中：mp4 在旧项目内容寻址目录，项目内路径不存在
    mp4 = _upstream_file(ctx, "F04", "MP4", _project_file(ctx, "out/film/intermediate.mp4"))
    ff = await _ffprobe(ctx, mp4)
    expect_frames = profile["frames"] or frames_for(profile["duration"], profile["fps"])
    if abs(ff["frames"] - expect_frames) > 1:
        raise RuntimeError(f"成片帧数 {ff['frames']} ≠ {expect_frames}")
    half_frame = 0.5 / _norm_fps(profile.get("fps") or 24)
    if abs(ff["duration"] - profile["duration"]) > max(0.02, half_frame + 1e-6):
        raise RuntimeError(f"时长 {ff['duration']}s 偏差超过半帧 {half_frame:.4f}s")
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
                _log.debug("swallowed exception in f05 (except Exception:)", exc_info=True)
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
    from ...services import artifacts as art
    from ...services import audio as audio_svc
    take = audio_svc.primary_take(ctx["project_root"], "voice")
    dst = _project_file(ctx, "card/voice.wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    concat = None
    if not ctx.get("run_imported"):
        tl_p = _run_doc_file(ctx, "timeline.doc.json")
        timeline = _read_json(tl_p) if tl_p.exists() else {}
        if timeline.get("scenes"):
            concat = await asyncio.to_thread(
                audio_svc.concat_voice, ctx["project_root"], timeline["scenes"],
                float(_profile(ctx)["duration"]), dst)
    if concat:
        ap, sha = art.store_file(ctx["project_root"], dst, "WAV")
        art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha,
                     {"takeId": None, "sceneConcat": True, "picks": concat["picks"]})
        return
    src = Path(ctx["project_root"]) / take["file"] if take else Path(
        ctx["params"].get("path") or _project_file(ctx, "card/voice_raw.wav"))
    if not src.exists():
        raise RuntimeError("未上传口播音频（card/voice_raw.wav 或 audio Take）")
    if take and take.get("processedFile"):
        src = Path(ctx["project_root"]) / take["processedFile"]
    argv = ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "48000", str(dst)]
    res = await ctx["runner"].run(argv, timeout=120)
    if not res.ok:
        raise RuntimeError("口播转码失败")
    ap, sha = art.store_file(ctx["project_root"], dst, "WAV")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha,
                 {"takeId": take.get("id") if take else None,
                  "processed": bool(take and take.get("processedFile"))})


@executor("audio-align")
async def g02(ctx):
    from ...config import detect_whisper_cli, settings
    cli = detect_whisper_cli()
    model = settings.home / "models" / f"{settings.whisper_model}.bin"
    voice = _project_file(ctx, "card/voice.wav")
    if not voice.exists():
        raise RuntimeError("voice.wav 缺失")
    from ...services import audio as audio_svc
    manual = ctx["params"].get("manual_segments") or audio_svc.load_alignment(ctx["project_root"]).get("segments")
    if manual:
        # 手动对齐优先（source=manual）；whisper 缺失也走这里，不静默降级
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
    from ...services import audio as audio_svc
    take = audio_svc.primary_take(ctx["project_root"], "music")
    music = Path(ctx["params"].get("music_path") or
                 (Path(ctx["project_root"]) / take["file"] if take else _project_file(ctx, "card/music.wav")))
    if not music.exists():
        raise RuntimeError("音乐文件缺失（card/music.wav 或音频工作台 music Take）")
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
    # 解码到文件，不走 stdout 管道（大音频会写满 64KB 管道导致 ffmpeg 阻塞）
    tmp = Path(ctx["workdir"]) / "pcm.f32"
    argv = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate),
            "-f", "f32le", "-y", str(tmp)]
    res = await ctx["runner"].run(argv, timeout=300)
    if not res.ok or not tmp.exists():
        raise RuntimeError("PCM 解码失败")
    import array
    a = array.array("f")
    a.frombytes(tmp.read_bytes())
    return list(a)


def _mix_filter(duration: float, music_db: float = -8.0, target_lufs: float = -16.0,
                with_sfx: bool = False) -> str:
    d = f"{duration:.3f}"
    fade_at = f"{max(0.0, duration - 1.0):.3f}"
    fmt = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono"
    base = (f"[0:a]{fmt},apad=whole_dur={d},atrim=duration={d}[voice];"
            f"[1:a]{fmt},highpass=f=80,atrim=duration={d},afade=t=out:st={fade_at}:d=1,"
            f"volume={music_db}dB[music];"
            "[music][voice]sidechaincompress=threshold=0.03:ratio=4:attack=80:release=350[ducked];"
            "[voice][ducked]amix=inputs=2:duration=longest:normalize=0[bed];")
    if with_sfx:
        return (base +
                f"[2:a]{fmt},atrim=duration={d},apad=whole_dur={d}[sfx];"
                "[bed][sfx]amix=inputs=2:duration=longest:normalize=0,"
                f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11,aresample=48000,"
                "alimiter=limit=0.7:level=false[a]")
    return (base +
            f"[bed]loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11,aresample=48000,"
            "alimiter=limit=0.7:level=false[a]")


def _timeline_sfx(ctx) -> list[dict]:
    """从 Run 快照 timeline 读取场景 SFX，解析为绝对时间与资产路径。"""
    from ...services import assets as asset_svc
    tl_p = _run_doc_file(ctx, "timeline.doc.json")
    timeline = _read_json(tl_p) if tl_p.exists() else {}
    out = []
    for scene in timeline.get("scenes") or []:
        start = float(scene.get("start") or 0)
        for sfx in scene.get("audio_layers") or []:
            sha = str(sfx.get("assetSha") or "")
            path = asset_svc.resolve_path_for_project(ctx["session"], ctx["project_root"], sha)
            if not path or not path.exists():
                raise RuntimeError(f"E_ASSET_MISSING: SFX {sha} 缺失，请重新链接")
            out.append({**sfx, "sceneId": scene.get("id"),
                        "at": round(start + max(0.0, float(sfx.get("at") or 0)), 3),
                        "path": str(path)})
    return out


async def _build_sfx_stem(ctx, sfx: list[dict], duration: float, gain_db: float) -> dict:
    raw = _project_file(ctx, "card/stems/sfx.raw.wav")
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not sfx:
        argv = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                "-t", f"{duration:.3f}", "-ar", "48000", "-ac", "1", str(raw)]
        res = await ctx["runner"].run(argv, timeout=120)
        if not res.ok or not raw.exists():
            raise RuntimeError("静音 SFX Stem 生成失败")
    else:
        argv = ["ffmpeg", "-y"]
        for item in sfx:
            argv += ["-i", item["path"]]
        filters = []
        for i, item in enumerate(sfx):
            delay = int(round(float(item["at"]) * 1000))
            chain = (f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:"
                     f"channel_layouts=mono,volume={float(item.get('gainDb') or 0):.2f}dB")
            fi = float(item.get("fadeIn") or 0)
            fo = float(item.get("fadeOut") or 0)
            if fi > 0:
                chain += f",afade=t=in:st=0:d={fi:.3f}"
            if fo > 0:
                # 场景内剩余时长未知，按场景时间轴尾部近似
                st = max(0.0, float(item["at"]) + max(0.0, fi) - fo)
                chain += f",afade=t=out:st={st:.3f}:d={fo:.3f}"
            chain += f",adelay={delay}|{delay}[s{i}]"
            filters.append(chain)
        labels = "".join(f"[s{i}]" for i in range(len(sfx)))
        filters.append(f"{labels}amix=inputs={len(sfx)}:duration=longest:normalize=0,"
                       f"atrim=duration={duration:.3f},apad=whole_dur={duration:.3f}[sfx]")
        argv += ["-filter_complex", ";".join(filters), "-map", "[sfx]",
                 "-t", f"{duration:.3f}", "-ar", "48000", "-ac", "1", str(raw)]
        res = await ctx["runner"].run(argv, timeout=300)
        if not res.ok or not raw.exists():
            raise RuntimeError("SFX 混音失败：" + "\n".join(res.stderr_tail[-6:]))
    out = _project_file(ctx, "card/stems/sfx.wav")
    # 复用 _make_stem 的响度/裁剪与 Artifact 登记
    result = await _make_stem(ctx, raw, out, duration, gain_db=gain_db)
    raw.unlink(missing_ok=True)
    return result


async def _make_stem(ctx, src: Path, out: Path, duration: float, loop: bool = False,
                     gain_db: float = 0.0) -> dict:
    from ...services import artifacts as art
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y"]
    if loop:
        argv += ["-stream_loop", "-1"]
    argv += ["-i", str(src), "-af",
             f"apad=whole_dur={duration:.3f},atrim=duration={duration:.3f},"
             f"afade=t=out:st={max(0.0, duration - 1.0):.3f}:d=1"
             + (f",volume={gain_db}dB" if gain_db else ""),
             "-ar", "48000", "-ac", "1", str(out)]
    res = await ctx["runner"].run(argv, timeout=180)
    if not res.ok or not out.exists():
        raise RuntimeError(f"Stem 生成失败：{out.name}\n" + "\n".join(res.stderr_tail[-5:]))
    ap, sha = art.store_file(ctx["project_root"], out, "WAV")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha,
                 {"stem": out.stem})
    return {"path": str(ap), "sha256": sha, "duration": duration}


@executor("audio-mix")
async def g05(ctx):
    from ...services import audio as audio_svc
    from ...services.artifacts import register, store_file
    voice = _project_file(ctx, "card/voice.wav")
    take = audio_svc.primary_take(ctx["project_root"], "music")
    music = Path(ctx["params"].get("music_path") or
                 (Path(ctx["project_root"]) / take["file"] if take else _project_file(ctx, "card/music.wav")))
    if not voice.exists():
        raise RuntimeError("voice.wav 缺失")
    if not music.exists():
        raise RuntimeError("音乐文件缺失（card/music.wav 或音频工作台 music Take）")
    if not ctx.get("run_imported"):
        ok, why = audio_svc.license_ok(audio_svc.load_license(ctx["project_root"]))
        if not ok:
            from ...errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_LICENSE_MISSING, why, status=409)
    duration = float(_profile(ctx)["duration"])
    settings = audio_svc.load_mix(ctx["project_root"])
    music_db = float(ctx["params"].get("music_db", settings["stems"].get("music", -8.0)))
    sfx_db = float(settings["stems"].get("sfx", 0.0))
    target_lufs = float(settings.get("targetLufs", -16.0))
    sfx = _timeline_sfx(ctx)
    sfx_stem = await _build_sfx_stem(ctx, sfx, duration, sfx_db)
    out = _project_file(ctx, "card/mix.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(music)]
    if sfx:
        argv += ["-i", sfx_stem["path"]]
    argv += ["-filter_complex", _mix_filter(duration, music_db, target_lufs, with_sfx=bool(sfx)),
             "-map", "[a]", "-t", f"{duration:.3f}", "-ar", "48000", "-ac", "1", str(out)]
    res = await ctx["runner"].run(argv, timeout=300)
    if not res.ok or not out.exists():
        raise RuntimeError("混音失败：" + "\n".join(res.stderr_tail[-6:]))
    ap, sha = store_file(ctx["project_root"], out, "WAV")
    register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "WAV", str(ap), sha,
             {"mix": True, "duration": duration, "sfx": len(sfx)})
    stems = _project_file(ctx, "card/stems")
    manifest = {
        "schema": "filmflow.stems/1", "duration": duration, "targetLufs": target_lufs,
        "voice": await _make_stem(ctx, voice, stems / "voice.wav", duration,
                                  gain_db=float(settings["stems"].get("voice", 0.0))),
        "music": await _make_stem(ctx, music, stems / "music.wav", duration, loop=True, gain_db=music_db),
        "sfx": sfx_stem,
        "mix": {"path": str(ap), "sha256": sha, "duration": duration},
        "sfxCount": len(sfx),
    }
    _artifact_json(ctx, "stems_manifest.json", manifest)


@executor("audio-loudness")
async def g06(ctx):
    mix = _project_file(ctx, "card/mix.wav")
    if not mix.exists():
        raise RuntimeError("mix.wav 缺失")
    res = await ctx["runner"].run(["ffmpeg", "-i", str(mix), "-af", "ebur128=peak=true", "-f", "null", "-"], timeout=120)
    lufs = tp = None
    for line in res.stderr_tail:
        if "I:" in line and "LUFS" in line:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except Exception:
                _log.debug("swallowed exception in g06 ()", exc_info=True)
        if "Peak:" in line and "dBFS" in line:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except Exception:
                _log.debug("swallowed exception in g06 ()", exc_info=True)
        if "True peak:" in line and "dBFS" in line:
            try:
                tp = float(line.split("True peak:")[1].split("dBFS")[0].strip())
            except Exception:
                _log.debug("swallowed exception in g06 (except Exception:)", exc_info=True)
    if lufs is None:
        raise RuntimeError("ebur128 解析失败")
    from ...services import audio as audio_svc
    mix_settings = audio_svc.load_mix(ctx["project_root"])
    target = float(mix_settings.get("targetLufs", -16.0))
    if not (target - 1.0 <= lufs <= target + 1.0):
        raise RuntimeError(f"LUFS {lufs} 超出目标 {target:.0f}±1")
    if tp is not None and tp > -1.5:
        raise RuntimeError(f"True Peak {tp} > −1.5dBTP")
    # 口播-画面同步偏差：alignment.segment.end vs scene.last_text_at（不再用 abs(start-0) 伪计算）
    from ...services.render_profiles import qa_policy
    u = _upstream_json(ctx, ["G02"])
    alignment = u.get("G02") or {}
    segments = alignment.get("segments") or []
    source = alignment.get("source")
    dev = None
    sync_verified = False
    basis = "unavailable"
    if segments and source in ("whisper", "manual"):
        task_p = _task_path(ctx)
        task = _read_json(task_p) if task_p.exists() else {}
        last_times = [float(s["last_text_at"]) + float(s.get("read_seconds") or 0)
                      for s in (task.get("scenes") or [])
                      if s.get("last_text_at") is not None]
        if last_times:
            pairs = [min((abs(float(seg.get("end", 0)) - lt)
                          for seg in segments if seg.get("end") is not None), default=None)
                     for lt in last_times]
            values = [x for x in pairs if x is not None]
            if values:
                dev = max(values)
                sync_verified = True
                basis = "alignment.segment.end vs scene.last_text_at+read_seconds"
    if not ctx.get("run_imported") and sync_verified and dev is not None and dev > 0.15:
        raise RuntimeError(f"音画同步偏差 {dev:.3f}s > 0.15s（{basis}）")
    _artifact_json(ctx, "audio_metrics.json", {
        "lufs": lufs, "true_peak": tp, "target_lufs": target,
        "profile": "final", "policy": qa_policy("final"),
        "sync_dev_s": round(dev, 3) if dev is not None else None,
        "sync_verified": sync_verified, "sync_basis": basis,
        "approximate": not sync_verified})


async def _probe_av(ctx, path: Path) -> dict:
    argv = ["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)]
    res = await ctx["runner"].run(argv, timeout=60)
    if not res.ok:
        raise RuntimeError("ffprobe 失败")
    data = json.loads("\n".join(res.stdout_tail))
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    num, den = (video.get("r_frame_rate") or "0/1").split("/")
    return {"duration": round(float((data.get("format") or {}).get("duration") or 0), 3),
            "width": video.get("width"), "height": video.get("height"),
            "fps": round(int(num) / max(1, int(den)), 3) if int(den) else 0,
            "audio": any(s.get("codec_type") == "audio" for s in data.get("streams", []))}


async def _measure_loudness(ctx, path: Path) -> dict:
    res = await ctx["runner"].run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true",
         "-f", "null", "-"], timeout=300)
    text = "\n".join(res.stderr_tail)
    lufs = tp = None
    for line in text.splitlines():
        if "I:" in line and "LUFS" in line:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except ValueError:
                pass
        if "True peak:" in line and "dBFS" in line:
            try:
                tp = float(line.split("True peak:")[1].split("dBFS")[0].strip())
            except ValueError:
                pass
        if "Peak:" in line and "dBFS" in line and "True peak" not in line:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except ValueError:
                pass
    return {"lufs": round(lufs, 1) if lufs is not None else None,
            "truePeak": round(tp, 1) if tp is not None else None}


def _validate_master_qc(qc: dict, profile: dict, imported: bool, target_lufs: float = -16.0) -> None:
    if not qc["audio"]:
        raise RuntimeError("E_QC_AUDIO: master 无音轨；修复：检查 G05 混音与 G07 输入")
    if imported:
        qc["policy"] = "imported"
        return
    expected = float(profile.get("duration") or 0)
    if expected and abs(float(qc["duration"]) - expected) > 0.15:
        raise RuntimeError(
            f"E_QC_DURATION: master {qc['duration']}s ≠ profile {expected}s；"
            "修复：重跑 F04 并核对 project.profile.json")
    if (qc["width"], qc["height"]) != (profile.get("width"), profile.get("height")):
        raise RuntimeError(
            f"E_QC_RESOLUTION: master {qc['width']}×{qc['height']} ≠ "
            f"{profile.get('width')}×{profile.get('height')}；修复：重跑 F02/F04 final")
    if abs(float(qc["fps"]) - float(profile.get("fps") or qc["fps"])) > 0.01:
        raise RuntimeError(
            f"E_QC_FPS: master {qc['fps']}fps ≠ profile {profile.get('fps')}fps；"
            "修复：重跑 F04 final")
    if qc["lufs"] is None or qc["truePeak"] is None:
        raise RuntimeError("E_QC_LUFS: 无法测量响度/真峰；修复：检查 G05 输出音轨")
    if not (target_lufs - 1.0) <= qc["lufs"] <= (target_lufs + 1.0):
        raise RuntimeError(
            f"E_QC_LUFS: {qc['lufs']} LUFS 超出目标 {target_lufs:.0f}±1；"
            f"修复：在 G05 重新混音到 {target_lufs:.0f} LUFS")
    if qc["truePeak"] > -1.0:
        raise RuntimeError(
            f"E_QC_TRUE_PEAK: {qc['truePeak']} dBTP 超过 -1.0；"
            "修复：在 G05 降低峰值（alimiter 留 1dB 余量）")


@executor("package")
async def g07(ctx):
    from ...models import Run
    from ...services.render_profiles import ensure_final_ready
    if not ctx.get("run_imported"):
        run = ctx["session"].get(Run, ctx["run_id"])
        ensure_final_ready(ctx["session"], run, ctx["project_root"], False, _profile(ctx))
    video = _upstream_file(ctx, "F04", "MP4", _project_file(ctx, "out/film/intermediate.mp4"))
    mix = _project_file(ctx, "card/mix.wav")
    master = _project_file(ctx, "out/film/master.mp4")
    master.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-y", "-i", str(video), "-i", str(mix), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(master)]
    res = await ctx["runner"].run(argv, timeout=600)
    if not res.ok:
        raise RuntimeError("master 封装失败")
    from sqlmodel import select

    from ...models import Approval, Artifact
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], master, "MP4")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "MP4", str(ap), sha)
    qc = await _probe_av(ctx, master)
    qc.update(await _measure_loudness(ctx, master))
    from ...services import audio as audio_svc
    target_lufs = float(audio_svc.load_mix(ctx["project_root"]).get("targetLufs", -16.0))
    _validate_master_qc(qc, _profile(ctx), bool(ctx.get("run_imported")), target_lufs)
    _artifact_json(ctx, "qc_master.json", qc)
    approvals = ctx["session"].exec(select(Approval).where(Approval.run_id == ctx["run_id"])).all()  # type: ignore[arg-type]
    arts = ctx["session"].exec(select(Artifact).where(Artifact.run_id == ctx["run_id"])).all()  # type: ignore[arg-type]
    manifest = {"master": {"sha256": sha, "path": str(ap)},
                "qc": qc,
                "artifacts": [{"sha256": a.sha256, "type": a.type, "node": a.node_id} for a in arts],
                "approvals": [{"gate": a.gate_id, "decision": a.decision, "author": a.author,
                               "content_hash": a.content_hash, "at": str(a.created_at)} for a in approvals]}
    _artifact_json(ctx, "manifest.json", manifest)
