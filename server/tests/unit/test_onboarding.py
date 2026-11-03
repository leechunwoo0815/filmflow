"""FR-31：本地标题候选、只读示例目录、音频占位生命周期。"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.services import audio as audio_svc
from app.services import onboarding


def test_title_candidates_use_user_copy():
    copy = "很多工作不是难，是重复。把重复交给工具，人才有时间思考。今天就开始。"
    items = onboarding.title_candidates(copy)
    assert len(items) == 3
    assert len(set(items)) == 3
    assert items[0] in copy
    assert all("风从纸上起" not in x for x in items)


def test_title_candidates_empty_and_duplicates():
    assert len(onboarding.title_candidates("")) == 3
    assert len(set(onboarding.title_candidates("同一句话"))) == 3


def test_examples_are_readonly_catalog():
    items = onboarding.load_examples()
    assert {x["id"] for x in items} >= {"voice15", "product40"}
    for item in items:
        assert item["readonly"] is True
        assert item["copy"]
        profile = onboarding.example_profile(item)
        assert profile["frames"] == round(profile["duration"] * profile["fps"])
    assert onboarding.example("missing") is None


def test_audio_placeholder_lifecycle(tmp_path: Path):
    saved = audio_svc.save_placeholder(tmp_path, "voice", 15, "voice15")
    assert saved["duration"] == 15.0
    assert audio_svc.load_placeholder(tmp_path)["source"] == "voice15"
    audio_svc.clear_placeholder(tmp_path, "music")
    assert audio_svc.load_placeholder(tmp_path) is not None
    audio_svc.clear_placeholder(tmp_path, "voice")
    assert audio_svc.load_placeholder(tmp_path) is None
