"""R2.5 FR-26 验收：全场景静帧/contact sheet/逐场查看/D05 diff。

P1-19：自包含——默认用 fixtures/golden/15s 的规格自建项目（不再硬编码
已删除的 golden-40s-134 / workflow 119），跑完自删，DB 计数不变。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_run import build_golden_project  # noqa: E402

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def status(rid: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in req("GET", f"/runs/{rid}/graph").json()["nodes"]}


def pending(rid: int) -> dict[str, dict]:
    return {x["gate"]: x for x in req("GET", f"/gates/{rid}/pending").json()["items"]}


def wait(rid: int, node: str, timeout: float = 300) -> dict[str, str]:
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
        if st.get("D02") in ("running", "succeeded", "cached") or \
                st.get("B08") in ("succeeded", "cached"):
            return
        time.sleep(0.3)


def approve(gate: str, rid: int) -> httpx.Response:
    return c.post(f"/gates/{gate}/decide",
                  json={"run_id": rid, "decision": "approved", "author": "review-verify"})


def _cleanup(pid: int, root: Path) -> None:
    from _acceptance import destroy
    try:
        destroy(c, pid, root)
    except Exception as e:
        print(f"cleanup warn: {e}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", choices=["5s", "15s", "40s"], default="15s",
                    help="黄金规格（决定场景数；15s=4 场，约 2 分钟/Run）")
    args = ap.parse_args()

    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪")

    run_a, pid, root = build_golden_project(args.project, "r2_5-review")
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()["content"]
    scenes = [str(s["id"]) for s in tl["scenes"]]
    long_scenes = [s for s in tl["scenes"] if float(s["end"]) - float(s["start"]) >= 8.0]  # _still_times: ≥8s 才 6 帧
    print(f"runA={run_a} project={pid} scenes={scenes}", flush=True)
    try:
        start(run_a)
        pass_b08(run_a)
        wait(run_a, "D02")
        assert "D03" in pending(run_a), pending(run_a)
        # 未看任何场景，D03 必须拒绝
        r = approve("D03", run_a)
        assert r.status_code == 400, f"D03 未看全却批准成功: {r.text}"
        print("D03 blocked before viewing:", r.json()["detail"]["message"], flush=True)
        # 只看 S01，仍拒绝
        req("POST", f"/projects/{pid}/stills/viewed", {"scene": scenes[0], "time": 1.0})
        r = approve("D03", run_a)
        assert r.status_code == 400, "只看 1 场仍应拒绝"
        for sid in scenes:
            req("POST", f"/projects/{pid}/stills/viewed", {"scene": sid, "time": 1.0})
        assert approve("D03", run_a).status_code == 200
        wait(run_a, "D04")
        p = pending(run_a)
        assert "D05" in p, p
        rev = p["D05"].get("review") or {}
        stills = rev.get("stills") or []
        by_scene: dict[str, int] = {}
        for s in stills:
            by_scene[s["scene"]] = by_scene.get(s["scene"], 0) + 1
        print("D05 review scenes:", by_scene, "contact:", bool(rev.get("contactSheet")),
              flush=True)
        assert len(by_scene) == len(scenes), by_scene
        for s in long_scenes:
            assert by_scene.get(s["id"], 0) >= 6, f"{s['id']} 长场景应 ≥6 帧"
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

        # 改中间一句，Run B：diff 只标该场
        target = scenes[2] if len(scenes) >= 3 else scenes[-1]
        scene_text = next(str(s.get("text") or s.get("meaning") or "")
                          for s in tl["scenes"] if str(s["id"]) == target)
        new_text = scene_text.rstrip("。") + "了。"
        doc = req("GET", f"/projects/{pid}/docs/timeline").json()
        content = doc["content"]
        for s in content["scenes"]:
            if str(s["id"]) == target:
                s["text"] = new_text
        req("PUT", f"/projects/{pid}/docs/timeline",
            {"content": content, "base_version": doc["version"],
             "author": "review-verify"})
        wf_id = req("GET", f"/runs/{run_a}").json()["workflow_id"]
        run_b = req("POST", "/runs", {"workflowId": wf_id}).json()["id"]
        print(f"runB={run_b} 改 {target}: {scene_text} -> {new_text}", flush=True)
        start(run_b)
        pass_b08(run_b)
        wait(run_b, "D02")
        assert approve("D03", run_b).status_code == 200
        wait(run_b, "D04")
        p = pending(run_b)
        assert "D05" in p, p
        diff = (p["D05"].get("review") or {}).get("diff") or {}
        changed = diff.get("changed") or []
        print("diff changed:", changed, "scenes:",
              [(d["scene"], d["status"]) for d in diff.get("scenes", [])], flush=True)
        assert changed == [target], f"应只标 {target}，实际 {changed}"
        assert approve("D05", run_b).status_code == 200
        c.post(f"/runs/{run_b}/cancel")
        print("PASS: R2.5 FR-26 静帧审阅验收通过")
        return 0
    finally:
        _cleanup(pid, root)


if __name__ == "__main__":
    sys.exit(main())
