"""46 执行器注册表（tech-plan §3）：executor 名 → 协程。

ctx: {"run_id","node_id","node_run_id","params","workdir","session","project_root",
      "emit","progress","runner","cancel_event","engine_pkg"}
每个执行器真实执行（规格 §15.10 无 mock 生产路径）；产物经 services.artifacts 登记。
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

REGISTRY: dict[str, object] = {}


def executor(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


# ---------- 帮助函数 ----------

def _artifact_json(ctx, name: str, payload: dict) -> str:
    from ..services import artifacts as art
    p, sha = art.store_bytes(ctx["project_root"], json.dumps(payload, ensure_ascii=False, indent=1).encode(), "JSON")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "JSON", str(p), sha, {"name": name})
    return str(p)


def _project_file(ctx, rel: str) -> Path:
    return Path(ctx["project_root"]) / rel


def _read_json(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------- A 立项 ----------

@executor("ingest-copy")
async def a01(ctx):
    src = Path(ctx["params"].get("path") or _project_file(ctx, "card/copy.txt"))
    raw = src.read_text(encoding="utf-8-sig")
    import re
    sentences = [s for s in re.split(r"(?<=[。！？；!?;])", raw) if s.strip()]
    payload = {"text": raw, "chars": len(raw.replace("\n", "").replace(" ", "")),
               "sentences": sentences, "sentence_count": len(sentences),
               "sha256": __import__("hashlib").sha256(raw.encode()).hexdigest()}
    _artifact_json(ctx, "copy.json", payload)
    # 同时写入项目 card/copy.txt（导入即复制）
    dst = _project_file(ctx, "card/copy.txt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(raw, encoding="utf-8")


@executor("brief-form")
async def a02(ctx):
    _artifact_json(ctx, "brief.json", ctx["params"].get("brief") or {})


@executor("style-index")
async def a03(ctx):
    from ..services.style_index import scan_library
    report = scan_library()
    _artifact_json(ctx, "index_report.json", report)


@executor("style-previs")
async def a04(ctx):
    """为候选生成预演（有封面跳过），输出推荐 12。"""
    from sqlmodel import select
    from ..models import Style
    from ..services import style_index as si
    from ..services.recommend import recommend
    # 保证库已索引（幂等）
    if not si.library_status()["indexed"]:
        si.scan_library()
    session, rid = ctx["session"], ctx["run_id"]
    script = ctx["params"].get("script") or ""
    recs = recommend(session, script, ctx["params"].get("brief"),
                     ctx["params"].get("constraints"), seed=int(ctx["params"].get("seed", 0)))
    from ..services import previs as pv
    from ..services import engines as eng_svc
    from ..engine.cachekey import file_sha256
    for r in recs:
        st = session.get(Style, r["style_id"])
        if not st or st.has_cover or st.tokens_status != "complete":
            continue
        eng = eng_svc.engine_for_family(st.family)
        if not eng:
            continue
        esha = eng_svc.compute_pack_sha(eng["engine_id"])
        try:
            out = await pv.render_previs(st.id, eng["engine_id"], esha, st.tokens_json, variant="thumb")
            from ..models import StylePreview
            existing = session.exec(select(StylePreview).where(
                StylePreview.style_id == st.id, StylePreview.variant == "thumb")).all()
            sha = file_sha256(str(out))
            if not any(p.sha256 == sha and p.engine_sha == esha for p in existing):
                session.add(StylePreview(style_id=st.id, variant="thumb", path=str(out), sha256=sha,
                                         engine_sha=esha, renderer_ver=pv.RENDERER_VER))
                st.preview_status = "previs"
                session.add(st)
                session.commit()
        except Exception:
            st.preview_status = "failed"
            session.add(st)
            session.commit()
    _artifact_json(ctx, "recommend.json", {"recommendations": recs, "script_chars": len(script)})


@executor("token-extract")
async def a06(ctx):
    """A06：由 style_decision 生成 visual_tokens.json + font_plan.json。"""
    decision_path = Path(ctx["params"].get("decision_path") or _project_file(ctx, "card/style_decision.json"))
    decision = _read_json(decision_path) if decision_path.exists() else ctx["params"].get("decision") or {}
    from ..models import Style
    st = ctx["session"].get(Style, decision.get("primary"))
    if not st:
        raise ValueError(f"style_decision.primary {decision.get('primary')} 不在库中")
    tokens = st.tokens_json or {}
    palette = tokens.get("palette") or ["#F4EEE2", "#3D5588", "#FF665E", "#FFB511"]
    visual = {
        "style_id": st.id, "palette": palette,
        "texture": tokens.get("texture") or ["纸纹", "网点"],
        "screen": tokens.get("screen") or {"angle": 15, "period": 7},
        "motion": tokens.get("motion") or {"pacing": "medium"},
        "type": tokens.get("type") or ["Noto Sans SC 900/500"],
        "composition": tokens.get("composition") or ["满版", "套准十字"],
        "incomplete_fields": st.missing_fields,
    }
    _artifact_json(ctx, "visual_tokens.json", visual)
    _artifact_json(ctx, "font_plan.json", {
        "family": "Noto Sans SC", "weights": [900, 500], "license": "OFL",
        "source": "@fontsource/noto-sans-sc",
        "all_text": _all_text_of(ctx),
    })


def _all_text_of(ctx) -> str:
    """本片字集：文案 + 任务卡文字（C03 覆盖率检查用）。"""
    parts = []
    for rel in ("card/copy.txt", "card/task.json"):
        p = _project_file(ctx, rel)
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "".join(parts) or "风"


@executor("voice-plan")
async def a07(ctx):
    p = dict(ctx["params"].get("voice_plan") or {"mode": "待录", "rate_per_sec": 5.2})
    _artifact_json(ctx, "voice_plan.json", p)


@executor("music-plan")
async def a08(ctx):
    cands = ctx["params"].get("candidates") or [
        {"name": "候选A", "mood": "克制"}, {"name": "候选B", "mood": "冷静"},
        {"name": "候选C", "mood": "推进"}, {"name": "候选D", "mood": "收束"}]
    _artifact_json(ctx, "music_plan.json", {"candidates": cands})


# ---------- B 卡片 ----------

def _upstream_json(ctx, names: list[str]) -> dict:
    """读取上游产物 JSON（按名称在 workdir 树中查找太贵 → 用 run 级索引）。"""
    from ..models import Artifact
    out = {}
    for nid in names:
        rows = ctx["session"].exec(
            __import__("sqlmodel").select(Artifact).where(
                Artifact.run_id == ctx["run_id"], Artifact.node_id == nid)  # type: ignore[arg-type]
        ).all()
        for r in rows:
            p = Path(r.path)
            if p.exists() and p.suffix == ".json":
                out.setdefault(nid, _read_json(p))
    return out


@executor("duration-budget")
async def b01(ctx):
    u = _upstream_json(ctx, ["A01", "A07"])
    copy = u.get("A01", {})
    rate = (u.get("A07", {}) or {}).get("rate_per_sec", 5.2)
    sentences = copy.get("sentences") or []
    budget = [{"sentence": s, "seconds": round(max(len(s) / rate, 0.8), 2)} for s in sentences]
    total = round(sum(b["seconds"] for b in budget), 2)
    _artifact_json(ctx, "budget.json", {"per_sentence": budget, "total_seconds": total,
                                        "target": ctx["params"].get("target_seconds", total)})


@executor("scene-graph")
async def b02(ctx):
    """场景图：导入项目 → 直接用 task.json；新项目 → 编辑器草稿或句号模板。"""
    task_p = _project_file(ctx, "card/task.json")
    if task_p.exists():
        scenes = _read_json(task_p).get("scenes", [])
    else:
        draft = _project_file(ctx, "card/scenes_draft.json")
        scenes = _read_json(draft).get("scenes", []) if draft.exists() else []
        if not scenes:
            u = _upstream_json(ctx, ["A01", "B01"])
            budget = (u.get("B01") or {}).get("per_sentence") or []
            n = max(4, min(6, len(budget)))
            per = max(1, len(budget) // n)
            scenes, t = [], 0.0
            for i in range(n):
                chunk = budget[i * per:(i + 1) * per] or [{"seconds": 2}]
                dur = round(sum(c["seconds"] for c in chunk), 2)
                scenes.append({"id": f"S{i+1:02d}", "start": t, "end": round(t + dur, 2),
                               "time_basis": "planned", "meaning": "", "operation": "",
                               "last_text_at": t, "read_seconds": dur})
                t = round(t + dur, 2)
    _artifact_json(ctx, "scenes.json", {"scenes": scenes})


@executor("event-table")
async def b03(ctx):
    task_p = _project_file(ctx, "card/task.json")
    if task_p.exists():
        events = _read_json(task_p).get("events", [])
    else:
        u = _upstream_json(ctx, ["B02"])
        events = []
        for s in (u.get("B02") or {}).get("scenes", []):
            events.append({"id": f"E{len(events)+1:02d}", "scene_id": s["id"], "at": s["start"],
                           "time_basis": "planned", "role": "scene_start", "allow_snap": False})
    _artifact_json(ctx, "events.json", {"events": events})


@executor("layout-tokens")
async def b04(ctx):
    u = _upstream_json(ctx, ["A06"])
    visual = u.get("A06") or {}
    layout = {
        "grid": ctx["params"].get("grid", {"cols": 12, "margin_pct": {"w": 0.05, "h": 0.08}}),
        "safe_area": ctx["params"].get("safe_area", {"w": 0.05, "h": 0.08}),
        "registration_mark": [1768, 128],
        "plates": len((visual.get("palette") or [1, 2, 3])),
        "per_scene_style": ctx["params"].get("per_scene_style", {}),
    }
    _artifact_json(ctx, "layout_tokens.json", layout)
    if layout["per_scene_style"]:
        _artifact_json(ctx, "per_scene_style.json", layout["per_scene_style"])


@executor("type-spec")
async def b05(ctx):
    u = _upstream_json(ctx, ["A06", "B04"])
    _artifact_json(ctx, "type_spec.json", {
        "body_min_px": 44, "title_range": [72, 120],
        "line_height": 1.35, "letter_spacing": 0,
        "family": ((u.get("A06") or {}).get("type") or ["Noto Sans SC"])[0],
    })


@executor("task-assemble")
async def b06(ctx):
    """组装 card/task.json。导入项目：以现有 task.json 为准（保留 phase/actions）。"""
    task_p = _project_file(ctx, "card/task.json")
    if task_p.exists() and ctx["params"].get("mode") == "import":
        _artifact_json(ctx, "task.json", _read_json(task_p))
        return
    u = _upstream_json(ctx, ["A01", "A02", "A06", "B01", "B02", "B03", "B04", "B05"])
    scenes = (u.get("B02") or {}).get("scenes") or []
    events = (u.get("B03") or {}).get("events") or []
    duration = max((s.get("end", 0) for s in scenes), default=39.5)
    fps = ctx["params"].get("fps", 24)
    task = {
        "schema_version": 1,
        "task_id": ctx["params"].get("task_id", Path(ctx["project_root"]).name),
        "phase": ctx["params"].get("phase", "card"),
        "actions": ["read", "write_plan", "logic_check"],
        "fps": fps, "width": ctx["params"].get("width", 1920), "height": ctx["params"].get("height", 1080),
        "source": {"copy": (u.get("A01") or {}).get("text", "")[:200]},
        "style": u.get("A06") or {},
        "font": u.get("B05") or {},
        "voice": u.get("A07") or {},
        "scenes": scenes, "events": events,
        "film": {"duration": duration, "frames": round(duration * fps)},
        "evidence": [],
    }
    task_p.parent.mkdir(parents=True, exist_ok=True)
    task_p.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    _artifact_json(ctx, "task.json", task)


@executor("task-validate")
async def b07(ctx):
    """B07：调用 vendored validate_task.py（真实子进程）。"""
    task_p = _project_file(ctx, "card/task.json")
    if not task_p.exists():
        raise ValueError("card/task.json 不存在：必须先经任务卡编辑器或导入")
    tool = Path(__file__).resolve().parents[3] / "server" / "tools" / "validate_task.py"
    out = Path(ctx["workdir"]) / "validate_report.json"
    runner = ctx["runner"]
    res = await runner.run(["python3", str(tool), str(task_p), "--out", str(out)], timeout=120)
    if not res.ok or not out.exists():
        raise RuntimeError("validate_task.py 失败：" + "\n".join(res.stderr_tail[-10:]))
    report = _read_json(out)
    if not report.get("passed"):
        raise RuntimeError("任务卡校验未通过：" + json.dumps(report.get("errors", []), ensure_ascii=False))
    _artifact_json(ctx, "validate_report.json", report)


# ---------- C 资产 ----------

@executor("engine-compile")
async def c01(ctx):
    from ..services import engines as eng
    engine_id = ctx["params"].get("engine_id")
    if not engine_id:
        from ..models import Style
        from sqlmodel import select
        dec = _read_json(_project_file(ctx, "card/style_decision.json")) if _project_file(ctx, "card/style_decision.json").exists() else {}
        st = ctx["session"].get(Style, dec.get("primary"))
        engine_id = (eng.engine_for_family(st.family) or {}).get("engine_id") if st else None
    if not engine_id:
        raise RuntimeError("无法确定引擎包：主风格未选或其语义族无引擎")
    contract = eng.load_contract(engine_id)
    sha = eng.compute_pack_sha(engine_id)
    missing_fx = [f for f in contract.get("fixtures", []) if not (eng.engines_root() / engine_id / f).exists()]
    if missing_fx:
        raise RuntimeError(f"引擎 fixture 缺失：{missing_fx}")
    _artifact_json(ctx, "engine_build.json", {"engine_id": engine_id, "sha256": sha,
                                              "entry": contract["entry"], "capabilities": contract["capabilities"],
                                              "fixture_check": "structure"})


@executor("font-fetch")
async def c02(ctx):
    """从 @fontsource/noto-sans-sc 提取 woff2（网络或本地 node_modules 缓存）。"""
    fonts_dir = _project_file(ctx, "fonts/src")
    fonts_dir.mkdir(parents=True, exist_ok=True)
    target = fonts_dir / "@fontsource"
    if not target.exists():
        try:
            subprocess.run(["pnpm", "dlx", "npm-packlist"], capture_output=True, timeout=10)
        except Exception:
            pass
        # 真实获取：npm pack @fontsource/noto-sans-sc
        res = subprocess.run(["npm", "pack", "@fontsource/noto-sans-sc", "--pack-destination", str(fonts_dir)],
                             capture_output=True, text=True, timeout=600, cwd=str(fonts_dir))
        if res.returncode != 0:
            raise RuntimeError("npm pack 失败：" + res.stderr[-400:])
        tgz = sorted(fonts_dir.glob("*.tgz"))[-1]
        subprocess.run(["tar", "xzf", tgz.name, "-C", str(fonts_dir)], cwd=str(fonts_dir), timeout=120, check=True)
    files = list((fonts_dir / "package" / "files").glob("*.woff2")) if (fonts_dir / "package").exists() else []
    if not files:
        raise RuntimeError("@fontsource 包内未找到 woff2")
    _artifact_json(ctx, "font_fetch_report.json", {"files": len(files), "dir": str(fonts_dir / "package" / "files")})


@executor("font-subset")
async def c03(ctx):
    """pyftsubset 子集化 900/500，覆盖率检查 0 缺字（自动门）。"""
    from fontTools.subset import Subsetter, Options, load_font, save_font  # type: ignore
    from fontTools.ttLib import TTFont  # type: ignore
    fonts_dir = _project_file(ctx, "fonts/src/package/files")
    if not fonts_dir.exists():
        raise RuntimeError("字体源缺失：先运行 C02")
    all_text = _all_text_of(ctx)
    out = {}
    for weight in (900, 500):
        cands = sorted(fonts_dir.glob(f"*{weight}*.woff2")) or sorted(fonts_dir.glob(f"*{weight}*.woff"))
        if not cands:
            raise RuntimeError(f"未找到 {weight} 字重字体文件")
        src = cands[0]
        opts = Options()
        opts.flavor = "woff2"
        font = TTFont(str(src))
        ss = Subsetter(options=opts)
        ss.populate(text=all_text)
        ss.subset(font)
        dst = _project_file(ctx, f"fonts/noto-sans-sc-sub-{weight}.woff2")
        font.flavor = "woff2"
        font.save(str(dst))
        out[weight] = str(dst)
    # 覆盖率检查
    missing = []
    for weight, p in out.items():
        f = TTFont(str(p))
        cmap = f.getBestCmap()
        for ch in set(all_text):
            if ord(ch) not in cmap:
                missing.append(ch)
    if missing:
        raise RuntimeError("字体缺字：" + " ".join(sorted(set(missing))[:20]))
    _artifact_json(ctx, "font_subset_report.json", {"weights": list(out), "missing": [], "glyphs": len(set(all_text))})


@executor("font-embed")
async def c04(ctx):
    import base64
    css_parts = []
    for weight in (900, 500):
        p = _project_file(ctx, f"fonts/noto-sans-sc-sub-{weight}.woff2")
        b64 = base64.b64encode(p.read_bytes()).decode()
        css_parts.append(
            f"@font-face{{font-family:'Noto Sans SC';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    css = "\n".join(css_parts)
    if len(css) > 60 * 1024:
        raise RuntimeError(f"embed.css 超 60KB（{len(css)//1024}KB）")
    dst = _project_file(ctx, "fonts/embed.css")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(css, encoding="utf-8")
    from ..services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], dst, "CSS")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "CSS", str(ap), sha)


@executor("tokens-lock")
async def c05(ctx):
    u = _upstream_json(ctx, ["A06", "B04"])
    lock = {"visual": u.get("A06") or {}, "layout": u.get("B04") or {}, "locked_at": ctx.get("now", "")}
    _artifact_json(ctx, "tokens.lock.json", lock)
    dst = _project_file(ctx, "card/tokens.lock.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(lock, ensure_ascii=False, indent=1), encoding="utf-8")


# 注册 D–G 阶段执行器（必须在 helpers 定义之后导入，避免循环引用）
from . import pipeline as _pipeline  # noqa: E402,F401
