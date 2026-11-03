"""FR-22 规划器：改一句只脏 S03；改时长级联；改转场脏前后两场。"""
from app.engine.render_manifest import (
    build_manifest,
    build_plan,
    dirty_ranges,
    plan_dirty,
)

PROFILE = {"width": 1920, "height": 1080, "fps": 24, "duration": 39.5, "frames": 948}
SCENES = [
    {"id": "S01", "start": 0.0, "end": 8.0},
    {"id": "S02", "start": 8.0, "end": 16.0},
    {"id": "S03", "start": 16.0, "end": 24.0},
    {"id": "S04", "start": 24.0, "end": 31.0},
    {"id": "S05", "start": 31.0, "end": 39.5},
]
TRANS = [
    {"from": "S01", "to": "S02", "at": 8.0, "duration": 0.5, "type": "match-shape"},
    {"from": "S02", "to": "S03", "at": 16.0, "duration": 0.5, "type": "match-shape"},
    {"from": "S03", "to": "S04", "at": 24.0, "duration": 0.5, "type": "match-shape"},
    {"from": "S04", "to": "S05", "at": 31.0, "duration": 0.5, "type": "match-shape"},
]


def _programs(text="正文"):
    return {s["id"]: {"id": s["id"], "duration": s["end"] - s["start"], "text": text}
            for s in SCENES}


def _prev_done(plan):
    for s in plan:
        s["status"] = "done"
    return build_manifest(1, "final", PROFILE, plan, [])


def test_change_s03_text_only_dirty_s03_and_overlap():
    plan = build_plan(SCENES, _programs(), TRANS, PROFILE, "t", "e", "f")
    prev = _prev_done(plan)
    progs = _programs()
    progs["S03"] = {**progs["S03"], "text": "改了一句"}
    plan2 = build_plan(SCENES, progs, TRANS, PROFILE, "t", "e", "f")
    plan_dirty(plan2, prev, "final", PROFILE)
    assert [s["id"] for s in plan2 if s["status"] == "dirty"] == ["S03"]
    ranges = dirty_ranges(plan2, PROFILE["frames"])
    assert ranges == [(384, 588)]
    rendered = sum(b - a for a, b in ranges)
    assert rendered == 204
    assert rendered / PROFILE["frames"] <= 0.25


def test_change_s03_duration_cascades_to_end():
    plan = build_plan(SCENES, _programs(), TRANS, PROFILE, "t", "e", "f")
    prev = _prev_done(plan)
    scenes = [dict(s) for s in SCENES]
    scenes[2]["end"] = 26.0
    scenes[3]["start"] = 26.0
    scenes[3]["end"] = 33.0
    scenes[4]["start"] = 33.0
    scenes[4]["end"] = 39.5
    trans = [dict(t) for t in TRANS]
    trans[2]["at"] = 26.0
    trans[3]["at"] = 33.0
    plan2 = build_plan(scenes, _programs(), trans, PROFILE, "t", "e", "f")
    plan_dirty(plan2, prev, "final", PROFILE)
    assert [s["id"] for s in plan2 if s["status"] == "dirty"] == ["S03", "S04", "S05"]


def test_change_transition_dirties_both_sides():
    plan = build_plan(SCENES, _programs(), TRANS, PROFILE, "t", "e", "f")
    prev = _prev_done(plan)
    trans = [dict(t) for t in TRANS]
    trans[1]["type"] = "wipe"
    plan2 = build_plan(SCENES, _programs(), trans, PROFILE, "t", "e", "f")
    plan_dirty(plan2, prev, "final", PROFILE)
    assert {s["id"] for s in plan2 if s["status"] == "dirty"} == {"S02", "S03"}


def test_no_manifest_means_all_dirty():
    plan = build_plan(SCENES, _programs(), TRANS, PROFILE, "t", "e", "f")
    plan_dirty(plan, None, "final", PROFILE)
    assert all(s["status"] == "dirty" for s in plan)
    ranges = dirty_ranges(plan, PROFILE["frames"])
    assert ranges == [(0, 948)]


def test_build_manifest_accepts_completed_ranges_with_ms():
    plan = build_plan(SCENES, _programs(), TRANS, PROFILE, "t", "e", "f")
    m = build_manifest(1, "final", PROFILE, plan, [(0, 120, 900), (120, 240, 800)])
    assert m["renderedFrames"] == 240
    assert m["reusedFrames"] == PROFILE["frames"] - 240
