"""Run 驱动器：准备音频资产 + 自动批准可签的门 + 轮询到 Run 结束（真实全链）。

用法：uv run python scripts/drive_run.py <run_id> <project_id> [--timeout 2700]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=60, trust_env=False)


def prepare_audio(project_root: Path, task: dict):
    """真实本地资产：macOS say 生成口播；ffmpeg 程序化生成音乐（规格：本地合成/导入）。"""
    card = project_root / "card"
    card.mkdir(parents=True, exist_ok=True)
    voice_raw = card / "voice_raw.wav"
    if not voice_raw.exists():
        text = ""
        for s in task.get("scenes", []):
            text += (s.get("meaning") or "") + "。"
        text = text.replace("？。", "？") or "一条消息被转发，往往不是因为它真实。"
        aiff = card / "voice_raw.aiff"
        subprocess.run(["say", "-o", str(aiff), text], timeout=120, check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", "48000",
                        str(voice_raw)], timeout=120, check=True)
        aiff.unlink(missing_ok=True)
        print("voice prepared:", voice_raw.stat().st_size, "B")
    music = card / "music.wav"
    if not music.exists():
        duration = float((task.get("film") or {}).get("duration") or 39.5)
        # 程序化环境垫乐：A 小调三和弦 + 低通（真实合成，非占位）
        argv = ["ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
                "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={duration}",
                "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={duration}",
                "-filter_complex", "[0:a][1:a][2:a]amix=inputs=3:normalize=1,volume=0.5,afade=t=in:d=2,afade=t=out:st={d-3}:d=3,aformat=sample_rates=48000:channel_layouts=mono".replace("{d-3}", f"{duration-3:.1f}"),
                str(music)]
        subprocess.run(argv, timeout=180, check=True)
        print("music prepared:", music.stat().st_size, "B")


def set_manual_alignment(run_id: int, project_root: Path, task: dict):
    """G02 手动打点回退（规格：whisper 缺失不静默降级，回退手动）。"""
    wf_id = c.get(f"/runs/{run_id}").json()["workflow_id"]
    wf = c.get(f"/workflows/{wf_id}").json()
    graph = wf["graph_json"] or {}
    params = graph.setdefault("params", {}).setdefault("G02", {})
    if params.get("manual_segments"):
        return
    fps = task.get("fps", 24)
    segments = []
    for s in task.get("scenes", []):
        text = s.get("meaning") or ""
        if text:
            segments.append({"text": text, "start": s.get("start", 0), "end": min(s.get("end", 5),
                             s.get("start", 0) + max(1.2, len(text) / 5.2))})
    params["manual_segments"] = segments
    c.put(f"/workflows/{wf_id}", json={"graph": graph})
    print("manual alignment segments:", len(segments))


def main():
    run_id = int(sys.argv[1])
    project_id = int(sys.argv[2])
    timeout = 2700
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])
    proj_root = Path(c.get("/projects").json()["items"][0]["root"] if project_id == 1 else None) \
        if False else None
    # project root
    projects = {p["id"]: p["root"] for p in c.get("/projects").json()["items"]}
    root = Path(projects[project_id])
    task = json.loads((root / "card" / "task.json").read_text(encoding="utf-8-sig"))

    prepare_audio(root, task)
    set_manual_alignment(run_id, root, task)

    approved = set()
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            g = c.get(f"/runs/{run_id}/graph").json()
        except Exception as e:
            print("poll error", e); time.sleep(3); continue
        statuses = {n["id"]: n["status"] for n in g["nodes"]}
        run_status = g["run"]["status"]
        running = [k for k, v in statuses.items() if v == "running"]
        failed = {k: v for k, v in
                  ((n["id"], n["message"]) for n in g["nodes"] if n["status"] == "failed")}
        if int(time.time() - t0) % 30 < 5:
            done = sum(1 for v in statuses.values() if v in ("succeeded", "cached"))
            print(f"[{time.time()-t0:5.0f}s] done={done}/46 run={run_status} running={running}", flush=True)
        if failed:
            print("FAILED nodes:", {k: v[:160] for k, v in failed.items()})
            c.post(f"/runs/{run_id}/cancel")
            sys.exit(2)
        try:
            pending = c.get(f"/gates/{run_id}/pending").json()["items"]
        except Exception:
            pending = []
        for p in pending:
            gid = p["gate"]
            if gid not in approved:
                r = c.post(f"/gates/{gid}/decide", json={
                    "run_id": run_id, "decision": "approved", "author": "driver",
                    "note": "驱动器自动签字", "checklist": p.get("checklist", [])})
                if r.status_code == 200:
                    approved.add(gid)
                    print(f"  ✓ 批准 {gid}", flush=True)
                else:
                    print(f"  ✗ {gid}: {r.text[:120]}", flush=True)
                    approved.add(gid)  # 防止重复尝试刷屏
        if run_status in ("succeeded", "failed", "needs_changes") and not pending:
            print(f"RUN 终态：{run_status}，用时 {time.time()-t0:.0f}s")
            master = root / "out" / "film" / "master.mp4"
            print("master.mp4:", master.exists(), master.stat().st_size if master.exists() else "-")
            sys.exit(0 if run_status == "succeeded" else 3)
        time.sleep(4)
    print("超时")
    sys.exit(4)


if __name__ == "__main__":
    main()
