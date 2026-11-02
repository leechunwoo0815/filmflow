"""FR-27：混音滤镜/许可/手动对齐。"""
import json
from pathlib import Path

import pytest

from app.errors import ApiError, ErrorCode
from app.engine.executors.pipeline import _mix_filter
from app.services import audio


def test_mix_filter_sidechain_and_duration():
    f = _mix_filter(40.0, -8.0)
    assert "sidechaincompress" in f
    assert "duration=40.000" in f
    assert "duration=first" not in f
    assert "loudnorm=I=-16" in f
    assert "volume=-8.0dB" in f


def test_license_required_fields():
    ok, _ = audio.license_ok({})
    assert not ok
    ok, _ = audio.license_ok({"source": "local", "license": "CC0", "authorized": True})
    assert ok
    ok, why = audio.license_ok({"source": "local", "license": "CC0", "authorized": False})
    assert not ok and "authorized" in why


def test_manual_alignment_roundtrip(tmp_path: Path):
    data = audio.save_alignment(tmp_path, [
        {"text": "第一句。", "start": 0, "end": 2.5},
        {"text": "第二句。", "start": 2.5, "end": 5.0},
    ], "test")
    assert data["source"] == "manual" and len(data["segments"]) == 2
    loaded = audio.load_alignment(tmp_path)
    assert loaded["segments"][1]["text"] == "第二句。"
    with pytest.raises(ApiError) as err:
        audio.save_alignment(tmp_path, [{"text": "bad", "start": 3, "end": 2}])
    assert err.value.detail["code"] == ErrorCode.E_VALIDATION
