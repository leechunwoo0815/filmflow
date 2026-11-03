"""Scene DSL 编译器：文本来自 script、base/motion 静态一致、12 组件 schema。"""
from app.engine.scene.canonical import canonical
from app.engine.scene.compiler import compile_scene, static_program
from app.engine.scene.components import COMPONENT_NAMES, COMPONENTS, validate_props
from app.engine.scene.schema import validate_program
from app.services.project_docs import build_script_doc

TOKENS = {
    "visual": {"palette": ["#F4EEE2", "#3D5588", "#FF665E", "#FFB511"],
               "screen": {"angle": 15, "period": 7}},
    "type_spec": {"family": "Noto Sans SC", "title_range": [72, 120],
                  "line_height": 1.35, "letter_spacing": 0},
}
PROFILE = {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0}


def _scene():
    return {"id": "S01", "start": 0.0, "end": 2.5, "meaning": "", "operation": "",
            "source_span": [0], "last_text_at": 0.0, "read_seconds": 1.0}


def test_compiler_uses_user_text_and_static_identity():
    script = build_script_doc("风从纸上起。纸不动，风先动。")
    base = compile_scene(_scene(), script, TOKENS, PROFILE, motion=False)
    motion = compile_scene(_scene(), script, TOKENS, PROFILE,
                           camera={"zoom": [[0, 1.0], [2.5, 1.05]], "pan": [[0, 0], [2.5, 20]]},
                           motion=True)
    title = next(layer for layer in base["layers"] if layer["id"] == "L_title")
    assert title["content"] == "风从纸上起。"
    assert static_program(base) == static_program(motion)
    assert "camera" not in base and motion["camera"]["keyframes"][-1]["zoom"] == 1.05
    assert not validate_program(base) and not validate_program(motion)


def test_compiler_prefers_scene_text_override():
    script = build_script_doc("原始文案。")
    scene = {**_scene(), "text": "时间轴改写后的文案。"}
    prog = compile_scene(scene, script, TOKENS, PROFILE)
    title = next(layer for layer in prog["layers"] if layer["id"] == "L_title")
    assert title["content"] == "时间轴改写后的文案。"


def test_camera_keyframes_and_rotate_pass_through():
    script = build_script_doc("相机测试。")
    camera = {"anchor": [800, 500], "keyframes": [
        {"t": 0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0},
        {"t": 1.2, "zoom": 1.2, "x": 60, "y": -8, "rotate": 3},
        {"t": 2.5, "zoom": 1.05, "x": 0, "y": 0, "rotate": 0}]}
    prog = compile_scene(_scene(), script, TOKENS, PROFILE, camera=camera, motion=True)
    assert prog["camera"]["anchor"] == [800, 500]
    assert prog["camera"]["keyframes"][1]["rotate"] == 3
    assert prog["camera"]["keyframes"][1]["zoom"] == 1.2
    assert not validate_program(prog)


def test_font_family_strips_weight_suffix():
    script = build_script_doc("风从纸上起。")
    tokens = {**TOKENS, "type_spec": {**TOKENS["type_spec"], "family": "Noto Sans SC 900/500"}}
    prog = compile_scene(_scene(), script, tokens, PROFILE)
    title = next(layer for layer in prog["layers"] if layer["id"] == "L_title")
    assert title["style"]["font"] == "Noto Sans SC"


def test_vertical_layout_is_reflowed():
    script = build_script_doc("风从纸上起。")
    profile = {"width": 1080, "height": 1920, "fps": 24, "duration": 2.5}
    prog = compile_scene(_scene(), script, TOKENS, profile, layout="9x16")
    assert prog["canvas"]["w"] == 1080 and prog["canvas"]["h"] == 1920
    title = next(layer for layer in prog["layers"] if layer["id"] == "L_title")
    assert title["box"][2] <= 880
    assert not validate_program(prog)


def test_text_scale_reduces_title_size():
    script = build_script_doc("风从纸上起。")
    base = compile_scene(_scene(), script, TOKENS, PROFILE)
    scaled = compile_scene({**_scene(), "text_scale": 0.9}, script, TOKENS, PROFILE)
    b = next(layer for layer in base["layers"] if layer["id"] == "L_title")
    s = next(layer for layer in scaled["layers"] if layer["id"] == "L_title")
    assert s["style"]["size"] == round(b["style"]["size"] * 0.9)
    assert not validate_program(scaled)


def test_compiler_is_deterministic():
    script = build_script_doc("一句话。")
    a = compile_scene(_scene(), script, TOKENS, PROFILE)
    b = compile_scene(_scene(), script, TOKENS, PROFILE)
    assert canonical(a) == canonical(b)
    assert a["program_sha"] == b["program_sha"]


def test_all_12_components_have_defaults_and_validate():
    assert len(COMPONENT_NAMES) == 12 == len(COMPONENTS)
    for name in COMPONENT_NAMES:
        assert COMPONENTS[name]["props"]
        assert not validate_props(name, COMPONENTS[name]["props"])
    assert validate_props("paper-card", {"x": 1})
    assert validate_props("nope", {})


def test_unknown_component_is_rejected():
    script = build_script_doc("一句话。")
    scene = _scene()
    program = compile_scene(scene, script, TOKENS, PROFILE)
    program["layers"][0]["component"] = "nope"
    assert any("未知" in e for e in validate_program(program))
