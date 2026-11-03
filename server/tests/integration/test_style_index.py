"""T02 集成测试：A03 索引器跑真实风格库（断言 341/343/10 集/193 封面 + FTS 中文子串）。"""
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

# P0-3：不做静默 skip；若环境缺风格库，require_style_library 会明确失败，除非传 --allow-missing-env。
import pytest

pytestmark = pytest.mark.requires_style_library


def test_scan_real_library(isolated_db):
    from app.services.style_index import scan_library
    report = scan_library()
    assert report["prompt_count"] == 341
    assert report["entries"] == 343
    assert report["covers"] == 193
    assert report["by_series"] == {"O": 98, "L": 59, "M": 40, "K": 38, "X": 31,
                                   "AG": 26, "V": 15, "Z": 15, "H": 12, "R": 7}
    assert Path(report["index_path"]).exists()


def test_matrix_and_fts(isolated_db):
    from app.services.style_index import library_status, scan_library
    scan_library()
    st = library_status()
    assert st["indexed"] and st["total_styles"] == 341
    m = st["matrix"]
    assert m["cover_complete"] + m["cover_incomplete"] + m["nocover_complete"] + m["nocover_incomplete"] == 341
    assert m["cover_complete"] + m["cover_incomplete"] == 193
    # 「水墨」经同义词扩展命中 Z 集全部（规格 §7.0 同义词）
    from sqlmodel import Session

    from app.db import engine
    from app.services.search import search_styles
    with Session(engine) as s:
        hits = search_styles(s, "水墨")
        assert hits, "「水墨」应有命中"
        z_hits = [r for r in hits if "中国风" in r.collection]
        assert len(z_hits) >= 10, f"同义词扩展后 Z 集命中应≥10，实际 {len(z_hits)}"


def test_matrix_measured_consistency(isolated_db):
    """解析器 v1.0 实测矩阵（ADR-0002 终版：词典扩展后）：218 complete / 123 补标。"""
    from app.services.style_index import library_status, scan_library
    scan_library()
    m = library_status()["matrix"]
    assert m["cover_complete"] + m["nocover_complete"] == 218
    assert m["label_queue"] == 123
    assert m["cover_complete"] == 173 and m["cover_incomplete"] == 20
    assert m["nocover_complete"] == 45 and m["nocover_incomplete"] == 103


def test_k_collection_incomplete(isolated_db):
    """夹具 9：K 集任一条 tokens 残缺 → 不进推荐。"""
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Style
    from app.services.style_index import scan_library
    scan_library()
    with Session(engine) as s:
        ks = s.exec(select(Style).where(Style.collection.contains("卡通"))).all()
        assert len(ks) == 38
        assert any(r.tokens_status == "incomplete" for r in ks)
        from app.services.recommend import recommend
        recs = recommend(s, "一条关于谣言传播的科普短片", None, None)
        assert all(not r["style_id"].startswith("K") for r in recs)


def test_id_scheme_matches_fixture(isolated_db):
    """D1 决定：O88/L28 形态的 ID 存在。"""
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Style
    from app.services.style_index import scan_library
    scan_library()
    with Session(engine) as s:
        ids = {r.id for r in s.exec(select(Style)).all()}
        assert "O88" in ids and "L28" in ids
