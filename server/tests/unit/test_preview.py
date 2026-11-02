"""FR-23 预览：水印、缓存、base/motion program 编译。"""
import io
from pathlib import Path

from PIL import Image

from app.engine.scene.canonical import content_hash
from app.services import preview as pv
from app.services.project_docs import build_script_doc


def _ctx(text="风从纸上起。纸不动，风先动。"):
    script = build_script_doc(text, "测试")
    scenes = [
        {"id": "S01", "start": 0.0, "end": 2.5, "source_span": [0], "meaning": ""},
        {"id": "S02", "start": 2.5, "end": 5.0, "source_span": [1], "meaning": ""},
    ]
    return pv.PreviewContext(
        project_id=1, root=Path("/tmp"), profile={"width": 1920, "height": 1080,
                                                   "fps": 24, "duration": 5.0, "frames": 120},
        script=script, timeline={"scenes": scenes}, scenes=scenes,
        transitions=[], tokens={}, tokens_sha=content_hash({}), engine_id="riso",
        engine_sha="e", font_css="", font_sha="f", imported=False)


def test_still_uses_base_program_motion_adds_camera():
    ctx = _ctx()
    still = pv.build_programs(ctx, motion=False, scene_id="S01")
    motion = pv.build_programs(ctx, motion=True)
    assert "camera" not in still[0]["program"]
    assert "camera" in motion[0]["program"]
    assert still[0]["program"]["layers"] == motion[0]["program"]["layers"]
    assert len(motion) == 2


def test_text_change_changes_program_sha():
    a = pv.build_programs(_ctx(), motion=True)
    b = pv.build_programs(_ctx("风从纸上起。纸不动，字先动。"), motion=True)
    assert a[0]["program"]["program_sha"] == b[0]["program"]["program_sha"]
    assert a[1]["program"]["program_sha"] != b[1]["program"]["program_sha"]


def test_preview_cache_hit_and_lru_evict(tmp_path):
    cache = pv.PreviewCache(9, limit_bytes=250, cache_root=tmp_path / "cache")
    for i in range(3):
        cache.put("sceneA", f"k{i}", b"x" * 100)
    assert cache.get("sceneA", "k2") == b"x" * 100
    cache.evict()
    st = cache.stats()
    assert st["bytes"] <= 250
    assert cache.get("sceneA", "missing") is None


def test_watermark_visible_and_tagged():
    buf = io.BytesIO()
    Image.new("RGB", (320, 180), (244, 238, 226)).save(buf, format="PNG")
    out = pv.watermark_png(buf.getvalue(), True)
    img = Image.open(io.BytesIO(out))
    assert img.size == (320, 180)
    assert (img.info.get("ff_preview") or "") == "1"
    assert img.info.get("ff_renderer") == pv.RENDERER_VER
    assert out != buf.getvalue()
    assert pv.watermark_png(buf.getvalue(), False) == buf.getvalue()


def test_still_cache_key_varies_by_time_profile_and_watermark():
    out = pv.PREVIEW_PROFILES["draft"]
    base = pv._still_key("h", 1.0, "draft", out, True)
    assert base != pv._still_key("h", 1.5, "draft", out, True)
    assert base != pv._still_key("h", 1.0, "review", out, True)
    assert base != pv._still_key("h", 1.0, "draft", out, False)
