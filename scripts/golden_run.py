"""FR-30 黄金项目：建项目 → F06 → 6 帧 SSIM/pHash + 文案断言。

用法：
  uv run --project server python scripts/golden_run.py --project 5s
  uv run --project server python scripts/golden_run.py --project 5s --update
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageChops

BASE = "http://127.0.0.1:7860/api"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.engine.fpscalc import frames_for, norm_fps  # noqa: E402
FIXTURES = ROOT / "fixtures" / "golden"
REPORT_DIR = ROOT / "docs" / "reports" / "golden"
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
            _req("POST", "/gates/B08/decide", {"run_id": run_id, "decision": "approved", "author": "golden"})
        if "D03" in pending and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                # 逐场门禁要求**每个场景**都看过；写死 3 场会把 4/5 场的项目永远卡在 D03
                scenes = _req("GET", f"/projects/{project_id}/docs/timeline")["content"].get("scenes", [])
                for s in scenes:
                    _req("POST", f"/projects/{project_id}/stills/viewed", {"scene": s["id"], "t": 0})
                viewed = True
            _req("POST", "/gates/D03/decide", {"run_id": run_id, "decision": "approved", "author": "golden"})
        if "D05" in pending and st.get("D04") in ("succeeded", "cached"):
            _req("POST", "/gates/D05/decide", {"run_id": run_id, "decision": "approved", "author": "golden"})
        if "E07" in pending:
            _req("POST", "/gates/E07/decide", {"run_id": run_id, "decision": "approved", "author": "golden"})
        if "F06" in pending:
            _req("POST", "/gates/F06/decide", {"run_id": run_id, "decision": "approved", "author": "golden"})
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


def build_golden_project(name: str, label: str = "") -> tuple[int, int, Path, str]:
    """按 fixtures/golden/<name>/spec.json 建项目并 materialize；返回 (run_id, project_id, root, primary)。

    P1-19：供 verify_r2_5_review 等验收脚本复用，替代硬编码演示项目 ID。
    """
    spec = json.loads((FIXTURES / name / "spec.json").read_text(encoding="utf-8"))
    primary = _pick_style(spec)
    d = _req("POST", "/drafts", {"name": label or f"golden-{name}", "step": 1})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"golden-{name}-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": spec["copy"], "profile": spec["profile"],
        "pick": {"primary": primary, "alternates": [], "reason": "golden"},
        "brief": {"title": spec.get("name", "")}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    return r["run_id"], r["project"]["id"], root, primary


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _environment(root: Path) -> dict:
    """黄金报告的环境指纹（专家 P0-4b：基线绑 Chrome/ffmpeg/字体/风格库，报告必须能看出来）。

    没有这一段时，Chrome 自动升级或字体换版都会让 SSIM 莫名其妙掉下来，
    而报告里没有任何线索能区分"代码回归"和"环境变了"。
    """
    import platform

    from app.config import detect_chrome, settings
    from app.engine.cachekey import EXECUTOR_VERSION

    def _version(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
            return (r.stdout or r.stderr).splitlines()[0].strip()[:160]
        except (OSError, subprocess.SubprocessError, IndexError):
            return ""

    chrome = detect_chrome()
    font = root / "fonts" / "src" / "NotoSansSC[wght].ttf"
    if not font.exists():
        font = settings.home / "cache" / "fonts" / "NotoSansSC[wght].ttf"
    stats = settings.style_library_root / "_统计.json"
    return {
        "executorVersion": EXECUTOR_VERSION,
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "chrome": _version([chrome, "--version"]) if chrome else "",
        "ffmpeg": _version(["ffmpeg", "-version"]),
        "fontSha256": _sha(font),
        "styleLibrary": str(settings.style_library_root),
        "styleLibraryStatsSha256": _sha(stats),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, choices=["5s", "15s", "40s"])
    ap.add_argument("--update", action="store_true", help="写 baseline（首次/有意更新）")
    ap.add_argument("--reason", default="", help="--update 的理由（必填，写进基线台账）")
    ap.add_argument("--keep", action="store_true", help="保留本次黄金项目（默认跑完自删）")
    ap.add_argument("--resolution", choices=["thumb", "original", "both"], default="thumb",
                    help="thumb=兼容旧基线；original=1920×1080 原帧 SSIM；both=两种都跑")
    ap.add_argument("--archive", action="store_true", default=True,
                    help="将 golden_report 同步到 docs/reports/golden（默认开启）")
    args = ap.parse_args()
    if args.update and not args.reason.strip():
        raise SystemExit("--update 必须给 --reason：改基线是有后果的决定，要留下台账（P0-4b）")
    resolutions = ["thumb", "original"] if args.resolution == "both" else [args.resolution]
    spec = json.loads((FIXTURES / args.project / "spec.json").read_text(encoding="utf-8"))
    profile = spec["profile"]
    duration = float(profile["duration"])
    fps = norm_fps(profile["fps"])          # P1-12：验收脚本自己也不能再 int(fps)
    frames = frames_for(duration, fps)
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")
    rid, pid, root, primary = build_golden_project(args.project)
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

    times = [round((i + 0.5) * duration / 6, 3) for i in range(6)]
    resolution_reports = []
    for resolution in resolutions:
        baseline_dir = FIXTURES / args.project / ("baseline" if resolution == "thumb" else "baseline_original")
        baseline_json = baseline_dir / ("baseline.json" if resolution == "thumb" else "baseline_original.json")
        old = json.loads(baseline_json.read_text(encoding="utf-8")) if baseline_json.exists() else {}
        hashes, ssims, details, src_shas = [], [], [], []
        for i, t in enumerate(times):
            idx = min(frames - 1, int(round(t * fps)))
            src = root / "out" / "frames" / f"{idx:04d}.png"
            if not src.exists():
                raise RuntimeError(f"缺帧 {idx}（t={t}）")
            cur = Path("/tmp") / f"golden-{args.project}-{resolution}-{i}.png"
            if resolution == "thumb":
                _thumb(src, cur)
            else:
                cur.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, cur)
            h = phash(Image.open(cur))
            src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
            hashes.append(h)
            src_shas.append(src_sha)
            if args.update:
                dst = baseline_dir / f"frame_{i}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cur, dst)
                ssims.append(1.0)
                print(f"  update {resolution} frame {i} t={t} phash={h}", flush=True)
                continue
            base = baseline_dir / f"frame_{i}.png"
            if not base.exists() or not old:
                raise RuntimeError(f"缺 {resolution} baseline：先运行 --project {args.project} --resolution {resolution} --update")
            s = _ssim(base, cur)
            dist = hamming(old["phash"][i], h)
            ssims.append(s)
            details.append({"frame": i, "time": t, "index": idx, "ssim": round(s, 6),
                            "phash": h, "phashDistance": dist, "sourceSha256": src_sha})
            print(f"  {resolution} frame {i} t={t}: SSIM={s:.6f} pHashDist={dist}", flush=True)
            if s < 0.98 or dist > 6:
                diff = ImageChops.difference(Image.open(base).convert("RGB"), Image.open(cur).convert("RGB"))
                diff = diff.point(lambda x: min(255, x * 4))
                diff.save(root / "out" / f"golden_diff_{resolution}_{i}.png")
                raise RuntimeError(f"视觉回归失败 resolution={resolution} frame={i} t={t} SSIM={s:.4f} pHashDist={dist}；"
                                   f"diff={root / 'out' / f'golden_diff_{resolution}_{i}.png'}")

        resolution_reports.append({
            "resolution": resolution,
            "baselineDir": baseline_dir.relative_to(ROOT).as_posix(),
            "times": times,
            "phash": hashes,
            "ssim": ssims,
            "sourceSha256": src_shas,
            "details": details,
        })
        if args.update:
            baseline_json.parent.mkdir(parents=True, exist_ok=True)
            history = list(old.get("updateHistory") or [])
            history.append({
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reason": args.reason.strip(), "runId": rid,
                "environment": _environment(root)})
            baseline_json.write_text(json.dumps({
                "schema": "filmflow.golden-baseline/2", "project": args.project,
                "resolution": resolution, "primary": primary, "profile": profile,
                "times": times, "phash": hashes, "sourceSha256": src_shas,
                "sceneCount": len(task.get("scenes", [])),
                "updateHistory": history[-20:]}, ensure_ascii=False, indent=1), encoding="utf-8")

    env = _environment(root)
    report = {"schema": "filmflow.golden-report/3", "project": args.project,
              "runId": rid, "primary": primary, "profile": profile,
              "frames": frames, "sceneCount": len(task.get("scenes", [])),
              "resolutions": resolution_reports, "update": args.update,
              "updateReason": args.reason.strip(),
              "status": "updated" if args.update else "pass",
              "environment": env,
              "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print(f"env: EXECUTOR={env['executorVersion']} · {env['chrome'][:40]} · "
          f"{env['ffmpeg'][:40]} · font={env['fontSha256'][:12]}", flush=True)
    (root / "out" / "golden_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.archive:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        for rr in resolution_reports:
            archived = REPORT_DIR / f"{args.project}-{rr['resolution']}-run{rid}.json"
            archived.write_text(json.dumps({**report, "resolution": rr["resolution"],
                                            "summary": rr}, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            print(f"  archived report: {archived}", flush=True)
    print(f"{'UPDATED' if args.update else 'PASS'}: {args.project} "
          f"resolutions={','.join(resolutions)} report={root / 'out' / 'golden_report.json'}")
    if not args.keep:
        # 跑完自删：黄金项目 541MB 一个，留着就是残留（生产库里曾积了 6 个 golden-5s）
        sys.path.insert(0, str(ROOT / "scripts"))
        from _acceptance import destroy
        destroy(c, pid, root)
        print(f"已自删黄金项目 {pid}（{root.name}）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
