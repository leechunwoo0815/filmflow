"""FR-36 资产库验收：50 图去重/引用计数/删除保护/替换/缺资产阻断/字体缺字/全局复用。"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import httpx
from PIL import Image

BASE = "http://127.0.0.1:7860/api"
PID = 211
c = httpx.Client(base_url=BASE, timeout=180, trust_env=False)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r


def png_b64(color: tuple[int, int, int], size=(24, 14)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def upload(scope: str, name: str, data: str, **extra) -> dict:
    payload = {"scope": scope, "filename": f"{name}.png", "name": name, "data": data,
               "license": {"source": "自制", "type": "CC0"}, **extra}
    if scope == "project":
        payload["projectId"] = PID
    return req("POST", "/assets", payload).json()


def delete_asset(aid: int) -> None:
    try:
        req("DELETE", f"/assets/{aid}")
    except RuntimeError as e:
        if "404" not in str(e):
            raise


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    tl = req("GET", f"/projects/{PID}/docs/timeline").json()
    version = tl["version"]
    scenes = tl["content"]["scenes"]
    s1, s2 = scenes[0]["id"], scenes[1]["id"]
    before_layers = len(scenes[0].get("layers") or [])
    created: list[int] = []

    # 1. 50 张图，两种内容各重复 25 次
    color_a = (220, 40, 40)
    color_b = (30, 90, 210)
    data_a, data_b = png_b64(color_a), png_b64(color_b)
    new = dup = 0
    ids: dict[str, int] = {}
    for i in range(50):
        color, data = (color_a, data_a) if i % 2 == 0 else (color_b, data_b)
        r = upload("project", f"f36-{color[0]}-{i}", data)
        ids.setdefault(str(color), r["asset"]["id"])
        if r["deduped"]:
            dup += 1
        else:
            new += 1
            created.append(r["asset"]["id"])
    assert (new, dup) == (2, 48), (new, dup)
    assert len(ids) == 2
    print(f"✓ 1. 50 图去重：新增 {new} / 去重 {dup}", flush=True)

    # 2. 引用计数 + 使用处
    old_id = ids[str(color_a)]
    old_created = old_id in created
    old_sha = next(a["sha256"] for a in req("GET", f"/assets?scope=project&projectId={PID}").json()["items"]
                   if a["id"] == old_id)
    r = req("POST", f"/projects/{PID}/timeline/ops", {
        "op": "add_image", "baseVersion": version, "sceneId": s1,
        "assetSha": old_sha, "box": [640, 300, 640, 360], "z": 20,
        "fit": "cover", "opacity": 0.9, "name": "F36 验收图"})
    version = r.json()["version"]
    layer_id = r.json()["content"]["scenes"][0]["layers"][-1]["id"]
    listed = req("GET", f"/assets?scope=project&projectId={PID}").json()["items"]
    item = next(a for a in listed if a["id"] == old_id)
    assert item["refCount"] == 1 and item["usages"][0]["sceneId"] == s1
    assert item["usages"][0]["layerId"] == layer_id
    print("✓ 2. 引用计数=1，使用处指向 S01/" + layer_id, flush=True)

    # 3. 删除被引用资产阻断
    d = c.delete(f"/assets/{old_id}")
    assert d.status_code == 409, d.text
    body = d.json()["detail"]
    assert body["code"] == "E_ASSET_IN_USE"
    assert body["details"]["usages"][0]["sceneId"] == s1
    print("✓ 3. 删除被引用资产返回 E_ASSET_IN_USE + 使用处", flush=True)

    # 4. 替换只改使用该图的场景
    rep = upload("project", "f36-replacement", png_b64((20, 160, 80)))
    if not rep["deduped"]:
        created.append(rep["asset"]["id"])
    r = req("POST", f"/assets/{old_id}/replace", {"assetId": rep["asset"]["id"]})
    assert r.json()["affectedScenes"] == [s1], r.text
    assert all(p["scenes"] == [s1] for p in r.json()["projects"])
    tl = req("GET", f"/projects/{PID}/docs/timeline").json()
    version = tl["version"]
    used = [l for l in tl["content"]["scenes"][0]["layers"] if l["id"] == layer_id][0]
    assert used["assetSha"] == rep["asset"]["sha256"]
    assert len(tl["content"]["scenes"][1].get("layers") or []) == 0
    if old_created:
        req("DELETE", f"/assets/{old_id}")
    print("✓ 4. 替换只标记 S01；旧资产可删除", flush=True)

    # 5. 缺失资产在渲染前阻断
    r = req("POST", f"/projects/{PID}/timeline/ops", {
        "op": "add_image", "baseVersion": version, "sceneId": s1,
        "assetSha": "0" * 64, "box": [100, 100, 200, 200]})
    version = r.json()["version"]
    bogus_id = r.json()["content"]["scenes"][0]["layers"][-1]["id"]
    pv = c.post(f"/projects/{PID}/preview/still", json={
        "sceneId": s1, "time": 0.5, "profile": "draft", "watermark": True})
    assert pv.status_code == 409, (pv.status_code, pv.text[:300])
    assert pv.json()["detail"]["code"] == "E_ASSET_MISSING"
    r = req("POST", f"/projects/{PID}/timeline/ops", {
        "op": "remove_layer", "baseVersion": version, "sceneId": s1, "layerId": bogus_id})
    version = r.json()["version"]
    print("✓ 5. 缺资产预览 409 E_ASSET_MISSING（给重新链接提示）", flush=True)

    # 6. 字体缺字检查
    font = Path("/Users/litianyu/cc-projects/ai-v/filmflow/web/node_modules/.pnpm/"
                "next@15.5.28_@types+node@22.20.5_react-dom@19.3.1_react@19.3.1__react@19.3.1/"
                "node_modules/next/dist/compiled/@vercel/og/noto-sans-v27-latin-regular.ttf")
    if font.exists():
        data = "data:font/ttf;base64," + base64.b64encode(font.read_bytes()).decode()
        fr = req("POST", "/assets", {"scope": "project", "projectId": PID,
                                     "filename": "f36-latin.ttf", "name": "F36 Latin",
                                     "data": data, "license": {"source": "Next.js", "type": "OFL"}}).json()
        if not fr["deduped"]:
            created.append(fr["asset"]["id"])
        chk = req("POST", f"/assets/{fr['asset']['id']}/font-check", {"text": "ABC 中文"}).json()
        assert not chk["ok"] and chk["missingCount"] == 2, chk
        print("✓ 6. 字体覆盖：中文缺 2 字", flush=True)
    else:
        print("! 6. 跳过字体检查（Latin 测试字体不存在）", flush=True)

    # 7. 全局资产按 sha 复用，不复制
    g = upload("global", "f36-global", png_b64((90, 30, 180)))
    if not g["deduped"]:
        created.append(g["asset"]["id"])
    shared = upload("project", "f36-global-copy", png_b64((90, 30, 180)))
    assert shared["deduped"] is True and shared["asset"]["id"] == g["asset"]["id"]
    assert shared["asset"]["scope"] == "global"
    print("✓ 7. 项目引用全局资产复用同一条记录", flush=True)

    # 8. 清理，保持演示项目时间轴回到脚本执行前
    r = req("POST", f"/projects/{PID}/timeline/ops", {
        "op": "remove_layer", "baseVersion": version, "sceneId": s1, "layerId": layer_id})
    version = r.json()["version"]
    assert len(r.json()["content"]["scenes"][0].get("layers") or []) == before_layers
    for aid in created:
        delete_asset(aid)
    print("✓ 8. 清理测试图层/资产；时间轴图层数恢复", flush=True)
    print("PASS: FR-36 资产库验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
