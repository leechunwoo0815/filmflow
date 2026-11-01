"""测试基座：隔离 FILMFLOW_HOME，保证测试不污染真实 ~/.filmflow。"""
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
def isolated_db(tmp_path, monkeypatch):
    """每个用例独立的 SQLite。"""
    monkeypatch.setenv("FILMFLOW_HOME", str(tmp_path))
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    from app import db as dbm
    importlib.reload(dbm)
    from app import events as ev
    importlib.reload(ev)
    dbm.init_db()
    yield dbm
