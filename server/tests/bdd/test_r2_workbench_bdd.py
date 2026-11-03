"""BDD 绑定：R2.0 四条工作台主链路（服务级，不启动 Chrome）。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))
FEATURES = SERVER.parent / "bdd" / "features"

from pytest_bdd import given, scenarios, then, when

scenarios(str(FEATURES / "r2-workbench.feature"))

_ctx: dict = {}


@given("5 秒文案「风从纸上起。纸不动，风先动。」", target_fixture="doc_ctx")
def five_second_doc():
    from app.services.project_docs import build_script_doc, build_timeline_doc
    script = build_script_doc("风从纸上起。纸不动，风先动。", "BDD")
    profile = {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0}
    timeline = build_timeline_doc(script, profile)
    _ctx.update(script=script, timeline=timeline, profile=profile)
    return _ctx


@when("编译全部场景程序")
def compile_all():
    from app.engine.scene.compiler import compile_scene
    _ctx["programs"] = [compile_scene(s, _ctx["script"], {}, _ctx["profile"], motion=False)
                        for s in _ctx["timeline"]["scenes"]]


@then("每个场景程序包含用户原文")
def programs_have_copy():
    texts = "".join(p["meta"].get("text", "") for p in _ctx["programs"])
    for s in ("风从纸上起。", "纸不动，风先动。"):
        assert s in texts


@then("时间轴有 2 个场景")
def timeline_two_scenes():
    assert len(_ctx["timeline"]["scenes"]) == 2


@given("40 秒 5 场时间轴", target_fixture="inc_ctx")
def forty_second_timeline():
    scenes = [{"id": f"S{i:02d}", "start": (i - 1) * 8.0, "end": i * 8.0} for i in range(1, 6)]
    _ctx["scenes"] = scenes
    _ctx["profile40"] = {"width": 1920, "height": 1080, "fps": 24, "duration": 40.0, "frames": 960}
    _ctx["prev_programs"] = {s["id"]: {"id": s["id"], "duration": 8, "text": "原文"} for s in scenes}
    return _ctx


@when("只修改 S03 的一句文案")
def change_s03():
    from app.engine.render_manifest import build_manifest, build_plan, dirty_ranges, plan_dirty
    scenes, profile = _ctx["scenes"], _ctx["profile40"]
    prev_plan = build_plan(scenes, _ctx["prev_programs"], [], profile, "t", "e", "f")
    for s in prev_plan:
        s["status"] = "done"
    prev = build_manifest(1, "final", profile, prev_plan, [])
    progs = dict(_ctx["prev_programs"])
    progs["S03"] = {**progs["S03"], "text": "改了一句"}
    plan = build_plan(scenes, progs, [], profile, "t", "e", "f")
    plan_dirty(plan, prev, "final", profile)
    _ctx["plan"] = plan
    _ctx["ranges"] = dirty_ranges(plan, 960)


@then("只有 S03 及其离场转场帧脏")
def only_s03_dirty():
    assert [s["id"] for s in _ctx["plan"] if s["status"] == "dirty"] == ["S03"]
    assert _ctx["ranges"] == [(384, 576)] or all(384 <= a and b <= 576 for a, b in _ctx["ranges"])


@then("渲染帧数不超过总帧数的 25%")
def frame_ratio():
    rendered = sum(b - a for a, b in _ctx["ranges"])
    assert rendered <= 960 * 0.25


@given("队列中有 batch 与 preview 两种 Job", target_fixture="queue_ctx")
def jobs_in_queue():
    from sqlmodel import Session, delete

    from app.db import engine
    from app.models import Job
    from app.services import jobs as jobs_svc
    with Session(engine) as s:
        s.exec(delete(Job).where(Job.kind.in_(("bdd_batch", "bdd_preview"))))  # type: ignore[arg-type]
        s.commit()
        batch = jobs_svc.create_job(s, "bdd_batch", 40, {})
        preview = jobs_svc.create_job(s, "bdd_preview", 100, {})
        _ctx["batch_id"], _ctx["preview_id"] = batch.id, preview.id
        _ctx["summary"] = jobs_svc.queue_summary(s)
    return _ctx


@then("preview Job 的优先级是 100 且排在 batch 前面")
def priority_order():
    ids = [j["id"] for j in _ctx["summary"]["active"]]
    assert _ctx["summary"]["priorities"]["preview"] == 100
    assert ids.index(_ctx["preview_id"]) < ids.index(_ctx["batch_id"])


def _write_manifest(root: Path, profile_name: str):
    p = root / "renders" / "final" / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": "filmflow.render/1", "run_id": 7,
                             "profile": profile_name, "fps": 24, "frames": 120,
                             "profileSpec": {"width": 1920, "height": 1080, "fps": 24}}),
                 encoding="utf-8")


@given("最新 manifest 是 final", target_fixture="final_ctx")
def final_manifest(tmp_path):
    from app.services.render_profiles import ensure_final_ready
    _write_manifest(tmp_path, "final")
    _ctx["root"] = tmp_path
    _ctx["run"] = SimpleNamespace(id=7)
    _ctx["profile"] = {"width": 1920, "height": 1080, "fps": 24, "duration": 5, "frames": 120}
    _ctx["ensure"] = ensure_final_ready
    return _ctx


@then("允许打包 final")
def final_allowed():
    assert _ctx["ensure"](None, _ctx["run"], _ctx["root"], False, _ctx["profile"])["profile"] == "final"


@when("最新 manifest 是 review")
def review_manifest():
    _write_manifest(_ctx["root"], "review")


@then("打包被 E_FINAL_REQUIRED 拒绝")
def review_rejected():
    from app.errors import ApiError, ErrorCode
    with pytest.raises(ApiError) as err:
        _ctx["ensure"](None, _ctx["run"], _ctx["root"], False, _ctx["profile"])
    assert err.value.detail["code"] == ErrorCode.E_FINAL_REQUIRED
