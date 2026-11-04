"""B9 两条 UI 改动的真机验收（§7 第 2 项第 4 步）：

- P1-08：两个浏览器上下文改同一项目时间轴 → 后保存方吃到 409，横幅必须**渲染服务端
  的字段级 diff**（`data-testid="timeline-conflict-diff"`，B9 之前只读 current_version，diff 被丢掉）。
- P1-18：`/audio` 页许可"已授权"复选框**默认不勾选**（B9 之前默认 true），读回也 `=== true`。

UI 自动化纪律：系统 Chrome + **真键盘输入**（React 19 `fill()` 不触发 onChange）；
项目自建自删（Cleanup）。跑前确认没有别的渲染类任务在占 Chrome。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import httpx
from playwright.sync_api import sync_playwright

from _acceptance import Cleanup, create
from app.config import detect_chrome

BASE = "http://127.0.0.1:7860/api"
WEB = "http://127.0.0.1:3000"


def wait_autosave(c: httpx.Client, pid: int, v0: int, timeout: float = 15.0) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = c.get(f"/projects/{pid}/docs/timeline").json()["version"]
        if v > v0:
            return v
        time.sleep(0.2)
    raise RuntimeError(f"autosave 没把 version 从 {v0} 推上去")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code != 200:
        raise SystemExit("API 未就绪：先 ./dev.sh")

    c = httpx.Client(base_url=BASE, timeout=60, trust_env=False)
    summary: dict = {}
    with Cleanup(c, keep=args.keep) as clean:
        proj = create(c, "b9-ui", "这是 B9 UI 验收项目。两句话够了。")
        pid = proj["id"]
        clean.track(pid, proj["root"])
        # 派生 timeline 的场景只有 ~2s，加一个字就会 E_SCENE_READ_OVERFLOW（headless 里
        # window.confirm 被自动 dismiss，409 后永远不重试，autosave 版本就推不动）。
        # 播种 6s 场景 + 初始文案，让"追加短句"落在读时预算内。
        tl = c.get(f"/projects/{pid}/docs/timeline").json()
        content = tl["content"]
        base_scene = dict(content["scenes"][0])
        base_scene.update({"start": 0.0, "end": 6.0, "text": "初始文案。"})
        content["scenes"] = [base_scene]
        content["duration"] = 6.0
        r = c.put(f"/projects/{pid}/docs/timeline",
                  json={"content": content, "base_version": tl["version"],
                        "author": "b9-ui-seed"})
        assert r.status_code == 200, r.text
        pid = pid
        print(f"project={pid}（已播种 6s 场景）", flush=True)
        v0 = c.get(f"/projects/{pid}/docs/timeline").json()["version"]

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=detect_chrome(), headless=True,
                                        args=["--no-sandbox"])
            # --- P1-18：/audio 默认未勾选（先于时间轴，单独页面互不干扰） ---
            page_a = browser.new_context(viewport={"width": 1600, "height": 900}).new_page()
            page_a.goto(f"{WEB}/audio?project={pid}", wait_until="domcontentloaded")
            page_a.wait_for_selector("input[type='checkbox']", timeout=20000)
            boxes = page_a.locator("input[type='checkbox']")
            authorized_checked = None
            for i in range(boxes.count()):
                # 「已授权」label 旁边的复选框
                if "已授权" in (boxes.nth(i).locator("xpath=..").inner_text() or ""):
                    authorized_checked = boxes.nth(i).is_checked()
                    break
            if authorized_checked is None:
                authorized_checked = boxes.first.is_checked()
            summary["audio_authorized_default_checked"] = authorized_checked
            assert authorized_checked is False, \
                f"P1-18 回潮：已授权默认勾选（checked={authorized_checked}）"
            print("P1-18 ✓ /audio 已授权默认未勾选", flush=True)

            # --- P1-08：B 先开页面（base=v0），A 改成 v1，B 再改 → 409 + 字段级 diff ---
            page_b = browser.new_context(viewport={"width": 1600, "height": 900}).new_page()
            page_b.goto(f"{WEB}/timeline?project={pid}", wait_until="domcontentloaded")
            page_b.wait_for_selector("[data-testid='scene-block-S01']", timeout=30000)

            page_a.goto(f"{WEB}/timeline?project={pid}", wait_until="domcontentloaded")
            page_a.wait_for_selector("[data-testid='scene-block-S01']", timeout=30000)

            # autosave effect 依赖 selectedId：先点场景块选中，再进 textarea 输入
            page_a.get_by_test_id("scene-block-S01").click()
            ta_a = page_a.get_by_test_id("timeline-text")
            ta_a.click()
            ta_a.type("甲的改动。", delay=30)          # 真键盘：React 19 onChange
            v1 = wait_autosave(c, pid, v0)
            print(f"A 保存成功 v{v0}→v{v1}", flush=True)

            page_b.get_by_test_id("scene-block-S01").click()
            ta_b = page_b.get_by_test_id("timeline-text")
            ta_b.click()
            ta_b.type("乙的冲突改动。", delay=30)
            page_b.wait_for_selector("[data-testid='timeline-conflict']", timeout=20000)
            banner = page_b.get_by_test_id("timeline-conflict").inner_text()
            diff = page_b.get_by_test_id("timeline-conflict-diff")
            diff.wait_for(timeout=10000)
            diff_items = diff.locator("li")
            diff_text = diff.inner_text()
            summary["conflict_banner"] = banner[:120]
            summary["conflict_diff_items"] = diff_items.count()
            summary["conflict_diff_text"] = diff_text[:200]
            assert diff_items.count() > 0, \
                "P1-08 回潮：409 横幅没有渲染字段级 diff（ul 为空）"
            assert "text" in diff_text.lower() or "文案" in diff_text or "S0" in diff_text, \
                f"diff 里应能看到字段/场景级信息，实际：{diff_text!r}"
            # 冲突期间页面保留草稿（P1-08 保稿语义）：输入框仍是乙的文案
            assert "乙的冲突改动" in (ta_b.input_value() or ""), "冲突保稿丢失"
            print(f"P1-08 ✓ 409 横幅 + {diff_items.count()} 条字段级 diff：{diff_text!r}",
                  flush=True)
            browser.close()

        print("PASS: B9 UI 验收（P1-08 字段级 diff + P1-18 默认不勾选）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
