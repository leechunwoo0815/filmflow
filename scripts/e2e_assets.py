"""FR-36 UI 冒烟：资产上传/列表/字体缺字/时间轴插入/引用计数/删除保护。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from playwright.sync_api import sync_playwright  # noqa: E402

WEB = "http://localhost:3000"
API = "http://127.0.0.1:7860/api"
PID = 211
http = httpx.Client(base_url=API, timeout=120, trust_env=False)
stamp = str(int(time.time()))


def cleanup(image_sha: str, asset_ids: list[int], layer_id: str | None) -> None:
    try:
        tl = http.get(f"/projects/{PID}/docs/timeline").json()
        if layer_id:
            for scene in tl["content"]["scenes"]:
                if any(l.get("id") == layer_id for l in scene.get("layers") or []):
                    http.post(f"/projects/{PID}/timeline/ops", json={
                        "op": "remove_layer", "baseVersion": tl["version"],
                        "sceneId": scene["id"], "layerId": layer_id})
                    break
        for aid in asset_ids:
            http.delete(f"/assets/{aid}")
    except Exception as e:
        print("cleanup warning:", e, flush=True)


def main() -> int:
    png = Path(f"/tmp/f36-e2e-{stamp}.png")
    Image.new("RGB", (240, 140), (240, 90, 40)).save(png, "PNG")
    wav = Path(f"/tmp/f36-e2e-{stamp}.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=660:duration=0.3", "-ac", "1", "-ar", "48000", str(wav)],
                   check=True)
    from fontTools.ttLib import TTFont
    font_src = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    font = Path(f"/tmp/f36-e2e-font-{stamp}.ttf")
    ft = TTFont(str(font_src))
    ft["name"].setName(f"F36 E2E {stamp}", 1, 3, 1, 0x409)
    ft.save(font)
    font_sha = hashlib.sha256(font.read_bytes()).hexdigest()
    image_name, sfx_name, font_name = png.stem, wav.stem, f"E2E字体{stamp}"
    asset_ids: list[int] = []
    layer_id = None
    image_sha = ""
    with sync_playwright() as pw:
        from app.config import detect_chrome
        b = pw.chromium.launch(headless=True, executable_path=detect_chrome(),
                               args=["--no-sandbox"])
        page = b.new_page(viewport={"width": 1500, "height": 1000})
        page.set_default_timeout(30000)
        try:
            page.goto(f"{WEB}/assets?project={PID}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('div[data-testid^="asset-"]', timeout=30000)
            page.set_input_files('[data-testid="asset-file-input"]', [str(png), str(wav)])
            page.wait_for_selector(f'text={image_name}', timeout=30000)
            page.wait_for_selector(f'text={sfx_name}', timeout=30000)
            items = http.get(f"/assets?scope=project&projectId={PID}").json()["items"]
            img = next(a for a in items if a["name"] == image_name and a["kind"] == "image")
            sfx = next(a for a in items if a["name"] == sfx_name and a["kind"] == "audio")
            asset_ids += [img["id"], sfx["id"]]
            image_sha = img["sha256"]
            print("✓ 1. UI 上传图片/SFX", flush=True)

            assert font.exists(), font
            page.get_by_placeholder("自制 / CC0 / 购买").fill("system")
            page.get_by_placeholder("CC0 / OFL / 商业授权").fill("system")
            page.set_input_files('[data-testid="asset-file-input"]', [str(font)])
            font_item = None
            for _ in range(60):
                font_item = next((a for a in http.get(
                    f"/assets?scope=project&projectId={PID}").json()["items"]
                                  if a["sha256"] == font_sha), None)
                if font_item:
                    break
                time.sleep(0.25)
            assert font_item, "字体上传未完成"
            http.patch(f"/assets/{font_item['id']}", json={"name": font_name})
            asset_ids.append(font_item["id"])
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(f'text={font_name}', timeout=30000)
            card = page.locator('div[data-testid^="asset-"]').filter(has_text=font_name).first
            card.get_by_text("使用处").click()
            card.locator("textarea").fill("ABC 中文")
            card.get_by_text("检查缺字").click()
            page.wait_for_selector("text=缺 2 字", timeout=10000)
            print("✓ 2. 字体缺字在 UI 标红（缺 2 字）", flush=True)

            page.goto(f"{WEB}/timeline?project={PID}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('[data-testid="scene-block-S01"]', timeout=30000)
            page.locator('[data-testid="scene-block-S01"]').click()
            page.wait_for_timeout(800)
            page.locator(f'[data-testid="asset-insert-{img["id"]}"]').click()
            page.wait_for_timeout(1500)
            tl = http.get(f"/projects/{PID}/docs/timeline").json()
            layers = [l for s in tl["content"]["scenes"] for l in s.get("layers") or []
                      if l.get("assetSha") == image_sha]
            assert layers, tl["content"]["scenes"][0]
            layer_id = layers[0]["id"]
            print("✓ 3. 时间轴插入图片图层", flush=True)

            page.goto(f"{WEB}/assets?project={PID}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(f'div[data-testid="asset-{img["id"]}"]', timeout=30000)
            card = page.locator(f'div[data-testid="asset-{img["id"]}"]')
            card.locator('[data-testid="asset-ref-count"]').wait_for(timeout=10000)
            assert card.locator('[data-testid="asset-ref-count"]').inner_text().strip() == "引用 1"
            page.on("dialog", lambda d: d.accept())
            card.get_by_text("删除").click()
            page.wait_for_selector("text=不能删除", timeout=10000)
            print("✓ 4. 引用计数=1；UI 删除被阻断并列出使用处", flush=True)
            page.screenshot(path="/tmp/ff_e2e_assets.png")
        finally:
            b.close()
    cleanup(image_sha, asset_ids, layer_id)
    print("PASS: FR-36 资产库 UI 冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
