"""P1-12：全项目唯一的 fps / 帧网格口径。

之前 fps 在 preview/render_profiles/compiler/pipeline/routes/templates 各处
int() 截断，23.976 会被静默变 23，导致帧网格、时长、QC 全部漂移。
现在：
- fps 一律经 norm_fps 归一（接受数字/"23.976"/"24000/1001"）；
- 帧数一律 frames_for(duration, fps) = round(duration * fps)；
- 帧号一律 frame_at(t, fps) = round(t * fps)，时间一律 time_at(i) = i / fps；
- ffmpeg 的 -framerate/-r 用 fps_rational（NTSC 率输出精确有理数）；
- 比较一律 FPS_TOL 容差，禁止 int() 后比较。
"""
from __future__ import annotations

from fractions import Fraction

# 与 G07 QC（pipeline.py E_QC_FPS）一致的容差口径
FPS_TOL = 1e-3

# 常见 NTSC/广播率：十进制别名 → 精确有理数（分母 1001）
_RATIONAL_ALIASES: dict[str, Fraction] = {
    "23.976": Fraction(24000, 1001),
    "29.97": Fraction(30000, 1001),
    "59.94": Fraction(60000, 1001),
    "119.88": Fraction(120000, 1001),
    "47.952": Fraction(48000, 1001),
    "24.0": Fraction(24, 1),
}


def norm_fps(value) -> float:
    """fps 归一：数字、十进制字符串、'24000/1001' 有理数字符串都接受。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("fps 不能为空")
        if "/" in text:
            num, _, den = text.partition("/")
            try:
                frac = Fraction(int(num.strip()), int(den.strip()))
            except (ValueError, ZeroDivisionError) as e:
                raise ValueError(f"fps 有理数无效：{value}") from e
            if frac <= 0:
                raise ValueError(f"fps 必须大于 0：{value}")
            return float(frac)
        try:
            fps = float(text)
        except ValueError as e:
            raise ValueError(f"fps 不是数字：{value}") from e
    else:
        if value is None:
            raise ValueError("fps 不能为空")
        try:
            fps = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as e:
            raise ValueError(f"fps 不是数字：{value}") from e
    if not fps > 0 or fps != fps or fps == float("inf"):
        raise ValueError(f"fps 必须大于 0：{value}")
    return fps


def frames_for(duration: float, fps) -> int:
    """时长 → 帧数：round(duration * fps)。全项目唯一入口。"""
    f = norm_fps(fps)
    return max(0, int(round(float(duration or 0) * f)))


def frame_at(t: float, fps) -> int:
    """时间 → 帧号：round(t * fps)，clamp ≥0。"""
    f = norm_fps(fps)
    return max(0, int(round(float(t or 0) * f)))


def time_at(index: int, fps) -> float:
    """帧号 → 时间：i / fps（float 除法，确定性由 frame_at 往返保证）。"""
    f = norm_fps(fps)
    return (int(index) if index == index else 0) / f


def fps_rational(fps) -> str:
    """ffmpeg -framerate/-r 的精确字符串：NTSC 率出有理数，其余出十进制。"""
    f = norm_fps(fps)
    frac = _RATIONAL_ALIASES.get(repr(f))
    if frac is None:
        frac = Fraction(f).limit_denominator(1001)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"
