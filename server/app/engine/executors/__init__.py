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
    from ...services import artifacts as art
    p, sha = art.store_bytes(ctx["project_root"], json.dumps(payload, ensure_ascii=False, indent=1).encode(), "JSON")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "JSON", str(p), sha, {"name": name})
    return str(p)


def _project_file(ctx, rel: str) -> Path:
    return Path(ctx["project_root"]) / rel


def _read_json(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _run_doc_file(ctx, name: str) -> Path:
    base = ctx.get("run_docs_dir")
    return Path(base) / name if base else _project_file(ctx, "runs/__missing__") / name


def _task_path(ctx) -> Path:
    """运行时任务卡：优先 Run 快照；B06 缓存命中时快照 task 可能未落盘，回退只读导出。"""
    p = _run_doc_file(ctx, "task.json")
    if p.exists():
        return p
    card = _project_file(ctx, "card/task.json")
    if card.exists():
        return card
    return p


# ---------- A 立项 ----------

@executor("ingest-copy")
async def a01(ctx):
    script_p = _run_doc_file(ctx, "script.doc.json")
    script = _read_json(script_p) if script_p.exists() else {}
    if script.get("text"):
        raw = script["text"]
        sentences = [s.get("text", "") for s in script.get("sentences", []) if s.get("text")]
    else:
        src = Path(ctx["params"].get("path") or _project_file(ctx, "card/copy.txt"))
        if not src.exists():
            # 导入模式回退：task.json.source.copy → card/任务卡.md（作者卡片含文案全文）
            task_p = _project_file(ctx, "card/task.json")
            fallback = _read_json(task_p).get("source", {}).get("copy", "") if task_p.exists() else ""
            card_md = _project_file(ctx, "card/任务卡.md")
            if not fallback and card_md.exists():
                src = card_md
            elif fallback:
                src = _project_file(ctx, "card/copy.txt")
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_text(fallback, encoding="utf-8")
            else:
                raise ValueError("card/copy.txt 不存在且 task.json 无 source.copy、无 任务卡.md")
        raw = src.read_text(encoding="utf-8-sig")
        import re
        sentences = [s for s in re.split(r"(?<=[。！？；!?;])", raw) if s.strip()]
    payload = {"text": raw, "chars": len(raw.replace("\n", "").replace(" ", "")),
               "sentences": sentences, "sentence_count": len(sentences),
               "sha256": __import__("hashlib").sha256(raw.encode()).hexdigest()}
    _artifact_json(ctx, "copy.json", payload)
    # 同时写入项目 card/copy.txt（导入即复制 / 新项目导出）
    dst = _project_file(ctx, "card/copy.txt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(raw, encoding="utf-8")


@executor("brief-form")
async def a02(ctx):
    _artifact_json(ctx, "brief.json", ctx["params"].get("brief") or {})


@executor("style-index")
async def a03(ctx):
    import asyncio
    from ...services.style_index import scan_library
    report = await asyncio.to_thread(scan_library)
    _artifact_json(ctx, "index_report.json", report)


@executor("style-previs")
async def a04(ctx):
    """为候选生成预演（有封面跳过），输出推荐 12。"""
    from sqlmodel import select
    from ...models import Style
    from ...services import style_index as si
    from ...services.recommend import recommend
    # 保证库已索引（幂等）
    if not si.library_status()["indexed"]:
        si.scan_library()
    session, rid = ctx["session"], ctx["run_id"]
    script = ctx["params"].get("script") or ""
    recs = recommend(session, script, ctx["params"].get("brief"),
                     ctx["params"].get("constraints"), seed=int(ctx["params"].get("seed", 0)))
    from ...services import previs as pv
    from ...services import engines as eng_svc
    from ..cachekey import file_sha256
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
            from ...models import StylePreview
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
    """A06：由 style_decision 生成 visual_tokens.json；导入模式回退 task.json.style。"""
    decision_path = Path(ctx["params"].get("decision_path") or _project_file(ctx, "card/style_decision.json"))
    decision = _read_json(decision_path) if decision_path.exists() else ctx["params"].get("decision") or {}
    from ...models import Style
    st = ctx["session"].get(Style, decision.get("primary")) if decision.get("primary") else None
    if st:
        tokens = st.tokens_json or {}
    else:
        task_p = _project_file(ctx, "card/task.json")  # 导入项目：视觉系统已在任务卡内
        tokens = (_read_json(task_p).get("style") or {}) if task_p.exists() else {}
    palette = tokens.get("palette") or ["#F4EEE2", "#3D5588", "#FF665E", "#FFB511"]
    visual = {
        "style_id": decision.get("primary") or "imported", "palette": palette,
        "texture": tokens.get("texture") or ["纸纹", "网点"],
        "screen": tokens.get("screen") or {"angle": 15, "period": 7},
        "motion": tokens.get("motion") or {"pacing": "medium"},
        "type": tokens.get("type") or ["Noto Sans SC 900/500"],
        "composition": tokens.get("composition") or ["满版", "套准十字"],
        "incomplete_fields": (st.missing_fields if st else []) or
                             [k for k, v in tokens.items() if not v],
    }
    _artifact_json(ctx, "visual_tokens.json", visual)
    _artifact_json(ctx, "font_plan.json", {
        "family": "Noto Sans SC", "weights": [900, 500], "license": "OFL",
        "source": "@fontsource/noto-sans-sc",
        "all_text": _all_text_of(ctx),
    })


def _all_text_of(ctx) -> str:
    """本片字集：Run 快照文档 + 任务卡 + 文案（C03 覆盖率检查用）。"""
    parts = []
    for p in (_run_doc_file(ctx, "script.doc.json"), _run_doc_file(ctx, "timeline.doc.json"),
              _run_doc_file(ctx, "task.json")):
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    for rel in ("card/copy.txt", "card/task.json"):
        p = _project_file(ctx, rel)
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    # 组件/图表固定字符（数字、单位、标点），避免程序化组件缺字
    return "".join(parts) + "0123456789%.,:/-—·()（） " if parts else "风"


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
    from ...models import Artifact
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


def _upstream_file(ctx, node_id: str, type_: str, fallback: Path) -> Path:
    """上游文件产物优先：跨项目缓存命中时文件留在旧项目，项目内路径可能不存在。"""
    from ...models import Artifact
    from sqlmodel import select
    rows = ctx["session"].exec(select(Artifact).where(
        Artifact.run_id == ctx["run_id"], Artifact.node_id == node_id,
        Artifact.type == type_)).all()  # type: ignore[arg-type]
    for r in reversed(rows):
        p = Path(r.path)
        if p.exists():
            return p
    return fallback


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
    """场景图：imported 读快照 task.json；新项目读快照 timeline.doc，缺省则确定性构建。"""
    task_p = _task_path(ctx)
    timeline_p = _run_doc_file(ctx, "timeline.doc.json")
    if ctx.get("run_imported") and task_p.exists():
        scenes = _read_json(task_p).get("scenes", [])
    elif timeline_p.exists():
        scenes = _read_json(timeline_p).get("scenes", [])
    else:
        if task_p.exists():
            scenes = _read_json(task_p).get("scenes", [])
        else:
            draft = _project_file(ctx, "card/scenes_draft.json")
            scenes = _read_json(draft).get("scenes", []) if draft.exists() else []
        if not scenes:
            from ...services.project_docs import build_script_doc, build_timeline_doc
            script_p = _run_doc_file(ctx, "script.doc.json")
            script = _read_json(script_p) if script_p.exists() else {}
            if not script.get("sentences"):
                u = _upstream_json(ctx, ["A01"])
                script = build_script_doc((u.get("A01") or {}).get("text", ""))
            profile = ctx.get("run_profile") or {}
            if not profile:
                p = _project_file(ctx, "project.profile.json")
                profile = _read_json(p) if p.exists() else {}
            timeline = build_timeline_doc(script, profile)
            timeline_p.parent.mkdir(parents=True, exist_ok=True)
            timeline_p.write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
            scenes = timeline["scenes"]
    _artifact_json(ctx, "scenes.json", {"scenes": scenes})


@executor("event-table")
async def b03(ctx):
    task_p = _task_path(ctx)
    timeline_p = _run_doc_file(ctx, "timeline.doc.json")
    if ctx.get("run_imported") and task_p.exists():
        events = _read_json(task_p).get("events", [])
    else:
        events = _read_json(timeline_p).get("events", []) if timeline_p.exists() else []
        if not events and task_p.exists():
            events = _read_json(task_p).get("events", [])
        if not events:
            u = _upstream_json(ctx, ["B02"])
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
    import re
    u = _upstream_json(ctx, ["A06", "B04"])
    raw_family = str(((u.get("A06") or {}).get("type") or ["Noto Sans SC"])[0])
    # A06 的 type 常带字重（如 "Noto Sans SC 900/500"）；CSS font-family 必须去掉字重
    family = re.sub(r"\s+\d{3}(?:/\d{3})?.*$", "", raw_family).strip() or "Noto Sans SC"
    _artifact_json(ctx, "type_spec.json", {
        "body_min_px": 44, "title_range": [72, 120],
        "line_height": 1.35, "letter_spacing": 0,
        "family": family,
    })


@executor("task-assemble")
async def b06(ctx):
    """组装任务卡：imported 复制快照；新项目写 Run 快照 + card 只读导出。"""
    src_task = _task_path(ctx)
    if src_task.exists() and ctx.get("run_imported"):
        task = _read_json(src_task)
        run_task = _run_doc_file(ctx, "task.json")
        run_task.parent.mkdir(parents=True, exist_ok=True)
        run_task.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
        _artifact_json(ctx, "task.json", task)
        return
    u = _upstream_json(ctx, ["A01", "A02", "A06", "B01", "B02", "B03", "B04", "B05"])
    scenes = [dict(s) for s in ((u.get("B02") or {}).get("scenes") or [])]
    events = (u.get("B03") or {}).get("events") or []
    script = _read_json(_run_doc_file(ctx, "script.doc.json")) if _run_doc_file(ctx, "script.doc.json").exists() else {}
    sentences = script.get("sentences") or []
    for s in scenes:
        span = s.get("source_span") or []
        if not s.get("meaning") and span:
            s["meaning"] = "".join(sentences[i].get("text", "") for i in span
                                   if isinstance(i, int) and 0 <= i < len(sentences))
        if not s.get("operation"):
            s["operation"] = "Scene DSL 自动排版（source_span 见 script.doc）"
    profile = ctx.get("run_profile") or {}
    fps = ctx["params"].get("fps", profile.get("fps", 24))
    width = ctx["params"].get("width", profile.get("width", 1920))
    height = ctx["params"].get("height", profile.get("height", 1080))
    duration = profile.get("duration") or max((s.get("end", 0) for s in scenes), default=39.5)
    snapshot_p = _run_doc_file(ctx, "snapshot.json")
    snapshot = _read_json(snapshot_p) if snapshot_p.exists() else {}
    doc_versions = {k: (v or {}).get("version", 0) for k, v in (snapshot.get("docs") or {}).items()}
    task = {
        "schema_version": 1,
        "task_id": ctx["params"].get("task_id", Path(ctx["project_root"]).name),
        "phase": ctx["params"].get("phase", "card"),
        "actions": ["read", "write_plan", "logic_check"],
        "fps": fps, "width": width, "height": height,
        "source": {"copy": (u.get("A01") or {}).get("text", "")[:200]},
        "style": u.get("A06") or {},
        "font": u.get("B05") or {},
        "voice": u.get("A07") or {},
        "scenes": scenes, "events": events,
        "film": {"duration": duration, "frames": round(duration * fps)},
        "doc_version": doc_versions,
        "doc_hash": ctx.get("doc_snapshot_sha", ""),
        "evidence": [],
    }
    run_task = _run_doc_file(ctx, "task.json")
    run_task.parent.mkdir(parents=True, exist_ok=True)
    run_task.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    # card/task.json 是只读导出（validator/UI 兼容），运行时不再读取
    card_task = _project_file(ctx, "card/task.json")
    card_task.parent.mkdir(parents=True, exist_ok=True)
    card_task.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    _artifact_json(ctx, "task.json", task)


@executor("task-validate")
async def b07(ctx):
    """B07：调用 vendored validate_task.py（真实子进程）。"""
    task_p = _task_path(ctx)
    if not task_p.exists():
        raise ValueError("Run 快照 task.json 不存在：必须先经 B06 组装或导入")
    tool = Path(__file__).resolve().parents[3] / "tools" / "validate_task.py"
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
    from ...services import engines as eng
    engine_id = ctx["params"].get("engine_id")
    if not engine_id:
        from ...models import Style
        from sqlmodel import select
        dec = _read_json(_project_file(ctx, "card/style_decision.json")) if _project_file(ctx, "card/style_decision.json").exists() else {}
        st = ctx["session"].get(Style, dec.get("primary"))
        engine_id = (eng.engine_for_family(st.family) or {}).get("engine_id") if st else None
        if not engine_id:
            task_p = _project_file(ctx, "card/task.json")  # 导入项目回退
            engine_id = ((_read_json(task_p).get("style") or {}).get("engine_id") if task_p.exists() else None) or "riso"
    if not engine_id:
        raise RuntimeError("无法确定引擎包：主风格未选或其语义族无引擎")
    contract = eng.load_contract(engine_id)
    sha = eng.compute_pack_sha(engine_id)
    api_version = str(contract.get("api_version", "1.0"))
    if not ctx.get("run_imported") and not api_version.startswith("2"):
        from ...errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENGINE_API_UNSUPPORTED,
                       f"引擎 {engine_id} 是 Contract {api_version}，R2.0 新项目需要 2.x（film_spec）")
    missing_fx = [f for f in contract.get("fixtures", []) if not (eng.engines_root() / engine_id / f).exists()]
    if missing_fx:
        raise RuntimeError(f"引擎 fixture 缺失：{missing_fx}")
    if api_version.startswith("2"):
        from ..scene.components import COMPONENT_NAMES
        caps = contract.get("capabilities") or {}
        declared = set((caps.get("components") if isinstance(caps, dict) else []) or [])
        if declared != set(COMPONENT_NAMES):
            raise RuntimeError(f"Contract v2 组件声明与 scene-kit 不一致：{sorted(declared)}")
        kit = eng.engines_root() / engine_id / "fixture/scene-kit.json"
        if not kit.exists():
            raise RuntimeError("scene-kit fixture 缺失：fixture/scene-kit.json")
        kit_data = _read_json(kit)
        if len(kit_data.get("components", [])) != 12:
            raise RuntimeError("scene-kit fixture 必须覆盖 12 组件")
    _artifact_json(ctx, "engine_build.json", {
        "engine_id": engine_id, "sha256": sha, "api_version": api_version,
        "scene_schema": contract.get("scene_schema"),
        "entry": contract["entry"], "legacy_entry": contract.get("legacy_entry") or {},
        "capabilities": contract["capabilities"], "fixture_check": "structure"})


@executor("font-fetch")
async def c02(ctx):
    """获取 Noto Sans SC 变量字体（Google Fonts 官方仓，含 CJK+拉丁+希腊全子集）。"""
    import shutil
    from ...config import settings
    url = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
    d = _project_file(ctx, "fonts/src")
    d.mkdir(parents=True, exist_ok=True)
    ttf = d / "NotoSansSC[wght].ttf"
    cache = settings.home / "cache" / "fonts" / "NotoSansSC[wght].ttf"
    min_bytes = 5_000_000
    if not ttf.exists() and cache.exists() and cache.stat().st_size >= min_bytes:
        shutil.copyfile(cache, ttf)
    if not ttf.exists():
        # 本地既有 C02 产物（内容寻址，跨项目）优先，避免无网环境阻塞
        from ...models import Artifact
        from sqlmodel import select
        rows = ctx["session"].exec(select(Artifact).where(
            Artifact.node_id == "C02", Artifact.type == "TXT").order_by(Artifact.id.desc())).all()  # type: ignore[arg-type]
        for r in rows:
            p = Path(r.path)
            if p.exists() and p.stat().st_size >= min_bytes:
                shutil.copyfile(p, ttf)
                break
    if not ttf.exists():
        res = await ctx["runner"].run(
            ["curl", "-L", "--fail", "--max-time", "120", "-o", str(ttf), url], timeout=180)
        if not res.ok or not ttf.exists() or ttf.stat().st_size < min_bytes:
            raise RuntimeError("变量字体下载失败：" + "\n".join(res.stderr_tail[-3:]))
    if not cache.exists() or cache.stat().st_size < min_bytes:
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ttf, cache)
    from ...services.artifacts import store_file, register
    ap, sha = store_file(ctx["project_root"], ttf, "TXT")
    register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "TXT", str(ap), sha,
             {"source": url, "bytes": ttf.stat().st_size})
    _artifact_json(ctx, "font_fetch_report.json", {"source": url, "sha256": sha,
                                                   "bytes": ttf.stat().st_size, "artifact_path": str(ap)})


@executor("font-subset")
async def c03(ctx):
    """变量字体 → instancer(900/500) → pyftsubset → 2 个 woff2；覆盖率检查 0 缺字（自动门）。"""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    from fontTools.subset import Subsetter, Options
    # C02 跨项目缓存命中时，源字体在旧项目的内容寻址产物里；优先读报告/DB 里的产物路径
    c02 = (_upstream_json(ctx, ["C02"]).get("C02") or {})
    src_path = c02.get("artifact_path")
    if not src_path:
        from sqlmodel import select
        from ...models import Artifact
        rows = ctx["session"].exec(select(Artifact).where(
            Artifact.run_id == ctx["run_id"], Artifact.node_id == "C02",
            Artifact.type == "TXT")).all()  # type: ignore[arg-type]
        src_path = rows[-1].path if rows else None
    src_ttf = Path(src_path or _project_file(ctx, "fonts/src/NotoSansSC[wght].ttf"))
    if not src_ttf.exists():
        raise RuntimeError("变量字体缺失：先运行 C02")
    all_text = _all_text_of(ctx)
    needed = {ch for ch in all_text if ch == " " or not ch.isspace()}
    def _build(weight: int) -> dict:
        font = TTFont(str(src_ttf))
        instantiateVariableFont(font, {"wght": weight}, inplace=True)
        opts = Options()
        opts.flavor = "woff2"
        ss = Subsetter(options=opts)
        ss.populate(text="".join(sorted(needed)))
        ss.subset(font)
        dst = _project_file(ctx, f"fonts/noto-sans-sc-sub-{weight}.woff2")
        dst.parent.mkdir(parents=True, exist_ok=True)
        font.flavor = "woff2"
        font.save(str(dst))
        font.close()
        f2 = TTFont(str(dst))
        cmap = f2.getBestCmap()
        missing = [c for c in sorted(needed) if ord(c) not in cmap]
        if missing:
            raise RuntimeError("字体缺字：" + " ".join(missing[:20]))
        return {"file": str(dst), "glyphs": len(needed)}

    out = {}
    for weight in (900, 500):
        out[weight] = await asyncio.to_thread(_build, weight)   # CPU 密集，勿阻塞事件循环
    _artifact_json(ctx, "font_subset_report.json", {"weights": list(out), "missing": [],
                                                    **{f"w{w}": v for w, v in out.items()}})


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
    # 上限来自 profile（规格 §4.3 的 60KB 是参考项目 82 字子集的特例标定；ADR-0003：
    # 变量字体子集含场景全文，默认上限放宽为 512KB，可在 profile.embed_max_kb 调整）
    profile_p = _project_file(ctx, "project.profile.json")
    max_kb = 512
    if profile_p.exists():
        max_kb = int(_read_json(profile_p).get("embed_max_kb", 512))
    if len(css) > max_kb * 1024:
        raise RuntimeError(f"embed.css 超 {max_kb}KB（{len(css)//1024}KB）；可在 profile.embed_max_kb 调整")
    dst = _project_file(ctx, "fonts/embed.css")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(css, encoding="utf-8")
    from ...services import artifacts as art
    ap, sha = art.store_file(ctx["project_root"], dst, "CSS")
    art.register(ctx["session"], ctx["run_id"], ctx["node_run_id"], ctx["node_id"], "CSS", str(ap), sha)


@executor("tokens-lock")
async def c05(ctx):
    u = _upstream_json(ctx, ["A06", "B04", "B05"])
    lock = {"visual": u.get("A06") or {}, "layout": u.get("B04") or {},
            "type_spec": u.get("B05") or {}, "locked_at": ctx.get("now", "")}
    _artifact_json(ctx, "tokens.lock.json", lock)
    dst = _project_file(ctx, "card/tokens.lock.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(lock, ensure_ascii=False, indent=1), encoding="utf-8")


# 注册 D–G 阶段执行器（必须在 helpers 定义之后导入，避免循环引用）
from . import pipeline as _pipeline  # noqa: E402,F401
