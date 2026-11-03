"""FR-36 资产库：全局/项目存储、sha 去重、元数据、引用扫描与替换。"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import subprocess
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

import numpy as np
from sqlmodel import Session, select

from ..config import settings
from ..errors import ApiError, ErrorCode
from ..models import Asset, Project, ProjectDoc

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
AUDIO_EXT = {".wav", ".mp3", ".m4a"}
FONT_EXT = {".ttf", ".otf", ".woff2"}
VIDEO_EXT = {".mp4", ".mov"}
MAX_BYTES = 500 * 1024 * 1024


def _kind_for(ext: str) -> str:
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in FONT_EXT:
        return "font"
    if ext in VIDEO_EXT:
        return "video"
    raise ApiError(ErrorCode.E_ASSET_KIND, f"不支持的资产格式：{ext}")


def asset_root(scope: str, project_root: str | Path | None = None) -> Path:
    if scope == "global":
        return settings.assets_dir
    if scope != "project" or not project_root:
        raise ApiError(ErrorCode.E_VALIDATION, "项目资产需要 projectRoot")
    return Path(project_root) / ".filmflow" / "assets"


def _rel_path(sha: str, ext: str) -> str:
    return f"{sha[:2]}/{sha}{ext}"


def _find(session: Session, scope: str, project_id: int | None, sha: str) -> Asset | None:
    stmt = select(Asset).where(Asset.sha256 == sha, Asset.scope == scope)
    if scope == "project":
        stmt = stmt.where(Asset.project_id == project_id)
    return session.exec(stmt).first()


def _decode(data_b64: str) -> bytes:
    try:
        raw = base64.b64decode((data_b64 or "").split(",", 1)[-1], validate=True)
    except Exception:
        raise ApiError(ErrorCode.E_VALIDATION, "资产 base64 无效")
    if not raw:
        raise ApiError(ErrorCode.E_VALIDATION, "资产为空")
    if len(raw) > MAX_BYTES:
        raise ApiError(ErrorCode.E_VALIDATION, "资产超过 500MB")
    return raw


def _license(value) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ApiError(ErrorCode.E_VALIDATION, "license 必须是对象")
    return {k: str(value.get(k) or "") for k in ("source", "type", "expires", "author", "notes")}


def _image_meta(path: Path, ext: str) -> dict:
    if ext == ".svg":
        try:
            root = ET.parse(path).getroot()
            width = root.get("width") or ""
            height = root.get("height") or ""
            view = root.get("viewBox") or ""
            if (not width or not height) and view:
                parts = [p for p in view.replace(",", " ").split() if p]
                if len(parts) == 4:
                    width, height = parts[2], parts[3]
            return {"width": int(float(str(width).rstrip("px") or 0)) or None,
                    "height": int(float(str(height).rstrip("px") or 0)) or None,
                    "format": "SVG"}
        except Exception:
            return {"format": "SVG"}
    from PIL import Image
    with Image.open(path) as img:
        return {"width": img.width, "height": img.height, "format": img.format or ext[1:].upper()}


def _audio_meta(path: Path) -> dict:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels,codec_type,width,height",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        data = json.loads(res.stdout or "{}")
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        out = {"duration": round(float(fmt.get("duration") or 0), 3)}
        if streams:
            s = streams[0]
            out.update({"sampleRate": int(s.get("sample_rate") or 0),
                        "channels": int(s.get("channels") or 0)})
        return out
    except Exception:
        return {"duration": 0.0}


def _video_meta(path: Path) -> dict:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,sample_rate,channels",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        data = json.loads(res.stdout or "{}")
        fmt = data.get("format") or {}
        out = {"duration": round(float(fmt.get("duration") or 0), 3)}
        for s in data.get("streams") or []:
            if s.get("codec_type") == "video" and s.get("width"):
                out["width"], out["height"] = int(s["width"]), int(s["height"])
                break
        return out
    except Exception:
        return {"duration": 0.0}


def _font_meta(path: Path) -> dict:
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(str(path), fontNumber=0, lazy=True)
        names = font.get("name")
        family = subfamily = ""
        if names:
            for rec in names.names:
                if rec.nameID == 1 and not family:
                    family = str(rec.toUnicode() or "")
                elif rec.nameID == 2 and not subfamily:
                    subfamily = str(rec.toUnicode() or "")
        weight = 400
        try:
            weight = int(font.get("OS/2").usWeightClass)
        except Exception:
            pass
        cmap = set()
        if "cmap" in font:
            for table in font["cmap"].tables:
                cmap.update(table.cmap.keys())
        return {"family": family or path.stem, "subfamily": subfamily,
                "weight": weight, "glyphCount": len(cmap)}
    except Exception as e:
        return {"family": path.stem, "error": str(e)[:200]}


def _make_thumb(path: Path, out: Path, kind: str, ext: str) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if kind == "image" and ext != ".svg":
            from PIL import Image
            with Image.open(path) as img:
                img.thumbnail((480, 270))
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(out, "JPEG", quality=86)
            return out.name
        if kind == "font":
            from PIL import Image, ImageDraw, ImageFont
            font = ImageFont.truetype(str(path), 56)
            img = Image.new("RGB", (480, 160), "white")
            ImageDraw.Draw(img).text((22, 42), "Aa 中文字体", fill="black", font=font)
            img.save(out, "JPEG", quality=90)
            return out.name
    except Exception:
        pass
    return ""


def import_asset(session: Session, scope: str, project_root: str | Path | None,
                 filename: str, data_b64: str, kind: str = "", name: str = "",
                 tags: list | None = None, license: dict | None = None,
                 author: str = "") -> tuple[Asset, bool]:
    if scope not in ("global", "project"):
        raise ApiError(ErrorCode.E_VALIDATION, "scope 必须是 global/project")
    ext = Path(filename or "").suffix.lower()
    real_kind = _kind_for(ext)
    if kind and kind != real_kind:
        raise ApiError(ErrorCode.E_ASSET_KIND, f"扩展名 {ext} 是 {real_kind}，不是 {kind}")
    raw = _decode(data_b64)
    lic = _license(license)
    if real_kind == "font" and (not lic.get("source") or not lic.get("type")):
        raise ApiError(ErrorCode.E_ASSET_LICENSE, "字体资产必须填写许可来源和类型")
    sha = hashlib.sha256(raw).hexdigest()
    if scope == "project":
        if not project_root:
            raise ApiError(ErrorCode.E_VALIDATION, "项目资产需要 projectRoot")
        # 跨作用域复用：项目直接引用全局同 sha，不复制
        shared = session.exec(select(Asset).where(
            Asset.sha256 == sha, Asset.scope == "global", Asset.archived == False)).first()  # type: ignore[arg-type]
        if shared:
            return shared, True
        proj = session.exec(select(Project).where(
            Project.root == str(Path(project_root).resolve()))).first()
        existing = _find(session, "project", proj.id if proj else None, sha)
    else:
        existing = _find(session, "global", None, sha)
    if existing:
        if existing.archived:
            existing.archived = False
            session.add(existing)
            session.commit()
        return existing, True
    root = asset_root(scope, project_root)
    rel = _rel_path(sha, ext)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    meta = {"name": (name or Path(filename).stem)[:120], "original": Path(filename).name,
            "ext": ext, "mime": mimetypes.guess_type(str(path))[0] or "application/octet-stream",
            "sha256": sha}
    if real_kind == "image":
        meta.update(_image_meta(path, ext))
    elif real_kind == "audio":
        meta.update(_audio_meta(path))
    elif real_kind == "video":
        meta.update(_video_meta(path))
    elif real_kind == "font":
        meta.update(_font_meta(path))
    thumb = _make_thumb(path, path.with_name(f"{sha}.thumb.jpg"), real_kind, ext)
    if thumb:
        meta["thumb"] = f"{sha[:2]}/{thumb}"
    pid = None
    if scope == "project":
        proj = session.exec(select(Project).where(
            Project.root == str(Path(project_root).resolve()))).first()
        pid = proj.id if proj else None
    asset = Asset(scope=scope, project_id=pid, kind=real_kind, path=str(path), sha256=sha,
                  bytes=len(raw), meta_json=meta, tags_json=[str(t) for t in (tags or [])],
                  license_json=lic)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset, False


def _thumb_path(asset: Asset) -> Path | None:
    rel = (asset.meta_json or {}).get("thumb")
    if not rel:
        return None
    root = Path(asset.path).parent.parent
    p = root / rel
    return p if p.exists() else None


def _project_ids_for_scan(session: Session, project_ids: list[int] | None) -> list[Project]:
    if project_ids:
        return [p for p in (session.get(Project, i) for i in project_ids) if p]
    return session.exec(select(Project)).all()


def scan_usages(session: Session, sha: str | None = None,
                project_ids: list[int] | None = None) -> dict[str, list[dict]]:
    """扫描项目 timeline 文档里的图片图层 / 字体 / SFX，返回 sha → 使用处。"""
    out: dict[str, list[dict]] = {}
    for proj in _project_ids_for_scan(session, project_ids):
        doc = session.exec(select(ProjectDoc).where(
            ProjectDoc.project_id == proj.id, ProjectDoc.kind == "timeline")).first()  # type: ignore[arg-type]
        if not doc:
            continue
        for scene in (doc.content_json or {}).get("scenes") or []:
            sid = scene.get("id")
            for layer in scene.get("layers") or []:
                s = str(layer.get("assetSha") or "")
                if s and (sha is None or s == sha):
                    out.setdefault(s, []).append({
                        "projectId": proj.id, "projectName": proj.name, "sceneId": sid,
                        "layerId": layer.get("id"), "field": "layer",
                        "layerType": layer.get("type") or "image"})
            fs = str(scene.get("fontSha") or "")
            if fs and (sha is None or fs == sha):
                out.setdefault(fs, []).append({
                    "projectId": proj.id, "projectName": proj.name, "sceneId": sid,
                    "layerId": None, "field": "font", "layerType": "font"})
            for sfx in scene.get("audio_layers") or []:
                s = str(sfx.get("assetSha") or "")
                if s and (sha is None or s == sha):
                    out.setdefault(s, []).append({
                        "projectId": proj.id, "projectName": proj.name, "sceneId": sid,
                        "layerId": sfx.get("id"), "field": "sfx", "layerType": "audio"})
    return out


def asset_dto(asset: Asset, usages: list[dict] | None = None) -> dict:
    meta = dict(asset.meta_json or {})
    usages = usages or []
    return {
        "id": asset.id, "scope": asset.scope, "projectId": asset.project_id,
        "kind": asset.kind, "sha256": asset.sha256, "bytes": asset.bytes,
        "name": meta.get("name") or Path(asset.path).name,
        "tags": asset.tags_json or [], "license": asset.license_json or {},
        "archived": asset.archived, "meta": meta,
        "fileUrl": f"/api/assets/{asset.id}/file",
        "thumbUrl": f"/api/assets/{asset.id}/thumb" if meta.get("thumb") else "",
        "refCount": len(usages), "usages": usages,
        "createdAt": asset.created_at.isoformat() if asset.created_at else "",
    }


def list_assets(session: Session, scope: str, project_id: int | None = None,
                kind: str = "", q: str = "", include_archived: bool = False) -> list[dict]:
    stmt = select(Asset).where(Asset.scope == scope)
    if scope == "project":
        if not project_id:
            raise ApiError(ErrorCode.E_VALIDATION, "projectId 必填")
        stmt = stmt.where(Asset.project_id == project_id)
    if kind:
        stmt = stmt.where(Asset.kind == kind)
    rows = session.exec(stmt).all()
    usages = scan_usages(session, project_ids=[project_id] if scope == "project" else None)
    needle = (q or "").strip().lower()
    out = []
    for a in rows:
        if a.archived and not include_archived:
            continue
        dto = asset_dto(a, usages.get(a.sha256, []))
        if needle and needle not in dto["name"].lower() and needle not in " ".join(dto["tags"]).lower():
            continue
        out.append(dto)
    out.sort(key=lambda x: (x["kind"], x["name"].lower(), x["id"]))
    return out


def get_asset(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if not asset:
        raise ApiError(ErrorCode.E_NOT_FOUND, "资产不存在", status=404)
    return asset


def update_asset(session: Session, asset_id: int, payload: dict) -> Asset:
    asset = get_asset(session, asset_id)
    meta = dict(asset.meta_json or {})
    if "name" in payload:
        meta["name"] = str(payload.get("name") or "").strip()[:120]
    if "tags" in payload:
        asset.tags_json = [str(t).strip() for t in (payload.get("tags") or []) if str(t).strip()][:20]
    if "license" in payload:
        asset.license_json = _license(payload.get("license"))
    if "archived" in payload:
        asset.archived = bool(payload.get("archived"))
    asset.meta_json = meta
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def delete_asset(session: Session, asset_id: int, force: bool = False) -> dict:
    asset = get_asset(session, asset_id)
    usages = scan_usages(session, sha=asset.sha256,
                         project_ids=[asset.project_id] if asset.scope == "project" else None)
    sites = usages.get(asset.sha256, [])
    if sites and not force:
        raise ApiError(ErrorCode.E_ASSET_IN_USE,
                       f"资产被 {len(sites)} 处引用，不能删除",
                       status=409, details={"usages": sites, "refCount": len(sites)})
    for p in (Path(asset.path), _thumb_path(asset)):
        if p:
            p.unlink(missing_ok=True)
    session.delete(asset)
    session.commit()
    return {"deleted": asset_id, "usages": sites, "forced": bool(force)}


def replace_doc_refs(doc: dict, old_sha: str, new_sha: str) -> list[str]:
    changed: set[str] = set()
    for scene in doc.get("scenes") or []:
        sid = str(scene.get("id") or "")
        for layer in scene.get("layers") or []:
            if layer.get("assetSha") == old_sha:
                layer["assetSha"] = new_sha
                changed.add(sid)
        if scene.get("fontSha") == old_sha:
            scene["fontSha"] = new_sha
            changed.add(sid)
        for sfx in scene.get("audio_layers") or []:
            if sfx.get("assetSha") == old_sha:
                sfx["assetSha"] = new_sha
                changed.add(sid)
    return sorted(s for s in changed if s)


def font_coverage(path: str | Path, text: str) -> dict:
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(str(path), fontNumber=0, lazy=True)
        cmap: set[int] = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())
    except Exception as e:
        raise ApiError(ErrorCode.E_VALIDATION, f"字体解析失败：{e}")
    chars = sorted({ch for ch in (text or "") if not ch.isspace()})
    missing = [ch for ch in chars if ord(ch) not in cmap]
    return {"total": len(chars), "covered": len(chars) - len(missing),
            "missing": missing[:300], "missingCount": len(missing),
            "ok": not missing}


def waveform(path: str | Path, width: int = 2000) -> dict:
    width = max(100, min(int(width), 8000))
    try:
        res = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000",
                              "-f", "f32le", "-"], capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise ApiError(ErrorCode.E_VALIDATION, "音频解码超时")
    arr = np.frombuffer(res.stdout, dtype="<f4")
    if arr.size == 0:
        raise ApiError(ErrorCode.E_VALIDATION, "音频解码为空")
    n = max(1, arr.size // width)
    peaks = []
    for i in range(width):
        chunk = arr[i * n:(i + 1) * n]
        peaks.append([round(float(chunk.min()), 3), round(float(chunk.max()), 3)] if chunk.size
                     else [0, 0])
    return {"width": width, "peaks": peaks}


def _pick_asset(session: Session, project_root: str | Path, sha: str) -> Asset | None:
    root = Path(project_root).resolve()
    rows = session.exec(select(Asset).where(
        Asset.sha256 == sha, Asset.archived == False)).all()  # type: ignore[arg-type]
    for asset in rows:
        p = Path(asset.path)
        if asset.scope == "project" and p.exists():
            try:
                p.resolve().relative_to(root)
                return asset
            except ValueError:
                continue
    for asset in rows:
        if asset.scope == "global" and Path(asset.path).exists():
            return asset
    return None


def resolve_for_project(session: Session, project_root: str | Path, sha: str) -> dict | None:
    """给渲染器返回同源 URL；项目内资产优先，其次全局。"""
    root = Path(project_root).resolve()
    asset = _pick_asset(session, root, sha)
    if not asset:
        return None
    p = Path(asset.path)
    meta = asset.meta_json or {}
    if asset.scope == "project":
        rel = p.resolve().relative_to(root).as_posix()
        url = f"/project/{quote(rel, safe='/')}"
    else:
        rel = p.resolve().relative_to(settings.assets_dir.resolve()).as_posix()
        url = f"/global-assets/{quote(rel, safe='/')}"
    return {"url": url, "kind": asset.kind, "family": meta.get("family", ""),
            "name": meta.get("name", ""), "path": str(p)}


def resolve_path_for_project(session: Session, project_root: str | Path, sha: str) -> Path | None:
    asset = _pick_asset(session, project_root, sha)
    return Path(asset.path) if asset else None


def ensure_asset_shas(session: Session, source_project_id: int | None,
                      target_project_root: str | Path, shas: list[str]) -> list[int]:
    """模板实例化时把源项目的本地资产复制到目标项目；全局资产直接复用。"""
    target_root = Path(target_project_root).resolve()
    copied: list[int] = []
    for sha in shas or []:
        rows = session.exec(select(Asset).where(
            Asset.sha256 == sha, Asset.archived == False)).all()  # type: ignore[arg-type]
        if not rows:
            raise ApiError(ErrorCode.E_ASSET_MISSING, f"模板资产 {sha[:12]} 缺失")
        if any(r.scope == "global" for r in rows):
            continue
        if any(Path(r.path).resolve().is_relative_to(target_root) for r in rows):
            continue
        source = next((r for r in rows if r.project_id == source_project_id), rows[0])
        p = Path(source.path)
        if not p.exists():
            raise ApiError(ErrorCode.E_ASSET_MISSING, f"模板资产文件缺失：{sha[:12]}")
        meta = source.meta_json or {}
        ext = meta.get("ext") or p.suffix
        lic = dict(source.license_json or {})
        if source.kind == "font" and (not lic.get("source") or not lic.get("type")):
            lic.update({"source": "template", "type": "inherited"})
        new, _ = import_asset(
            session, "project", target_root, f"{sha[:12]}{ext}",
            base64.b64encode(p.read_bytes()).decode(), kind=source.kind,
            name=meta.get("name") or sha[:12], tags=source.tags_json or [],
            license=lic, author="template")
        copied.append(new.id or 0)
    return copied


def resolve_data_for_project(session: Session, project_root: str | Path, sha: str) -> dict | None:
    """预览页从 file:// 加载，资产内联为 data URL，避免跨源/路径问题。"""
    asset = _pick_asset(session, project_root, sha)
    if not asset:
        return None
    meta = asset.meta_json or {}
    raw = Path(asset.path).read_bytes()
    mime = meta.get("mime") or mimetypes.guess_type(asset.path)[0] or "application/octet-stream"
    url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return {"url": url, "kind": asset.kind, "family": meta.get("family", ""),
            "name": meta.get("name", ""), "path": asset.path}


def resolver_for_project(session: Session, project_root: str | Path, data: bool = False):
    cache: dict[str, dict | None] = {}

    def resolve(sha: str) -> dict | None:
        if sha not in cache:
            cache[sha] = (resolve_data_for_project(session, project_root, sha) if data
                          else resolve_for_project(session, project_root, sha))
        return cache[sha]

    return resolve
