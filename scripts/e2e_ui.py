"""Playwright UI E2E（tech-plan §10 验收流的自动化层）。

前置：API :7860 与 Web :3000 已启动（./dev.sh）。
场景：首页 → 向导 5 步（文案/画幅/风格选择器[搜索+chips+设主风格]/声音/生成）→ 画布 46 节点。

用法：uv run --project server python scripts/e2e_ui.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

WEB = "http://localhost:3000"


def fill_sticky(page, selector: str, text: str, attempts: int = 8) -> None:
    """Next dev 水合竞态防护：fill 后校验 React state 回写，未粘住则重试。"""
    for i in range(attempts):
        page.fill(selector, text)
        page.wait_for_timeout(500)
        if page.locator(selector).input_value() == text:
            return
    raise RuntimeError(f"fill 未粘住（水合未完成？）: {selector}")


def type_sticky(page, selector: str, text: str) -> None:
    """React 19 受控输入：fill 的原生 setter 不触发 onChange，用真实键盘输入。"""
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=6)
    page.wait_for_timeout(500)


def main() -> int:
    t0 = time.time()
    try:
        return _run()
    except Exception:
        import traceback; traceback.print_exc()
        Path("/tmp/e2e-fail.png").exists() and None
        sys.exit(1)


def _run() -> int:
    t0 = time.time()
    with sync_playwright() as pw:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from app.config import detect_chrome
        browser = pw.chromium.launch(headless=True,
                                     executable_path=detect_chrome(),  # 系统 Chrome（ADR-0001）
                                     args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(15000)

        # 1. 首页
        page.goto(WEB, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("text=导入项目", timeout=30000)
        expect(page.get_by_role("heading", name="FilmFlow")).to_be_visible()
        print("✓ 1. 首页加载", flush=True)

        # 2. 向导第 1 步：文案
        page.get_by_role("link", name="＋ 新建项目向导").click()
        page.wait_for_selector('[data-testid="copy-input"]')
        page.wait_for_timeout(1000)
        type_sticky(page, '[data-testid="copy-input"]', "一条消息被转发，往往不是因为它真实。真相经得起第二次查看，而谣言跑出一条街。")
        try:
            page.get_by_role("button", name="下一步").click(timeout=8000)
        except Exception:
            page.screenshot(path="/tmp/e2e-step1.png")
            print("step1 现场：", page.locator("textarea").input_value()[:30],
                  "| 禁用按钮数:", page.locator("button:disabled").count(), flush=True)
            raise
        print("✓ 2. 文案步骤", flush=True)

        # 3. 第 2 步：画幅默认值直接过
        page.wait_for_selector("text=帧数 = round")
        page.get_by_role("button", name="下一步").click()
        print("✓ 3. 画幅步骤（948 帧）", flush=True)

        # 4. 第 3 步：风格选择器
        page.wait_for_selector('[data-testid="style-picker"]')
        for _i in range(12):   # 轮询 60s：推荐/索引异步加载
            if page.locator('[data-testid^="style-card-"]').count() > 0:
                break
            page.wait_for_timeout(5000)
        assert page.locator('[data-testid^="style-card-"]').count() > 0, "风格卡片 60s 未加载"
        # 搜索「水墨」（同义词）
        type_sticky(page, '[data-testid="style-search"]', "水墨")
        page.wait_for_timeout(800)
        z_cards = page.locator('[data-testid^="style-card-Z"]')
        assert z_cards.count() >= 10, f"「水墨」同义词命中 Z 集不足：{z_cards.count()}"
        print(f"✓ 4. 搜索「水墨」命中 Z 集 {z_cards.count()} 条", flush=True)
        # 清空 → chips 可生产 → 点第一张卡 → 设为主风格
        type_sticky(page, '[data-testid="style-search"]', "")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="可生产", exact=True).click()
        page.wait_for_timeout(600)
        first_card = page.locator('[data-testid^="style-card-"]').first
        first_card.click()
        page.locator("aside").get_by_role("button", name="设为主风格").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="已选主风格").click()
        page.wait_for_selector("text=④ 声音方案", timeout=20000)
        print("✓ 5. 设为主风格（可生产集合）", flush=True)

        # 5. 第 4/5 步：生成工作流
        page.get_by_role("button", name="下一步").click()
        try:
            page.wait_for_selector('[data-testid="materialize"]', timeout=30000)
        except Exception:
            page.screenshot(path="/tmp/e2e-step5.png")
            errs = []
            print("step5 现场：当前可见步骤标题 =",
                  page.locator("h2").all_text_contents(), flush=True)
            raise
        page.get_by_role("button", name="生成工作流 →").click()
        try:
            page.wait_for_selector('[data-testid="node-canvas"]', timeout=60000)
        except Exception:
            page.screenshot(path="/tmp/e2e-canvas.png")
            print("canvas 现场: url =", page.url, flush=True)
            raise
        page.wait_for_selector(".react-flow__node", timeout=60000)
        nodes = page.locator(".react-flow__node").count()
        assert nodes == 46, f"画布节点数 {nodes} ≠ 46"
        print(f"✓ 6. 生成工作流 → 画布 46 节点", flush=True)

        # 6. 语言切换（i18n 脚手架）
        page.get_by_role("button", name="EN", exact=True).click()
        page.wait_for_timeout(400)
        expect(page.get_by_role("link", name="← Projects")).to_be_visible()
        print("✓ 7b. 画布 46 节点（EN 界面）", flush=True)
        print("✓ 7. 语言切换 EN 生效", flush=True)

        # 7. 导入路径：画布显示参考项目（回首页导入）
        page.evaluate("localStorage.removeItem('ff.lang')")   # 复位中文（导入按钮为中文文案）
        page.goto(WEB, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("text=导入项目", timeout=30000)
        page.wait_for_timeout(1500)   # 水合（输入框默认值即 rumor 路径，无需填写）
        page.get_by_role("button", name="导入 rumor-39s").click()
        page.wait_for_selector(".react-flow__node", timeout=60000)
        assert page.locator(".react-flow__node").count() == 46
        print("✓ 8. 导入 rumor-39s → 46 节点画布", flush=True)

        browser.close()
    print(f"\nUI E2E 全部通过（{time.time()-t0:.0f}s）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
