"""F01 回归：本机 httpx 客户端必须 trust_env=False。

2026-11-05 专家复核实测：NO_PROXY 带 IPv6 条目（[::1],::1——dev 进程环境实况）
时，trust_env=True（httpx 默认）解析代理环境变量直接抛 InvalidURL("Invalid port
':1]'")。该缺陷只随 shell 环境出现：报告作者的 shell 无代理变量时全绿，换一个
带该变量的 shell（如 dev 服务进程）任何 Run 的 F01 必挂。本测试自注毒环境，
任何机器确定性复现。

对照组钉住 httpx 的该行为：若上游修复了 NO_PROXY 解析，对照组会失败提示删除本文件。
"""
from __future__ import annotations

import socket

import httpx
import pytest

from app.config import settings
from app.engine.executors import pipeline

# dev 进程（pid 61295）实测的环境值，逐字复刻
_POISON = "localhost,.localhost,127.0.0.1,127.0.0.0/8,[::1],::1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_poisoned_no_proxy_breaks_default_client(monkeypatch):
    """对照组：毒环境 + trust_env=True（httpx 默认）→ InvalidURL。"""
    monkeypatch.setenv("NO_PROXY", _POISON)
    monkeypatch.setenv("no_proxy", _POISON)
    with pytest.raises(httpx.InvalidURL, match="Invalid port"):
        await httpx.AsyncClient().get("http://127.0.0.1:9/", timeout=2)


async def test_f01_survives_poisoned_no_proxy(tmp_path, monkeypatch):
    """F01 在毒环境下必须照常从真实帧服务拿到 200 并登记 artifact。"""
    monkeypatch.setenv("NO_PROXY", _POISON)
    monkeypatch.setenv("no_proxy", _POISON)
    monkeypatch.setattr(settings, "frame_port", _free_port())
    monkeypatch.setattr(pipeline, "_fs_instance", None)
    captured: dict = {}
    monkeypatch.setattr(pipeline, "_artifact_json",
                        lambda ctx, name, payload: captured.update(payload) or "stub")

    ctx = {"project_root": str(tmp_path), "session": None, "run_id": 0,
           "node_run_id": 0, "node_id": "F01"}
    try:
        await pipeline.f01(ctx)
    finally:
        if pipeline._fs_instance is not None:
            pipeline._fs_instance.stop()
    assert captured.get("engine_ok") is True, "毒环境下 F01 必须照常拿到 200"
    assert captured.get("port") == settings.frame_port
