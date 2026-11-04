"""FR-28：SRT 换行/时间码/QC 辅助 + 交付作业归属校验。"""
import sys
from pathlib import Path

import pytest
from sqlmodel import Session

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import engine  # noqa: E402
from app.services.delivery import _srt, _ts, _wrap  # noqa: E402


def test_wrap_respects_fullwidth_limit():
    text = "风从纸上起，慢慢穿过整条街。"
    lines = _wrap(text, 8).splitlines()
    assert lines and all(len(x) <= 8 for x in lines)
    assert "".join(lines) == text


def test_srt_format_and_metrics():
    text, meta = _srt([{"text": "风从纸上起。", "start": 0, "end": 2.24},
                       {"text": "纸不动，风先动。", "start": 2.24, "end": 5.0}])
    assert "00:00:00,000 --> 00:00:02,240" in text
    assert "00:00:02,240 --> 00:00:05,000" in text
    assert meta["count"] == 2 and meta["maxLineChars"] <= 16
    assert meta["maxCharsPerSec"] <= 9


def test_timestamp_rounding():
    assert _ts(65.5) == "00:01:05,500"


def test_delivery_job_rejects_foreign_run(tmp_path):
    """判官 P1：runId 必须属于该项目，否则会把别的 Run 的 master 与本项目混音打进同一个包。"""
    from app.errors import ApiError
    from app.models import Project, Run, Workflow
    from app.services import delivery

    with Session(engine) as session:
        a = Project(name="judge-del-a", root=str(tmp_path / "a"))
        b = Project(name="judge-del-b", root=str(tmp_path / "b"))
        session.add_all([a, b])
        session.commit()
        session.refresh(a)
        session.refresh(b)
        wfa = Workflow(project_id=a.id, name="main", graph_json={"meta": {}})
        wfb = Workflow(project_id=b.id, name="main", graph_json={"meta": {}})
        session.add_all([wfa, wfb])
        session.commit()
        session.refresh(wfa)
        session.refresh(wfb)
        run_b = Run(workflow_id=wfb.id, status="succeeded")
        session.add(run_b)
        session.commit()
        session.refresh(run_b)
        try:
            with pytest.raises(ApiError) as e:
                delivery.create_job(session, a, run_b.id, "final")
            assert e.value.detail["code"] == "E_DELIVERY_GATE", e.value.detail
            assert "不属于项目" in e.value.detail["message"], e.value.detail
            job = delivery.create_job(session, b, run_b.id, "final")
            assert job.payload_json["runId"] == run_b.id
            session.delete(job)
            session.commit()
        finally:
            from app.services.project_cleanup import delete_project
            for pid in (a.id, b.id):
                delete_project(session, pid, remove_dir=False, force=True)


def test_delivery_job_rejects_duplicate_active(tmp_path):
    """P2-05：同一 Run 不允许两个在飞交付作业（并发会 rmtree/重建同一个交付目录）。"""
    from sqlmodel import select

    from app.errors import ApiError
    from app.models import Job, Project, Run, Workflow
    from app.services import delivery, jobs as jobs_svc

    with Session(engine) as session:
        p = Project(name="judge-del-dup", root=str(tmp_path / "dup"))
        session.add(p)
        session.commit()
        session.refresh(p)
        wf = Workflow(project_id=p.id, name="main", graph_json={"meta": {}})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        try:
            job = delivery.create_job(session, p, run.id, "final")
            with pytest.raises(ApiError) as e:
                delivery.create_job(session, p, run.id, "final")
            assert e.value.detail["code"] == "E_DELIVERY_GATE", e.value.detail
            assert "已有在飞" in e.value.detail["message"], e.value.detail
            # 作业收尾（canceled）后允许再次交付
            jobs_svc.finish_job(session, job.id, "canceled", error_code="E_RUN_CANCELED")
            job2 = delivery.create_job(session, p, run.id, "final")
            jobs_svc.finish_job(session, job2.id, "canceled")
        finally:
            for j in session.exec(select(Job).where(Job.run_id == run.id,
                                                    Job.kind == "delivery")).all():
                if j.status in ("queued", "leased", "running", "retry_wait"):
                    jobs_svc.finish_job(session, j.id, "canceled")
            from app.services.project_cleanup import delete_project
            delete_project(session, p.id, remove_dir=False, force=True)


def test_gate_inherit_only_within_workflow(tmp_path):
    """P2-01：跨 Run 门继承必须限定同 workflow——不同项目撞相同 content_hash
    不许互相继承人工门批准（此前查询没过滤，注释与代码不符）。"""
    from app.engine import runengine
    from app.engine.edges import N
    from app.models import Approval, Project, Run, Workflow

    gate = next(g for g, spec in N.items()
                if spec.get("gate") == "human" and spec.get("policy", "inherit") == "inherit")
    content = "same-content-hash"

    with Session(engine) as session:
        pa = Project(name="judge-inherit-a", root=str(tmp_path / "ia"))
        pb = Project(name="judge-inherit-b", root=str(tmp_path / "ib"))
        session.add_all([pa, pb])
        session.commit()
        session.refresh(pa)
        session.refresh(pb)
        wfa = Workflow(project_id=pa.id, name="main", graph_json={"meta": {}})
        wfb = Workflow(project_id=pb.id, name="main", graph_json={"meta": {}})
        session.add_all([wfa, wfb])
        session.commit()
        session.refresh(wfa)
        session.refresh(wfb)
        run_a1 = Run(workflow_id=wfa.id, status="succeeded")
        run_a2 = Run(workflow_id=wfa.id, status="blocked")
        run_b1 = Run(workflow_id=wfb.id, status="blocked")
        session.add_all([run_a1, run_a2, run_b1])
        session.commit()
        session.refresh(run_a1)
        session.refresh(run_a2)
        session.refresh(run_b1)
        session.add(Approval(run_id=run_a1.id, gate_id=gate, decision="approved",
                             policy="inherit", content_hash=content, author="test"))
        session.commit()
        try:
            # 同 workflow 的另一个 Run：继承生效
            ok, stale = runengine._gate_valid(session, run_a2, gate, content)
            assert (ok, stale) == (True, False), (ok, stale)
            # 不同项目（不同 workflow）撞了相同 hash：不许继承
            ok, stale = runengine._gate_valid(session, run_b1, gate, content)
            assert (ok, stale) == (False, False), (ok, stale)
        finally:
            from app.services.project_cleanup import delete_project
            for pid in (pa.id, pb.id):
                delete_project(session, pid, remove_dir=False, force=True)
