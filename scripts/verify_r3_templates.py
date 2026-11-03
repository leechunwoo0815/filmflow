"""FR-37 模板/系列验收：另存项目模板、变量实例化、场景模板、diff/upgrade、小系列。"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7860/api"
SOURCE = 211
c = httpx.Client(base_url=BASE, timeout=180, trust_env=False)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def cleanup_projects(ids: list[int]) -> None:
    db = Path.home() / ".filmflow/filmflow.db"
    con = sqlite3.connect(db)
    try:
        for pid in ids:
            proj = con.execute("select root from project where id=?", (pid,)).fetchone()
            if not proj:
                continue
            root = Path(proj[0])
            assets = con.execute("select path from asset where project_id=?", (pid,)).fetchall()
            con.execute("delete from asset where project_id=?", (pid,))
            con.execute("delete from docrevision where doc_id in "
                        "(select id from projectdoc where project_id=?)", (pid,))
            con.execute("delete from projectdoc where project_id=?", (pid,))
            con.execute("delete from stylepick where project_id=?", (pid,))
            runs = con.execute("select id from run where workflow_id in "
                               "(select id from workflow where project_id=?)", (pid,)).fetchall()
            run_ids = [r[0] for r in runs]
            for rid in run_ids:
                con.execute("delete from artifact where run_id=?", (rid,))
                con.execute("delete from approval where run_id=?", (rid,))
                con.execute("delete from event where run_id=?", (rid,))
                con.execute("delete from noderun where run_id=?", (rid,))
                con.execute("delete from scenestate where run_id=?", (rid,))
                con.execute("delete from job where run_id=?", (rid,))
            con.execute("delete from run where workflow_id in "
                        "(select id from workflow where project_id=?)", (pid,))
            con.execute("delete from workflowversion where workflow_id in "
                        "(select id from workflow where project_id=?)", (pid,))
            con.execute("delete from workflow where project_id=?", (pid,))
            con.execute("delete from project where id=?", (pid,))
            con.execute("delete from draft where payload_json like ?", (f"%{root}%",))
            for (p,) in assets:
                Path(p).unlink(missing_ok=True)
            shutil.rmtree(root, ignore_errors=True)
        con.commit()
    finally:
        con.close()


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    stamp = str(int(time.time()))
    created_projects: list[int] = []
    template_ids: list[int] = []
    try:
        built = {t["id"] for t in req("GET", "/templates")["items"]}
        assert {"voice15", "opinion30", "product40"} <= built
        scenes = {t["id"] for t in req("GET", "/templates?kind=scene")["items"]}
        assert "builtin:scene-title" in scenes and "builtin:scene-cta" in scenes
        print("✓ 1. 内置项目/场景模板可见", flush=True)

        saved = req("POST", f"/projects/{SOURCE}/save-template", {
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
        created_projects.append(pid)
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

        st = req("POST", f"/projects/{SOURCE}/scenes/S01/save-template",
                 {"name": f"F37 场景 {stamp}", "description": "带资产"})["template"]
        template_ids.append(st["templateId"])
        before = req("GET", f"/projects/{pid}/docs/timeline")
        applied = req("POST", f"/projects/{pid}/timeline/scene-template", {
            "templateId": st["id"], "afterSceneId": tl["scenes"][0]["id"],
            "baseVersion": before["version"]})
        assert len(applied["content"]["scenes"]) == 3 and applied["sceneId"]
        print(f"✓ 4. 场景模板插入 {applied['sceneId']}", flush=True)

        versioned = req("POST", f"/templates/{saved['id']}/version", {
            "projectId": SOURCE,
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
            created_projects.append(item["project"]["id"])
            assert req("GET", f"/projects/{item['project']['id']}/docs/script")["content"]["text"] \
                .startswith(("A：1", "B：2"))
        print("✓ 6. 系列 2 项同步创建；失败项隔离字段已返回", flush=True)
        print("PASS: FR-37 模板/系列验收通过")
        return 0
    finally:
        cleanup_projects(created_projects)
        for tid in template_ids:
            try:
                c.delete(f"/templates/saved:{tid}")
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
