"""FR-36：资产 sha 去重、引用计数、删除保护、替换、字体覆盖、图片/字体编译。"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest
from PIL import Image
from sqlmodel import Session, select

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import engine  # noqa: E402
from app.engine.scene.compiler import compile_scene  # noqa: E402
from app.engine.scene.schema import validate_program  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.models import Asset, Project, ProjectDoc  # noqa: E402
from app.services import assets  # noqa: E402
from app.services import timeline_ops as tl  # noqa: E402
from app.services.project_docs import build_script_doc  # noqa: E402


def _png(color=(200, 30, 40)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (16, 9), color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    with Session(engine) as session:
        proj = Project(name=f"asset-test-{tmp_path.name}", root=str(root))
        session.add(proj)
        session.commit()
        session.refresh(proj)
        yield session, proj, root
        docs = session.exec(select(ProjectDoc).where(ProjectDoc.project_id == proj.id)).all()
        rows = session.exec(select(Asset).where(Asset.project_id == proj.id)).all()
        for doc in docs:
            session.delete(doc)
        for asset in rows:
            Path(asset.path).unlink(missing_ok=True)
            session.delete(asset)
        session.delete(proj)
        session.commit()


def test_import_50_images_dedupes_and_metadata(env):
    session, proj, root = env
    data = _png()
    first, deduped = assets.import_asset(session, "project", root, "x.png", data,
                                         name="图一", tags=["封面"])
    assert deduped is False and first.kind == "image"
    assert first.meta_json["width"] == 16 and first.meta_json["height"] == 9
    assert assets._thumb_path(first) and assets._thumb_path(first).exists()
    for i in range(49):
        same, dup = assets.import_asset(session, "project", root, f"copy{i}.png", data)
        assert dup is True and same.id == first.id
    rows = session.exec(select(Asset).where(Asset.project_id == proj.id,
                                            Asset.sha256 == first.sha256)).all()
    assert len(rows) == 1


def test_usage_delete_guard_and_replace(env):
    session, proj, root = env
    old, _ = assets.import_asset(session, "project", root, "old.png", _png((10, 20, 30)))
    new, _ = assets.import_asset(session, "project", root, "new.png", _png((30, 40, 50)))
    content = {"schema": "filmflow.timeline/2", "fps": 24, "duration": 4.0,
               "scenes": [{"id": "S01", "start": 0, "end": 2, "layers": [
                   {"id": "img01", "type": "image", "assetSha": old.sha256,
                    "box": [0, 0, 100, 100]}]},
                          {"id": "S02", "start": 2, "end": 4}]}
    session.add(ProjectDoc(project_id=proj.id, kind="timeline", content_json=content))
    session.commit()
    usages = assets.scan_usages(session, sha=old.sha256, project_ids=[proj.id])
    assert len(usages[old.sha256]) == 1
    with pytest.raises(ApiError) as e:
        assets.delete_asset(session, old.id)
    assert e.value.detail["code"] == "E_ASSET_IN_USE"
    assert e.value.detail["details"]["usages"][0]["sceneId"] == "S01"
    changed = assets.replace_doc_refs(content, old.sha256, new.sha256)
    assert changed == ["S01"]
    assert content["scenes"][0]["layers"][0]["assetSha"] == new.sha256
    doc = session.exec(select(ProjectDoc).where(ProjectDoc.project_id == proj.id,
                                                ProjectDoc.kind == "timeline")).first()
    doc.content_json = content
    session.add(doc)
    session.commit()
    assert assets.scan_usages(session, sha=old.sha256, project_ids=[proj.id]) == {}
    assert assets.delete_asset(session, old.id)["deleted"] == old.id


def test_font_requires_license(env):
    session, proj, root = env
    font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if not font.exists():
        pytest.skip("Arial 测试字体不存在")
    data = base64.b64encode(font.read_bytes()).decode()
    with pytest.raises(ApiError) as e:
        assets.import_asset(session, "project", root, "x.ttf", data)
    assert e.value.detail["code"] == "E_ASSET_LICENSE"
    ok, _ = assets.import_asset(session, "project", root, "x.ttf", data,
                                license={"source": "system", "type": "system"})
    assert ok.kind == "font"


def test_font_coverage_reports_missing_glyph():
    font = Path.home() / ".filmflow/cache/fonts/NotoSansSC[wght].ttf"
    if not font.exists():
        pytest.skip("Noto Sans SC 字体不存在")
    ok = assets.font_coverage(font, "中文 ABC")
    assert ok["ok"] and ok["missingCount"] == 0
    bad = assets.font_coverage(font, "中文\U0001F600")
    assert not bad["ok"] and "\U0001F600" in bad["missing"]


def _scene_with_asset(sha: str) -> dict:
    return {"id": "S01", "start": 0.0, "end": 2.5, "meaning": "", "operation": "",
            "source_span": [0], "last_text_at": 0.0, "read_seconds": 1.0,
            "layers": [{"id": "img01", "type": "image", "assetSha": sha,
                        "box": [100, 80, 500, 280], "z": 12, "fit": "contain",
                        "opacity": 0.8}],
            "fontSha": "font-sha", "audio_layers": [
                {"id": "sfx01", "assetSha": "audio-sha", "at": 0.2,
                 "gainDb": -3, "fadeIn": 0.1, "fadeOut": 0.2}]}


def test_compiler_resolves_image_and_font_assets():
    script = build_script_doc("风从纸上起。")
    tokens = {"visual": {"palette": ["#F4EEE2", "#3D5588", "#FF665E", "#FFB511"]},
              "type_spec": {"family": "Noto Sans SC"}}
    profile = {"width": 1920, "height": 1080, "fps": 24, "duration": 2.5}

    def resolver(sha: str):
        if sha == "font-sha":
            return {"url": "/global-assets/aa/font.ttf", "kind": "font",
                    "family": "My Font"}
        if sha == "img-sha":
            return {"url": "/project/.filmflow/assets/bb/img.png", "kind": "image"}
        return None

    scene = _scene_with_asset("img-sha")
    prog = compile_scene(scene, script, tokens, profile, asset_resolver=resolver)
    image = next(l for l in prog["layers"] if l["id"] == "img01")
    assert image["src"] == "/project/.filmflow/assets/bb/img.png"
    assert image["box"] == [100, 80, 500, 280] and image["fit"] == "contain"
    title = next(l for l in prog["layers"] if l["id"] == "L_title")
    assert title["style"]["font"] == "My Font"
    assert title["style"]["fontUrl"] == "/global-assets/aa/font.ttf"
    assert prog["meta"]["assets"]
    assert not validate_program(prog)
    with pytest.raises(ValueError, match="E_ASSET_MISSING"):
        compile_scene(_scene_with_asset("missing"), script, tokens, profile,
                      asset_resolver=resolver)


def test_timeline_ops_add_image_sfx_and_font():
    script = build_script_doc("第一句。第二句。")
    doc = {"schema": "filmflow.timeline/2", "fps": 24, "duration": 4.0,
           "scenes": [{"id": "S01", "start": 0, "end": 2, "source_span": [0],
                       "read_seconds": 1, "last_text_at": 0},
                      {"id": "S02", "start": 2, "end": 4, "source_span": [1],
                       "read_seconds": 1, "last_text_at": 2}],
           "events": [], "tracks": []}
    new, _ = tl.apply(doc, script, "add_image", {
        "sceneId": "S01", "assetSha": "img", "box": [10, 20, 300, 200]})
    assert new["scenes"][0]["layers"][0]["id"].startswith("img")
    assert new["scenes"][0]["layers"][0]["assetSha"] == "img"
    new, _ = tl.apply(new, script, "add_sfx", {
        "sceneId": "S01", "assetSha": "sfx", "at": 0.5, "gainDb": -4})
    assert new["scenes"][0]["audio_layers"][0]["at"] == 0.5
    new, _ = tl.apply(new, script, "set_font", {"sceneId": "S01", "assetSha": "font"})
    assert new["scenes"][0]["fontSha"] == "font"
    new, _ = tl.apply(new, script, "remove_sfx", {
        "sceneId": "S01", "layerId": new["scenes"][0]["audio_layers"][0]["id"]})
    assert new["scenes"][0]["audio_layers"] == []
    new, _ = tl.apply(new, script, "remove_layer", {
        "sceneId": "S01", "layerId": new["scenes"][0]["layers"][0]["id"]})
    assert new["scenes"][0]["layers"] == []
