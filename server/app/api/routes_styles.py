"""API 路由全集（规格 §9.1）。错误统一 ApiError 信封。"""
from __future__ import annotations

from ..logs import get as _get_log

_log = _get_log("routes")

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import engine, get_session
from ..errors import not_found
from ..models import (
    Style,
)
from ..services import recommend as rec_svc
from ..services import style_index as idx_svc
from . import deps

router = APIRouter(prefix="/api")


@router.post("/library/index")
async def library_index():
    report = idx_svc.scan_library()
    with Session(engine) as s:
        deps.audit(s, "library.index", report["index_path"], after=report)
    return report


@router.get("/library/status")
async def library_status():
    return idx_svc.library_status()


@router.get("/styles")
async def styles_list(q: str = "", family: str = "", collection: str = "", chips: str = "",
                      limit: int = 60, cursor: int = 0, session: Session = Depends(get_session)):
    """搜索（FTS5 trigram 中文子串）+ 筛选 chips（规格 §3.2）。"""
    chips_set = {c for c in chips.split(",") if c}
    from ..services.search import search_styles
    if q:
        items = search_styles(session, q, limit=400)
        if collection:
            items = [r for r in items if r.collection == collection]
        if family:
            items = [r for r in items if r.family == family or family in (r.sub_families_json or [])]
    else:
        items = [r for r in session.exec(select(Style)).all() if not r.id.startswith("EX")]
        if collection:
            items = [r for r in items if r.collection == collection]
        if family:
            items = [r for r in items if r.family == family or family in (r.sub_families_json or [])]
    if "可生产" in chips_set:
        items = [r for r in items if r.tokens_status == "complete" and r.engine_status == "available"]
    if "中文友好" in chips_set:
        items = [r for r in items if _zh_friendly(r)]
    if "低饱和" in chips_set:
        items = [r for r in items if _saturation(r) < 0.45]
    if "高密度" in chips_set:
        items = [r for r in items if "高密度" in r.search_text or "满版" in (r.tokens_json or {}).get("composition", [])]
    if "动态强" in chips_set:
        items = [r for r in items if (r.tokens_json or {}).get("motion", {}).get("pacing") in ("fast", "medium")]
    if "可印刷" in chips_set:
        items = [r for r in items if r.family in ("print", "collage")]
    if "≤3版" in chips_set or "<=3版" in chips_set:
        items = [r for r in items if r.family not in ("print", "collage") or len((r.tokens_json or {}).get("palette", [])) <= 3]
    total = len(items)
    items = items[cursor:cursor + limit]
    return {"total": total, "next_cursor": cursor + limit if cursor + limit < total else None,
            "items": [deps._style_dto(r) for r in items]}


def _fts_search(q: str) -> list[str] | None:
    try:
        with engine.connect() as conn:
            raw = conn.connection.driver_connection if hasattr(conn.connection, "driver_connection") else conn.connection
            rows = raw.execute("SELECT style_id FROM styles_fts WHERE styles_fts MATCH ? ORDER BY rank LIMIT 200", (q,)).fetchall()
            return [r[0] for r in rows]
    except Exception:   # noqa: BLE001 -- FTS 查询失败按"无候选"降级，主搜索路径不受影响
        return None


def _zh_friendly(r: Style) -> bool:
    t = " ".join((r.tokens_json or {}).get("type") or [])
    return any(w in t for w in ("黑体", "宋体", "900", "Noto", "中文")) or any("\u4e00" <= ch <= "\u9fff" for ch in r.name)


def _saturation(r: Style) -> float:
    """从 palette hex 估饱和度均值（0-1）。"""
    import colorsys
    pal = (r.tokens_json or {}).get("palette") or []
    if not pal:
        return 0.0
    vals = []
    for h in pal[:5]:
        try:
            hx = h.lstrip("#")
            if len(hx) == 3:
                hx = "".join(c * 2 for c in hx)
            rr, gg, bb = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
            vals.append(colorsys.rgb_to_hsv(rr, gg, bb)[1])
        except Exception:   # noqa: BLE001 -- 单个坏色值跳过，其余照算饱和度均值
            continue
    return sum(vals) / len(vals) if vals else 0.0


@router.get("/styles/{style_id}")
async def style_detail(style_id: str, session: Session = Depends(get_session)):
    r = session.get(Style, style_id)
    if not r:
        raise not_found("风格")
    return deps._style_dto(r)


@router.get("/styles/{style_id}/preview")
async def style_preview(style_id: str, variant: str = "thumb"):
    from fastapi.responses import FileResponse, Response
    from sqlmodel import select

    from ..models import StylePreview
    with Session(engine) as session:
        st = session.get(Style, style_id)
        # ① 预演缓存优先
        rows = session.exec(select(StylePreview).where(
            StylePreview.style_id == style_id, StylePreview.variant == variant)).all()
        for r in reversed(rows):
            p = Path(r.path)
            if p.exists():
                return FileResponse(p, media_type="image/png")
        # ② 自带封面（规格 §3.2：193 条封面直接展示）——同目录同名 jpg / covers/
        if st and st.has_cover:
            md = Path(st.path)
            for cand in (md.with_suffix(".jpg"), md.with_suffix(".jpeg"),
                         md.parent / "covers" / f"{md.stem}.jpg"):
                if cand.exists():
                    return FileResponse(cand, media_type="image/jpeg")
    # ③ 占位（不伪装）
    from ..services import previs as pv
    with Session(engine) as session:
        st2 = session.get(Style, style_id)
        reason = "待补标" if (st2 and st2.tokens_status != "complete") else "无预演"
    return Response(content=pv.placeholder_png(reason), media_type="image/png")


@router.get("/styles/{style_id}/similar")
async def styles_similar(style_id: str, session: Session = Depends(get_session)):
    return {"items": rec_svc.similar(session, style_id)}

