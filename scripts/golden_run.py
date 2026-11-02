"""FR-30 黄金项目：建项目 → F06 → 6 帧 SSIM/pHash + 文案断言。

用法：
  uv run --project server python scripts/golden_run.py --project 5s
  uv run --project server python scripts/golden_run.py --project 5s --update
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageChops

BASE = "http://127.0.0.1:7860/api"
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "golden"
c = httpx.Client(base_url=BASE, timeout=240)
SENT_RE = re.compile(r"(?<=[。！？；!?;])")


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
    while time.time() - t0 < 900:
        st = _status(run_id)
        pending = _pending(run_id)
        if "B08" in pending:
            c.post("/gates/B08/decide", json={"run_id": run_id, "decision": "approved", "author": "golden"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for i in range(3):
                    c.post(f"/projects/{project_id}/stills/viewed", json={"scene": f"S0{i + 1}", "t": 0})
                viewed = True
            c.post("/gates/D03/decide", json={"run_id": run_id, "decision": "approved", "author": "golden"})
        if "D05" in pending and st.get("D04") in ("succeeded", "cached"):
            c.post("/gates/D05/decide", json={"run_id": run_id, "decision": "approved", "author": "golden"})
        if "E07" in pending:
            c.post("/gates/E07/decide", json={"run_id": run_id, "decision": "approved", "author": "golden"})
        if "F06" in pending:
            c.post("/gates/F06/decide", json={"run_id": run_id, "decision": "approved", "author": "golden"})
        failures = [(n["id"], (n.get("message") or "")[:200]) for n in
                    _req("GET", f"/runs/{run_id}/graph")["nodes"]
                    if n["status"] == "failed" and n["id"][0] in "DEF"]
        if failures:
            raise RuntimeError(f"节点失败：{failures}")
        if st.get("F06") in ("succeeded", "cached"):
            return
        time.sleep(1)
    raise RuntimeError("等待 F06 超时")


def _pick_style(spec: dict) -> str:
    primary = spec.get("primary")
    if primary:
        try:
            s = _req("GET", f"/styles/{primary}")
            if s.get("available") and s.get("tokens_status") == "complete":
                return primary
        except Exception:
            pass
    family = spec.get("style_family") or "print"
    items = _req("GET", f"/styles?chips=可生产&family={family}&limit=5")["items"]
    if not items:
        raise RuntimeError(f"没有可生产的 {family} 风格")
    print(f"warning: primary {primary} 不可用，改用 {items[0]['id']}", flush=True)
    return items[0]["id"]


def _dct_matrix(n: int = 32) -> np.ndarray:
    c = np.zeros((n, n))
    for k in range(n):
        scale = math.sqrt(1 / n) if k == 0 else math.sqrt(2 / n)
        for i in range(n):
            c[k, i] = scale * math.cos(math.pi * (2 * i + 1) * k / (2 * n))
    return c


_DCT = _dct_matrix()


def phash(img: Image.Image, bits: int = 64) -> str:
    g = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=float)
    d = _DCT @ g @ _DCT.T
    low = d[:8, :8].flatten()
    med = np.median(low[1:])
    bs = (low > med).astype(np.uint8)
    return "".join(f"{int(''.join(map(str, bs[i:i + 8])), 2):02x}" for i in range(0, bits, 8))


def hamming(a: str, b: str) -> int:
    return sum(bin(int(x, 16) ^ int(y, 16)).count("1") for x, y in zip(a, b))


def _ssim(a: Path, b: Path) -> float:
    res = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi",
         "[0:v]format=gray[x];[1:v]format=gray[y];[x][y]ssim", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    m = re.findall(r"SSIM Y:([0-9.]+)", res.stderr)
    if not m:
        raise RuntimeError("SSIM 解析失败")
    return float(m[-1])


def _thumb(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB")
    img.thumbnail((480, 270), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, choices=["5s", "15s", "40s"])
    ap.add_argument("--update", action="store_true", help="写 baseline（首次/有意更新）")
    args = ap.parse_args()
    spec = json.loads((FIXTURES / args.project / "spec.json").read_text(encoding="utf-8"))
    profile = spec["profile"]
    duration = float(profile["duration"])
    fps = int(profile["fps"])
    frames = round(duration * fps)
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")
    primary = _pick_style(spec)
    d = _req("POST", "/drafts", {"name": f"golden-{args.project}", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"golden-{args.project}-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": spec["copy"], "profile": profile,
        "pick": {"primary": primary, "alternates": [], "reason": "golden"},
        "brief": {"title": spec.get("name", "")}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    rid, pid = r["run_id"], r["project"]["id"]
    print(f"golden={args.project} run={rid} project={pid} root={root}", flush=True)
    c.post(f"/runs/{rid}/start")
    _drive(rid, pid)

    manifest = _req("GET", f"/runs/{rid}/render-manifest")
    assert manifest["profile"] == "final"
    assert manifest["frames"] == frames and manifest["fps"] == fps, manifest
    task = json.loads((root / "card" / "task.json").read_text(encoding="utf-8"))
    joined = "".join(s.get("meaning", "") for s in task.get("scenes", []))
    sentences = [s for s in SENT_RE.split(spec["copy"]) if s.strip()]
    missing = [s for s in sentences if s not in joined]
    if missing:
        raise RuntimeError(f"场景文案缺句：{missing}")
    print(f"text ok: {len(sentences)} sentences / {len(task.get('scenes', []))} scenes", flush=True)

    baseline_dir = FIXTURES / args.project / "baseline"
    baseline_json = baseline_dir / "baseline.json"
    old = json.loads(baseline_json.read_text(encoding="utf-8")) if baseline_json.exists() else {}
    times = [round((i + 0.5) * duration / 6, 3) for i in range(6)]
    hashes, ssims, details = [], [], []
    for i, t in enumerate(times):
        idx = min(frames - 1, int(round(t * fps)))
        src = root / "out" / "frames" / f"{idx:04d}.png"
        if not src.exists():
            raise RuntimeError(f"缺帧 {idx}（t={t}）")
        cur = Path("/tmp") / f"golden-{args.project}-{i}.png"
        _thumb(src, cur)
        h = phash(Image.open(cur))
        hashes.append(h)
        if args.update:
            dst = baseline_dir / f"frame_{i}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            Image.open(cur).save(dst)
            ssims.append(1.0)
            print(f"  update frame {i} t={t} phash={h}", flush=True)
            continue
        base = baseline_dir / f"frame_{i}.png"
        if not base.exists() or not old:
            raise RuntimeError(f"缺 baseline：先运行 --project {args.project} --update")
        s = _ssim(base, cur)
        dist = hamming(old["phash"][i], h)
        ssims.append(s)
        details.append({"frame": i, "time": t, "index": idx, "ssim": round(s, 6),
                        "phash": h, "phashDistance": dist})
        print(f"  frame {i} t={t}: SSIM={s:.6f} pHashDist={dist}", flush=True)
        if s < 0.98 or dist > 6:
            diff = ImageChops.difference(Image.open(base).convert("RGB"), Image.open(cur).convert("RGB"))
            diff = diff.point(lambda x: min(255, x * 4))
            diff.save(root / "out" / f"golden_diff_{i}.png")
            raise RuntimeError(f"视觉回归失败 frame={i} t={t} SSIM={s:.4f} pHashDist={dist}；"
                               f"diff={root / 'out' / f'golden_diff_{i}.png'}")

    report = {"schema": "filmflow.golden-report/1", "project": args.project,
              "runId": rid, "primary": primary, "profile": profile,
              "frames": frames, "sceneCount": len(task.get("scenes", [])),
              "times": times, "phash": hashes, "ssim": ssims, "details": details,
              "update": args.update, "status": "updated" if args.update else "pass"}
    if args.update:
        baseline_json.parent.mkdir(parents=True, exist_ok=True)
        baseline_json.write_text(json.dumps({
            "schema": "filmflow.golden-baseline/1", "project": args.project,
            "primary": primary, "profile": profile, "times": times,
            "phash": hashes, "sceneCount": len(task.get("scenes", []))},
            ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "out" / "golden_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'UPDATED' if args.update else 'PASS'}: {args.project} "
          f"({len(times)} frames, report={root / 'out' / 'golden_report.json'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
