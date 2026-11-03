"""P0-4a：真实 Chrome + ffmpeg + SSIM 的 1s/12 帧最小出片冒烟。"""
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


def test_render_smoke_1s_12fps(api_client: httpx.Client, project_root: Path):
    d = _req(api_client, "POST", "/drafts", {"name": "smoke-1s", "step": 1})
    styles = _req(api_client, "GET", "/styles?chips=可生产&limit=1")
    primary = styles["items"][0]["id"]
    _req(api_client, "PATCH", f"/drafts/{d['id']}", {
        "step": 5,
        "payload": {
            "root": str(project_root),
            "copy": "冒烟测试。",
            "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 1.0},
            "pick": {"primary": primary, "alternates": [], "reason": "smoke-1s"},
            "brief": {"title": "冒烟测试"},
        },
    })
    created = _req(api_client, "POST", f"/drafts/{d['id']}/materialize", {})
    pid = created["project"]["id"]
    tl = _req(api_client, "GET", f"/projects/{pid}/docs/timeline")
    scene_id = tl["content"]["scenes"][0]["id"]
    assert tl["content"]["fps"] == 24 and tl["content"]["frames"] == 24

    still = api_client.post(f"/projects/{pid}/preview/still", json={
        "sceneId": scene_id, "time": 0.5, "profile": "draft",
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
    assert meta["frames"] == 12 and abs(meta["duration"] - 1.0) <= 0.08
    assert last["frames"] == 12 and last["rendered"] > 0 and last["chrome"] in {"new", "attached", "cache", "owned"}

    extracted = project_root / "smoke-frame.png"
    r = _run([
        "ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(mp4),
        "-frames:v", "1", str(extracted),
    ])
    assert r.returncode == 0, r.stderr[-1000:]
    score = _ssim(still_png, extracted)
    assert score >= 0.95, f"Chrome/ffmpeg/SSIM 冒烟不一致：{score}"
