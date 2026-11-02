"""R3.0 UI 冒烟：时间轴拖拽/改字/相机/撤销/刷新恢复 + 审片播放器批注。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

WEB = "http://localhost:3000"
API = "http://127.0.0.1:7860/api"
http = httpx.Client(base_url=API, timeout=120, trust_env=False)


def type_sticky(page, selector: str, text: str) -> None:
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=5)
    page.wait_for_timeout(400)


def main() -> int:
    name = f"r3-ui-{int(time.time())}"
    made = http.post("/projects/from-template", json={"templateId": "product40", "name": name}).json()
    pid, rid = made["project"]["id"], made["run_id"]
    print("project", pid, "run", rid, flush=True)
    with sync_playwright() as pw:
        from app.config import detect_chrome
        browser = pw.chromium.launch(headless=True, executable_path=detect_chrome(), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(20000)

        page.goto(f"{WEB}/timeline?project={pid}&run={rid}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid="scene-block-S01"]', timeout=30000)
        assert page.locator('[data-testid^="scene-block-"]').count() == 5
        print("✓ 1. 时间轴 5 场景 / 轨道", flush=True)

        before = http.get(f"/projects/{pid}/docs/timeline").json()["content"]
        s01 = before["scenes"][0]
        page.get_by_role("button", name="Fit").click()
        page.wait_for_timeout(300)
        handle = page.locator('[data-testid="scene-resize-S01"]')
        box = handle.bounding_box()
        assert box
        width = page.locator('[data-testid="scene-block-S01"]').bounding_box()["width"]
        pps = width / (s01["end"] - s01["start"])
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 2 * pps, box["y"] + box["height"] / 2, steps=8)
        page.mouse.up()
        page.wait_for_timeout(1200)
        after = http.get(f"/projects/{pid}/docs/timeline").json()["content"]
        assert abs(after["scenes"][0]["end"] - (s01["end"] + 2)) < 0.12, after["scenes"][0]
        assert abs(after["scenes"][1]["start"] - after["scenes"][0]["end"]) < 1e-6
        assert after["duration"] > before["duration"] + 1.9
        print("✓ 2. 拖右边缘 S01 +2s，S02 自动后移", flush=True)

        page.locator('[data-testid="scene-block-S01"]').click()
        new_text = "时间轴里改过的第一句文案。"
        type_sticky(page, '[data-testid="timeline-text"]', new_text)
        page.wait_for_timeout(1600)
        doc = http.get(f"/projects/{pid}/docs/timeline").json()["content"]
        assert doc["scenes"][0].get("text") == new_text, doc["scenes"][0]
        page.wait_for_selector('[data-testid="timeline-preview"]', timeout=30000)
        print("✓ 3. 场景文本自动保存 + 静帧预览", flush=True)

        page.locator('[data-testid="camera-preset-push-in"]').click()
        page.wait_for_timeout(800)
        doc = http.get(f"/projects/{pid}/docs/timeline").json()["content"]
        assert len(doc["scenes"][0].get("camera_keyframes") or []) == 2
        assert doc["scenes"][0]["camera_keyframes"][-1]["zoom"] == 1.08
        print("✓ 4. 相机预设写入 keyframes", flush=True)

        page.locator('[data-testid="timeline-undo"]').click()
        page.wait_for_timeout(900)
        doc = http.get(f"/projects/{pid}/docs/timeline").json()["content"]
        assert not doc["scenes"][0].get("camera_keyframes")
        print("✓ 5. 撤销相机操作", flush=True)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="scene-block-S01"]', timeout=30000)
        page.locator('[data-testid="scene-block-S01"]').click()
        expect(page.locator('[data-testid="timeline-text"]')).to_have_value(new_text)
        print("✓ 6. 刷新恢复自动保存", flush=True)

        # 审片播放器：用 40s 已交付项目 174 / run 223
        page.goto(f"{WEB}/player?project=174&run=223", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid="review-video"]', timeout=30000)
        page.wait_for_selector('[data-testid^="comment-"]', timeout=30000)
        n0 = page.locator('[data-testid^="comment-"]').count()
        assert n0 >= 10, n0
        comments = http.get("/projects/174/review").json()["comments"]
        target = next(c for c in comments if c["time"] > 0)
        page.locator(f'[data-testid="comment-{target["id"]}"]').click()
        page.wait_for_timeout(500)
        at = page.evaluate("() => document.querySelector('video')?.currentTime || 0")
        assert abs(at - target["time"]) <= 0.1, (at, target["time"])
        print(f"✓ 7. 点击批注跳帧 {target['time']}s → {at:.3f}s", flush=True)
        type_sticky(page, '[data-testid="review-body"]', "R3 播放器冒烟批注")
        page.locator('[data-testid="review-save"]').click()
        page.wait_for_timeout(800)
        assert page.locator('[data-testid^="comment-"]').count() == n0 + 1
        assert page.get_by_text("R3 播放器冒烟批注").count() >= 1
        print(f"✓ 8. 审片播放器批注 {n0} → {n0 + 1}", flush=True)

        browser.close()
    print("PASS: R3.0 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
