"""R2.0 Phase 7 验收：F02 运行中 kill -9 API，重启后自动恢复（FR-29）。

前置：./dev.sh 正在运行；系统 Chrome。脚本会杀掉并重启 dev.sh。
用法：uv run --project server python scripts/verify_r2_recovery.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
REPO = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url=BASE, timeout=60)
LOCAL = httpx.Client(base_url=BASE, timeout=5)


def _req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def _status(run_id: int) -> tuple[dict[str, str], str]:
    g = _req("GET", f"/runs/{run_id}/graph")
    return {n["id"]: n["status"] for n in g["nodes"]}, g["run"]["status"]


def _pending(run_id: int) -> set[str]:
    return {p["gate"] for p in _req("GET", f"/gates/{run_id}/pending")["items"]}


def _health(timeout: float = 1.0) -> bool:
    try:
        return LOCAL.get("/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def _restart_api() -> None:
    pids = subprocess.run(["pgrep", "-f", "uvicorn app.main:app"],
                          capture_output=True, text=True).stdout.split()
    for p in pids:
        try:
            os.kill(int(p), signal.SIGKILL)
        except OSError:
            pass
    time.sleep(2)
    log = open("/tmp/filmflow-recovery-verify.log", "wb")
    subprocess.Popen(["./dev.sh"], cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)


def main() -> int:
    if not _health(3):
        raise SystemExit("API 未就绪：先 ./dev.sh")
    styles = _req("GET", "/styles?chips=可生产&family=print&limit=5")["items"]
    if not styles:
        raise SystemExit("没有可生产的 print/riso 风格")
    d = _req("POST", "/drafts", {"name": "r2-recovery", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"r2-recovery-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": styles[0]["id"], "alternates": [], "reason": "recovery"}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    rid, pid = r["run_id"], r["project"]["id"]
    print(f"run={rid} project={pid} root={root}", flush=True)
    c.post(f"/runs/{rid}/start")

    t0 = time.time()
    viewed = False
    f02_running = False
    while time.time() - t0 < 180:
        st, _rs = _status(rid)
        pending = _pending(rid)
        if "B08" in pending:
            c.post("/gates/B08/decide", json={"run_id": rid, "decision": "approved", "author": "recovery"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for i in range(3):
                    c.post(f"/projects/{pid}/stills/viewed", json={"scene": f"S0{i + 1}", "t": 0})
                viewed = True
            c.post("/gates/D03/decide", json={"run_id": rid, "decision": "approved", "author": "recovery"})
        if "D05" in pending and st.get("D04") in ("succeeded", "cached"):
            c.post("/gates/D05/decide", json={"run_id": rid, "decision": "approved", "author": "recovery"})
        if "E07" in pending:
            c.post("/gates/E07/decide", json={"run_id": rid, "decision": "approved", "author": "recovery"})
        if st.get("F02") == "running":
            f02_running = True
            break
        time.sleep(0.3)
    if not f02_running:
        raise SystemExit(f"F02 未进入 running：{_status(rid)}")

    time.sleep(1.0)
    kill_t = time.time()
    _restart_api()
    up = False
    for _ in range(120):
        if _health():
            up = True
            break
        time.sleep(0.5)
    if not up:
        raise SystemExit("API 重启失败")
    up_s = time.time() - kill_t
    print(f"api restarted in {up_s:.1f}s; waiting F02 recover", flush=True)

    rec = None
    while time.time() - kill_t < 120:
        try:
            st, _rs = _status(rid)
        except Exception:
            time.sleep(0.5)
            continue
        if st.get("F02") in ("succeeded", "cached"):
            rec = time.time() - kill_t
            break
        if st.get("F02") == "failed":
            raise SystemExit(f"F02 恢复失败：{_status(rid)}")
        time.sleep(0.5)
    if rec is None:
        raise SystemExit(f"F02 60s 未恢复：{_status(rid)}")
    print(f"F02 recovered after {rec:.1f}s", flush=True)
    assert rec <= 60, "kill -9 后必须 ≤60s 恢复"

    for _ in range(120):
        st, _rs = _status(rid)
        if st.get("F05") in ("succeeded", "cached"):
            break
        time.sleep(0.5)
    frames = len(list((root / "out" / "frames").glob("*.png")))
    jobs = [j for j in _req("GET", "/jobs?kind=run")["items"] if j.get("run_id") == rid]
    print(f"F05={st.get('F05')} frames={frames} jobs={[(j['id'], j['status'], j['attempts']) for j in jobs]}",
          flush=True)
    assert st.get("F05") in ("succeeded", "cached")
    assert frames == 120
    assert len(jobs) == 1 and jobs[0]["attempts"] == 1, "一次崩溃应只有 1 个 Job、attempts=1"
    leftover = subprocess.run(["pgrep", "-fl", f"ff-F02-{rid}"], capture_output=True, text=True).stdout.strip()
    assert not leftover, f"残留 Chrome：{leftover}"
    c.post(f"/runs/{rid}/cancel")
    print("PASS: R2.0 Phase 7 崩溃恢复验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
