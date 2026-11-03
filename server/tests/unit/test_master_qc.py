"""FR-28：G07 master QC 阈值与修复建议（LUFS -20 必须阻断）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.engine.executors.pipeline import _validate_master_qc  # noqa: E402

PROFILE = {"width": 1920, "height": 1080, "fps": 24, "duration": 40.0}


def qc(**over) -> dict:
    base = {"duration": 40.0, "width": 1920, "height": 1080, "fps": 24.0,
            "audio": True, "lufs": -15.9, "truePeak": -10.5}
    base.update(over)
    return base


def test_valid_master_passes():
    data = qc()
    _validate_master_qc(data, PROFILE, False, -16.0)
    assert "policy" not in data


def test_lufs_minus_20_blocks_with_fix():
    with pytest.raises(RuntimeError) as e:
        _validate_master_qc(qc(lufs=-20.0), PROFILE, False, -16.0)
    assert "E_QC_LUFS" in str(e.value)
    assert "重新混音到 -16" in str(e.value)


def test_true_peak_blocks():
    with pytest.raises(RuntimeError, match="E_QC_TRUE_PEAK"):
        _validate_master_qc(qc(truePeak=-0.5), PROFILE, False, -16.0)


def test_duration_and_audio_block():
    with pytest.raises(RuntimeError, match="E_QC_DURATION"):
        _validate_master_qc(qc(duration=39.0), PROFILE, False, -16.0)
    with pytest.raises(RuntimeError, match="E_QC_AUDIO"):
        _validate_master_qc(qc(audio=False), PROFILE, False, -16.0)


def test_imported_skips_strict_checks():
    data = qc(lufs=-30.0, width=480, height=270)
    _validate_master_qc(data, {"width": 1920, "height": 1080, "fps": 24, "duration": 39.5}, True, -16.0)
    assert data["policy"] == "imported"
