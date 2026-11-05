"""P1 基础治理：SQLite pragma、workspace roots 环境解析、A05 自动批准守卫、交付门禁。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.config import Settings, settings
from app.db import engine
from app.engine import runengine
from app.services import delivery
from app.services import project_docs as docs


def test_workspace_roots_accept_plain_and_json(monkeypatch):
    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", "/tmp/filmflow-one")
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/filmflow-one")]

    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", '["/tmp/a", "/tmp/b"]')
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/a"), Path("/tmp/b")]

    monkeypatch.setenv("FILMFLOW_WORKSPACE_ROOTS", "/tmp/a,/tmp/b")
    assert Settings(_env_file=None).workspace_roots == [Path("/tmp/a"), Path("/tmp/b")]


def test_sqlite_pragmas_are_configured():
    with engine.connect() as conn:
        assert str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
        assert int(conn.exec_driver_sql("PRAGMA synchronous").scalar()) == 1
        # P1-06 收尾：级联删除就位后外键强制开启
        assert int(conn.exec_driver_sql("PRAGMA foreign_keys").scalar()) == 1


def test_a05_auto_approve_requires_import_or_style_decision():
    # 没有 imported/style_decision 时，必须在访问 session 前返回；session=None 即验证守卫。
    runengine._auto_approve_a05(
        None, SimpleNamespace(id=1), SimpleNamespace(graph_json={"meta": {}}), {}, "/tmp")


# ---------- 交付门禁（F-DEL-1/2：快照文件硬校验 + script 一并比对） ----------

SNAP_SCHEMA = "filmflow.snapshot/1"


def _write_snapshot(tmp_path: Path, doc_map: dict, *, run_id: int = 1,
                   profile: dict | None = None,
                   render_profiles: dict | None = None,
                   caps: list | None = None, params: dict | None = None) -> dict:
    """写一份**生产形态**的快照：run_id + doc_snapshot_sha 必须自洽，否则门禁会先拦 sha。"""
    d = tmp_path / "runs" / str(run_id) / "docs"
    d.mkdir(parents=True, exist_ok=True)
    body = {"schema": SNAP_SCHEMA, "run_id": run_id, "imported": False,
            "profile": profile or {}, "render_profiles": render_profiles or {}, "docs": doc_map}
    if caps is not None:
        body["caps"] = caps                     # 2.14.0 起新快照才有；历史快照缺省即不比对
    if params is not None:
        body["params"] = params
    body["doc_snapshot_sha"] = docs.content_hash({
        "docs": doc_map, "profile": body["profile"],
        "render_profiles": body["render_profiles"], "imported": False})
    (d / "snapshot.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return body


def _doc(content: dict) -> dict:
    return {"version": 1, "hash": "x", "content": content}


class _FakeDoc:
    def __init__(self, content):
        self.content_json = content


def _seed_current(monkeypatch, current: dict[str, dict]):
    def get_doc(_session, _pid, kind):
        return _FakeDoc(current[kind]) if kind in current else None
    monkeypatch.setattr(delivery.docs_svc, "get_doc", get_doc)


def test_delivery_rejects_missing_snapshot_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(delivery.docs_svc, "get_doc", lambda *a: None)
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*快照"):
        delivery._ensure_run_documents_match(
            None, SimpleNamespace(id=1), tmp_path, 1)  # 没写快照文件


def test_delivery_rejects_broken_or_wrong_schema_snapshot(monkeypatch, tmp_path: Path):
    d = tmp_path / "runs" / "1" / "docs"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)
    (d / "snapshot.json").write_text(json.dumps({"schema": "filmflow.snapshot/9"}),
                                     encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_snapshot_without_timeline(monkeypatch, tmp_path: Path):
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script)})
    _seed_current(monkeypatch, {"script": script})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*timeline"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_timeline_drift(monkeypatch, tmp_path: Path):
    tl_snap = {"duration": 5.0}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(tl_snap)})
    _seed_current(monkeypatch, {"script": script, "timeline": {"duration": 5.5}})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_script_drift(monkeypatch, tmp_path: Path):
    """F-DEL-2：Run 后只改 script（不改 timeline）也必须拦——9:16/SRT/封面都用得到。"""
    tl = {"duration": 5.0}
    script_snap = {"title": "旧标题", "sentences": [{"text": "旧句子"}]}
    _write_snapshot(tmp_path, {"script": _doc(script_snap), "timeline": _doc(tl)})
    _seed_current(monkeypatch, {"script": {"title": "新标题", "sentences": [{"text": "新句子"}]},
                                "timeline": tl})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*script"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_rejects_current_profile_drift(monkeypatch, tmp_path: Path):
    tl = {"duration": 5.0}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(tl),
                               "profile": _doc({"fps": 24})})
    _seed_current(monkeypatch, {"script": script, "timeline": tl, "profile": {"fps": 30}})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*profile"):
        delivery._ensure_run_documents_match(None, SimpleNamespace(id=1), tmp_path, 1)


def test_delivery_accepts_matching_run_snapshot(monkeypatch, tmp_path: Path):
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)})
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    snap = delivery._ensure_run_documents_match(
        None, SimpleNamespace(id=1), tmp_path, 1)
    assert snap["schema"] == SNAP_SCHEMA


def test_delivery_rejects_caps_shrunk_after_snapshot(monkeypatch, tmp_path: Path):
    """P1-13 残余：caps 只许经审批增长；快照里的 caps 在当前 Run 上缺了就是被改写过。"""
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                    caps=["read", "write_plan", "logic_check", "approve_T01"])
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*caps"):
        delivery._ensure_run_documents_match(
            None, SimpleNamespace(id=1, caps_json=["read", "write_plan"]), tmp_path, 1)


def test_delivery_caps_superset_passes(monkeypatch, tmp_path: Path):
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                    caps=["read"])
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    delivery._ensure_run_documents_match(
        None, SimpleNamespace(id=1, caps_json=["read", "write_plan", "approve_T01"]),
        tmp_path, 1)


def test_delivery_rejects_params_drift(monkeypatch, tmp_path: Path):
    """P1-13 残余：params 非空才比对（现网全空，不假装覆盖）；非空漂移必须拦。"""
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                    params={"variant": "v1"})
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*params"):
        delivery._ensure_run_documents_match(
            None, SimpleNamespace(id=1, caps_json=[], params_snapshot={"variant": "v2"}),
            tmp_path, 1)


def test_delivery_empty_params_snapshot_skips_and_match_passes(monkeypatch, tmp_path: Path):
    """A6：把「空即跳过」钉成测试——**快照侧** params 为空（生产实况：POST /runs
    的 payload.params 无人传 → 快照无 params）时完全不比对，run 侧带什么都放行；
    快照侧非空且 run 一致时放行；非空漂移由 test_delivery_rejects_params_drift 钉死。"""
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    # 快照无 params（生产实况）：run 侧就算带值也跳过（无从比对就不假装比对）
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)})
    delivery._ensure_run_documents_match(
        None, SimpleNamespace(id=1, caps_json=[], params_snapshot={"anything": 1}), tmp_path, 1)
    # 快照有 params 且 run 一致：放行
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                    params={"variant": "v1"})
    delivery._ensure_run_documents_match(
        None, SimpleNamespace(id=1, caps_json=[], params_snapshot={"variant": "v1"}),
        tmp_path, 1)


def test_delivery_rejects_final_crf_drift(monkeypatch, tmp_path: Path):
    """P1-13 残余：final 档位从只比 w/h/fps 扩到全字段（crf/preset 直接进 master 编码）。"""
    timeline = {"duration": 5.0, "scenes": [{"id": "S01"}]}
    script = {"title": "t", "sentences": [{"text": "a"}]}
    snap_final = {"width": 1920, "height": 1080, "fps": 24, "crf": 17, "preset": "medium"}
    _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                    profile={"width": 1920, "height": 1080, "fps": 24},
                    render_profiles={"final": snap_final})
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    # render.profile.json 只能覆盖 crf/preset：把 crf 改成 19，resolve() 就会漂
    (tmp_path / "render.profile.json").write_text(
        json.dumps({"schema": "filmflow.render-profile/1", "final": {"crf": 19}}),
        encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*crf"):
        delivery._ensure_run_documents_match(
            None, SimpleNamespace(id=1, caps_json=[]), tmp_path, 1)


def test_delivery_title_prefers_snapshot_script(monkeypatch):
    """F-DEL-3：封面标题取快照 script；当前文档改成新标题也不影响本次交付。"""
    snap = {"docs": {"script": {"content": {"title": "快照标题",
                                            "sentences": [{"text": "旧句"}]}}}}

    class _Proj:
        id = 1
        root = "/tmp/whatever"

    def _boom(*_a):
        raise AssertionError("不应读取当前 script")
    monkeypatch.setattr(delivery.docs_svc, "doc_payload", _boom)
    assert delivery._title(None, _Proj(), snap) == "快照标题"


# ---------- P2-04 / P2-07：帧原子写与版本链上限 ----------

def test_frameserver_writes_frames_atomically(tmp_path: Path):
    """P2-04：/frame 落盘必须 tmp+replace——中途 kill 不留半张帧给 F03。"""
    import base64 as b64
    import socket
    import urllib.request

    from app.engine.executors.pipeline import FrameServer

    root = tmp_path / "proj"
    (root / "out").mkdir(parents=True)
    png = b64.b64encode(b"\x89PNG\r\n\x1a\ntest").decode()
    # A8（2026-11-06）：帧端口自 2.14.0 起可配置——绑空闲端口，测试不再依赖 8787
    # 是否被 dev 占用（旧实现写死 8787 + skip 门控，dev 在跑就丢覆盖率）；空闲端口
    # 也保证 start() 不会走 reuse 探针静默复用别家 root。
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    srv = FrameServer(str(root))
    srv.port = port
    srv.start()
    try:
        body = ("data:image/png;base64," + png).encode()
        # P2-32：帧上传在数据面，必须带本进程 token（同进程测试直接读 settings）
        from app.config import settings as _settings
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/frame?i=7&tok={_settings.frame_token}",
            data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
        f = root / "out" / "frames" / "0007.png"
        assert f.exists() and f.read_bytes() == b"\x89PNG\r\n\x1a\ntest"
        assert not list((root / "out" / "frames").glob("*.tmp")), "不得残留 .tmp"
    finally:
        srv.stop() if hasattr(srv, "stop") else None


def test_doc_revisions_capped_at_100(tmp_path: Path):
    """P2-07：连续保存 110 次，版本链只保留最近 100 条；版本号不受影响。"""
    from app.models import DocRevision
    from app.services.project_cleanup import delete_project

    root = tmp_path / "rev-cap"
    (root / "card").mkdir(parents=True)
    (root / "card" / "copy.txt").write_text("版本裁剪。", encoding="utf-8")
    with Session(engine) as session:
        from app.models import Project
        p = Project(name="rev-cap", root=str(root))
        session.add(p)
        session.commit()
        session.refresh(p)
        pid = p.id
        try:
            for i in range(110):
                docs.save_doc(session, pid, "script",
                              {"text": f"第 {i} 版内容。", "title": "t"}, i, "cap-test")
            doc = docs.get_doc(session, pid, "script")
            assert doc is not None and doc.version == 110
            n = len(session.exec(select(DocRevision).where(
                DocRevision.doc_id == doc.id)).all())
            assert n == 100, n
            # 最新版本仍在链上
            tops = docs.list_versions(session, doc)
            assert tops[0]["version"] == 110
        finally:
            session.rollback()
            delete_project(session, pid, remove_dir=False)
    import shutil
    shutil.rmtree(root, ignore_errors=True)


def test_dir_policy_blocks_workspace_root_and_git():
    from app.config import settings
    from app.services.project_cleanup import dir_policy, is_protected

    ws = Path(settings.workspace_roots[0]).resolve()
    assert dir_policy(ws)[0] is False
    assert dir_policy(Path(__file__).resolve().parents[3])[0] is False  # 本仓库（含 .git）
    ok, _ = dir_policy(ws / "filmflow-projects" / "any-proj")
    assert ok is True
    assert is_protected("rumor-39s") and is_protected("rumor-clean-20261102")
    assert is_protected("FR37 模板演示") and not is_protected("一次性验证项目")
    # 验收项目与演示项目同名前缀时不能被误锁（精确匹配演示名，只有 rumor 按前缀）
    assert not is_protected("r2_5-delivery-277") and not is_protected("golden-5s-246")
    assert is_protected("r2_5-delivery") and is_protected("rumor-clean-20261102")


def test_delete_refuses_while_job_running_and_keeps_rows(tmp_path: Path):
    """在飞作业存在时必须拒绝删除，且不碰任何库行（判官 P0-1 的"先校验后动数据"）。"""
    from app.models import Job, Project, Run, Workflow
    from app.services.project_cleanup import delete_project, plan_delete

    root = tmp_path / "inflight-proj"
    root.mkdir()
    with Session(engine) as session:
        p = Project(name="inflight-proj", root=str(root))
        session.add(p)
        session.commit()
        session.refresh(p)
        wf = Workflow(project_id=p.id, name="main", graph_json={"meta": {}})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="running")
        job = Job(kind="run", status="running", payload_json={"projectId": p.id}, run_id=run.id)
        session.add_all([run, job])
        session.commit()
        pid = p.id
        try:
            plan = plan_delete(session, pid)
            assert plan["inflight"], plan
            with pytest.raises(Exception) as e:
                delete_project(session, pid, remove_dir=False)
            assert "在飞" in str(e.value), str(e.value)
            assert session.get(Project, pid) is not None, "被拒后库行必须还在"
            assert session.get(Job, job.id) is not None
            # force 只可越过"在飞作业"这一条，并要留审计痕迹
            out = delete_project(session, pid, remove_dir=False, force=True)
            assert out["deleted"] == pid
            from app.models import AuditLog
            log = session.exec(select(AuditLog).where(
                AuditLog.action == "project.delete",
                AuditLog.target == str(pid),
                AuditLog.after_json["name"].as_string() == "inflight-proj")
                .order_by(AuditLog.id.desc())).first()
            assert log is not None and log.after_json.get("forcedInflight") is True
        finally:
            if session.get(Project, pid) is not None:   # 上面 force 删除已生效则无需再清
                delete_project(session, pid, remove_dir=False, force=True)
            assert session.get(Project, pid) is None


def test_dir_policy_failure_does_not_delete_rows(tmp_path: Path):
    """目录不合规时，绝不能出现"库已删、目录还在"的半死状态。"""
    from app.models import Project
    from app.services.project_cleanup import delete_project

    with Session(engine) as session:
        p = Project(name="bad-root", root=str(Path(settings.workspace_roots[0]).resolve()))
        session.add(p)
        session.commit()
        session.refresh(p)
        pid = p.id
        try:
            with pytest.raises(Exception) as e:
                delete_project(session, pid, remove_dir=True)
            assert "白名单根" in str(e.value), str(e.value)
            assert session.get(Project, pid) is not None, "校验未过时不得删库"
        finally:
            row = session.get(Project, pid)
            if row:
                session.delete(row)
                session.commit()


# ---------- 判官 #4 后半：快照与库内封印绑定 ----------

def _seed(tmp_path: Path, monkeypatch, script: dict, timeline: dict, *, run_id: int = 1) -> dict:
    body = _write_snapshot(tmp_path, {"script": _doc(script), "timeline": _doc(timeline)},
                           run_id=run_id)
    _seed_current(monkeypatch, {"script": script, "timeline": timeline})
    return body


def test_snapshot_from_other_run_is_rejected(tmp_path: Path, monkeypatch):
    script, timeline = {"title": "t", "sentences": [{"text": "a"}]}, {"duration": 5.0}
    _seed(tmp_path, monkeypatch, script, timeline)
    import shutil
    shutil.copytree(tmp_path / "runs" / "1", tmp_path / "runs" / "2")  # 整目录拷走，内容仍写着 run 1
    run = SimpleNamespace(id=2, snapshot_sha="")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*属于 run 1"):
        delivery._load_run_snapshot_file(tmp_path, 2, run=run, session=None)


def test_snapshot_with_edited_docs_fails_sha_self_check(tmp_path: Path, monkeypatch):
    """把快照里的 timeline 段落改掉、不重算 doc_snapshot_sha —— 这正是"复制旧快照绕过门禁"的形状。"""
    script, timeline = {"title": "t", "sentences": [{"text": "a"}]}, {"duration": 5.0}
    _seed(tmp_path, monkeypatch, script, timeline)
    snap_p = tmp_path / "runs" / "1" / "docs" / "snapshot.json"
    body = json.loads(snap_p.read_text(encoding="utf-8"))
    body["docs"]["timeline"]["content"] = {"duration": 9.9}
    snap_p.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*doc_snapshot_sha"):
        delivery._load_run_snapshot_file(tmp_path, 1, run=SimpleNamespace(id=1, snapshot_sha=""),
                                        session=None)


def test_snapshot_file_swapped_out_breaks_seal(tmp_path: Path, monkeypatch):
    script, timeline = {"title": "t", "sentences": [{"text": "a"}]}, {"duration": 5.0}
    _seed(tmp_path, monkeypatch, script, timeline)
    run = SimpleNamespace(id=1, snapshot_sha="0" * 64)   # 库内封印来自另一个字节序列
    with pytest.raises(RuntimeError, match="E_DELIVERY_GATE.*封印"):
        delivery._load_run_snapshot_file(tmp_path, 1, run=run, session=None)


def test_legacy_run_gets_sealed_on_first_passing_delivery_check(tmp_path: Path, monkeypatch):
    """历史 Run（sha 未记）首次通过内容校验时补封印，之后替换文件即被拦。"""
    script, timeline = {"title": "t", "sentences": [{"text": "a"}]}, {"duration": 5.0}
    from app.models import Project, Run, Workflow
    from app.services.project_cleanup import delete_project

    with Session(engine) as session:
        p = Project(name=f"seal-{tmp_path.name}", root=str(tmp_path))
        session.add(p)
        session.commit()
        session.refresh(p)
        wf = Workflow(project_id=p.id)
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id)
        session.add(run)
        session.commit()
        session.refresh(run)
        _seed(tmp_path, monkeypatch, script, timeline, run_id=run.id)   # 快照目录必须就是本 Run
        try:
            assert run.snapshot_sha == ""
            delivery._load_run_snapshot_file(tmp_path, run.id, run=run, session=session)
            session.refresh(run)
            assert run.snapshot_sha == delivery._file_sha(tmp_path / "runs" / str(run.id) / "docs" / "snapshot.json")
            snap_p = tmp_path / "runs" / str(run.id) / "docs" / "snapshot.json"
            # 整份替换：JSON 语义不变（sha 自洽那道过得去），但字节序列变了 —— 只有库内封印拦得住
            snap_p.write_text(snap_p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with pytest.raises(RuntimeError, match="封印不一致"):
                delivery._load_run_snapshot_file(tmp_path, run.id, run=run, session=session)
        finally:
            delete_project(session, p.id, remove_dir=False, force=True)
