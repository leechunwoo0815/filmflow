"""持久化 Job（FR-29）：租约/心跳/恢复/队列 API 的数据层。"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..models import Job, NodeRun, Run

LEASE_SECONDS = 30
HEARTBEAT_SECONDS = 5
PRIORITY = {"preview": 100, "interactive": 80, "batch": 40, "delivery": 20}
ACTIVE = ("queued", "leased", "running", "retry_wait")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_job(session: Session, run_id: int) -> Job | None:
    return session.exec(select(Job).where(
        Job.run_id == run_id, Job.kind == "run", Job.status.in_(ACTIVE))
        .order_by(Job.id.desc())).first()  # type: ignore[arg-type,union-attr]


def ensure_run_job(session: Session, run_id: int, priority: int = PRIORITY["batch"]) -> Job:
    job = _active_job(session, run_id)
    if job:
        return job
    job = Job(kind="run", status="queued", priority=priority, run_id=run_id,
              payload_json={"run_id": run_id}, updated_at=_now())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def latest_run_job(session: Session, run_id: int) -> Job | None:
    return session.exec(select(Job).where(Job.run_id == run_id, Job.kind == "run")
                        .order_by(Job.id.desc())).first()  # type: ignore[arg-type,union-attr]


def create_job(session: Session, kind: str, priority: int, payload: dict,
               run_id: int | None = None, result: dict | None = None,
               parent_id: int | None = None) -> Job:
    job = Job(kind=kind, status="queued", priority=priority, payload_json=payload,
              result_json=result or {}, run_id=run_id, parent_id=parent_id,
              updated_at=_now())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def heartbeat(session: Session, job_id: int, owner: str = "") -> None:
    job = session.get(Job, job_id)
    if not job or job.status not in ("leased", "running"):
        return
    now = _now()
    job.heartbeat_at = now
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.updated_at = now
    job.lease_owner = owner or job.lease_owner
    session.add(job)
    session.commit()


def start_job(session: Session, job_id: int, owner: str = "") -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise KeyError(f"job {job_id}")
    now = _now()
    job.status = "running"
    job.started_at = job.started_at or now
    job.heartbeat_at = now
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.lease_owner = owner
    job.updated_at = now
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def update_job(session: Session, job_id: int, **fields) -> None:
    job = session.get(Job, job_id)
    if not job:
        return
    for k, v in fields.items():
        if hasattr(job, k):
            setattr(job, k, v)
    job.updated_at = _now()
    session.add(job)
    session.commit()


def finish_job(session: Session, job_id: int, status: str, *, error_code: str = "",
               error_msg: str = "", result: dict | None = None) -> None:
    job = session.get(Job, job_id)
    if not job:
        return
    job.status = status
    job.error_code = error_code
    job.error_msg = error_msg[:2000]
    if result is not None:
        job.result_json = {**(job.result_json or {}), **result}
    job.finished_at = _now()
    job.updated_at = _now()
    job.lease_until = None
    session.add(job)
    session.commit()


def park_job(session: Session, job_id: int, status: str = "retry_wait",
             error_code: str = "", error_msg: str = "") -> None:
    """Run 等待门/needs_changes：保留 active Job 以便批准后复用，不计崩溃 attempts。"""
    job = session.get(Job, job_id)
    if not job:
        return
    job.status = status
    job.error_code = error_code
    job.error_msg = error_msg[:2000]
    job.lease_until = None
    job.updated_at = _now()
    session.add(job)
    session.commit()


def cancel_requested(session: Session, job_id: int) -> bool:
    job = session.get(Job, job_id)
    if not job:
        return False
    job.cancel_requested = True
    job.updated_at = _now()
    session.add(job)
    session.commit()
    return True


def list_jobs(session: Session, status: str | None = None, kind: str | None = None,
              limit: int = 200) -> list[Job]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if kind:
        stmt = stmt.where(Job.kind == kind)
    rows = session.exec(stmt.order_by(Job.priority.desc(), Job.id.desc())).all()  # type: ignore[arg-type,union-attr]
    return rows[:max(1, min(limit, 500))]


def queue_summary(session: Session) -> dict:
    rows = session.exec(select(Job)).all()
    counts: dict[str, int] = {}
    for j in rows:
        counts[j.status] = counts.get(j.status, 0) + 1
    active = [j for j in rows if j.status in ACTIVE]
    active.sort(key=lambda j: (-j.priority, j.id))
    return {"counts": counts, "active": [_job_dict(j) for j in active[:50]],
            "priorities": PRIORITY}


def _job_dict(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "priority": j.priority,
            "runId": j.run_id, "attempts": j.attempts, "maxAttempts": j.max_attempts,
            "progress": j.progress, "eta": j.eta, "errorCode": j.error_code,
            "errorMsg": j.error_msg, "cancelRequested": j.cancel_requested,
            "leaseUntil": j.lease_until.isoformat() if j.lease_until else None,
            "heartbeatAt": j.heartbeat_at.isoformat() if j.heartbeat_at else None}


def recover(session: Session) -> dict:
    """启动恢复：运行中的 run job 重新排队；中断的 preview job 标记失败。"""
    requeued: list[int] = []
    failed: list[int] = []
    interrupted_preview: list[int] = []
    rows = session.exec(select(Job).where(Job.status.in_(ACTIVE))).all()  # type: ignore[arg-type]
    for job in rows:
        if job.kind == "run":
            if job.status in ("leased", "running"):
                job.attempts += 1
                if job.attempts >= max(1, job.max_attempts):
                    job.status = "failed"
                    job.error_code = "E_JOB_LEASE_LOST"
                    job.error_msg = f"连续 {job.attempts} 次中断，超过 max_attempts"
                    job.finished_at = _now()
                    failed.append(job.run_id or 0)
                    if job.run_id:
                        run = session.get(Run, job.run_id)
                        if run:
                            run.status = "failed"
                            session.add(run)
                else:
                    job.status = "queued"
                    job.error_code = "E_JOB_LEASE_LOST"
                    job.error_msg = "进程重启，重新排队"
                    requeued.append(job.run_id or 0)
            elif job.status == "queued" and job.run_id:
                requeued.append(job.run_id)
            job.lease_until = None
            job.lease_owner = ""
            job.updated_at = _now()
            session.add(job)
        else:
            # 预览 job 的参数在内存里，重启后无法恢复；统一标记失败
            job.status = "failed"
            job.error_code = "E_JOB_INTERRUPTED"
            job.error_msg = "进程重启，预览任务未自动重试"
            job.finished_at = _now()
            job.lease_until = None
            interrupted_preview.append(job.id or 0)
            session.add(job)
    # 中断节点的 NodeRun 回 idle，交给 resume 逻辑重跑
    for run_id in {r for r in requeued if r}:
        run = session.get(Run, run_id)
        if run:
            run.status = "queued"
            session.add(run)
        for st in session.exec(select(NodeRun).where(NodeRun.run_id == run_id)).all():  # type: ignore[arg-type]
            if st.status in ("running", "queued"):
                st.status = "idle"
                st.progress = 0.0
                st.message = "进程重启，重跑"
                session.add(st)
    # 没有 Job 的幽灵 running Run 标 blocked，避免永久 running
    for run in session.exec(select(Run).where(Run.status == "running")).all():  # type: ignore[arg-type]
        if not _active_job(session, run.id or 0):
            job = latest_run_job(session, run.id or 0)
            if not job or job.status not in ("queued", "leased", "running"):
                run.status = "blocked"
                session.add(run)
    session.commit()
    return {"requeued": sorted({x for x in requeued if x}),
            "failed": sorted({x for x in failed if x}),
            "interruptedPreview": interrupted_preview}


def cleanup_orphans() -> dict:
    """清理上次进程遗留的 Chrome/ffmpeg 与过期 profile。仅匹配 FilmFlow 前缀。"""
    killed: list[int] = []
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_s, cmd = parts
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        chrome = ("--user-data-dir=/tmp/ff-" in cmd
                  and ("Google Chrome" in cmd or "Chromium" in cmd or "chrome" in cmd))
        ffmpeg = ("ffmpeg" in cmd and ("/out/frames/" in cmd or "/out/proxy/" in cmd))
        if chrome or ffmpeg:
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except OSError:
                pass
    removed = 0
    now = time.time()
    for p in Path("/tmp").glob("ff-*"):
        try:
            if p.is_dir() and now - p.stat().st_mtime > 3600:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return {"killed": killed, "removedProfiles": removed}
