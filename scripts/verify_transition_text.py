"""B3/P2-13：转场期文字可见性的逐帧量化证据。

旧实现：文字 out 固定 `duration-0.4/0.4s`——转场窗一开始（=场景边界）文字早已消失，
背景还在 crossfade、文字却提前没了。新实现：文字满显到场景末尾、随出转场窗口
一起淡出。本脚本在 scratch 项目上真渲到 F04，抽取转场窗口前后逐帧，
统计标题文字区的"亮像素数"（pal[0] 纸色文字 ≈ lum>200）作为文字在场度量：

  t=1.9（窗前）   文字满显 → 亮像素多
  t=2.0（窗起点） 新行为：仍满显；旧行为：已归零 ←—— 修复点
  t=2.0→2.5（窗） 随转场平滑衰减
  t≥2.5（窗后）   归零（下一场接管）

用法：uv run --project server python scripts/verify_transition_text.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _acceptance import destroy
from _scratch_state import create_project, drive_to, set_scene_text

C = httpx.Client(base_url="http://127.0.0.1:7860/api", timeout=120, trust_env=False,
                 headers={"Origin": "http://127.0.0.1:3000"})
# compiler 16x9 的标题框（L_title box）
TITLE_BOX = (160, 320, 1600, 360)
TIMES = [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6]


def dark_pixels(png: Path) -> int:
    """文字可见度 = 标题区内**暗像素数**（H2：纸色卡片上的深墨文字）。

    相机缓推带来的卡片缩放会轻微扰动亮像素总数，暗像素只由文字笔画贡献，
    对文字在场/消失远比亮像素敏感。
    """
    im = Image.open(png).convert("L").crop(TITLE_BOX)
    return sum(im.histogram()[:120])


def frame_at(mp4: Path, t: float, out: Path) -> Path:
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4),
                        "-frames:v", "1", str(out)], capture_output=True, text=True,
                       check=False)
    assert r.returncode == 0 and out.exists(), r.stderr[-300:]
    return out


def main() -> int:
    proj = create_project(C, "b3-transition-text")
    pid, rid = proj["pid"], proj["run_id"]
    try:
        # 清空 S02 文字：窗口帧的标题区亮像素就只剩 S01 的**出场文字**，度量不被
        # 下一场的入场文字淹没（入场文字另算，不构成本证据的干扰项）
        tl = C.get(f"/projects/{pid}/docs/timeline").json()["content"]
        set_scene_text(C, pid, tl["scenes"][1]["id"], "")
        drive_to(C, pid, rid, node="F04", timeout=600.0)
        root = Path(proj["root"])
        mp4 = root / "out" / "film" / "intermediate.mp4"
        assert mp4.exists(), "F04 未产出 intermediate.mp4"
        tmp = Path(tempfile.mkdtemp(prefix="b3-frames-"))
        counts = {}
        for t in TIMES:
            counts[t] = dark_pixels(frame_at(mp4, t, tmp / f"f{t:.2f}.png"))
        print("转场窗 [2.0, 2.5) 前后逐帧 文字区暗像素数（S01 出场文字）：", flush=True)
        for t in TIMES:
            bar = "#" * min(60, counts[t] // 400)
            print(f"  t={t:.2f}  {counts[t]:6d}  {bar}", flush=True)
        full = max(counts[1.8], counts[1.9])
        floor = counts[2.6]
        assert full > 1200, f"窗前文字应满显（暗像素 {full} 太少，标题区取样可能失效）"
        assert counts[2.0] > full * 0.9, \
            f"t=2.0（窗口起点）文字必须仍满显：{counts[2.0]} vs {full}——" \
            "旧行为（duration-0.4 固定淡出）这里已衰减到地板"
        assert counts[2.4] < full * 0.5, \
            f"窗口末端（t=2.4）应已大幅衰减：{counts[2.4]} vs 满显 {full}"
        assert counts[2.6] < full * 0.25, \
            f"窗后（t=2.6）应到地板：{counts[2.6]} vs 满显 {full}（地板={floor}）"
        print("PASS: 转场期文字随出转场窗口淡出（不再提前消失）——逐帧量化见上表", flush=True)
        return 0
    finally:
        destroy(C, pid, root)


if __name__ == "__main__":
    sys.exit(main())
