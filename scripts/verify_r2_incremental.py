"""R2.0 场景级增量验收：5s/15s/40s 均可复用。

前置：./dev.sh（API :7860）。
用法：
  uv run --project server python scripts/verify_r2_incremental.py --project 5s
  uv run --project server python scripts/verify_r2_incremental.py --project 40s
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import httpx
from _acceptance import Cleanup, add_keep_flag

BASE = "http://127.0.0.1:7860/api"
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "golden"
REPORT_DIR = ROOT / "docs" / "reports" / "r2-incremental"


def _req(client: httpx.Client, method: str, path: str, payload: dict | None = None):
    r = client.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def frame_shas(root: Path) -> dict[int, str]:
    return {int(p.stem): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "out/frames").glob("*.png"))}


def approve_gates(client: httpx.Client, run_id: int, project_id: int) -> None:
    st = {n["id"]: n["status"] for n in _req(client, "GET", f"/runs/{run_id}/graph")["nodes"]}
    pending = {p["gate"] for p in _req(client, "GET", f"/gates/{run_id}/pending")["items"]}
    if "B08" in pending:
        client.post("/gates/B08/decide", json={"run_id": run_id, "decision": "approved", "author": "incremental-verify"})
    if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
        for _ in range(20):
            status = _req(client, "GET", f"/projects/{project_id}/stills/viewed")
            for scene in status["missing"]:
                client.post(f"/projects/{project_id}/stills/viewed",
                            json={"scene": scene, "t": 0})
            if not _req(client, "GET", f"/projects/{project_id}/stills/viewed")["missing"]:
                break
        client.post("/gates/D03/decide", json={"run_id": run_id, "decision": "approved", "author": "incremental-verify"})
    if "D05" in pending and st.get("D04") in ("succeeded", "cached"):
        client.post("/gates/D05/decide", json={"run_id": run_id, "decision": "approved", "author": "incremental-verify"})
    if "E07" in pending and st.get("E06") in ("succeeded", "cached"):
        client.post("/gates/E07/decide", json={"run_id": run_id, "decision": "approved", "author": "incremental-verify"})
    if "F06" in pending and st.get("F05") in ("succeeded", "cached"):
        client.post("/gates/F06/decide", json={"run_id": run_id, "decision": "approved", "author": "incremental-verify"})


def drive(client: httpx.Client, run_id: int, project_id: int, label: str, timeout: int) -> float:
    client.post(f"/runs/{run_id}/start")
    t0 = time.time()
    last_status: dict[str, str] = {}
    while time.time() - t0 < timeout:
        nodes = _req(client, "GET", f"/runs/{run_id}/graph")["nodes"]
        last_status = {n["id"]: n["status"] for n in nodes}
        approve_gates(client, run_id, project_id)
        failures = [(n["id"], (n.get("message") or "")[:300]) for n in nodes
                    if n["status"] == "failed" and n["id"][0] in "DEF"]
        elapsed = time.time() - t0
        if int(elapsed) % 15 < 3:
            print(f"  [{elapsed:5.0f}s] {label} "
                  + " ".join(f"{k}={last_status.get(k)}" for k in ("F02", "F03", "F04", "F05", "F06")),
                  flush=True)
        if failures:
            raise RuntimeError(f"{label} D/E/F 失败：{failures}")
        if last_status.get("F06") in ("succeeded", "cached"):
            return elapsed
        time.sleep(2)
    raise RuntimeError(f"{label} 等待 F06 超时（{timeout}s）：{last_status}")


def create_project(client: httpx.Client, spec: dict, primary: str) -> dict:
    d = _req(client, "POST", "/drafts", {"name": f"r2-verify-{spec['name']}", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"r2-verify-{spec['name']}-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req(client, "PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": spec["copy"], "profile": spec["profile"],
        "pick": {"primary": primary, "alternates": [], "reason": "incremental-verify"},
        "brief": {"title": spec.get("name", "")}}})
    r = _req(client, "POST", f"/drafts/{d['id']}/materialize", {})
    r["root"] = root
    return r


def change_one_sentence(client: httpx.Client, pid: int, wf: int, scene_index: int) -> tuple[str, str]:
    doc = _req(client, "GET", f"/projects/{pid}/docs/script")
    text = doc["content"]["text"]
    parts = [s for s in text.replace("。", "。 ").replace("！", "！ ").replace("？", "？ ").split(" ") if s]
    idx = min(scene_index, max(0, len(parts) - 1))
    target = parts[idx]
    if target.endswith("。"):
        replacement = target[:-1] + "字。"
    else:
        replacement = target + "字。"
    new_text = text.replace(target, replacement, 1)
    if new_text == text:
        raise RuntimeError(f"无法替换第 {idx} 句：{target}")
    _req(client, "PUT", f"/projects/{pid}/docs/script", {
        "content": {"schema": "filmflow.script/1", "title": doc["content"].get("title", ""), "text": new_text},
        "base_version": doc["version"], "author": "incremental-verify"})
    return target, new_text


def summarize_manifest(m: dict) -> dict:
    return {
        "frames": m["frames"], "fps": m["fps"], "profile": m.get("profile"),
        "renderedFrames": m["renderedFrames"], "reusedFrames": m["reusedFrames"],
        "sceneHashes": {s["id"]: s["hash"] for s in m.get("scenes", [])},
        "sceneRanges": {s["id"]: s["range"] for s in m.get("scenes", [])},
    }


def cleanup_project(root: Path) -> None:
    shutil.rmtree(root / "out" / "frames", ignore_errors=True)
    shutil.rmtree(root / "out" / "proxy", ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, choices=["5s", "15s", "40s"])
    ap.add_argument("--scene-index", type=int, default=1,
                    help="修改第几句（0 基）；5s 默认 1，40s 建议 2")
    ap.add_argument("--timeout", type=int, default=0,
                    help="每轮最长秒数；0=按项目时长自动给预算")
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--archive", action="store_true", default=True)
    add_keep_flag(ap)
    args = ap.parse_args()

    spec = json.loads((FIXTURES / args.project / "spec.json").read_text(encoding="utf-8"))
    duration = float(spec["profile"]["duration"])
    timeout = args.timeout or max(1800, int(duration * 30))
    if args.project == "40s" and args.scene_index == 1:
        args.scene_index = 2
    client = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
    if client.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")
    styles = _req(client, "GET", "/styles?chips=可生产&family=print&limit=5")["items"]
    if not styles:
        raise SystemExit("没有可生产的 print/riso 风格")
    primary = spec.get("primary") or styles[0]["id"]
    if not any(s["id"] == primary for s in styles):
        primary = styles[0]["id"]

    created = create_project(client, spec, primary)
    rid, pid, wf, root = created["run_id"], created["project"]["id"], created["workflow_id"], created["root"]
    # §7-3：建完即登记，跑完/失败都自删（--keep 保留现场；--keep-frames 只管帧目录）
    clean = Cleanup(client, keep=args.keep)
    clean.track(pid, root)
    atexit.register(clean.__exit__, None, None, None)
    print(f"run1={rid} project={pid} primary={primary}\nroot={root}", flush=True)
    try:
        t1 = drive(client, rid, pid, "run1", timeout)
        m1 = _req(client, "GET", f"/runs/{rid}/render-manifest")
        s1 = frame_shas(root)
        if len(s1) != m1["frames"]:
            raise SystemExit(f"run1 帧数 {len(s1)} != manifest {m1['frames']}")
        old_sentence, new_text = change_one_sentence(client, pid, wf, args.scene_index)
        print(f"target sentence={old_sentence!r} -> new text={new_text!r}", flush=True)

        r2 = _req(client, "POST", "/runs", {"workflowId": wf})
        rid2 = r2["id"]
        print(f"run2={rid2}", flush=True)
        t2 = drive(client, rid2, pid, "run2", timeout)
        m2 = _req(client, "GET", f"/runs/{rid2}/render-manifest")
        s2 = frame_shas(root)
        if len(s2) != m2["frames"]:
            raise SystemExit(f"run2 帧数 {len(s2)} != manifest {m2['frames']}")

        ids1 = [s["id"] for s in m1["scenes"]]
        ids2 = [s["id"] for s in m2["scenes"]]
        changed_scenes = [i for i in range(len(ids1)) if m1["scenes"][i]["hash"] != m2["scenes"][i]["hash"]]
        first = changed_scenes[0] if changed_scenes else None
        prefix = m1["scenes"][first]["range"][0] if first is not None else m1["frames"]
        unchanged_prefix = all(s1[i] == s2.get(i) for i in range(prefix))
        reused_prefix_scenes = ids1[:first] == ids2[:first] if first is not None else False
        rendered_ratio = m2["renderedFrames"] / max(1, m2["frames"])
        max_ratio = {"5s": 0.60, "15s": 0.35, "40s": 0.25}[args.project]

        print(f"run1 {t1:.1f}s; run2 {t2:.1f}s; rendered={m2['renderedFrames']}/{m2['frames']} "
              f"({rendered_ratio:.2%}); reused={m2['reusedFrames']}", flush=True)
        print(f"first changed scene={ids1[first] if first is not None else None} "
              f"unchanged_prefix_frames={prefix}", flush=True)
        ok = (first is not None and reused_prefix_scenes and unchanged_prefix
              and rendered_ratio <= max_ratio and t2 < t1)
        report = {
            "schema": "filmflow.r2-incremental-report/1",
            "projectSpec": args.project,
            "primary": primary,
            "project": {"id": pid, "name": root.name},
            "runs": {"run1": rid, "run2": rid2},
            "sceneChange": {"index": first, "sceneId": ids1[first] if first is not None else None,
                            "sentence": old_sentence, "newText": new_text},
            "timings": {"run1Seconds": round(t1, 1), "run2Seconds": round(t2, 1)},
            "manifest1": summarize_manifest(m1),
            "manifest2": summarize_manifest(m2),
            "assertions": {
                "reusedPrefixScenes": reused_prefix_scenes,
                "unchangedPrefixFrames": unchanged_prefix,
                "renderedRatio": round(rendered_ratio, 4),
                "maxRenderedRatio": max_ratio,
                "fasterSecondRun": t2 < t1,
            },
            "ok": ok,
            "status": "pass" if ok else "fail",
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (root / "out" / "verify_incremental.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.archive:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            archived = REPORT_DIR / f"{args.project}-run{rid2}.json"
            archived.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"report archived: {archived}", flush=True)
        if not ok:
            raise SystemExit(f"FAIL: 增量断言未通过：{report['assertions']}")
        print(f"PASS: R2.0 {args.project} 增量验收通过", flush=True)
        return 0
    finally:
        if not args.keep_frames:
            cleanup_project(root)


if __name__ == "__main__":
    sys.exit(main())
