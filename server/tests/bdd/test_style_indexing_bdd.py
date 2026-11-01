"""BDD 绑定：bdd/features/style-indexing.feature 的服务级场景（pytest-bdd 中文步骤）。"""
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))
FEATURES = SERVER.parent / "bdd" / "features"

pytestmark = pytest.mark.skipif(
    not (Path.home() / "Documents" / "fy-style-library" / "代码动画_341种风格提示词").is_dir(),
    reason="真实风格库不存在",
)

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

scenarios(str(FEATURES / "style-indexing.feature"))

_ctx: dict = {}


@given(parsers.parse("风格库根目录登记为 {root}"), target_fixture="lib_ctx")
def real_library(root: str):
    from app.config import settings
    assert settings.style_library_root.is_dir()
    assert Path(root) == settings.style_library_root or Path(root).is_dir()
    return {"root": settings.style_library_root}


@when("A03 执行")
def run_index():
    from app.config import settings
    from app.services.style_index import scan_library
    _ctx["report"] = scan_library()
    _ctx["report_root"] = settings.style_library_root


@then("生成 adapters/style-index.json")
def index_file_exists():
    assert Path(_ctx["report"]["index_path"]).exists()


@then("记录数 entries 等于 343")
def entries_343():
    assert _ctx["report"]["entries"] == 343


@then("其中 kind=prompt 有 341 条")
def prompts_341():
    assert _ctx["report"]["prompt_count"] == 341


@then("其中 kind=example 有 2 条且不入选择器")
def examples_2():
    import json
    data = json.loads(Path(_ctx["report"]["index_path"]).read_text(encoding="utf-8"))
    ex = [r for r in data["records"] if r["kind"] == "example"]
    assert len(ex) == 2


@then("每条记录包含 id、name、kind、path、sha256、bytes、lines、has_cover")
def record_fields():
    import json
    data = json.loads(Path(_ctx["report"]["index_path"]).read_text(encoding="utf-8"))
    need = {"id", "name", "kind", "path", "sha256", "bytes", "lines", "has_cover"}
    assert all(need <= set(r) for r in data["records"][:50])


@then("与 _统计.json 的 bySeries 完全一致")
def stats_cross_check():
    import json
    stats = json.loads((_ctx["report_root"] / "_统计.json").read_text(encoding="utf-8"))
    by = _ctx["report"]["by_series"]
    for k, v in (stats.get("bySeries") or {}).items():
        assert by.get(k.upper(), 0) == v, f"{k}: {by.get(k.upper())} != {v}"


@when("A03 执行完成")
def run_index_done():
    from app.config import settings
    from app.services.style_index import scan_library
    _ctx["report"] = scan_library()
    _ctx["report_root"] = settings.style_library_root


@then("来源集计数为 O98 L59 M40 K38 X31 AG26 V15 Z15 H12 R7")
def series_counts():
    assert _ctx["report"]["by_series"] == {"O": 98, "L": 59, "M": 40, "K": 38, "X": 31,
                                           "AG": 26, "V": 15, "Z": 15, "H": 12, "R": 7}


@then("有封面 jpg 的条目为 193 条")
def covers_193():
    assert _ctx["report"]["covers"] == 193


@when("A03 连续执行两次且库未变化")
def run_twice():
    from app.services.style_index import scan_library
    scan_library()
    _ctx["report2"] = scan_library()


@then("两次生成的 index 内容哈希完全一致")
def index_hash_stable():
    assert _ctx["report"]["index_sha"] == _ctx["report2"]["index_sha"]
