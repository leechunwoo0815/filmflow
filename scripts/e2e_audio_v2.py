"""FR-35 UI 冒烟：Take/A-B/处理/拍点/拼接/响度设置。

只跑自建 scratch 项目：`--project <id>`（先 `python scripts/_acceptance.py --create audio-e2e` 并上传两条 Take）；
指向演示项目 211 会被直接拒绝（判官 P1-9）。"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import sync_playwright

WEB = "http://localhost:3000"
API = "http://127.0.0.1:7860/api"
http = httpx.Client(base_url=API, timeout=60, trust_env=False)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _acceptance import require_scratch_project

# 判官 P1-9：会写 timeline/mix/license，绝不能再打在演示项目 211 上
PID = require_scratch_project(http, Path(__file__).name, sys.argv)


def main() -> int:
    audio = http.get(f"/projects/{PID}/audio").json()
    takes = [t for t in audio["takes"] if t["kind"] == "voice"]
    assert len(takes) >= 2, takes
    assert any(t.get("processedFile") for t in takes)
    with sync_playwright() as pw:
        from app.config import detect_chrome
        b = pw.chromium.launch(headless=True, executable_path=detect_chrome(), args=["--no-sandbox"])
        page = b.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(30000)
        page.goto(f"{WEB}/audio?project={PID}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid^="take-"]', timeout=30000)
        assert page.locator('[data-testid^="take-"]').count() >= 2
        assert page.locator("audio").count() >= 2
        assert page.get_by_text("已处理").count() >= 1
        print("✓ 1. Take/A-B 播放器/已处理标记", flush=True)

        page.locator('[data-testid="audio-onsets"]').click()
        page.wait_for_timeout(1200)
        assert page.get_by_text("onsets").count() >= 1
        onsets = http.get(f"/projects/{PID}/audio/markers").json()["onsets"]
        assert len(onsets) >= 1, onsets
        print(f"✓ 2. 检测拍点 {len(onsets)}", flush=True)

        page.locator('[data-testid="audio-concat"]').click()
        page.wait_for_timeout(1200)
        assert page.get_by_text("拼接预览").count() >= 1
        print("✓ 3. 场景 Take 拼接试听", flush=True)

        page.locator('[data-testid="audio-loudness"]').select_option("-16")
        page.locator('[data-testid="audio-mix-save"]').click()
        page.wait_for_timeout(500)
        assert http.get(f"/projects/{PID}/audio/mix").json()["targetLufs"] == -16.0
        page.locator('[data-testid="audio-loudness"]').select_option("-14")
        page.locator('[data-testid="audio-mix-save"]').click()
        page.wait_for_timeout(500)
        assert http.get(f"/projects/{PID}/audio/mix").json()["targetLufs"] == -14.0
        print("✓ 4. 响度预设保存", flush=True)

        b.close()
    print("PASS: FR-35 音频 v2 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
