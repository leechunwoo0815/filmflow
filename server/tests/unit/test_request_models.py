"""P1-23：高风险写端点的请求模型必须把类型错误挡在 422，而不是落到服务层 500。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from sqlmodel import Session

from app.db import engine
from app.main import app

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


def test_gate_decide_full_approve_path_end_to_end(tmp_path):
    """P1-23 回归网：模型化端点必须走完整业务路径（不是只测 422）。

    本次 gate_decide 后半段残留 payload.get() 就是只测 422/404 漏掉的——
    任何模型化端点改完必须有一条 happy-path 断言。
    """
    import json as _json
    from pathlib import Path as _Path

    from app.engine import edges as edges_mod
    from app.models import NodeRun, Project, Run, Workflow
    from app.services import project_cleanup

    root = tmp_path / "gate-e2e"
    (root / "card").mkdir(parents=True)
    (root / "card" / "copy.txt").write_text("门禁回归。", encoding="utf-8")
    with Session(engine) as s:
        p = Project(name="gate-e2e", root=str(root))
        s.add(p)
        s.commit()
        s.refresh(p)
        wf = Workflow(project_id=p.id, graph_json={"meta": {"imported": True},
                                                   "nodes": [], "edges": []})
        s.add(wf)
        s.commit()
        s.refresh(wf)
        run = Run(workflow_id=wf.id, status="running")
        s.add(run)
        s.commit()
        s.refresh(run)
        # 上游全部 succeeded，门才允许签字（E07 无 D03/D05 的查看前置）
        ups = set()
        for g in ("E07", "F06", "B08", "A05"):
            for up, ty in edges_mod.UPSTREAM[g].items():
                if ty in ("data", "trigger"):
                    ups.add(up)
        for up in sorted(ups):
            s.add(NodeRun(run_id=run.id, node_id=up, status="succeeded",
                          cache_key="t", params_json={}))
        s.commit()
        run_id, pid, wf_id = run.id, p.id, wf.id
    try:
        with client() as c:
            # D03 有"已查看≥3 区域"前置，逐个人工门尝试到第一个可签的为止
            ok_gate, body = None, None
            for gate in ("E07", "F06", "B08", "A05"):
                r = c.post(f"/api/gates/{gate}/decide",
                           json={"run_id": run_id, "decision": "approved",
                                 "note": "回归", "author": "test"})
                if r.status_code == 200:
                    ok_gate, body = gate, r.json()
                    break
            assert ok_gate, f"所有人工门都未走到 happy path；最后响应 {r.text[:200]}"
            assert body.get("decision") == "approved", body
    finally:
        with Session(engine) as s:
            project_cleanup.delete_project(s, pid, remove_dir=False, force=True)
    import shutil
    shutil.rmtree(root, ignore_errors=True)


def test_validation_error_uses_api_error_envelope():
    """422 必须是 {code,message,details} 信封：前端 api.ts 读的就是这三个字段。"""
    from app.errors import ErrorCode

    with client() as c:
        r = c.post("/api/projects", json={"name": "", "root": "/tmp"}, headers=HEADERS)
        assert r.status_code == 422, r.text
        d = r.json()["detail"]
        assert d["code"] == ErrorCode.E_VALIDATION, d
        assert "name" in d["message"] and len(d["message"]) > 10, d
        assert d["details"]["errors"][0]["type"] == "string_too_short", d
        r2 = c.post("/api/projects/1/timeline/ops", json={}, headers=HEADERS)
        assert r2.status_code == 422 and r2.json()["detail"]["code"] == ErrorCode.E_VALIDATION, r2.text
        assert "op" in r2.json()["detail"]["message"], r2.text


def test_project_create_happy_path_via_route():
    """happy path：合法请求必须继续走通（历史上只测 422 让 gate_decide 的 500 溜了出去）。"""
    import shutil
    import uuid as _uuid

    from app.config import settings
    from pathlib import Path as _P
    # 必须在白名单内：tempfile 目录会被目录策略拒（那正是 B1 的防线）
    root = _P(settings.workspace_roots[0]).resolve() / f"judge-create-{_uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True)
    try:
        with client() as c:
            r = c.post("/api/projects", json={"name": "judge-create", "root": str(root)},
                       headers=HEADERS)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["project"]["id"] > 0 and body["run_id"] > 0
            docs = c.get(f"/api/projects/{body['project']['id']}/docs", headers=HEADERS)
            assert docs.status_code == 200 and len(docs.json()["items"]) >= 4, docs.text
            dele = c.delete(f"/api/projects/{body['project']['id']}",
                             params={"confirm": "true"}, headers=HEADERS)
            assert dele.status_code == 200, dele.text
            assert dele.json()["deleted"] == body["project"]["id"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
