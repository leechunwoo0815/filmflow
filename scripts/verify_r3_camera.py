"""R3.0 FR-34：时间轴改字/相机/转场 → D01/E03/F04，预览与 final 同刻 SSIM。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
ROOT = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects"
COPY = "风声起。纸不动。第三句。第四句。最后句。"


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def status(rid: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in req("GET", f"/runs/{rid}/graph").json()["nodes"]}


def pending(rid: int) -> set[str]:
    return {x["gate"] for x in req("GET", f"/gates/{rid}/pending").json()["items"]}


def decide(gate: str, rid: int):
    req("POST", f"/gates/{gate}/decide",
        {"run_id": rid, "decision": "approved", "author": "r3-camera"})


def ssim(a: Path, b: Path) -> float:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a), "-i", str(b),
                          "-lavfi", "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim",
                          "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"SSIM Y:([0-9.]+)", res.stderr)
    if not m:
        raise RuntimeError("SSIM 解析失败：" + res.stderr[-300:])
    return float(m[-1])


def main() -> int:
    styles = req("GET", "/styles?chips=可生产&family=print&limit=5").json()["items"]
    d = req("POST", "/drafts", {"name": "r3-camera", "step": 1}).json()
    root = ROOT / f"r3-camera-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": COPY,
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": styles[0]["id"], "alternates": [], "reason": "r3-camera"}}})
    m = req("POST", f"/drafts/{d['id']}/materialize", {}).json()
    pid, rid = m["project"]["id"], m["run_id"]
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()
    version = tl["version"]
    assert len(tl["content"]["scenes"]) == 5
    # 改第三句 + 相机 3 帧 + 4 种转场
    ops = [
        {"op": "set_text", "sceneId": "S03", "text": "改写三。"},
        {"op": "set_camera", "sceneId": "S03", "keyframes": [
            {"t": 0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0},
            {"t": 0.5, "zoom": 1.15, "x": 60, "y": -8, "rotate": 2},
            {"t": 1.0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0}], "anchor": [900, 500]},
        {"op": "set_transition", "sceneId": "S02", "transition": "dissolve", "duration": 0.4},
        {"op": "set_transition", "sceneId": "S03", "transition": "wipe", "duration": 0.4},
        {"op": "set_transition", "sceneId": "S04", "transition": "glitch", "duration": 0.4},
        {"op": "set_transition", "sceneId": "S05", "transition": "push", "duration": 0.4},
    ]
    for op in ops:
        out = req("POST", f"/projects/{pid}/timeline/ops", {**op, "baseVersion": version}).json()
        version = out["version"]
    print("project", pid, "run", rid, "timeline v", version, flush=True)

    req("POST", f"/runs/{rid}/start")
    viewed = False
    t0 = time.time()
    st: dict[str, str] = {}
    while time.time() - t0 < 300:
        st = status(rid); pend = pending(rid)
        if "B08" in pend: decide("B08", rid)
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for s in tl["content"]["scenes"]:
                    req("POST", f"/projects/{pid}/stills/viewed", {"scene": s["id"], "time": 0.5})
                viewed = True
            decide("D03", rid)
        if "D05" in pend and st.get("D04") in ("succeeded", "cached"): decide("D05", rid)
        if "E07" in pend: decide("E07", rid)
        fails = [(n["id"], (n.get("message") or "")[:160]) for n in
                 req("GET", f"/runs/{rid}/graph").json()["nodes"]
                 if n["status"] == "failed" and n["id"][0] in "DEF"]
        if fails: raise SystemExit(f"节点失败：{fails}")
        if st.get("F04") in ("succeeded", "cached"): break
        time.sleep(1)
    assert st.get("F04") in ("succeeded", "cached"), st
    print("run wall %.1fs" % (time.time() - t0), flush=True)

    base_prog = json.loads((root / "scenes" / "S03.base.program.json").read_text(encoding="utf-8"))
    motion_prog = json.loads((root / "scenes" / "S03.program.json").read_text(encoding="utf-8"))
    title = next(x for x in base_prog["layers"] if x["id"] == "L_title")
    assert title["content"] == "改写三。", title["content"]
    assert len(motion_prog["camera"]["keyframes"]) == 3
    assert motion_prog["camera"]["keyframes"][1]["zoom"] == 1.15
    transitions = json.loads((root / "scenes" / "transitions.json").read_text(encoding="utf-8"))
    types = {x["type"] for x in transitions["transitions"]}
    assert {"dissolve", "wipe", "glitch", "push"} <= types, types
    print("✓ D01 文本 override / E03 相机 3 帧 / E04 4 种转场", flush=True)

    t_scene = 2.0 + 0.5  # S03 中点
    pv = c.post(f"/projects/{pid}/preview/still", json={
        "sceneId": "S03", "time": t_scene, "profile": "draft",
        "watermark": False, "motion": True})
    assert pv.status_code == 200, pv.text
    preview = Path("/tmp/r3-camera-preview.png")
    preview.write_bytes(pv.content)
    final = Path("/tmp/r3-camera-final.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t_scene),
                    "-i", str(root / "out" / "film" / "intermediate.mp4"),
                    "-frames:v", "1", "-vf", "scale=960:540", str(final)], check=True)
    score = ssim(preview, final)
    assert score >= 0.97, score
    print("✓ preview vs final SSIM %.6f（同刻 S03 t=%.1fs）" % (score, t_scene), flush=True)
    print("PASS: R3.0 相机/文本/转场 final 一致性通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
