"""集成测试隔离：启动临时 uvicorn + 独立 FILMFLOW_HOME/工作区，不碰生产 DB。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_health(base: str, proc: subprocess.Popen) -> None:
    deadline = time.time() + 30
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise RuntimeError(f"集成服务提前退出 code={proc.returncode}\n{out[-4000:]}")
        try:
            r = httpx.get(f"{base}/health", timeout=1, trust_env=False)
            if r.status_code == 200:
                return
            last = f"{r.status_code} {r.text[:200]}"
        except Exception as e:
            last = str(e)
        time.sleep(0.5)
    raise RuntimeError(f"集成服务未在 30s 内就绪：{last}")


@pytest.fixture(scope="session")
def isolated_api(tmp_path_factory):
    home = tmp_path_factory.mktemp("filmflow-int-home")
    workspace = tmp_path_factory.mktemp("filmflow-workspaces")
    env = os.environ.copy()
    env["FILMFLOW_HOME"] = str(home)
    env["FILMFLOW_WORKSPACE_ROOTS"] = json.dumps([str(workspace)])
    port = _free_port()
    base = f"http://127.0.0.1:{port}/api"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "critical"],
        cwd=str(SERVER_DIR), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        _wait_health(base, proc)
        with httpx.Client(base_url=base, timeout=180, trust_env=False) as seed:
            r = seed.post("/library/index", json={})
            if r.status_code >= 400:
                raise RuntimeError(f"隔离服务初始化风格库失败：{r.status_code} {r.text[:1000]}")
            r = seed.get("/styles?chips=可生产&limit=1")
            if r.status_code >= 400 or not r.json().get("items"):
                raise RuntimeError(f"隔离服务可生产风格为空：{r.status_code} {r.text[:500]}")
        yield base, Path(workspace)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture(scope="session")
def api_client(isolated_api):
    base, _ = isolated_api
    with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
        yield client


@pytest.fixture()
def project_root(isolated_api):
    _, workspace = isolated_api
    root = workspace / f"it-{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True)
    return root
