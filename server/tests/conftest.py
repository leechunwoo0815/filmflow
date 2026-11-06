"""测试基座：导入前设置一次性隔离 FILMFLOW_HOME（每次 pytest 独立临时库；A03 扫描幂等 upsert）。"""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# 生产库路径必须在覆盖 FILMFLOW_HOME 之前取：P0-3 的验收原句是"连续两次 pytest 后
# 生产 DB 项目数不变"，所以要在会话前后各读一次真实库（只读，绝不写）。
_PROD_HOME = Path(os.environ.get("FILMFLOW_HOME") or (Path.home() / ".filmflow"))
_PROD_DB = _PROD_HOME / "filmflow.db"
# 子 conftest（integration）拿不到覆盖前的 env，用这个键把真实 HOME 传下去
os.environ["FILMFLOW_PROD_HOME"] = str(_PROD_HOME)

_TEST_HOME = Path(tempfile.mkdtemp(prefix="filmflow-test-home-"))
os.environ["FILMFLOW_HOME"] = str(_TEST_HOME)

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

import pytest

from app.config import detect_chrome, detect_ffmpeg, settings

_PROD_TABLES = ("project", "run", "draft", "docrevision", "job", "asset", "template")


def _prod_snapshot() -> dict | None:
    """生产库计数快照；库不存在（干净机器）返回 None，守卫自动跳过。"""
    if not _PROD_DB.exists():
        return None
    con = sqlite3.connect(f"file:{_PROD_DB}?mode=ro", uri=True, timeout=5)
    try:
        counts = {}
        for t in _PROD_TABLES:
            try:
                counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
            except sqlite3.OperationalError:
                continue
        counts["project_ids"] = [r[0] for r in con.execute("select id from project order by id")]
        return counts
    finally:
        con.close()


def pytest_addoption(parser):
    parser.addoption(
        "--allow-missing-env",
        action="store_true",
        default=False,
        help="允许在缺少风格库/Chrome/ffmpeg时跳过相关测试（默认直接失败，不静默skip）",
    )
    parser.addoption(
        "--allow-prod-drift",
        action="store_true",
        default=False,
        help="允许测试期间生产库发生变化（例如同时在用工作台）；默认会话结束后计数必须一致",
    )


# H9-c：两个"本机才有"的字体面。路径必须和用例真正读的那个一致，否则门禁与测试说的是两套话。
_SYSTEM_FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
_CACHED_FONT = _PROD_HOME / "cache" / "fonts" / "NotoSansSC[wght].ttf"


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_style_library: 需要真实风格库")
    config.addinivalue_line("markers", "requires_chrome: 需要本机 Chrome")
    config.addinivalue_line("markers", "requires_ffmpeg: 需要本机 ffmpeg")
    config.addinivalue_line("markers", "requires_system_font: 需要 macOS 系统字体（Arial.ttf）")
    config.addinivalue_line("markers", "requires_cached_font: 需要本机已缓存的 Noto Sans SC")
    config.addinivalue_line("markers", "slow: 真实 Chrome/ffmpeg 冒烟，耗时较长")


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """所有测试共享本次运行的临时库：先建表，避免 BDD 在集成测试之前跑时缺表。"""
    from app.db import init_db
    init_db()
    try:
        yield
    finally:
        from app.db import engine
        engine.dispose()
        shutil.rmtree(_TEST_HOME, ignore_errors=True)


@pytest.fixture()
def isolated_db():
    """兼容签名：环境已在导入前隔离；保证建表。"""
    from app.db import init_db
    init_db()
    yield


@pytest.fixture(scope="session", autouse=True)
def _production_db_untouched(request):
    """P0-3 验收守卫：跑完整套测试，生产库计数必须一模一样。

    专家原句是"连续两次 pytest 后生产 DB 项目数不变"，此前只靠人工核对（还核对错过：
    文档写"当前 24"、库里其实 25）。集成测试现在起独立 uvicorn + 独立 FILMFLOW_HOME，
    这条守卫就是那道隔离真的没漏的证明——漏了会在这里炸，而不是靠人事后发现。
    """
    before = _prod_snapshot()
    yield
    if before is None or request.config.getoption("--allow-prod-drift"):
        return
    after = _prod_snapshot()
    if after == before:
        return
    delta = {k: (before.get(k), after.get(k)) for k in set(before) | set(after or {})
             if k != "project_ids" and before.get(k) != (after or {}).get(k)}
    new_ids = sorted(set((after or {}).get("project_ids", [])) - set(before["project_ids"]))
    gone_ids = sorted(set(before["project_ids"]) - set((after or {}).get("project_ids", [])))
    pytest.fail(
        f"测试期间生产库 {_PROD_DB} 被写脏了：计数变化 {delta}"
        f"{'；新增项目 ' + str(new_ids) if new_ids else ''}"
        f"{'；消失项目 ' + str(gone_ids) if gone_ids else ''}"
        "。若这是你自己在用工作台，加 --allow-prod-drift 重跑。", pytrace=False)


@pytest.fixture(autouse=True)
def _env_guard(request):
    allow_missing = request.config.getoption("--allow-missing-env")
    checks = [
        ("requires_style_library", settings.style_library_root.is_dir(), f"风格库不存在 {settings.style_library_root}"),
        ("requires_chrome", detect_chrome() is not None, "未检测到 Chrome/Chromium"),
        ("requires_ffmpeg", detect_ffmpeg() is not None, "未检测到 ffmpeg"),
        # H9-c：以前这些用例是"字体不在就 pytest.skip"，本机永远绿、CI 上静默少跑 N 条，
        # 从没人发现。现在统一走同一扇门：缺环境就**硬失败**，只有 --allow-missing-env 才 skip。
        ("requires_system_font", _SYSTEM_FONT.is_file(), f"系统字体不在 {_SYSTEM_FONT}（macOS 专有路径）"),
        ("requires_cached_font", _CACHED_FONT.is_file(), f"Noto Sans SC 缓存不在 {_CACHED_FONT}"),
    ]
    for marker, present, reason in checks:
        if request.node.get_closest_marker(marker) and not present:
            message = f"E_ENV_MISSING: {reason}"
            if allow_missing:
                pytest.skip(message)
            pytest.fail(message, pytrace=False)
