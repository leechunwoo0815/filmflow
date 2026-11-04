"""FR-27 本地音频工作台：Take 管理、waveform peaks、手动对齐、音乐许可。"""
from __future__ import annotations

import base64
import json
import subprocess
import uuid
from datetime import date
from pathlib import Path

import numpy as np

from ..engine.cachekey import file_sha256
from ..errors import ApiError, ErrorCode

from ..atomicwrite import write_atomic

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}
MAX_BYTES = 200 * 1024 * 1024


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, data: dict) -> None:
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1))


def manifest_path(root: str | Path) -> Path:
    return Path(root) / "card" / "audio.json"


def load_manifest(root: str | Path) -> dict:
    data = _read(manifest_path(root))
    data.setdefault("schema", "filmflow.audio/1")
    data.setdefault("takes", [])
    data.setdefault("scenePrimary", {})
    return data


def save_manifest(root: str | Path, data: dict) -> dict:
    data = {**data, "schema": "filmflow.audio/1"}
    _write(manifest_path(root), data)
    return data


def placeholder_path(root: str | Path) -> Path:
    return Path(root) / "card" / "audio.placeholder.json"


def load_placeholder(root: str | Path) -> dict | None:
    data = _read(placeholder_path(root))
    return data or None


def save_placeholder(root: str | Path, kind: str, duration: float, source: str = "") -> dict:
    data = {"schema": "filmflow.audio-placeholder/1", "kind": kind,
            "duration": round(float(duration or 0), 3), "source": source,
            "note": "模板占位：录制或上传后替换；不会自动生成音频"}
    _write(placeholder_path(root), data)
    return data


def clear_placeholder(root: str | Path, kind: str) -> None:
    current = load_placeholder(root)
    if current and current.get("kind") == kind:
        placeholder_path(root).unlink(missing_ok=True)


def _duration(path: Path) -> float:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30)
        return round(float(json.loads(res.stdout)["format"]["duration"]), 3)
    except Exception:
        return 0.0


def import_take(root: str | Path, filename: str, data_b64: str, kind: str = "voice",
                scene_id: str = "", name: str = "") -> dict:
    root = Path(root)
    ext = Path(filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise ApiError(ErrorCode.E_VALIDATION, f"不支持的音频格式：{ext}")
    try:
        raw = base64.b64decode(data_b64.split(",", 1)[-1], validate=True)
    except Exception:
        raise ApiError(ErrorCode.E_VALIDATION, "音频 base64 无效")
    if not raw or len(raw) > MAX_BYTES:
        raise ApiError(ErrorCode.E_VALIDATION, "音频为空或超过 200MB")
    outdir = root / "card" / "audio"
    outdir.mkdir(parents=True, exist_ok=True)
    tid = uuid.uuid4().hex[:12]
    src = outdir / f"{tid}.src{ext}"
    write_atomic(src, raw)
    wav = outdir / f"{tid}.wav"
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "48000", str(wav)],
                         capture_output=True, text=True, timeout=300)
    src.unlink(missing_ok=True)
    if res.returncode != 0 or not wav.exists():
        raise ApiError(ErrorCode.E_VALIDATION, "音频解码失败：" + res.stderr[-300:])
    manifest = load_manifest(root)
    takes = manifest["takes"]
    is_primary = kind == "voice" and not any(t.get("kind") == "voice" and t.get("primary") for t in takes)
    take = {"id": tid, "kind": kind, "sceneId": scene_id, "name": name or Path(filename).stem,
            "file": str(wav.relative_to(root)), "sha256": file_sha256(str(wav)),
            "duration": _duration(wav), "primary": is_primary,
            "bytes": wav.stat().st_size}
    takes.append(take)
    _write(manifest_path(root), manifest)
    clear_placeholder(root, kind)
    return take


def set_primary(root: str | Path, take_id: str) -> dict:
    manifest = load_manifest(root)
    found = None
    for t in manifest["takes"]:
        if t["id"] == take_id:
            t["primary"] = True
            found = t
        else:
            t["primary"] = False
    if not found:
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频 Take 不存在", status=404)
    _write(manifest_path(root), manifest)
    return found


def primary_take(root: str | Path, kind: str = "voice") -> dict | None:
    takes = load_manifest(root)["takes"]
    primary = [t for t in takes if t.get("kind") == kind and t.get("primary")]
    if primary:
        return primary[-1]
    same = [t for t in takes if t.get("kind") == kind]
    return same[-1] if same else None


def waveform(root: str | Path, take_id: str, width: int = 2000) -> dict:
    take = next((t for t in load_manifest(root)["takes"] if t["id"] == take_id), None)
    if not take:
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频 Take 不存在", status=404)
    path = Path(root) / take["file"]
    if not path.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频文件不存在", status=404)
    width = max(100, min(int(width), 8000))
    res = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000",
                          "-f", "f32le", "-"], capture_output=True, timeout=120)
    arr = np.frombuffer(res.stdout, dtype="<f4")
    if arr.size == 0:
        raise ApiError(ErrorCode.E_VALIDATION, "音频解码为空")
    n = max(1, arr.size // width)
    peaks = []
    for i in range(width):
        chunk = arr[i * n:(i + 1) * n]
        if chunk.size == 0:
            peaks.append([0, 0])
        else:
            peaks.append([round(float(chunk.min()), 3), round(float(chunk.max()), 3)])
    return {"takeId": take_id, "width": width, "duration": take.get("duration", 0),
            "peaks": peaks}


def alignment_path(root: str | Path) -> Path:
    return Path(root) / "card" / "alignment.manual.json"


def load_alignment(root: str | Path) -> dict:
    data = _read(alignment_path(root))
    if not data.get("segments"):
        return {"source": "manual", "segments": []}
    data["source"] = "manual"
    return data


def save_alignment(root: str | Path, segments: list[dict], author: str = "local") -> dict:
    clean = []
    for s in segments or []:
        try:
            start, end = float(s.get("start")), float(s.get("end"))
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.E_VALIDATION, "对齐段 start/end 必须是数字")
        if start < 0 or end <= start:
            raise ApiError(ErrorCode.E_VALIDATION, f"对齐段时间非法：{start}-{end}")
        clean.append({"text": str(s.get("text") or ""), "start": round(start, 3),
                      "end": round(end, 3)})
    data = {"schema": "filmflow.alignment/1", "source": "manual",
            "author": author, "segments": clean}
    _write(alignment_path(root), data)
    return data


def license_path(root: str | Path) -> Path:
    return Path(root) / "card" / "music_license.json"


def load_license(root: str | Path) -> dict:
    return _read(license_path(root))


def license_ok(lic: dict) -> tuple[bool, str]:
    if not lic:
        return False, "缺少 card/music_license.json"
    if not str(lic.get("source") or "").strip():
        return False, "缺少音乐来源"
    if not str(lic.get("license") or "").strip():
        return False, "缺少许可类型"
    if lic.get("authorized") is not True:
        return False, "音乐未标记 authorized=true"
    exp = lic.get("expires")
    if exp:
        try:
            if date.fromisoformat(str(exp)[:10]) < date.today():
                return False, "音乐许可已过期"
        except ValueError:
            return False, "音乐许可到期日格式错误（YYYY-MM-DD）"
    return True, ""


def save_license(root: str | Path, payload: dict) -> dict:
    lic = {k: payload.get(k) for k in ("source", "license", "authorized", "expires", "note")}
    ok, why = license_ok(lic)
    if not ok:
        raise ApiError(ErrorCode.E_LICENSE_MISSING, why, status=409)
    _write(license_path(root), lic)
    return lic


# ---------- FR-35 v2：场景 Take / 处理 / 拼接 / 拍点 / 响度 ----------

def _take(root: str | Path, take_id: str) -> dict | None:
    return next((t for t in load_manifest(root)["takes"] if t.get("id") == take_id), None)


def take_path(root: str | Path, take_id: str, processed: bool = False) -> Path:
    take = _take(root, take_id)
    if not take:
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频 Take 不存在", status=404)
    rel = take.get("processedFile") if processed and take.get("processedFile") else take["file"]
    p = Path(root) / rel
    if not p.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频文件不存在", status=404)
    return p


def set_scene_primary(root: str | Path, scene_id: str, take_id: str) -> dict:
    take = _take(root, take_id)
    if not take:
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频 Take 不存在", status=404)
    if take.get("kind") != "voice":
        raise ApiError(ErrorCode.E_VALIDATION, "只能把 voice Take 设为场景主 Take")
    data = load_manifest(root)
    data["scenePrimary"][scene_id] = take_id
    save_manifest(root, data)
    return {"sceneId": scene_id, "takeId": take_id}


def clear_scene_primary(root: str | Path, scene_id: str) -> dict:
    data = load_manifest(root)
    data["scenePrimary"].pop(scene_id, None)
    save_manifest(root, data)
    return {"sceneId": scene_id, "takeId": None}


def take_for_scene(root: str | Path, scene_id: str) -> dict | None:
    tid = load_manifest(root).get("scenePrimary", {}).get(scene_id)
    if tid:
        take = _take(root, tid)
        if take:
            return take
    return primary_take(root, "voice")


def processing_filter(opts: dict) -> str:
    parts = []
    if opts.get("highpass"):
        parts.append("highpass=f=80")
    if opts.get("denoise"):
        parts.append("afftdn=nr=12:nf=-30")
    if opts.get("deesser"):
        parts.append("deesser=i=0.5")
    if opts.get("eq"):
        parts += ["equalizer=f=120:t=q:w=1:g=2", "equalizer=f=1000:t=q:w=1:g=0",
                  "equalizer=f=6000:t=q:w=1:g=-1.5"]
    if opts.get("trim"):
        parts.append("silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:"
                     "stop_periods=-1:stop_duration=0.1:stop_threshold=-45dB")
    if opts.get("normalize"):
        parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    return ",".join(parts)


def process_take(root: str | Path, take_id: str, opts: dict) -> dict:
    root = Path(root)
    take = _take(root, take_id)
    if not take:
        raise ApiError(ErrorCode.E_NOT_FOUND, "音频 Take 不存在", status=404)
    chain = processing_filter(opts)
    outdir = root / "card" / "audio"
    out = outdir / f"{take_id}.processed.wav"
    if not chain:
        out.unlink(missing_ok=True)
        data = load_manifest(root)
        for t in data["takes"]:
            if t.get("id") == take_id:
                for key in ("processedFile", "processedSha", "processing", "processedDuration"):
                    t.pop(key, None)
                take = t
        save_manifest(root, data)
        return take
    src = root / take["file"]
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", chain,
                          "-ac", "1", "-ar", "48000", str(out)],
                         capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not out.exists():
        raise ApiError(ErrorCode.E_VALIDATION, "音频处理失败：" + res.stderr[-500:])
    data = load_manifest(root)
    for t in data["takes"]:
        if t.get("id") == take_id:
            t["processedFile"] = str(out.relative_to(root))
            t["processedSha"] = file_sha256(str(out))
            t["processing"] = {k: bool(opts.get(k)) for k in
                               ("highpass", "denoise", "deesser", "eq", "trim", "normalize")}
            t["processedDuration"] = _duration(out)
            take = t
    save_manifest(root, data)
    return take


def concat_voice(root: str | Path, scenes: list[dict], duration: float,
                 out_path: str | Path | None = None) -> dict | None:
    """按 scenePrimary 把多段口播放到场景起点，空场留静音；无映射返回 None。"""
    root = Path(root)
    data = load_manifest(root)
    mapping = data.get("scenePrimary") or {}
    if not mapping:
        return None
    picks = []
    for scene in scenes:
        tid = mapping.get(scene.get("id"))
        take = _take(root, tid) if tid else None
        if not take:
            continue
        start = float(scene.get("start", 0))
        dur = max(0.1, float(scene.get("end", 0)) - start)
        picks.append((take_path(root, take["id"], processed=True), start, dur, take["id"]))
    if not picks:
        return None
    out = Path(out_path) if out_path else root / "card" / "voice.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = f"{float(duration):.3f}"
    argv = ["ffmpeg", "-y"]
    for path, _start, _dur, _tid in picks:
        argv += ["-i", str(path)]
    filters = []
    labels = []
    for i, (_path, start, dur, _tid) in enumerate(picks):
        ms = max(0, round(start * 1000))
        filters.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,"
                       f"apad=whole_dur={dur:.3f},atrim=duration={dur:.3f},"
                       f"adelay={ms}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
                   f"apad=whole_dur={d},atrim=duration={d}[a]")
    argv += ["-filter_complex", ";".join(filters), "-map", "[a]", "-t", d,
             "-ar", "48000", "-ac", "1", str(out)]
    res = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not out.exists():
        raise ApiError(ErrorCode.E_VALIDATION, "多 Take 拼接失败：" + res.stderr[-500:])
    return {"path": str(out), "duration": _duration(out), "picks": len(picks),
            "scenes": [p[3] for p in picks]}


def mix_path(root: str | Path) -> Path:
    return Path(root) / "card" / "audio.mix.json"


def load_mix(root: str | Path) -> dict:
    data = _read(mix_path(root))
    base = {"schema": "filmflow.audio-mix/1", "preset": "-16", "targetLufs": -16.0,
            "stems": {"voice": 0.0, "music": -8.0, "sfx": 0.0}}
    if data.get("schema") != base["schema"]:
        return base
    base.update({k: data.get(k) for k in ("preset", "targetLufs") if data.get(k) is not None})
    base["stems"] = {**base["stems"], **(data.get("stems") or {})}
    return base


def save_mix(root: str | Path, payload: dict) -> dict:
    preset = str(payload.get("preset") or "-16")
    targets = {"-14": -14.0, "-16": -16.0, "-18": -18.0}
    try:
        target = float(payload.get("targetLufs") if payload.get("targetLufs") is not None
                       else targets.get(preset, -16.0))
    except (TypeError, ValueError):
        raise ApiError(ErrorCode.E_VALIDATION, "targetLufs 必须是数字")
    if not -30 <= target <= -5:
        raise ApiError(ErrorCode.E_VALIDATION, "targetLufs 必须在 -30..-5")
    stems = {}
    src = payload.get("stems") or {}
    for k in ("voice", "music", "sfx"):
        try:
            v = float(src.get(k, {"voice": 0.0, "music": -8.0, "sfx": 0.0}[k]))
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.E_VALIDATION, f"stems.{k} 必须是数字")
        if not -120 <= v <= 12:
            raise ApiError(ErrorCode.E_VALIDATION, f"stems.{k} 必须在 -60..12dB")
        stems[k] = v
    data = {"schema": "filmflow.audio-mix/1", "preset": preset,
            "targetLufs": round(target, 1), "stems": stems}
    _write(mix_path(root), data)
    return data


def markers_path(root: str | Path) -> Path:
    return Path(root) / "card" / "markers.json"


def load_markers(root: str | Path) -> dict:
    data = _read(markers_path(root))
    return {"schema": "filmflow.markers/1",
            "markers": data.get("markers") or [],
            "onsets": data.get("onsets") or []}


def save_markers(root: str | Path, markers: list[dict], onsets: list[dict] | None = None) -> dict:
    clean = []
    for m in markers or []:
        try:
            t = round(float(m.get("time")), 3)
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.E_VALIDATION, "marker.time 必须是数字")
        if t < 0:
            raise ApiError(ErrorCode.E_VALIDATION, "marker.time 不能为负")
        clean.append({"id": str(m.get("id") or uuid.uuid4().hex[:8]), "time": t,
                      "label": str(m.get("label") or "")[:40]})
    clean.sort(key=lambda x: x["time"])
    if onsets is None:
        onsets = load_markers(root).get("onsets") or []
    data = {"schema": "filmflow.markers/1", "markers": clean, "onsets": onsets}
    _write(markers_path(root), data)
    return data


def detect_onsets(root: str | Path, take_id: str, min_gap: float = 0.12) -> list[dict]:
    import tempfile
    path = take_path(root, take_id, processed=True)
    fd, name = tempfile.mkstemp(suffix=".f32")
    try:
        with open(fd, "wb") as fh:
            res = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1",
                                  "-ar", "48000", "-f", "f32le", "-y", name],
                                 capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise ApiError(ErrorCode.E_VALIDATION, "拍点检测解码失败")
        arr = np.fromfile(name, dtype="<f4")
    finally:
        Path(name).unlink(missing_ok=True)
    if arr.size == 0:
        return []
    win = 240  # 5ms
    e = np.abs(arr[: arr.size // win * win]).reshape(-1, win).mean(axis=1)
    flux = np.maximum(np.diff(e), 0)
    if flux.size == 0:
        return []
    thr = float(flux.mean() + 1.2 * flux.std())
    peaks = []
    last = -1.0
    for i in range(1, len(flux) - 1):
        if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]:
            t = i * win / 48000.0
            if t - last >= min_gap:
                peaks.append({"time": round(t, 3),
                              "strength": round(float(flux[i] / (flux.max() or 1)), 3)})
                last = t
    return peaks
