"""P0-2：preview 与 final 的转场映射必须完全一致。"""
from __future__ import annotations

import pytest

from app.engine.executors.pipeline import _transition_type as final_transition
from app.engine.scene.transitions import TRANSITIONS
from app.services.preview import _transition_type as preview_transition


@pytest.mark.parametrize("value", TRANSITIONS)
def test_preview_and_final_share_english_enum(value: str):
    assert preview_transition(value) == final_transition(value) == value


@pytest.mark.parametrize(("label", "expected"), [
    ("硬切", "cut"),
    ("溶解", "dissolve"),
    ("擦除", "wipe"),
    ("推镜", "push"),
    ("滑动", "paper-slide"),
    ("墨迹", "ink-bleed"),
    ("故障", "glitch"),
    ("匹配", "match-shape"),
])
def test_preview_and_final_share_chinese_labels(label: str, expected: str):
    assert preview_transition(label) == final_transition(label) == expected


def test_unknown_transition_falls_back_to_match_shape():
    assert preview_transition("unknown") == "match-shape"
    assert final_transition("unknown") == "match-shape"
