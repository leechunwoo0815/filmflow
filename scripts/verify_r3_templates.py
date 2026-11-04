"""FR-37 模板/系列验收：另存项目模板、变量实例化、场景模板、diff/upgrade、小系列。

判官 §六 #9：模板源项目由 `_scratch_state.build_template_source()` 自建（2 场 + S01 图层
+ S01 音效），实例/系列项目自建自删；原先写死演示 211，还用裸 sqlite DELETE 清实例。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _acceptance import destroy
from _scratch_state import build_template_source, wait_api

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=180, trust_env=False)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def cleanup_projects(items: list[tuple[int, Path]]) -> None:
    """实例/系列项目一律走 DELETE 服务级联删除（裸 sqlite 会绕开外键与目录策略）。"""
    for pid, root in items:
        try:
            destroy(c, pid, root)
        except Exception as e:      # noqa: BLE001 - 清理失败不该掩盖验收结论
            print(f"! 清理项目 {pid} 失败：{e}", flush=True)


def main(source_id: int) -> int:
    stamp = str(int(time.time()))
    created_projects: list[tuple[int, Path]] = []
    template_ids: list[int] = []
    try:
        built = {t["id"] for t in req("GET", "/templates")["items"]}
        assert {"voice15", "opinion30", "product40"} <= built
        scenes = {t["id"] for t in req("GET", "/templates?kind=scene")["items"]}
        assert "builtin:scene-title" in scenes and "builtin:scene-cta" in scenes
        print("✓ 1. 内置项目/场景模板可见", flush=True)

        saved = req("POST", f"/projects/{source_id}/save-template", {
            "name": f"F37 验收模板 {stamp}", "description": "两场结构+资产",
            "copy": "{{title}}：{{number}} 个要点。第二句说明。"})["template"]
        template_ids.append(saved["templateId"])
        assert set(saved["variables"]) == {"title", "number"}
        assert saved["sceneCount"] == 2 and saved["content"]["assetShas"]
        print(f"✓ 2. 另存项目模板 {saved['id']} v{saved['version']}，变量 {saved['variables']}",
              flush=True)

        inst = req("POST", "/projects/from-template", {
            "templateId": saved["id"], "name": f"F37 验收实例 {stamp}",
            "variables": {"title": "验收", "number": 3}})
        pid = inst["project"]["id"]
        created_projects.append((pid, Path(inst["project"]["root"])))
        assert inst["templateVersion"] == 1
        script = req("GET", f"/projects/{pid}/docs/script")["content"]["text"]
        assert script == "验收：3 个要点。第二句说明。", script
        tl = req("GET", f"/projects/{pid}/docs/timeline")["content"]
        assert len(tl["scenes"]) == 2
        assert tl["scenes"][0]["layers"] and tl["scenes"][0]["audio_layers"]
        assets = req("GET", f"/assets?scope=project&projectId={pid}")["items"]
        assert {a["kind"] for a in assets} == {"image", "audio"}, assets
        lock = req("GET", f"/projects/{pid}/template-lock")["lock"]
        assert lock["templateId"] == saved["templateId"] and lock["version"] == saved["version"]
        print(f"✓ 3. 实例化 project {pid}：文案替换/结构/资产复制/模板锁", flush=True)

        st = req("POST", f"/projects/{source_id}/scenes/S01/save-template",
                 {"name": f"F37 场景 {stamp}", "description": "带资产"})["template"]
        template_ids.append(st["templateId"])
        before = req("GET", f"/projects/{pid}/docs/timeline")
        applied = req("POST", f"/projects/{pid}/timeline/scene-template", {
            "templateId": st["id"], "afterSceneId": tl["scenes"][0]["id"],
            "baseVersion": before["version"]})
        assert len(applied["content"]["scenes"]) == 3 and applied["sceneId"]
        print(f"✓ 4. 场景模板插入 {applied['sceneId']}", flush=True)

        versioned = req("POST", f"/templates/{saved['id']}/version", {
            "projectId": source_id,
            "copy": "{{title}}：{{number}} 个要点。第二句说明。"})["template"]
        assert versioned["version"] == 2
        diff = req("GET", f"/projects/{pid}/template-diff?templateId={saved['id']}")
        assert diff["diff"]["sceneCount"]["current"] == 3
        dry = req("POST", f"/projects/{pid}/template-upgrade",
                   {"templateId": saved["id"], "confirm": False})
        assert dry["applied"] is False
        up = req("POST", f"/projects/{pid}/template-upgrade",
                 {"templateId": saved["id"], "confirm": True})
        assert up["applied"] is True and up["lock"]["version"] == 2
        assert req("GET", f"/projects/{pid}/template-lock")["lock"]["version"] == 2
        print("✓ 5. 模板 v2 diff → 显式 confirm 升级；锁从 v1 升 v2", flush=True)

        series = req("POST", "/series/from-template", {
            "templateId": saved["id"], "name": f"F37 系列 {stamp}",
            "items": [{"name": f"F37 系列 {stamp} A", "variables": {"title": "A", "number": 1}},
                      {"name": f"F37 系列 {stamp} B", "variables": {"title": "B", "number": 2}}]})
        assert series["created"] == 2 and series["failed"] == 0, series
        for item in series["items"]:
            created_projects.append((item["project"]["id"], Path(item["project"]["root"])))
            assert req("GET", f"/projects/{item['project']['id']}/docs/script")["content"]["text"] \
                .startswith(("A：1", "B：2"))
        print("✓ 6. 系列 2 项同步创建；失败项隔离字段已返回", flush=True)
        print("PASS: FR-37 模板/系列验收通过")
        return 0
    finally:
        cleanup_projects(created_projects)
        for tid in template_ids:
            r = c.delete(f"/templates/saved:{tid}")
            if r.status_code >= 400:
                print(f"! 模板 {tid} 删除返回 {r.status_code}（可能已被级联清理）", flush=True)


if __name__ == "__main__":
    wait_api()
    # 模板源项目必须自带「图层 + 音效」资产引用，所以由 builder 造，而不是借演示 211
    src = build_template_source(c, "templates-verify")
    try:
        sys.exit(main(src["pid"]))
    finally:
        destroy(c, src["pid"], src["root"])
        print("模板源项目已清理")
