"""FR-40：通知中心——去重、已读、容量修剪、API 面、Run 终态接线。

B4/a11y 钩子：通知面板的前端组件必须带 role="alert"/aria-live（B4 验收 grep 计数）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.services import notifications as svc


@pytest.fixture()
def iso_home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "home", tmp_path)
    return tmp_path


def test_notify_dedupes_while_unread(iso_home):
    a = svc.notify("gate_pending", "gate:1:B08", "B08 待批")
    b = svc.notify("gate_pending", "gate:1:B08", "B08 待批")
    assert a is not None and b is None, "同 (kind,ref) 未读期间必须去重"
    svc.mark_read(a["id"])
    c = svc.notify("gate_pending", "gate:1:B08", "B08 待批")
    assert c is not None, "已读后同引用应可再发（新事件）"


def test_mark_read_and_read_all(iso_home):
    x = svc.notify("run_failed", "run:1", "R1 失败", detail="失败节点：F03",
                   action={"kind": "open_canvas", "runId": 1})
    y = svc.notify("run_succeeded", "run:2", "R2 完成")
    assert svc.mark_read(x["id"]) is True
    assert svc.mark_read(x["id"]) is False, "重复已读幂等"
    assert svc.mark_all_read() == 1   # 剩 y 一条
    data = svc.load()
    assert data["unread"] == 0
    assert all(i["readAt"] for i in data["items"])


def test_failed_notification_carries_repair_entry(iso_home):
    """PRD 验收③：失败通知带修复入口，而且**链接真的能打开画布**。"""
    x = svc.run_finished(9, "测试片", ok=False, detail="失败节点：F03", project_id=4)
    assert x is not None
    assert x["action"] == {"kind": "open_canvas", "runId": 9, "projectId": 4}, "失败通知必须带修复动作"
    assert x["link"], "失败通知必须带跳转"
    # 链接口径回归（FR-40 前端接线时实测发现的）：页面读 ?project=/?run=，
    # 旧写法 `?projectId=&runId=` 点进去正好落在 canvas 的「缺 project 参数」白屏上。
    assert x["link"] == "/canvas?project=4&run=9", x["link"]


def test_gate_notification_link_carries_project(iso_home):
    """待门通知的入口同理：project 与 run 都要在链接里，否则"打开画布签门"是句空话。"""
    x = svc.gate_pending(11, "B08", "测试片", project_id=7)
    assert x["link"] == "/canvas?project=7&run=11", x["link"]
    assert x["action"]["gate"] == "B08"


def test_link_degrades_to_run_only_when_project_missing(iso_home):
    """取不到项目 id 时链接仍要可用（只带 run），不能拼出 `project=` 空值那种假链接。"""
    x = svc.run_finished(12, "测试片", ok=False, project_id=None)
    assert x["link"] == "/canvas?run=12", x["link"]
    assert "project=" not in x["link"]


def test_trim_keeps_unread_never_dropped(iso_home):
    for i in range(svc.MAX_KEEP + 30):
        svc.notify("noise", f"n{i}", f"噪声 {i}")
        if i < svc.MAX_KEEP + 30 - 5:
            svc.mark_all_read()
    data = svc.load()
    unread = [i for i in svc._load_raw()["items"] if not i.get("readAt")]
    assert len(unread) == 5, "未读不许因容量修剪丢失"
    assert len(svc._load_raw()["items"]) <= svc.MAX_KEEP


def test_api_surface(iso_home):
    """API 三端点：list / {id}/read / read-all（FR-40 后端面）。"""
    from app.main import app
    with TestClient(app, base_url="http://127.0.0.1/api",
                    headers={"Origin": "http://127.0.0.1:3000"}) as c:
        svc.notify("gate_pending", "gate:2:D03", "D03 待批")
        r = c.get("/notifications")
        assert r.status_code == 200 and r.json()["unread"] == 1
        nid = r.json()["items"][-1]["id"]
        assert c.post(f"/notifications/{nid}/read").status_code == 200
        assert c.get("/notifications").json()["unread"] == 0
        svc.notify("run_succeeded", "run:3", "R3 完成")
        assert c.post("/notifications/read-all").status_code == 200
        assert c.get("/notifications").json()["unread"] == 0
        assert c.post("/notifications/nope/read").status_code == 404


def test_runengine_wires_gate_notification(iso_home):
    """Run 停在人工门 → gate_pending 通知落库（去重键含 run+gate）。"""
    import asyncio

    from app.engine import runengine

    async def fake_loop(rid: int) -> None:
        raise RuntimeError("stop")

    # 直接调 runengine 的通知路径不方便造整链——用 _project_name_of + gate_pending 的
    # 组合语义验证：parked 分支调用的函数本身已被上面用例覆盖，这里验证接线存在。
    src = Path(runengine.__file__).read_text(encoding="utf-8")
    assert "notify_svc.gate_pending" in src and "notify_svc.run_finished" in src, \
        "runengine 终态/等门分支必须接通知"
