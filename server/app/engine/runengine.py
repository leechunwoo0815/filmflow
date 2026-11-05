"""RunEngine：拓扑调度 + caps + 锁 + 缓存 + 门 + 失效 + 断点续跑（规格 §5/§7.4/§7.5）。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..events import emit
from ..models import Approval, Artifact, NodeRun, Project, Run, Workflow
from ..services import jobs as jobs_svc
from ..services.render_profiles import PROFILE_NODES, profiles_sha
from . import caps as caps_mod
from .cachekey import EXECUTOR_VERSION, file_sha256, gate_content_hash, node_cache_key
from .edges import UPSTREAM, N
from .executors import REGISTRY
from .locks import LockManager
from .runner import ProcessRunner
from .snapshot import ensure_run_snapshot

ACTIVE: dict[int, asyncio.Task] = {}
from ..logs import get as _get_log

_log = _get_log("engine")

CANCELS: dict[int, asyncio.Event] = {}
LOCK_MANAGER = LockManager()

TERMINAL_OK = {"succeeded", "cached"}
# 只读文档快照的节点：文档变化必须使这些节点缓存失效（FR-25）
DOC_NODES = {"A01", "B02", "B03", "B06", "D01", "E01", "E03"}
# 这些节点写项目内文件（stills/proxy/frames/mp4/wav/master）；跨项目缓存会让消费者找不到文件
PROJECT_LOCAL_NODES = {"D01", "D02", "E03", "E04", "E05", "F02", "F04", "G01", "G05", "G07"}
# C01 是引擎包的缓存根；引擎文件变化必须从这里失效，下游靠 C01 产物哈希传播
ENGINE_NODES = {"C01"}
# 这些节点读项目文件而不是 DAG 边；文件变化必须进缓存键
_PROJECT_INPUTS = {
    "G01": ("card/audio.json",),
    "G02": ("card/alignment.manual.json",),
    "G04": ("card/audio.json",),
    "G05": ("card/audio.json", "card/audio.mix.json"),
    "G06": ("card/audio.mix.json",),
    "G07": ("card/audio.mix.json",),
}


class EngineError(RuntimeError):
    pass


def _now():
    return datetime.now(UTC)


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
    out.update(_external_input_hashes(project_root, node_id))
    return out


_EXTERNAL_FILES = {
    "A01": ["card/copy.txt"], "A03": ["_library_"], "F01": ["project_root"],
    "G01": ["card/voice_raw.wav", "card/voice.wav"],
}


def _library_fingerprint(lib: Path) -> str:
    """风格库内容指纹：路径 + 所有非示例文件内容；库内容变化必须使 A03 失效。"""
    if not lib.is_dir():
        return f"nolib:{lib}"
    h = hashlib.sha256()
    h.update(str(lib.resolve()).encode("utf-8"))
    for p in sorted(lib.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(lib)
        if "示例" in rel.parts or any(part.startswith(".") for part in rel.parts):
            continue
        h.update(str(rel).encode("utf-8"))
        h.update(file_sha256(str(p)).encode("utf-8"))
    return h.hexdigest()


def _external_fingerprint(project_root: str, node_id: str) -> str:
    root = Path(project_root)
    parts = []
    for rel in _EXTERNAL_FILES.get(node_id, []):
        if rel == "_library_":
            parts.append(_library_fingerprint(settings.style_library_root))
        elif rel == "project_root":
            parts.append(root.name)
        else:
            p = root / rel
            parts.append(file_sha256(str(p)) if p.exists() else "missing")
    return ";".join(parts) or "none"


def _external_input_hashes(project_root: str, node_id: str) -> dict[str, str]:
    if node_id not in _EXTERNAL_FILES:
        return {}
    return {f"_external:{node_id}": _external_fingerprint(project_root, node_id)}


def _project_input_hashes(project_root: str, node_id: str) -> dict[str, str]:
    root = Path(project_root)
    hashes: dict[str, str] = {}
    for rel in _PROJECT_INPUTS.get(node_id, ()):
        p = root / rel
        if p.exists():
            hashes[rel] = file_sha256(str(p))
    if node_id == "G04":
        audio_dir = root / "card" / "audio"
        if audio_dir.is_dir():
            for p in sorted(audio_dir.glob("*.wav")):
                hashes[str(p.relative_to(root))] = file_sha256(str(p))
    return hashes


def _style_primary(wf: Workflow, project_root: str) -> str:
    meta = (wf.graph_json or {}).get("meta") or {}
    decision = meta.get("style_decision") or {}
    primary = str(decision.get("primary") or "")
    if primary:
        return primary
    p = Path(project_root) / "card" / "style_decision.json"
    if not p.exists():
        return ""
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("primary") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def _engine_pack_sha(session: Session, wf: Workflow, project_root: str) -> str:
    from ..models import Style
    from ..services import engines as engines_svc

    decision = ((wf.graph_json or {}).get("meta") or {}).get("style_decision") or {}
    engine_id = str(decision.get("engine_id") or "")
    primary = _style_primary(wf, project_root)
    if not engine_id and primary:
        style = session.get(Style, primary)
        if style:
            eng = engines_svc.engine_for_family(style.family)
            if eng:
                return str(eng.get("sha256") or engines_svc.compute_pack_sha(eng["engine_id"]))
    if not engine_id:
        task = Path(project_root) / "card" / "task.json"
        if task.exists():
            try:
                engine_id = str((json.loads(task.read_text(encoding="utf-8")).get("style") or {})
                                 .get("engine_id") or "")
            except (OSError, json.JSONDecodeError):
                engine_id = ""
    return engines_svc.compute_pack_sha(engine_id) if engine_id else ""


def _cache_params_for_node(session: Session, wf: Workflow, node_id: str, params: dict,
                           project_root: str, snapshot: dict) -> dict:
    cache_params = params
    run_profiles = snapshot.get("render_profiles") or {}
    if node_id in PROFILE_NODES and run_profiles:
        cache_params = {**cache_params, "renderProfilesSha": profiles_sha(run_profiles)}
    if node_id in PROJECT_LOCAL_NODES:
        cache_params = {**cache_params, "projectRoot": str(project_root)}
    if node_id in ENGINE_NODES:
        cache_params = {**cache_params,
                        "enginePackSha": _engine_pack_sha(session, wf, project_root)}
    project_hashes = _project_input_hashes(project_root, node_id)
    if project_hashes:
        cache_params = {**cache_params, "projectInputsSha": project_hashes}
        if node_id in ("G01", "G05"):
            cache_params = {**cache_params,
                            "timelineSha": snapshot.get("doc_snapshot_sha", "")}
    return cache_params


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
    # 跨 Run 复用（inherit）：查同 workflow 的其他 Run。
    # P2-01：此前注释写"同 workflow"但查询没过滤——不同项目撞了相同 content_hash
    # （比如同一段 copy 建的两个项目）会互相继承人工门批准，越权放行。
    if N[gate_id].get("policy", "inherit") == "inherit":
        others = session.exec(
            select(Approval).join(Run, Approval.run_id == Run.id).where(
                Approval.gate_id == gate_id, Run.workflow_id == run.workflow_id)).all()  # type: ignore[arg-type]
        for r in others:
            if r.decision == "approved" and r.content_hash == content_hash and r.run_id != run.id:
                return True, False
    return False, bool(rows)


def _ready_set(session: Session, run: Run, wf: Workflow, states: dict[str, NodeRun], project_root: str) -> dict[str, str]:
    """返回 {node_id: 原因}，原因空字符串 = ready。"""
    graph = _graph(wf)
    caps = list(run.caps_json or caps_mod.initial_caps())
    caps_dirty = False
    ready: dict[str, str] = {}
    for nid, node in N.items():
        st = states[nid]
        if node["gate"] == "human" and st.status in TERMINAL_OK:
            # 已批准的门的 caps 必须补发（跨 Run 继承/重启后尤其重要）
            new_caps = caps_mod.caps_after_approval(caps, nid)
            if new_caps != caps:
                caps = new_caps
                run.caps_json = caps
                session.add(run)
                caps_dirty = True
        if st.status in TERMINAL_OK or st.status == "running":
            ready[nid] = "busy_or_done"
            continue
        if st.status in ("failed", "skipped", "canceled"):
            # 失败不自动重排：retry 端点显式把 failed → idle；resume 显式重置 skipped
            ready[nid] = "terminal"
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
        # 门有效性（human gate）：活同步门节点状态——有效→succeeded（纯门）/ idle（有真实执行体），失效→blocked
        if node["gate"] == "human":
            params = _node_params(graph, nid)
            ch = gate_content_hash(nid, params, _upstream_hashes(session, run.id, nid, states, project_root))
            ok, stale = _gate_valid(session, run, nid, ch)
            if ok:
                # 跨 Run 继承的批准同样要补发 caps（否则 F01/F02 会无门可等却永远 idle）
                new_caps = caps_mod.caps_after_approval(caps, nid)
                if new_caps != caps:
                    caps = new_caps
                    run.caps_json = caps
                    session.add(run)
                    caps_dirty = True
                target = "idle" if node["executor"] not in ("gate", "still-view") else "succeeded"
                if st.status != target:
                    st.status = target
                    session.add(st)
                if target == "succeeded":
                    ready[nid] = "busy_or_done"
                    continue
            else:
                if st.status in ("succeeded", "cached"):
                    emit("gate.stale", run.id, nid)
                if st.status not in ("blocked",):
                    st.status = "blocked"
                    session.add(st)
                ready[nid] = "等待批准" + ("（stale）" if stale else "")
                continue
        # caps
        ok, why = caps_mod.check_allowed(nid, caps)
        if not ok:
            ready[nid] = why
            continue
        ready[nid] = ""
    if caps_dirty:
        session.add(run)
        session.commit()
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
        if node_id == "B06":
            # task_id 的默认值依赖项目根；必须进缓存键，否则会跨项目复用任务卡
            params = {**params, "task_id": params.get("task_id") or Path(project_root).name}
        st = states[node_id]
        snapshot = ensure_run_snapshot(session, run, project_root)

        if N[node_id]["gate"] == "human":
            # 人工门：审批有效性活同步；有真实执行体的门（如 G07 打包）在批准后照常执行
            ok, _ = _gate_valid(session, run, node_id,
                                gate_content_hash(node_id, params,
                                                  _upstream_hashes(session, run_id, node_id, states, project_root)))
            if not ok:
                if st.status not in ("blocked", "idle"):
                    st.status = "blocked"
                    session.add(st)
                    session.commit()
                return {"status": "blocked", "reason": "等待批准"}
            new_caps = caps_mod.caps_after_approval(run.caps_json or [], node_id)
            if new_caps != (run.caps_json or []):
                run.caps_json = new_caps
                session.add(run)
                session.commit()
            if N[node_id]["executor"] in ("gate", "still-view"):
                if st.status != "succeeded":
                    st.status = "succeeded"
                    st.finished_at = _now()
                    session.add(st)
                    session.commit()
                return {"status": "succeeded"}
            # 落到下方真实执行流程

        input_hashes = _upstream_hashes(session, run_id, node_id, states, project_root)
        doc_sha = snapshot.get("doc_snapshot_sha", "") if node_id in DOC_NODES else ""
        cache_params = _cache_params_for_node(session, wf, node_id, params, project_root, snapshot)
        key = node_cache_key(node_id, EXECUTOR_VERSION, cache_params, input_hashes,
                             run.caps_json or [], doc_sha)

        # 缓存命中：同 workflow 任意 run 的同键成功记录（规格 §5.3）
        candidates = session.exec(select(NodeRun).where(
            NodeRun.node_id == node_id, NodeRun.cache_key == key,
            NodeRun.status.in_(TERMINAL_OK)).order_by(NodeRun.id.desc())).all()  # type: ignore[arg-type,union-attr]
        prev = next((c for c in candidates
                     if c.run_id != run_id and _cache_hit_is_material(session, c, node_id)), None)
        if prev is not None:
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
            "run_docs_dir": str(Path(project_root) / "runs" / str(run_id) / "docs"),
            "doc_snapshot_sha": snapshot.get("doc_snapshot_sha", ""),
            "run_imported": bool(snapshot.get("imported")),
            "run_profile": snapshot.get("profile") or {},
            "run_render_profiles": snapshot.get("render_profiles") or {},
        }
        try:
            # P2-02：节点表的 timeout/retries 此前是死配置（从未被读取）。现在
            # timeout>0 时强制 asyncio.wait_for（超时先杀执行器里仍在飞的子进程），
            # 超时按 retries 自动重试（渲染类抖动的 Recoverable 失败）；timeout=0
            # 表示节点自管超时（A04 每张 15s、A05 人工门），语义不变。
            node_timeout = float(N[node_id].get("timeout") or 0)
            retries_left = int(N[node_id].get("retries") or 0)
            while True:
                try:
                    fn = REGISTRY[N[node_id]["executor"]]
                    result = fn(ctx)
                    if asyncio.iscoroutine(result):
                        result = (await asyncio.wait_for(result, timeout=node_timeout)
                                  if node_timeout > 0 else await result)
                    st.status = "succeeded"
                    st.progress = 1.0
                    st.message = ""   # 成功即清空历史失败信息（重试后 UI 不再显示旧错误）
                    emit("node.succeeded", run_id, node_id, lock_waits=lock_waits)
                    if node_id == "A04":
                        _auto_approve_a05(session, run, wf, states, project_root)
                    break
                except TimeoutError:
                    await runner.kill_current()
                    if retries_left > 0:
                        retries_left -= 1
                        st.message = (f"E_NODE_TIMEOUT：节点超过 {node_timeout:.0f}s 未完成，"
                                      f"自动重试（剩 {retries_left} 次）")
                        st.progress = 0.0
                        session.add(st)
                        session.commit()
                        emit("node.progress", run_id, node_id, pct=0.0, msg=st.message)
                        continue
                    raise RuntimeError(
                        f"E_NODE_TIMEOUT：节点超过 {node_timeout:.0f}s 未完成"
                        f"（已重试 {N[node_id].get('retries') or 0} 次）") from None
        except Exception as e:  # 失败必须可见（规格 §16）
            st.status = "failed"
            st.message = str(e)[:2000]
            _log.warning("node failed run=%s node=%s: %s", run_id, node_id, str(e)[:300])
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


def _auto_approve_a05(session: Session, run: Run, wf: Workflow, states: dict, project_root: str) -> None:
    """A04 完成后自动携带 A05 批准（导入继承原风格 / 向导 materialize 携带选择）。

    哈希在 A04 产物落定后计算，保证门 content_hash 与上游一致（不产生假 stale）。
    """
    meta = (wf.graph_json or {}).get("meta", {})
    decision = meta.get("style_decision") or {}
    if not meta.get("imported") and not decision:
        return
    existing = session.exec(select(Approval).where(
        Approval.run_id == run.id, Approval.gate_id == "A05", Approval.decision == "approved")).first()  # type: ignore[arg-type]
    if existing is not None:
        return
    params = _node_params(_graph(wf), "A05")
    ch = gate_content_hash("A05", params, _upstream_hashes(session, run.id, "A05", states, project_root))
    session.add(Approval(run_id=run.id, gate_id="A05", decision="approved", policy="inherit",
                         content_hash=ch, author="local",
                         note=decision.get("reason") or "导入继承原风格"))
    session.commit()
    emit("gate.decided", run.id, "A05", decision="approved", auto=True)


def _cache_hit_is_material(session: Session, prev: NodeRun, node_id: str) -> bool:
    """缓存命中必须"文件真的还在"，否则退回真实执行。

    产物是内容寻址存在**产出它的那个项目根**里的，跨项目命中只登记路径不复制文件。
    所以删掉一个验收残留项目，就会让之后任何 Run 的命中指向空气：实测 C02 命中已删的
    `r3-audio-v2-299/artifacts/a3/a304….txt`，C03 直接报"变量字体缺失：先运行 C02"，
    整条渲染链在一个全新项目上跑不下去。
    """
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == prev.run_id, Artifact.node_id == node_id)).all()  # type: ignore[arg-type]
    return all(Path(a.path).exists() for a in rows)


def _clone_artifacts(session: Session, prev: NodeRun, run_id: int, new_node_run_id: int | None, node_id: str) -> None:
    """缓存命中：把旧产物登记引用到本 run（内容寻址，不复制文件）。"""
    rows = session.exec(select(Artifact).where(
        Artifact.run_id == prev.run_id, Artifact.node_id == node_id)).all()  # type: ignore[arg-type]
    for a in rows:
        session.add(Artifact(run_id=run_id, node_run_id=new_node_run_id, node_id=node_id,
                             type=a.type, path=a.path, sha256=a.sha256, bytes=a.bytes,
                             meta_json={**a.meta_json, "cached_from_run": prev.run_id}))
    session.commit()


def _job_finish(job_id: int | None, status: str, *, error_code: str = "",
                error_msg: str = "", result: dict | None = None) -> None:
    if not job_id:
        return
    with Session(engine) as session:
        jobs_svc.finish_job(session, job_id, status, error_code=error_code,
                            error_msg=error_msg, result=result)


def _job_park(job_id: int | None, status: str, error_code: str, error_msg: str) -> None:
    if not job_id:
        return
    with Session(engine) as session:
        jobs_svc.park_job(session, job_id, status, error_code, error_msg)


async def _heartbeat_job(job_id: int, owner: str) -> None:
    while True:
        await asyncio.sleep(jobs_svc.HEARTBEAT_SECONDS)
        try:
            with Session(engine) as session:
                jobs_svc.heartbeat(session, job_id, owner)
        except Exception:
            # 心跳失败不能杀死 run；下次心跳继续
            _log.debug("swallowed exception in _heartbeat_job (except Exception:)", exc_info=True)


def _project_name_of(session, wf) -> str:
    try:
        from ..models import Project
        proj = session.get(Project, wf.project_id) if wf else None
        return (proj.name if proj and proj.name else f"project {wf.project_id}") if wf else "-"
    except Exception:   # noqa: BLE001 -- 仅为通知/日志取项目名，任何失败回 "-" 不致败 Run
        return "-"


async def _run_loop(run_id: int) -> None:
    owner = f"run:{run_id}"
    job_id: int | None = None
    hb_task: asyncio.Task | None = None
    with Session(engine) as session:
        run = session.get(Run, run_id)
        job = jobs_svc.ensure_run_job(session, run_id)
        job = jobs_svc.start_job(session, job.id or 0, owner)  # type: ignore[arg-type]
        job_id = job.id
        run.status = "running"
        run.started_at = run.started_at or _now()
        session.add(run)
        session.commit()
    hb_task = asyncio.create_task(_heartbeat_job(job_id or 0, owner))
    emit("run.started", run_id)
    try:
        while True:
            if CANCELS.get(run_id) and CANCELS[run_id].is_set():
                with Session(engine) as session:
                    run = session.get(Run, run_id)
                    run.status = "canceled"
                    run.finished_at = _now()
                    session.add(run)
                    session.commit()
                _job_finish(job_id, "canceled", error_code="E_RUN_CANCELED",
                            result={"runStatus": "canceled"})
                emit("run.finished", run_id, status="canceled")
                return
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
                        # 无就绪节点、无等待门却不是终态：暴露为 blocked，避免“running 但不动”
                        run.status = "blocked"
                    run.finished_at = _now() if run.status in ("succeeded", "failed") else None
                    session.add(run)
                    session.commit()
                    if run.status == "succeeded":
                        _log.info("run finished run=%s status=succeeded", run_id)
                        _job_finish(job_id, "succeeded", result={"runStatus": "succeeded"})
                        try:
                            from ..services import notifications as notify_svc
                            notify_svc.run_finished(run_id, _project_name_of(session, wf), True)
                        except Exception:   # noqa: BLE001 -- 通知尽力而为，失败只记日志
                            _log.debug("notify run_finished failed", exc_info=True)
                    elif run.status == "failed":
                        _log.info("run finished run=%s status=failed", run_id)
                        _job_finish(job_id, "failed", error_code="E_RUN_FAILED",
                                    error_msg="run failed", result={"runStatus": "failed"})
                        try:
                            from ..services import notifications as notify_svc
                            fails = ",".join(n for n in N if states[n].status == "failed")
                            notify_svc.run_finished(run_id, _project_name_of(session, wf), False,
                                                    detail=f"失败节点：{fails}")
                        except Exception:   # noqa: BLE001 -- 通知尽力而为，失败只记日志
                            _log.debug("notify run_finished failed", exc_info=True)
                    else:
                        # 等门/needs_changes：保留 active job，批准后 start_run 复用
                        _log.info("run parked run=%s status=%s blocked=%s",
                                  run_id, run.status, blocked)
                        _job_park(job_id, "retry_wait", "E_RUN_BLOCKED", run.status)
                        # FR-40：人工门待批通知（同 (run,gate) 未读期间去重）
                        try:
                            from ..services import notifications as notify_svc
                            pname = _project_name_of(session, wf)
                            for gate in blocked:
                                notify_svc.gate_pending(run_id, gate, pname)
                        except Exception:   # noqa: BLE001 -- 通知尽力而为，失败只记日志
                            _log.debug("notify gate_pending failed", exc_info=True)
                    emit("run.finished", run_id, status=run.status)
                    return
            # 并发：纯分析节点 2 并发，锁由 LockManager 串行（规格 §9.3）
            batch = runnable[:2]
            results = await asyncio.gather(*(execute_node(run_id, nid) for nid in batch))
            if all(r.get("status") == "cached" for r in results) and len(batch) == 1:
                # 全 cached 时避免忙转：继续下一轮（ready 集会推进）
                continue
    except asyncio.CancelledError:
        # 进程关闭/任务取消：保留 running job 与租约，交给启动恢复
        raise
    except Exception as e:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            run.status = "failed"
            session.add(run)
            session.commit()
        _job_finish(job_id, "failed", error_code="E_RUN_FAILED", error_msg=str(e)[:300],
                    result={"runStatus": "failed"})
        emit("run.finished", run_id, status="failed", error=str(e)[:300])
    finally:
        if hb_task:
            hb_task.cancel()


def start_run(run_id: int) -> None:
    if run_id in ACTIVE and not ACTIVE[run_id].done():
        return
    root = ""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run:
            wf = session.get(Workflow, run.workflow_id)
            project = session.get(Project, wf.project_id) if wf else None
            if project:
                root = project.root
                ensure_run_snapshot(session, run, project.root)
        jobs_svc.ensure_run_job(session, run_id)
    CANCELS[run_id] = asyncio.Event()
    if root:
        _retain_run_lock_slot(root)   # A4：排队等锁也在册，最后一个退出者清字典
    ACTIVE[run_id] = asyncio.create_task(_run_loop_locked(run_id, root))


# P2-03：同一项目根同一时刻只允许一个"执行中"的 Run 任务。frames/out/film 都是
# 项目根共享的，两个任务并发写就是帧互相覆盖。锁按任务生命周期持有：任务 park
# （等人工门）或结束就释放，等门的 Run 让位给同项目的下一个 Run，恢复时重新拿锁。
# A4（2026-11-06）：字典按 root 只增不清曾无人管——登记计数（含排队等锁的 Run）
# 归零时锁与计数一起 pop；项目删除时走 drop_project_run_lock 强制清。
# 只动进程内字典卫生：节点执行/调度结果逐字节等价，EXECUTOR_VERSION 不升（同
# trust_env 修复的产出等价裁决，见 b9-close-report §9.1）。
_PROJECT_RUN_LOCKS: dict[str, asyncio.Lock] = {}
_PROJECT_RUN_HOLDERS: dict[str, int] = {}


def _project_run_lock(root: str) -> asyncio.Lock:
    lock = _PROJECT_RUN_LOCKS.get(root)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_RUN_LOCKS[root] = lock
    return lock


def _retain_run_lock_slot(root: str) -> None:
    """Run 任务注册期 +1（排队等锁也在册）；最后一个退出者负责清字典。"""
    _PROJECT_RUN_HOLDERS[root] = _PROJECT_RUN_HOLDERS.get(root, 0) + 1


def _release_run_lock_slot(root: str) -> None:
    n = _PROJECT_RUN_HOLDERS.get(root, 0) - 1
    if n > 0:
        _PROJECT_RUN_HOLDERS[root] = n
        return
    _PROJECT_RUN_HOLDERS.pop(root, None)
    _PROJECT_RUN_LOCKS.pop(root, None)


def drop_project_run_lock(root: str) -> None:
    """A4：项目删除时清掉它的 Run 锁与登记计数（不随历史项目无限增长）。"""
    _PROJECT_RUN_HOLDERS.pop(root, None)
    _PROJECT_RUN_LOCKS.pop(root, None)


async def _run_loop_locked(run_id: int, root: str) -> None:
    if not root:
        await _run_loop(run_id)
        return
    try:
        async with _project_run_lock(root):
            await _run_loop(run_id)
    finally:
        _release_run_lock_slot(root)


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
    active = run_id in ACTIVE and not ACTIVE[run_id].done()
    if run_id in CANCELS:
        CANCELS[run_id].set()
    with Session(engine) as session:
        job = jobs_svc._active_job(session, run_id)
        if not job or not job.id:
            return
        if not active:
            run = session.get(Run, run_id)
            if run and run.status not in ("succeeded", "failed"):
                run.status = "canceled"
                session.add(run)
            jobs_svc.finish_job(session, job.id, "canceled",
                                error_code="E_RUN_CANCELED", result={"runStatus": "canceled"})
        else:
            jobs_svc.cancel_requested(session, job.id)


async def resume_run(run_id: int) -> dict:
    """断点续跑（规格 §9.4）：非终态节点重新入队（含被级联 skip 的人工门）。"""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        states = _states(session, run_id)
        n = 0
        for st in states.values():
            if st.status in ("failed", "canceled", "running", "queued", "idle", "skipped"):
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
