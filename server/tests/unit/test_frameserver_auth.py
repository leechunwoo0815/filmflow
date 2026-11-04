"""P2-32：FrameServer 进程内 token 鉴权。

绑定 127.0.0.1 只防外部，不防本机其它进程——引擎 URL 携带 ?tok=（进程内随机），
首载种 HttpOnly cookie 供 CSS/字体子资源过闸；不带 token 的任何请求一律 403。
复用探针也带 token：另一进程的帧服务会 403 → E_PORT_BUSY（fail-closed，
修掉"静默复用别的进程帧服务 → 引擎取到别的项目根 → 黑帧"的旧隐患）。
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
    monkeypatch.setattr(settings, "frame_port", _free_port())   # 不与 dev 抢 8787
    server = FrameServer(str(tmp_path))
    server.start()
    if server.httpd is None:            # 端口被别的进程占着且探针通过（复用）→ 测试没意义
        pytest.skip("帧服务端口被其它进程占用")
    yield server
    server.stop()


def _base(server) -> str:
    return f"http://127.0.0.1:{server.port}"


def test_rejects_missing_or_wrong_token(fs):
    r = httpx.get(f"{_base(fs)}/project/hello.txt", timeout=5, trust_env=False)
    assert r.status_code == 403, r.status_code
    r = httpx.get(f"{_base(fs)}/project/hello.txt", params={"tok": "wrong"}, timeout=5,
                  trust_env=False)
    assert r.status_code == 403
    r = httpx.head(f"{_base(fs)}/project/hello.txt", timeout=5, trust_env=False)
    assert r.status_code == 403, "HEAD 也必须过闸"


def test_accepts_query_token_and_sets_cookie(fs):
    r = httpx.get(f"{_base(fs)}/project/hello.txt", params={"tok": settings.frame_token},
                  timeout=5, trust_env=False)
    assert r.status_code == 200 and r.text == "ok"
    assert "ff_tok=" in (r.headers.get("set-cookie") or ""), "首载必须种 cookie 供子资源过闸"
    # 之后仅凭 cookie（无 query）也能过
    cookie = r.headers["set-cookie"].split(";", 1)[0]
    r2 = httpx.get(f"{_base(fs)}/project/hello.txt", headers={"Cookie": cookie},
                   timeout=5, trust_env=False)
    assert r2.status_code == 200 and r2.text == "ok"


def test_rejects_post_without_token_writes_with_token(fs):
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG-fake").decode()
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0"}, content=png.encode(),
                   timeout=5, trust_env=False)
    assert r.status_code == 403
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0", "tok": settings.frame_token},
                   content=png.encode(), timeout=5, trust_env=False)
    assert r.status_code == 204
    assert (fs.project_root / "out" / "frames" / "0000.png").exists()
