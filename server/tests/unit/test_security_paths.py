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
