"""FR-35 v2 验收：场景 Take 拼接 + 处理 + 拍点 + −14 LUFS + Stems + G07。"""
from __future__ import annotations

import argparse
import atexit
import base64
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from _acceptance import Cleanup, add_keep_flag

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
ROOT = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects"
COPY = "第一句。第二句。"


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:400]}")
    return r


def b64(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode()


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    return round(float(json.loads(out)["format"]["duration"]), 3)


def status(rid: int) -> dict[str, str]:
    return {n["id"]: n["status"] for n in req("GET", f"/runs/{rid}/graph").json()["nodes"]}


def pending(rid: int) -> set[str]:
    return {x["gate"] for x in req("GET", f"/gates/{rid}/pending").json()["items"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    add_keep_flag(ap)
    args = ap.parse_args()
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    styles = req("GET", "/styles?chips=可生产&family=print&limit=3").json()["items"]
    d = req("POST", "/drafts", {"name": "r3-audio-v2", "step": 1}).json()
    root = ROOT / f"r3-audio-v2-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    req("PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": COPY,
        "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        "pick": {"primary": styles[0]["id"], "alternates": [], "reason": "audio-v2"}}})
    m = req("POST", f"/drafts/{d['id']}/materialize", {}).json()
    pid, rid = m["project"]["id"], m["run_id"]
    # §7-3：建完即登记，跑完/失败都自删（--keep 保留现场）
    clean = Cleanup(c, keep=args.keep)
    clean.track(pid, root)
    atexit.register(clean.__exit__, None, None, None)
    tl = req("GET", f"/projects/{pid}/docs/timeline").json()["content"]
    script = req("GET", f"/projects/{pid}/docs/script").json()["content"]
    scenes = tl["scenes"]
    assert len(scenes) == 2, scenes

    tone_a, tone_b, music = Path("/tmp/fr35-a.wav"), Path("/tmp/fr35-b.wav"), Path("/tmp/fr35-music.wav")
    for p, f, sec in ((tone_a, 220, 2), (tone_b, 440, 2), (music, 660, 2)):
        if not p.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            f"sine=frequency={f}:duration={sec}", "-ac", "1", "-ar", "48000",
                            str(p)], check=True)
    take_a = req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "a.wav", "data": b64(tone_a), "kind": "voice",
        "sceneId": scenes[0]["id"], "name": "S01 take"}).json()["take"]
    take_b = req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "b.wav", "data": b64(tone_b), "kind": "voice",
        "sceneId": scenes[1]["id"], "name": "S02 take"}).json()["take"]
    req("POST", f"/projects/{pid}/audio/upload", {
        "filename": "music.wav", "data": b64(music), "kind": "music", "name": "music"})
    req("POST", f"/projects/{pid}/audio/scene-primary", {"sceneId": scenes[0]["id"], "takeId": take_a["id"]})
    req("POST", f"/projects/{pid}/audio/scene-primary", {"sceneId": scenes[1]["id"], "takeId": take_b["id"]})
    req("POST", f"/projects/{pid}/audio/takes/{take_a['id']}/process",
        {"highpass": True, "denoise": True, "normalize": False})
    req("POST", f"/projects/{pid}/audio/mix", {
        "preset": "-14", "stems": {"voice": 0, "music": -8, "sfx": -120}})
    segments = [{"text": "".join(script["sentences"][i]["text"] for i in (s.get("source_span") or [])),
                 "start": s["start"], "end": s["end"]} for s in scenes]
    req("POST", f"/projects/{pid}/audio/alignment", {"segments": segments, "author": "audio-v2"})
    req("POST", f"/projects/{pid}/audio/license", {
        "source": "local-sine", "license": "CC0", "authorized": True, "expires": "2099-12-31"})
    onsets = req("GET", f"/projects/{pid}/audio/onset?takeId={take_b['id']}").json()
    assert onsets["count"] >= 0
    req("POST", f"/projects/{pid}/audio/markers", {
        "markers": [{"time": scenes[0]["start"], "label": "S01"}], "onsets": onsets["onsets"]})
    print("project", pid, "run", rid, "takes", take_a["id"], take_b["id"],
          "onsets", onsets["count"], flush=True)

    req("POST", f"/runs/{rid}/start")
    viewed = False
    t0 = time.time()
    st: dict[str, str] = {}
    # 冷缓存实测：F02 要渲 120 帧（约 5 分钟，run 333 于 21:24→21:29 完成），
    # 原来的 300s 上限只有热缓存才够——干净机器上会把这条验收误判成失败。
    while time.time() - t0 < 600:
        st = status(rid); pend = pending(rid)
        if "B08" in pend: req("POST", "/gates/B08/decide", {"run_id": rid, "decision": "approved", "author": "audio-v2"})
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for s in scenes:
                    req("POST", f"/projects/{pid}/stills/viewed", {"scene": s["id"], "time": 0.5})
                viewed = True
            req("POST", "/gates/D03/decide", {"run_id": rid, "decision": "approved", "author": "audio-v2"})
        if "D05" in pend and st.get("D04") in ("succeeded", "cached"):
            req("POST", "/gates/D05/decide", {"run_id": rid, "decision": "approved", "author": "audio-v2"})
        for gate in ("E07", "F06", "G03", "G07"):
            if gate in pend:
                req("POST", f"/gates/{gate}/decide", {"run_id": rid, "decision": "approved", "author": "audio-v2"})
        fails = [(n["id"], (n.get("message") or "")[:180]) for n in
                 req("GET", f"/runs/{rid}/graph").json()["nodes"]
                 if n["status"] == "failed" and n["id"][0] in "DEFG"]
        if fails: raise SystemExit(f"节点失败：{fails}")
        if st.get("G07") in ("succeeded", "cached"): break
        time.sleep(1)
    print("run wall %.1fs" % (time.time() - t0), {k: st.get(k) for k in ("G01", "G05", "G06", "G07")}, flush=True)
    assert st.get("G07") in ("succeeded", "cached"), st

    voice = root / "card" / "voice.wav"
    mix = root / "card" / "mix.wav"
    assert abs(duration(voice) - 5.0) <= 0.05, duration(voice)
    assert abs(duration(mix) - 5.0) <= 0.05
    stems = root / "card" / "stems"
    for name in ("voice", "music", "sfx"):
        assert abs(duration(stems / f"{name}.wav") - 5.0) <= 0.05
    arts = req("GET", f"/runs/{rid}/artifacts").json()["items"]
    art = next(a for a in arts if a["node_id"] == "G06" and a["type"] == "JSON")
    metrics = json.loads(req("GET", f"/artifacts/{art['id']}/file").content)
    assert abs(float(metrics["lufs"]) - (-14.0)) <= 1.0, metrics
    assert metrics.get("target_lufs") == -14.0, metrics
    assert metrics.get("sync_verified") is True, metrics
    art5 = next(a for a in arts if a["node_id"] == "G05" and a["type"] == "JSON")
    stems_manifest = json.loads(req("GET", f"/artifacts/{art5['id']}/file").content)
    assert stems_manifest.get("targetLufs") == -14.0
    print("✓ G01 concat 5.0s · G05 mix 5.0s · G06", metrics["lufs"], "LUFS target", metrics["target_lufs"],
          "· stems 5/5/5s", flush=True)
    # 处理后的 take 已写入
    audio = req("GET", f"/projects/{pid}/audio").json()
    ta = next(t for t in audio["takes"] if t["id"] == take_a["id"])
    assert ta.get("processedFile"), ta
    print("✓ processed take", ta["processedFile"], "· markers/onsets",
          len(audio["markers"]["markers"]), len(audio["markers"]["onsets"]), flush=True)

    # 验收项目只保留证据，删渲染帧/proxy
    for sub in ("out/frames", "out/proxy", "out/preview"):
        q = root / sub
        if q.exists(): shutil.rmtree(q)
    print("PASS: FR-35 音频工作台 v2 验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
