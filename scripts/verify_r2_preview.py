"""R2.0 Phase 5 验收：PreviewService（FR-23）。

前置：./dev.sh（API :7860 / Web :3000）；系统 Chrome。
用法：uv run --project server python scripts/verify_r2_preview.py

证据：
- F02 运行中 CDP 附加同一 Chrome 的单帧 p50/p95；
- 同参数二次缓存 ≤300ms；
- 20 并发拖动只保留最后一次（其余 429 superseded）；
- 5s 片段 ≤20s，写 out/preview，不写 out/frames；
- 预览不产生 Artifact/Approval 记录。
"""
from __future__ import annotations

import argparse
import atexit
import concurrent.futures
import io
import json
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
from _acceptance import Cleanup, add_keep_flag
from PIL import Image

BASE = "http://127.0.0.1:7860/api"
DB = Path.home() / ".filmflow" / "filmflow.db"
c = httpx.Client(base_url=BASE, timeout=240)


def _req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def _graph(run_id: int) -> dict:
    return _req("GET", f"/runs/{run_id}/graph")


def _status(run_id: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in _graph(run_id)["nodes"]}


def _pending(run_id: int) -> set[str]:
    return {p["gate"] for p in _req("GET", f"/gates/{run_id}/pending")["items"]}


def _decision_loop(run_id: int, project_id: int, until: tuple[str, ...] = ("F06",)) -> dict[str, str]:
    viewed = False
    t0 = time.time()
    last = {}
    while time.time() - t0 < 240:
        st = _status(run_id)
        last = st
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
        failures = [(n["id"], (n.get("message") or "")[:200]) for n in _graph(run_id)["nodes"]
                    if n["status"] == "failed" and n["id"][0] in "EF"]
        if failures:
            raise RuntimeError(f"E/F 失败：{failures}")
        if all(st.get(n) in ("succeeded", "cached") for n in until):
            return st
        time.sleep(1)
    raise RuntimeError(f"等待 {until} 超时：{last}")


def _counts(run_id: int) -> tuple[int, int]:
    con = sqlite3.connect(DB)
    try:
        arts = con.execute("select count(*) from artifact where run_id=?", (run_id,)).fetchone()[0]
        approvals = con.execute("select count(*) from approval where run_id=?", (run_id,)).fetchone()[0]
    finally:
        con.close()
    return int(arts), int(approvals)


def _png_ok(data: bytes) -> tuple[bool, tuple[int, int], dict]:
    img = Image.open(io.BytesIO(data))
    return (img.info.get("ff_preview") == "1", img.size, dict(img.info))


def _ssim(a: Path, b: Path) -> float:
    res = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi",
         "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    m = re.findall(r"SSIM Y:([0-9.]+)", res.stderr)
    if not m:
        raise RuntimeError("SSIM 解析失败：" + res.stderr[-300:])
    return float(m[-1])


def _ffprobe_video(path: Path) -> dict:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    data = json.loads(res.stdout)
    st = data["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"width": st["width"], "height": st["height"],
            "fps": round(int(num) / int(den), 3), "frames": int(st["nb_frames"]),
            "duration": round(float(data["format"]["duration"]), 3)}


def _wait_job(job_id: str, timeout: float = 90) -> tuple[dict, float]:
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout:
        last = _req("GET", f"/preview/jobs/{job_id}")
        if last["status"] in ("succeeded", "failed", "canceled"):
            return last, time.time() - t0
        time.sleep(0.5)
    raise RuntimeError(f"预览 job 超时：{last}")


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

    d = _req("POST", "/drafts", {"name": "r2-preview", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"r2-preview-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": primary, "alternates": [], "reason": "preview-verify"},
        "brief": {"title": "风从纸上起"}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    rid, pid, wf = r["run_id"], r["project"]["id"], r["workflow_id"]
    proj = Path(r["project"]["root"])
    # §7-3：建完即登记，跑完/失败都自删（--keep 保留现场）
    clean = Cleanup(c, keep=args.keep)
    clean.track(pid, proj)
    atexit.register(clean.__exit__, None, None, None)
    print(f"run1={rid} project={pid} root={proj}", flush=True)
    c.post(f"/runs/{rid}/start")
    _decision_loop(rid, pid)
    print("run1 F06 OK", flush=True)

    # 1) 空闲单帧：临时 Chrome；同参数二次命中缓存
    body = {"sceneId": "S02", "time": 3.0, "profile": "draft"}
    t0 = time.monotonic()
    r1 = c.post(f"/projects/{pid}/preview/still", json={**body, "debounce": False})
    ms1 = (time.monotonic() - t0) * 1000
    if r1.status_code != 200:
        raise SystemExit(f"still 失败 {r1.status_code} {r1.text[:200]}")
    ok, size, info = _png_ok(r1.content)
    chrome1 = r1.headers.get("x-preview-chrome")
    print(f"still idle: {ms1:.0f}ms chrome={chrome1} size={size} watermark={ok} info={info}", flush=True)
    assert ok and size == (960, 540), "预览必须 960×540 且带 PREVIEW 水印"
    t0 = time.monotonic()
    r2 = c.post(f"/projects/{pid}/preview/still", json={**body, "debounce": False})
    ms2 = (time.monotonic() - t0) * 1000
    print(f"still cache: {ms2:.0f}ms cache={r2.headers.get('x-preview-cache')}", flush=True)
    assert r2.status_code == 200 and r2.headers.get("x-preview-cache") == "hit" and ms2 <= 300, "缓存命中必须 ≤300ms"

    # 2) 改两场文案触发性重渲，F02 运行中附加预览
    doc = _req("GET", f"/projects/{pid}/docs/script")
    new_text = doc["content"]["text"].replace("风从纸上起。", "风从纸上再起。").replace("风先动。", "字先动。")
    if new_text == doc["content"]["text"]:
        raise SystemExit("文案未替换")
    _req("PUT", f"/projects/{pid}/docs/script", {
        "content": {"schema": "filmflow.script/1", "title": "风从纸上起", "text": new_text},
        "base_version": doc["version"], "author": "verify"})
    run2 = _req("POST", "/runs", {"workflowId": wf})["id"]
    print(f"run2={run2} text={new_text}", flush=True)
    c.post(f"/runs/{run2}/start")

    samples: list[tuple[float, str, str]] = []
    fired = 0
    viewed2 = False
    t_start = time.time()
    while time.time() - t_start < 240:
        st = _status(run2)
        pending = _pending(run2)
        if "B08" in pending:
            c.post("/gates/B08/decide", json={"run_id": run2, "decision": "approved", "author": "verify"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            if not viewed2:
                for i in range(3):
                    c.post(f"/projects/{pid}/stills/viewed", json={"scene": f"S0{i + 1}", "t": 0})
                viewed2 = True
            c.post("/gates/D03/decide", json={"run_id": run2, "decision": "approved", "author": "verify"})
        for gate in ("D05", "E07", "F06"):
            if gate in pending:
                c.post(f"/gates/{gate}/decide", json={"run_id": run2, "decision": "approved", "author": "verify"})
        if st.get("F02") == "running" and fired < 24:
            t = 2.6 + (fired % 12) * 0.18
            t0 = time.monotonic()
            resp = c.post(f"/projects/{pid}/preview/still",
                          json={"sceneId": "S02", "time": round(t, 2), "profile": "draft", "debounce": False})
            ms = (time.monotonic() - t0) * 1000
            if resp.status_code == 200:
                samples.append((ms, resp.headers.get("x-preview-chrome", ""), resp.headers.get("x-preview-cache", "")))
                print(f"  during F02 {fired}: {ms:.0f}ms chrome={samples[-1][1]} cache={samples[-1][2]}", flush=True)
            fired += 1
        failures = [(n["id"], (n.get("message") or "")[:160]) for n in _graph(run2)["nodes"]
                    if n["status"] == "failed" and n["id"][0] in "EF"]
        if failures:
            raise SystemExit(f"预览导致 E/F 失败：{failures}")
        if st.get("F06") in ("succeeded", "cached"):
            break
        time.sleep(0.35)
    attached = [s for s in samples if s[1] == "attached"]
    print(f"during-F02 samples={len(samples)} attached={len(attached)}", flush=True)
    if len(attached) < 5:
        raise SystemExit(f"F02 运行中附加样本不足：{len(attached)}")
    lat = sorted(s[0] for s in attached)
    p50 = statistics.median(lat)
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
    print(f"attached p50={p50:.0f}ms p95={p95:.0f}ms max={max(lat):.0f}ms", flush=True)
    assert p50 <= 2000 and p95 <= 6000, "F02 运行中预览 p50≤2s / p95≤6s 未达标"
    st = _status(run2)
    assert st.get("F02") in ("succeeded", "cached"), "预览导致 F02 失败"

    # 一致性：单帧预览 vs final 同刻帧（归一化 960×540）SSIM ≥0.98
    final_frame = proj / "out/frames/0072.png"
    still = c.post(f"/projects/{pid}/preview/still",
                   json={"sceneId": "S02", "time": 3.0, "profile": "draft",
                         "watermark": False, "debounce": False})
    assert still.status_code == 200, still.text
    still_p = Path("/tmp") / f"r2-preview-consistency-{pid}.png"
    still_p.write_bytes(still.content)
    final_960 = Path("/tmp") / f"r2-preview-final960-{pid}.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(final_frame),
                    "-vf", "scale=960:540:flags=lanczos", str(final_960)], check=True, timeout=60)
    ssim = _ssim(final_960, still_p)
    print(f"preview vs final normalized SSIM={ssim:.6f}", flush=True)
    assert ssim >= 0.98, "预览与 final 归一化 SSIM 必须 ≥0.98"

    # 后续预览操作不再产生 Artifact/Approval
    arts_before, approvals_before = _counts(run2)

    # 3) 20 并发拖动：只保留最后一次（S01 不同时间，避免缓存命中干扰）
    def one(i: int):
        rr = c.post(f"/projects/{pid}/preview/still",
                    json={"sceneId": "S01", "time": round(0.4 + i * 0.1, 2), "profile": "draft"})
        return rr.status_code, (rr.json().get("detail", {}) or {}).get("code") if rr.status_code >= 400 else ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(one, range(20)))
    ok_n = sum(1 for code, _ in results if code == 200)
    superseded = sum(1 for code, cd in results if code == 429 and cd == "E_PREVIEW_BUSY")
    print(f"latest-wins: 200={ok_n} 429={superseded} codes={sorted(set(results))}", flush=True)
    assert ok_n == 1 and ok_n + superseded == 20, "20 次拖动必须只保留最后一次"

    # 4) 5s 片段（F02 完成后）≤20s，写 out/preview，不写 out/frames
    frames_after_run = len(list((proj / "out/frames").glob("*.png"))) if (proj / "out/frames").exists() else 0
    job = c.post(f"/projects/{pid}/preview/segment",
                 json={"sceneId": "S01", "start": 0, "end": 5, "profile": "draft"})
    assert job.status_code == 202, job.text
    job_id = job.json()["jobId"]
    done, elapsed = _wait_job(job_id)
    print(f"segment {job_id}: {done['status']} {elapsed:.1f}s frames={done['frames']} "
          f"rendered={done['rendered']} reused={done['reused']} chrome={done['chrome']}", flush=True)
    assert done["status"] == "succeeded" and elapsed <= 20, "5s 片段必须 ≤20s"
    mp4 = c.get(f"/preview/jobs/{job_id}/file")
    assert mp4.status_code == 200 and len(mp4.content) > 100_000, "片段文件缺失"
    seg_path = proj / "out/preview" / f"segment_S01_0.0_5.0_draft.mp4"
    meta = _ffprobe_video(seg_path)
    print(f"segment meta={meta}", flush=True)
    assert meta["width"] == 960 and meta["height"] == 540 and meta["fps"] == 12.0
    assert abs(meta["duration"] - 5.0) <= 0.02
    out_dir = proj / "out/preview"
    frame_delta = (len(list((proj / "out/frames").glob("*.png"))) if (proj / "out/frames").exists() else 0) - frames_after_run
    cache = _req("GET", f"/projects/{pid}/preview/cache")
    arts_after, approvals_after = _counts(run2)
    print(f"out/preview={sorted(p.name for p in out_dir.glob('*.mp4'))} frame_delta={frame_delta} "
          f"cache={cache['files']} files/{cache['bytes'] // 1024}KB "
          f"artifacts {arts_before}->{arts_after} approvals {approvals_before}->{approvals_after}", flush=True)
    assert frame_delta == 0, "预览不能写 out/frames"
    assert (arts_before, approvals_before) == (arts_after, approvals_after), "预览不能产生 Artifact/Approval"
    assert cache["files"] > 0

    c.post(f"/runs/{run2}/cancel")
    print("PASS: R2.0 Phase 5 PreviewService 验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
