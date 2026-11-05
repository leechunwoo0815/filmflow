"""R2.5 FR-31 验收：模板音频占位、只读示例克隆、3 标题候选、15s draft ≤10min。"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.config import settings

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=240, trust_env=False)
COPY = "很多工作不是难，是重复。把重复交给工具，人才有时间思考。"


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return {"width": v["width"], "height": v["height"],
            "fps": round(int(num) / int(den), 3),
            "duration": round(float(d["format"]["duration"]), 3)}


def b64(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")

    templates = req("GET", "/templates").json()["items"]
    builtin = {"voice15", "opinion30", "product40"}
    assert builtin <= {t["id"] for t in templates}
    assert all(t.get("audioPlaceholder") == "voice"
               for t in templates if t["id"] in builtin)
    print("templates", [(t["id"], t["seconds"]) for t in templates[:6]], flush=True)

    titles = req("GET", "/wizard/titles?" + str(httpx.QueryParams({"copy": COPY}))).json()["items"]
    assert len(titles) == 3 and len(set(titles)) == 3
    assert titles[0] in COPY and all("风从纸上起" not in t for t in titles)
    print("titles", titles, flush=True)

    examples = req("GET", "/examples").json()["items"]
    assert {x["id"] for x in examples} == {"voice15", "product40"}
    assert all(x["readonly"] and "copy" not in x for x in examples)
    print("examples", [(x["id"], x["seconds"], x["readonly"]) for x in examples], flush=True)

    # 模板 → 15s 项目；路径全部落在登记工作区
    t0 = time.time()
    stamp = int(t0)
    made = req("POST", "/projects/from-template",
               {"templateId": "voice15", "name": f"fr31-verify-{stamp}"}).json()
    pid, rid = made["project"]["id"], made["run_id"]
    root = Path(made["project"]["root"])
    assert root.is_dir() and any(root.is_relative_to(Path(x).resolve()) for x in settings.workspace_roots)
    profile = json.loads((root / "project.profile.json").read_text(encoding="utf-8"))
    assert profile["duration"] == 15.0 and profile["frames"] == 360
    placeholder = json.loads((root / "card" / "audio.placeholder.json").read_text(encoding="utf-8"))
    assert placeholder["kind"] == "voice" and placeholder["duration"] == 15.0
    audio = req("GET", f"/projects/{pid}/audio").json()
    assert audio["placeholder"]["source"] == "voice15" and audio["takes"] == []
    print("template project", pid, "run", rid, "root", root, "placeholder", placeholder["duration"], flush=True)

    # 所有 card/doc 文本都在项目根内，无外部示例依赖
    text_suffixes = {".json", ".txt", ".md", ".srt"}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in text_suffixes and "out" not in p.parts:
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert str(ROOT / "fixtures") not in text, p
            assert "file://" not in text, p

    # 15s draft 预览：从模板到可播放 draft 的走查
    job = req("POST", f"/projects/{pid}/preview/film", {"profile": "draft"}).json()
    jid = job["jobId"]
    draft_t0 = time.time()
    while time.time() - draft_t0 < 600:
        job = req("GET", f"/preview/jobs/{jid}").json()
        if job["status"] in ("succeeded", "failed", "canceled"):
            break
        time.sleep(1)
    assert job["status"] == "succeeded", job
    draft_seconds = time.time() - draft_t0
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "draft.mp4"
        out.write_bytes(req("GET", f"/preview/jobs/{jid}/file").content)
        info = probe(out)
    assert (info["width"], info["height"], info["fps"]) == (960, 540, 12.0)
    assert abs(info["duration"] - 15.0) <= 0.1
    assert draft_seconds < 600
    print("15s draft", info, "wall %.1fs" % draft_seconds, flush=True)

    # 占用/替换：上传真实口播后占位应消失
    voice = Path(tempfile.gettempdir()) / "fr31-voice.wav"
    if not voice.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=220:duration=1", "-ac", "1", "-ar", "48000", str(voice)], check=True)
    req("POST", f"/projects/{pid}/audio/upload",
        {"filename": "voice.wav", "data": b64(voice), "kind": "voice", "name": "voice"})
    audio = req("GET", f"/projects/{pid}/audio").json()
    assert audio["takes"] and audio["placeholder"] is None
    print("placeholder cleared after upload; takes", len(audio["takes"]), flush=True)

    # 只读示例 → 克隆为独立项目
    cloned = req("POST", "/examples/product40/clone", {"name": f"fr31-example-{stamp}"}).json()
    croot = Path(cloned["project"]["root"])
    assert croot != root and croot.is_dir()
    assert croot.is_relative_to(Path(settings.workspace_roots[0]).resolve())
    cloned_profile = json.loads((croot / "project.profile.json").read_text(encoding="utf-8"))
    assert cloned_profile["duration"] == 40.0 and cloned_profile["frames"] == 960
    assert (croot / "card" / "audio.placeholder.json").exists()
    print("example clone", cloned["project"]["id"], "run", cloned["run_id"], croot, flush=True)

    print("PASS: R2.5 FR-31 新手引导验收通过（15s draft %.1fs）" % draft_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
