"""FR-28 交付 v1：16:9 + 9:16 master、SRT、双封面、manifest/qc/rights/zip。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import detect_chrome
from ..engine.scene.compiler import compile_scene
from ..models import Approval, Artifact, Job, NodeRun, Project, Run
from . import audio as audio_svc
from . import engines as engines_svc
from . import jobs as jobs_svc
from . import preview as pv
from . import project_docs as docs_svc
from . import takes as takes_svc
from .render_profiles import ensure_final_ready


@dataclass(frozen=True)
class Variant:
    id: str
    width: int
    height: int


V16 = Variant("16x9", 1920, 1080)
V9 = Variant("9x16", 1080, 1920)
MAX_CAPTION_CHARS = 16
MAX_CAPTION_CPS = 9.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_cmd(argv: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _probe(path: Path) -> dict:
    res = _run_cmd(["ffprobe", "-v", "error", "-show_entries",
                    "stream=codec_type,codec_name,width,height,r_frame_rate,bit_rate:format=duration,size",
                    "-of", "json", str(path)], 60)
    data = json.loads(res.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, den = (video.get("r_frame_rate") or "0/1").split("/")
    return {"width": video.get("width"), "height": video.get("height"),
            "fps": round(int(num) / max(1, int(den)), 3) if int(den) else 0,
            "duration": round(float((data.get("format") or {}).get("duration") or 0), 3),
            "size": int((data.get("format") or {}).get("size") or 0),
            "videoCodec": video.get("codec_name"), "audioCodec": audio.get("codec_name"),
            "bitrate": int((data.get("format") or {}).get("bit_rate") or 0)}


def _loudness(path: Path) -> dict:
    res = _run_cmd(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true",
                    "-f", "null", "-"], 300)
    lufs = tp = None
    for line in res.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except Exception:
                pass
        if "True peak:" in line and "dBFS" in line:
            try:
                tp = float(line.split("True peak:")[1].split("dBFS")[0].strip())
            except Exception:
                pass
        if "Peak:" in line and "dBFS" in line and "True peak" not in line:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except Exception:
                pass
    return {"lufs": lufs, "truePeak": tp}


def _wrap(text: str, max_chars: int = MAX_CAPTION_CHARS) -> str:
    lines, line = [], ""
    for ch in str(text or ""):
        if ch == "\n":
            lines.append(line); line = ""; continue
        if len(line) >= max_chars:
            lines.append(line); line = ""
        line += ch
    if line:
        lines.append(line)
    return "\n".join(lines) or str(text or "")


def _ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _srt(segments: list[dict]) -> tuple[str, dict]:
    out, max_chars, max_cps = [], 0, 0.0
    for i, seg in enumerate(segments, 1):
        text = str(seg.get("text") or "")
        start, end = float(seg.get("start") or 0), float(seg.get("end") or 0)
        if end <= start or not text:
            continue
        wrapped = _wrap(text)
        max_chars = max(max_chars, max(len(x) for x in wrapped.splitlines()))
        max_cps = max(max_cps, len(text.replace("\n", "")) / max(0.001, end - start))
        out.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{wrapped}\n")
    return "\n".join(out), {"count": len(out), "maxLineChars": max_chars,
                            "maxCharsPerSec": round(max_cps, 2)}


def _alignment(session: Session, root: Path, run: Run, task: dict,
               project_id: int) -> tuple[list[dict], str]:
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == run.id, Artifact.node_id == "G02", Artifact.type == "JSON")).all()  # type: ignore[arg-type]
    for a in reversed(rows):
        try:
            d = json.loads(Path(a.path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("segments"):
            return d["segments"], d.get("source") or "alignment"
    manual = audio_svc.load_alignment(root)
    if manual.get("segments"):
        return manual["segments"], "manual"
    segments = []
    for s in task.get("scenes", []):
        text = s.get("meaning") or ""
        if text:
            segments.append({"text": text, "start": float(s.get("start", 0)),
                             "end": float(s.get("end", 0))})
    return segments, "planned"


def _title(session: Session, project: Project) -> str:
    script = docs_svc.doc_payload(session, project.id or 0, project.root, "script")["content"]
    return str(script.get("title") or "").strip() or \
        (script.get("sentences") or [{}])[0].get("text", "").strip()


def _font(size: int):
    from PIL import ImageFont
    candidates = [Path.home() / ".filmflow/cache/fonts/NotoSansSC[wght].ttf",
                  Path.home() / "Library/Fonts/NotoSansSC[wght].ttf"]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _cover(src: Path, dst: Path, width: int, height: int, title: str) -> None:
    from PIL import Image, ImageDraw
    img = Image.open(src).convert("RGB")
    img = img.resize((width, height), Image.LANCZOS)
    if title:
        draw = ImageDraw.Draw(img, "RGBA")
        size = max(42, int(width * 0.065))
        font = _font(size)
        lines = _wrap(title, 14 if width < 1400 else 18).splitlines()[:4]
        line_h = int(size * 1.25)
        box_h = line_h * len(lines) + 40
        draw.rounded_rectangle([40, height - box_h - 40, width - 40, height - 40],
                               radius=10, fill=(0, 0, 0, 150))
        for i, line in enumerate(lines):
            draw.text((60, height - box_h - 20 + i * line_h), line, fill=(255, 255, 255, 245), font=font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=92)


def _variant_programs(ctx: pv.PreviewContext, variant: Variant) -> tuple[list[dict], dict]:
    profile = {**ctx.profile, "width": variant.width, "height": variant.height}
    out = []
    for s in ctx.scenes:
        prog = compile_scene(s, ctx.script, ctx.tokens, profile,
                             camera=pv._camera(s, profile), motion=True, layout=variant.id)
        out.append({"id": s["id"], "start": float(s.get("start", 0)),
                    "end": float(s.get("end", 0)), "program": prog})
    return out, profile


async def _render_variant_frames(job_id: int, ctx: pv.PreviewContext, variant: Variant,
                                 frames_dir: Path) -> dict:
    programs, profile = _variant_programs(ctx, variant)
    fps = int(ctx.profile.get("fps") or 24)
    duration = float(ctx.profile.get("duration") or 0)
    frames = round(duration * fps)
    payload = {"programs": programs, "transitions": ctx.transitions,
               "width": variant.width, "height": variant.height, "scale": 1,
               "fontCss": ctx.font_css}
    frames_dir.mkdir(parents=True, exist_ok=True)
    async with pv.PreviewRenderer() as renderer:
        await renderer.init(payload)
        for i in range(frames):
            png = await renderer.frame(i / fps)
            (frames_dir / f"{i:06d}.png").write_bytes(png)
            if i % 20 == 0:
                from ..db import engine as db_engine
                with Session(db_engine) as s:
                    jobs_svc.update_job(s, job_id, progress=0.15 + 0.35 * i / max(1, frames))
    return {"frames": frames, "fps": fps, "profile": profile}


def _mux(video: Path, mix: Path | None, out: Path, width: int, height: int,
         fps: int, crf: int = 19, preset: str = "medium") -> None:
    argv = ["ffmpeg", "-y", "-i", str(video)]
    if mix:
        argv += ["-i", str(mix)]
    argv += ["-vf", f"scale={width}:{height}:flags=lanczos", "-c:v", "libx264",
             "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p"]
    if mix:
        argv += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    argv += ["-movflags", "+faststart", str(out)]
    res = _run_cmd(argv, 900)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError("编码失败：" + res.stderr[-800:])


def _encode_frames(pattern: Path, mix: Path | None, out: Path, width: int, height: int,
                   fps: int, crf: int = 19, preset: str = "medium") -> None:
    argv = ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(pattern)]
    if mix:
        argv += ["-i", str(mix)]
    argv += ["-vf", f"scale={width}:{height}:flags=lanczos", "-c:v", "libx264",
             "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p"]
    if mix:
        argv += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    argv += ["-movflags", "+faststart", str(out)]
    res = _run_cmd(argv, 1200)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError("变体编码失败：" + res.stderr[-800:])


def _artifact(session: Session, run_id: int, node_id: str, type_: str) -> Artifact | None:
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == run_id, Artifact.node_id == node_id, Artifact.type == type_)).all()  # type: ignore[arg-type]
    for a in reversed(rows):
        if Path(a.path).exists():
            return a
    return None


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


async def run_delivery(job_id: int) -> None:
    from ..db import engine as db_engine
    job = None
    hb = None
    try:
        with Session(db_engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return
            payload = job.payload_json or {}
            project = session.get(Project, int(payload.get("projectId") or 0))
            if not project:
                raise RuntimeError("项目不存在")
            root = Path(project.root)
            run_id = int(payload.get("runId") or 0)
            run = session.get(Run, run_id)
            if not run:
                raise RuntimeError("Run 不存在")
            jobs_svc.start_job(session, job_id, "delivery")
            ctx = pv.resolve_context(session, project.id or 0)
            profile = ctx.profile
            if not ctx.imported:
                ensure_final_ready(session, run, root, False, profile)
                g07 = session.exec(select(NodeRun).where(
                    NodeRun.run_id == run_id, NodeRun.node_id == "G07")).first()  # type: ignore[arg-type,union-attr]
                if not g07 or g07.status not in ("succeeded", "cached"):
                    raise RuntimeError(
                        "E_DELIVERY_GATE: G07 未通过（需先完成交付打包/审批与 master QC），"
                        "再生成交付包")
            task_p = root / "runs" / str(run_id) / "docs" / "task.json"
            task = json.loads(task_p.read_text(encoding="utf-8")) if task_p.exists() else {}
        hb = asyncio.create_task(_heartbeat(job_id))
        outdir = root / "out" / "deliveries" / str(run_id)
        if outdir.exists():
            shutil.rmtree(outdir)
        outdir.mkdir(parents=True)
        video = _artifact(session, run_id, "F04", "MP4") if False else None
        # re-open session for artifact reads
        with Session(db_engine) as session:
            video_a = _artifact(session, run_id, "F04", "MP4")
            mix_a = next((a for a in session.exec(select(Artifact).where(
                Artifact.run_id == run_id, Artifact.node_id == "G05",
                Artifact.type == "WAV")).all()  # type: ignore[arg-type]
                if (a.meta_json or {}).get("mix") and Path(a.path).exists()), None)
            stills = session.exec(select(Artifact).where(
                Artifact.run_id == run_id, Artifact.node_id == "D02", Artifact.type == "PNG")).all()  # type: ignore[arg-type]
            g07_a = _artifact(session, run_id, "G07", "MP4")
        video = Path(video_a.path) if video_a else root / "out/film/intermediate.mp4"
        mix = root / "card/mix.wav"
        if not mix.exists() and mix_a:
            mix = Path(mix_a.path)
        if not video.exists():
            raise RuntimeError("缺少 F04 视频")
        if not mix.exists():
            raise RuntimeError("缺少混音 card/mix.wav")
        # 16:9 master（直接用 F04 + mix，避免重复降采样）
        master16 = outdir / "master_16x9.mp4"
        from ..engine.runengine import LOCK_MANAGER
        await LOCK_MANAGER.acquire("ffmpeg", f"delivery:{job_id}")
        try:
            await asyncio.to_thread(_mux, video, mix, master16, 1920, 1080,
                                    int(profile.get("fps") or 24), 18, "medium")
        finally:
            LOCK_MANAGER.release("ffmpeg", f"delivery:{job_id}")
        with Session(db_engine) as s:
            jobs_svc.update_job(s, job_id, progress=0.55)
        # 9:16 变体
        frames_dir = outdir / "frames_9x16"
        info = await _render_variant_frames(job_id, ctx, V9, frames_dir)
        master9 = outdir / "master_9x16.mp4"
        await LOCK_MANAGER.acquire("ffmpeg", f"delivery:{job_id}")
        try:
            await asyncio.to_thread(_encode_frames, frames_dir / "%06d.png", mix, master9,
                                    1080, 1920, info["fps"], 19, "medium")
        finally:
            LOCK_MANAGER.release("ffmpeg", f"delivery:{job_id}")
        with Session(db_engine) as s:
            jobs_svc.update_job(s, job_id, progress=0.8)
        # SRT
        with Session(db_engine) as session:
            segments, source = _alignment(session, root, run, task, project.id or 0)
        srt_text, srt_meta = _srt(segments)
        captions = outdir / "captions.zh.srt"
        captions.write_text(srt_text, encoding="utf-8")
        # 封面：16:9 取 D02 review；9:16 取变体中间帧
        title = ""
        with Session(db_engine) as session:
            title = _title(session, project)
        review = [a for a in stills if (a.meta_json or {}).get("profile") == "review"]
        if not review:
            raise RuntimeError("缺少 D02 review 静帧")
        cover_src = Path(review[len(review) // 2].path)
        cover16 = outdir / "cover_16x9.jpg"
        await asyncio.to_thread(_cover, cover_src, cover16, 1920, 1080, title)
        scenes = ctx.scenes
        mid_scene = scenes[len(scenes) // 2] if scenes else {"start": 0, "end": 5}
        t_mid = float(mid_scene.get("start", 0)) + max(
            0.8, (float(mid_scene.get("end", 5)) - float(mid_scene.get("start", 0))) * 0.5)
        mid = min(info["frames"] - 1, max(0, round(t_mid * info["fps"])))
        cover9 = outdir / "cover_9x16.jpg"
        await asyncio.to_thread(_cover, frames_dir / f"{mid:06d}.png", cover9, 1080, 1920, title)
        shutil.rmtree(frames_dir, ignore_errors=True)
        # rights
        lic = audio_svc.load_license(root)
        ok, why = audio_svc.license_ok(lic)
        if not ok:
            raise RuntimeError(f"E_LICENSE_MISSING: {why}")
        engine_id = ctx.engine_id
        rights = {"schema": "filmflow.rights/1", "font": {"family": "Noto Sans SC", "license": "OFL"},
                  "style": {"engine": engine_id, "engineSha": ctx.engine_sha},
                  "music": lic, "generatedAt": _now()}
        (outdir / "rights.json").write_text(json.dumps(rights, ensure_ascii=False, indent=1), encoding="utf-8")
        # manifest
        files = [master16, master9, captions, cover16, cover9,
                 outdir / "rights.json"]
        approvals = []
        with Session(db_engine) as session:
            for a in session.exec(select(Approval).where(Approval.run_id == run_id)).all():  # type: ignore[arg-type]
                approvals.append({"gate": a.gate_id, "decision": a.decision,
                                  "author": a.author, "contentHash": a.content_hash})
        chrome = detect_chrome()
        chrome_ver = ""
        if chrome:
            try:
                chrome_ver = _run_cmd([chrome, "--version"], 20).stdout.strip()
            except Exception:
                pass
        ff = _run_cmd(["ffmpeg", "-version"], 20).stdout.splitlines()
        manifest = {"schema": "filmflow.delivery/1", "runId": run_id,
                    "project": {"id": project.id, "name": project.name},
                    "profile": profile, "variants": ["16x9", "9x16"],
                    "captions": {"file": captions.name, "source": source, **srt_meta},
                    "files": [{"name": p.name, "sha256": _file_sha(p), "bytes": p.stat().st_size}
                              for p in files],
                    "g07Master": ({"sha256": g07_a.sha256, "path": g07_a.path,
                                   "bytes": Path(g07_a.path).stat().st_size}
                                  if g07_a else None),
                    "approvals": approvals,
                    "env": {"engine": engine_id, "engineSha": ctx.engine_sha,
                            "fontSha": ctx.font_sha, "chrome": chrome_ver,
                            "ffmpeg": ff[0] if ff else ""},
                    "generatedAt": _now()}
        (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        # QC
        p16, p9 = await asyncio.to_thread(_probe, master16), await asyncio.to_thread(_probe, master9)
        loud = await asyncio.to_thread(_loudness, master16)
        from PIL import Image
        c16, c9 = Image.open(cover16).size, Image.open(cover9).size
        checks = {
            "master16": p16["width"] == 1920 and p16["height"] == 1080 and p16["fps"] == 24,
            "master9": p9["width"] == 1080 and p9["height"] == 1920 and p9["fps"] == 24,
            "duration": abs(p16["duration"] - float(profile.get("duration") or 0)) <= 0.05
                        and abs(p9["duration"] - float(profile.get("duration") or 0)) <= 0.05,
            "audio": p16["audioCodec"] is not None and p9["audioCodec"] is not None,
            "lufs": loud["lufs"] is not None and -17.0 <= loud["lufs"] <= -15.0,
            "truePeak": loud["truePeak"] is not None and loud["truePeak"] <= -1.5,
            "captions": srt_meta["count"] > 0 and srt_meta["maxLineChars"] <= 16
                        and srt_meta["maxCharsPerSec"] <= MAX_CAPTION_CPS,
            "covers": c16 == (1920, 1080) and c9 == (1080, 1920),
        }
        qc = {"schema": "filmflow.qc/1", "ok": all(checks.values()), "checks": checks,
              "probing": {"master16": p16, "master9": p9, "loudness": loud},
              "captions": srt_meta, "generatedAt": _now()}
        (outdir / "qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")
        if not qc["ok"]:
            raise RuntimeError(f"E_DELIVERY_QC: {[k for k, v in checks.items() if not v]}")
        # zip（8 个交付文件 + README）
        readme = ("FilmFlow delivery\n\n"
                  "master_16x9.mp4 / master_9x16.mp4: H.264 + AAC\n"
                  "captions.zh.srt: UTF-8 SRT\n"
                  "cover_16x9.jpg / cover_9x16.jpg: JPEG q92\n"
                  "manifest.json / qc.json / rights.json\n\n"
                  "校验：sha256sum * 对照 manifest.json files[].sha256\n")
        zpath = outdir / "FilmFlow-delivery.zip"
        def _zip() -> str:
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for p in files + [outdir / "qc.json", outdir / "manifest.json"]:
                    z.write(p, p.name)
                z.writestr("README.txt", readme)
            return _file_sha(zpath)
        zip_sha = await asyncio.to_thread(_zip)
        result = {"runId": run_id, "dir": str(outdir), "zip": str(zpath),
                  "zipSha256": zip_sha, "qc": str(outdir / "qc.json"),
                  "manifest": str(outdir / "manifest.json"), "files": [p.name for p in files]}
        with Session(db_engine) as s:
            jobs_svc.finish_job(s, job_id, "succeeded", result=result)
    except Exception as e:
        with Session(db_engine) as s:
            jobs_svc.finish_job(s, job_id, "failed", error_code="E_DELIVERY_FAILED",
                                error_msg=str(e)[:1500])
    finally:
        if hb:
            hb.cancel()


async def _heartbeat(job_id: int) -> None:
    from ..db import engine as db_engine
    while True:
        await asyncio.sleep(jobs_svc.HEARTBEAT_SECONDS)
        try:
            with Session(db_engine) as s:
                jobs_svc.heartbeat(s, job_id, "delivery")
        except Exception:
            pass


def create_job(session: Session, project: Project, run_id: int | None = None,
               profile: str = "final") -> Job:
    if not run_id:
        from ..models import Workflow
        wf = session.exec(select(Workflow).where(Workflow.project_id == project.id)).first()  # type: ignore[arg-type,union-attr]
        current = takes_svc.current_run(project.root)
        run = session.get(Run, current) if current else None
        if run and run.workflow_id != (wf.id if wf else -1):
            run = None
        if not run:
            run = session.exec(select(Run).where(Run.workflow_id == (wf.id if wf else -1))
                               .order_by(Run.id.desc())).first() if wf else None  # type: ignore[arg-type,union-attr]
        if not run:
            raise RuntimeError("项目没有 Run")
        run_id = run.id
    job = jobs_svc.create_job(session, "delivery", jobs_svc.PRIORITY["delivery"],
                              {"projectId": project.id, "runId": run_id, "profile": profile},
                              run_id=run_id)
    return job
