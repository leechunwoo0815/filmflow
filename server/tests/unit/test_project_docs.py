"""FR-25：文档 hash/版本/409/回滚；Run 快照不可变。"""
import json
from pathlib import Path

import pytest
from sqlmodel import Session

from app.db import engine
from app.engine.snapshot import ensure_run_snapshot
from app.errors import ApiError
from app.models import Project, Run, Workflow
from app.services import project_docs as docs


def _project(tmp_path: Path, name: str) -> tuple[int, int, Path]:
    root = tmp_path / name
    (root / "card").mkdir(parents=True)
    with Session(engine) as s:
        p = Project(name=name, root=str(root))
        s.add(p)
        s.commit()
        s.refresh(p)
        wf = Workflow(project_id=p.id, graph_json={"meta": {}, "params": {}, "positions": {}})
        s.add(wf)
        s.commit()
        s.refresh(wf)
        run = Run(workflow_id=wf.id)
        s.add(run)
        s.commit()
        s.refresh(run)
        return p.id, run.id, root


def test_script_doc_offsets_and_timeline_duration(tmp_path: Path):
    text = "风从纸上起。纸不动，风先动。"
    script = docs.build_script_doc(text)
    assert [s["text"] for s in script["sentences"]] == ["风从纸上起。", "纸不动，风先动。"]
    assert script["sentences"][0]["source_span"] == [0, text.index("纸不动")]
    timeline = docs.build_timeline_doc(script, {"fps": 24, "duration": 5.0})
    assert len(timeline["scenes"]) == 2
    assert abs(sum(s["end"] - s["start"] for s in timeline["scenes"]) - 5.0) < 0.01
    assert all(s["meaning"] == "" for s in timeline["scenes"])
    assert timeline["scenes"][0]["source_span"] == [0]
    assert timeline["scenes"][1]["source_span"] == [1]
    assert timeline["scenes"][0]["last_text_at"] == timeline["scenes"][0]["start"]
    assert timeline["frames"] == 120


def test_doc_versions_conflict_and_restore(tmp_path: Path):
    project_id, _, _ = _project(tmp_path, "doc-project")
    content = docs.build_script_doc("第一句。第二句。")
    with Session(engine) as s:
        doc, diff = docs.save_doc(s, project_id, "script", content, 0, "tester")
        assert doc.version == 1 and diff
        content2 = {**content, "text": content["text"] + "第三句。"}
        content2["sentences"] = content["sentences"] + [{"id": "L003", "text": "第三句。", "source_span": [0, 0]}]
        doc2, _ = docs.save_doc(s, project_id, "script", content2, 1, "tester")
        assert doc2.version == 2
        with pytest.raises(ApiError) as e:
            docs.save_doc(s, project_id, "script", content, 1, "tester")
        assert e.value.status_code == 409
        versions = docs.list_versions(s, doc2)
        assert [v["version"] for v in versions] == [2, 1]
        restored, _ = docs.restore_doc(s, project_id, "script", 1, "tester")
        assert restored.version == 3
        assert restored.content_json["text"] == content["text"]
        diff = docs.version_diff(s, restored, 1, 3)
        assert diff == []


def test_default_timeline_uses_profile_duration(tmp_path: Path):
    project_id, _, root = _project(tmp_path, "default-project")
    (root / "card" / "copy.txt").write_text("风从纸上起。纸不动，风先动。", encoding="utf-8")
    (root / "project.profile.json").write_text(json.dumps(
        {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0}), encoding="utf-8")
    with Session(engine) as s:
        payload = docs.doc_payload(s, project_id, str(root), "timeline")
        assert payload["version"] == 0
        assert abs(payload["content"]["duration"] - 5.0) < 0.01


def test_run_snapshot_new_project_is_immutable(tmp_path: Path):
    project_id, run_id, root = _project(tmp_path, "snap-project")
    (root / "card" / "copy.txt").write_text("风从纸上起。纸不动，风先动。", encoding="utf-8")
    (root / "project.profile.json").write_text(json.dumps(
        {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0}), encoding="utf-8")
    with Session(engine) as s:
        run = s.get(Run, run_id)
        snap = ensure_run_snapshot(s, run, str(root))
        sha = snap["doc_snapshot_sha"]
        assert snap["imported"] is False
        assert (root / "runs" / str(run_id) / "docs" / "script.doc.json").exists()
        assert (root / "runs" / str(run_id) / "docs" / "timeline.doc.json").exists()
        (root / "card" / "copy.txt").write_text("改过的文案。", encoding="utf-8")
        again = ensure_run_snapshot(s, run, str(root))
        assert again["doc_snapshot_sha"] == sha
        assert again["docs"]["script"]["content"]["text"].startswith("风从纸上起")


def test_run_snapshot_imported_copies_task(tmp_path: Path):
    project_id, run_id, root = _project(tmp_path, "snap-imported")
    task = {"fps": 24, "width": 1920, "height": 1080, "film": {"duration": 39.5, "frames": 948},
            "scenes": [], "events": []}
    (root / "card" / "task.json").write_text(json.dumps(task), encoding="utf-8")
    with Session(engine) as s:
        wf = s.exec(__import__("sqlmodel").select(Workflow).where(Workflow.project_id == project_id)).first()
        wf.graph_json = {"meta": {"imported": True}, "params": {}, "positions": {}}
        s.add(wf)
        s.commit()
        run = s.get(Run, run_id)
        snap = ensure_run_snapshot(s, run, str(root))
        assert snap["imported"] is True
        assert snap["profile"]["duration"] == 39.5
        assert (root / "runs" / str(run_id) / "docs" / "task.json").exists()
