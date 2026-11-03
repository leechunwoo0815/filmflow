"""FR-33：批注 CRUD/resolve/决议/导出导入去重/审片包。"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.errors import ApiError
from app.services import review_comments as rv


def _add(root: Path, i: int = 0) -> dict:
    return rv.add(root, {"frame": i * 24, "time": float(i), "sceneId": "S01",
                         "kind": "rect" if i % 2 == 0 else "text", "category": "must",
                         "body": f"批注 {i}", "geometry": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}})


def test_comments_resolve_reply_and_decisions(tmp_path: Path):
    c = _add(tmp_path, 1)
    assert c["status"] == "open"
    rv.update(tmp_path, c["id"], {"status": "resolved", "reply": "已改", "author": "b"})
    data = rv.load(tmp_path)
    assert data["comments"][0]["status"] == "resolved"
    assert data["comments"][0]["replies"][0]["body"] == "已改"
    rv.decide(tmp_path, {"sceneId": "S01", "decision": "needs_changes"})
    rv.decide(tmp_path, {"decision": "approved"})
    summary = rv.summary(tmp_path)
    assert summary["total"] == 1 and summary["resolved"] == 1
    assert summary["overall"]["decision"] == "approved"


def test_invalid_comment_payload(tmp_path: Path):
    with pytest.raises(ApiError):
        rv.add(tmp_path, {"frame": 0, "time": 0, "kind": "circle", "body": "x"})
    with pytest.raises(ApiError):
        rv.add(tmp_path, {"frame": 0, "time": 0, "body": "x", "category": "bad"})


def test_export_import_dedupe(tmp_path: Path):
    for i in range(3):
        _add(tmp_path, i)
    exported = rv.load(tmp_path)
    # 清空后导入
    rv.save(tmp_path, {"comments": [], "decisions": {"scenes": {}, "overall": None}})
    result = rv.import_json(tmp_path, exported)
    assert result == {"added": 3, "skipped": 0, "total": 3}
    result = rv.import_json(tmp_path, exported)
    assert result["added"] == 0 and result["skipped"] == 3
    csv_text = rv.export_csv(tmp_path)
    assert csv_text.count("\n") >= 4 and "批注 0" in csv_text


def test_package_contains_video_json_readme(tmp_path: Path):
    _add(tmp_path, 1)
    video = tmp_path / "review.mp4"
    video.write_bytes(b"fake-mp4")
    result = rv.package(tmp_path, video, "测试片")
    assert result["comments"] == 1 and result["bytes"] > 0
    with zipfile.ZipFile(result["path"]) as z:
        names = set(z.namelist())
        assert {"review.mp4", "review.json", "README.txt"} <= names
        meta = json.loads(z.read("review.json"))
        assert meta["comments"][0]["body"] == "批注 1"
