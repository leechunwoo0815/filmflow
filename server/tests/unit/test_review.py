"""FR-26 静帧审阅：长场景多帧、16 宫格覆盖全部场景。"""
from app.engine.executors.pipeline import _contact_sheet_picks, _still_times


def test_short_scene_one_still():
    times = _still_times(0.0, 5.0)
    assert times == [2.5]


def test_long_scene_six_stills_and_bounds():
    times = _still_times(10.0, 20.0)
    assert len(times) == 6
    assert all(10.0 <= t <= 20.0 for t in times)
    assert times == sorted(set(times))


def test_contact_sheet_covers_all_scenes_with_limit():
    items = []
    for sid in ("S01", "S02", "S03", "S04", "S05"):
        for i in range(6):
            items.append((sid, round(i * 0.5, 2), f"/tmp/{sid}-{i}.png", f"sha{sid}{i}"))
    picks = _contact_sheet_picks(items, 16)
    assert len(picks) == 16
    assert {p[0] for p in picks} == {"S01", "S02", "S03", "S04", "S05"}
    # 每场第一张必须入选，保证 contact sheet 含全部场景
    firsts = [next(x for x in items if x[0] == sid) for sid in
              ("S01", "S02", "S03", "S04", "S05")]
    assert all(f in picks for f in firsts)
