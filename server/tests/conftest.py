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


@pytest.fixture()
def isolated_db():
    """兼容签名：环境已在导入前隔离；保证建表。"""
    from app.db import init_db
    init_db()
    yield
