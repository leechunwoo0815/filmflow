"""FR-24 渲染档位：解析/覆盖/校验、QA 策略、G07 final 校验。"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.errors import ApiError, ErrorCode
from app.services import render_profiles as rp

PROFILE = {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0, "frames": 120}


def _write_manifest(root: Path, run_id: int = 5, profile: str = "final",
                    fps: int = 24, frames: int = 120) -> None:
    p = root / "renders" / "final" / "manifest.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"schema": "filmflow.render/1", "run_id": run_id,
                             "profile": profile, "fps": fps, "frames": frames,
                             "profileSpec": {"width": 1920, "height": 1080, "fps": 24}}),
                 encoding="utf-8")


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def exec(self, _stmt):
        return _Result(self.rows)


def test_default_profiles_and_final_from_project(tmp_path):
    prof = rp.resolve(tmp_path, PROFILE)
    assert prof["source"] == "default"
    assert prof["draft"]["width"] == 960 and prof["draft"]["fps"] == 12
    assert prof["review"]["width"] == 1280 and prof["review"]["fps"] == 24
    assert prof["final"]["width"] == 1920 and prof["final"]["fps"] == 24
    assert prof["final"]["crf"] == 17


def test_file_override_draft_and_final_encoding(tmp_path):
    (tmp_path / "render.profile.json").write_text(json.dumps({
        "schema": rp.SCHEMA,
        "draft": {"width": 640, "height": 360, "fps": 10, "crf": 30, "preset": "fast"},
        "final": {"crf": 18, "preset": "slow"},
    }), encoding="utf-8")
    prof = rp.resolve(tmp_path, PROFILE)
    assert prof["source"] == "file"
    assert prof["draft"] == {"width": 640, "height": 360, "fps": 10, "crf": 30, "preset": "fast"}
    assert prof["final"]["width"] == 1920 and prof["final"]["crf"] == 18
    assert prof["final"]["preset"] == "slow"


def test_final_cannot_override_project_dimensions(tmp_path):
    (tmp_path / "render.profile.json").write_text(json.dumps({
        "schema": rp.SCHEMA, "final": {"width": 2560, "height": 1440, "fps": 24},
    }), encoding="utf-8")
    with pytest.raises(ApiError) as err:
        rp.resolve(tmp_path, PROFILE)
    assert err.value.detail["code"] == ErrorCode.E_VALIDATION


def test_low_final_rejected(tmp_path):
    with pytest.raises(ApiError) as err:
        rp.resolve(tmp_path, {"width": 1280, "height": 720, "fps": 24, "duration": 5, "frames": 120})
    assert err.value.detail["code"] == ErrorCode.E_VALIDATION


def test_imported_low_final_allowed(tmp_path):
    prof = rp.resolve(tmp_path, {"width": 1280, "height": 720, "fps": 12,
                                 "duration": 3, "frames": 36}, allow_low_final=True)
    assert prof["final"]["width"] == 1280 and prof["final"]["fps"] == 12


def test_qa_policy_by_profile():
    assert rp.qa_policy("draft")["lufs"] is False and rp.qa_policy("draft")["dups"] is False
    assert rp.qa_policy("review")["motion"] is True and rp.qa_policy("review")["ssim"] is False
    assert rp.qa_policy("final")["ssim"] is True and rp.qa_policy("final")["lufs"] is True


def test_profiles_sha_changes_with_override(tmp_path):
    a = rp.profiles_sha(rp.resolve(tmp_path, PROFILE))
    (tmp_path / "render.profile.json").write_text(json.dumps({
        "schema": rp.SCHEMA, "draft": {"width": 640, "height": 360, "fps": 10},
    }), encoding="utf-8")
    b = rp.profiles_sha(rp.resolve(tmp_path, PROFILE))
    assert a != b


def test_final_ready_accepts_current_run(tmp_path):
    _write_manifest(tmp_path, run_id=5)
    run = SimpleNamespace(id=5)
    m = rp.ensure_final_ready(_Session(), run, tmp_path, False, PROFILE)
    assert m["profile"] == "final"


def test_final_ready_allows_cached_f02_from_previous_run(tmp_path):
    _write_manifest(tmp_path, run_id=4)
    f02 = SimpleNamespace(node_id="F02", status="cached")
    m = rp.ensure_final_ready(_Session([f02]), SimpleNamespace(id=5), tmp_path, False, PROFILE)
    assert m["run_id"] == 4


def test_final_ready_rejects_missing_or_non_final(tmp_path):
    run = SimpleNamespace(id=5)
    with pytest.raises(ApiError) as err:
        rp.ensure_final_ready(_Session(), run, tmp_path, False, PROFILE)
    assert err.value.detail["code"] == ErrorCode.E_FINAL_REQUIRED
    _write_manifest(tmp_path, profile="review")
    with pytest.raises(ApiError) as err:
        rp.ensure_final_ready(_Session(), run, tmp_path, False, PROFILE)
    assert err.value.detail["code"] == ErrorCode.E_FINAL_REQUIRED


def test_final_ready_rejects_old_run_without_successful_f02(tmp_path):
    _write_manifest(tmp_path, run_id=4)
    f02 = SimpleNamespace(node_id="F02", status="failed")
    with pytest.raises(ApiError) as err:
        rp.ensure_final_ready(_Session([f02]), SimpleNamespace(id=5), tmp_path, False, PROFILE)
    assert err.value.detail["code"] == ErrorCode.E_FINAL_REQUIRED


def test_final_ready_skips_imported(tmp_path):
    assert rp.ensure_final_ready(_Session(), SimpleNamespace(id=5), tmp_path, True, PROFILE) == {}
