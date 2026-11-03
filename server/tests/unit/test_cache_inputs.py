"""P1-02/03/04：缓存键必须覆盖外部文件、引擎包与项目音频输入。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.engine import runengine
from app.services import engines as engines_svc


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "card").mkdir(parents=True)
    return root


def test_external_input_hashes_tracks_copy(tmp_path: Path):
    root = _project(tmp_path)
    copy = root / "card" / "copy.txt"
    copy.write_text("第一版", encoding="utf-8")
    before = runengine._external_input_hashes(str(root), "A01")
    copy.write_text("第二版", encoding="utf-8")
    after = runengine._external_input_hashes(str(root), "A01")
    assert before["_external:A01"] != after["_external:A01"]


def test_root_node_external_hash_is_reachable(tmp_path: Path):
    root = _project(tmp_path)
    (root / "card" / "copy.txt").write_text("文案", encoding="utf-8")
    out = runengine._upstream_hashes(object(), 1, "A01", {}, str(root))
    assert "_external:A01" in out


def test_external_input_hashes_tracks_style_library(tmp_path: Path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "_统计.json").write_text('{"total": 1}', encoding="utf-8")
    prompt = lib / "O01.md"
    prompt.write_text("第一版提示词", encoding="utf-8")
    monkeypatch.setattr(runengine, "settings", SimpleNamespace(style_library_root=lib))
    root = _project(tmp_path)
    before = runengine._external_input_hashes(str(root), "A03")
    prompt.write_text("第二版提示词", encoding="utf-8")
    after = runengine._external_input_hashes(str(root), "A03")
    assert before["_external:A03"] != after["_external:A03"]


def test_project_inputs_track_alignment_and_audio_takes(tmp_path: Path):
    root = _project(tmp_path)
    alignment = root / "card" / "alignment.manual.json"
    alignment.write_text('{"segments": []}', encoding="utf-8")
    before = runengine._project_input_hashes(str(root), "G02")
    alignment.write_text('{"segments": [{"start": 0}]}', encoding="utf-8")
    after = runengine._project_input_hashes(str(root), "G02")
    assert before != after

    audio_dir = root / "card" / "audio"
    audio_dir.mkdir()
    (root / "card" / "audio.json").write_text('{"takes": []}', encoding="utf-8")
    wav = audio_dir / "music.wav"
    wav.write_bytes(b"take-one")
    before = runengine._project_input_hashes(str(root), "G04")
    assert "card/audio.json" in before and "card/audio/music.wav" in before
    wav.write_bytes(b"take-two")
    after = runengine._project_input_hashes(str(root), "G04")
    assert before["card/audio/music.wav"] != after["card/audio/music.wav"]

    params = runengine._cache_params_for_node(
        SimpleNamespace(), SimpleNamespace(graph_json={}), "G04", {}, str(root), {})
    assert "card/audio.json" in params["projectInputsSha"]
    assert "card/audio/music.wav" in params["projectInputsSha"]


def test_engine_pack_sha_changes_with_engine_content(tmp_path: Path, monkeypatch):
    wf = SimpleNamespace(graph_json={"meta": {"style_decision": {"primary": "O88"}}})

    class _Session:
        def get(self, _model, _key):
            return SimpleNamespace(family="print")

    monkeypatch.setattr(engines_svc, "engine_for_family",
                        lambda family: {"engine_id": "riso", "sha256": "sha-one"})
    assert runengine._engine_pack_sha(_Session(), wf, str(tmp_path)) == "sha-one"
    monkeypatch.setattr(engines_svc, "engine_for_family",
                        lambda family: {"engine_id": "riso", "sha256": "sha-two"})
    assert runengine._engine_pack_sha(_Session(), wf, str(tmp_path)) == "sha-two"


def test_c01_cache_params_include_engine_sha(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runengine, "_engine_pack_sha", lambda *_: "engine-sha")
    wf = SimpleNamespace(graph_json={})
    params = runengine._cache_params_for_node(
        SimpleNamespace(), wf, "C01", {}, str(tmp_path), {})
    assert params["enginePackSha"] == "engine-sha"
