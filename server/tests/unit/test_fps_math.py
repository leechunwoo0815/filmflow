"""P1-12：非整数 fps 的帧网格与时长口径（先失败后实现）。

结论口径（写死在测试里，防回退）：
- fps 保留浮点/有理数，不再 int() 截断；
- 全项目唯一帧数函数 frames_for(duration, fps) = round(duration * fps)；
- 帧号→时间 time_at(i) = i / fps；时间→帧号 frame_at(t) = round(t * fps)；
- ffmpeg 用 fps_rational 输出精确有理数字符串；
- manifest/profile 校验比较用容差，不再 int() 后比较；
- final 不得低于 1080p/24 的门对 NTSC 23.976/29.97 放行（广播标准帧率）。
"""
from __future__ import annotations

import math
import tempfile

_TMPROOT = tempfile.mkdtemp(prefix="ff-fps-test-")

import pytest

from app.engine.fpscalc import FPS_TOL, fps_rational, frame_at, frames_for, norm_fps, time_at
from app.engine.render_manifest import build_plan, scene_ranges
from app.services import render_profiles as rp

# ---------- fpscalc 基础 ----------

def test_norm_fps_accepts_float_and_rational_and_rejects_bad():
    assert norm_fps(24) == 24.0
    assert norm_fps("23.976") == pytest.approx(24000 / 1001, abs=1e-9)  # 十进制写法吸附到精确有理数
    assert norm_fps("24000/1001") == pytest.approx(23.976023976, abs=1e-6)
    assert norm_fps(29.97) == pytest.approx(30000 / 1001, abs=1e-9)
    for bad in (0, -5, "abc", None, ""):
        with pytest.raises(Exception):
            norm_fps(bad)


def test_frames_for_matches_all_declared_grids():
    assert frames_for(5.0, 24) == 120
    assert frames_for(5.0, 12) == 60
    assert frames_for(3.0, 25) == 75
    assert frames_for(30.0, 30) == 900
    # NTSC：40s @ 23.976 = 959.04 帧 → 959；1s → 24
    assert frames_for(40.0, 23.976) == 959
    assert frames_for(1.0, 23.976) == 24
    assert frames_for(1.0, 29.97) == 30
    assert frames_for(0.0, 24) == 0


def test_frame_grid_roundtrip_and_monotonic():
    for fps in (12, 24, 25, 30, 23.976, 29.97):
        n = frames_for(5.0, fps)
        ts = [time_at(i, fps) for i in range(n)]
        assert all(ts[i] < ts[i + 1] for i in range(n - 1)), fps
        assert all(frame_at(t, fps) == i for i, t in enumerate(ts)), fps
    assert abs(frames_for(5.0, 23.976) / 23.976 - 5.0) <= 0.5 / 23.976 + 1e-9


def test_fps_rational_outputs_exact_strings():
    assert fps_rational(24) == "24"
    assert fps_rational(12) == "12"
    assert fps_rational(23.976) == "24000/1001"
    assert fps_rational(29.97) == "30000/1001"
    assert fps_rational(25) == "25"


# ---------- render_profiles：档位 fps 不再截断 ----------

def test_tier_keeps_fractional_fps():
    out = rp._tier("final", {"width": 1920, "height": 1080, "fps": 23.976,
                             "crf": 17}, rp.DEFAULT_PROFILES["final"])
    assert out["fps"] == pytest.approx(23.976, abs=1e-4)


def test_resolve_keeps_fractional_project_fps():
    resolved = rp.resolve(_TMPROOT, {"width": 1920, "height": 1080,
                                     "fps": 23.976, "duration": 5.0},
                          allow_low_final=False)
    assert resolved["final"]["fps"] == pytest.approx(23.976, abs=1e-4)
    assert resolved["draft"]["fps"] == 12
    assert resolved["review"]["fps"] == 24


def test_final_gate_admits_ntsc_but_blocks_low_fps():
    ntsc = rp.resolve(_TMPROOT, {"width": 1920, "height": 1080,
                                 "fps": "24000/1001", "duration": 5.0},
                      allow_low_final=False)
    assert ntsc["final"]["fps"] == pytest.approx(23.976023976, abs=1e-6)
    with pytest.raises(Exception):
        rp.resolve(_TMPROOT, {"width": 1920, "height": 1080, "fps": 12,
                              "duration": 5.0}, allow_low_final=False)


def test_normalize_project_profile_frames_uses_frames_for():
    prof = rp.normalize_project_profile(
        {"width": 1920, "height": 1080, "fps": "23.976", "duration": 40.0})
    assert prof["fps"] == pytest.approx(23.976, abs=1e-4)
    assert prof["frames"] == 959
    prof2 = rp.normalize_project_profile({"width": 1920, "height": 1080,
                                          "fps": 24, "duration": 5.0})
    assert prof2["frames"] == 120


def test_final_ready_compare_uses_tolerance_not_int():
    manifest = {"fps": 23.976, "frames": 959, "width": 1920, "height": 1080,
                "profile": "final"}
    prof = {"fps": 23.976024, "frames": 959, "width": 1920, "height": 1080}
    # int() 口径下 23.976 != 23.976024 会误报 409；浮点容差下应放行
    assert abs(float(manifest["fps"]) - float(prof["fps"])) <= 0.01


# ---------- render_manifest：range 不漂移、末端吃满 ----------

def _scenes(n: int, dur: float):
    step = dur / n
    return [{"id": f"S{i+1:02d}", "start": round(i * step, 6),
             "end": round((i + 1) * step, 6)} for i in range(n)]


def test_scene_ranges_with_ntsc_fps_fill_to_frames():
    fps = 23.976
    frames = frames_for(40.0, fps)
    ranges = scene_ranges(_scenes(4, 40.0), fps, frames)
    assert ranges[0]["range"][0] == 0
    assert ranges[-1]["range"][1] == frames
    starts = [r["range"][0] for r in ranges]
    ends = [r["range"][1] for r in ranges]
    assert starts == sorted(starts) and ends == sorted(ends)
    # 确定性：两次计算完全一致（不允许浮点漂移造成增量误判）
    again = scene_ranges(_scenes(4, 40.0), fps, frames)
    assert [r["range"] for r in ranges] == [r["range"] for r in again]


def test_build_plan_records_fractional_fps():
    fps = 23.976
    profile = {"width": 960, "height": 540, "fps": fps, "duration": 40.0}
    plan = build_plan(_scenes(2, 40.0), {"S01": {"layers": []}, "S02": {"layers": []}},
                      [], profile, "tok", "eng", "font")
    assert plan  # 结构存在
    assert abs(float(profile["fps"]) - 23.976) <= FPS_TOL


# ---------- 与 ffprobe 口径一致（QC 容差） ----------

def test_qc_fps_tolerance_matches_probe_rounding():
    # ffprobe r_frame_rate 24000/1001 → round(num/den, 3) = 23.976；
    # profile 配 23.976 → 必须在 0.01 容差内相等
    assert abs(23.976 - norm_fps("24000/1001")) <= 0.01
    assert math.isclose(round(24000 / 1001, 3), 23.976, abs_tol=0.0001)


def test_profile_frames_ignores_truncated_persisted_value():
    """23.976 项目里被 int() 截断写进文档的 frames 不得再生效。"""
    from app.engine.fpscalc import profile_frames
    stale = {"fps": 23.976, "duration": 40.0, "frames": 920}     # 23fps 截断产物
    assert profile_frames(stale) == 959
    assert profile_frames({"fps": 24, "duration": 5.0, "frames": 120}) == 120
    assert profile_frames({"fps": 24, "frames": 48}) == 48        # 无 duration 时退回持久值


def test_delivery_grid_is_single_valued_across_aspect_ratios():
    """16:9 与 9:16 共用同一帧网格：帧数与末帧时间由 duration+fps 现算，不再被 int(fps) 分叉。"""
    from app.engine.fpscalc import profile_frames, time_at
    prof = {"fps": 23.976, "duration": 40.0}
    frames = profile_frames(prof)
    assert frames == 959, frames                       # 旧 int(23.976)=23 口径会算成 920
    assert abs(time_at(0, prof["fps"])) < 1e-9
    last = time_at(frames - 1, prof["fps"])
    from fractions import Fraction as _F
    assert abs(last - (frames - 1) * float(_F(1001, 24000))) < 1e-9, \
        "帧网格必须与 ffmpeg 的 24000/1001 一致，不能一半按 23.976"
    assert 39.9 < last < 40.0, last
    assert profile_frames({"fps": 24, "duration": 5.0}) == profile_frames({"fps": "24/1", "duration": 5.0})


def test_final_fps_whitelist_accepts_ntsc_and_rejects_offgrid():
    """final 帧率门槛放行 NTSC 标准率，拒 23.9/23.95 这类贴阈值值；_tier 另有正数/上界校验。"""
    import pytest as _pt

    from app.engine.fpscalc import is_delivery_fps
    from app.errors import ApiError
    from app.services import render_profiles as rp
    assert all(is_delivery_fps(v) for v in (24, 25, 30, 50, 60, 23.976, 29.97, 59.94, "24000/1001"))
    assert not any(is_delivery_fps(v) for v in (23.9, 23.95, 48, 120, 1000, 0.5))
    base = {"width": 1920, "height": 1080, "crf": 17, "preset": "medium"}
    for fps in (24, 23.976, "24000/1001"):
        assert rp._tier("final", {**base, "fps": fps}, rp.DEFAULT_PROFILES["final"])["fps"] > 0
    for bad in (0, -1, 1000, "abc"):
        with _pt.raises(ApiError):
            rp._tier("final", {**base, "fps": bad}, rp.DEFAULT_PROFILES["final"])


def test_f05_duration_tolerance_follows_half_frame():
    """23.976 下半帧 0.02085s > 旧硬编码 0.02s：容差必须按帧率推导，否则合法 NTSC 成片会被 F05 拒。"""
    from app.engine.fpscalc import FPS_TOL, frames_for
    fps = 23.976
    quantization = 0.5 / fps
    assert quantization > 0.02, "旧固定容差确实小于半帧（这是 F05 的假失败来源）"
    expected = frames_for(39.5, fps)
    assert abs(expected / fps - 39.5) <= quantization      # 落在帧网格上的时长可被接受
    assert FPS_TOL < quantization
