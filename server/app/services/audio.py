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

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}
MAX_BYTES = 200 * 1024 * 1024


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def manifest_path(root: str | Path) -> Path:
    return Path(root) / "card" / "audio.json"


def load_manifest(root: str | Path) -> dict:
    data = _read(manifest_path(root))
    return {"schema": "filmflow.audio/1", "takes": data.get("takes", [])}


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
    src.write_bytes(raw)
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
