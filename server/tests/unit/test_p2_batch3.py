"""P2-18/19/20（模板三连）+ P2-21（QA 失败落账）的回归测试。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from app.db import engine
from app.services import qa, templates


# ---------- P2-18：项目模板保留场景文本 ----------

def test_project_template_keeps_scene_text():
    timeline = {"fps": 24, "scenes": [
        {"id": "S01", "start": 0.0, "end": 3.0, "text": "改过的文案。",
         "meaning": "原意", "operation": "typewriter"},
        {"id": "S02", "start": 3.0, "end": 5.0, "text": ""},
    ]}
    content = templates.project_template_content(
        profile={"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
        timeline=timeline, style_id="H2", delivery={}, copy="原始 copy。",
        source_project_id=1)
    saved = content["timeline"]["scenes"]
    assert saved[0].get("text") == "改过的文案。", "timeline 上的改字必须进模板"
    assert "text" not in saved[1], "空文本场景不该带 text 键"
    # 重建：script 没有句子时用保存的文本兜底；分到句子的场景仍以 script 为准
    rebuilt = templates.build_timeline_from_content(
        content, {"sentences": []}, {"width": 1920, "height": 1080, "fps": 24})
    assert rebuilt["scenes"][0]["text"] == "改过的文案。"
    assert rebuilt["scenes"][1].get("text", "") == ""
    rebuilt2 = templates.build_timeline_from_content(
        content, {"sentences": [{"text": "新文案甲。"}, {"text": "新文案乙。"}]},
        {"width": 1920, "height": 1080, "fps": 24})
    # 分到句子的场景不落 text 键，文本按 source_span 从 script 现算（timeline_ops.scene_text）
    assert rebuilt2["scenes"][0]["source_span"] == [0]
    from app.services import timeline_ops as tl_ops
    assert tl_ops.scene_text(rebuilt2["scenes"][0],
                             {"sentences": [{"text": "新文案甲。"}, {"text": "新文案乙。"}]}
                             ) == "新文案甲。", "换文案场景不应被模板文本覆盖"


# ---------- P2-19：升级绝不删用户资产图层 ----------

def test_overlay_never_drops_user_layers():
    current = {"fps": 24, "scenes": [
        {"id": "S01", "start": 0.0, "end": 3.0, "text": "在。",
         "layers": [{"id": "L1", "assetSha": "abc", "kind": "image"}],
         "audio_layers": [{"id": "A1", "assetSha": "def"}],
         "camera": "static", "transition_duration": 0.5}]}
    # 模板场景不带任何图层 → 此前会把当前项目的 layers/audio_layers 静默 pop 掉
    content = {"schema": "filmflow.template-project/1",
               "timeline": {"fps": 24, "scenes": [{"duration": 3.0, "id": "S01"}]},
               "profile": {"width": 1920, "height": 1080, "fps": 24}}
    doc, prof = templates.overlay_template(current, content)
    s = doc["scenes"][0]
    assert s.get("layers") == current["scenes"][0]["layers"], "用户图层不许被升级删掉"
    assert s.get("audio_layers") == current["scenes"][0]["audio_layers"]
    assert "camera_keyframes" not in s, "纯视觉结构键仍按模板重置"


# ---------- P2-20：系列半途失败回滚已建项目 ----------

async def test_series_rolls_back_created_projects_on_failure(monkeypatch):
    from app.api import routes
    from app.api.schemas import SeriesCreateIn
    from app.services import project_cleanup

    saved = SimpleNamespace(id=7, name="模板T")
    calls = {"materialize": 0, "deleted": [], "canceled": []}

    async def fake_materialize(session, saved_, vars_, name, copy_):
        calls["materialize"] += 1
        if calls["materialize"] == 2:
            raise RuntimeError("E_INJECTED: 第二项失败")
        return {"project": {"id": 100 + calls["materialize"]}, "run_id": 900 + calls["materialize"],
                "missingVariables": []}

    real_delete = project_cleanup.delete_project

    def spy_delete(session_, pid, **kw):
        calls["deleted"].append(pid)
        return real_delete(session_, pid, remove_dir=False, force=True)

    def fake_cancel(rid):
        calls["canceled"].append(rid)

    monkeypatch.setattr(routes, "_materialize_saved_template", fake_materialize)
    monkeypatch.setattr(routes, "_resolve_template",
                        lambda session_, tid: ("project", {}, saved, None))
    monkeypatch.setattr(routes, "_run_ids_of_project",
                        lambda session_, pid: [900 + pid - 100])
    monkeypatch.setattr(project_cleanup, "delete_project", spy_delete)
    monkeypatch.setattr("app.engine.runengine.cancel_run", fake_cancel)

    resp = await routes.series_from_template(
        SeriesCreateIn(templateId="saved:7", name="系列", items=[{"copy": "甲"}, {"copy": "乙"}]),
        Session(engine))
    assert resp["failed"] == 1
    assert resp["created"] == 0, "半途失败的系列不许申报已创建"
    assert sorted(x["projectId"] for x in resp["rolledBack"]) == [101]
    assert calls["canceled"] == [901]
    # 第一项的 ok 结果被标记 rolledBack，不冒充成功
    assert resp["items"][0].get("rolledBack") is True


# ---------- P2-21：apply_fix 失败也要落账，报告如实反映 ----------

def test_apply_fix_failure_recorded_and_reported(tmp_path: Path, monkeypatch):
    root = tmp_path / "qa-fail"
    root.mkdir()
    proj = SimpleNamespace(id=42, root=str(root))
    issue = {"id": "iss1", "category": "text_overflow",
             "location": {"sceneId": "S01"},
             "suggestions": [{"kind": "auto", "action": "extend_scene",
                              "params": {"sceneId": "S01", "delta": 0.5}}]}

    def fake_analyze(session_, project_, run_id=None):
        return {"issues": [issue]}

    def boom(*a, **k):
        raise RuntimeError("E_INJECTED: 应用失败")

    monkeypatch.setattr(qa, "analyze", fake_analyze)
    monkeypatch.setattr(qa, "_apply", boom)
    monkeypatch.setattr(qa, "_timeline_before", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        qa.apply_fix(None, proj, "iss1", "extend_scene", {"delta": 0.5})
    rep = qa.report(proj)
    assert rep["failed"] == 1, "失败尝试必须落账"
    assert rep["successRate"] == 0.0
    assert rep["items"][0]["error"].startswith("E_INJECTED")
    # 成功一条后 successRate 如实变成 1/2
    data = qa._read_fixes(str(root))
    data["items"].append({"id": "fix_ok", "issueId": "iss1", "category": "text_overflow",
                          "action": "extend_scene", "result": "applied"})
    qa._write_fixes(str(root), data)
    rep2 = qa.report(proj)
    assert rep2["failed"] == 1 and rep2["applied"] == 1
    assert rep2["successRate"] == pytest.approx(0.5)
