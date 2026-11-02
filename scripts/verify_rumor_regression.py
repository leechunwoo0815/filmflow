"""导入项目回归：干净 rumor 新建 Run → 46/46 + master 可播（G07 QC 的 imported 路径）。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
ROOT = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / "rumor-clean-20261102"


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def graph(rid: int) -> dict:
    return req("GET", f"/runs/{rid}/graph").json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.project_root).resolve()
    project = next(p for p in req("GET", "/projects").json()["items"]
                   if Path(p["root"]).resolve() == root)
    pid = project["id"]
    wfs = req("GET", f"/projects/{pid}/workflows").json()["items"]
    assert wfs, "项目没有 workflow"
    run = req("POST", "/runs", {"workflowId": wfs[0]["id"]}).json()
    rid = run["id"]
    print("project", pid, "workflow", wfs[0]["id"], "new run", rid, flush=True)
    t0 = time.time()
    req("POST", f"/runs/{rid}/start")
    viewed: set[str] = set()
    while time.time() - t0 < 1800:
        g = graph(rid)
        nodes = {n["id"]: n for n in g["nodes"]}
        failed = [(i, (n.get("message") or "")[:160]) for i, n in nodes.items() if n["status"] == "failed"]
        if failed:
            raise SystemExit(f"节点失败：{failed}")
        for item in req("GET", f"/gates/{rid}/pending").json()["items"]:
            gate = item["gate"]
            missing = ((item.get("review") or {}).get("missing") or [])
            for scene in missing:
                if scene not in viewed:
                    req("POST", f"/projects/{pid}/stills/viewed", {"scene": scene, "time": 1.0})
                    viewed.add(scene)
            req("POST", f"/gates/{gate}/decide", {
                "run_id": rid, "decision": "approved", "author": "rumor-regression"})
            print("approved", gate, "missing", len(missing), flush=True)
        final = {"succeeded", "cached"}
        if all(n["status"] in final for n in nodes.values()):
            break
        time.sleep(2)
    g = graph(rid)
    nodes = g["nodes"]
    bad = [(n["id"], n["status"], (n.get("message") or "")[:100]) for n in nodes
           if n["status"] not in ("succeeded", "cached")]
    assert not bad, bad
    assert len(nodes) == 46
    master = root / "out" / "film" / "master.mp4"
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type:format=duration,size", "-of", "json", str(master)],
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    info = {"duration": round(float(d["format"]["duration"]), 3),
            "size": int(d["format"]["size"]),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}
    print("46/46, wall %.1fs, master %s" % (time.time() - t0, info), flush=True)
    assert info["audio"] and abs(info["duration"] - 39.5) <= 0.1
    print("PASS: 干净 rumor 46/46 回归通过（run %d）" % rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
