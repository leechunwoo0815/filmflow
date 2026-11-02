"""R2.5 FR-28 验收：16:9+9:16、SRT、双封面、QC、manifest/rights、zip。"""
from __future__ import annotations
import base64
import json
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from PIL import Image

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240)
ROOT = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects"


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
    return c.post(f"/gates/{gate}/decide", json={"run_id": rid, "decision": "approved",
                                                 "author": "delivery-verify"})


def b64(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode()


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration,size",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    d = json.loads(out); v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return {"width": v["width"], "height": v["height"], "fps": round(int(num) / int(den), 3),
            "duration": round(float(d["format"]["duration"]), 3),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"]),
            "size": int(d["format"]["size"])}


def main() -> int:
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪")
    voice, music = Path("/tmp/voice.wav"), Path("/tmp/music.wav")
    for p, freq, dur in ((voice, 220, 5), (music, 440, 2)):
        if not p.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            f"sine=frequency={freq}:duration={dur}", "-ac", "1",
                            "-ar", "48000", str(p)], check=True)
    styles = req("GET", "/styles?chips=可生产&family=print&limit=5").json()["items"]
    d = req("POST", "/drafts", {"name": "r2_5-delivery", "step": 1}).json()
    root = ROOT / f"r2_5-delivery-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": styles[0]["id"], "alternates": [], "reason": "delivery"}}})
    m = req("POST", f"/drafts/{d['id']}/materialize", {}).json()
    rid, pid = m["run_id"], m["project"]["id"]
    print("run", rid, "project", pid, "root", root, flush=True)
    v = req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "voice.wav", "data": b64(voice), "kind": "voice", "name": "voice"}).json()["take"]
    req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "music.wav", "data": b64(music), "kind": "music", "name": "music"})
    req("POST", f"/projects/{pid}/audio/primary", {"takeId": v["id"]})
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()["content"]
    script = req("GET", f"/projects/{pid}/docs/script").json()["content"]
    segments = [{"text": "".join(script["sentences"][i]["text"] for i in (s.get("source_span") or [])),
                 "start": s["start"], "end": s["end"]} for s in tl["scenes"]]
    req("POST", f"/projects/{pid}/audio/alignment", {"segments": segments, "author": "delivery"})
    req("POST", f"/projects/{pid}/audio/license", {
        "source": "local-sine", "license": "CC0", "authorized": True, "expires": "2099-12-31"})
    req("POST", f"/runs/{rid}/start")
    viewed = False
    t0 = time.time()
    while time.time() - t0 < 300:
        st = status(rid); pend = pending(rid)
        if "B08" in pend: decide("B08", rid)
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for s in tl["scenes"]:
                    req("POST", f"/projects/{pid}/stills/viewed", {"scene": s["id"], "time": 1.0})
                viewed = True
            decide("D03", rid)
        if "D05" in pend and st.get("D04") in ("succeeded", "cached"): decide("D05", rid)
        for gate in ("E07", "F06", "G03", "G07"):
            if gate in pend: decide(gate, rid)
        fails = [(n["id"], (n.get("message") or "")[:160]) for n in
                 req("GET", f"/runs/{rid}/graph").json()["nodes"]
                 if n["status"] == "failed" and n["id"][0] in "DEFG"]
        if fails: raise SystemExit(f"节点失败：{fails}")
        if st.get("G07") in ("succeeded", "cached"): break
        time.sleep(1)
    print("G chain", {k: st.get(k) for k in ("G05", "G06", "G07")}, flush=True)
    assert st.get("G07") in ("succeeded", "cached")
    r = req("POST", f"/projects/{pid}/delivery", {"runId": rid, "profile": "final"})
    assert r.status_code == 202
    jid = r.json()["jobId"]
    t0 = time.time()
    while time.time() - t0 < 600:
        job = req("GET", f"/jobs/{jid}").json()
        if job["status"] in ("succeeded", "failed", "canceled"):
            break
        time.sleep(2)
    print("delivery job", job["status"], "wall %.1fs" % (time.time() - t0), job.get("error_msg"), flush=True)
    assert job["status"] == "succeeded", job
    detail = req("GET", f"/projects/{pid}/deliveries/{rid}").json()
    names = {f["name"] for f in detail["files"]}
    expected = {"master_16x9.mp4", "master_9x16.mp4", "captions.zh.srt", "cover_16x9.jpg",
                "cover_9x16.jpg", "manifest.json", "qc.json", "rights.json", "FilmFlow-delivery.zip"}
    assert names == expected, names
    q = detail["qc"]
    print("qc", q["checks"], q["probing"]["loudness"], q["captions"], flush=True)
    assert q["ok"]
    m16 = probe(root / "out/deliveries" / str(rid) / "master_16x9.mp4")
    m9 = probe(root / "out/deliveries" / str(rid) / "master_9x16.mp4")
    print("masters", m16, m9, flush=True)
    assert (m16["width"], m16["height"], m16["fps"], m16["audio"]) == (1920, 1080, 24, True)
    assert (m9["width"], m9["height"], m9["fps"], m9["audio"]) == (1080, 1920, 24, True)
    assert abs(m16["duration"] - 5.0) <= 0.05 and abs(m9["duration"] - 5.0) <= 0.05
    srt = (root / "out/deliveries" / str(rid) / "captions.zh.srt").read_text(encoding="utf-8")
    assert "风从纸上起。" in srt and "纸不动，风先动。" in srt
    assert all(len(line) <= 16 for line in srt.splitlines() if not line.isdigit() and "-->" not in line)
    assert Image.open(root / "out/deliveries" / str(rid) / "cover_16x9.jpg").size == (1920, 1080)
    assert Image.open(root / "out/deliveries" / str(rid) / "cover_9x16.jpg").size == (1080, 1920)
    manifest = detail["manifest"]
    assert manifest["approvals"] and manifest["env"]["engine"] and manifest["env"]["chrome"]
    with tempfile.TemporaryDirectory() as td:
        zp = root / "out/deliveries" / str(rid) / "FilmFlow-delivery.zip"
        with zipfile.ZipFile(zp) as z:
            z.testzip()
            z.extractall(td)
            inner = set(z.namelist())
        assert {"master_16x9.mp4", "master_9x16.mp4", "captions.zh.srt", "cover_16x9.jpg",
                "cover_9x16.jpg", "manifest.json", "qc.json", "rights.json", "README.txt"} <= inner
        assert (Path(td) / "master_9x16.mp4").exists()
    print("PASS: R2.5 FR-28 交付 v1 验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
