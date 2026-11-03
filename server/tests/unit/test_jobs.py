"""FR-29 持久化 Job：迁移、租约/心跳、启动恢复、attempts 上限。"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import NodeRun, Project, Run, SchemaMigration, Workflow
from app.services import jobs as jobs_svc


def _run(tmp_path: Path, status: str = "running") -> int:
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    with Session(engine) as s:
        p = Project(name="job-test", root=str(root))
        s.add(p); s.commit(); s.refresh(p)
        wf = Workflow(project_id=p.id, graph_json={"meta": {}, "params": {}, "positions": {}})
        s.add(wf); s.commit(); s.refresh(wf)
        run = Run(workflow_id=wf.id, status=status)
        s.add(run); s.commit(); s.refresh(run)
        s.add(NodeRun(run_id=run.id, node_id="F02", status="running"))
        s.commit()
        return run.id or 0


def test_job_table_migrated():
    init_db()
    with engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(job)").fetchall()}
    for name in ("priority", "attempts", "lease_until", "heartbeat_at", "cancel_requested",
                 "progress", "error_code", "run_id", "lease_owner"):
        assert name in cols
    with Session(engine) as s:
        assert s.get(SchemaMigration, 3) is not None


def test_job_lease_heartbeat_and_finish():
    with Session(engine) as s:
        job = jobs_svc.create_job(s, "probe", 40, {"x": 1})
        assert job.status == "queued"
        claimed = jobs_svc.start_job(s, job.id, "worker-1")
        assert claimed.status == "running" and claimed.attempts == 0
        assert claimed.lease_until is not None
        old_lease = claimed.lease_until
        claimed.lease_until = old_lease - timedelta(seconds=10)
        s.add(claimed); s.commit()
        jobs_svc.heartbeat(s, job.id, "worker-1")
        s.refresh(claimed)
        assert claimed.lease_until > old_lease - timedelta(seconds=1)
        jobs_svc.finish_job(s, job.id, "succeeded", result={"ok": True})
        s.refresh(claimed)
        assert claimed.status == "succeeded" and claimed.lease_until is None
        assert claimed.result_json["ok"] is True


def test_park_retry_wait_reuses_same_job(tmp_path):
    run_id = _run(tmp_path, status="blocked")
    with Session(engine) as s:
        job = jobs_svc.ensure_run_job(s, run_id)
        jobs_svc.start_job(s, job.id, "w")
        jobs_svc.park_job(s, job.id, "retry_wait", "E_RUN_BLOCKED", "等待批准")
        again = jobs_svc.ensure_run_job(s, run_id)
        assert again.id == job.id and again.status == "retry_wait"
        jobs_svc.start_job(s, job.id, "w")
        s.refresh(again)
        assert again.status == "running" and again.attempts == 0


def test_recover_requeues_interrupted_run(tmp_path):
    run_id = _run(tmp_path)
    with Session(engine) as s:
        job = jobs_svc.ensure_run_job(s, run_id)
        job.status = "running"
        job.attempts = 1
        job.lease_until = datetime.now(UTC) + timedelta(seconds=30)
        s.add(job); s.commit()
        rec = jobs_svc.recover(s)
        assert run_id in rec["requeued"]
        s.refresh(job)
        assert job.status == "queued"
        assert s.get(Run, run_id).status == "queued"
        st = s.exec(select(NodeRun).where(NodeRun.run_id == run_id, NodeRun.node_id == "F02")).first()
        assert st.status == "idle"


def test_recover_fails_after_max_attempts(tmp_path):
    run_id = _run(tmp_path)
    with Session(engine) as s:
        job = jobs_svc.ensure_run_job(s, run_id)
        job.status = "running"
        job.attempts = 2
        job.max_attempts = 3
        s.add(job); s.commit()
        rec = jobs_svc.recover(s)
        assert run_id in rec["failed"]
        s.refresh(job)
        assert job.status == "failed" and job.error_code == "E_JOB_LEASE_LOST"
        assert s.get(Run, run_id).status == "failed"


def test_recover_interrupts_preview_jobs():
    with Session(engine) as s:
        job = jobs_svc.create_job(s, "preview_film", 100, {"projectId": 1})
        job.status = "running"
        s.add(job); s.commit()
        rec = jobs_svc.recover(s)
        assert job.id in rec["interruptedPreview"]
        s.refresh(job)
        assert job.status == "failed" and job.error_code == "E_JOB_INTERRUPTED"


def test_queue_summary_priority_order():
    with Session(engine) as s:
        low = jobs_svc.create_job(s, "batch_probe", 40, {})
        high = jobs_svc.create_job(s, "preview_probe", 100, {})
        summary = jobs_svc.queue_summary(s)
        active_ids = [j["id"] for j in summary["active"]]
        assert active_ids.index(high.id) < active_ids.index(low.id)
        assert summary["priorities"]["preview"] == 100
