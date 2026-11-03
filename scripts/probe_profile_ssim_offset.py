"""档位 SSIM 阈值归因探针（专家复核用，一次性）。

问题：verify_r2_profiles.py 把"切点/入场 0.5s 窗口"的 draft-vs-final 阈值放宽到 0.90
（实测最低 0.952097），这是"合理放宽"还是"藏问题"？

归因逻辑：draft 只有 12fps，采样相位与 final（24fps）最多差 1/24s。
若 SSIM(final(t), final(t±1/24)) 在同窗口也掉到 ≈0.95，则 draft 低点纯属时间量化，
0.90 阈值诚实；若 final-vs-final 相邻帧仍 >0.99，则 draft 低点含真实空间差异，
阈值在掩盖漂移，应改为"对齐 12fps 网格再比"而不是放宽阈值。

用法：
  uv run --project server python scripts/probe_profile_ssim_offset.py <master.mp4> <scene_count>
采样点与 verify_r2_profiles.py 相同（0.5..4.8 八点 + 场景边界）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _frame(mp4: Path, idx: int, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-vf",
         f"select='eq(n,{idx})',scale=960:540:flags=lanczos",
         "-frames:v", "1", str(out)], check=True, timeout=60)


def _ssim(a: Path, b: Path) -> float:
    res = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b),
         "-filter_complex", "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    for line in (res.stderr or "").splitlines():
        if "SSIM" in line and "All:" in line:
            return float(line.split("All:")[1].split("(")[0].strip())
    raise RuntimeError("无 SSIM 输出：" + res.stderr[-300:])


def main() -> int:
    mp4 = Path(sys.argv[1])
    n_scenes = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    duration = 5.0
    bounds = [round(duration * i / n_scenes, 3) for i in range(1, n_scenes)] + \
             [round(duration * i / n_scenes, 3) for i in range(1, n_scenes + 1)]
    fps = 24
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rows = []
        worst = {"steady": 1.0, "cut": 1.0}
        for t in (0.5, 1.5, 2.45, 2.55, 3.2, 3.8, 4.2, 4.8):
            idx = int(round(t * fps))
            f0, fm, fp = tmp / "f0.png", tmp / "fm.png", tmp / "fp.png"
            _frame(mp4, idx, f0)
            _frame(mp4, max(idx - 1, 0), fm)
            _frame(mp4, idx + 1, fp)
            sm, sp = _ssim(f0, fm), _ssim(f0, fp)
            near_cut = any(-0.001 <= t - b <= 0.5 for b in bounds)
            key = "cut" if near_cut else "steady"
            lo = min(sm, sp)
            worst[key] = min(worst[key], lo)
            rows.append({"t": t, "idx": idx, "ssim_minus1f": round(sm, 6),
                         "ssim_plus1f": round(sp, 6), "worst": round(lo, 6),
                         "window": key})
            print(f"t={t}: final vs final±1/24s  −1f={sm:.6f}  +1f={sp:.6f}  "
                  f"({'切点/入场窗口' if near_cut else '稳定段'})", flush=True)
    print(json.dumps({"rows": rows,
                      "worst": {k: round(v, 6) for k, v in worst.items()}},
                     ensure_ascii=False, indent=1))
    print("判读：若切点窗口 worst ≈ draft-vs-final 的 0.9521 → 时间量化归因成立，0.90 诚实；"
          "若明显更高 → 阈值在掩盖空间差异，应对齐网格再比。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
