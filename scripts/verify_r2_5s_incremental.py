"""R2.0 Phase 4 验收脚本：5s 新项目跑到 F06；改 S02 文案后新建 Run，验证增量。

前置：./dev.sh（API :7860 / Web :3000）；系统 Chrome。
用法：uv run --project server python scripts/verify_r2_5s_incremental.py
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=180)


def _req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def frame_shas(root: Path) -> dict[int, str]:
    return {int(p.stem): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "out/frames").glob("*.png"))}


def drive(run_id: int, project_id: int, label: str) -> None:
    c.post(f"/runs/{run_id}/start")
    viewed = 0
    failures: list[tuple[str, str]] = []
    t0 = time.time()
    for _ in range(240):
        g = _req("GET", f"/runs/{run_id}/graph")
        st = {n["id"]: n["status"] for n in g["nodes"]}
        pending = {p["gate"] for p in _req("GET", f"/gates/{run_id}/pending")["items"]}
        if "B08" in pending:
            c.post("/gates/B08/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            while viewed < 3:
                c.post(f"/projects/{project_id}/stills/viewed",
                       json={"scene": f"S0{viewed + 1}", "t": 0})
                viewed += 1
            c.post("/gates/D03/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        if "D05" in pending:
            c.post("/gates/D05/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        if "E07" in pending:
            c.post("/gates/E07/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        if "F06" in pending:
            c.post("/gates/F06/decide", json={"run_id": run_id, "decision": "approved", "author": "verify"})
        failures = [(n["id"], (n.get("message") or "")[:300]) for n in g["nodes"]
                    if n["status"] == "failed" and n["id"][0] in "EF"]
        if int(time.time() - t0) % 10 < 3:
            print(f"  [{time.time() - t0:4.0f}s] {label} "
                  + " ".join(f"{k}={st.get(k)}" for k in ("F02", "F03", "F04", "F05", "F06")),
                  flush=True)
        if st.get("F06") in ("succeeded", "cached") or failures:
            break
        time.sleep(2)
    c.post(f"/runs/{run_id}/cancel")
    if failures:
        raise RuntimeError(f"{label} E/F 失败：{failures}")
    if st.get("F06") not in ("succeeded", "cached"):
        raise RuntimeError(f"{label} F06 未完成：{st}")
    print(f"  {label} F06 OK（{time.time() - t0:.0f}s）", flush=True)


def main() -> int:
    health = httpx.get(f"{BASE}/health", timeout=3, trust_env=False)
    if health.status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")
    styles = _req("GET", "/styles?chips=可生产&family=print&limit=5")["items"]
    if not styles:
        raise SystemExit("没有可生产的 print/riso 风格")
    primary = styles[0]["id"]
    d = _req("POST", "/drafts", {"name": "r2-verify-5s", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"r2-verify-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": primary, "alternates": [], "reason": "verify"},
        "brief": {"title": "风从纸上起"}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    rid, pid, wf = r["run_id"], r["project"]["id"], r["workflow_id"]
    proj = Path(r["project"]["root"])
    print(f"run1={rid} project={pid} primary={primary}\nroot={proj}")

    drive(rid, pid, "run1")
    m1 = _req("GET", f"/runs/{rid}/render-manifest")
    s1 = frame_shas(proj)
    if len(s1) != m1["frames"]:
        raise SystemExit(f"run1 帧数 {len(s1)} != manifest {m1['frames']}")
    print(f"manifest1 rendered={m1['renderedFrames']} reused={m1['reusedFrames']} "
          f"scenes={[(s['id'], s['range']) for s in m1['scenes']]}")

    doc = _req("GET", f"/projects/{pid}/docs/script")
    new_text = doc["content"]["text"].replace("纸不动，风先动。", "纸不动，字先动。")
    if new_text == doc["content"]["text"]:
        raise SystemExit("文案未替换，检查源文案")
    _req("PUT", f"/projects/{pid}/docs/script", {
        "content": {"schema": "filmflow.script/1", "title": "风从纸上起", "text": new_text},
        "base_version": doc["version"], "author": "verify"})

    r2 = _req("POST", "/runs", {"workflowId": wf})
    rid2 = r2["id"]
    print(f"run2={rid2} 文案：{new_text}")
    drive(rid2, pid, "run2")
    m2 = _req("GET", f"/runs/{rid2}/render-manifest")
    s2 = frame_shas(proj)
    first_end = int(m1["scenes"][0]["range"][1])
    unchanged = all(s1[i] == s2.get(i) for i in range(first_end))
    changed = sum(1 for i in range(first_end, m2["frames"]) if s1[i] != s2.get(i))
    s1_hash = {s["id"]: s["hash"] for s in m1["scenes"]}
    s2_hash = {s["id"]: s["hash"] for s in m2["scenes"]}

    print(f"manifest2 rendered={m2['renderedFrames']} reused={m2['reusedFrames']}")
    print(f"S01 hash same={s1_hash.get('S01') == s2_hash.get('S01')} "
          f"S02 changed={s1_hash.get('S02') != s2_hash.get('S02')}")
    print(f"frames 0..{first_end - 1} unchanged={unchanged}; "
          f"{first_end}..{m2['frames'] - 1} changed={changed}")

    ok = (m2["renderedFrames"] < m2["frames"] and m2["reusedFrames"] > 0
          and unchanged and s1_hash.get("S01") == s2_hash.get("S01")
          and s1_hash.get("S02") != s2_hash.get("S02"))
    if not ok:
        raise SystemExit("FAIL: 增量断言未通过")
    print("PASS: R2.0 Phase 4 5s 增量验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
