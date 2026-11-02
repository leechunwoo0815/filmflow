"""FR-25 API：文档版本、409 冲突、回滚、新项目 task.json 只读。"""
import json
import shutil
import uuid
from pathlib import Path

import httpx
import pytest

BASE = "http://127.0.0.1:7860/api"


def _alive() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=3, trust_env=False).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _alive(), reason="API 服务未运行（先 ./dev.sh 或 uvicorn）")


@pytest.fixture()
def client():
    with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as c:
        yield c


def _req(c, method, path, payload=None):
    r = c.request(method, path, json=payload)
    return r


def test_docs_versions_conflict_restore_and_task_readonly(client):
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"it-docs-{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True)
    try:
        p = _req(client, "POST", "/projects", {"name": "it-docs", "root": str(root)}).json()
        pid = p["project"]["id"]
        timeline = _req(client, "GET", f"/projects/{pid}/docs/timeline").json()
        assert timeline["version"] == 0 and timeline["content"]["scenes"]
        saved = _req(client, "PUT", f"/projects/{pid}/docs/timeline",
                     {"content": timeline["content"], "base_version": 0, "author": "test"}).json()
        assert saved["version"] == 1
        stale = _req(client, "PUT", f"/projects/{pid}/docs/timeline",
                     {"content": timeline["content"], "base_version": 0, "author": "test"})
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "E_DOC_CONFLICT"
        versions = _req(client, "GET", f"/projects/{pid}/docs/timeline/versions").json()
        assert versions["current_version"] == 1 and versions["items"][0]["version"] == 1
        diff = _req(client, "GET", f"/projects/{pid}/docs/timeline/diff?from_version=1&to_version=1").json()
        assert diff["diff"] == []
        restored = _req(client, "POST", f"/projects/{pid}/docs/timeline/restore",
                        {"version": 1, "author": "test"}).json()
        assert restored["version"] == 2
        ro = _req(client, "PUT", f"/projects/{pid}/task", {"task": {"phase": "card", "actions": []}})
        assert ro.status_code == 409
        assert ro.json()["detail"]["code"] == "E_DOC_READONLY"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_import_persists_meta_and_params(client):
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"it-import-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True)
    try:
        (root / "card" / "task.json").write_text(json.dumps(
            {"fps": 24, "width": 1920, "height": 1080, "film": {"duration": 5, "frames": 120},
             "scenes": [{"id": "S01", "start": 0, "end": 5, "meaning": "导入场景",
                         "operation": "保留", "last_text_at": 0, "read_seconds": 1}],
             "events": []}), encoding="utf-8")
        r = _req(client, "POST", "/projects/import", {"root": str(root)}).json()
        wf = _req(client, "GET", f"/workflows/{r['workflow_id']}").json()
        assert wf["graph_json"]["meta"]["imported"] is True
        assert wf["graph_json"]["params"]["B06"] == {"mode": "import"}
        assert wf["graph_json"]["params"]["C01"] == {"engine_id": "riso"}
        tl = _req(client, "GET", f"/projects/{r['project']['id']}/docs/timeline").json()
        assert tl["imported"] is True
        assert [s["id"] for s in tl["content"]["scenes"]] == ["S01"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
