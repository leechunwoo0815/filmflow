"""R2.5 FR-26 验收：全场景静帧/contact sheet/逐场查看/D05 diff。"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def status(rid: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in req("GET", f"/runs/{rid}/graph").json()["nodes"]}


def pending(rid: int) -> dict[str, dict]:
    return {x["gate"]: x for x in req("GET", f"/gates/{rid}/pending").json()["items"]}


def wait(rid: int, node: str, timeout: float = 180) -> dict[str, str]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = status(rid)
        if st.get(node) in ("succeeded", "cached"):
            return st
        if st.get(node) == "failed":
            raise RuntimeError(f"{node} failed: {req('GET', f'/runs/{rid}/graph').json()}")
        time.sleep(0.5)
    raise RuntimeError(f"wait {node} timeout")


def start(rid: int) -> None:
    req("POST", f"/runs/{rid}/start")


def pass_b08(rid: int) -> None:
    t0 = time.time()
    while time.time() - t0 < 20:
        if "B08" in pending(rid):
            assert approve("B08", rid).status_code == 200
            return
        st = status(rid)
        if st.get("D02") in ("running", "succeeded", "cached") or st.get("B08") in ("succeeded", "cached"):
            return
        time.sleep(0.3)


def approve(gate: str, rid: int) -> httpx.Response:
    return c.post(f"/gates/{gate}/decide", json={"run_id": rid, "decision": "approved", "author": "review-verify"})


def main() -> int:
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪")
    wf = 119  # 40s golden-40s-134
    root = Path("/Users/litianyu/cc-projects/ai-v/filmflow-projects/golden-40s-134")
    viewed_p = root / "card" / "viewed.json"
    viewed_p.unlink(missing_ok=True)
    run_a = req("POST", "/runs", {"workflowId": wf}).json()["id"]
    print("runA", run_a, flush=True); start(run_a)
    pass_b08(run_a)
    wait(run_a, "D02")
    p = pending(run_a)
    assert "D03" in p, p
    # 未看任何场景，D03 必须拒绝
    r = approve("D03", run_a)
    assert r.status_code == 400, f"D03 未看全却批准成功: {r.text}"
    print("D03 blocked before viewing:", r.json()["detail"]["message"], flush=True)
    # 只看 S01，仍拒绝
    scenes = ["S01", "S02", "S03", "S04", "S05"]
    req("POST", "/projects/119/stills/viewed", {"scene": "S01", "time": 1.0})
    r = approve("D03", run_a)
    assert r.status_code == 400, "只看 1 场仍应拒绝"
    for sid in scenes:
        req("POST", "/projects/119/stills/viewed", {"scene": sid, "time": 1.0})
    assert approve("D03", run_a).status_code == 200
    wait(run_a, "D04")
    p = pending(run_a)
    assert "D05" in p, p
    rev = p["D05"].get("review") or {}
    stills = rev.get("stills") or []
    by_scene: dict[str, int] = {}
    for s in stills:
        by_scene[s["scene"]] = by_scene.get(s["scene"], 0) + 1
    print("D05 review scenes:", by_scene, "contact:", bool(rev.get("contactSheet")), flush=True)
    assert len(by_scene) == 5
    assert by_scene["S01"] >= 6 and by_scene["S04"] >= 6 and by_scene["S05"] >= 6
    contact = rev.get("contactSheet") or {}
    assert contact.get("artifact"), "缺 contact sheet"
    meta = req("GET", f"/runs/{run_a}/artifacts").json()["items"]
    cs = next(a for a in meta if a["id"] == contact["artifact"])
    img = Image.open(cs["path"])
    assert img.size == (1920, 1080)
    assert set(contact.get("scenes") or []) == set(scenes)
    assert rev.get("missing") == []
    assert approve("D05", run_a).status_code == 200
    c.post(f"/runs/{run_a}/cancel")

    # 改 S03，Run B：diff 只标 S03
    doc = req("GET", "/projects/119/docs/script").json()
    text = doc["content"]["text"].replace("短句改", "短句再改").replace("短句。", "短句改。")
    if text == doc["content"]["text"]:
        text = text.replace("短句再改", "短句又改")
    req("PUT", "/projects/119/docs/script", {"content": {"schema": "filmflow.script/1",
        "title": "golden-40s", "text": text}, "base_version": doc["version"], "author": "review-verify"})
    run_b = req("POST", "/runs", {"workflowId": wf}).json()["id"]
    print("runB", run_b, flush=True); start(run_b)
    pass_b08(run_b)
    wait(run_b, "D02")
    assert approve("D03", run_b).status_code == 200
    wait(run_b, "D04")
    p = pending(run_b)
    assert "D05" in p, p
    diff = (p["D05"].get("review") or {}).get("diff") or {}
    changed = diff.get("changed") or []
    print("diff changed:", changed, "scenes:", [(d["scene"], d["status"]) for d in diff.get("scenes", [])], flush=True)
    assert changed == ["S03"], f"应只标 S03，实际 {changed}"
    assert approve("D05", run_b).status_code == 200
    c.post(f"/runs/{run_b}/cancel")
    print("PASS: R2.5 FR-26 静帧审阅验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
