"""FR-39：QA 分类、安全修复、即时验证、撤销与报告。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, select

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.db import engine
from app.models import DocRevision, Project
from app.services import project_docs as docs
from app.services import qa


def _project(tmp_path: Path):
    session = Session(engine)
    proj = Project(name=f"qa-{tmp_path.name}", root=str(tmp_path))
    session.add(proj)
    session.commit()
    session.refresh(proj)
    script = docs.build_script_doc("这一句需要时。第二句。")
    docs.save_doc(session, proj.id, "script", script, 0)
    docs.save_doc(session, proj.id, "profile", {
        "schema": "filmflow.profile/1", "width": 1920, "height": 1080,
        "fps": 24, "duration": 2.0, "frames": 48}, 0)
    timeline = {"schema": "filmflow.timeline/2", "fps": 24, "duration": 2.0,
                "frames": 48, "events": [], "tracks": [],
                "scenes": [{"id": "S01", "start": 0.0, "end": 1.0, "source_span": [0],
                            "text": "这一句需要时。", "read_seconds": 1.0,
                            "last_text_at": 0.0},
                           {"id": "S02", "start": 1.0, "end": 2.0, "source_span": [1],
                            "read_seconds": 1.0, "last_text_at": 1.0}]}
    docs.save_doc(session, proj.id, "timeline", timeline, 0)
    return session, proj


def _cleanup(session: Session, proj: Project) -> None:
    # P1-06：统一走级联删除服务（foreign_keys=ON 后手工逐删顺序易漏）
    from app.services.project_cleanup import delete_project
    root, pid = proj.root, proj.id
    session.rollback()
    session.close()
    with Session(engine) as s:
        delete_project(s, pid, remove_dir=False)
    shutil.rmtree(root, ignore_errors=True)


def test_analyze_fix_verify_undo(tmp_path: Path):
    session, proj = _project(tmp_path)
    try:
        analysis = qa.analyze(session, proj)
        cats = {i["category"] for i in analysis["issues"]}
        assert "text_overflow" in cats and "license_missing" in cats
        overflow = next(i for i in analysis["issues"] if i["category"] == "text_overflow")
        assert overflow["location"]["sceneId"] == "S01"
        fix = qa.apply_fix(session, proj, overflow["id"], "extend_scene",
                           {"sceneId": "S01", "delta": 0.5})
        assert fix["result"] == "applied" and fix["verified"] is None
        assert fix["documentVerified"] is True and fix["requiresRerun"] is True
        after = qa.analyze(session, proj)
        assert all(i["category"] != "text_overflow" for i in after["issues"])
        prof = docs.doc_payload(session, proj.id, proj.root, "profile")["content"]
        assert prof["duration"] == 2.5 and prof["frames"] == 60
        report = qa.report(proj)
        assert report["applied"] == 1 and report["verified"] == 0
        assert report["pendingRerun"] == 1
        entry = qa.undo_fix(session, proj, fix["id"])
        assert entry["undone"] is True
        restored = qa.analyze(session, proj)
        assert any(i["category"] == "text_overflow" for i in restored["issues"])
        prof2 = docs.doc_payload(session, proj.id, proj.root, "profile")["content"]
        assert prof2["duration"] == 2.0 and prof2["frames"] == 48
        assert qa.report(proj)["items"][0]["undone"] is True
    finally:
        _cleanup(session, proj)


def test_license_fix_and_scale_op(tmp_path: Path):
    session, proj = _project(tmp_path)
    try:
        analysis = qa.analyze(session, proj)
        lic = next(i for i in analysis["issues"] if i["category"] == "license_missing")
        fix = qa.apply_fix(session, proj, lic["id"], "fill_license", {
            "source": "自制", "license": "CC0", "authorized": True, "expires": ""})
        assert fix["verified"] is True
        assert not any(i["category"] == "license_missing"
                       for i in qa.analyze(session, proj)["issues"])
        overflow = next(i for i in qa.analyze(session, proj)["issues"]
                        if i["category"] == "text_overflow")
        sf = qa.apply_fix(session, proj, overflow["id"], "scale_text",
                          {"sceneId": "S01"})
        assert sf["action"] == "scale_text"
        tl = docs.doc_payload(session, proj.id, proj.root, "timeline")["content"]
        assert tl["scenes"][0]["text_scale"] == 0.9
    finally:
        _cleanup(session, proj)


def test_classify_node_messages():
    assert qa._classify_node("G06", "LUFS -12.0 超出目标") == "lufs_out"
    assert qa._classify_node("G07", "True Peak -0.4 超过 -1.0") == "tp_out"
    assert qa._classify_node("F03", "黑帧 3：[1,2,3]") == "black_frame"
    assert qa._classify_node("F03", "缺失帧 12") == "missing_frame"
    assert qa._classify_node("C03", "字体缺字：中") == "font_missing"
    assert qa._classify_node("G05", "E_LICENSE_MISSING: 缺少音乐来源") == "license_missing"
    assert qa._classify_node("C01", "引擎不可用") == "engine_unavailable"


def test_license_fix_requires_explicit_authorization_and_flags_unlicensed_asset(tmp_path: Path):
    import base64

    from app.errors import ApiError
    from app.services import assets as assets_svc

    png = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")).decode()
    session, proj = _project(tmp_path)
    asset = None
    try:
        lic = next(i for i in qa.analyze(session, proj)["issues"]
                   if i["category"] == "license_missing")
        spec = next(s for s in lic["suggestions"] if s["action"] == "fill_license")
        assert spec["kind"] == "confirm" and "authorized" not in (spec.get("params") or {})
        with pytest.raises(ApiError) as e:
            qa.apply_fix(session, proj, lic["id"], "fill_license",
                         {"source": "自制", "license": "CC0", "expires": ""})
        assert "authorized" in e.value.detail["message"]

        asset, _ = assets_svc.import_asset(session, "project", proj.root, "qa.png", png,
                                           license={"source": "自制", "type": "CC0"})
        assets_svc.update_asset(session, asset.id, {"license": {"source": "", "type": ""}})
        payload = docs.doc_payload(session, proj.id, proj.root, "timeline")
        content = payload["content"]
        content["scenes"][0]["layers"] = [{"id": "img1", "type": "image",
                                           "assetSha": asset.sha256,
                                           "box": [0, 0, 100, 100]}]
        docs.save_doc(session, proj.id, "timeline", content, payload["version"])
        issues = qa.analyze(session, proj)["issues"]
        bad = next(i for i in issues if i["category"] == "asset_license_missing")
        assert bad["location"]["sceneId"] == "S01" and "缺少许可" in bad["reason"]
        assert any(s["action"] == "open_assets" for s in bad["suggestions"])
    finally:
        if asset:
            Path(asset.path).unlink(missing_ok=True)
            row = session.get(type(asset), asset.id)
            if row:
                session.delete(row)
                session.commit()
        _cleanup(session, proj)


def test_undo_chain_is_multi_step_and_lifo(tmp_path: Path):
    session = Session(engine)
    proj = Project(name=f"qa-chain-{tmp_path.name}", root=str(tmp_path))
    session.add(proj)
    session.commit()
    session.refresh(proj)
    script = docs.build_script_doc(
        "第一句话很长很长很长需要更多时间才能读完。第二句话也很长很长很长需要更多时间才能读完。")
    docs.save_doc(session, proj.id, "script", script, 0)
    docs.save_doc(session, proj.id, "profile", {
        "schema": "filmflow.profile/1", "width": 1920, "height": 1080,
        "fps": 24, "duration": 2.0, "frames": 48}, 0)
    saved_tl, _ = docs.save_doc(session, proj.id, "timeline", {
        "schema": "filmflow.timeline/2", "fps": 24, "duration": 2.0, "frames": 48,
        "events": [], "tracks": [],
        "scenes": [{"id": "S01", "start": 0.0, "end": 1.0, "source_span": [0],
                    "read_seconds": 1.0, "last_text_at": 0.0},
                   {"id": "S02", "start": 1.0, "end": 2.0, "source_span": [1],
                    "read_seconds": 1.0, "last_text_at": 1.0}]}, 0)
    original_hash = docs.content_hash(saved_tl.content_json)
    try:
        overs = [i for i in qa.analyze(session, proj)["issues"]
                 if i["category"] == "text_overflow"]
        assert {o["location"]["sceneId"] for o in overs} == {"S01", "S02"}
        fix_a = qa.apply_fix(session, proj, overs[0]["id"], "scale_text", {"sceneId": "S01"})
        s02 = next(i for i in qa.analyze(session, proj)["issues"]
                   if i["category"] == "text_overflow" and i["location"]["sceneId"] == "S02")
        fix_b = qa.apply_fix(session, proj, s02["id"], "scale_text", {"sceneId": "S02"})
        assert docs.content_hash(fix_b["before"]["content"]) == fix_a["afterHash"]
        assert fix_a["afterHash"] and fix_b["afterHash"] and fix_a["afterHash"] != fix_b["afterHash"]

        with pytest.raises(ValueError) as e:
            qa.undo_fix(session, proj, fix_a["id"])
        assert "倒序" in str(e.value) and fix_b["id"] in str(e.value)

        qa.undo_fix(session, proj, fix_b["id"])
        qa.undo_fix(session, proj, fix_a["id"])
        current = docs.doc_payload(session, proj.id, proj.root, "timeline")
        assert docs.content_hash(current["content"]) == original_hash
        report = qa.report(proj)
        assert report["undone"] == 2 and report["active"] == 0
    finally:
        _cleanup(session, proj)


def test_undo_removes_profile_doc_created_by_fix(tmp_path: Path):
    """修复前没有 profile 文档行时，撤销要回到"没有"，不能固化残缺默认文档。"""
    session = Session(engine)
    proj = Project(name=f"qa-noprof-{tmp_path.name}", root=str(tmp_path))
    session.add(proj)
    session.commit()
    session.refresh(proj)
    script = docs.build_script_doc("这一句话需要再多一点时间才能读完。")
    docs.save_doc(session, proj.id, "script", script, 0)
    docs.save_doc(session, proj.id, "timeline", {
        "schema": "filmflow.timeline/2", "fps": 24, "duration": 1.0, "frames": 24,
        "events": [], "tracks": [],
        "scenes": [{"id": "S01", "start": 0.0, "end": 1.0, "source_span": [0],
                    "text": "这一句话需要再多一点时间才能读完。",
                    "read_seconds": 1.0, "last_text_at": 0.0}]}, 0)
    try:
        assert docs.get_doc(session, proj.id, "profile") is None
        overflow = next(i for i in qa.analyze(session, proj)["issues"]
                        if i["category"] == "text_overflow")
        fix = qa.apply_fix(session, proj, overflow["id"], "extend_scene",
                           {"sceneId": "S01", "delta": 0.5})
        assert fix["before"]["profileExisted"] is False
        assert docs.get_doc(session, proj.id, "profile") is not None
        qa.undo_fix(session, proj, fix["id"])
        assert docs.get_doc(session, proj.id, "profile") is None
        current = docs.doc_payload(session, proj.id, proj.root, "timeline")["content"]
        assert float(current["duration"]) == 1.0
    finally:
        leftover = docs.get_doc(session, proj.id, "profile")
        if leftover:
            for rev in session.exec(select(DocRevision).where(
                    DocRevision.doc_id == leftover.id)).all():
                session.delete(rev)
            session.delete(leftover)
            session.commit()
        _cleanup(session, proj)


def test_mix_undo_guard_rejects_manual_edit_after_fix(tmp_path: Path):
    """F-QA-1：set_lufs 撤销必须走链顶守卫——修复后又手工改过 targetLufs 时拒绝撤销。"""
    session, proj = _project(tmp_path)
    try:
        # 项目里先有一份 mix（targetLufs=-16），再走一次 set_lufs 修复到 -14
        from app.services import audio as audio_svc
        mix_before = {"schema": "filmflow.audio-mix/1",
                      "preset": "-16", "targetLufs": -16.0,
                      "stems": {"voice": 0.0, "music": -8.0, "sfx": 0.0}}
        audio_svc.save_mix(proj.root, mix_before)
        result = qa._apply(session, proj, {"location": {}}, "set_lufs",
                           {"target": -14}, None,
                           {"kind": "mix", "content": audio_svc.load_mix(proj.root)})
        after_state = result[0]
        assert after_state["hash"] == docs.content_hash(audio_svc.load_mix(proj.root))
        entry = {"id": "fix_mixtest", "issueId": "x", "category": "lufs", "action": "set_lufs",
                 "result": "applied", "before": {"kind": "mix", "content": mix_before},
                 "after": after_state, "afterHash": after_state.get("hash")}
        data = qa._read_fixes(proj.root)
        data["items"].append(entry)
        qa._write_fixes(proj.root, data)
        # 手工把响度改回 -16（模拟修复后的人工编辑）
        audio_svc.save_mix(proj.root, {**audio_svc.load_mix(proj.root),
                                       "preset": "-16", "targetLufs": -16.0})
        with pytest.raises(ValueError, match="混音配置"):
            qa.undo_fix(session, proj, "fix_mixtest")
        # 恢复到修复后状态（链顶）→ 撤销放行并回到 -16 前值
        audio_svc.save_mix(proj.root, {**audio_svc.load_mix(proj.root),
                                       "preset": "-14", "targetLufs": -14.0})
        undone = qa.undo_fix(session, proj, "fix_mixtest")
        assert undone["undone"] is True
        assert float(audio_svc.load_mix(proj.root)["targetLufs"]) == -16.0
    finally:
        _cleanup(session, proj)


def test_license_undo_guard_rejects_manual_edit_after_fix(tmp_path: Path):
    """F-QA-1：fill_license 撤销同样受链顶守卫。"""
    session, proj = _project(tmp_path)
    try:
        from app.services import audio as audio_svc
        result = qa._apply(session, proj, {"location": {}}, "fill_license",
                           {"source": "自制", "license": "CC0", "authorized": True},
                           None, None)
        after_state = result[0]
        entry = {"id": "fix_lictest", "issueId": "x", "category": "license_missing",
                 "action": "fill_license", "result": "applied",
                 "before": {"kind": "license", "content": {}},
                 "after": after_state, "afterHash": after_state.get("hash")}
        data = qa._read_fixes(proj.root)
        data["items"].append(entry)
        qa._write_fixes(proj.root, data)
        # 修复后手工换许可 → 撤销被拒
        audio_svc.save_license(proj.root, {"source": "他人", "license": "MIT",
                                           "authorized": True})
        with pytest.raises(ValueError, match="音乐许可"):
            qa.undo_fix(session, proj, "fix_lictest")
        # 回到链顶 → 撤销放行，许可回到"不存在"（修复前没有）
        audio_svc.save_license(proj.root, {"source": "自制", "license": "CC0",
                                           "authorized": True})
        undone = qa.undo_fix(session, proj, "fix_lictest")
        assert undone["undone"] is True
        assert not audio_svc.license_path(proj.root).exists()
    finally:
        _cleanup(session, proj)


def test_undo_guard_is_lifo_by_sequence_even_for_identical_values():
    """两次改成同一个值时内容哈希相同，只有链序号能挡住"撤销旧的抹掉新的"。"""
    older = {"id": "fix_old", "result": "applied", "action": "set_lufs",
             "undoKind": "mix", "seq": 1, "before": {"kind": "mix"},
             "afterHash": "same-hash"}
    newer = {"id": "fix_new", "result": "applied", "action": "set_lufs",
             "undoKind": "mix", "seq": 2, "before": {"kind": "mix"},
             "afterHash": "same-hash"}
    data = {"items": [older, newer]}
    with pytest.raises(ValueError) as e:
        qa._require_undo_head(data, older, "same-hash", "same-hash", None, None, "混音配置")
    assert "fix_new" in str(e.value), str(e.value)
    # 链顶那条即使内容一致也放行
    qa._require_undo_head(data, newer, "same-hash", "same-hash", None, None, "混音配置")


def test_undo_guard_refuses_legacy_record_without_evidence():
    """本轮改造前的历史记录（既无 seq 又无 afterHash）不再被当作"无需守卫"。"""
    legacy = {"id": "fix_legacy", "result": "applied", "action": "fill_license",
              "before": {"kind": "license"}}
    with pytest.raises(ValueError) as e:
        qa._require_undo_head({"items": [legacy]}, legacy, "whatever", None, None, None, "音乐许可")
    assert "历史" in str(e.value), str(e.value)


def test_undo_guard_still_blocks_post_fix_manual_edit():
    """有依据时内容守卫不松：手工改过 mix 之后，撤销必须被拒。"""
    entry = {"id": "fix_a", "result": "applied", "action": "set_lufs",
             "undoKind": "mix", "seq": 1, "before": {"kind": "mix"}, "afterHash": "hash-a"}
    with pytest.raises(ValueError) as e:
        qa._require_undo_head({"items": [entry]}, entry, "hand-edited-hash", "hash-a",
                             None, None, "混音配置")
    assert "又被改动" in str(e.value), str(e.value)
