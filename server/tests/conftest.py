"""测试基座：导入前设置隔离的 FILMFLOW_HOME（测试共享一个临时库；A03 扫描幂等 upsert）。"""
import os
import sys
import tempfile
from pathlib import Path

_TEST_HOME = Path(tempfile.gettempdir()) / "filmflow-test-home"
_TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["FILMFLOW_HOME"] = str(_TEST_HOME)

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

import pytest  # noqa: E402

from app.config import detect_chrome, detect_ffmpeg, settings  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--allow-missing-env",
        action="store_true",
        default=False,
        help="允许在缺少风格库/Chrome/ffmpeg时跳过相关测试（默认直接失败，不静默skip）",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_style_library: 需要真实风格库")
    config.addinivalue_line("markers", "requires_chrome: 需要本机 Chrome")
    config.addinivalue_line("markers", "requires_ffmpeg: 需要本机 ffmpeg")
    config.addinivalue_line("markers", "slow: 真实 Chrome/ffmpeg 冒烟，耗时较长")


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """所有测试共享同一临时库：先建表，避免 BDD 在集成测试之前跑时缺表。"""
    from app.db import init_db
    init_db()
    yield


@pytest.fixture()
def isolated_db():
    """兼容签名：环境已在导入前隔离；保证建表。"""
    from app.db import init_db
    init_db()
    yield


@pytest.fixture(autouse=True)
def _env_guard(request):
    allow_missing = request.config.getoption("--allow-missing-env")
    checks = [
        ("requires_style_library", settings.style_library_root.is_dir(), f"风格库不存在 {settings.style_library_root}"),
        ("requires_chrome", detect_chrome() is not None, "未检测到 Chrome/Chromium"),
        ("requires_ffmpeg", detect_ffmpeg() is not None, "未检测到 ffmpeg"),
    ]
    for marker, present, reason in checks:
        if request.node.get_closest_marker(marker) and not present:
            message = f"E_ENV_MISSING: {reason}"
            if allow_missing:
                pytest.skip(message)
            pytest.fail(message, pytrace=False)
