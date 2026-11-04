"""P0-4a：真实 Chrome + ffmpeg + SSIM 的 3s 最小出片冒烟。

专家口径是"3s/12 帧"：时长照做 3s，帧数由 draft 档的 12fps 决定 → 36 帧（只多不少）。
SSIM 断言不写死一个魔数：同一时刻的静帧必须**明显比异刻对照更像**成片帧（实测
H2 风格 0.9377 vs 对照 0.8579），这样换风格不会让阈值失效，也仍能抓住"预览与成片不一致"。
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.requires_style_library,
    pytest.mark.requires_chrome,
    pytest.mark.requires_ffmpeg,
]


def _req(client: httpx.Client, method: str, path: str, payload: dict | None = None):
    r = client.request(method, path, json=payload)
    assert r.status_code < 400, f"{method} {path} -> {r.status_code} {r.text[:1000]}"
    return r.json()


def _run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _ffprobe(path: Path) -> dict:
    r = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
        "-of", "json", str(path),
    ])
    assert r.returncode == 0, r.stderr[-1000:]
    data = json.loads(r.stdout)
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": round(int(num) / int(den), 3),
        "frames": int(stream.get("nb_frames") or 0),
        "duration": float(data["format"]["duration"]),
    }


def _ssim(a: Path, b: Path) -> float:
    r = _run([
        "ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi",
        "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim", "-f", "null", "-",
    ])
    m = re.findall(r"SSIM Y:([0-9.]+)", r.stderr)
    assert m, f"SSIM 解析失败：{r.stderr[-1000:]}"
    return float(m[-1])


def test_render_smoke_3s_draft12fps(api_client: httpx.Client, project_root: Path, style_id: str):
    d = _req(api_client, "POST", "/drafts", {"name": "smoke-1s", "step": 1})
    primary = style_id
    _req(api_client, "PATCH", f"/drafts/{d['id']}", {
        "step": 5,
        "payload": {
            "root": str(project_root),
            "copy": "冒烟测试。",
            "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 3.0},
            "pick": {"primary": primary, "alternates": [], "reason": "smoke-1s"},
            "brief": {"title": "冒烟测试"},
        },
    })
    created = _req(api_client, "POST", f"/drafts/{d['id']}/materialize", {})
    pid = created["project"]["id"]
    tl = _req(api_client, "GET", f"/projects/{pid}/docs/timeline")
    scene_id = tl["content"]["scenes"][0]["id"]
    assert tl["content"]["fps"] == 24 and tl["content"]["frames"] == 72, tl["content"]

    still = api_client.post(f"/projects/{pid}/preview/still", json={
        "sceneId": scene_id, "time": 1.5, "profile": "draft",
        "watermark": False, "debounce": False, "motion": True})
    assert still.status_code == 200, still.text[:1000]
    assert still.headers.get("X-Preview-Chrome") in {"new", "attached", "cache", "owned"}
    still_png = project_root / "smoke-still.png"
    still_png.write_bytes(still.content)
    assert still_png.stat().st_size > 1000

    job = _req(api_client, "POST", f"/projects/{pid}/preview/film", {
        "profile": "draft", "watermark": False})
    deadline = time.time() + 120
    last = None
    while time.time() < deadline:
        last = _req(api_client, "GET", f"/preview/jobs/{job['jobId']}")
        if last["status"] in ("succeeded", "failed", "canceled"):
            break
        time.sleep(0.5)
    assert last is not None and last["status"] == "succeeded", last

    mp4 = project_root / "smoke-film.mp4"
    file_resp = api_client.get(f"/preview/jobs/{job['jobId']}/file")
    assert file_resp.status_code == 200, file_resp.text[:1000]
    mp4.write_bytes(file_resp.content)
    meta = _ffprobe(mp4)
    assert meta["width"] == 960 and meta["height"] == 540 and meta["fps"] == 12
    assert meta["frames"] == 36 and abs(meta["duration"] - 3.0) <= 0.12, meta
    assert last["frames"] == 36 and last["rendered"] > 0 and last["chrome"] in {"new", "attached", "cache", "owned"}

    extracted = project_root / "smoke-frame.png"
    control = project_root / "smoke-frame-ctrl.png"
    for t, dest in (("1.5", extracted), ("0.0", control)):
        r = _run(["ffmpeg", "-y", "-v", "error", "-ss", t, "-i", str(mp4),
                  "-frames:v", "1", str(dest)])
        assert r.returncode == 0, r.stderr[-1000:]
    score = _ssim(still_png, extracted)
    score_ctrl = _ssim(still_png, control)
    print(f"  SSIM 同刻 {score:.6f} / 异刻对照 {score_ctrl:.6f}（风格 {primary}）")
    assert score >= 0.90, f"Chrome/ffmpeg/SSIM 冒烟不一致：同刻 {score} / 异刻 {score_ctrl}"
    assert score > score_ctrl, f"同一时刻的帧还不如异刻对照像：{score} vs {score_ctrl}"
