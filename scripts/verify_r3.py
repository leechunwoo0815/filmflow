"""R3.0 验收：时间轴 ops/读时/相机/预览、30 版本恢复、审片批注与审片包。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
PROJECTS = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects"


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:400]}")
    return r


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    made = req("POST", "/projects/from-template",
               {"templateId": "product40", "name": f"r3-verify-{int(time.time())}"}).json()
    pid, rid = made["project"]["id"], made["run_id"]
    root = Path(made["project"]["root"])
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()
    doc, version = tl["content"], tl["version"]
    scenes = doc["scenes"]
    assert len(scenes) == 5
    print("project", pid, "run", rid, "scenes", [s["id"] for s in scenes], flush=True)

    # 1. resize/ripple
    s3 = next(s for s in scenes if s["id"] == "S03")
    old_dur = doc["duration"]
    out = req("POST", f"/projects/{pid}/timeline/ops",
              {"op": "resize", "sceneId": "S03", "end": s3["end"] + 2, "baseVersion": version}).json()
    doc, version = out["content"], out["version"]
    assert abs(out["content"]["scenes"][2]["end"] - (s3["end"] + 2)) < 1e-6
    assert abs(out["content"]["scenes"][3]["start"] - out["content"]["scenes"][2]["end"]) < 1e-6
    assert out["content"]["duration"] > old_dur + 1.9
    print("✓ resize S03 +2s → S04/S05 ripple，duration %.2f → %.2f" %
          (old_dur, out["content"]["duration"]), flush=True)

    # 2. split + merge
    s2 = next(s for s in doc["scenes"] if s["id"] == "S02")
    mid = round((s2["start"] + s2["end"]) / 2, 3)
    out = req("POST", f"/projects/{pid}/timeline/ops",
              {"op": "split", "sceneId": "S02", "at": mid, "baseVersion": version}).json()
    doc, version = out["content"], out["version"]
    ids = [s["id"] for s in doc["scenes"]]
    assert ids[:3] == ["S01", "S02", "S02b"]
    halves = doc["scenes"][1:3]
    assert halves[1]["transition"] == "cut" and halves[0]["text"] and halves[1]["text"]
    out = req("POST", f"/projects/{pid}/timeline/ops",
              {"op": "merge", "sceneId": "S02", "nextId": "S02b", "baseVersion": version}).json()
    doc, version = out["content"], out["version"]
    assert "S02b" not in [s["id"] for s in doc["scenes"]]
    print("✓ split S02 → S02/S02b（cut）→ merge 还原", flush=True)

    # 3. 读时阻断 + force
    long_text = "这一段故意写得很长，用来验证两秒钟根本读不完的读时阻断，必须强制确认才能应用。"
    out = req("POST", f"/projects/{pid}/timeline/ops",
              {"op": "set_text", "sceneId": "S01", "text": long_text, "baseVersion": version}).json()
    doc, version = out["content"], out["version"]
    s1 = doc["scenes"][0]
    r = c.post(f"/projects/{pid}/timeline/ops", json={
        "op": "resize", "sceneId": "S01", "end": s1["start"] + 1.2, "baseVersion": version})
    assert r.status_code == 409 and "E_SCENE_READ_OVERFLOW" in r.text, r.text
    out = req("POST", f"/projects/{pid}/timeline/ops", {
        "op": "resize", "sceneId": "S01", "end": s1["start"] + 1.2,
        "baseVersion": version, "force": True}).json()
    doc, version = out["content"], out["version"]
    assert not out["validation"]["ok"]
    print("✓ 读时不足 409 E_SCENE_READ_OVERFLOW；force 后保留告警", flush=True)

    # 4. 相机 3 keyframes + 预览 ≤3s
    kfs = [{"t": 0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0},
           {"t": 0.6, "zoom": 1.16, "x": 70, "y": -8, "rotate": 2},
           {"t": 1.2, "zoom": 1.04, "x": 0, "y": 0, "rotate": 0}]
    out = req("POST", f"/projects/{pid}/timeline/ops", {
        "op": "set_camera", "sceneId": "S01", "keyframes": kfs,
        "anchor": [900, 500], "baseVersion": version}).json()
    doc, version = out["content"], out["version"]
    assert doc["scenes"][0]["camera_keyframes"][1]["rotate"] == 2
    t0 = time.time()
    pv = c.post(f"/projects/{pid}/preview/still", json={
        "sceneId": "S01", "time": doc["scenes"][0]["start"] + 0.6,
        "profile": "draft", "motion": True})
    assert pv.status_code == 200, pv.text
    pv_ms = time.time() - t0
    assert pv_ms < 3.2, pv_ms
    print("✓ 相机 3 keyframes + motion preview %.2fs（%s）" %
          (pv_ms, pv.headers.get("X-Preview-Ms")), flush=True)

    # 5. 30 个版本 + 恢复初始
    initial = req("GET", f"/projects/{pid}/docs/timeline").json()
    base_version = initial["version"]
    for i in range(30):
        out = req("POST", f"/projects/{pid}/timeline/ops", {
            "op": "set_text", "sceneId": "S01", "text": ("甲" if i % 2 == 0 else "乙"),
            "baseVersion": base_version}).json()
        base_version = out["version"]
    versions = req("GET", f"/projects/{pid}/docs/timeline/versions").json()
    assert len(versions["items"]) >= 30
    restored = req("POST", f"/projects/{pid}/docs/timeline/restore",
                   {"version": initial["version"]}).json()
    assert restored["content"]["scenes"][0].get("text") == initial["content"]["scenes"][0].get("text")
    print("✓ 30 个文档版本可恢复（当前 v%s → 初始 v%s）" %
          (versions["current_version"], initial["version"]), flush=True)

    # 6. 审片：10 条批注 export→clear→import、决议、审片包
    proj = next(p for p in req("GET", "/projects").json()["items"] if p["id"] == 174)
    root174 = Path(proj["root"])
    rv_path = root174 / "review" / "review.json"
    rv_path.unlink(missing_ok=True)
    for i in range(10):
        req("POST", "/projects/174/review/comments", {
            "frame": i * 96, "time": i * 4.0, "sceneId": f"S{i % 5 + 1:02d}",
            "kind": "rect" if i % 2 == 0 else "text",
            "category": ["must", "suggest", "question"][i % 3],
            "body": f"R3 验收批注 {i + 1}",
            "geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1} if i % 2 == 0 else {}})
    exported = req("GET", "/projects/174/review/export").content
    rv_path.unlink()
    imp = req("POST", "/projects/174/review/import", json.loads(exported)).json()
    assert imp == {"added": 10, "skipped": 0, "total": 10}, imp
    again = req("POST", "/projects/174/review/import", json.loads(exported)).json()
    assert again["added"] == 0 and again["skipped"] == 10
    req("POST", "/projects/174/review/decisions", {"sceneId": "S03", "decision": "needs_changes"})
    req("POST", "/projects/174/review/decisions", {"decision": "approved"})
    videos = req("GET", "/projects/174/review/videos").json()["items"]
    video = next(v for v in videos if v["node"] == "F04")
    pkg = req("POST", "/projects/174/review/package", {"videoId": video["id"]}).json()
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(pkg["path"]) as z:
            names = set(z.namelist())
            assert {"review.mp4", "review.json", "README.txt"} <= names
            z.extractall(td)
        inner = json.loads((Path(td) / "review.json").read_text(encoding="utf-8"))
        assert len(inner["comments"]) == 10
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "json", str(Path(td) / "review.mp4")],
                             capture_output=True, text=True).stdout
        dur = float(json.loads(out)["format"]["duration"])
        assert abs(dur - 40.0) <= 0.1
    print("✓ 审片 10 条批注 export→clear→import；审片包 %.1fMB / %.1fs" %
          (pkg["bytes"] / 1048576, dur), flush=True)
    print("PASS: R3.0 创作闭环验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
