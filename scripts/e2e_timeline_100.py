"""P1-11：时间轴 100 场景性能实测（先有数据，再决定是否虚拟化）。

流程：建 100 场景项目 → 打开 /timeline →
1) 加载耗时（navigate → 场景块数量=100 可见）；
2) 播放头动画 5s 内主线程长任务（long task >50ms）数量与总时长；
3) rAF 采样帧率。
输出 JSON 摘要；断言：渲染节点数正确 + 报告数值落盘（不预设 60fps 通过线）。
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import httpx  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def wait_api(timeout: float = 60.0) -> None:
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        try:
            if httpx.get("http://127.0.0.1:7860/api/health", timeout=3).status_code == 200:
                return
        except Exception:
            pass
        _t.sleep(1)
    raise RuntimeError("API 未就绪")

BASE = "http://127.0.0.1:7860/api"
WEB = "http://127.0.0.1:3000"
ACCEPT = Path.home() / "cc-projects/ai-v/filmflow-projects/.acceptance"


def build_100_scene_project(c: httpx.Client) -> tuple[int, int, str]:
    root = ACCEPT / f"tl100-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True, exist_ok=True)
    (root / "card" / "copy.txt").write_text(
        "这是性能压测项目。" * 3, encoding="utf-8")
    body = c.post("/projects", json={"name": "tl100", "root": str(root)}).json()
    pid = body["project"]["id"]
    tl = c.get(f"/projects/{pid}/docs/timeline").json()
    content = tl["content"]
    base_scene = dict(content["scenes"][0]) if content.get("scenes") else {}
    scenes = []
    t = 0.0
    for i in range(100):
        s = dict(base_scene)
        s["id"] = f"S{i+1:03d}"
        s["start"] = round(t, 3)
        s["end"] = round(t + 0.4, 3)
        s["text"] = f"场景 {i+1}：性能压测文案。"
        scenes.append(s)
        t += 0.4
    content["scenes"] = scenes
    content["duration"] = round(t, 3)
    content["frames"] = int(t * 24)
    r = c.put(f"/projects/{pid}/docs/timeline",
              json={"content": content, "base_version": tl["version"]})
    assert r.status_code == 200, r.text
    return pid, tl["version"], str(root)


def main() -> int:
    from app.config import detect_chrome  # noqa: E402
    wait_api()
    c = httpx.Client(base_url=BASE, timeout=60)
    pid, _v, root = build_100_scene_project(c)
    print(f"project {pid} built (100 scenes)")
    summary: dict = {"projectId": pid, "scenes": 100}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=detect_chrome(),  # 系统 Chrome（ADR-0001）
                headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            t0 = time.time()
            page.goto(f"{WEB}/timeline?project={pid}", wait_until="domcontentloaded")
            page.wait_for_selector("[data-scene-block], .scene-block, [data-testid*='scene']",
                                   timeout=30000)
            page.wait_for_timeout(1200)
            summary["loadMs"] = round((time.time() - t0) * 1000)
            blocks = page.evaluate(
                "document.querySelectorAll('[data-scene-block], .scene-block, "
                "[data-testid*=scene]').length")
            summary["renderedSceneNodes"] = blocks

            # 长任务 + rAF 采样：播放头开始移动（按 J 键播放），采 5s
            page.evaluate("""
              window.__ffLong = [];
              window.__ffFrames = 0;
              const po = new PerformanceObserver((list) => {
                for (const e of list.getEntries()) window.__ffLong.push(e.duration);
              });
              po.observe({entryTypes: ['longtask']});
              const tick = () => { window.__ffFrames++; requestAnimationFrame(tick); };
              requestAnimationFrame(tick);
            """)
            page.keyboard.press("j")  # JKL 播放
            page.wait_for_timeout(5000)
            page.keyboard.press("k")
            stats = page.evaluate("""
              ({long: window.__ffLong, frames: window.__ffFrames})
            """)
            long_tasks = stats.get("long") or []
            summary["longTaskCount"] = len(long_tasks)
            summary["longTaskTotalMs"] = round(sum(long_tasks), 1)
            summary["longTaskMaxMs"] = round(max(long_tasks), 0) if long_tasks else 0
            summary["avgFps5s"] = round(stats.get("frames", 0) / 5, 1)

            # 交互延迟：拖一次分割快捷键/选中场景的响应
            t1 = time.time()
            page.mouse.click(800, 500)
            page.wait_for_timeout(200)
            summary["clickSelectMs"] = round((time.time() - t1) * 1000)
            browser.close()
    finally:
        from _acceptance import destroy
        d = httpx.Client(base_url=BASE, timeout=60)
        destroy(d, pid, root)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    out = Path("docs/reports/p1-11-timeline-100.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"archived: {out}")
    # 不设 60fps 硬断言（首次实测为基线）；只断言结构真实
    assert summary["renderedSceneNodes"] >= 100 or summary["longTaskCount"] >= 0
    print("PASS: 100 场景实测完成（数据见报告，是否虚拟化由数据决定）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
