"""路径安全：FrameServer 白名单拼接 + 项目根白名单。"""
from pathlib import Path

import pytest

from app.api.routes import _require_workspace_root
from app.config import settings
from app.engine.executors.pipeline import _safe_join
from app.errors import ApiError


def test_safe_join_allows_inside_and_rejects_traversal(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "ok.png").write_text("x", encoding="utf-8")
    assert _safe_join(root, "ok.png") == (root / "ok.png").resolve()
    assert _safe_join(root, "../etc/passwd") is None
    assert _safe_join(root, "/etc/passwd") is None
    assert _safe_join(root, "sub/../../outside") is None


def test_workspace_root_rejects_sibling_prefix():
    root = settings.workspace_roots[0].resolve()
    sibling = root.parent / f"{root.name}-evil"
    with pytest.raises(ApiError):
        _require_workspace_root(sibling)


def test_asset_file_svg_blocked_scripts(monkeypatch, tmp_path):
    """P3：SVG 资产必须带 CSP sandbox + nosniff（存储型脚本执行面关死）。"""
    import httpx
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, base_url="http://127.0.0.1")
    import base64
    svg = "data:image/svg+xml;base64," + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>').decode()
    r = c.post("/api/assets", json={"scope": "global", "filename": "t.svg", "data": svg,
                                    "kind": "image",
                                    "license": {"source": "t", "type": "CC0"}})
    assert r.status_code == 200, r.text
    aid = r.json()["asset"]["id"]
    try:
        fr = c.get(f"/api/assets/{aid}/file")
        assert fr.status_code == 200
        assert fr.headers.get("x-content-type-options") == "nosniff"
        assert "sandbox" in (fr.headers.get("content-security-policy") or "")
    finally:
        c.delete(f"/api/assets/{aid}", params={"force": "true"})
