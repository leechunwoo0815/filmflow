"""B5 判官 #7/#8：落盘原子性 + 文件响应 Content-Type/CSP 策略。

覆盖两条曾被判官点名的静默面：
- 崩溃/并发留下的半文件被 `exists()` 当成有效产物（帧/快照/manifest）。
- 产物与资产按后缀猜类型，`x.html`/未知后缀同源内联 = 存储型脚本执行。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app import atomicwrite
from app.security import (
    EXECUTABLE_SUFFIXES,
    INLINE_MEDIA,
    file_response,
    frameserver_denied,
    frameserver_headers,
)

# ---------- write_atomic ----------

def test_write_atomic_creates_parents_and_leaves_no_temp(tmp_path):
    dst = tmp_path / "deep" / "nested" / "manifest.json"
    write_atomic = atomicwrite.write_atomic
    write_atomic(dst, json.dumps({"ok": True}))
    assert json.loads(dst.read_text()) == {"ok": True}
    assert list(dst.parent.iterdir()) == [dst]  # 没有遗留 .tmp


def test_write_atomic_bytes_and_str_use_same_path(tmp_path):
    p = tmp_path / "frame.png"
    atomicwrite.write_atomic(p, b"\x89PNG\r\n")
    assert p.read_bytes() == b"\x89PNG\r\n"
    atomicwrite.write_atomic(p, "replaced")
    assert p.read_text() == "replaced"


def test_temp_names_are_unique_across_writers(tmp_path, monkeypatch):
    """同目标并发不能再共用一个临时名（旧 `with_suffix(".tmp")` 会互相踩）。"""
    seen: list[str] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(atomicwrite.os, "replace", spy)
    d = tmp_path / "out"
    atomicwrite.write_atomic(d / "a.json", "{}")
    atomicwrite.write_atomic(d / "a.json", '{"n": 1}')
    assert len(seen) == 2 and seen[0] != seen[1]
    assert str(os.getpid()) in seen[0]


def test_writer_fsyncs_file_and_parent_dir(tmp_path, monkeypatch):
    calls: list[int] = []
    real = os.fsync

    def spy(fd):
        calls.append(fd)
        return real(fd)

    monkeypatch.setattr(atomicwrite.os, "fsync", spy)
    p = tmp_path / "x.json"
    atomicwrite.write_atomic(p, "{}")
    assert len(calls) >= 2  # 文件 + 父目录


def test_failed_replace_leaves_target_intact(tmp_path, monkeypatch):
    target = tmp_path / "snap.json"
    atomicwrite.write_atomic(target, "v1")

    def boom(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(atomicwrite.os, "replace", boom)
    with pytest.raises(OSError):
        atomicwrite.write_atomic(target, "v2")
    assert target.read_text() == "v1"          # 旧内容还在
    assert list(tmp_path.glob(".*.tmp")) == []  # 临时名已清理


def test_prune_tmp_only_removes_our_pattern_and_old_files(tmp_path):
    d = tmp_path / "frames"
    d.mkdir()
    stale = d / ".0001.png.123.abcd1234.tmp"
    stale.write_text("x")
    os.utime(stale, (0, 0))
    fresh = d / ".0002.png.123.abcd5678.tmp"
    fresh.write_text("x")
    unrelated = d / "keep.tmp"
    unrelated.write_text("x")
    removed = atomicwrite.prune_tmp([d], older_than_s=60)
    assert removed == 1
    assert not stale.exists() and fresh.exists() and unrelated.exists()


def test_no_bare_writers_left_in_server_app():
    """新代码必须走 write_atomic：`exists()` 判据遍地都是，半文件会被当有效产物。"""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    offenders = []
    for py in sorted(app_dir.rglob("*.py")):
        if py.name == "atomicwrite.py":
            continue
        for n, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if ".write_text(" in code or ".write_bytes(" in code:
                offenders.append(f"{py.relative_to(app_dir)}:{n}")
    assert offenders == [], f"非原子写站点复现了：{offenders}"


# ---------- :8787 帧服务 ----------

@pytest.mark.parametrize("path,denied", [
    ("/project/scenes/S01.base.program.json", False),
    ("/project/fonts/embed.css", False),
    ("/project/card/evil.html", True),
    ("/global-assets/ab/abcd.svg", False),      # SVG 仍要能当图片用
    ("/global-assets/ab/abcd.js", True),
    ("/global-assets/ab/evil.xhtml", True),
    ("/engine/r1/index.html?w=1", False),       # 引擎页面必须能执行自己的脚本
    ("/etc/passwd", False),                     # 非数据根：translate_path 本来就 404
])
def test_frameserver_denies_documents_under_data_roots(path, denied):
    assert frameserver_denied(path) is denied


@pytest.mark.parametrize("path", ["/project/a.json", "/global-assets/a.svg"])
def test_frameserver_headers_sandbox_data_roots(path):
    h = frameserver_headers(path)
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in h["Content-Security-Policy"]


def test_frameserver_headers_do_not_sandbox_engine():
    h = frameserver_headers("/engine/r1/index.html")
    assert h == {"X-Content-Type-Options": "nosniff"}


# ---------- API 文件响应 ----------

@pytest.mark.parametrize("suffix,expect_media,expect_disposition", [
    (".png", "image/png", "inline"),
    (".mp4", "video/mp4", "inline"),
    (".json", "application/json", "inline"),
    (".srt", "text/plain; charset=utf-8", "inline"),
    (".svg", "image/svg+xml", "inline"),        # 时间轴要用它，靠 CSP 而不是断供
    (".html", "application/octet-stream", "attachment"),
    (".xml", "application/octet-stream", "attachment"),
    (".js", "application/octet-stream", "attachment"),
    (".exe", "application/octet-stream", "attachment"),
    (".no_such_ext", "application/octet-stream", "attachment"),
])
def test_file_response_whitelists_content_type(tmp_path, suffix, expect_media, expect_disposition):
    p = tmp_path / f"artifact{suffix}"
    p.write_bytes(b"<script>alert(1)</script>" if suffix == ".html" else b"data")
    resp = file_response(p)
    assert resp.media_type == expect_media
    cd = resp.headers["content-disposition"]
    assert cd.startswith(expect_disposition)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]
    assert INLINE_MEDIA[".svg"] == "image/svg+xml"
    assert EXECUTABLE_SUFFIXES >= {".html", ".xml", ".js"}


def test_stored_html_artifact_downloads_instead_of_executing():
    """判官 #7 要求的存储型脚本回归：同源直开不能变成 UI 源上的脚本。

    产物目录必须落在工作区白名单内（`artifact_file` 会校验），所以用 filmflow-projects 下
    的一次性目录；库是本次 pytest 的临时 FILMFLOW_HOME，跑完自己清干净。
    """
    import shutil

    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.config import settings
    from app.db import engine
    from app.main import app
    from app.models import Artifact, Project, Run, Workflow

    root = next(iter(settings.workspace_roots)) / "filmflow-projects" / f".resp-policy-{os.getpid()}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    ids: list[int] = []
    try:
        with Session(engine) as s:
            proj = Project(name=f"resp-policy-{os.getpid()}", root=str(root))
            s.add(proj)
            s.commit()
            s.refresh(proj)
            pid = proj.id
            wf = Workflow(project_id=pid)      # Artifact.run_id 有 FK，foreign_keys=ON 会拦假 run
            s.add(wf)
            s.commit()
            s.refresh(wf)
            run = Run(workflow_id=wf.id)
            s.add(run)
            s.commit()
            s.refresh(run)
            for kind, fname, body in (("HTML", "x.html", "<script>alert(1)</script>"),
                                      ("SVG", "y.svg",
                                       '<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>')):
                f = root / fname
                f.write_text(body)
                art = Artifact(run_id=run.id, node_id="D02", type=kind, path=str(f), sha256=kind.lower())
                s.add(art)
                s.commit()
                s.refresh(art)
                ids.append(art.id)

        with TestClient(app, base_url="http://127.0.0.1") as c:  # TrustedHostMiddleware 只放行本机 host
            html = c.get(f"/api/artifacts/{ids[0]}/file")
            assert html.status_code == 200, html.text
            assert html.headers["content-type"].startswith("application/octet-stream")
            assert html.headers["content-disposition"].startswith("attachment")
            assert html.headers["x-content-type-options"] == "nosniff"

            svg = c.get(f"/api/artifacts/{ids[1]}/file")
            # SVG 还是时间轴要用的图片，但响应带 sandbox CSP：直接导航过去脚本不执行
            assert svg.headers["content-type"].startswith("image/svg+xml")
            assert "sandbox" in svg.headers["content-security-policy"]

        with Session(engine) as s:  # 级联清理走生产同一套服务，别留下 run/workflow 孤儿
            from app.services import project_cleanup as cleanup
            cleanup.delete_project(s, pid, remove_dir=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
