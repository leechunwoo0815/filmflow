"""自建验收状态（P1-19 / 判官 §六 #9 的后半）。

背景：`require_scratch_project()` 只保证脚本**不再打在演示项目上**，但
`e2e_takes.py` / `verify_r3_takes.py` 这类脚本依赖"项目里已经有两次完成的 Run"、
`e2e_audio_v2.py` 依赖"已经有两条口播 Take"。没有 builder 时，换一个 scratch 项目就
会因为"没有 Take"而失败，于是人又回去指 188/211。本模块把这些**前置状态本身**
做成脚本自建的产物：建项目 → 驱动到 F04 出片 → 改文案 → 第二次 Run → 用完自删。

用法：
    from _scratch_state import build_take_state, build_audio_state
    st = build_take_state(c, "takes-e2e")          # dict(pid, run_a, run_b, text_a/text_b)
    ...                                            # 跑 UI 冒烟
    destroy_project(c, st["pid"], st["root"])      # 一律自删

命令行自检（只建不删，打印状态供其它脚本 --project 指过去）：
    uv run --project server python scripts/_scratch_state.py --takes [--keep]
"""
from __future__ import annotations

import base64
import contextlib
import io
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _acceptance import ACCEPT_ROOT, destroy

BASE = "http://127.0.0.1:7860/api"

# 三句 4 字短文案 → 时间轴 3 场（Take/采纳验收需要 S03 存在）。
# 文案长度按 READ_CPS=5.2 反推：4s/3 场 ≈ 每场 1.33s，文案 ≤6 字才不会撞 E_SCENE_READ_OVERFLOW。
# 分辨率必须 1080p/24fps——`POST /runs/start` 会挡非交付档位（实测 400："final 需 1080p"）。
COPY_3 = "风起了。纸动了。字落了。"
TEXT_A = "字落定。"
TEXT_B = "字落稳了。"


def req(c, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:400]}")
    return r.json() if r.content else {}


def wait_api(base: str = BASE, timeout: float = 60.0) -> None:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=3, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError as e:          # 服务没起来是预期分支，但别的错误不该被吞掉
            print(f"  waiting for API: {type(e).__name__}", flush=True)
        time.sleep(1)
    raise SystemExit("API 未就绪（:7860）")


def pick_style(c, family: str = "print", want: str | None = None) -> str:
    """风格库是本地资产：优先用指定 id，不可用则回退到该 family 里第一个可生产风格。"""
    if want:
        try:
            s = req(c, "GET", f"/styles/{want}")
            if s.get("available") and s.get("tokens_status") == "complete":
                return want
        except RuntimeError:
            pass
    items = req(c, "GET", f"/styles?chips=可生产&family={family}&limit=5")["items"]
    if not items:
        raise SystemExit(f"风格库里没有可生产的 {family} 风格——builder 需要本地风格库")
    return items[0]["id"]


def create_project(c, name: str, *, copy_text: str = COPY_3, duration: float = 4.0,
                   fps: float = 24.0, width: int = 1920, height: int = 1080,
                   style_family: str = "print", primary: str | None = "H2") -> dict[str, Any]:
    """走 5 步向导 materialize（**不是**裸 POST /projects）：只有这条路会写 profile/style pick。"""
    style = pick_style(c, style_family, primary)
    d = req(c, "POST", "/drafts", {"name": name, "step": 1})
    root = ACCEPT_ROOT / f"{name}-{d['id']}"
    (root / "card").mkdir(parents=True, exist_ok=True)
    req(c, "PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": copy_text,
        "profile": {"width": width, "height": height, "fps": fps, "duration": duration},
        "pick": {"primary": style, "alternates": [], "reason": "scratch-state"},
        "brief": {"title": name}}})
    m = req(c, "POST", f"/drafts/{d['id']}/materialize", {})
    run_id = int(m["run_id"])
    return {"pid": int(m["project"]["id"]), "root": root, "style": style, "run_id": run_id,
            "workflow_id": int(req(c, "GET", f"/runs/{run_id}")["workflow_id"])}


def timeline(c, pid: int) -> tuple[dict, int]:
    doc = req(c, "GET", f"/projects/{pid}/docs/timeline")
    return doc["content"], doc["version"]


def set_scene_text(c, pid: int, scene_id: str, text: str) -> int:
    content, version = timeline(c, pid)
    hit = False
    for s in content["scenes"]:
        if s["id"] == scene_id:
            s["text"] = text
            hit = True
    if not hit:
        raise SystemExit(f"项目 {pid} 的时间轴里没有 {scene_id}（builder 前置不成立）")
    req(c, "PUT", f"/projects/{pid}/docs/timeline",
        {"content": content, "base_version": version, "author": "scratch-state"})
    return version + 1


def _pending(c, run_id: int) -> set[str]:
    return {p["gate"] for p in req(c, "GET", f"/gates/{run_id}/pending")["items"]}


def drive_to(c, pid: int, run_id: int, node: str = "F04", timeout: float = 600.0,
             author: str = "scratch-state") -> float:
    """真实驱动到 node（默认 F04 编码出片）：逐个签可签的门，D03 前逐场标已读。

    D03 是逐场门禁，写死场景数会永远卡住（15s golden 就这么失败过），所以读的是当前时间轴。
    第二次 Run 靠内容哈希命中缓存——只改 S03 就只重渲 S03。
    """
    req(c, "POST", f"/runs/{run_id}/start", {})
    viewed = False
    signed: set[str] = set()
    t0 = time.time()
    while time.time() - t0 < timeout:
        graph = req(c, "GET", f"/runs/{run_id}/graph")
        st = {n["id"]: n["status"] for n in graph["nodes"]}
        if st.get(node) in ("succeeded", "cached"):
            return time.time() - t0
        # 只认**目标节点上游**的失败：驱动到 F04 时 G01「未上传口播」是预期内的，
        # 把它当致命错误会把已经出片的 Run 判死（实测踩过）。
        failed = [(n["id"], (n.get("message") or "")[:200]) for n in graph["nodes"]
                  if n["status"] == "failed" and _upstream_of(n["id"], node)]
        if failed:
            raise SystemExit(f"节点失败：{failed}")
        pend = _pending(c, run_id)
        if "B08" in pend:
            _gate(c, run_id, "B08", signed, author)
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                content, _v = timeline(c, pid)
                for s in content["scenes"]:
                    req(c, "POST", f"/projects/{pid}/stills/viewed",
                        {"scene": s["id"], "time": 0.5})
                viewed = True
            _gate(c, run_id, "D03", signed, author)
        if "D05" in pend and st.get("D04") in ("succeeded", "cached"):
            _gate(c, run_id, "D05", signed, author)
        if "E07" in pend and st.get("E05") in ("succeeded", "cached"):
            _gate(c, run_id, "E07", signed, author)
        time.sleep(1)
    raise SystemExit(f"等待 {node} 超时（{timeout:.0f}s）")


def _upstream_of(node: str, target: str) -> bool:
    """节点是否排在 target 之前（阶段字母序 + 同阶段按编号）。"""
    order = "ABCDEFG"
    a, b = order.index(node[0]), order.index(target[0])
    return (a, node) <= (b, target)


def _gate(c, run_id: int, gate: str, signed: set[str], author: str) -> None:
    if gate in signed:
        return
    req(c, "POST", f"/gates/{gate}/decide",
        {"run_id": run_id, "decision": "approved", "author": author})
    signed.add(gate)


def take_mp4(c, pid: int, run_id: int) -> dict[str, Any]:
    """该 Run 的成片 MP4——Take 对比比的就是这两个文件的哈希。"""
    vids = [v for v in req(c, "GET", f"/projects/{pid}/review/videos")["items"]
            if v["runId"] == run_id]
    if not vids:
        raise SystemExit(f"Run {run_id} 没有可对比的 MP4 产物（E05 未出片？）")
    return vids[0]


def build_take_state(c, name: str = "takes-scratch", *, timeout: float = 900.0,
                     keep_on_error: bool = False) -> dict[str, Any]:
    """两次跑到 F04、S03 文案不同的项目：`(pid, run_a, run_b)` + 各自 S03 文本与成片哈希。

    中途失败**必须**把半建好的项目删掉：builder 泄漏一次，判官就会在库里多看到一个孤儿。
    """
    proj = create_project(c, name)
    pid, root, run_a = proj["pid"], proj["root"], proj["run_id"]
    try:
        content, _v = timeline(c, pid)
        if len(content["scenes"]) < 3:
            raise SystemExit(f"builder 需要 ≥3 场，实际 {len(content['scenes'])}（文案句数不够）")
        s03 = content["scenes"][2]["id"]
        set_scene_text(c, pid, s03, TEXT_A)
        w_a = drive_to(c, pid, run_a, "F04", timeout)
        vid_a = take_mp4(c, pid, run_a)
        req(c, "POST", f"/runs/{run_a}/cancel", {})     # 停在 F06 前，别把 Run 留在在飞态

        set_scene_text(c, pid, s03, TEXT_B)
        run_b = req(c, "POST", "/runs", {"workflowId": proj["workflow_id"]})["id"]
        w_b = drive_to(c, pid, run_b, "F04", timeout)
        vid_b = take_mp4(c, pid, run_b)
        req(c, "POST", f"/runs/{run_b}/cancel", {})
        if vid_a["sha256"] == vid_b["sha256"]:
            raise SystemExit("两次 Run 的成片哈希相同——改文案没生效，Take 对比是假的")
    except BaseException:
        if not keep_on_error:
            destroy(c, pid, root)
        raise
    return {"pid": pid, "root": root, "run_a": run_a, "run_b": run_b, "scene": s03,
            "text_a": TEXT_A, "text_b": TEXT_B, "wall_a": round(w_a, 1), "wall_b": round(w_b, 1),
            "vid_a": vid_a, "vid_b": vid_b}


def wav_b64(freq: int, seconds: float = 2.0) -> str:
    """本地 ffmpeg 合成口播替身（不联网、不请在线模型）。"""
    p = Path(f"/tmp/scratch-state-{freq}-{seconds}.wav")
    if not p.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={freq}:duration={seconds}", "-ac", "1", "-ar", "48000", str(p)],
                       check=True, timeout=120)
    return base64.b64encode(p.read_bytes()).decode()


def build_audio_state(c, pid: int, *, kinds: tuple[str, ...] = ("voice", "voice", "music")) -> dict[str, Any]:
    """/audio 页冒烟的前置态：≥2 条口播 Take，其中一条已处理。"""
    content, _v = timeline(c, pid)
    scenes = content["scenes"]
    take_ids: list[int] = []
    for i, kind in enumerate(kinds):
        scene_id = scenes[i % len(scenes)]["id"] if kind == "voice" else None
        body = req(c, "POST", f"/projects/{pid}/audio/upload", {
            "filename": f"{kind}-{i}.wav", "data": wav_b64(220 + 110 * i),
            "kind": kind, "sceneId": scene_id, "name": f"{scene_id or 'music'} take {i}"})
        take_ids.append(body["take"]["id"])
        if scene_id:
            req(c, "POST", f"/projects/{pid}/audio/scene-primary",
                {"sceneId": scene_id, "takeId": body["take"]["id"]})
    req(c, "POST", f"/projects/{pid}/audio/takes/{take_ids[0]}/process",
        {"highpass": True, "denoise": True, "normalize": False})
    req(c, "POST", f"/projects/{pid}/audio/license",
        {"source": "本地 ffmpeg 合成", "license": "CC0", "authorized": True, "expires": "2099-12-31"})
    return {"takes": take_ids}


def build_asset_state(c, pid: int, *, count: int = 1) -> list[dict[str, Any]]:
    """资产库前置态：真 PNG（自制/CC0），可按需批量去重压测。"""
    from PIL import Image

    out = []
    for i in range(count):
        buf = io.BytesIO()
        Image.new("RGB", (24 * (i + 1), 14), (200 - 20 * i, 60 + 30 * i, 90)).save(buf, "PNG")
        out.append(_upload_asset(c, pid, f"scratch-{i}.png", f"scratch-{i}",
                                 base64.b64encode(buf.getvalue()).decode())["asset"])
    return out


def _upload_asset(c, pid: int, filename: str, name: str, data: str) -> dict[str, Any]:
    return req(c, "POST", "/assets", {
        "scope": "project", "projectId": pid, "filename": filename, "name": name,
        "data": data, "license": {"source": "自制", "type": "CC0"}})


def build_template_source(c, name: str = "templates-scratch") -> dict[str, Any]:
    """FR-37 模板验收的前置态：2 场项目，S01 上有一个图层 + 一个 SFX 音层。

    原先写死演示 211，因为"另存项目模板"要求源项目**同时**有 image/audio 资产引用
    （`assetShas` 为空就没得验）；这两样现在由脚本自己插。
    """
    proj = create_project(c, name, copy_text="风起了。纸动了。", duration=4.0)
    pid = proj["pid"]
    try:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (32, 18), (210, 70, 30)).save(buf, "PNG")
        img = _upload_asset(c, pid, "tpl-image.png", "tpl-image",
                            base64.b64encode(buf.getvalue()).decode())["asset"]
        sfx = _upload_asset(c, pid, "tpl-sfx.wav", "tpl-sfx", wav_b64(880, 0.4))["asset"]
        content, version = timeline(c, pid)
        s01 = content["scenes"][0]["id"]
        req(c, "POST", f"/projects/{pid}/timeline/ops", {
            "op": "add_image", "baseVersion": version, "sceneId": s01,
            "assetSha": img["sha256"], "box": [640, 300, 640, 360], "z": 20,
            "fit": "cover", "opacity": 0.9, "name": "模板源图层"})
        content, version = timeline(c, pid)
        req(c, "POST", f"/projects/{pid}/timeline/ops", {
            "op": "add_sfx", "baseVersion": version, "sceneId": s01,
            "assetSha": sfx["sha256"], "at": 0.2, "gainDb": -6, "name": "模板源音效"})
        content, _v = timeline(c, pid)
        if not content["scenes"][0].get("layers") or not content["scenes"][0].get("audio_layers"):
            raise SystemExit("模板源前置态没建成：S01 缺图层或音层")
    except BaseException:
        destroy(c, pid, proj["root"])
        raise
    return {**proj, "image_sha": img["sha256"], "sfx_sha": sfx["sha256"]}


def build_review_source(c, name: str = "review-scratch", *, duration: float = 4.0,
                        comments: int = 10, fps: float = 24.0,
                        timeout: float = 900.0) -> dict[str, Any]:
    """审片验收的前置态：一个真出过片（F04）的项目 + N 条批注。

    原先 verify_r3 / e2e_r3 直接借用已交付的演示 174/40s——那是唯一"已经有成片"的项目，
    代价是批注写进演示、review.json 被 unlink。自建一份 4s 成片只多花一分多钟，
    断言强度不变（批注跳转/去重/打包都走真实 MP4）。
    """
    proj = create_project(c, name, copy_text=COPY_3, duration=duration, fps=fps)
    pid, root, run_id = proj["pid"], proj["root"], proj["run_id"]
    try:
        drive_to(c, pid, run_id, "F04", timeout)
        req(c, "POST", f"/runs/{run_id}/cancel", {})
        vids = [v for v in req(c, "GET", f"/projects/{pid}/review/videos")["items"]
                if v["runId"] == run_id and v["node"] == "F04"]
        if not vids:
            raise SystemExit(f"审片源没有 F04 成片：{vids}")
        content, _v = timeline(c, pid)
        scene_ids = [s["id"] for s in content["scenes"]]
        for i in range(comments):
            req(c, "POST", f"/projects/{pid}/review/comments", {
                "frame": round(duration * fps * (i + 1) / (comments + 1)),
                "time": round(duration * (i + 1) / (comments + 1), 3),
                "sceneId": scene_ids[i % len(scene_ids)],
                "kind": "rect" if i % 2 == 0 else "text",
                "category": ["must", "suggest", "question"][i % 3],
                "body": f"{name} 批注 {i + 1}",
                "geometry": ({"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1} if i % 2 == 0 else {})})
        got = req(c, "GET", f"/projects/{pid}/review")
        if len(got["comments"]) != comments:
            raise SystemExit(f"批注写入不完整：{len(got['comments'])}/{comments}")
    except BaseException:
        destroy(c, pid, root)
        raise
    return {**proj, "video": vids[0], "duration": duration, "fps": fps,
            "scenes": scene_ids, "comments": len(got["comments"])}


def own_runs(c, pid: int) -> set[int]:
    return {int(r["id"]) for r in req(c, "GET", f"/projects/{pid}/runs")["items"]}


def destroy_project(c, pid: int, root: Path) -> None:
    destroy(c, pid, root)


@contextlib.contextmanager
def scratch_project(c, name: str, *, keep: bool = False, **profile):
    """自建项目 + 退出必删（除非显式 keep）：验收脚本不再留下半截项目。"""
    proj = create_project(c, name, **profile)
    try:
        yield proj
    finally:
        if not keep:
            destroy(c, proj["pid"], proj["root"])


if __name__ == "__main__":
    import argparse
    import json as _json

    import httpx

    ap = argparse.ArgumentParser(description="自建验收前置态（判官 §六 #9）")
    ap.add_argument("--takes", action="store_true", help="建两次到 F04 的 Run（Take 对比前置态）")
    ap.add_argument("--audio", action="store_true", help="建两条口播 Take + 已处理 + 许可")
    ap.add_argument("--assets", action="store_true", help="建项目级图片资产")
    ap.add_argument("--name", default="scratch-state")
    ap.add_argument("--keep", action="store_true", help="保留项目（默认建完即自检后删除）")
    args = ap.parse_args()
    wait_api()
    with httpx.Client(base_url=BASE, timeout=900, trust_env=False) as client:
        if args.takes:
            st = build_take_state(client, args.name, keep_on_error=args.keep)
            print(_json.dumps({k: v for k, v in st.items() if k != "root"}, ensure_ascii=False, indent=1))
            print(f"{st['scene']} A={st['vid_a']['sha256'][:12]} B={st['vid_b']['sha256'][:12]} "
                  f"wall A={st['wall_a']}s wall B={st['wall_b']}s")
            if args.keep:
                print(f"保留：project={st['pid']} runs={st['run_a']},{st['run_b']} root={st['root']}")
            else:
                destroy_project(client, st["pid"], st["root"])
                print("已自删（builder 自检通过）")
        elif args.audio:
            with scratch_project(client, args.name + "-audio", keep=args.keep) as proj:
                print(_json.dumps(build_audio_state(client, proj["pid"]), ensure_ascii=False))
                print(f"audio state ready: project={proj['pid']}")
        elif args.assets:
            with scratch_project(client, args.name + "-assets", keep=args.keep) as proj:
                print(_json.dumps(build_asset_state(client, proj["pid"], count=3), ensure_ascii=False))
                print(f"asset state ready: project={proj['pid']}")
        else:
            ap.print_help()
