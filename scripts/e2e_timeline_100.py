"""P1-11 / 判官 §六 #6：时间轴 100 场景的**有效**性能实测。

旧脚本被判官判为无效，四条都对得上，本版逐条改掉：
1. 按键：`j` 是**反向**播放（`setPlaying(-1)`），播放头 0.2s 内归零停 rAF —— 改用 `l`（正向），
   并**断言播放头时间码真的前进了**，否则整段采样是在量空闲页。
2. 路径：100 场景的批量播种只能整份写文档（`PUT /docs/timeline`），但**交互与自动保存走真路径**：
   测量窗口内跑 `timeline/ops`（set_text）并量「键盘改文案 → 服务端 version +1」的端到端 autosave
   延迟（页面是 700ms 防抖 + 一次 op + 一次文档落盘，见 web/src/app/timeline/page.tsx）。
3. 恒真断言：删掉旧的 `or longTaskCount >= 0`，只断言结构真实 + 播放真发生 + autosave 真落库。
4. 硬编码等待：点击/选择延迟改为页内 `performance.now()` 差值，不再 `wait_for_timeout(200)` 括进来。

结论口径：不预设"60fps 通过线"，但按阈值给出**要不要虚拟化**的数据判定，落
`docs/reports/p1-11-timeline-100.json`。项目自建自删（走 `DELETE /projects/{id}`）。
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:7860/api"
WEB = "http://127.0.0.1:3000"
ACCEPT = Path.home() / "cc-projects/ai-v/filmflow-projects/.acceptance"
SCENES = 100
SCENE_SECONDS = 4.0          # 100 × 4s ≈ 400s（6.7 分钟片）；再短就会被读时窗口门禁拒，
                            # 用 force 绕过量的就不是用户走的真路径了
SAMPLE_MS = 5000


def wait_api(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health", timeout=3).status_code == 200:
                return
        except (httpx.HTTPError, OSError):     # 服务还没起来，继续等
            pass
        time.sleep(1)
    raise RuntimeError("API 未就绪：先 ./dev.sh")


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return round(s[min(len(s) - 1, max(0, round(q * (len(s) - 1))) )], 1)


def build_project(c: httpx.Client) -> int:
    """批量播种 100 场景（整份写文档）；后续交互全走 ops/autosave 真路径。"""
    root = ACCEPT / f"tl100-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True, exist_ok=True)
    (root / "card" / "copy.txt").write_text("这是性能压测项目。" * 3, encoding="utf-8")
    body = c.post("/projects", json={"name": f"tl100-{uuid.uuid4().hex[:6]}", "root": str(root)}).json()
    pid = body["project"]["id"]
    tl = c.get(f"/projects/{pid}/docs/timeline").json()
    content = tl["content"]
    base_scene = dict(content["scenes"][0]) if content.get("scenes") else {}
    scenes, t = [], 0.0
    for i in range(SCENES):
        s = dict(base_scene)
        s.update({"id": f"S{i + 1:03d}", "start": round(t, 3), "end": round(t + SCENE_SECONDS, 3),
                  "text": f"场景 {i + 1}：性能压测文案。"})
        scenes.append(s)
        t += SCENE_SECONDS
    content["scenes"] = scenes
    content["duration"] = round(t, 3)
    r = c.put(f"/projects/{pid}/docs/timeline",
              json={"content": content, "base_version": tl["version"], "author": "perf-seed"})
    assert r.status_code == 200, r.text
    return pid


def main() -> int:
    from app.config import detect_chrome
    wait_api()
    c = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    pid = build_project(c)
    print(f"project {pid} built ({SCENES} scenes)", flush=True)
    summary: dict = {"projectId": pid, "scenes": SCENES,
                     "method": {"playKey": "l (forward)", "seeding": "PUT /docs/timeline (bulk)",
                                "interaction": "POST /timeline/ops + UI autosave"}}
    ops_lat: list[float] = []
    try:
        # --- 真 ops 路径的服务端往返（页面每停 700ms 就会打一次这个） ---
        for i in range(30):
            t0 = time.perf_counter()
            r = c.post(f"/projects/{pid}/timeline/ops", json={
                "op": "set_text", "sceneId": f"S{i + 1:03d}",
                "text": f"场景 {i + 1}：压测文案 {i}。"})
            assert r.status_code == 200, r.text
            ops_lat.append((time.perf_counter() - t0) * 1000)
        summary["ops"] = {"count": len(ops_lat), "p50ms": pct(ops_lat, 0.5),
                          "p95ms": pct(ops_lat, 0.95), "maxMs": round(max(ops_lat), 1)}

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=detect_chrome(), headless=True,
                                        args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            t0 = time.time()
            page.goto(f"{WEB}/timeline?project={pid}", wait_until="domcontentloaded")
            page.wait_for_selector("[data-testid='scene-block-S001']", timeout=30000)
            summary["loadMs"] = round((time.time() - t0) * 1000)
            summary["renderedSceneNodes"] = page.evaluate(
                "document.querySelectorAll('[data-testid^=\"scene-block-\"]').length")

            page.evaluate("""
              window.__ffLong = []; window.__ffFrames = 0;
              new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__ffLong.push(e.duration); })
                .observe({entryTypes: ['longtask']});
              const tick = () => { window.__ffFrames++; requestAnimationFrame(tick); };
              requestAnimationFrame(tick);
            """)

            def tc() -> str:
                return page.get_by_test_id("playhead-tc").inner_text().split("/")[0].strip()

            # headless Chrome 的页内时钟（performance.now / beginFrame）可以远快于墙上时钟；
            # 不量这个比值，rAF 次数和 longtask 时长就会被误读成"用户看到的帧率"。
            wall0, page0 = time.perf_counter(), page.evaluate("performance.now()")
            before = tc()
            page.keyboard.press("l")                 # l = 正向播放（旧脚本按的是 j = 反向）
            page.wait_for_timeout(SAMPLE_MS)
            after = tc()
            page.keyboard.press("k")                 # k = 停
            wall1, page1 = time.perf_counter(), page.evaluate("performance.now()")
            clock_ratio = round((page1 - page0) / max(0.001, (wall1 - wall0) * 1000), 2)
            stats = page.evaluate("({long: window.__ffLong, frames: window.__ffFrames})")
            long_tasks = stats.get("long") or []
            summary["playback"] = {"tcBefore": before, "tcAfter": after, "advanced": before != after}
            summary["clockRatioPageToWall"] = clock_ratio
            summary["longTaskCount"] = len(long_tasks)
            summary["longTaskTotalMs"] = round(sum(long_tasks), 1)
            summary["longTaskMaxMs"] = round(max(long_tasks)) if long_tasks else 0
            summary["rafCallbacksPerWallSecond"] = round(stats.get("frames", 0) / (SAMPLE_MS / 1000), 1)
            summary["fpsIsUserFacing"] = clock_ratio < 1.5   # 时钟被加速时，这个数不是用户帧率

            # --- 点击选择延迟：页内 performance.now 差值 ---
            summary["clickSelectMs"] = page.evaluate("""async () => {
              const t0 = performance.now();
              const el = document.querySelector('[data-testid="scene-block-S042"]');
              el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
              el.click();
              await new Promise((res) => requestAnimationFrame(() => res()));
              return Math.round(performance.now() - t0);
            }""")
            summary["clickSelectShowsText"] = bool(page.evaluate(
                "document.querySelector('[data-testid=\"timeline-text\"]')?.value?.length > 0"))

            # --- UI autosave 端到端：真键盘输入 → 服务端 version +1（含 700ms 防抖） ---
            v0 = c.get(f"/projects/{pid}/docs/timeline").json()["version"]
            ta = page.get_by_test_id("timeline-text")
            ta.click()
            ta.type("追加一个字。", delay=40)         # React 19：必须真键盘才触发 onChange
            t_start = time.perf_counter()
            bumped = False
            while time.perf_counter() - t_start < 20:
                if c.get(f"/projects/{pid}/docs/timeline").json()["version"] > v0:
                    bumped = True
                    break
                page.wait_for_timeout(50)
            summary["autosaveEndToEndMs"] = round((time.perf_counter() - t_start) * 1000, 1)
            summary["autosaveVersionBumped"] = bumped
            browser.close()

        # --- 阈值判定（给数据结论，不是硬断言） ---
        reasons = []
        if summary["fpsIsUserFacing"] and summary["rafCallbacksPerWallSecond"] < 50:
            reasons.append(f"播放 {summary['rafCallbacksPerWallSecond']} 帧/秒 <50")
        if summary["fpsIsUserFacing"] and summary["longTaskMaxMs"] >= 200:
            reasons.append(f"最长任务 {summary['longTaskMaxMs']}ms ≥200ms")
        if summary["loadMs"] > 2000:
            reasons.append(f"首屏 {summary['loadMs']}ms >2000ms")
        if summary.get("autosaveEndToEndMs", 0) > 2500:
            reasons.append(f"autosave {summary['autosaveEndToEndMs']}ms >2500ms")
        if summary.get("clickSelectMs", 0) > 200:
            reasons.append(f"选中响应 {summary['clickSelectMs']}ms >200ms")
        summary["verdictNeedsVirtualization"] = bool(reasons)
        summary["verdictReasons"] = reasons or ["墙上时钟可量到的指标都在阈值内"]
        if not summary["fpsIsUserFacing"]:
            summary["verdictScope"] = (
                f"headless 页内时钟是墙上时钟的 {summary['clockRatioPageToWall']}×，"
                "rAF 次数与 longtask 时长不能当用户帧率引用；"
                "本判定只覆盖首屏、DOM 节点数、ops 往返、autosave 端到端与选中响应")

        print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
        assert summary["renderedSceneNodes"] == SCENES, summary["renderedSceneNodes"]
        assert summary["playback"]["advanced"], f"播放头没动，采样无效：{summary['playback']}"
        assert summary["autosaveVersionBumped"], "UI 编辑没落到服务端，autosave 路径没被测到"
        assert summary["ops"]["p95ms"] > 0

        out = Path("docs/reports/p1-11-timeline-100.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"archived: {out} | 判定："
              f"{'需要虚拟化' if summary['verdictNeedsVirtualization'] else '暂不虚拟化'}"
              f" — {summary['verdictReasons']}", flush=True)
        print("PASS: 100 场景有效实测完成（正向播放 + 真 ops/autosave + 无恒真断言）", flush=True)
        return 0
    finally:
        d = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
        r = d.delete(f"/projects/{pid}?confirm=true")
        print("cleanup:", r.status_code, r.text[:200], flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
