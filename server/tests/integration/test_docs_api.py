"""FR-25 API：文档版本、409 冲突、回滚、新项目 task.json 只读。"""
import json
import shutil
from pathlib import Path


def _req(client, method, path, payload=None):
    r = client.request(method, path, json=payload)
    return r


def _json(client, method, path, payload=None):
    return _req(client, method, path, payload).json()


def test_docs_versions_conflict_restore_and_task_readonly(api_client, project_root):
    p = _json(api_client, "POST", "/projects", {"name": "it-docs", "root": str(project_root)})
    pid = p["project"]["id"]
    timeline = _json(api_client, "GET", f"/projects/{pid}/docs/timeline")
    assert timeline["version"] == 0 and timeline["content"]["scenes"]
    saved = _json(api_client, "PUT", f"/projects/{pid}/docs/timeline",
                  {"content": timeline["content"], "base_version": 0, "author": "test"})
    assert saved["version"] == 1
    stale = _req(api_client, "PUT", f"/projects/{pid}/docs/timeline",
                 {"content": timeline["content"], "base_version": 0, "author": "test"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "E_DOC_CONFLICT"
    versions = _json(api_client, "GET", f"/projects/{pid}/docs/timeline/versions")
    assert versions["current_version"] == 1 and versions["items"][0]["version"] == 1
    diff = _json(api_client, "GET",
                 f"/projects/{pid}/docs/timeline/diff?from_version=1&to_version=1")
    assert diff["diff"] == []
    restored = _json(api_client, "POST", f"/projects/{pid}/docs/timeline/restore",
                     {"version": 1, "author": "test"})
    assert restored["version"] == 2
    ro = _req(api_client, "PUT", f"/projects/{pid}/task",
              {"task": {"phase": "card", "actions": []}})
    assert ro.status_code == 409
    assert ro.json()["detail"]["code"] == "E_DOC_READONLY"


def test_import_persists_meta_and_params(api_client, project_root):
    (project_root / "card").mkdir(parents=True)
    (project_root / "card" / "task.json").write_text(json.dumps(
        {"fps": 24, "width": 1920, "height": 1080, "film": {"duration": 5, "frames": 120},
         "scenes": [{"id": "S01", "start": 0, "end": 5, "meaning": "导入场景",
                     "operation": "保留", "last_text_at": 0, "read_seconds": 1}],
         "events": []}), encoding="utf-8")
    r = _json(api_client, "POST", "/projects/import", {"root": str(project_root)})
    wf = _json(api_client, "GET", f"/workflows/{r['workflow_id']}")
    assert wf["graph_json"]["meta"]["imported"] is True
    assert wf["graph_json"]["params"]["B06"] == {"mode": "import"}
    assert wf["graph_json"]["params"]["C01"] == {"engine_id": "riso"}
    tl = _json(api_client, "GET", f"/projects/{r['project']['id']}/docs/timeline")
    assert tl["imported"] is True
    assert [s["id"] for s in tl["content"]["scenes"]] == ["S01"]
