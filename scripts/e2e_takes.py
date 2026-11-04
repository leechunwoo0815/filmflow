"""FR-38 UI 冒烟：双视频同步/差异/元数据/提升/场景采纳。

两种起手：
  --build                自建两次到 F04 的 Run（判官 §六 #9：状态也自己造，用完自删）
  --project <id> --run A --run B   指向已有的 scratch 项目
指向演示/保护项目会被直接拒绝（判官 P1-9：本脚本曾写脏 188 的时间轴版本链）。"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import sync_playwright

WEB = "http://localhost:3000"
http = httpx.Client(base_url="http://127.0.0.1:7860/api", timeout=600, trust_env=False)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _acceptance import require_scratch_project
from _scratch_state import build_take_state, destroy_project, wait_api

BUILD = "--build" in sys.argv
if BUILD:
    wait_api()
    STATE = build_take_state(http, "takes-e2e")
    PID = STATE["pid"]
    RUN_WANT = [STATE["run_a"], STATE["run_b"]]
    ADOPT_TEXT = STATE["text_b"]
    SCENE_ADOPT = STATE["scene"]
    print(f"自建状态：project={PID} runs={RUN_WANT} "
          f"wall A={STATE['wall_a']}s B={STATE['wall_b']}s", flush=True)
else:
    # 判官 P1-9：本脚本会改文档/建 Take，绝不能再打在演示项目 188 上（默认拒绝，见 _acceptance）
    PID = require_scratch_project(http, Path(__file__).name, sys.argv)
    STATE = None
    ADOPT_TEXT = None
    SCENE_ADOPT = "S03"


def _flag_values(argv: list[str], flag: str) -> list[int]:
    """收集 `--run 237` 与 `--run=237` 两种写法。"""
    out = [int(a.split("=", 1)[1]) for a in argv if a.startswith(f"{flag}=")]
    out += [int(argv[i + 1]) for i, a in enumerate(argv) if a == flag and i + 1 < len(argv)]
    return out


RUN_WANT = RUN_WANT if BUILD else _flag_values(sys.argv, "--run")

SENTINEL = "先占个位。"   # 先把 S03 改成它，采纳断言才不是"改了个本来就对的字符串"


def _flag_text(argv: list[str], flag: str) -> str | None:
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return argv[i + 1]
    return None


EXPECT_B_TEXT = _flag_text(sys.argv, "--expect-b")


def _require_own_runs(pid: int, want: list[int]) -> None:
    """Take 冒烟要对**属于自己的 Run** 动手：写死 237/254 会把演示项目 188 的 Take 提升掉。"""
    items = http.get(f"/projects/{pid}/runs").json().get("items", [])
    have = {int(r["id"]) for r in items}
    missing = [r for r in want if r not in have]
    if missing:
        raise SystemExit(f"项目 {pid} 没有这些 Run：{missing}（现有 {sorted(have)[:6]}…）。"
                         "请用 --build 自建，或 --run <a> --run <b> 指向该自己项目里已完成 A–F 的两个 Run。")


def type_sticky(page, selector: str, text: str) -> None:
    page.click(selector)
    page.fill(selector, "")
    page.keyboard.type(text, delay=5)
    page.wait_for_timeout(300)


def run_a_slot() -> int:
    """页面把 items[0] 当作 A，items[1] 当作 B（`takes[0]` / `takes[1]`）。

    列表按 (评分, runId) 倒序排——所以**不能假设 A 就是先建的那个 Run**。
    老脚本写死 `RUN_WANT[0]` 恰好命中演示 188 的评分顺序，换个项目就会指错。
    """
    items = http.get(f"/projects/{PID}/takes").json()["items"]
    assert len(items) >= 2, items
    return int(items[0]["runId"])


def run_b_slot() -> int:
    return int(http.get(f"/projects/{PID}/takes").json()["items"][1]["runId"])


def expected_text_for(run_id: int) -> str:
    if BUILD:
        return {STATE["run_a"]: STATE["text_a"], STATE["run_b"]: STATE["text_b"]}[run_id]
    if EXPECT_B_TEXT:
        return EXPECT_B_TEXT
    raise SystemExit("手动模式请给 B 槽 Run 的快照文案：--expect-b <文本>（或直接用 --build）")


def set_timeline_scene(text: str) -> None:
    """直接改文档，制造"采纳前该场不是这个文本"的前置态。"""
    doc = http.get(f"/projects/{PID}/docs/timeline").json()
    content = doc["content"]
    for s in content["scenes"]:
        if s["id"] == SCENE_ADOPT:
            s["text"] = text
    r = http.put(f"/projects/{PID}/docs/timeline",
                 json={"content": content, "base_version": doc["version"], "author": "e2e-takes"})
    assert r.status_code == 200, r.text


def main() -> int:
    with sync_playwright() as pw:
        from app.config import detect_chrome
        browser = pw.chromium.launch(headless=True, executable_path=detect_chrome(), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(30000)
        assert len(RUN_WANT) >= 2, "需要两个 `--run <id>`（同一自建项目里已完成 A–F 的两次 Run）"
        _require_own_runs(PID, RUN_WANT)
        page.goto(f"{WEB}/takes?project={PID}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(f'[data-testid="take-{RUN_WANT[0]}"]', timeout=30000)
        page.wait_for_selector(f'[data-testid="take-{RUN_WANT[1]}"]', timeout=30000)
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

        # 元数据表单编辑的是 A 槽那个 Run（页面用 takes[0]），不是"先建的那个 Run"
        a_run = run_a_slot()
        type_sticky(page, '[data-testid="take-name"]', "A版-UI")
        page.locator('[data-testid="take-save-meta"]').click()
        page.wait_for_timeout(700)
        item = next(x for x in http.get(f"/projects/{PID}/takes").json()["items"] if x["runId"] == a_run)
        assert item["name"] == "A版-UI", item
        print(f"✓ 4. 元数据保存（A 槽 #{a_run}）", flush=True)

        page.locator(f'[data-testid="take-{RUN_WANT[0]}"]').get_by_role("button", name="提升").click()
        page.wait_for_timeout(600)
        assert http.get(f"/projects/{PID}/takes").json()["currentRunId"] == RUN_WANT[0]
        page.locator(f'[data-testid="take-{RUN_WANT[1]}"]').get_by_role("button", name="提升").click()
        page.wait_for_timeout(600)
        assert http.get(f"/projects/{PID}/takes").json()["currentRunId"] == RUN_WANT[1]
        print("✓ 5. 提升当前 Take（A→B）", flush=True)

        # 先把当前文档改成占位串，再采纳：否则"采纳后的文本"可能本来就是对的，断言是空的。
        b_run = run_b_slot()
        expect = expected_text_for(b_run)
        set_timeline_scene(SENTINEL)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(f'[data-testid="take-{b_run}"]', timeout=30000)
        page.locator("select").last.select_option(SCENE_ADOPT)
        page.locator('[data-testid="take-adopt"]').click()
        page.wait_for_timeout(800)
        doc = http.get(f"/projects/{PID}/docs/timeline").json()["content"]
        s3 = next(s for s in doc["scenes"] if s["id"] == SCENE_ADOPT)
        # 「B」槽位是哪一个 Run 由列表排序决定（评分→runId 倒序），所以期望值从**实际 B** 反查，
        # 不再写死字符串——写死 "B版三。" 正是本脚本当年只能跑在演示 188 上的原因。
        assert s3.get("text") == expect, (s3, expect)
        print(f"✓ 6. 采纳 B(#{b_run}) 的 {SCENE_ADOPT}：{SENTINEL} → {expect}", flush=True)

        browser.close()
    print("PASS: FR-38 Take 对比 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        if BUILD:
            destroy_project(http, PID, STATE["root"])
            print("自建状态已清理（--build 用完即删）")
