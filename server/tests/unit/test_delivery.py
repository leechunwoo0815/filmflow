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
