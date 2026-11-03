"""向导 materialize 全流程集成测试（T05/T10 验收）：drafts → pick → materialize → 画布/门/引擎门。"""
import json


def _req(client, method, path, payload=None):
    return client.request(method, path, json=payload).json()


def _req_status(client, method, path, payload=None):
    r = client.request(method, path, json=payload)
    return r.status_code, r.json()


def test_wizard_materialize_full(api_client, project_root):
    d = _req(api_client, "POST", "/drafts", {"name": "集成测试项目", "step": 1})
    styles = _req(api_client, "GET", "/styles?chips=可生产&limit=5")
    assert styles["items"], "可生产集合为空——引擎未登记？"
    primary = styles["items"][0]["id"]
    _req(api_client, "PATCH", f"/drafts/{d['id']}",
         {"step": 5,
          "payload": {"root": str(project_root),
                      "copy": "一条关于谣言核查的测试文案。真相经得起第二次查看。",
                      "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
                      "pick": {"primary": primary, "alternates": [], "reason": "集成测试"}}})
    r = _req(api_client, "POST", f"/drafts/{d['id']}/materialize", {})
    assert r["run_id"] > 0, r
    g = _req(api_client, "GET", f"/runs/{r['run_id']}/graph")
    assert len(g["nodes"]) == 46 and len(g["edges"]) == 93
    wf = _req(api_client, "GET", f"/workflows/{r['workflow_id']}")
    assert wf["graph_json"]["meta"]["style_decision"]["primary"] == primary
    assert wf["graph_json"]["params"]["A01"]["path"].endswith("copy.txt")
    gates = _req(api_client, "GET", f"/gates/{r['run_id']}/pending")
    assert all(p["gate"] != "A05" for p in gates["items"])
    sd = json.loads((project_root / "card" / "style_decision.json").read_text(encoding="utf-8"))
    assert sd["primary"] == primary
    prof = json.loads((project_root / "project.profile.json").read_text(encoding="utf-8"))
    assert prof["frames"] == round(prof["duration"] * prof["fps"])


def test_engine_unavailable_blocks_materialize(api_client, project_root):
    """夹具 11：选引擎未就绪族 → E_ENGINE_UNAVAILABLE。"""
    d = _req(api_client, "POST", "/drafts", {"name": "引擎未就绪", "step": 3,
                                             "payload": {"copy": "测试文案。",
                                                         "pick": {"primary": "K1"}}})
    _req(api_client, "PATCH", f"/drafts/{d['id']}",
         {"payload": {"root": str(project_root), "copy": "测试文案。",
                      "pick": {"primary": "K1"}}})
    status, body = _req_status(api_client, "POST", f"/drafts/{d['id']}/materialize", {})
    assert status >= 400, f"应当被阻断，实际返回 {body}"
    assert body.get("detail", {}).get("code") == "E_ENGINE_UNAVAILABLE", body
