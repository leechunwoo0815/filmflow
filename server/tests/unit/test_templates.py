"""FR-37：模板变量、项目模板套用、场景模板插入、升级覆盖范围、模板锁。"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.services import templates as tpl
from app.services import timeline_ops as tl
from app.services.project_docs import build_script_doc


def _timeline() -> dict:
    return {"schema": "filmflow.timeline/2", "fps": 24, "duration": 6.0,
            "frames": 144, "layout": {"grid": {"cols": 12}},
            "scenes": [
                {"id": "S01", "start": 0.0, "end": 2.5, "source_span": [0],
                 "meaning": "开场", "operation": "标题", "camera": "缓推",
                 "camera_keyframes": [{"t": 0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0},
                                      {"t": 2.5, "zoom": 1.08, "x": 0, "y": 0, "rotate": 0}],
                 "camera_anchor": [960, 540], "transition": "cut",
                 "transition_duration": 0.5,
                 "layers": [{"id": "img01", "type": "image", "assetSha": "abc",
                             "box": [10, 20, 300, 200]}],
                 "audio_layers": [{"id": "sfx01", "assetSha": "def", "at": 0.2,
                                   "gainDb": -3, "fadeIn": 0, "fadeOut": 0}],
                 "fontSha": "font", "read_seconds": 1.0, "last_text_at": 0.0},
                {"id": "S02", "start": 2.5, "end": 6.0, "source_span": [1],
                 "meaning": "结论", "operation": "", "transition": "dissolve",
                 "transition_duration": 0.5, "read_seconds": 1.0, "last_text_at": 2.5},
            ]}


def test_substitute_and_extract_variables():
    obj = {"copy": "{{title}} 用 {{number}} 个证据，重点 {{accent}}",
           "list": ["{{title}}", 3]}
    out, missing = tpl.substitute(obj, {"title": "真话", "number": 3, "accent": "#FF665E"})
    assert out["copy"] == "真话 用 3 个证据，重点 #FF665E"
    assert out["list"] == ["真话", 3] and missing == []
    _, missing = tpl.substitute(obj, {"title": "真话"})
    assert missing == ["accent", "number"]
    assert tpl.extract_variables(obj) == ["accent", "number", "title"]


def test_project_template_roundtrip_preserves_visual_structure():
    profile = {"schema": "filmflow.profile/1", "width": 1920, "height": 1080,
               "fps": 24, "duration": 6.0, "frames": 144}
    content = tpl.project_template_content(profile=profile, timeline=_timeline(),
                                           style_id="O88", style_family="print",
                                           delivery={"schema": "filmflow.delivery/1"},
                                           copy="{{title}} 的第一条片", description="d")
    assert content["schema"] == tpl.PROJECT_SCHEMA
    assert content["variables"] == ["title"]
    assert len(content["timeline"]["scenes"]) == 2
    assert "camera_keyframes" in content["timeline"]["scenes"][0]
    script = build_script_doc("新的第一句。新的第二句。")
    timeline = tpl.build_timeline_from_content(content, script, profile)
    assert [s["id"] for s in timeline["scenes"]] == ["S01", "S02"]
    assert timeline["scenes"][0]["source_span"] == [0]
    assert timeline["scenes"][1]["source_span"] == [1]
    assert timeline["scenes"][0]["camera_keyframes"][-1]["zoom"] == 1.08
    assert timeline["scenes"][0]["layers"][0]["assetSha"] == "abc"
    assert timeline["scenes"][0]["audio_layers"][0]["at"] == 0.2


def test_scene_template_add_and_overlay():
    scene = _timeline()["scenes"][0]
    content = tpl.scene_template_content(scene, keep_text=False)
    assert content["duration"] == 2.5 and content["text"] == "新场景。"
    assert content["layers"][0]["assetSha"] == "abc"
    script = build_script_doc("一句。两句。")
    doc = {"schema": "filmflow.timeline/2", "fps": 24, "duration": 3.0, "frames": 72,
           "scenes": [{"id": "S01", "start": 0, "end": 3.0, "source_span": [0],
                       "text": "一句。", "read_seconds": 1, "last_text_at": 0}],
           "events": [], "tracks": []}
    new, meta = tl.apply(doc, script, "add_scene", {"scene": content, "index": 1})
    assert len(new["scenes"]) == 2 and new["scenes"][1]["text"] == "新场景。"
    assert new["scenes"][1]["camera_keyframes"][-1]["zoom"] == 1.08
    # 升级只覆盖视觉结构，保留当前文本/时长/id
    upgraded, prof = tpl.overlay_template(new, {"timeline": {"scenes": [
        {"camera_keyframes": [{"t": 0, "zoom": 2.0}], "transition": "wipe",
         "layers": [{"id": "L1", "type": "image", "assetSha": "new"}]}]},
        "profile": {"width": 1080, "height": 1920, "fps": 30}}, script)
    assert upgraded["scenes"][0]["text"] == "一句。"
    assert upgraded["scenes"][0]["id"] == "S01"
    assert upgraded["scenes"][0]["transition"] == "wipe"
    assert upgraded["scenes"][0]["camera_keyframes"][0]["zoom"] == 2.0
    assert prof == {"width": 1080, "height": 1920, "fps": 30}


def test_template_lock_roundtrip(tmp_path: Path):
    assert tpl.read_lock(tmp_path) == {}
    data = tpl.write_lock(tmp_path, 7, 3, ["title"])
    assert data["templateId"] == 7 and data["version"] == 3
    assert tpl.read_lock(tmp_path)["variables"] == ["title"]
