"""R2.5 FR-27 验收：Take/波形/手动对齐/许可/G05 混音/Stems/G06/G07。"""
from __future__ import annotations

import argparse
import atexit
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from _acceptance import Cleanup, add_keep_flag

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


def decide(gate: str, rid: int) -> int:
    return c.post(f"/gates/{gate}/decide", json={"run_id": rid, "decision": "approved",
                                                 "author": "audio-verify"}).status_code


def b64(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode()


def ffprobe_dur(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
    return round(float(json.loads(r.stdout)["format"]["duration"]), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    add_keep_flag(ap)
    args = ap.parse_args()
    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪")
    voice = Path("/tmp/voice.wav")
    music = Path("/tmp/music.wav")
    if not voice.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=220:duration=5", "-ac", "1", "-ar", "48000", str(voice)], check=True)
    if not music.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-ac", "1", "-ar", "48000", str(music)], check=True)
    styles = req("GET", "/styles?chips=可生产&family=print&limit=5").json()["items"]
    d = req("POST", "/drafts", {"name": "r2_5-audio", "step": 1}).json()
    root = ROOT / f"r2_5-audio-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": "风从纸上起。纸不动，风先动。",
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": styles[0]["id"], "alternates": [], "reason": "audio"}}})
    m = req("POST", f"/drafts/{d['id']}/materialize", {}).json()
    rid, pid = m["run_id"], m["project"]["id"]
    # §7-3：建完即登记，跑完/失败/被杀外的任何退出路径都自删（--keep 保留现场）
    clean = Cleanup(c, keep=args.keep)
    clean.track(pid, root)
    atexit.register(clean.__exit__, None, None, None)
    print("run", rid, "project", pid, "root", root, flush=True)
    v = req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "voice.wav", "data": b64(voice), "kind": "voice", "name": "voice"}).json()["take"]
    mu = req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "music.wav", "data": b64(music), "kind": "music", "name": "music"}).json()["take"]
    req("POST", f"/projects/{pid}/audio/primary", {"takeId": v["id"]})
    t0 = time.monotonic()
    wave = req("GET", f"/projects/{pid}/audio/waveform?takeId={v['id']}&w=1200").json()
    wav_ms = (time.monotonic() - t0) * 1000
    print(f"waveform {len(wave['peaks'])} peaks in {wav_ms:.0f}ms", flush=True)
    assert len(wave["peaks"]) == 1200 and wav_ms < 1000
    # 手动对齐：段末 = 场景 last_text_at（G06 口径），文本来自 script source_span
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()["content"]
    script = req("GET", f"/projects/{pid}/docs/script").json()["content"]
    segments = []
    for s in tl["scenes"]:
        text = "".join(script["sentences"][i]["text"] for i in (s.get("source_span") or [])
                       if 0 <= i < len(script["sentences"]))
        segments.append({"text": text, "start": s["start"], "end": s["end"]})
    req("POST", f"/projects/{pid}/audio/alignment", {"segments": segments, "author": "audio-verify"})
    req("POST", f"/projects/{pid}/audio/license", {
        "source": "local-sine", "license": "CC0", "authorized": True, "expires": "2099-12-31"})
    req("POST", f"/runs/{rid}/start")
    viewed = False
    t0 = time.time()
    st: dict[str, str] = {}
    while time.time() - t0 < 300:
        st = status(rid)
        pend = pending(rid)
        if "B08" in pend:
            decide("B08", rid)
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for sid in [x["id"] for x in tl["scenes"]]:
                    req("POST", f"/projects/{pid}/stills/viewed", {"scene": sid, "time": 1.0})
                viewed = True
            decide("D03", rid)
        if "D05" in pend and st.get("D04") in ("succeeded", "cached"):
            decide("D05", rid)
        for gate in ("E07", "F06", "G03", "G07"):
            if gate in pend:
                decide(gate, rid)
        fails = [(n["id"], (n.get("message") or "")[:160]) for n in
                 req("GET", f"/runs/{rid}/graph").json()["nodes"]
                 if n["status"] == "failed" and n["id"][0] in "DEFG"]
        if fails:
            raise SystemExit(f"节点失败：{fails}")
        if st.get("G07") in ("succeeded", "cached"):
            break
        time.sleep(1)
    print("nodes", {k: st.get(k) for k in ("G01", "G02", "G05", "G06", "G07")}, flush=True)
    assert st.get("G05") in ("succeeded", "cached") and st.get("G06") in ("succeeded", "cached")
    assert st.get("G07") in ("succeeded", "cached")
    arts = req("GET", f"/runs/{rid}/artifacts").json()["items"]
    g02 = next(a for a in arts if a["node_id"] == "G02" and a["type"] == "JSON")
    align = json.loads(Path(g02["path"]).read_text())
    assert align["source"] == "manual"
    g06 = next(a for a in arts if a["node_id"] == "G06" and a["type"] == "JSON")
    metrics = json.loads(Path(g06["path"]).read_text())
    print("audio metrics", {k: metrics.get(k) for k in ("lufs", "true_peak", "sync_dev_s", "sync_verified")}, flush=True)
    assert metrics["sync_verified"] is True and metrics["sync_dev_s"] <= 0.15
    assert -17.0 <= metrics["lufs"] <= -15.0
    mix = root / "card" / "mix.wav"
    assert abs(ffprobe_dur(mix) - 5.0) <= 0.02
    for name in ("voice", "music", "sfx"):
        p = root / "card" / "stems" / f"{name}.wav"
        assert p.exists(), p
        d = ffprobe_dur(p)
        print("stem", name, d, flush=True)
        assert abs(d - 5.0) <= 1 / 24
    master = root / "out" / "film" / "master.mp4"
    assert master.exists()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type", "-of", "json", str(master)],
                           capture_output=True, text=True).stdout
    meta = json.loads(probe)
    print("master", meta, flush=True)
    assert abs(float(meta["format"]["duration"]) - 5.0) <= 0.02
    assert any(s["codec_type"] == "audio" for s in meta["streams"])
    print("PASS: R2.5 FR-27 音频工作台验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
