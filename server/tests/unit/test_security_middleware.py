"""P0-1：本机 Host 白名单与跨源写请求拒绝。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.security import LocalOriginMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
    app.add_middleware(LocalOriginMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.post("/write")
    def write():
        return {"ok": True}

    return TestClient(app, base_url="http://127.0.0.1")


def test_rejects_non_local_host():
    c = _client()
    assert c.get("/ping").status_code == 200
    assert c.get("/ping", headers={"Host": "attacker.example.com"}).status_code == 400


def test_rejects_cross_origin_write():
    c = _client()
    r = c.post("/write", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "E_ORIGIN_DENIED"


def test_allows_local_origin_and_cli_requests():
    c = _client()
    assert c.post("/write", headers={"Origin": "http://127.0.0.1:3000"}).status_code == 200
    assert c.post("/write", headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert c.post("/write").status_code == 200
    assert c.get("/ping", headers={"Origin": "https://evil.example.com"}).status_code == 200
