"""新项目的风格可用性：只有 Contract 2.x 族才允许进新项目（engine_v2_ok）。

背景：engine_status 只回答「家族有没有引擎」，不回答「契约几代」——code-video/ink
是 1.0，把 127 个版式标成 available，而 R2.0 新项目点了就在 C01 炸
（E_ENGINE_API_UNSUPPORTED，2026-11-07 老板首次 UI 实测踩中）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))


def test_contract2_families_only_riso_coverage():
    from app.services.engines import contract2_families

    assert contract2_families() == {"print", "collage"}, \
        "riso 2.0.0 覆盖 print/collage；code-video/ink 是 1.0 不算"


def test_style_dto_carries_engine_v2_ok():
    from app.api.deps import _style_dto
    from app.models import Style

    ok = _style_dto(Style(id="H2", name="H2 BlockFrame",
                          collection="H_现成版式", family="print"))
    bad = _style_dto(Style(id="X1", name="X1", collection="X_code-video",
                           family="infographic"))
    ink = _style_dto(Style(id="Z1", name="Z1", collection="Z_中国风", family="ink"))
    assert ok["engine_v2_ok"] is True
    assert bad["engine_v2_ok"] is False
    assert ink["engine_v2_ok"] is False


def test_recommend_excludes_contract1_families():
    """推荐流的候选必须整体落在 2.x 族内（老板第一次推荐就拿到 code-video 的教训）。"""
    import inspect

    from app.services import recommend as rec

    src = inspect.getsource(rec.recommend)
    assert "contract2_families()" in src, \
        "recommend 必须按 contract2_families 过滤候选"
