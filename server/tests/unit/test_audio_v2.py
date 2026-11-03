"""FR-35 v2：processed take、场景 Take 拼接、拍点、响度/Stem 设置。"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.errors import ApiError  # noqa: E402
from app.services import audio as au  # noqa: E402


def _wav(path: Path, seconds: float, freq: int = 220) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={seconds}", "-ac", "1", "-ar", "48000",
                    str(path)], check=True)
    return path


def _import(root: Path, wav: Path, kind: str = "voice", scene: str = "") -> dict:
    b64 = "data:audio/wav;base64," + base64.b64encode(wav.read_bytes()).decode()
    return au.import_take(root, wav.name, b64, kind, scene, wav.stem)


def test_process_take_and_processing_filter(tmp_path: Path):
    take = _import(tmp_path, _wav(tmp_path / "a.wav", 1.0))
    out = au.process_take(tmp_path, take["id"], {"highpass": True, "denoise": True})
    assert out["processedFile"].endswith(".processed.wav")
    assert (tmp_path / out["processedFile"]).exists()
    assert out["processing"]["highpass"] is True
    chain = au.processing_filter({"eq": True, "normalize": True, "deesser": True})
    assert "equalizer" in chain and "loudnorm" in chain and "deesser" in chain


def test_scene_primary_and_concat_voice(tmp_path: Path):
    a = _import(tmp_path, _wav(tmp_path / "a.wav", 1.0, 220), scene="S01")
    b = _import(tmp_path, _wav(tmp_path / "b.wav", 1.0, 440), scene="S02")
    au.set_scene_primary(tmp_path, "S01", a["id"])
    au.set_scene_primary(tmp_path, "S02", b["id"])
    scenes = [{"id": "S01", "start": 0.0, "end": 1.0},
              {"id": "S02", "start": 1.0, "end": 2.0},
              {"id": "S03", "start": 2.0, "end": 3.0}]
    out = tmp_path / "card" / "voice.wav"
    result = au.concat_voice(tmp_path, scenes, 3.0, out)
    assert result and result["picks"] == 2
    assert abs(result["duration"] - 3.0) <= 0.05
    assert au.take_for_scene(tmp_path, "S02")["id"] == b["id"]
    with pytest.raises(ApiError):
        au.set_scene_primary(tmp_path, "S01", "missing")


def test_markers_and_loudness_settings(tmp_path: Path):
    data = au.save_markers(tmp_path, [{"time": 0.5, "label": "拍点"},
                                      {"time": 0.1}], [{"time": 0.5, "strength": 1}])
    assert [m["time"] for m in data["markers"]] == [0.1, 0.5]
    assert au.load_markers(tmp_path)["onsets"]
    mix = au.save_mix(tmp_path, {"preset": "-14", "stems": {"voice": 1, "music": -10, "sfx": -120}})
    assert mix["targetLufs"] == -14.0 and mix["stems"]["music"] == -10.0
    assert au.load_mix(tmp_path)["preset"] == "-14"
    with pytest.raises(ApiError):
        au.save_mix(tmp_path, {"stems": {"music": 30}})


def test_detect_onsets_on_pulses(tmp_path: Path):
    take = _import(tmp_path, _wav(tmp_path / "pulse.wav", 1.2, 330))
    onsets = au.detect_onsets(tmp_path, take["id"])
    assert isinstance(onsets, list)
