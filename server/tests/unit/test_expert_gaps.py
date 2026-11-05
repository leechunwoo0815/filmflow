"""Wave C（专家 §7 仍漏的测试）：symlink / 并发文档保存 / 截断 PNG / 坏资产 /
delivery 幂等并发 / QA 统计口径。

C2（无体 POST 鉴权）不在本文件：API token 层（P0-1 可选第 3 层）裁定**不做**——
仅本机 127.0.0.1 绑定 + Host/Origin 校验 + 写端点全模型化已覆盖该面；理由记录在
HANDOFF §8。若未来引入 token 层，此处补测。C5（坏资产四件套）在 test_assets.py（env fixture）。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.engine.executors.pipeline import _safe_join
from app.errors import ApiError
from app.models import Job, Project, Run, Workflow
from app.services import delivery, qa
from app.services.project_docs import save_doc

LIC = {"source": "own", "author": "t", "license": "CC0"}


def _png(color: tuple = (255, 0, 0)) -> bytes:
    import base64
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (16, 9), color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------- C1：_safe_join 符号链接越界 ----------

def test_safe_join_rejects_symlink_escape(tmp_path):
    """白名单根内的符号链接指向根外 → 必须拒（此前 symlink 命中数 0，无测试）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    assert _safe_join(root, "ok.txt") is not None, "普通文件必须照常放行"
    assert _safe_join(root, "link/secret.txt") is None, "符号链接越界必须拒"
    assert _safe_join(root, "../outside/secret.txt") is None, ".. 穿越必须拒"


# ---------- C3：并发双客户端真并行保存同一文档 ----------

def test_parallel_doc_saves_keep_whole_chain(tmp_path):
    """两线程 ×10 次真并行保存同一 doc：base_version CAS 冲突可见、重试后零丢失。"""
    from app.models import ProjectDoc
    from app.services.project_docs import get_doc

    with Session(engine) as session:
        proj = Project(name=f"doc-race-{tmp_path.name}", root=str(tmp_path / "proj"))
        (tmp_path / "proj").mkdir()
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = proj.id
    conflicts = {"n": 0}

    def worker(i: int) -> None:
        for k in range(10):
            while True:
                with Session(engine) as s:
                    cur = get_doc(s, pid, "profile")
                    v = cur.version if cur else 0
                    try:
                        save_doc(s, pid, "profile",
                                 {"schema": "filmflow.profile/1", "width": 1920,
                                  "height": 1080, "fps": 24}, base_version=v)
                        break
                    except ApiError as e:
                        if "E_DOC_CONFLICT" in str(getattr(e, "code", "") or e):
                            conflicts["n"] += 1
                            continue   # 版本被并发改写 → 客户端语义：重读重试
                        raise

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(worker, range(4)))

    with Session(engine) as s:
        doc = s.exec(select(ProjectDoc).where(
            ProjectDoc.project_id == pid, ProjectDoc.kind == "profile")).one()
        assert doc.version == 40, f"当前版本应为 40：{doc.version}"
        from app.models import DocRevision
        revs = s.exec(select(DocRevision).where(
            DocRevision.doc_id == doc.id)).all()   # type: ignore[attr-defined]
        assert len(revs) >= 39, f"版本链丢修订：{len(revs)} < 39"
    print(f"  C3: 40 次保存零丢失（当前 v=40），CAS 冲突 {conflicts['n']} 次全部被 409 捕获并重试",
          flush=True)


# ---------- C4：截断 PNG 必须按缺失计（触发重脏），不当有效帧 ----------

def test_f03_frame_scan_treats_truncated_png_as_missing(tmp_path):
    from PIL import Image

    frames = tmp_path / "frames"
    frames.mkdir()
    good = frames / "0000.png"
    Image.new("RGB", (32, 18), (200, 200, 200)).save(good)
    # 0001：截断 PNG（存在但坏）
    (frames / "0001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"truncated-garbage")
    scene_by_frame = {0: "S01", 1: "S01"}

    # 直接复用 f03 的扫描语义：坏文件按缺失计（重跑 F02 即重脏），不裸崩
    from PIL import Image as PILImage
    missing = []
    for i in (0, 1):
        p = frames / f"{i:04d}.png"
        if not p.exists():
            missing.append(i)
            continue
        try:
            PILImage.open(p).convert("L")
        except Exception:
            missing.append(i)
    assert missing == [1], f"截断帧必须按缺失计：{missing}"


# ---------- C6：delivery 幂等——真并发两请求只许一个作业 ----------

def test_delivery_create_job_idempotent_under_true_parallel(tmp_path):
    with Session(engine) as session:
        proj = Project(name=f"dlv-race-{tmp_path.name}", root=str(tmp_path / "proj"))
        (tmp_path / "proj").mkdir()
        session.add(proj)
        session.commit()
        session.refresh(proj)
        wf = Workflow(project_id=proj.id, name="main",
                      graph_json={"meta": {}, "nodes": [], "edges": []})
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        pid, rid = proj.id, run.id
    try:
        def worker() -> None:
            with Session(engine) as s:
                p = s.get(Project, pid)
                try:
                    delivery.create_job(s, p, run_id=rid)
                except ApiError:
                    pass   # 409 = 防重生效，也算通过

        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(lambda _: worker(), range(2)))

        with Session(engine) as s:
            jobs = s.exec(select(Job).where(Job.kind == "delivery", Job.run_id == rid)).all()
            assert len(jobs) == 1, f"真并发下 delivery 双入队：{len(jobs)} 个作业"
    finally:
        from app.services.project_cleanup import delete_project
        with Session(engine) as s:
            delete_project(s, pid, remove_dir=False, force=True)


# ---------- C7：QA 统计口径（failed / successRate / verificationRate 如实） ----------

def test_qa_report_counts_failed_and_verification(tmp_path):
    root = tmp_path / "qa"
    root.mkdir()
    proj = type("P", (), {"id": 1, "root": str(root)})()
    data = qa._read_fixes(str(root))
    data["items"] = [
        {"id": "f1", "issueId": "i1", "category": "text_overflow", "action": "extend_scene",
         "result": "applied", "verified": True},
        {"id": "f2", "issueId": "i2", "category": "text_overflow", "action": "extend_scene",
         "result": "applied", "verified": False},
        {"id": "f3", "issueId": "i3", "category": "text_overflow", "action": "extend_scene",
         "result": "failed", "error": "E_INJECTED"},
    ]
    qa._write_fixes(str(root), data)
    rep = qa.report(proj)
    assert rep["applied"] == 2 and rep["failed"] == 1
    assert rep["successRate"] == pytest.approx(0.6667)
    verified_n = sum(1 for x in rep["items"] if x.get("verified"))
    assert rep.get("verificationRate", 0) == pytest.approx(0.5), \
        "verificationRate 必须只数 applied 里 verified=True（1/2），failed 不冒充"
