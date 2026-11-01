"""RunEngine：拓扑调度 + caps + 锁 + 缓存 + 门 + 失效 + 断点续跑（规格 §5/§7.4/§7.5）。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..events import emit
from ..models import Approval, Artifact, NodeRun, Run, Workflow
from . import caps as caps_mod
from .cachekey import EXECUTOR_VERSION, gate_content_hash, node_cache_key
from .edges import N, UPSTREAM, data_descendants
from .executors import REGISTRY
from .locks import LockManager
from .runner import ProcessRunner

ACTIVE: dict[int, asyncio.Task] = {}
CANCELS: dict[int, asyncio.Event] = {}
LOCK_MANAGER = LockManager()

TERMINAL_OK = {"succeeded", "cached"}


class EngineError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _states(session: Session, run_id: int) -> dict[str, NodeRun]:
    rows = session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all()  # type: ignore[arg-type]
    by = {r.node_id: r for r in rows}
    for nid in N:
        if nid not in by:
            nr = NodeRun(run_id=run_id, node_id=nid, status="idle", params_json={})
            session.add(nr)
            by[nid] = nr
    session.commit()
    for r in by.values():
        session.refresh(r)
    return by


def _workflow(session: Session, run: Run) -> Workflow:
    wf = session.get(Workflow, run.workflow_id)
    if not wf:
        raise EngineError("workflow 不存在")
    return wf


def _graph(wf: Workflow) -> dict:
    g = wf.graph_json or {}
    return {"params": g.get("params", {}), "positions": g.get("positions", {}),
            "meta": g.get("meta", {})}


def _node_params(graph: dict, node_id: str) -> dict:
    return (graph.get("params", {}) or {}).get(node_id, {}) or {}


def _project_root(session: Session, run: Run) -> str:
    from ..models import Project
    wf = session.get(Workflow, run.workflow_id)
    proj = session.get(Project, wf.project_id)  # type: ignore[arg-type]
    return proj.root


def _upstream_hashes(session: Session, run_id: int, node_id: str, states: dict, project_root: str) -> dict[str, str]:
    """上游产物哈希；根节点用项目文件指纹。人工门额外包含 trigger 上游（门为全部上游签字）。"""
    include_trigger = N[node_id]["gate"] == "human"
    out: dict[str, str] = {}
    for up, ty in UPSTREAM[node_id].items():
        if ty not in (("data", "trigger") if include_trigger else ("data",)):
            continue
        up_state = states.get(up)
        if up_state and up_state.cache_key:
            arts = session.exec(select(Artifact).where(
                Artifact.run_id == run_id, Artifact.node_id == up)).all()  # type: ignore[arg-type]
            if arts:
                out[up] = ";".join(sorted(a.sha256 for a in arts))
                continue
        out[up] = _external_fingerprint(project_root, up)
    return out


_EXTERNAL_FILES = {
    "A01": ["card/copy.txt"], "A03": ["_library_"], "F01": ["project_root"],
    "G01": ["card/voice_raw.wav", "card/voice.wav"],
}


def _external_fingerprint(project_root: str, node_id: str) -> str:
    from .cachekey import file_sha256
    root = Path(project_root)
    parts = []
    for rel in _EXTERNAL_FILES.get(node_id, []):
        if rel == "_library_":
            lib = settings.style_library_root
            parts.append(file_sha256(str(lib / "_统计.json")) if (lib / "_统计.json").exists() else "nolib")
        elif rel == "project_root":
            parts.append(root.name)
        else:
            p = root / rel
            parts.append(file_sha256(str(p)) if p.exists() else "missing")
    return ";".join(parts) or "none"


def _gate_valid(session: Session, run: Run, gate_id: str, content_hash: str) -> tuple[bool, bool]:
    """(是否有效, 是否 stale)。inherit：任一 Run 的 approved 且 hash 相同即可；reapprove：必须本 Run。"""
    rows = session.exec(select(Approval).where(
        Approval.run_id == run.id, Approval.gate_id == gate_id)).all()  # type: ignore[arg-type]
    if N[gate_id]["gate"] != "human":
        return False, False
    for r in rows:
        if r.decision == "approved":
            if r.policy == "reapprove":
                return (r.content_hash == content_hash), (r.content_hash != content_hash)
            return (r.content_hash == content_hash), (r.content_hash != content_hash)
    # 跨 Run 复用（inherit）：查同 workflow 的其他 Run
    if N[gate_id].get("policy", "inherit") == "inherit":
        others = session.exec(select(Approval).where(Approval.gate_id == gate_id)).all()  # type: ignore[arg-type]
        for r in others:
            if r.decision == "approved" and r.content_hash == content_hash and r.run_id != run.id:
                return True, False
    return False, bool(rows)


def _ready_set(session: Session, run: Run, wf: Workflow, states: dict[str, NodeRun], project_root: str) -> dict[str, str]:
    """返回 {node_id: 原因}，原因空字符串 = ready。"""
    graph = _graph(wf)
    caps = run.caps_json or caps_mod.initial_caps()
    ready: dict[str, str] = {}
    for nid, node in N.items():
        st = states[nid]
        if st.status in TERMINAL_OK or st.status == "running":
            ready[nid] = "busy_or_done"
            continue
        if st.status == "disabled":
            ready[nid] = "disabled"
            continue
        # 上游
        blocked_reason = ""
        for up, ty in UPSTREAM[nid].items():
            up_st = states.get(up)
            if up_st is None:
                blocked_reason = f"上游 {up} 缺失"
                break
            if ty in ("data", "order", "trigger"):
                if up_st.status not in TERMINAL_OK:
                    blocked_reason = f"等待 {up}（{up_st.status}）"
                    break
        if blocked_reason:
            ready[nid] = blocked_reason
            continue
        # 门有效性（human gate）
        if node["gate"] == "human":
            params = _node_params(graph, nid)
            ch = gate_content_hash(nid, params, _upstream_hashes(session, run.id, nid, states, project_root))
            ok, _stale = _gate_valid(session, run, nid, ch)
            if not ok:
                ready[nid] = "等待批准"
                continue
        # caps
        ok, why = caps_mod.check_allowed(nid, caps)
        if not ok:
            ready[nid] = why
            continue
        ready[nid] = ""
    return ready


def _mark_skipped(session: Session, run_id: int, states: dict[str, NodeRun]) -> None:
    """上游失败/跳过的下游 → skipped（规格 §8.2）。"""
    from .edges import EDGES
    changed = True
    while changed:
        changed = False
        for f, t, _ty in EDGES:
            fs, ts = states.get(f), states.get(t)
            if fs and ts and fs.status in ("failed", "skipped", "disabled") \
                    and ts.status not in ("failed", "skipped", "succeeded", "cached"):
                ts.status = "skipped"
                session.add(ts)
                changed = True
    session.commit()


async def execute_node(run_id: int, node_id: str) -> dict:
    """执行单个节点（step / 调度循环共用）。"""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        wf = _workflow(session, run)
        states = _states(session, run_id)
        project_root = _project_root(session, run)
        graph = _graph(wf)
        params = _node_params(graph, node_id)
        st = states[node_id]

        if N[node_id]["gate"] == "human":
            return {"status": "blocked", "reason": "人工门由审批驱动"}

        input_hashes = _upstream_hashes(session, run_id, node_id, states, project_root)
        key = node_cache_key(node_id, EXECUTOR_VERSION, params, input_hashes, run.caps_json or [])

        # 缓存命中：同 workflow 任意 run 的同键成功记录（规格 §5.3）
        prev = session.exec(select(NodeRun).where(
            NodeRun.node_id == node_id, NodeRun.cache_key == key,
            NodeRun.status.in_(TERMINAL_OK))).first()  # type: ignore[arg-type,union-attr]
        if prev is not None and prev.run_id != run_id:
            st.status = "cached"
            st.cache_key = key
            st.finished_at = _now()
            session.add(st)
            _clone_artifacts(session, prev, run_id, st.id, node_id)
            emit("node.succeeded", run_id, node_id, cached=True)
            return {"status": "cached"}

        # 真实执行
        st.status = "running"
        st.started_at = _now()
        st.cache_key = key
        session.add(st)
        session.commit()
        emit("node.started", run_id, node_id)

        workdir = Path(project_root) / "runs" / str(run_id) / node_id
        workdir.mkdir(parents=True, exist_ok=True)
        runner = ProcessRunner(workdir)

        lock_waits: dict[str, float] = {}
        acquired: list[str] = []
        try:
            for lock in N[node_id]["locks"]:
                lock_waits[lock] = await LOCK_MANAGER.acquire(lock, f"{run_id}:{node_id}")
                acquired.append(lock)
        except Exception:
            for l in acquired:
                LOCK_MANAGER.release(l, f"{run_id}:{node_id}")
            raise

        async def progress(pct: float, msg: str):
            st.progress = max(st.progress, pct)
            st.message = msg
            session.add(st)
            session.commit()
            emit("node.progress", run_id, node_id, pct=round(pct, 4), msg=msg)

        ctx = {
            "run_id": run_id, "node_id": node_id, "node_run_id": st.id,
            "params": params, "workdir": str(workdir), "session": session,
            "project_root": project_root, "emit": emit, "progress": progress,
            "runner": runner, "cancel_event": CANCELS.get(run_id),
            "lock_manager": LOCK_MANAGER, "now": _now().isoformat(),
        }
        try:
            fn = REGISTRY[N[node_id]["executor"]]
            result = fn(ctx)
            if asyncio.iscoroutine(result):
                result = await result
            st.status = "succeeded"
            st.progress = 1.0
            emit("node.succeeded", run_id, node_id, lock_waits=lock_waits)
        except Exception as e:  # 失败必须可见（规格 §16）
            st.status = "failed"
            st.message = str(e)[:2000]
            emit("node.failed", run_id, node_id, error=str(e)[:500])
            _mark_skipped(session, run_id, states)
            run.status = "failed" if run.status == "running" else run.status
            session.add(run)
        finally:
            for l in acquired:
                LOCK_MANAGER.release(l, f"{run_id}:{node_id}")
            st.finished_at = _now()
            session.add(st)
            session.commit()
        return {"status": st.status, "message": st.message}


def _clone_artifacts(session: Session, prev: NodeRun, run_id: int, new_node_run_id: int | None, node_id: str) -> None:
    """缓存命中：把旧产物登记引用到本 run（内容寻址，不复制文件）。"""
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == prev.run_id, Artifact.node_id == node_id)).all()  # type: ignore[arg-type]
    for a in rows:
        session.add(Artifact(run_id=run_id, node_run_id=new_node_run_id, node_id=node_id,
                             type=a.type, path=a.path, sha256=a.sha256, bytes=a.bytes,
                             meta_json={**a.meta_json, "cached_from_run": prev.run_id}))
    session.commit()


async def _run_loop(run_id: int) -> None:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        run.status = "running"
        run.started_at = run.started_at or _now()
        session.add(run)
        session.commit()
    emit("run.started", run_id)
    try:
        while True:
            if CANCELS.get(run_id) and CANCELS[run_id].is_set():
                break
            with Session(engine) as session:
                run = session.get(Run, run_id)
                wf = _workflow(session, run)
                states = _states(session, run_id)
                project_root = _project_root(session, run)
                ready = _ready_set(session, run, wf, states, project_root)
                runnable = [nid for nid, why in ready.items() if why == ""]
                done = all(s in TERMINAL_OK or s in ("failed", "skipped") for s in (states[n].status for n in N))
                blocked = [nid for nid, why in ready.items() if why.startswith("等待批准")]
                if not runnable:
                    if done:
                        failed = [n for n in N if states[n].status == "failed"]
                        run.status = "needs_changes" if blocked and not failed else ("failed" if failed else "succeeded")
                    else:
                        run.status = "blocked" if blocked else run.status or "running"
                    run.finished_at = _now() if run.status in ("succeeded", "failed") else None
                    session.add(run)
                    session.commit()
                    emit("run.finished", run_id, status=run.status)
                    return
            # 并发：纯分析节点 2 并发，锁由 LockManager 串行（规格 §9.3）
            batch = runnable[:2]
            results = await asyncio.gather(*(execute_node(run_id, nid) for nid in batch))
            if all(r.get("status") == "cached" for r in results) and len(batch) == 1:
                # 全 cached 时避免忙转：继续下一轮（ready 集会推进）
                continue
    except asyncio.CancelledError:
        pass
    except Exception as e:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            run.status = "failed"
            session.add(run)
            session.commit()
        emit("run.finished", run_id, status="failed", error=str(e)[:300])


def start_run(run_id: int) -> None:
    if run_id in ACTIVE and not ACTIVE[run_id].done():
        return
    CANCELS[run_id] = asyncio.Event()
    ACTIVE[run_id] = asyncio.create_task(_run_loop(run_id))


async def step_run(run_id: int) -> dict:
    """单步：执行一个就绪节点（规格 §7.4 Step）。"""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        wf = _workflow(session, run)
        states = _states(session, run_id)
        project_root = _project_root(session, run)
        ready = _ready_set(session, run, wf, states, project_root)
        runnable = [nid for nid, why in ready.items() if why == ""]
        if not runnable:
            return {"ok": False, "reason": "无就绪节点", "ready": ready}
    nid = runnable[0]
    r = await execute_node(run_id, nid)
    return {"ok": r.get("status") in ("succeeded", "cached"), "node": nid, **r}


def cancel_run(run_id: int) -> None:
    if run_id in CANCELS:
        CANCELS[run_id].set()


async def resume_run(run_id: int) -> dict:
    """断点续跑（规格 §9.4）：非终态节点重新入队。"""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        states = _states(session, run_id)
        n = 0
        for st in states.values():
            if st.status in ("failed", "canceled", "running", "queued", "idle", "skipped"):
                if N[st.node_id]["gate"] != "human":
                    st.status = "idle"
                    st.progress = 0.0
                    session.add(st)
                    n += 1
        session.add(run)
        session.commit()
    start_run(run_id)
    return {"requeued": n}


def refresh_invalidations(run_id: int) -> dict:
    """按当前产物哈希重算下游 invalidated / 门 stale（改参数或重算后调用）。"""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        wf = _workflow(session, run)
        states = _states(session, run_id)
        project_root = _project_root(session, run)
        graph = _graph(wf)
        params_by = {nid: _node_params(graph, nid) for nid in N}
        hashes_by = {nid: _upstream_hashes(session, run_id, nid, states, project_root) for nid in N}
        gate_hashes = {}
        for nid in N:
            if N[nid]["gate"] == "human":
                gate_hashes[nid] = gate_content_hash(nid, params_by[nid], hashes_by[nid])
        changed = [nid for nid, st in states.items() if st.status in ("succeeded", "cached")]
        out = {"invalidated": [], "stale_gates": []}
        for src in changed:
            r = __import__("app.engine.invalidation", fromlist=["propagate"]).propagate(
                src, params_by, hashes_by, gate_hashes)
            out["invalidated"] = sorted(set(out["invalidated"]) | set(r["invalidated"]))
            out["stale_gates"] = sorted(set(out["stale_gates"]) | set(r["stale_gates"]))
        for nid in out["invalidated"]:
            if states[nid].status in ("succeeded", "cached") and N[nid]["gate"] != "human":
                states[nid].status = "idle"
                states[nid].cache_key = None
                session.add(states[nid])
        for gid in out["stale_gates"]:
            emit("gate.stale", run_id, gid)
        session.commit()
        return out
