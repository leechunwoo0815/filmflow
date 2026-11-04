"""P2-02 / P2-03：节点 timeout/retries 强制执行 + 同项目 Run 互斥。

P2-02：edges.py 节点表的 timeout/retries 此前是死配置——execute_node 从不读它们，
卡死的节点会永远卡住。现在 timeout>0 强制 wait_for（超时先杀执行器的子进程），
超时按 retries 自动重试，重试耗尽按 E_NODE_TIMEOUT 失败。
P2-03：同一项目根的 frames/out/film 是共享的，两个 Run 任务并发写会互相覆盖帧；
项目级锁按任务生命周期持有（park/结束释放，等门的 Run 让位）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.engine import runengine
from app.engine.cachekey import EXECUTOR_VERSION


def test_executor_version_bumped_for_scheduling_change():
    # 节点调度行为变化（timeout 强制 + 项目互斥）→ 至少 2.15.0
    major, minor, _ = (int(x) for x in EXECUTOR_VERSION.split("."))
    assert (major, minor) >= (2, 15)


async def test_run_loop_locked_waits_for_project_lock(monkeypatch):
    entered: list[tuple[str, int]] = []

    async def fake_loop(rid: int) -> None:
        entered.append(("in", rid))
        await asyncio.sleep(0.02)
        entered.append(("out", rid))

    monkeypatch.setattr(runengine, "_run_loop", fake_loop)
    lock = runengine._project_run_lock("/root-t")
    async with lock:                       # 模拟同项目另一个 Run 正在执行
        t = asyncio.create_task(runengine._run_loop_locked(1, "/root-t"))
        await asyncio.sleep(0.005)
        assert ("in", 1) not in entered, "同项目的第二个 Run 没被项目锁挡住"
        assert lock.locked()
    await t
    assert entered == [("in", 1), ("out", 1)]
    assert not lock.locked(), "任务 park/结束后必须释放项目锁"


async def test_run_loop_locked_rootless_runs_without_lock(monkeypatch):
    entered: list[tuple[str, int]] = []

    async def fake_loop(rid: int) -> None:
        entered.append(("in", rid))

    monkeypatch.setattr(runengine, "_run_loop", fake_loop)
    t = asyncio.create_task(runengine._run_loop_locked(2, ""))
    await t
    assert entered == [("in", 2)]


async def test_node_timeout_kills_child_and_retries(monkeypatch):
    """P2-02：第一次超时 → 杀子进程 → 自动重试 → 第二次成功。"""
    from app.engine.runner import ProcessRunner
    from app.engine.runengine import N, execute_node

    calls = {"n": 0, "killed": 0}

    async def counting_kill(self):
        calls["killed"] += 1

    monkeypatch.setattr(ProcessRunner, "kill_current", counting_kill)

    async def flaky_executor(ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(30)        # 超过 monkeypatch 后的 1s 节点超时
        return {"ok": True}

    monkeypatch.setitem(N, "A02", {**N["A02"], "timeout": 1, "retries": 1})
    monkeypatch.setitem(runengine.REGISTRY, "brief-form", flaky_executor)

    import tempfile
    from pathlib import Path

    from app.db import engine
    from app.models import NodeRun, Project, Run, Workflow
    from app.services.project_cleanup import delete_project
    from sqlmodel import Session

    root = Path(tempfile.mkdtemp(prefix="p2-02-"))
    with Session(engine) as session:
        p = Project(name="p2-02-timeout", root=str(root))
        session.add(p)
        session.commit()
        session.refresh(p)
        wf = Workflow(project_id=p.id, name="main", graph_json={"meta": {}, "nodes": [], "edges": []})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(NodeRun(run_id=run.id, node_id="A02", status="idle"))
        session.commit()
        try:
            res = await runengine.execute_node(run.id, "A02")
            assert res["status"] == "succeeded", res
            assert calls["n"] == 2, f"应重试一次后成功，实际调用 {calls['n']} 次"
            assert calls["killed"] >= 1, "超时必须先杀执行器的子进程"
        finally:
            delete_project(session, p.id, remove_dir=False, force=True)


async def test_node_timeout_exhausted_retries_fails(monkeypatch):
    """P2-02：retries 耗尽 → 节点 failed，message 带 E_NODE_TIMEOUT。"""
    from app.engine.runengine import N, execute_node

    calls = {"n": 0}

    class FakeRunner:
        async def kill_current(self):
            pass

    async def hang_executor(ctx):
        calls["n"] += 1
        await asyncio.sleep(30)

    monkeypatch.setitem(N, "A02", {**N["A02"], "timeout": 1, "retries": 1})
    monkeypatch.setitem(runengine.REGISTRY, "brief-form", hang_executor)

    from pathlib import Path
    import tempfile

    from app.models import NodeRun, Project, Run, Workflow
    from app.services.project_cleanup import delete_project
    from sqlmodel import Session

    from app.db import engine

    root = Path(tempfile.mkdtemp(prefix="p2-02b-"))
    with Session(engine) as session:
        p = Project(name="p2-02-timeout2", root=str(root))
        session.add(p)
        session.commit()
        session.refresh(p)
        wf = Workflow(project_id=p.id, name="main", graph_json={"meta": {}, "nodes": [], "edges": []})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(NodeRun(run_id=run.id, node_id="A02", status="idle"))
        session.commit()
        try:
            res = await runengine.execute_node(run.id, "A02")
            assert res["status"] == "failed", res
            assert calls["n"] == 2, "初始 1 次 + 重试 1 次"
            assert "E_NODE_TIMEOUT" in (res.get("message") or ""), res
        finally:
            delete_project(session, p.id, remove_dir=False, force=True)
