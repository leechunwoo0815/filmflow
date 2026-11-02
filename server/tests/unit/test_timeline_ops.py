"""FR-32/34：时间轴 ripple/分割/合并/读时/相机/转场。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.services import timeline_ops as tl  # noqa: E402


def script() -> dict:
    texts = ["开场一句。", "前半句，后半句。", "第三句话。", "第四句话。", "结尾一句。"]
    return {"schema": "filmflow.script/1", "title": "t", "text": "".join(texts),
            "sentences": [{"id": f"L{i + 1:03d}", "text": t, "source_span": [0, 0]}
                          for i, t in enumerate(texts)]}


def doc(n: int = 5, dur: float = 8.0) -> dict:
    scenes = []
    for i in range(n):
        scenes.append({"id": f"S{i + 1:02d}", "start": i * dur, "end": (i + 1) * dur,
                       "source_span": [i] if i < 5 else [], "meaning": "", "operation": "",
                       "camera": "", "transition": "", "read_seconds": dur,
                       "last_text_at": i * dur + 3})
    return {"schema": "filmflow.timeline/2", "fps": 24, "duration": n * dur,
            "frames": round(n * dur * 24), "scenes": scenes, "events": [],
            "tracks": [{"id": "V1", "type": "video", "clips": []}]}


def test_resize_ripples_following_scenes():
    s, d = script(), doc()
    tl.resize(d, s, "S03", 26.0)
    assert d["scenes"][2]["end"] == 26.0
    assert d["scenes"][3]["start"] == 26.0
    assert d["scenes"][4]["start"] == 34.0
    assert d["duration"] == 42.0 and d["frames"] == 1008
    assert d["scenes"][3]["start"] >= d["scenes"][2]["end"]
    assert d["tracks"][0]["clips"][2]["end"] == 26.0
    assert d["events"][2]["at"] == 16.0


def test_read_overflow_blocks_and_force_allows():
    s, d = script(), doc()
    d["scenes"][1]["text"] = "这是一段很长的文案，长到两秒钟根本读不完，需要更长时间才能读完。"
    tl.normalize(d, s)
    with pytest.raises(tl.TimelineOpError) as e:
        tl.resize(d, s, "S02", 10.0)
    assert e.value.code == "E_SCENE_READ_OVERFLOW"
    tl.resize(d, s, "S02", 10.0, force=True)
    assert d["scenes"][1]["read_seconds"] == 2.0
    assert not tl.validate(d, s)["ok"]


def test_split_and_merge_preserve_text_and_cut():
    s, d = script(), doc()
    tl.split(d, s, "S02", 12.0)
    ids = [x["id"] for x in d["scenes"]]
    assert ids[:3] == ["S01", "S02", "S02b"]
    left, right = d["scenes"][1], d["scenes"][2]
    assert left["text"] and right["text"]
    assert left["end"] == 12.0 and right["start"] == 12.0
    assert right["transition"] == "cut"
    assert left["text"] + right["text"] == "前半句，后半句。"
    tl.merge(d, s, "S02", "S02b")
    assert [x["id"] for x in d["scenes"]] == ["S01", "S02", "S03", "S04", "S05"]
    assert d["scenes"][1]["text"] == "前半句，后半句。"
    assert d["duration"] == 40.0


def test_split_rejects_single_short_sentence():
    s, d = script(), doc()
    d["scenes"][0]["text"] = "短"
    tl.normalize(d, s)
    with pytest.raises(tl.TimelineOpError, match="无法在中间分割"):
        tl.split(d, s, "S01", 4.0)


def test_move_and_duplicate():
    s, d = script(), doc()
    tl.move(d, s, "S05", 0)
    assert d["scenes"][0]["id"] == "S05"
    assert d["scenes"][0]["start"] == 0 and d["scenes"][1]["start"] == 8
    tl.duplicate(d, s, "S01")
    assert [x["id"] for x in d["scenes"]][:3] == ["S05", "S01", "S01b"]
    assert d["scenes"][2]["transition"] == "cut"


def test_structural_ops_ignore_existing_read_error():
    s, d = script(), doc()
    d["scenes"][1]["text"] = "这一场文案非常非常长，八秒钟完全读不完，但相机和转场仍然应该可以继续调整，因为结构操作不应被既有读时错误连带阻断，否则用户会卡住。"
    tl.normalize(d, s)
    assert not tl.validate(d, s)["ok"]
    tl.set_camera(d, s, "S02", [{"t": 0, "zoom": 1.05, "x": 10, "y": 0, "rotate": 1}])
    tl.set_transition(d, s, "S02", "wipe", 0.5)
    assert d["scenes"][1]["camera_keyframes"][0]["zoom"] == 1.05
    assert d["scenes"][1]["transition"] == "wipe"
    assert not tl.validate(d, s)["ok"]


def test_camera_keyframes_and_preset():
    s, d = script(), doc()
    kfs = [{"t": 0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0},
           {"t": 4, "zoom": 1.15, "x": 80, "y": -10, "rotate": 2},
           {"t": 8, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0}]
    tl.set_camera(d, s, "S02", kfs, [800, 500])
    assert d["scenes"][1]["camera_keyframes"][1]["zoom"] == 1.15
    assert d["scenes"][1]["camera_anchor"] == [800.0, 500.0]
    preset = tl.camera_preset("push-in", 8)
    assert preset["keyframes"][-1]["zoom"] == 1.08
    tl.set_camera(d, s, "S03", preset["keyframes"], preset["anchor"])
    with pytest.raises(tl.TimelineOpError, match="zoom"):
        tl.set_camera(d, s, "S04", [{"t": 0, "zoom": 9}])
    with pytest.raises(tl.TimelineOpError, match="rotate"):
        tl.set_camera(d, s, "S04", [{"t": 0, "zoom": 1, "rotate": 90}])


def test_transition_and_unknown():
    s, d = script(), doc()
    tl.set_transition(d, s, "S03", "wipe", 0.8)
    assert d["scenes"][2]["transition"] == "wipe"
    assert d["scenes"][2]["transition_duration"] == 0.8
    with pytest.raises(tl.TimelineOpError, match="未知转场"):
        tl.set_transition(d, s, "S03", "star-wars")


def test_hundred_scenes_fast():
    s, d = script(), doc(100, 2.0)
    t0 = time.perf_counter()
    tl.resize(d, s, "S50", 100.5)
    tl.move(d, s, "S100", 0)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2, elapsed
    assert len(d["scenes"]) == 100
    assert d["scenes"][0]["id"] == "S100"
    assert d["duration"] > 200
