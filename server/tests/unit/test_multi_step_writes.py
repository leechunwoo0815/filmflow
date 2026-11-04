"""P1-09：多步写事务的故障注入——任何一步失败都不允许留半成品。

四条路径：
1. take branch：Run 构造失败 → 已保存的 script/timeline/profile 必须倒序回滚；
2. assets replace：多项目循环中途失败 → 已改项目必须回滚；
3. qa extend_scene：profile 保存失败 → timeline 必须被补偿回滚（P0-5 已有，回归锁定）；
4. saved 模板 materialize：项目行出现后任何失败 → 半成品项目（库行+目录）必须被清掉。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))
from app.db import engine
from app.models import Project, ProjectDoc, Run, Workflow
from app.services import project_docs as docs
from app.services import qa


def _make_project(tmp_path: Path, name: str):
    root = tmp_path / name
    (root / "card").mkdir(parents=True, exist_ok=True)
    (root / "card" / "copy.txt").write_text("第一句。第二句。第三句。", encoding="utf-8")
    session = Session(engine)
    p = Project(name=name, root=str(root))
    session.add(p)
    session.commit()
    session.refresh(p)
    session.add(Workflow(project_id=p.id, graph_json={"nodes": [], "edges": []}))
    session.commit()
    pid, root = p.id, str(p.root)
    return session, pid, root


def _cleanup(session: Session, pid: int, root: str):
    from app.services.project_cleanup import delete_project
    session.rollback()
    session.close()
    with Session(engine) as s:
        try:
            delete_project(s, pid, remove_dir=False)  # 级联清行；目录单独删
        except Exception:
            pass
    shutil.rmtree(root, ignore_errors=True)


def _row(pid: int, kind: str) -> ProjectDoc | None:
    with Session(engine) as s:
        return s.exec(select(ProjectDoc).where(
            ProjectDoc.project_id == pid, ProjectDoc.kind == kind)).first()


def _hash(content) -> str:
    return docs.content_hash(content or {})


# ---------- 1. take branch：Run 构造失败 → 文档倒序回滚 ----------

def test_take_branch_rolls_back_docs_when_run_creation_fails(tmp_path: Path, monkeypatch):
    from app.api import routes as routes_mod

    session, pid, root = _make_project(tmp_path, "branch-fail")
    try:
        docs.save_doc(session, pid, "script", {"text": "原脚本。", "title": "t"}, 0, "seed")
        docs.save_doc(session, pid, "timeline",
                      {"schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 2.0,
                       "frames": 48, "scenes": [{"id": "S01", "start": 0.0, "end": 2.0}],
                       "events": [], "tracks": []}, 0, "seed")
        wf = session.exec(select(Workflow).where(Workflow.project_id == pid)).first()
        src = Run(workflow_id=wf.id)
        session.add(src)
        session.commit()
        session.refresh(src)
        # branch 的源数据来自 runs/<id>/docs/snapshot.json —— 先落一份
        run_docs = Path(root) / "runs" / str(src.id) / "docs"
        run_docs.mkdir(parents=True, exist_ok=True)
        (run_docs / "snapshot.json").write_text(json.dumps(
            {"schema": "filmflow.snapshot/1",
             "docs": {"timeline": {"version": 1, "content": {
                 "schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 3.0,
                 "frames": 72,
                 "scenes": [{"id": "S01", "start": 0.0, "end": 3.0,
                             "text": "快照句子。"}]}}}}), encoding="utf-8")
        (run_docs / "timeline.doc.json").write_text(json.dumps(
            {"schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 3.0,
             "frames": 72,
             "scenes": [{"id": "S01", "start": 0.0, "end": 3.0, "text": "快照句子。"}]}),
            encoding="utf-8")
        before = {k: deepcopy(_row(pid, k).content_json) for k in ("script", "timeline")}

        monkeypatch.setattr(routes_mod, "audit", lambda *a, **kw: None)

        class BoomOnAdd:
            '''代理 session：对 branch 新建的 Run（带 parent_run_id）在 add 时抛错。'''
            def __init__(self, real):
                self._real = real
            def __getattr__(self, item):
                return getattr(self._real, item)
            def add(self, obj):
                if isinstance(obj, Run) and getattr(obj, "id", None) is None \
                        and getattr(obj, "parent_run_id", None) is not None:
                    raise RuntimeError("injected run failure")
                return self._real.add(obj)
            def commit(self):
                return self._real.commit()
            def refresh(self, *a):
                return self._real.refresh(*a)

        with pytest.raises(RuntimeError, match="injected run failure"):
            asyncio.new_event_loop().run_until_complete(
                routes_mod.project_take_branch(pid, src.id,
                                               routes_mod.TakeBranchIn(author="test"),
                                               session=BoomOnAdd(session)))

        for kind in ("script", "timeline"):
            now = _row(pid, kind)
            assert now is not None and _hash(now.content_json) == _hash(before[kind]), \
                f"{kind} 未回滚（留了半分支）"
        with Session(engine) as s:
            runs = s.exec(select(Run).where(Run.workflow_id == wf.id)).all()
            assert len(runs) == 1, "不应留下新 Run"
    finally:
        _cleanup(session, pid, root)


# ---------- 2. assets replace：第二个项目失败 → 第一个回滚 ----------

def test_assets_replace_rolls_back_previous_projects_on_failure(tmp_path: Path, monkeypatch):
    from app.api import routes as routes_mod
    from app.services import assets as assets_svc

    session, pid_a, root_a = _make_project(tmp_path, "rep-1")
    session_b, pid_b, root_b = _make_project(tmp_path, "rep-2")
    session_b.close()  # 行已落库；后续只用 pid/root 纯值
    try:
        # 两个项目各引用同一个全局资产 sha
        png = tmp_path / "dot.png"
        from PIL import Image
        Image.new("RGB", (4, 4), (200, 30, 30)).save(png)
        data = base64_data(png)
        a, _ = assets_svc.import_asset(session, "global", None, "dot.png", data,
                                       kind="image",
                                       license={"source": "自制", "type": "CC0"})
        sha = a.sha256
        for pid_x in (pid_a, pid_b):
            docs.save_doc(session, pid_x, "timeline",
                          {"schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 1.0,
                           "frames": 24, "scenes": [{"id": "S01", "start": 0.0, "end": 1.0,
                                                     "layers": [{"id": "L1", "type": "image",
                                                                 "assetSha": sha}]}],
                           "events": [], "tracks": []}, 0, "seed")
        png2 = tmp_path / "dot2.png"
        Image.new("RGB", (4, 4), (30, 200, 30)).save(png2)
        b, _ = assets_svc.import_asset(session, "global", None, "dot2b.png",
                                       base64_data(png2), kind="image",
                                       license={"source": "自制", "type": "CC0"})
        before_a = deepcopy(_row(pid_a, "timeline").content_json)

        # 注入：第二个项目的 save_doc 抛错
        real_save = docs.save_doc
        calls = {"n": 0}

        def save_doc_then_boom(s, pid, kind, content, base_version, author="local", **kw):
            if kind == "timeline" and author == "asset-replace":
                calls["n"] += 1
                if calls["n"] >= 2:
                    raise RuntimeError("injected replace failure")
            return real_save(s, pid, kind, content, base_version, author, **kw)

        monkeypatch.setattr(docs, "save_doc", save_doc_then_boom)
        with pytest.raises(RuntimeError, match="injected replace failure"):
            asyncio.new_event_loop().run_until_complete(
                routes_mod.assets_replace(a.id, type("P", (), {"assetId": b.id})(),
                                          session=session))
        monkeypatch.undo()
        now_a = _row(pid_a, "timeline")
        assert _hash(now_a.content_json) == _hash(before_a), "项目 A 未回滚（半替换）"
    finally:
        _cleanup(session, pid_a, root_a)
        _cleanup(session, pid_b, root_b)


def base64_data(png: Path) -> str:
    import base64
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()


# ---------- 3. qa extend_scene：profile 失败 → timeline 补偿（回归锁定） ----------

def test_qa_extend_scene_profile_failure_compensates(tmp_path: Path, monkeypatch):
    session, proj = _qa_ready(tmp_path)
    try:
        before_tl = deepcopy(docs.doc_payload(session, proj.id, proj.root,
                                              "timeline")["content"])
        real_save = docs.save_doc

        def save_doc_boom(s, pid, kind, content, base_version, author="local", **kw):
            if kind == "profile":
                raise RuntimeError("injected profile failure")
            return real_save(s, pid, kind, content, base_version, author, **kw)

        monkeypatch.setattr(docs, "save_doc", save_doc_boom)
        with pytest.raises(ValueError, match="配置文件更新失败"):
            qa._apply(session, proj, {"location": {"sceneId": "S01"}}, "extend_scene",
                      {"sceneId": "S01", "delta": 0.5}, None,
                      qa._timeline_before(session, proj))
        monkeypatch.undo()
        now_tl = docs.doc_payload(session, proj.id, proj.root, "timeline")["content"]
        assert _hash(now_tl) == _hash(before_tl), "timeline 未被补偿回滚"
    finally:
        _cleanup(session, proj.id, proj.root)


# ---------- 4. saved 模板 materialize：锁写失败 → 半成品项目被清 ----------

def test_template_materialize_cleans_up_on_lock_failure(tmp_path: Path, monkeypatch):
    from app.api import routes as routes_mod
    from app.services import templates as tpl_svc

    session, pid, root = _make_project(tmp_path, "tpl-src")
    try:
        docs.save_doc(session, int(pid), "script", {"text": "模板句。", "title": "tpl"}, 0, "seed")
        docs.save_doc(session, pid, "timeline",
                      {"schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 1.0,
                       "frames": 24, "scenes": [{"id": "S01", "start": 0.0, "end": 1.0,
                                                 "text": "模板句。"}],
                       "events": [], "tracks": []}, 0, "seed")
        docs.save_doc(session, pid, "profile",
                      {"schema": docs.SCHEMAS["profile"], "width": 960, "height": 540,
                       "fps": 24, "duration": 1.0, "frames": 24}, 0, "seed")
        content = {"schema": "filmflow.project-template/1", "copy": "模板句。",
                   "profile": {"width": 960, "height": 540, "fps": 24,
                               "duration": 1.0, "frames": 24},
                   "timeline": {"fps": 24,
                                "scenes": [{"id": "S01", "text": "模板句。",
                                            "duration": 1.0}]}}
        from app.models import Template
        saved = Template(kind="project", name="boom-tpl", description="",
                         content_json=content)
        session.add(saved)
        session.commit()
        session.refresh(saved)
        before_count = len(_all_projects())

        real_lock = tpl_svc.write_lock

        def lock_boom(*a, **kw):
            raise RuntimeError("injected lock failure")

        monkeypatch.setattr(tpl_svc, "write_lock", lock_boom)

        # 直接打"项目行出现后"的补偿段（drafts/风格机制由 API 层测试覆盖）
        content_sub = json.loads(json.dumps(content))
        with pytest.raises(RuntimeError, match="injected lock failure"):
            asyncio.new_event_loop().run_until_complete(
                routes_mod._finish_saved_template_materialize(
                    session, saved, content, content_sub,
                    content["profile"], int(pid), None,
                    {"project": {"id": int(pid)}},
                    [], [], [], "boom-inst"))
        monkeypatch.undo()
        assert len(_all_projects()) == before_count, "半成品项目未清理"
        assert not (tmp_path / "boom-inst").exists() or \
            not any((tmp_path / "boom-inst").iterdir()), "半成品目录未清理"
    finally:
        _cleanup(session, int(pid), root)


def _all_projects():
    with Session(engine) as s:
        return s.exec(select(Project)).all()


# ---- QA 用最小构造（与 test_qa.py 等价） ----

def _qa_ready(tmp_path: Path):
    session, pid, root = _make_project(tmp_path, "qa-fail")
    (Path(root) / "card" / "copy.txt").write_text("一" * 40, encoding="utf-8")
    docs.save_doc(session, pid, "script", {"text": "一" * 40, "title": "t"}, 0, "seed")
    docs.save_doc(session, pid, "timeline",
                  {"schema": docs.SCHEMAS["timeline"], "fps": 24, "duration": 2.0,
                   "frames": 48, "scenes": [{"id": "S01", "start": 0.0, "end": 2.0,
                                             "text": "一" * 40}],
                   "events": [], "tracks": []}, 0, "seed")
    docs.save_doc(session, pid, "profile",
                  {"schema": docs.SCHEMAS["profile"], "width": 960, "height": 540,
                   "fps": 24, "duration": 2.0, "frames": 48}, 0, "seed")

    class _P:
        pass
    _P.id, _P.root = pid, root
    return session, _P
