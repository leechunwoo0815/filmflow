"""R2.0 Phase 6 验收：draft/review/final 档位（FR-24）。

前置：./dev.sh；系统 Chrome。
用法：uv run --project server python scripts/verify_r2_profiles.py
"""
from __future__ import annotations

import argparse
import atexit
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
from _acceptance import Cleanup, add_keep_flag
from PIL import Image

BASE = "http://127.0.0.1:7860/api"
DB = Path.home() / ".filmflow" / "filmflow.db"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)


def _req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def _status(run_id: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in _req("GET", f"/runs/{run_id}/graph")["nodes"]}


def _pending(run_id: int) -> set[str]:
    return {p["gate"] for p in _req("GET", f"/gates/{run_id}/pending")["items"]}


def _drive(run_id: int, project_id: int) -> None:
    viewed = False
    t0 = time.time()
    while time.time() - t0 < 240:
        st = _status(run_id)
        pending = _pending(run_id)
        if "B08" in pending:
            c.post("/gates/B08/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for i in range(3):
                    c.post(f"/projects/{project_id}/stills/viewed", json={"scene": f"S0{i + 1}", "t": 0})
                viewed = True
            c.post("/gates/D03/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        for gate in ("D05", "E07", "F06"):
            if gate in pending:
                c.post(f"/gates/{gate}/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        failures = [(n["id"], (n.get("message") or "")[:160]) for n in _req("GET", f"/runs/{run_id}/graph")["nodes"]
                    if n["status"] == "failed" and n["id"][0] in "DEF"]
        if failures:
            raise SystemExit(f"节点失败：{failures}")
        if st.get("F06") in ("succeeded", "cached"):
            return
        time.sleep(1)
    raise SystemExit("等待 F06 超时")


def _artifacts(run_id: int) -> list[dict]:
    return _req("GET", f"/runs/{run_id}/artifacts")["items"]


def _json_art(items: list[dict], node_id: str, name: str) -> dict:
    for a in items:
        if a["node_id"] == node_id and (a.get("meta_json") or {}).get("name") == name:
            return json.loads(Path(a["path"]).read_text(encoding="utf-8"))
    raise RuntimeError(f"缺产物 {node_id}/{name}")


def _wait_job(job_id: str, timeout: float = 240) -> tuple[dict, float]:
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout:
        last = _req("GET", f"/preview/jobs/{job_id}")
        if last["status"] in ("succeeded", "failed", "canceled"):
            return last, time.time() - t0
        time.sleep(0.5)
    raise RuntimeError(f"job 超时：{last}")


def _ffprobe(path: Path) -> dict:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    st = json.loads(res.stdout)["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"width": st["width"], "height": st["height"],
            "fps": round(int(num) / int(den), 3), "frames": int(st["nb_frames"]),
            "duration": round(float(json.loads(res.stdout)["format"]["duration"]), 3)}


def _ssim(a: Path, b: Path) -> float:
    res = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi",
         "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    m = re.findall(r"SSIM Y:([0-9.]+)", res.stderr)
    if not m:
        raise RuntimeError("SSIM 解析失败")
    return float(m[-1])


def _f02_state(run_id: int) -> dict:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute("select status,cache_key from noderun where run_id=? and node_id='F02'",
                        (run_id,)).fetchone()
        return dict(r) if r else {}
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    add_keep_flag(ap)
    args = ap.parse_args()
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")
    styles = _req("GET", "/styles?chips=可生产&family=print&limit=5")["items"]
    if not styles:
        raise SystemExit("没有可生产的 print/riso 风格")
    primary = styles[0]["id"]
    d = _req("POST", "/drafts", {"name": "r2-profiles", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"r2-profiles-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": primary, "alternates": [], "reason": "profiles-verify"},
        "brief": {"title": "风从纸上起"}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    rid, pid = r["run_id"], r["project"]["id"]
    # §7-3：建完即登记，跑完/失败都自删（--keep 保留现场）
    clean = Cleanup(c, keep=args.keep)
    clean.track(pid, root)
    atexit.register(clean.__exit__, None, None, None)
    print(f"run={rid} project={pid} root={root}", flush=True)
    c.post(f"/runs/{rid}/start")
    _drive(rid, pid)
    items = _artifacts(rid)

    # 1) D02 draft + review 静帧（contact sheet 没有 profile，归为 other）
    pngs = [a for a in items if a["node_id"] == "D02" and a["type"] == "PNG"]
    sizes = sorted({((a.get("meta_json") or {}).get("profile") or "other",
                     Image.open(a["path"]).size) for a in pngs})
    print("D02 stills:", sizes, flush=True)
    assert (("review", (1280, 720)) in sizes) and (("draft", (960, 540)) in sizes)
    d04 = _json_art(items, "D04", "still_metrics.json")
    assert set(d04["coverage"]["review"]) == {"S01", "S02"}
    assert set(d04["coverage"]["draft"]) == {"S01", "S02"}

    # 2) E05 review proxy：1280×720 / 24fps / 120 帧
    proxy = sorted((root / "out/proxy").glob("*.png"))
    psize = Image.open(proxy[0]).size
    print(f"E05 proxy frames={len(proxy)} size={psize}", flush=True)
    assert len(proxy) == 120 and psize == (1280, 720)
    e06 = _json_art(items, "E06", "motion_metrics.json")
    assert e06["profile"] == "review" and e06["fps"] == 24 and e06["policy"]["motion"] is True

    # 3) F02 只跑 final；manifest 带 profileSpec
    manifest = _req("GET", f"/runs/{rid}/render-manifest")
    print("F02 manifest:", {k: manifest.get(k) for k in ("profile", "profileSpec", "fps", "frames")}, flush=True)
    assert manifest["profile"] == "final" and manifest["fps"] == 24 and manifest["frames"] == 120
    assert manifest["profileSpec"]["width"] == 1920 and manifest["profileSpec"]["fps"] == 24
    assert Image.open(root / "out/frames/0000.png").size == (1920, 1080)
    f03 = _json_art(items, "F03", "frame_report.json")
    assert f03["profile"] == "final" and f03["policy"]["ssim"] is True

    # 4) PreviewService draft/review 整片
    for prof, dims, fps, frames in (("draft", (960, 540), 12, 60), ("review", (1280, 720), 24, 120)):
        job = c.post(f"/projects/{pid}/preview/film", json={"profile": prof})
        assert job.status_code == 202, job.text
        done, elapsed = _wait_job(job.json()["jobId"])
        print(f"preview film {prof}: {done['status']} {elapsed:.1f}s frames={done['frames']} "
              f"chrome={done['chrome']}", flush=True)
        assert done["status"] == "succeeded" and done["frames"] == frames
        mp4 = root / "out" / "preview" / f"film_{prof}.mp4"
        meta = _ffprobe(mp4)
        print("  meta:", meta, flush=True)
        assert (meta["width"], meta["height"], meta["fps"], meta["frames"]) == (*dims, fps, frames)
        assert abs(meta["duration"] - 5.0) <= 0.02

    # 5) draft 与 final 场景内容一致（抽帧含转场窗口，防止双实现漂移）
    #    draft 只有 12fps：每个采样帧最多比 final 偏 1/24s，切点/场景起始后 0.5s 的入场动画
    #    窗口里这个偏差肉眼可见，属档位固有近似而非双实现漂移。因此窗口内要求 >=0.90，
    #    稳定段仍要求 >=0.98，两个最差值都打印出来。
    scenes = _req("GET", f"/projects/{pid}/docs/timeline")["content"]["scenes"]
    bounds = [float(s["start"]) for s in scenes] + [float(s["end"]) for s in scenes]
    cut_window = 0.5
    worst = {"steady": 1.0, "cut": 1.0}
    for t in (0.5, 1.5, 2.45, 2.55, 3.2, 3.8, 4.2, 4.8):
        still = c.post(f"/projects/{pid}/preview/still",
                       json={"sceneId": "S01" if t < 2.5 else "S02", "time": t,
                             "profile": "draft", "watermark": False, "debounce": False,
                             "motion": True})
        assert still.status_code == 200, still.text
        p = Path("/tmp") / f"r2-profiles-still-{pid}-{t}.png"
        p.write_bytes(still.content)
        src = root / "out" / "frames" / f"{int(round(t * 24)):04d}.png"
        small = Path("/tmp") / f"r2-profiles-final-{pid}-{t}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                        "scale=960:540:flags=lanczos", str(small)], check=True, timeout=60)
        s = _ssim(small, p)
        near_cut = any(-0.001 <= t - b <= cut_window for b in bounds)
        key = "cut" if near_cut else "steady"
        worst[key] = min(worst[key], s)
        print(f"  SSIM t={t}: {s:.6f} ({'切点/入场窗口' if near_cut else '稳定段'})", flush=True)
    print(f"draft vs final worst SSIM: 稳定段={worst['steady']:.6f} 切点={worst['cut']:.6f}",
          flush=True)
    assert worst["steady"] >= 0.98, worst
    assert worst["cut"] >= 0.90, worst

    # 6) 切档不重跑 final；预览输出跟随项目覆盖
    before = _f02_state(rid)
    changed = _req("PUT", f"/projects/{pid}/render-profile", {
        "draft": {"width": 640, "height": 360, "fps": 10, "crf": 30, "preset": "fast"}})
    print("render profile override:", changed, flush=True)
    after = _f02_state(rid)
    assert before == after, "切档不能重跑/改动已完成 final"
    still = c.post(f"/projects/{pid}/preview/still",
                   json={"sceneId": "S02", "time": 3.0, "profile": "draft", "debounce": False})
    assert still.status_code == 200
    assert Image.open(__import__("io").BytesIO(still.content)).size == (640, 360)
    _req("PUT", f"/projects/{pid}/render-profile", {
        "draft": {"width": 960, "height": 540, "fps": 12, "crf": 28, "preset": "ultrafast"}})
    assert (root / "render.profile.json").exists()

    print("PASS: R2.0 Phase 6 档位验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
