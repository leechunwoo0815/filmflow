"""渲染档位 draft/review/final（FR-24）：默认值、项目覆盖、校验、QA 策略。

final 的分辨率/fps 由 project.profile.json 决定（时间轴/帧号以它为准）；
render.profile.json 只能覆盖编码 crf/preset，以及 draft/review 的分辨率/fps。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..engine.fpscalc import FPS_TOL, frames_for, norm_fps
from ..errors import ApiError, ErrorCode

SCHEMA = "filmflow.render-profile/1"
PROFILE_NAMES = ("draft", "review", "final")
DEFAULT_PROFILES = {
    "draft": {"width": 960, "height": 540, "fps": 12, "crf": 28, "preset": "ultrafast"},
    "review": {"width": 1280, "height": 720, "fps": 24, "crf": 22, "preset": "fast"},
    "final": {"width": 1920, "height": 1080, "fps": 24, "crf": 17, "preset": "medium"},
}
PROFILE_NODES = {"D02", "E05", "E06", "F02", "F03", "F04", "F05", "G07"}
PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"}

_QA = {
    "draft": {"missing": True, "black": True, "dups": False, "motion": False,
              "sync": False, "ssim": False, "lufs": False},
    "review": {"missing": True, "black": True, "dups": True, "motion": True,
               "sync": True, "ssim": False, "lufs": False},
    "final": {"missing": True, "black": True, "dups": True, "motion": True,
              "sync": True, "ssim": True, "lufs": True},
}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def profiles_sha(profiles: dict) -> str:
    payload = {k: profiles[k] for k in PROFILE_NAMES if k in profiles}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def qa_policy(profile_name: str) -> dict:
    if profile_name not in _QA:
        raise ApiError(ErrorCode.E_VALIDATION, f"未知渲染档位：{profile_name}")
    return dict(_QA[profile_name])


def _tier(name: str, value: dict | None, default: dict) -> dict:
    out = {**default, **(value or {})}
    try:
        out["width"] = int(out["width"])
        out["height"] = int(out["height"])
        out["crf"] = int(out["crf"])
    except (TypeError, ValueError):
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位 width/height/crf 必须是整数")
    try:
        # P1-12：fps 保留非整数（23.976/"24000/1001"），不再 int() 截断
        out["fps"] = norm_fps(out["fps"])
    except ValueError as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位 fps 无效：{e}")
    out["preset"] = str(out.get("preset") or default["preset"])
    if out["width"] <= 0 or out["height"] <= 0 or out["fps"] <= 0:
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位尺寸/fps 必须大于 0")
    if out["width"] % 2 or out["height"] % 2:
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位宽高必须是偶数（H.264）")
    if not 0 <= out["crf"] <= 51:
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位 crf 必须在 0–51")
    if out["preset"] not in PRESETS:
        raise ApiError(ErrorCode.E_VALIDATION, f"{name} 档位 preset 非法：{out['preset']}")
    return out


def resolve(project_root: str | Path, project_profile: dict | None = None,
            allow_low_final: bool = False) -> dict:
    """返回三档 resolved profiles；final 尺寸/fps 始终以项目 profile 为准。"""
    path = Path(project_root) / "render.profile.json"
    raw = _read_json(path)
    source = "default"
    if raw:
        if raw.get("schema") != SCHEMA:
            raise ApiError(ErrorCode.E_VALIDATION,
                           f"render.profile.json schema 必须是 {SCHEMA}")
        source = "file"
    out = {name: _tier(name, raw.get(name), DEFAULT_PROFILES[name]) for name in PROFILE_NAMES}
    prof = project_profile or {}
    if prof.get("width") and prof.get("height"):
        out["final"]["width"] = int(prof["width"])
        out["final"]["height"] = int(prof["height"])
    if prof.get("fps"):
        try:
            out["final"]["fps"] = norm_fps(prof["fps"])
        except ValueError as e:
            raise ApiError(ErrorCode.E_VALIDATION, f"项目 fps 无效：{e}")
    if raw and isinstance(raw.get("final"), dict):
        for key in ("width", "height", "fps"):
            if key in raw["final"]:
                desired, actual = raw["final"][key], out["final"][key]
                differs = (abs(float(desired) - float(actual)) > FPS_TOL
                           if key == "fps" else int(desired) != int(actual))
                if differs:
                    raise ApiError(
                        ErrorCode.E_VALIDATION,
                        f"final 的 {key} 由 project.profile.json 决定（{actual}），"
                        f"render.profile.json 不能改成 {desired}")
    out["final"] = _tier("final", out["final"], DEFAULT_PROFILES["final"])
    fw, fh, ffps = out["final"]["width"], out["final"]["height"], out["final"]["fps"]
    # 23.976/29.97 是广播标准交付帧率；低于 23.9 的才视为未达 final 门槛
    if not allow_low_final and (fw * fh < 1920 * 1080 or ffps < 23.9):
        raise ApiError(ErrorCode.E_VALIDATION,
                       f"final 不得低于 1080p/23.976（当前 {fw}×{fh}/{ffps}）")
    out["source"] = source
    return out


def ensure_final_ready(session, run, project_root: str | Path, imported: bool,
                       profile: dict) -> dict:
    """G07 前校验：最新 F02 manifest 必须是 final 且属于当前 Run（cached 例外）。"""
    if imported:
        return {}
    path = Path(project_root) / "renders" / "final" / "manifest.json"
    if not path.exists():
        raise ApiError(ErrorCode.E_FINAL_REQUIRED, "缺少 F02 final manifest，不能交付", status=409)
    manifest = _read_json(path)
    if manifest.get("profile") != "final":
        raise ApiError(ErrorCode.E_FINAL_REQUIRED,
                       f"最新 manifest 是 {manifest.get('profile')}，必须重新跑 F02 final",
                       status=409)
    # P1-12：fps 用容差比较（manifest 可能存 23.976，profile 存 24000/1001 归一后的浮点）
    if abs(float(manifest.get("fps") or 0) - float(profile.get("fps") or 0)) > 0.01 or \
            int(manifest.get("frames") or 0) != int(profile.get("frames") or 0):
        raise ApiError(ErrorCode.E_FINAL_REQUIRED,
                       "final manifest 的 fps/frames 与当前项目 profile 不一致", status=409)
    if int(manifest.get("run_id") or 0) != run.id:
        from sqlmodel import select

        from ..models import NodeRun
        row = session.exec(select(NodeRun).where(
            NodeRun.run_id == run.id, NodeRun.node_id == "F02")).first()  # type: ignore[arg-type,union-attr]
        if not row or row.status not in ("succeeded", "cached"):
            raise ApiError(ErrorCode.E_FINAL_REQUIRED,
                           "final manifest 不属于当前 Run（F02 未成功）", status=409)
    spec = manifest.get("profileSpec") or {}
    for key in ("width", "height", "fps"):
        if key not in spec:
            continue
        differs = (abs(float(spec[key]) - float(profile.get(key) or spec[key])) > 0.01
                   if key == "fps" else int(spec[key]) != int(profile.get(key) or spec[key]))
        if differs:
            raise ApiError(ErrorCode.E_FINAL_REQUIRED,
                           f"final profileSpec.{key} 与项目 profile 不一致", status=409)
    return manifest


def normalize_project_profile(profile: dict) -> dict:
    """项目 profile 归一出口：fps 走 norm_fps，frames 走 frames_for（P1-12 唯一口径）。"""
    out = dict(profile or {})
    if out.get("fps"):
        try:
            out["fps"] = norm_fps(out["fps"])
        except ValueError as e:
            raise ApiError(ErrorCode.E_VALIDATION, f"项目 fps 无效：{e}")
    if out.get("duration") and out.get("fps"):
        out["frames"] = frames_for(out["duration"], out["fps"])
    return out


def save(project_root: str | Path, payload: dict, project_profile: dict | None = None,
         allow_low_final: bool = False) -> dict:
    """写入 render.profile.json 并返回 resolved；final 尺寸与项目 profile 不一致会被拒绝。"""
    data = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else payload
    content = {"schema": SCHEMA}
    for name in PROFILE_NAMES:
        if isinstance(data.get(name), dict):
            content[name] = {k: v for k, v in data[name].items()
                             if k in ("width", "height", "fps", "crf", "preset")}
    # 先校验再落盘
    tmp_probe = {**content}
    path = Path(project_root) / "render.profile.json"
    old = _read_json(path)
    try:
        path.write_text(json.dumps(tmp_probe, ensure_ascii=False, indent=1), encoding="utf-8")
        resolved = resolve(project_root, project_profile, allow_low_final)
    except Exception:
        if old:
            path.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        raise
    return resolved
