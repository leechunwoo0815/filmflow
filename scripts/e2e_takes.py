"""FR-38 UI 冒烟：双视频同步/差异/元数据/提升/场景采纳。"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

WEB = "http://localhost:3000"
http = httpx.Client(base_url="http://127.0.0.1:7860/api", timeout=60, trust_env=False)
PID = 188


def type_sticky(page, selector: str, text: str) -> None:
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=5)
    page.wait_for_timeout(300)


def main() -> int:
    with sync_playwright() as pw:
        from app.config import detect_chrome
        browser = pw.chromium.launch(headless=True, executable_path=detect_chrome(), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(30000)
        page.goto(f"{WEB}/takes?project={PID}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid="take-237"]', timeout=30000)
        page.wait_for_selector('[data-testid="take-254"]', timeout=30000)
        page.wait_for_selector('[data-testid="take-video-a"]', timeout=30000)
        page.wait_for_selector('[data-testid="take-video-b"]', timeout=30000)
        print("✓ 1. Takes 列表 + A/B 视频", flush=True)

        page.get_by_role("button", name="同步播放").click()
        page.wait_for_timeout(1200)
        ta = page.evaluate("() => document.querySelector('[data-testid=take-video-a]')?.currentTime || 0")
        tb = page.evaluate("() => document.querySelector('[data-testid=take-video-b]')?.currentTime || 0")
        assert abs(ta - tb) <= 1 / 24 + 0.08, (ta, tb)
        page.get_by_role("button", name="暂停").click()
        page.get_by_role("button", name="帧→").click()
        page.get_by_role("button", name="帧→").click()
        page.wait_for_timeout(300)
        ta = page.evaluate("() => document.querySelector('[data-testid=take-video-a]')?.currentTime || 0")
        tb = page.evaluate("() => document.querySelector('[data-testid=take-video-b]')?.currentTime || 0")
        assert abs(ta - tb) <= 0.02, (ta, tb)
        print(f"✓ 2. 同步播放/逐帧 {ta:.3f}s vs {tb:.3f}s", flush=True)

        page.locator('[data-testid="take-diff"]').check()
        page.wait_for_selector('[data-testid="take-diff-panel"]', timeout=10000)
        print("✓ 3. 差异叠加面板", flush=True)
        page.locator('[data-testid="take-diff"]').uncheck()

        type_sticky(page, '[data-testid="take-name"]', "A版-UI")
        page.locator('[data-testid="take-save-meta"]').click()
        page.wait_for_timeout(700)
        item = next(x for x in http.get(f"/projects/{PID}/takes").json()["items"] if x["runId"] == 237)
        assert item["name"] == "A版-UI", item
        print("✓ 4. 元数据保存", flush=True)

        page.locator('[data-testid="take-237"]').get_by_role("button", name="提升").click()
        page.wait_for_timeout(600)
        assert http.get(f"/projects/{PID}/takes").json()["currentRunId"] == 237
        page.locator('[data-testid="take-254"]').get_by_role("button", name="提升").click()
        page.wait_for_timeout(600)
        assert http.get(f"/projects/{PID}/takes").json()["currentRunId"] == 254
        print("✓ 5. 提升当前 Take（A→B）", flush=True)

        page.locator("select").last.select_option("S03")
        page.locator('[data-testid="take-adopt"]').click()
        page.wait_for_timeout(800)
        doc = http.get(f"/projects/{PID}/docs/timeline").json()["content"]
        s3 = next(s for s in doc["scenes"] if s["id"] == "S03")
        assert s3.get("text") == "B版三。", s3
        print("✓ 6. 采纳 B 的 S03", flush=True)

        browser.close()
    print("PASS: FR-38 Take 对比 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
