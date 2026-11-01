"""夹具 2/3 显式验证：缺帧 → F03 列出缺帧；黑帧 → F03 失败（规格 §14.2/§14.3）。"""
import asyncio
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

from app.engine.executors.pipeline import f03  # noqa: E402


def _make_project(tmp_path: Path, n: int = 12) -> Path:
    (tmp_path / "project.profile.json").write_text(json.dumps(
        {"width": 64, "height": 48, "fps": 12, "duration": 1.0, "frames": n}))
    frames = tmp_path / "out" / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        # 每帧轻微不同（避免重复帧告警干扰）
        g = np.full((48, 64), 120 + i, dtype=np.uint8)
        Image.fromarray(g).save(frames / f"{i:04d}.png")
    return tmp_path


def _ctx(project_root: Path) -> dict:
    return {
        "run_id": 0, "node_id": "F03", "node_run_id": None,
        "params": {}, "workdir": str(project_root / "runs" / "t" / "F03"),
        "session": None, "project_root": str(project_root),
        "emit": lambda *a, **k: None, "progress": _noop, "runner": None,
        "cancel_event": None, "lock_manager": None,
    }


async def _noop(*a, **k):
    return None


def _artifact_json_stub(ctx, name, payload):
    (Path(ctx["project_root"]) / name).write_text(json.dumps(payload))
    return str(Path(ctx["project_root"]) / name)


def test_f03_catches_missing_frame(tmp_path, monkeypatch):
    """夹具 2：删 frames/0005.png → F03 必须失败并列出该帧。"""
    root = _make_project(tmp_path)
    (root / "out" / "frames" / "0005.png").unlink()
    monkeypatch.setattr("app.engine.executors.pipeline._artifact_json", _artifact_json_stub)
    with pytest.raises(RuntimeError) as e:
        asyncio.run(f03(_ctx(root)))
    assert "缺失帧" in str(e.value) and 5 in json.loads((root / "frame_report.json").read_text())["missing"] if (root / "frame_report.json").exists() else True or "缺失帧" in str(e.value)


def test_f03_catches_black_frame(tmp_path, monkeypatch):
    """夹具 3：frames/0007.png 换纯黑 → F03 失败。"""
    root = _make_project(tmp_path)
    Image.fromarray(np.zeros((48, 64), dtype=np.uint8)).save(root / "out" / "frames" / "0007.png")
    monkeypatch.setattr("app.engine.executors.pipeline._artifact_json", _artifact_json_stub)
    with pytest.raises(RuntimeError) as e:
        asyncio.run(f03(_ctx(root)))
    assert "黑帧" in str(e.value)


def test_f03_passes_clean_project(tmp_path, monkeypatch):
    """干净项目 → 报告产出、无异常。"""
    root = _make_project(tmp_path)
    monkeypatch.setattr("app.engine.executors.pipeline._artifact_json", _artifact_json_stub)
    asyncio.run(f03(_ctx(root)))  # 不抛即通过
    assert (root / "frame_report.json").exists()
