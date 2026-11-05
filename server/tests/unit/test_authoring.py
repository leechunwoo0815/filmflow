"""FR-41：本地规则式创作辅助——PRD 原文验收四条的纯本地证据。

PRD 验收（逐条）：
① 粘贴 300 字 → 1s 内给 4–6 场景建议 + 每场理由（计时证据）。
② 每条建议可接受/拒绝/编辑 → 建议以草稿层返回（结构化、可拒绝），不改文档。
③ 断网可用；进程无外部请求 → 模块零网络 import（审计）+ 规则全本地。
④ 建议不改原文，只改结构 → 返回里原文逐字保留。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.config import settings
from app.config import settings
from app.services import authoring


@pytest.fixture()
def iso_home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "home", tmp_path)
    return tmp_path

TEXT_300 = (
    "上一季度，某平台的转发量暴涨了三倍。但是，转发量的增长并不等于真相的传播。"
    "研究发现，超过六成的爆款消息在两小时内被证伪。然而，辟谣信息的触达只有谣言的十分之一。"
    "一条消息被转发，往往不是因为它真实。真相经得起第二次查看，而谣言跑出一条街。"
    "于是，平台开始给辟谣打上显眼标签。直到标签机制上线，转发结构才出现变化。"
    "其实，用户并不拒绝真相，他们只是需要更快的真相。"
) * 2   # ≈300 字


def test_prd1_300chars_within_1s_and_4_to_6_scenes():
    t0 = time.monotonic()
    pack = authoring.suggest(TEXT_300)
    wall = time.monotonic() - t0
    assert 4 <= len(pack["scenes"]) <= 6, len(pack["scenes"])
    assert all(s["reason"] for s in pack["scenes"]), "每场必须带理由"
    assert wall < 1.0, f"300 字建议耗时 {wall:.3f}s > 1s"
    assert all(s["readCheck"]["chars"] > 0 for s in pack["scenes"])


def test_prd2_suggestions_are_draft_layer():
    """草稿层：结构化 + 可解释，不含任何对原文的改写。"""
    pack = authoring.suggest(TEXT_300)
    for sc in pack["scenes"]:
        for sent in sc["sentences"]:
            assert sent in TEXT_300, f"建议里出现非原文文本：{sent!r}"


def test_prd3_no_network_capability():
    """断网可用：模块不 import 任何网络库（代码审计），规则全本地常量。"""
    import app.services.authoring as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("import httpx", "import requests", "import socket", "urllib",
                   "urlopen", "aiohttp"):
        assert banned not in src, f"authoring 不得引入网络能力：{banned}"


def test_prd4_structure_only_no_text_rewrite():
    text = "真相经得起第二次查看。而谣言跑出一条街。"
    pack = authoring.suggest(text)
    joined = "".join(s for sc in pack["scenes"] for s in sc["sentences"])
    assert joined == text.replace("。而", "。而"), "断句重组必须逐字等于原文（不改原文）"
    assert "真相经得起第二次查看" in joined


def test_component_and_camera_suggestions():
    pack = authoring.suggest("数据增长了三倍。证据在卡片里。")
    s1 = pack["scenes"][0]
    assert any(c["component"] == "count-up" for c in s1["components"])
    assert len(s1["cameraPresets"]) in (2, 3), "镜头建议 2–3 个预设"
    assert all("note" in c for c in s1["cameraPresets"])


def test_api_surface_and_rules_export(iso_home):
    from app.main import app
    with TestClient(app, base_url="http://127.0.0.1/api",
                    headers={"Origin": "http://127.0.0.1:3000"}) as c:
        r = c.post("/projects/1/suggest", json={"text": TEXT_300})
        assert r.status_code == 200
        body = r.json()
        assert 4 <= len(body["scenes"]) <= 6
        rules = c.get("/authoring/rules")
        assert rules.status_code == 200
        assert rules.json()["readCps"] == 5.2, "读时口径必须复用 timeline_ops.READ_CPS"
