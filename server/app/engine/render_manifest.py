"""场景级增量渲染规划（FR-22）：scene_hash、dirty 场景、转场重叠、manifest。"""
from __future__ import annotations

import math

from .fpscalc import FPS_TOL, norm_fps, profile_frames
from .scene.canonical import content_hash

MANIFEST_SCHEMA = "filmflow.render/1"


def scene_ranges(scenes: list[dict], fps: float, frames: int) -> list[dict]:
    out = []
    for i, s in enumerate(scenes):
        start = max(0, min(frames, round(float(s.get("start", 0)) * fps)))
        end = max(start, min(frames, round(float(s.get("end", 0)) * fps)))
        out.append({"id": s["id"], "start": float(s.get("start", 0)),
                    "end": float(s.get("end", 0)), "range": [start, end]})
    if out:
        out[-1]["range"][1] = max(out[-1]["range"][1], frames)
        out[0]["range"][0] = min(out[0]["range"][0], 0)
    return out


def transitions_for_scene(transitions: list[dict], scene_id: str) -> list[dict]:
    picked = [t for t in transitions if t.get("from") == scene_id or t.get("to") == scene_id]
    return sorted(picked, key=lambda t: (str(t.get("from")), str(t.get("to")), t.get("at", 0)))


def transition_overlap(transitions: list[dict], scene_id: str, fps: int) -> int:
    durs = [float(t.get("duration", 0.5) or 0.5) for t in transitions_for_scene(transitions, scene_id)]
    return math.ceil(max(durs) * fps) if durs else 0


def transition_out_overlap(transitions: list[dict], scene_id: str, fps: int) -> int:
    """离开本场景的转场帧（落在下一场开头，但依赖本场 program）。"""
    durs = [float(t.get("duration", 0.5) or 0.5) for t in transitions if t.get("from") == scene_id]
    return math.ceil(max(durs) * fps) if durs else 0


def scene_hash(program: dict, tokens_sha: str, engine_sha: str, font_sha: str,
               profile: dict, transitions: list[dict], scene_id: str) -> str:
    return content_hash({
        "program": program,
        "tokens": tokens_sha,
        "engine": engine_sha,
        "font": font_sha,
        "profile": profile,
        "transitions": transitions_for_scene(transitions, scene_id),
    })


def build_plan(scenes: list[dict], programs: dict[str, dict], transitions: list[dict],
               profile: dict, tokens_sha: str, engine_sha: str, font_sha: str) -> list[dict]:
    fps = norm_fps(profile.get("fps") or 24)
    frames = profile_frames(profile)
    plan = []
    for r in scene_ranges(scenes, fps, frames):
        prog = programs.get(r["id"])
        if prog is None:
            raise ValueError(f"E_PROGRAM_INVALID: 缺少场景 {r['id']} 的 program")
        plan.append({
            **r,
            "hash": scene_hash(prog, tokens_sha, engine_sha, font_sha, profile, transitions, r["id"]),
            "overlap": transition_overlap(transitions, r["id"], fps),
            "out_overlap": transition_out_overlap(transitions, r["id"], fps),
            "status": "dirty", "ms": 0,
        })
    return plan


def _layout_change_index(prev: list[dict], plan: list[dict]) -> int | None:
    for i, cur in enumerate(plan):
        if i >= len(prev):
            return i
        old = prev[i]
        if old.get("id") != cur["id"] or old.get("range") != cur["range"]:
            return i
    if len(prev) > len(plan):
        return len(plan) - 1
    return None


def plan_dirty(plan: list[dict], prev_manifest: dict | None, profile_name: str,
               profile: dict) -> list[dict]:
    if not prev_manifest or prev_manifest.get("schema") != MANIFEST_SCHEMA:
        for s in plan:
            s["status"] = "dirty"
        return plan
    if (prev_manifest.get("profile") != profile_name
            or abs(float(prev_manifest.get("fps") or 0)
                   - float(profile.get("fps") or 24)) > FPS_TOL
            or int(prev_manifest.get("frames") or 0) != int(profile.get("frames") or 0)):
        for s in plan:
            s["status"] = "dirty"
        return plan
    prev_scenes = prev_manifest.get("scenes") or []
    prev_by_id = {s.get("id"): s for s in prev_scenes}
    layout_from = _layout_change_index(prev_scenes, plan)
    for i, s in enumerate(plan):
        old = prev_by_id.get(s["id"])
        done = bool(old and old.get("status") == "done" and old.get("hash") == s["hash"])
        dirty = (not done) or (layout_from is not None and i >= layout_from)
        s["status"] = "dirty" if dirty else "done"
    return plan


def dirty_ranges(plan: list[dict], frames: int) -> list[tuple[int, int]]:
    ranges = []
    for s in plan:
        if s.get("status") != "dirty":
            continue
        # 本场自身 + 本场离开时的转场帧；进入转场帧已落在本场 range 内，不向前扩
        start = s["range"][0]
        end = min(frames, s["range"][1] + s.get("out_overlap", s.get("overlap", 0)))
        if end > start:
            ranges.append((start, end))
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def build_manifest(run_id: int, profile_name: str, profile: dict, plan: list[dict],
                   ranges: list[tuple[int, int]], profile_spec: dict | None = None) -> dict:
    frames = profile_frames(profile)
    # ranges 可能是 (start,end) 或 (start,end,ms)
    rendered = sum(int(r[1]) - int(r[0]) for r in ranges)
    return {
        "schema": MANIFEST_SCHEMA, "run_id": run_id, "profile": profile_name,
        "profileSpec": dict(profile_spec or {}),
        "fps": norm_fps(profile.get("fps") or 24), "frames": frames,
        "scenes": [{"id": s["id"], "hash": s["hash"], "range": s["range"],
                    "status": s["status"], "ms": s.get("ms", 0)} for s in plan],
        "transitionOverlap": max([s.get("overlap", 0) for s in plan] or [0]),
        "reusedFrames": max(0, frames - rendered), "renderedFrames": rendered,
    }
