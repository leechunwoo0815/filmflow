"""FR-39 UI 冒烟：QA 问题卡、扩场景修复、即时验证、撤销。

判官 §六 #9：项目与"文案超出读时"这个问题态都由脚本自建（原先写死演示 227，
还带着 force=true 往演示时间轴上写脏文案、退出时靠 restore() 补救）。"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _acceptance import require_scratch_project, throwaway
from playwright.sync_api import sync_playwright

WEB = "http://localhost:3000"
API = "http://127.0.0.1:7860/api"
LONG_TEXT = "这一句话需要再多一点时间读。"   # 一次 extend_scene(+0.5s) 刚好能消化
COPY = "第一句话要读完其实不容易。第二句话同样需要更多时间才能读完。"
http = httpx.Client(base_url=API, timeout=120, trust_env=False)


def smoke(pid: int) -> int:
    tl = http.get(f"/projects/{pid}/docs/timeline").json()
    scene_id = tl["content"]["scenes"][0]["id"]
    # 自建项目上才允许 force：问题态是脚本造出来的，不是从演示借来的
    r = http.post(f"/projects/{pid}/timeline/ops", json={
        "op": "set_text", "sceneId": scene_id, "baseVersion": tl["version"],
        "text": LONG_TEXT, "force": True})
    assert r.status_code == 200, r.text

    def overflow_scenes() -> set[str]:
        return {i["location"]["sceneId"] for i in http.get(f"/projects/{pid}/qa").json()["issues"]
                if i["category"] == "text_overflow"}

    assert scene_id in overflow_scenes(), overflow_scenes()
    with sync_playwright() as pw:
        from app.config import detect_chrome
        b = pw.chromium.launch(headless=True, executable_path=detect_chrome(),
                               args=["--no-sandbox"])
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        page.set_default_timeout(30000)
        try:
            page.goto(f"{WEB}/qa?project={pid}", wait_until="domcontentloaded", timeout=60000)
            # 问题卡按类别打 testid，同类别会有多张卡 → 用「位置：S0x」锁定本场景那张
            card = page.locator('[data-testid="qa-issue-text_overflow"]').filter(has_text=scene_id).first
            card.wait_for(timeout=30000)
            assert page.get_by_text("文案超出场景读时").count() >= 1
            print(f"✓ 1. QA 页展示 {scene_id} 的 text_overflow 位置/建议", flush=True)

            card.get_by_test_id("qa-fix-text_overflow-extend_scene").click()
            # 文档级修复（timeline）的契约是 verified=null + documentVerified=true，
            # UI 因此显示"需要下一次 Run 验证"；老脚本等的是 verified=true 的文案，
            # 那个分支现在只有 fill_license/missing_asset 会走到——这里是实测出来的漂移。
            page.wait_for_selector("text=已执行；需要下一次 Run 验证", timeout=20000)
            assert scene_id not in overflow_scenes(), overflow_scenes()
            fix = http.get(f"/projects/{pid}/qa/report").json()["items"][-1]
            assert fix["category"] == "text_overflow" and fix.get("documentVerified") is True, fix
            assert fix.get("verified") is None and fix.get("requiresRerun") is True, fix
            print(f"✓ 2. 扩场景 0.5s 后 {scene_id} 问题消失 + documentVerified=true（verified=null 需新 Run）",
                  flush=True)

            page.get_by_text("撤销", exact=True).first.click()
            page.wait_for_selector("text=已撤销修复", timeout=20000)
            assert scene_id in overflow_scenes(), overflow_scenes()
            print(f"✓ 3. UI 撤销后 {scene_id} 问题复现", flush=True)
            page.screenshot(path="/tmp/ff_qa_ui.png")
        finally:
            b.close()
    print("PASS: FR-39 QA UI 冒烟通过（全程只动自建项目，退出即级联删除）")
    return 0


def main() -> int:
    if "--build" in sys.argv:
        with throwaway(http, "qa-e2e", COPY) as proj:
            return smoke(proj["id"])
    return smoke(require_scratch_project(http, Path(__file__).name, sys.argv))


if __name__ == "__main__":
    sys.exit(main())
