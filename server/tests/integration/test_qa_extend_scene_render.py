"""P0-5 渲染级验收：扩场景之后开新 Run，成片时长必须真的变长、尾部场景必须还在。

专家验收原句（`docs/reviews/2026-11-03-expert-review-analysis.md` §3 P0-5）：
「text_overflow 项目扩 0.5s 后，新 Run 的 master 时长增加，尾部场景存在」。
在这条测试之前，仓库里只有文档级断言（timeline/profile 同步、撤销链），
渲染级证据是空的——而原缺陷恰恰是「扩中间场景把后续场景推移、尾部 range 清空、
内容整场消失，而帧数/时长 QC 仍绿」。所以这里断言的是 ffprobe 出来的真实成片。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageStat

# 历史阻塞（2026-11-05 已解）：隔离环境曾与 dev 服务共用 :8787 帧服务 → 引擎取不到
# program/贴图 → 静帧全黑 → D04 判"过暗 lum_mean=17.9 < 40"。修法：`config.frame_port`
# 支持 `FILMFLOW_FRAME_PORT` 覆盖（默认仍 8787，规格端口不偏离），集成 conftest 为隔离
# 服务分配空闲端口，锁名 `port-8787` 在 acquire 处归一化成 `port-<实际端口>`；
# 执行器行为变化 → `EXECUTOR_VERSION` 升 2.14.0。真环境在此之前的对照证据：
# run 335 → 336，4.0s/96 帧 → 4.5s/108 帧，尾部 S03 [3.166,4.5] 完好、静帧 lum≈233。
pytestmark = [
    pytest.mark.slow,
    pytest.mark.requires_style_library,
    pytest.mark.requires_chrome,
    pytest.mark.requires_ffmpeg,
]

COPY_3 = "风起了。纸动了。字落了。"
FPS = 24
# 4.0s 是验收脚本（_scratch_state.build_take_state/build_review_source）实测能过 D04 的口径：
# 2.0s/3 场时每场只有 0.67s，静帧采在入场动画里 → D04 判"过暗 lum_mean=17.9 < 40"。
DURATION = 4.0
DELTA = 0.5
GATES = ("B08", "D03", "D05", "E07")


def _req(client: httpx.Client, method: str, path: str, payload: dict | None = None):
    r = client.request(method, path, json=payload)
    assert r.status_code < 400, f"{method} {path} -> {r.status_code} {r.text[:1000]}"
    return r.json()


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _ffprobe(path: Path) -> dict:
    r = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
        "-of", "json", str(path),
    ])
    assert r.returncode == 0, r.stderr[-1000:]
    stream = json.loads(r.stdout)["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return {"fps": round(int(num) / int(den), 3), "frames": int(stream.get("nb_frames") or 0),
            "duration": float(json.loads(r.stdout)["format"]["duration"])}


def _frame_at(mp4: Path, t: float, out: Path) -> Path:
    r = _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4),
              "-frames:v", "1", str(out)])
    assert r.returncode == 0, r.stderr[-1000:]
    assert out.stat().st_size > 1000, f"{out} 不是有效 PNG"
    return out


def _gray_stddev(png: Path) -> float:
    return float(ImageStat.Stat(Image.open(png).convert("L")).stddev[0])


def _drive_to_f04(client: httpx.Client, pid: int, run_id: int, timeout: float = 900.0) -> dict:
    """真实驱动到 F04（编码出片）：逐个签可签的门，D03 前逐场标已读。"""
    _req(client, "POST", f"/runs/{run_id}/start", {})
    viewed, signed = False, set()
    t0 = time.time()
    while time.time() - t0 < timeout:
        graph = _req(client, "GET", f"/runs/{run_id}/graph")
        st = {n["id"]: n["status"] for n in graph["nodes"]}
        if st.get("F04") in ("succeeded", "cached"):
            return {"wall": round(time.time() - t0, 1), "states": st}
        failed = [(n["id"], (n.get("message") or "")[:200]) for n in graph["nodes"]
                  if n["status"] == "failed" and n["id"] <= "F04"]
        assert not failed, f"run {run_id} 节点失败：{failed}"
        pend = {p["gate"] for p in _req(client, "GET", f"/gates/{run_id}/pending")["items"]}
        if "B08" in pend:
            _sign(client, run_id, "B08", signed)
        if "D03" in pend and st.get("D02") in ("succeeded", "cached"):
            if not viewed:
                for s in _req(client, "GET", f"/projects/{pid}/docs/timeline")["content"]["scenes"]:
                    _req(client, "POST", f"/projects/{pid}/stills/viewed",
                         {"scene": s["id"], "time": 0.5})
                viewed = True
            _sign(client, run_id, "D03", signed)
        for gate, upstream in (("D05", "D04"), ("E07", "E05")):
            if gate in pend and st.get(upstream) in ("succeeded", "cached"):
                _sign(client, run_id, gate, signed)
        time.sleep(1)
    raise AssertionError(f"run {run_id} 在 {timeout:.0f}s 内没到 F04")


def _sign(client: httpx.Client, run_id: int, gate: str, signed: set[str]) -> None:
    if gate in signed or gate not in GATES:
        return
    _req(client, "POST", f"/gates/{gate}/decide",
         {"run_id": run_id, "decision": "approved", "author": "p0-5-e2e"})
    signed.add(gate)


def _master(client: httpx.Client, pid: int, run_id: int, dest: Path) -> dict:
    """下载该 Run 的 F04 成片并 ffprobe：断言的是真实文件，不是库里的元数据。"""
    vids = [v for v in _req(client, "GET", f"/projects/{pid}/review/videos")["items"]
            if v["runId"] == run_id and v["node"] == "F04"]
    assert vids, f"run {run_id} 没有 F04 成片产物"
    r = client.get(f"/artifacts/{vids[0]['id']}/file")
    assert r.status_code == 200, r.text[:400]
    dest.write_bytes(r.content)
    return _ffprobe(dest)


def _scene_ranges(timeline: dict) -> list[tuple[str, float, float]]:
    """场景的实际时段（start/end 是 timeline 文档的规范字段）。

    2026-11-05 实测：文档里的场景字典形状随最后写入路径变化——派生/ops 路径只有
    start/end，qa 修复路径会带 duration 键；只读 duration 会把规范文档误判成
    "range 清空"（第三轮 E2E 假失败的原因）。
    """
    out, t = [], 0.0
    for s in timeline["scenes"]:
        dur = float(s["end"]) - float(s["start"]) if s.get("end") is not None \
            else float(s.get("duration") or 0)
        out.append((str(s["id"]), t, t + dur))
        t += dur
    return out


def _cleanup(client: httpx.Client, pid: int) -> None:
    """删掉临时项目：先取消 Run（停在门上的 Run 会把作业 parked 成 retry_wait，
    心跳 120s 内删除闸门判它"在飞"→ 409），**等作业真的离开 active 态**，再轮询 DELETE。
    （2026-11-05 实测：cancel 响应被忽略 + 不等收敛时，首个 DELETE 仍会 409——虽然
    手工探针证明 cancel 对 blocked Run 一定收掉 retry_wait 作业。）"""
    for r in client.get(f"/projects/{pid}/runs").json().get("items", []):
        # 无条件 cancel：**终态为 failed/needs_changes 的 Run 仍可能持有活跃作业**
        # （停在人工门时作业合法 park 成 retry_wait；实测 run2 failed 但 job 仍在
        # running↔retry_wait 循环，跳过它删除就被"在飞作业"拦死）。终态 Run 没有
        # 活跃作业时 cancel 是 no-op，无副作用。
        resp = client.post(f"/runs/{r['id']}/cancel", json={})
        print(f"  cancel run {r['id']} (status={r.get('status')}) -> {resp.status_code}",
              flush=True)
    time.sleep(1.0)
    # 诊断：cancel 后作业必须离开 active 态；还停在 retry_wait 说明 cancel 只置了
    # 标志位（引擎任务还活着在等什么）——把这组状态打出来再轮询。
    jobs = client.get("/jobs?kind=run").json().get("items", [])
    mine = [(j["id"], j.get("run_id"), j["status"]) for j in jobs]
    runs = [(r["id"], r.get("status")) for r in
            client.get(f"/projects/{pid}/runs").json().get("items", [])]
    print(f"  cleanup 诊断 runs={runs} jobs={mine}", flush=True)
    # 等 parked 作业收敛成 canceled（正常应立刻完成；轮询只是防未观察过的竞态）
    deadline = time.time() + 30
    while time.time() < deadline:
        plan = client.delete(f"/projects/{pid}", params={"confirm": "false"})
        if plan.status_code < 400:
            break
        blockers = []
        try:
            blockers = plan.json().get("blockers") or []
        except ValueError:          # 非 JSON 响应体（如 5xx 文本）＝没有结构化 blockers
            pass
        inflight = [b for b in blockers if "在飞" in b]
        if not inflight:
            break
        time.sleep(1.0)
    deadline, last = time.time() + 90, None
    while time.time() < deadline:
        last = client.delete(f"/projects/{pid}", params={"confirm": "true"})
        if last.status_code < 400:
            return
        time.sleep(2)
    raise AssertionError(f"临时项目 {pid} 没删掉：{last.status_code} {last.text[:400]}")


def test_extend_scene_shows_up_in_the_new_master(api_client: httpx.Client, project_root: Path,
                                                 style_id: str):
    primary = style_id
    d = _req(api_client, "POST", "/drafts", {"name": "p0-5-extend", "step": 1})
    root = project_root / "p0-5-extend"
    (root / "card").mkdir(parents=True, exist_ok=True)
    _req(api_client, "PATCH", f"/drafts/{d['id']}", {"step": 5, "payload": {
        "root": str(root), "copy": COPY_3,
        "profile": {"width": 1920, "height": 1080, "fps": FPS, "duration": DURATION},
        "pick": {"primary": primary, "alternates": [], "reason": "p0-5-e2e"},
        "brief": {"title": "P0-5 扩场景"}}})
    created = _req(api_client, "POST", f"/drafts/{d['id']}/materialize", {})
    pid, run1 = int(created["project"]["id"]), int(created["run_id"])
    wf_id = int(_req(api_client, "GET", f"/runs/{run1}")["workflow_id"])
    try:
        tl = _req(api_client, "GET", f"/projects/{pid}/docs/timeline")["content"]
        assert len(tl["scenes"]) == 3, tl["scenes"]
        s01, s03 = str(tl["scenes"][0]["id"]), str(tl["scenes"][2]["id"])

        # 把 S01 文案加长到刚刚溢出（超出量 < 0.5s，保证扩 0.5s 真能修好）
        issue = None
        for n in range(1, 40):
            _req(api_client, "POST", f"/projects/{pid}/timeline/ops",
                 {"op": "set_text", "sceneId": s01, "text": "字落定" + "很" * n + "了。",
                  "force": True})
            issue = next((i for i in _req(api_client, "GET", f"/projects/{pid}/qa")["issues"]
                          if i["category"] == "text_overflow" and i["location"]["sceneId"] == s01),
                         None)
            if issue:
                break
        assert issue, "造不出 S01 读时溢出，前置态不成立"

        # 修复前的基线成片：48 帧 / 2.0s
        drive1 = _drive_to_f04(api_client, pid, run1)
        m1 = _master(api_client, pid, run1, root / "master-run1.mp4")
        assert m1["frames"] == round(DURATION * FPS), m1
        assert abs(m1["duration"] - DURATION) <= 1 / FPS, m1
        ranges_before = {sid: (a, b) for sid, a, b in
                         _scene_ranges(_req(api_client, "GET",
                                            f"/projects/{pid}/docs/timeline")["content"])}
        tail_mid_before = sum(ranges_before[s03]) / 2

        fix = _req(api_client, "POST", f"/projects/{pid}/qa/fix", {
            "issueId": issue["id"], "action": "extend_scene",
            "payload": {"sceneId": s01, "delta": DELTA}})["fix"]
        assert fix["requiresRerun"] is True and fix["nextAction"] == "run_new", fix
        assert fix["verified"] is None, "文档级修复不许自称渲染级已验证"

        # 旧 Run 的重试必须被拦住：它的快照还是 2.0s，重跑只会重渲旧内容（P0-5 根因之一）
        stale = api_client.post(f"/runs/{run1}/retry")
        assert stale.status_code == 409, stale.text[:400]
        body = stale.json()["detail"] if "detail" in stale.json() else stale.json()
        assert body["code"] == "E_RUN_SNAPSHOT_STALE", body
        assert "timeline" in json.dumps(body["details"]["drift"], ensure_ascii=False), body

        # 新 Run：修复必须出现在真实成片里
        run2 = int(_req(api_client, "POST", "/runs", {"workflowId": wf_id})["id"])
        drive2 = _drive_to_f04(api_client, pid, run2)
        m2 = _master(api_client, pid, run2, root / "master-run2.mp4")
        expected_frames = round((DURATION + DELTA) * FPS)
        assert m2["frames"] == expected_frames, (m2, expected_frames)
        assert abs(m2["duration"] - (DURATION + DELTA)) <= 1 / FPS, m2
        assert m2["frames"] - m1["frames"] == round(DELTA * FPS), (m1, m2)

        tl2 = _req(api_client, "GET", f"/projects/{pid}/docs/timeline")["content"]
        prof2 = _req(api_client, "GET", f"/projects/{pid}/docs/profile")["content"]
        assert abs(prof2["duration"] - float(tl2["duration"])) < 1e-6, (prof2, tl2)
        ranges_after = _scene_ranges(tl2)
        tail = next(r for r in ranges_after if r[0] == s03)
        assert tail[2] - tail[1] > 0, f"尾部场景 range 被清空：{ranges_after}"
        assert abs(tail[2] - (DURATION + DELTA)) <= 1e-6, f"尾部场景没顶到片尾：{ranges_after}"
        assert abs(tail[1] - ranges_before[s03][0]) >= DELTA - 1e-6, \
            f"S01 扩了 {DELTA}s，尾部场景却没被推移：{ranges_before} → {ranges_after}"

        # 尾部场景真的渲出内容了（原缺陷：range 清空 → 整场消失，而 QC 仍绿）
        tail_png = _frame_at(root / "master-run2.mp4", tail[1] + (tail[2] - tail[1]) / 2,
                             root / "tail-run2.png")
        before_png = _frame_at(root / "master-run1.mp4", tail_mid_before, root / "tail-run1.png")
        sd_tail, sd_before = _gray_stddev(tail_png), _gray_stddev(before_png)
        assert sd_tail > 2.0, f"尾部场景是平的/空的（灰度标准差 {sd_tail:.2f}）"
        assert sd_tail >= sd_before * 0.5, f"尾部场景内容塌了：{sd_before:.2f} → {sd_tail:.2f}"

        qa2 = _req(api_client, "GET", f"/projects/{pid}/qa")["issues"]
        ghosts = [i for i in qa2 if i["category"] in ("black_frame", "missing_frame")]
        assert not ghosts, ghosts
        assert not [i for i in qa2 if i["category"] == "text_overflow"
                    and i["location"]["sceneId"] == s01], "扩了 0.5s 溢出还在"
        print(f"  run1 {m1['frames']}帧/{m1['duration']:.2f}s（wall {drive1['wall']}s）→ "
              f"run2 {m2['frames']}帧/{m2['duration']:.2f}s（wall {drive2['wall']}s）；"
              f"尾部 {s03} [{tail[1]:.2f},{tail[2]:.2f}] 灰度σ {sd_before:.1f}→{sd_tail:.1f}")
    finally:
        _cleanup(api_client, pid)
