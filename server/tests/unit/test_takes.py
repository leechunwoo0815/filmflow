"""FR-38：Take 元数据/评分/当前/软删除。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.errors import ApiError
from app.services import takes as tk


def test_metadata_score_and_note(tmp_path: Path):
    item = tk.item(tmp_path, 7)
    assert item["name"] == "Take 7" and item["current"] is False
    item = tk.update(tmp_path, 7, {"name": "片 A", "score": 5, "note": "节奏好"})
    assert (item["name"], item["score"], item["note"]) == ("片 A", 5, "节奏好")
    with pytest.raises(ApiError):
        tk.update(tmp_path, 7, {"score": 9})
    with pytest.raises(ApiError):
        tk.update(tmp_path, 7, {"name": " "})


def test_promote_current_and_delete_guard(tmp_path: Path):
    tk.update(tmp_path, 1, {"name": "旧版"})
    tk.update(tmp_path, 2, {"name": "新版"})
    result = tk.promote(tmp_path, 2)
    assert result["currentRunId"] == 2 and tk.current_run(tmp_path) == 2
    current = json.loads((tmp_path / "out" / "CURRENT.json").read_text(encoding="utf-8"))
    assert current["runId"] == 2
    with pytest.raises(ApiError, match="当前 Take 不能删除"):
        tk.delete(tmp_path, 2)
    assert tk.delete(tmp_path, 1)["hidden"] is True
    assert tk.item(tmp_path, 1)["hidden"] is True
    assert tk.item(tmp_path, 2)["current"] is True
