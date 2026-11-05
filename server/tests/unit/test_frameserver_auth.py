"""P2-32/A2：FrameServer token 只护数据面（/project、/global-assets、帧 POST）。

/engine/ 的页面与脚本是入库的公开引擎代码（另有 CSP 头），不设闸——进程内随机
token 随重启轮换，长命 Chrome 的缓存页/旧 cookie 会让相对路径的引擎脚本 403 →
静帧全黑（2026-11-05 实测的 D04 过暗回归，见 Handler._needs_token 注释）。
A2（2026-11-06）：数据面凭据从 `?tok=`（会进访问日志/浏览器历史，且会被持久化进
artifact JSON）改为 **X-FilmFlow-Token header**；引擎页用 URL #fragment 携带
token（fragment 不进任何 HTTP 请求）。query 里的 tok 一律不再被接受。
复用探针打 /engine/ 公开面并带 header：另一进程的帧服务 403 → E_PORT_BUSY fail-closed。
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


def test_project_files_require_token_header(fs):
    url = f"{_base(fs)}/project/hello.txt"
    no_h = httpx.get(url, timeout=5, trust_env=False)
    assert no_h.status_code == 403, "无 header 必须拒绝"
    wrong = httpx.get(url, headers={"X-FilmFlow-Token": "wrong"}, timeout=5, trust_env=False)
    assert wrong.status_code == 403, "错 token 必须拒绝"
    stale_query = httpx.get(url, params={"tok": settings.frame_token}, timeout=5, trust_env=False)
    assert stale_query.status_code == 403, \
        "A2 回归钉：query ?tok= 一律不再被接受（凭据不许再进 URL/日志）"
    head = httpx.head(url, headers={"X-FilmFlow-Token": settings.frame_token},
                      timeout=5, trust_env=False)
    assert head.status_code == 200, "HEAD 也必须过闸（带 header）"
    ok = httpx.get(url, headers={"X-FilmFlow-Token": settings.frame_token},
                   timeout=5, trust_env=False)
    assert ok.status_code == 200 and ok.text == "ok"


def test_frame_posts_require_token(fs):
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG-fake").decode()
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0"}, content=png.encode(),
                   timeout=5, trust_env=False)
    assert r.status_code == 403, "无 header 的帧上传必须拒绝"
    r = httpx.post(f"{_base(fs)}/frame", params={"i": "0"}, content=png.encode(),
                   headers={"X-FilmFlow-Token": settings.frame_token},
                   timeout=5, trust_env=False)
    assert r.status_code == 204
    assert (fs.project_root / "out" / "frames" / "0000.png").exists()
