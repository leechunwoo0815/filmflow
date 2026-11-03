"""P1-23：高风险写端点的请求模型必须把类型错误挡在 422，而不是落到服务层 500。"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.main import app  # noqa: E402

HEADERS = {"Origin": "http://127.0.0.1:3000"}


def client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def test_project_create_requires_name_and_root():
    with client() as c:
        assert c.post("/api/projects", json={}, headers=HEADERS).status_code == 422
        assert c.post("/api/projects", json={"name": "x"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects", json={"name": "x", "root": 123},
                      headers=HEADERS).status_code == 422


def test_doc_put_rejects_non_object_content_and_version():
    with client() as c:
        bad = c.put("/api/projects/1/docs/timeline",
                    json={"content": "文本不是对象", "base_version": 1}, headers=HEADERS)
        assert bad.status_code == 422
        assert c.put("/api/projects/1/docs/timeline",
                     json={"content": {}, "base_version": "v1"},
                     headers=HEADERS).status_code == 422


def test_doc_restore_requires_integer_version():
    with client() as c:
        assert c.post("/api/projects/1/docs/timeline/restore",
                      json={"version": "abc"}, headers=HEADERS).status_code == 422


def test_timeline_ops_require_op_string():
    with client() as c:
        assert c.post("/api/projects/1/timeline/ops", json={},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/timeline/ops", json={"op": ""},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/timeline/ops", json={"op": 5},
                      headers=HEADERS).status_code == 422


def test_asset_endpoints_validate_payload():
    with client() as c:
        assert c.post("/api/assets", json={"scope": "global"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/assets", json={"scope": "wrong", "filename": "a.png",
                                           "data": "AAA"}, headers=HEADERS).status_code == 422
        assert c.post("/api/assets", json={"scope": "global", "filename": "a.png",
                                           "data": ""}, headers=HEADERS).status_code == 422
        assert c.patch("/api/assets/1", json={"archived": "不是布尔"},
                       headers=HEADERS).status_code == 422
        assert c.post("/api/assets/1/replace", json={"assetId": "x"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/assets/1/replace", json={"assetId": 0},
                      headers=HEADERS).status_code == 422


def test_qa_endpoints_require_ids():
    with client() as c:
        assert c.post("/api/projects/1/qa/fix", json={"action": "scale_text"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/qa/fix", json={"issueId": "", "action": "x"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/qa/undo", json={"fixId": ""},
                      headers=HEADERS).status_code == 422


def test_validation_errors_do_not_leak_stack():
    with client() as c:
        r = c.post("/api/assets", json={"scope": "global", "filename": "a.png", "data": 7},
                   headers=HEADERS)
        assert r.status_code == 422
        body = r.text
        assert "Traceback" not in body and "string_type" in body


# ---------- P1-23 第二批（交付/预览/门禁/promote/档位/任务卡/音频） ----------

def _post_422(c, url, body):
    r = c.post(url, json=body)
    assert r.status_code == 422, (r.status_code, r.text[:200])
    assert "detail" in r.json()


def test_batch2_models_reject_bad_types():
    with client() as c:
        _post_422(c, "/api/projects/1/delivery", {"runId": "不是数字"})
        _post_422(c, "/api/projects/1/preview/still", {"sceneId": "S01", "time": "12点"})
        _post_422(c, "/api/projects/1/preview/segment",
                  {"sceneId": "S01", "start": "a", "end": 1.0})
        _post_422(c, "/api/gates/D03/decide", {"run_id": 1, "decision": "随便"})
        _post_422(c, "/api/projects/1/audio/alignment", {"segments": "不是数组"})


def test_batch2_models_accept_legacy_aliases():
    with client() as c:
        # 门禁双键名兼容（runId / run_id）在模型层不报 422（服务层负责 404）
        r = c.post("/api/gates/D03/decide", json={"runId": 999999, "decision": "approved"})
        assert r.status_code == 404, r.status_code
        # 预览蛇形别名 scene_id 同样不 422（进入服务层）
        r = c.post("/api/projects/999999/preview/still",
                   json={"scene_id": "S01"})
        assert r.status_code == 404, r.status_code
