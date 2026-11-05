"""FR-31 UI 冒烟：模板/示例入口、Studio 5 步引导、向导用户标题预演。

前置：API :7860 与 Web :3000 已启动（./dev.sh）。
用法：uv run --project server python scripts/e2e_onboarding.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import expect, sync_playwright

WEB = "http://localhost:3000"
COPY = "很多工作不是难，是重复。把重复交给工具，人才有时间思考。"


def type_sticky(page, selector: str, text: str) -> None:
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=6)
    page.wait_for_timeout(500)


def main() -> int:
    with sync_playwright() as pw:
        from app.config import detect_chrome
        browser = pw.chromium.launch(headless=True, executable_path=detect_chrome(),
                                     args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(15000)

        # 1. 首页：3 模板 + 2 只读示例
        page.goto(WEB, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid="template-voice15"]', timeout=30000)
        assert page.locator('[data-testid^="template-"]').count() >= 3
        assert page.locator('[data-testid^="example-"]').count() == 2
        expect(page.get_by_text("示例项目（只读）")).to_be_visible()
        print("✓ 1. 首页 3 模板 + 2 只读示例", flush=True)

        # 2. 模板 → Studio 引导（首次显示 / 跳过 / 重看 / 刷新不反弹）
        page.locator('[data-testid="use-template-voice15"]').click()
        page.wait_for_url("**/canvas?project=*", timeout=60000)
        page.wait_for_selector('[data-testid="studio-guide"]', timeout=30000)
        guide_text = page.locator('[data-testid="studio-guide"]').inner_text()
        for step in ("1. 场景列表", "2. 单帧预览", "3. 改一句", "4. 看 diff", "5. 出 draft"):
            assert step in guide_text, guide_text
        page.locator('[data-testid="studio-guide-close"]').click()
        expect(page.locator('[data-testid="studio-guide"]')).to_have_count(0)
        page.locator('[data-testid="studio-guide-btn"]').click()
        expect(page.locator('[data-testid="studio-guide"]')).to_be_visible()
        page.locator('[data-testid="studio-guide-close"]').click()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        assert page.locator('[data-testid="studio-guide"]').count() == 0, "已读引导不应自动重开"
        print("✓ 2. Studio 引导 5 步 / 可跳过 / 可重看 / 记忆", flush=True)

        # 3. 示例 → 复制为我的项目
        page.goto(WEB, wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="example-voice15"]', timeout=30000)
        page.locator('[data-testid="example-voice15"] button').click()
        page.wait_for_url("**/canvas?project=*", timeout=60000)
        print("✓ 3. 示例复制为我的项目", flush=True)

        # 4. 向导第 3 步：用户标题预演 + 3 候选切换
        page.goto(f"{WEB}/wizard", wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="copy-input"]', timeout=30000)
        page.wait_for_timeout(800)
        type_sticky(page, '[data-testid="copy-input"]', COPY)
        page.get_by_role("button", name="下一步").click()
        page.wait_for_selector("text=帧数 = round")
        page.get_by_role("button", name="下一步").click()
        page.wait_for_selector('[data-testid="style-picker"]', timeout=30000)
        for _ in range(12):
            if page.locator('[data-testid^="style-card-"]').count() > 0:
                break
            page.wait_for_timeout(5000)
        assert page.locator('[data-testid^="style-card-"]').count() > 0, "风格卡片未加载"
        page.get_by_role("button", name="可生产", exact=True).click()
        page.wait_for_timeout(600)
        page.locator('[data-testid^="style-card-"]').first.click()
        page.locator("aside").get_by_role("button", name="设为主风格").click()
        page.wait_for_selector('[data-testid="title-preview"]', timeout=20000)
        first_title = page.locator('[data-testid="wizard-title"]').inner_text()
        assert "很多工作不是难" in first_title, first_title
        assert "风从纸上起" not in first_title
        assert page.locator('[data-testid^="title-choice-"]').count() == 3
        page.locator('[data-testid="title-preview"]').scroll_into_view_if_needed()
        page.locator('[data-testid="title-choice-1"]').click()
        page.wait_for_timeout(300)
        second_title = page.locator('[data-testid="wizard-title"]').inner_text()
        assert second_title != first_title, (first_title, second_title)
        print(f"✓ 4. 标题预演用用户文案：{first_title} → {second_title}", flush=True)

        browser.close()
    print("PASS: FR-31 新手引导 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    t0 = time.time()
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
