"""跨项目缓存命中：文件产物可能留在旧项目，消费者必须走上游产物路径。"""
from pathlib import Path
from types import SimpleNamespace

from app.engine.executors import _upstream_file


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows

    def exec(self, _stmt):
        return _Result(self._rows)


def test_upstream_file_prefers_existing_artifact(tmp_path: Path):
    old = tmp_path / "old" / "a.mp4"
    old.parent.mkdir()
    old.write_bytes(b"cached")
    cur = tmp_path / "cur" / "a.mp4"   # 当前项目没有文件
    ctx = {"run_id": 2, "session": _Session([
        SimpleNamespace(node_id="F04", type="MP4", path=str(old)),
        SimpleNamespace(node_id="F04", type="MP4", path=str(tmp_path / "gone.mp4")),
    ])}
    assert _upstream_file(ctx, "F04", "MP4", cur) == old


def test_upstream_file_falls_back_when_artifact_missing(tmp_path: Path):
    cur = tmp_path / "cur" / "a.mp4"
    ctx = {"run_id": 2, "session": _Session([
        SimpleNamespace(node_id="F04", type="MP4", path=str(tmp_path / "gone.mp4")),
    ])}
    assert _upstream_file(ctx, "F04", "MP4", cur) == cur
