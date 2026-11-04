"""帧服务端口可配置（2026-11-05，P0-5 E2E 转正的前置）。

规格把帧服务钉在 :8787；`FILMFLOW_FRAME_PORT` 只是**测试隔离**用的覆盖口
（集成 conftest 给隔离服务分配空闲端口），默认值不偏离规格。
锁名跟着端口走：节点表里按规格写死的 `"port-8787"` 在 acquire/holders/release
处归一化成 `port-<实际端口>`，46 节点/93 边的规格表不动。
"""
from __future__ import annotations

from app.config import Settings
from app.engine.locks import LockManager, frame_port_lock_name, normalize_lock


def test_frame_port_defaults_to_spec_and_env_overrides(monkeypatch):
    assert Settings(_env_file=None).frame_port == 8787        # 规格硬约束默认值
    monkeypatch.setenv("FILMFLOW_FRAME_PORT", "18999")
    assert Settings(_env_file=None).frame_port == 18999       # 测试隔离覆盖口


def test_lock_name_follows_frame_port(monkeypatch):
    monkeypatch.setattr("app.config.settings.frame_port", 18999)
    assert frame_port_lock_name() == "port-18999"
    # 节点表（edges.py）按规格写死 port-8787；归一化后落到实际端口的锁上
    assert normalize_lock("port-8787") == "port-18999"
    assert normalize_lock("chrome-queue") == "chrome-queue"


async def test_port_lock_acquire_release_via_spec_name(monkeypatch):
    monkeypatch.setattr("app.config.settings.frame_port", 18999)
    m = LockManager()
    waited = await m.acquire("port-8787", "run1:F01")
    assert waited >= 0.0
    assert m.holders("port-8787") == {"run1:F01"}          # 按规格名也能查
    assert m.holders("port-18999") == {"run1:F01"}         # 按实际名也能查
    m.release("port-8787", "run1:F01")
    assert m.holders("port-8787") == set()
