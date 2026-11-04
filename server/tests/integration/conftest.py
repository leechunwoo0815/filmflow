"""集成测试隔离：启动临时 uvicorn + 独立 FILMFLOW_HOME/工作区，不碰生产 DB。"""
from __future__ import annotations

import json
import os
import shutil
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


def _seed_font_cache(home: Path) -> None:
    """把本机字体缓存拷进隔离 HOME，让集成测试**离线且确定**。

    C02 在拿不到本地字体时会 `curl` 联网下载 Noto Sans SC（17.7MB）：
    隔离 HOME 是全新的空库，于是每次集成渲染都变成一次网络赌博
    （实测同一测试第一次过、第二次 curl 收到 0 字节直接失败）。
    """
    src = Path(os.environ.get("FILMFLOW_PROD_HOME") or (Path.home() / ".filmflow")) / "cache" / "fonts"
    if not src.is_dir():
        return
    dst = home / "cache" / "fonts"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.ttf"):
        if not (dst / f.name).exists():
            shutil.copyfile(f, dst / f.name)


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
    _seed_font_cache(home)
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


@pytest.fixture(scope="session")
def style_id(api_client):
    """渲染级测试必须钉一个**能真出片**的风格。

    `?chips=可生产&limit=1` 返回的第一条随索引顺序变（实测同一测试第一次拿到 print 系、
    第三次拿到 pixel 系 AG1 → C01 直接判 `E_ENGINE_API_UNSUPPORTED`：code-video 还是
    Contract 1.0）。所以优先用验收脚本一直在用的 H2，退化时也只挑 print 家族。
    """
    r = api_client.get("/styles/H2")
    if r.status_code < 400:
        s = r.json()
        if s.get("available") and s.get("tokens_status") == "complete":
            return "H2"
    for family in ("print", ""):
        q = "/styles?chips=可生产&limit=10" + (f"&family={family}" if family else "")
        items = api_client.get(q).json().get("items") or []
        hit = next((i["id"] for i in items
                    if i.get("available") and i.get("tokens_status") == "complete"), None)
        if hit:
            return hit
    raise RuntimeError("隔离服务里没有可生产风格，渲染级测试无法进行")
