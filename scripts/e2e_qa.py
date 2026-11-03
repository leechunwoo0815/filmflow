"""FR-39 UI 冒烟：QA 问题卡、扩场景修复、即时验证、撤销。"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import sync_playwright  # noqa: E402

WEB = "http://localhost:3000"
API = "http://127.0.0.1:7860/api"
PID = 227
http = httpx.Client(base_url=API, timeout=120, trust_env=False)
original = http.get(f"/projects/{PID}/docs/timeline").json()
scene_id = original["content"]["scenes"][0]["id"]


def restore() -> None:
    cur = http.get(f"/projects/{PID}/docs/timeline").json()
    if cur["content"] != original["content"]:
        http.put(f"/projects/{PID}/docs/timeline", json={
            "content": original["content"], "base_version": cur["version"],
            "author": "e2e-qa-cleanup"})


def main() -> int:
    try:
        http.post(f"/projects/{PID}/timeline/ops", json={
            "op": "set_text", "sceneId": scene_id,
            "text": "这一句话需要再多一点时间读。", "force": True})
        with sync_playwright() as pw:
            from app.config import detect_chrome
            b = pw.chromium.launch(headless=True, executable_path=detect_chrome(),
                                   args=["--no-sandbox"])
            page = b.new_page(viewport={"width": 1400, "height": 1000})
            page.set_default_timeout(30000)
            try:
                page.goto(f"{WEB}/qa?project={PID}", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector('[data-testid="qa-issue-text_overflow"]', timeout=30000)
                assert page.get_by_text("文案超出场景读时").count() >= 1
                print("✓ 1. QA 页展示 text_overflow 位置/建议", flush=True)

                page.get_by_test_id("qa-fix-text_overflow-extend_scene").click()
                page.wait_for_selector("text=已修复并即时验证", timeout=20000)
                qa = http.get(f"/projects/{PID}/qa").json()
                assert not any(i["category"] == "text_overflow" for i in qa["issues"])
                print("✓ 2. 扩场景 0.5s 后即时验证消失", flush=True)

                page.get_by_text("撤销", exact=True).first.click()
                page.wait_for_selector("text=已撤销修复", timeout=20000)
                qa = http.get(f"/projects/{PID}/qa").json()
                assert any(i["category"] == "text_overflow" for i in qa["issues"])
                print("✓ 3. UI 撤销后问题复现", flush=True)
                page.screenshot(path="/tmp/ff_qa_ui.png")
            finally:
                b.close()
        print("PASS: FR-39 QA UI 冒烟通过")
        return 0
    finally:
        restore()


if __name__ == "__main__":
    sys.exit(main())
