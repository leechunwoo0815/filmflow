"""FR-36：资产 sha 去重、引用计数、删除保护、替换、字体覆盖、图片/字体编译。"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from sqlmodel import Session, select

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import engine
from app.engine.scene.compiler import compile_scene
from app.engine.scene.schema import validate_program
from app.errors import ApiError
from app.models import Asset, Project, ProjectDoc, Run, Template, Workflow
from app.services import assets
from app.services import timeline_ops as tl
from app.services.project_docs import build_script_doc

LIC = {"source": "自制", "type": "CC0"}


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
        # P1-06：级联删除服务清库行；资产文件单独清理
        from app.services.project_cleanup import delete_project
        rows = session.exec(select(Asset).where(Asset.project_id == proj.id)).all()
        for asset in rows:
            Path(asset.path).unlink(missing_ok=True)
        pid = proj.id
        session.rollback()
        delete_project(session, pid, remove_dir=False)


def test_import_50_images_dedupes_and_metadata(env):
    session, proj, root = env
    data = _png()
    first, deduped = assets.import_asset(session, "project", root, "x.png", data,
                                         name="图一", tags=["封面"], license=LIC)
    assert deduped is False and first.kind == "image"
    assert first.meta_json["width"] == 16 and first.meta_json["height"] == 9
    assert assets._thumb_path(first) and assets._thumb_path(first).exists()
    for i in range(49):
        same, dup = assets.import_asset(session, "project", root, f"copy{i}.png", data, license=LIC)
        assert dup is True and same.id == first.id
    rows = session.exec(select(Asset).where(Asset.project_id == proj.id,
                                            Asset.sha256 == first.sha256)).all()
    assert len(rows) == 1


def test_usage_delete_guard_and_replace(env):
    session, proj, root = env
    old, _ = assets.import_asset(session, "project", root, "old.png", _png((10, 20, 30)),
                                license=LIC)
    new, _ = assets.import_asset(session, "project", root, "new.png", _png((30, 40, 50)),
                                license=LIC)
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


def _write_snapshot(root: Path, run_id: int, snapshot: dict) -> None:
    snap_dir = root / "runs" / str(run_id) / "docs"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False),
                                            encoding="utf-8")


@pytest.fixture()
def usage_env(tmp_path: Path):
    """引用面测试：项目 + workflow + run + 快照目录。"""
    root = tmp_path / "project"
    root.mkdir()
    with Session(engine) as session:
        proj = Project(name=f"usage-test-{tmp_path.name}", root=str(root))
        session.add(proj)
        session.commit()
        session.refresh(proj)
        wf = Workflow(project_id=proj.id, name="main", graph_json={"meta": {}})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        docs, rows, tpls = [], [], []
        try:
            yield session, proj, root, run, docs, rows, tpls
        finally:
            for a in rows:
                Path(a.path).unlink(missing_ok=True)
            # P1-06：级联删除服务（含 run/workflow/template/projectdoc）
            from app.services.project_cleanup import delete_project
            pid = proj.id
            session.rollback()
            delete_project(session, pid, remove_dir=False)


def _add_doc(session, docs, proj, kind, content):
    doc = ProjectDoc(project_id=proj.id, kind=kind, content_json=content)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    docs.append(doc)
    return doc


def test_walk_refs_covers_nested_lists_and_font_shas():
    refs = assets.walk_refs({"scenes": [{"layers": [{"assetSha": "a" * 64}],
                                         "fontSha": "f" * 64,
                                         "audio_layers": [{"assetSha": "a" * 64}]}],
                             "assetShas": ["a" * 64, "", 7]})
    shas = sorted({s for s, _f, _p in refs})
    assert shas == sorted(["a" * 64, "f" * 64])
    assert {f for _s, f, _p in refs} == {"layer", "font", "list"}
    assert any(p.endswith("scenes[0].layers[0].assetSha") for _s, _f, p in refs)


def test_scan_usages_covers_docs_templates_and_run_snapshots(usage_env):
    session, proj, root, run, docs, rows, tpls = usage_env
    asset, _ = assets.import_asset(session, "project", root, "a.png", _png((9, 9, 9)), license=LIC)
    rows.append(asset)
    sha = asset.sha256
    _add_doc(session, docs, proj, "timeline",
             {"scenes": [{"id": "S01", "layers": [{"id": "img01", "assetSha": sha}]}]})
    _add_doc(session, docs, proj, "audio",
             {"sfx": [{"id": "hit", "assetSha": sha}]})
    tpl = Template(kind="scene", name="引用模板", version=3,
                   content_json={"scenes": [{"layers": [{"assetSha": sha}]}], "assetShas": [sha]})
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    tpls.append(tpl)
    _write_snapshot(root, run.id, {"schema": "filmflow.run-snapshot/1",
                                   "docs": {"timeline": {"content": {"scenes": [
                                       {"id": "S01", "layers": [{"assetSha": sha}]}]}}}})

    live = assets.scan_usages(session, sha=sha, project_ids=[proj.id])
    assert {u["source"] for u in live[sha]} == {"timeline", "doc", "template"}
    history = assets.scan_usages(session, sha=sha, project_ids=[proj.id], include_history=True)
    assert {u["source"] for u in history[sha]} == {"timeline", "doc", "template", "run"}
    run_usage = next(u for u in history[sha] if u["source"] == "run")
    assert run_usage["runId"] == run.id and run_usage["sceneId"] == f"Run {run.id}"
    doc_usage = next(u for u in live[sha] if u["source"] == "doc")
    assert doc_usage["sceneId"] == "文档:audio"
    tpl_usage = next(u for u in live[sha] if u["source"] == "template")
    assert tpl_usage["templateId"] == tpl.id and tpl_usage["sceneId"] == "v3"
    # 模板里 assetShas 索引与真实图层同一容器，不重复计数
    assert len([u for u in live[sha] if u["source"] == "template"]) == 1
    assert len([u for u in live[sha] if u["source"] == "doc"]) == 1


def test_delete_blocked_by_template_only(usage_env):
    session, proj, root, run, docs, rows, tpls = usage_env
    asset, _ = assets.import_asset(session, "project", root, "solo.png", _png((8, 8, 8)), license=LIC)
    rows.append(asset)
    tpl = Template(kind="project", name="仅模板引用", content_json={"assetShas": [asset.sha256]})
    session.add(tpl)
    session.commit()
    tpls.append(tpl)
    with pytest.raises(ApiError) as e:
        assets.delete_asset(session, asset.id)
    assert e.value.detail["code"] == "E_ASSET_IN_USE"
    assert e.value.detail["details"]["usages"][0]["source"] == "template"


def test_delete_blocked_by_run_snapshot_only(usage_env):
    session, proj, root, run, docs, rows, tpls = usage_env
    asset, _ = assets.import_asset(session, "project", root, "ghost.png", _png((7, 7, 7)), license=LIC)
    rows.append(asset)
    _write_snapshot(root, run.id, {"docs": {"timeline": {"content": {"scenes": [
        {"id": "S01", "fontSha": asset.sha256}]}}}})
    assert assets.scan_usages(session, sha=asset.sha256, project_ids=[proj.id]) == {}
    with pytest.raises(ApiError) as e:
        assets.delete_asset(session, asset.id)
    assert e.value.detail["details"]["usages"][0]["source"] == "run"


def test_import_requires_license_for_every_kind(env):
    session, proj, root = env
    with pytest.raises(ApiError) as e:
        assets.import_asset(session, "project", root, "no-lic.png", _png((1, 2, 3)))
    assert e.value.detail["code"] == "E_ASSET_LICENSE"
    with pytest.raises(ApiError) as e2:
        assets.import_asset(session, "project", root, "old.png", _png((1, 2, 4)),
                            license={"source": "买断", "type": "商业授权",
                                     "expires": "2020-01-01"})
    assert "已过期" in e2.value.detail["message"]
    with pytest.raises(ApiError) as e3:
        assets.import_asset(session, "project", root, "bad.png", _png((1, 2, 5)),
                            license={"source": "买断", "type": "商业授权", "expires": "明年"})
    assert "ISO" in e3.value.detail["message"]
    ok, _ = assets.import_asset(session, "project", root, "ok.png", _png((1, 2, 6)),
                                license={"source": "买断", "type": "商业授权",
                                         "expires": "2099-12-31"})
    rows = session.exec(select(Asset).where(Asset.project_id == proj.id)).all()
    for a in rows:
        Path(a.path).unlink(missing_ok=True)
        session.delete(a)
    session.commit()
    assert ok.kind == "image"


def test_license_can_be_stripped_only_while_unused(env):
    session, proj, root = env
    loose, _ = assets.import_asset(session, "project", root, "loose.png", _png((40, 40, 40)),
                                   license={"source": "自制", "type": "CC0"})
    doc = _add_doc(session, [], proj, "timeline",
                   {"scenes": [{"id": "S01", "layers": [
                       {"id": "img01", "assetSha": loose.sha256}]}]})
    with pytest.raises(ApiError) as e:
        assets.update_asset(session, loose.id, {"license": {"source": "", "type": ""}})
    assert e.value.detail["code"] == "E_ASSET_LICENSE"
    assert "正被引用" in e.value.detail["message"]
    doc.content_json = {"scenes": [{"id": "S01"}]}
    session.add(doc)
    session.commit()
    assets.update_asset(session, loose.id, {"license": {"source": "", "type": ""}})
    tightened = assets.update_asset(session, loose.id, {"license": {
        "source": "素材库", "type": "商业授权", "expires": "2099-12-31"}})
    assert tightened.license_json["type"] == "商业授权"


def test_rights_lists_run_assets_and_flags_license_gaps(env):
    from app.services import delivery

    session, proj, root = env
    licensed, _ = assets.import_asset(session, "project", root, "lic.png", _png((50, 50, 50)),
                                      license={"source": "自制", "type": "CC0"})
    bare, _ = assets.import_asset(session, "project", root, "bare.png", _png((60, 60, 60)),
                                  license={"source": "自制", "type": "CC0"})
    assets.update_asset(session, bare.id, {"license": {"source": "", "type": ""}})
    snapshot = {"docs": {"timeline": {"content": {"scenes": [
        {"id": "S01", "layers": [{"assetSha": licensed.sha256}]},
        {"id": "S02", "layers": [{"assetSha": bare.sha256}]},
        {"id": "S03", "fontSha": "0" * 64}]}}}}
    items, gaps = delivery._asset_rights(session, snapshot)
    by_sha = {i["sha256"]: i for i in items}
    assert set(by_sha) == {licensed.sha256, bare.sha256}
    assert by_sha[licensed.sha256]["type"] == "CC0"
    assert by_sha[bare.sha256]["type"] == ""
    assert len(gaps) == 2
    assert any("bare" in g or "缺少许可" in g for g in gaps)
    assert any("资产记录已不存在" in g for g in gaps)


def test_delete_asset_blocked_by_inflight_job(env):
    """B5/P2-17：在飞作业 payload 引用该资产 → 409；心跳过期（僵尸）→ 放行。"""
    from datetime import UTC, datetime, timedelta

    from app.models import Job

    session, proj, root = env
    data = _png()
    asset, _dedup = assets.import_asset(session, "project", root, "inflight.png", data,
                                        name="在飞图", license=LIC)
    job = Job(kind="run", status="running", payload_json={"assetSha": asset.sha256},
              heartbeat_at=datetime.now(UTC))
    session.add(job)
    session.commit()
    with pytest.raises(ApiError, match="在飞作业"):
        assets.delete_asset(session, asset.id)
    job.heartbeat_at = datetime.now(UTC) - timedelta(seconds=600)
    session.add(job)
    session.commit()
    r = assets.delete_asset(session, asset.id)
    assert r["deleted"] == asset.id and r["inflightJobs"] == []


def test_corrupt_assets_import_graceful(env):
    """C5（专家 §7）：截断 PNG / 伪装 SVG / 0 字节 WAV / 非法 TTF——导入 4xx 优雅拒，不许 500。"""
    session, proj, root = env
    with pytest.raises(ApiError):
        assets.import_asset(session, "project", root, "bad.png", "XHg4OVBOR1xyXG5ceDFhXG50cmFzaA==",
                            name="坏PNG", license=LIC)
    # 伪装 SVG：裁定为**优雅降级**——按 SVG 收下但解析不出尺寸（_image_meta 窄化
    # except 返回 {"format": "SVG"}），服务面另有 CSP/nosniff 兜底，不许 500
    imported = assets.import_asset(session, "project", root, "evil.svg",
                                   "PGh0bWw+PC9odG1sPg==", name="坏SVG", license=LIC)
    asset_row = imported[0] if isinstance(imported, tuple) else imported
    assert asset_row.meta_json.get("format") == "SVG", asset_row.meta_json
    with pytest.raises(ApiError):
        assets.import_asset(session, "project", root, "empty.wav", "", name="空WAV", license=LIC)
    with pytest.raises(ApiError):
        assets.import_asset(session, "project", root, "fake.ttf", "XHgwMFx4MDFceDAybm90LWEtZm9udA==",
                            name="坏字体", license=LIC)
