"""向导 materialize 全流程集成测试（T05/T10 验收）：drafts → pick → materialize → 画布/门/引擎门。"""
import json
import sys
import httpx
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

BASE = "http://127.0.0.1:7860/api"
_http = httpx.Client(trust_env=False, timeout=120)

pytestmark = pytest.mark.skipif(
    not _server_up() if (_server_up := None) else False, reason=""
)  # placeholder replaced below


def _server_alive() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=3, trust_env=False)  # 本机直连，不吃代理
        return r.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(not (Path.home() / "Documents" / "fy-style-library" /
                            "代码动画_341种风格提示词").is_dir(), reason="风格库不存在"),
    pytest.mark.skipif(not _server_alive(), reason="API 服务未运行（先 ./dev.sh 或 uvicorn）"),
]


def _req(method: str, path: str, payload: dict | None = None) -> dict:
    r = _http.request(method, f"{BASE}{path}", json=payload)
    return r.json()


def _req_status(method: str, path: str, payload: dict | None = None):
    r = _http.request(method, f"{BASE}{path}", json=payload)
    return r.status_code, r.json()


def test_wizard_materialize_full():
    # 1 建草稿
    d = _req("POST", "/drafts", {"name": "集成测试项目", "step": 1})
    # 2 选一个可生产风格（可生产集合非空）
    styles = _req("GET", "/styles?chips=可生产&limit=5")
    assert styles["items"], "可生产集合为空——引擎未登记？"
    primary = styles["items"][0]["id"]
    # 4 materialize（合法 pick；残缺风格不可主选由 test_engine_unavailable 覆盖）
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"it-wizard-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"step": 5,
         "payload": {"root": str(root), "copy": "一条关于谣言核查的测试文案。真相经得起第二次查看。",
                     "profile": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
                     "pick": {"primary": primary, "alternates": [], "reason": "集成测试"}}})
    r = _req("POST", f"/drafts/{d['id']}/materialize", {})
    assert r["run_id"] > 0, r
    # 5 画布：46 节点
    g = _req("GET", f"/runs/{r['run_id']}/graph")
    assert len(g["nodes"]) == 46 and len(g["edges"]) == 90
    # 6 A05 已随 materialize 批准（批准人在 approvals）
    gates = _req("GET", f"/gates/{r['run_id']}/pending")
    assert all(p["gate"] != "A05" for p in gates["items"])
    # 7 style_decision.json 落盘
    sd = json.loads((root / "card" / "style_decision.json").read_text(encoding="utf-8"))
    assert sd["primary"] == primary
    # 8 profile 帧数推导（规格 §1：round(duration*fps)）
    prof = json.loads((root / "project.profile.json").read_text(encoding="utf-8"))
    assert prof["frames"] == round(prof["duration"] * prof["fps"])


def test_engine_unavailable_blocks_materialize():
    """夹具 11：选引擎未就绪族 → E_ENGINE_UNAVAILABLE。"""
    d = _req("POST", "/drafts", {"name": "引擎未就绪", "step": 3,
                                 "payload": {"copy": "测试文案。", "pick": {"primary": "K1"}}})
    root = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / f"it-engine-{d['id']}"
    root.mkdir(parents=True, exist_ok=True)
    _req("PATCH", f"/drafts/{d['id']}", {"payload": {"root": str(root), "copy": "测试文案。",
                                                     "pick": {"primary": "K1"}}})
    status, body = _req_status("POST", f"/drafts/{d['id']}/materialize", {})
    assert status >= 400, f"应当被阻断，实际返回 {body}"
    assert body.get("detail", {}).get("code") == "E_ENGINE_UNAVAILABLE", body
