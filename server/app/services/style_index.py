"""A03 风格库索引器：扫描 风格提示词/ 十个子目录 → 生成 style-index.json + styles 表。

断言（规格 §4.1 / 夹具 9）：prompt_count=341、entries=343、10 集计数、封面 193、与 _统计.json 交叉核对。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from sqlmodel import Session, select

from ..atomicwrite import write_atomic
from ..config import settings
from ..db import engine
from ..errors import ApiError, ErrorCode
from ..models import Style
from .family_map import COLLECTION_FAMILY, EXPECTED_COLLECTION_COUNTS
from .token_parser import parse, search_text_of

COLLECTIONS_DIR = "风格提示词"
STATS_FILE = "_统计.json"
EXAMPLES_DIR = "示例"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prefix_of(collection_dir: str) -> str:
    return collection_dir.split("_")[0].replace("-", "").upper()


def _ensure_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS styles_fts USING fts5"
        "(style_id UNINDEXED, search_text, tokenize='trigram')"
    )


def rebuild_fts() -> int:
    with engine.connect() as conn:
        raw = conn.connection.driver_connection if hasattr(conn.connection, "driver_connection") else conn.connection
        _ensure_fts(raw)
        raw.execute("DELETE FROM styles_fts")
        rows = raw.execute("SELECT id, search_text FROM style").fetchall()
        raw.executemany("INSERT INTO styles_fts(style_id, search_text) VALUES (?, ?)", rows)
        raw.commit()
        return len(rows)


def scan_library() -> dict:
    """执行 A03：返回报告并落库。任何硬断言失败 → ApiError。"""
    root = settings.style_library_root
    prompt_dir = root / COLLECTIONS_DIR
    if not prompt_dir.is_dir():
        raise ApiError(ErrorCode.E_ENV_MISSING, f"风格提示词目录不存在：{prompt_dir}")

    records: list[dict] = []
    for coll_dir in sorted(p for p in prompt_dir.iterdir() if p.is_dir()):
        prefix = _prefix_of(coll_dir.name)
        for seq, md in enumerate(sorted(coll_dir.glob("*.md")), start=1):
            style_id = f"{prefix}{seq}"
            cover = _find_cover(coll_dir, md)
            records.append(_record(style_id, coll_dir.name, md, cover, kind="prompt"))
    # 示例（kind=example）：示例/<名字>/提示词.md
    ex_dir = root / EXAMPLES_DIR
    if ex_dir.is_dir():
        for seq, md in enumerate(sorted(ex_dir.glob("*/提示词.md")), start=1):
            records.append(_record(f"EX{seq}", EXAMPLES_DIR, md, None, kind="example"))

    prompts = [r for r in records if r["kind"] == "prompt"]
    if len(prompts) != 341:
        raise ApiError(ErrorCode.E_VALIDATION, f"prompt_count={len(prompts)} ≠ 341")
    if len(records) != 343:
        raise ApiError(ErrorCode.E_VALIDATION, f"entries={len(records)} ≠ 343")

    # 10 集计数断言
    by_series: dict[str, int] = {}
    for r in prompts:
        by_series[r["collection_prefix"]] = by_series.get(r["collection_prefix"], 0) + 1
    for prefix, expected in EXPECTED_COLLECTION_COUNTS.items():
        if by_series.get(prefix, 0) != expected:
            raise ApiError(ErrorCode.E_VALIDATION, f"来源集 {prefix} 计数 {by_series.get(prefix, 0)} ≠ {expected}")

    # 封面断言 193
    n_cover = sum(1 for r in prompts if r["has_cover"])
    if n_cover != 193:
        raise ApiError(ErrorCode.E_VALIDATION, f"封面数 {n_cover} ≠ 193")

    # 与 _统计.json 交叉核对
    stats_file = root / STATS_FILE
    if stats_file.exists():
        stats = json.loads(stats_file.read_text(encoding="utf-8"))
        if stats.get("total") != 341 or stats.get("withStill") != 193:
            raise ApiError(ErrorCode.E_VALIDATION, "_统计.json 与扫描结果不一致（total/withStill）")
        for k, v in (stats.get("bySeries") or {}).items():
            if by_series.get(k.upper(), 0) != v:
                raise ApiError(ErrorCode.E_VALIDATION, f"_统计.json bySeries[{k}]={v} 与扫描 {by_series.get(k.upper(), 0)} 不一致")

    # 写索引文件（库目录不可写则回落）
    index_payload = {
        "version": hashlib.sha256(
            json.dumps([[r["id"], r["sha256"]] for r in records], ensure_ascii=False).encode()
        ).hexdigest(),
        "entries": len(records),
        "prompt_count": len(prompts),
        "records": records,
    }
    index_path = _write_index(root, index_payload)

    # 落库（upsert）
    _upsert_styles(records, index_payload["version"])
    n = rebuild_fts()
    return {
        "prompt_count": len(prompts), "entries": len(records), "covers": n_cover,
        "by_series": by_series, "index_path": str(index_path), "index_sha": index_payload["version"],
        "fts_rows": n,
    }


def _find_cover(coll_dir: Path, md: Path) -> Path | None:
    stem = md.stem
    for cand in (coll_dir / f"{stem}.jpg", coll_dir / "covers" / f"{stem}.jpg",
                 coll_dir / f"{stem}.jpeg", coll_dir / "covers" / f"{stem}.jpeg"):
        if cand.exists():
            return cand
    return None


def _record(style_id: str, collection: str, md: Path, cover: Path | None, kind: str) -> dict:
    raw = md.read_bytes()
    return {
        "id": style_id, "kind": kind, "collection": collection,
        "collection_prefix": collection.split("_")[0].replace("-", "").upper() if kind == "prompt" else "EX",
        "name": md.stem, "path": str(md), "sha256": _sha256(md),
        "bytes": len(raw), "lines": raw.decode("utf-8", "replace").count("\n") + 1,
        "has_cover": bool(cover), "cover_path": str(cover) if cover else None,
    }


def _write_index(root: Path, payload: dict) -> Path:
    target = root / "adapters" / "style-index.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, json.dumps(payload, ensure_ascii=False, indent=1))
        return target
    except OSError:
        fallback = settings.index_path_fallback
        fallback.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(fallback, json.dumps(payload, ensure_ascii=False, indent=1))
        return fallback


def _upsert_styles(records: list[dict], index_sha: str) -> None:
    with Session(engine) as session:
        existing = {s.id: s for s in session.exec(select(Style)).all()}
        from .engines import engine_for_family
        for r in records:
            if r["kind"] != "prompt":
                continue
            prefix = r["collection_prefix"]
            fam = COLLECTION_FAMILY.get(prefix, {"family": "uncategorized", "sub": []})
            parsed = parse(Path(r["path"]).read_text(encoding="utf-8", errors="replace"), prefix)
            st = existing.get(r["id"]) or Style(id=r["id"])
            st.collection = r["collection"]
            st.family = st.family if (st.labeled and st.family) else fam["family"]
            st.sub_families_json = fam["sub"]
            st.name = r["name"]
            st.path = r["path"]
            st.sha256 = r["sha256"]
            st.bytes = r["bytes"]
            st.lines = r["lines"]
            st.has_cover = r["has_cover"]
            if not st.tokens_json or not st.labeled:
                st.tokens_json = parsed["tokens"]
            st.tokens_status = parsed["status"] if not st.labeled else "complete"
            st.missing_fields = [f for f in ["palette", "texture", "screen", "motion", "type", "composition"]
                                 if f not in parsed["fields"]]
            st.search_text = search_text_of(r["name"], Path(r["path"]).read_text(encoding="utf-8", errors="replace"))
            st.available = Path(r["path"]).exists()
            st.indexed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            eng = engine_for_family(st.family)
            st.engine_status = "available" if eng else "unavailable"
            st.preview_status = "cover" if st.has_cover else ("previs" if (st.tokens_status == "complete" and eng) else "no_preview")
            session.add(st)
        session.commit()


def library_status() -> dict:
    """库是否已索引 + 矩阵数字（选择器库信息条）。"""
    with Session(engine) as session:
        rows = session.exec(select(Style)).all()
        prompts = [r for r in rows if not r.id.startswith("EX")]
        matrix = {
            "cover_complete": sum(1 for r in prompts if r.has_cover and r.tokens_status == "complete"),
            "cover_incomplete": sum(1 for r in prompts if r.has_cover and r.tokens_status != "complete"),
            "nocover_complete": sum(1 for r in prompts if not r.has_cover and r.tokens_status == "complete"),
            "nocover_incomplete": sum(1 for r in prompts if not r.has_cover and r.tokens_status != "complete"),
        }
        matrix["producible"] = sum(
            1 for r in prompts if r.tokens_status == "complete" and r.engine_status == "available"
        )
        matrix["label_queue"] = sum(1 for r in prompts if r.tokens_status != "complete")
        return {
            "indexed": bool(rows), "total_styles": len(prompts),
            "collections": sorted({r.collection for r in prompts}),
            "matrix": matrix,
        }
