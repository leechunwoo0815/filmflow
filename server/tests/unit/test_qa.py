"""FR-39：QA 分类、安全修复、即时验证、撤销与报告。"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, select

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import engine  # noqa: E402
from app.models import DocRevision, Project, ProjectDoc  # noqa: E402
from app.services import project_docs as docs  # noqa: E402
from app.services import qa  # noqa: E402


def _project(tmp_path: Path):
    session = Session(engine)
    proj = Project(name=f"qa-{tmp_path.name}", root=str(tmp_path))
    session.add(proj)
    session.commit()
    session.refresh(proj)
    script = docs.build_script_doc("这一句需要时。第二句。")
    docs.save_doc(session, proj.id, "script", script, 0)
    docs.save_doc(session, proj.id, "profile", {
        "schema": "filmflow.profile/1", "width": 1920, "height": 1080,
        "fps": 24, "duration": 2.0, "frames": 48}, 0)
    timeline = {"schema": "filmflow.timeline/2", "fps": 24, "duration": 2.0,
                "frames": 48, "events": [], "tracks": [],
                "scenes": [{"id": "S01", "start": 0.0, "end": 1.0, "source_span": [0],
                            "text": "这一句需要时。", "read_seconds": 1.0,
                            "last_text_at": 0.0},
                           {"id": "S02", "start": 1.0, "end": 2.0, "source_span": [1],
                            "read_seconds": 1.0, "last_text_at": 1.0}]}
    docs.save_doc(session, proj.id, "timeline", timeline, 0)
    return session, proj


def _cleanup(session: Session, proj: Project) -> None:
    docs_rows = session.exec(select(ProjectDoc).where(ProjectDoc.project_id == proj.id)).all()
    for doc in docs_rows:
        for rev in session.exec(select(DocRevision).where(DocRevision.doc_id == doc.id)).all():
            session.delete(rev)
        session.delete(doc)
    session.delete(proj)
    session.commit()
    session.close()


def test_analyze_fix_verify_undo(tmp_path: Path):
    session, proj = _project(tmp_path)
    try:
        analysis = qa.analyze(session, proj)
        cats = {i["category"] for i in analysis["issues"]}
        assert "text_overflow" in cats and "license_missing" in cats
        overflow = next(i for i in analysis["issues"] if i["category"] == "text_overflow")
        assert overflow["location"]["sceneId"] == "S01"
        fix = qa.apply_fix(session, proj, overflow["id"], "extend_scene",
                           {"sceneId": "S01", "delta": 0.5})
        assert fix["result"] == "applied" and fix["verified"] is True
        after = qa.analyze(session, proj)
        assert all(i["category"] != "text_overflow" for i in after["issues"])
        report = qa.report(proj)
        assert report["applied"] == 1 and report["verified"] == 1
        entry = qa.undo_fix(session, proj, fix["id"])
        assert entry["undone"] is True
        restored = qa.analyze(session, proj)
        assert any(i["category"] == "text_overflow" for i in restored["issues"])
        assert qa.report(proj)["items"][0]["undone"] is True
    finally:
        _cleanup(session, proj)


def test_license_fix_and_scale_op(tmp_path: Path):
    session, proj = _project(tmp_path)
    try:
        analysis = qa.analyze(session, proj)
        lic = next(i for i in analysis["issues"] if i["category"] == "license_missing")
        fix = qa.apply_fix(session, proj, lic["id"], "fill_license", {
            "source": "自制", "license": "CC0", "authorized": True, "expires": ""})
        assert fix["verified"] is True
        assert not any(i["category"] == "license_missing"
                       for i in qa.analyze(session, proj)["issues"])
        overflow = next(i for i in qa.analyze(session, proj)["issues"]
                        if i["category"] == "text_overflow")
        sf = qa.apply_fix(session, proj, overflow["id"], "scale_text",
                          {"sceneId": "S01"})
        assert sf["action"] == "scale_text"
        tl = docs.doc_payload(session, proj.id, proj.root, "timeline")["content"]
        assert tl["scenes"][0]["text_scale"] == 0.9
    finally:
        _cleanup(session, proj)


def test_classify_node_messages():
    assert qa._classify_node("G06", "LUFS -12.0 超出目标") == "lufs_out"
    assert qa._classify_node("G07", "True Peak -0.4 超过 -1.0") == "tp_out"
    assert qa._classify_node("F03", "黑帧 3：[1,2,3]") == "black_frame"
    assert qa._classify_node("F03", "缺失帧 12") == "missing_frame"
    assert qa._classify_node("C03", "字体缺字：中") == "font_missing"
    assert qa._classify_node("G05", "E_LICENSE_MISSING: 缺少音乐来源") == "license_missing"
    assert qa._classify_node("C01", "引擎不可用") == "engine_unavailable"
