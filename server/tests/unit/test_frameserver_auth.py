"""P2-32：FrameServer token 只护数据面（/project、/global-assets、帧 POST）。

/engine/ 的页面与脚本是入库的公开引擎代码（另有 CSP 头），不设闸——进程内随机
token 随重启轮换，长命 Chrome 的缓存页/旧 cookie 会让相对路径的引擎脚本 403 →
静帧全黑（2026-11-05 实测的 D04 过暗回归，见 Handler._needs_token 注释）。
数据面 URL 全部由服务端构造（?tok=），不受 Chrome 缓存影响。
复用探针打受保护路径：另一进程的帧服务 403 → E_PORT_BUSY fail-closed。
"""
from __future__ import annotations

import base64
import socket

import httpx
import pytest

from app.config import settings
from app.engine.executors.pipeline import FrameServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture()
def fs(tmp_path, monkeypatch):
    (tmp_path / "hello.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(settings, "frame_port", _free_port())   # 不与 dev 抢 8787
    server = FrameServer(str(tmp_path))
    server.start()
    if server.httpd is None:            # 端口被别的进程占着且探针通过（复用）→ 测试没意义
        pytest.skip("帧服务端口被其它进程占用")
    yield server
    server.stop()


def _base(server) -> str:
    return f"http://127.0.0.1:{server.port}"


def test_engine_assets_are_public(fs):
    r = httpx.get(f"{_base(fs)}/engine/riso/entry/film_spec.html", timeout=5, trust_env=False)
    assert r.status_code == 200, "引擎代码不设 token 闸（缓存页/旧 cookie 不再致 403）"


def test_project_files_require_token(fs):
    r = httpx.get(f"{_base(fs)}/project/hello.txt", timeout=5, trust_env=False)
    assert r.status_code == 403
    r = httpx.get(f"{_base(fs)}/project/hello.txt", params={"tok": "wrong"}, timeout=5,
                  trust_env=False)
    assert r.status_code == 403
    r = httpx.head(f"{_base(fs)}/project/hello.txt", timeout=5, trust_env=False)
    assert r.status_code == 403, "HEAD 也必须过闸"
    r = httpx.get(f"{_base(fs)}/project/hello.txt", params={"tok": settings.frame_token},
                  timeout=5, trust_env=False)
    assert r.status_code == 200 and r.text == "ok"


def test_frame_posts_require_token(fs):
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG-fake").decode()
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0"}, content=png.encode(),
                   timeout=5, trust_env=False)
    assert r.status_code == 403
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0", "tok": settings.frame_token},
                   content=png.encode(), timeout=5, trust_env=False)
    assert r.status_code == 204
    assert (fs.project_root / "out" / "frames" / "0000.png").exists()
