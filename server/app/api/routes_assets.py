"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..errors import ApiError, ErrorCode
from ..models import (
    Project,
    ProjectDoc,
)
from ..security import file_response
from ..services import assets as assets_svc
from ..services import audio as audio_svc
from ..services import project_docs as docs_svc
from . import deps
from .schemas import (
    AssetImportIn,
    AssetReplaceIn,
    AssetUpdateIn,
    AudioAlignmentSaveIn,
    AudioLicenseSaveIn,
    AudioMarkersIn,
    AudioMixSaveIn,
    AudioPrimaryIn,
    AudioProcessIn,
    AudioScenePrimaryIn,
    AudioUploadIn,
    FontCheckIn,
)

router = APIRouter(prefix="/api")


def _asset_project(session: Session, project_id: int | None) -> Project | None:
    if not project_id:
        return None
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    return proj


@router.get("/assets")
async def assets_list(scope: str = "global", projectId: int | None = None,
                      kind: str = "", q: str = "", includeArchived: bool = False,
                      session: Session = Depends(get_session)):
    if scope not in ("global", "project"):
        raise ApiError(ErrorCode.E_VALIDATION, "scope 必须是 global/project")
    if scope == "project":
        _asset_project(session, projectId)
    items = assets_svc.list_assets(session, scope, projectId, kind, q, includeArchived)
    return {"items": items, "scope": scope, "projectId": projectId}


@router.post("/assets")
async def assets_import(payload: AssetImportIn, session: Session = Depends(get_session)):
    scope = payload.scope
    proj = _asset_project(session, payload.projectId) if scope == "project" else None
    asset, deduped = await asyncio.to_thread(
        assets_svc.import_asset, session, scope, proj.root if proj else None,
        payload.filename, payload.data, payload.kind, payload.name,
        payload.tags, payload.license, payload.author)
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    deps.audit(session, "asset.import", f"{scope}:{asset.id}",
          after={"sha256": asset.sha256, "kind": asset.kind, "deduped": deduped})
    return {"asset": assets_svc.asset_dto(asset, usages), "deduped": deduped}


@router.get("/assets/{asset_id}")
async def assets_get(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    return {"asset": assets_svc.asset_dto(asset, usages)}


@router.patch("/assets/{asset_id}")
async def assets_update(asset_id: int, payload: AssetUpdateIn,
                        session: Session = Depends(get_session)):
    body = {k: v for k, v in payload.model_dump().items() if v is not None}
    asset = await asyncio.to_thread(assets_svc.update_asset, session, asset_id, body)
    deps.audit(session, "asset.update", str(asset_id),
          after={"name": (asset.meta_json or {}).get("name"), "archived": asset.archived})
    usages = assets_svc.scan_usages(
        session, sha=asset.sha256,
        project_ids=[asset.project_id] if asset.scope == "project" else None).get(asset.sha256, [])
    return {"asset": assets_svc.asset_dto(asset, usages)}


@router.delete("/assets/{asset_id}")
async def assets_delete(asset_id: int, force: bool = False,
                        session: Session = Depends(get_session)):
    result = await asyncio.to_thread(assets_svc.delete_asset, session, asset_id, force)
    deps.audit(session, "asset.delete", str(asset_id), after=result)
    return result


@router.get("/assets/{asset_id}/file")
async def assets_file(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    p = Path(asset.path)
    if not p.exists():
        raise ApiError(ErrorCode.E_ASSET_MISSING, "资产文件缺失", status=404)
    # P3：SVG 可携带 <script>，同源直开=存储型脚本执行；白名单 Content-Type + CSP sandbox + nosniff
    return file_response(p, download_name=p.name)


@router.get("/assets/{asset_id}/thumb")
async def assets_thumb(asset_id: int, session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    p = assets_svc._thumb_path(asset)
    if not p:
        raise ApiError(ErrorCode.E_NOT_FOUND, "缩略图不存在", status=404)
    return file_response(p)


@router.get("/assets/{asset_id}/waveform")
async def assets_waveform(asset_id: int, w: int = 2000,
                          session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    if asset.kind != "audio":
        raise ApiError(ErrorCode.E_ASSET_KIND, "只有音频资产有波形")
    data = await asyncio.to_thread(assets_svc.waveform, asset.path, w)
    return {**data, "assetId": asset_id, "duration": (asset.meta_json or {}).get("duration", 0)}


@router.post("/assets/{asset_id}/font-check")
async def assets_font_check(asset_id: int, payload: FontCheckIn,
                            session: Session = Depends(get_session)):
    asset = assets_svc.get_asset(session, asset_id)
    if asset.kind != "font":
        raise ApiError(ErrorCode.E_ASSET_KIND, "只有字体资产可做覆盖检查")
    return await asyncio.to_thread(assets_svc.font_coverage, asset.path, payload.text)


@router.post("/assets/{asset_id}/replace")
async def assets_replace(asset_id: int, payload: AssetReplaceIn,
                         session: Session = Depends(get_session)):
    old = assets_svc.get_asset(session, asset_id)
    new = assets_svc.get_asset(session, payload.assetId)
    if old.kind != new.kind:
        raise ApiError(ErrorCode.E_ASSET_KIND, "替换资产必须同类型")
    if old.id == new.id:
        raise ApiError(ErrorCode.E_VALIDATION, "新旧资产相同")
    if old.scope == "global" and new.scope != "global":
        raise ApiError(ErrorCode.E_ASSET_KIND, "全局资产只能替换为全局资产")
    if old.scope == "project" and new.scope == "project" and new.project_id != old.project_id:
        raise ApiError(ErrorCode.E_ASSET_KIND, "项目资产不能替换为其他项目资产")
    usages = assets_svc.scan_usages(
        session, sha=old.sha256,
        project_ids=[old.project_id] if old.scope == "project" else None).get(old.sha256, [])
    target_ids = sorted({u["projectId"] for u in usages if u.get("projectId")}) if old.scope == "global" else \
        ([old.project_id] if old.project_id else [])
    changed_projects = []
    before_docs: list[tuple[int, dict, int]] = []  # (pid, 保存前内容, 保存前版本)
    try:
        for pid in target_ids:
            doc = session.exec(select(ProjectDoc).where(
                ProjectDoc.project_id == pid, ProjectDoc.kind == "timeline")).first()  # type: ignore[arg-type]
            if not doc:
                continue
            content = json.loads(json.dumps(doc.content_json or {}))
            scenes = assets_svc.replace_doc_refs(content, old.sha256, new.sha256)
            if not scenes:
                continue
            before_docs.append((pid, json.loads(json.dumps(doc.content_json or {})),
                                doc.version))
            saved, diff = docs_svc.save_doc(session, pid, "timeline", content, doc.version,
                                            "asset-replace")
            changed_projects.append({"projectId": pid, "version": saved.version,
                                     "scenes": scenes, "diff": diff[:50]})
    except Exception:
        # P1-09：多项目替换中途失败 → 倒序把已改项目回滚（base 用当前行版本）
        for pid, content_before, _version_before in reversed(before_docs):
            try:
                row = session.exec(select(ProjectDoc).where(
                    ProjectDoc.project_id == pid, ProjectDoc.kind == "timeline")).first()
                docs_svc.save_doc(session, pid, "timeline", content_before,
                                  row.version if row else 0, "asset-replace-rollback")
            except Exception:
                _log.debug("swallowed exception in assets_replace (except Exception:)", exc_info=True)
        raise
    untouched = {}
    for u in usages:
        if u.get("source") in ("template", "run", "doc"):
            untouched[u["source"]] = untouched.get(u["source"], 0) + 1
    deps.audit(session, "asset.replace", str(asset_id),
          after={"with": new.id, "projects": changed_projects, "untouched": untouched})
    return {"old": assets_svc.asset_dto(old, usages),
            "new": assets_svc.asset_dto(new, []),
            "projects": changed_projects,
            "untouched": untouched,
            "affectedScenes": sorted({s for p in changed_projects for s in p["scenes"]})}



def _default_alignment_segments(session: Session, project_id: int) -> list[dict]:
    """首次使用（尚无已存对齐）时给音频页的默认对齐段：[场景窗口] + [场景文本]。

    为什么做成产品能力而不是让用户手填：对齐段 text 为空时交付字幕 QC 必挂
    （SRT count=0，2026-11-07 attempt 14 实测、e2e 一直用脚本回填）；时间线场景的
    last_text_at+read_seconds ≡ end（project_docs），段取 [start,end]=场景窗口即天然
    满足 G06 音画同步（偏差 0）与字幕 cps（建议时长=字数/5.2）。落库仍是用户显式
    动作——音频页「保存手动对齐」。
    """
    tl = docs_svc.get_doc(session, project_id, "timeline")
    sc = docs_svc.get_doc(session, project_id, "script")
    if tl is None or sc is None:
        return []
    scenes = (tl.content_json or {}).get("scenes") or []
    sentences = (sc.content_json or {}).get("sentences") or []
    out: list[dict] = []
    for s in scenes:
        span = s.get("source_span") or []
        text = "".join(sentences[i].get("text", "") for i in span
                       if isinstance(i, int) and i < len(sentences)).strip()
        start, end = float(s.get("start") or 0.0), float(s.get("end") or 0.0)
        if end <= start or not text:
            continue
        out.append({"text": text, "start": round(start, 3), "end": round(end, 3)})
    return out

# ---------- 音频工作台（FR-27） ----------


@router.get("/projects/{project_id}/audio")
async def project_audio(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    manifest = audio_svc.load_manifest(proj.root)
    lic = audio_svc.load_license(proj.root)
    ok, why = audio_svc.license_ok(lic)
    primary = audio_svc.primary_take(proj.root)
    alignment = audio_svc.load_alignment(proj.root)
    if not alignment.get("segments"):
        segs = _default_alignment_segments(session, project_id)
        if segs:
            alignment = {"schema": "filmflow.alignment/1", "source": "default",
                         "author": "system", "segments": segs}
    return {"takes": manifest["takes"], "primary": primary,
            "scenePrimary": manifest.get("scenePrimary") or {},
            "alignment": alignment,
            "license": lic, "licenseOk": ok, "licenseReason": why,
            "mix": audio_svc.load_mix(proj.root),
            "markers": audio_svc.load_markers(proj.root),
            "placeholder": audio_svc.load_placeholder(proj.root)}


@router.post("/projects/{project_id}/audio/upload")
async def project_audio_upload(project_id: int, payload: AudioUploadIn,
                               session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    take = await asyncio.to_thread(
        audio_svc.import_take, proj.root, payload.filename,
        payload.data, payload.kind, payload.sceneId, payload.name)
    deps.audit(session, "audio.upload", proj.root, after={"take": take["id"], "kind": take["kind"]})
    return {"take": take, "primary": audio_svc.primary_take(proj.root)}


@router.post("/projects/{project_id}/audio/primary")
async def project_audio_primary(project_id: int, payload: AudioPrimaryIn,
                                session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    take = audio_svc.set_primary(proj.root, payload.takeId)
    deps.audit(session, "audio.primary", proj.root, after={"take": take["id"]})
    return {"primary": take}


@router.post("/projects/{project_id}/audio/scene-primary")
async def audio_scene_primary(project_id: int, payload: AudioScenePrimaryIn,
                              session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    result = (audio_svc.clear_scene_primary(proj.root, payload.sceneId) if not payload.takeId
              else audio_svc.set_scene_primary(proj.root, payload.sceneId, payload.takeId))
    deps.audit(session, "audio.scene_primary", proj.root, after=result)
    return result


@router.post("/projects/{project_id}/audio/takes/{take_id}/process")
async def audio_process_take(project_id: int, take_id: str, payload: AudioProcessIn | None = None,
                             session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    take = await asyncio.to_thread(audio_svc.process_take, proj.root, take_id,
                                   payload.model_dump() if payload else {})
    deps.audit(session, "audio.process", proj.root, after={"take": take_id,
          "processing": take.get("processing")})
    return {"take": take}


@router.get("/projects/{project_id}/audio/takes/{take_id}/file")
async def audio_take_file(project_id: int, take_id: str, processed: bool = False,
                          session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    p = audio_svc.take_path(proj.root, take_id, processed=processed)
    return file_response(p)


@router.post("/projects/{project_id}/audio/concat")
async def audio_concat_preview(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    tl = docs_svc.doc_payload(session, project_id, proj.root, "timeline")["content"]
    profile = docs_svc.doc_payload(session, project_id, proj.root, "profile")["content"]
    out = Path(proj.root) / "card" / "audio" / "preview_concat.wav"
    result = await asyncio.to_thread(
        audio_svc.concat_voice, proj.root, tl.get("scenes") or [],
        float(profile.get("duration") or 0), out)
    if not result:
        raise ApiError(ErrorCode.E_VALIDATION, "还没有场景 Take；先在 Take 上点“设为场景”", status=409)
    return {**result, "url": f"/api/projects/{project_id}/audio/concat/file"}


@router.get("/projects/{project_id}/audio/concat/file")
async def audio_concat_file(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    p = Path(proj.root) / "card" / "audio" / "preview_concat.wav"
    if not p.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, "拼接预览尚未生成", status=404)
    return file_response(p, download_name="concat-preview.wav")


@router.get("/projects/{project_id}/audio/onset")
async def audio_onset(project_id: int, takeId: str, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    onsets = await asyncio.to_thread(audio_svc.detect_onsets, proj.root, takeId)
    return {"takeId": takeId, "onsets": onsets, "count": len(onsets)}


@router.get("/projects/{project_id}/audio/markers")
async def audio_markers_get(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return audio_svc.load_markers(proj.root)


@router.post("/projects/{project_id}/audio/markers")
async def audio_markers_save(project_id: int, payload: AudioMarkersIn,
                             session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    data = audio_svc.save_markers(proj.root, payload.markers or [], payload.onsets or [])
    deps.audit(session, "audio.markers", proj.root, after={"markers": len(data["markers"])})
    return data


@router.get("/projects/{project_id}/audio/mix")
async def audio_mix_get(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return audio_svc.load_mix(proj.root)


@router.post("/projects/{project_id}/audio/mix")
async def audio_mix_save(project_id: int, payload: AudioMixSaveIn,
                         session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    data = audio_svc.save_mix(proj.root, payload.model_dump(exclude_none=True))
    deps.audit(session, "audio.mix", proj.root, after=data)
    return data


@router.get("/projects/{project_id}/audio/waveform")
async def project_audio_waveform(project_id: int, takeId: str, w: int = 2000,
                                 session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    return await asyncio.to_thread(audio_svc.waveform, proj.root, takeId, w)


@router.get("/projects/{project_id}/audio/alignment")
async def project_audio_alignment(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    return audio_svc.load_alignment(proj.root)


@router.post("/projects/{project_id}/audio/alignment")
async def project_audio_alignment_save(project_id: int, payload: AudioAlignmentSaveIn,
                                       session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    data = audio_svc.save_alignment(proj.root, payload.segments, payload.author)
    deps.audit(session, "audio.alignment", proj.root, after={"segments": len(data["segments"])})
    return data


@router.get("/projects/{project_id}/audio/license")
async def project_audio_license(project_id: int, session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    lic = audio_svc.load_license(proj.root)
    ok, why = audio_svc.license_ok(lic)
    return {"license": lic, "ok": ok, "reason": why}


@router.post("/projects/{project_id}/audio/license")
async def project_audio_license_save(project_id: int, payload: AudioLicenseSaveIn,
                                     session: Session = Depends(get_session)):
    proj = deps._project_or_404(session, project_id)
    deps._require_workspace_root(Path(proj.root).resolve())
    lic = audio_svc.save_license(proj.root, payload.model_dump())
    deps.audit(session, "audio.license", proj.root, after=lic)
    return {"license": lic, "ok": True, "reason": ""}


# ---------- FR-33 审片批注 ----------

