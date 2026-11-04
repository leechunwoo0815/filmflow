"""缓存命中必须"文件还在"，否则退回真实执行。

实测事故（B9 复现，run 335）：产物是内容寻址存在**产出它的那个项目根**里的，
跨项目命中只登记路径不复制文件。清理验收残留时删掉 `r3-audio-v2-299`，
之后一个全新项目的 C02 命中了它的字体产物 → C03 报"变量字体缺失：先运行 C02"，
整条渲染链在本机跑不下去。删项目不该有这种跨项目副作用。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))
from app.db import engine
from app.engine.runengine import _cache_hit_is_material
from app.models import Artifact, NodeRun, Project, Run, Workflow


def _prev_node_run(tmp_path: Path, files: list[Path]) -> tuple[int, str]:
    root = tmp_path / "producer"
    root.mkdir(parents=True, exist_ok=True)
    with Session(engine) as s:
        p = Project(name="producer", root=str(root))
        s.add(p); s.commit(); s.refresh(p)
        wf = Workflow(project_id=p.id, graph_json={"nodes": [], "edges": []})
        s.add(wf); s.commit(); s.refresh(wf)
        run = Run(workflow_id=wf.id)
        s.add(run); s.commit(); s.refresh(run)
        nr = NodeRun(run_id=run.id, node_id="C02", status="succeeded")
        s.add(nr); s.commit(); s.refresh(nr)
        for i, f in enumerate(files):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x" * 16)
            s.add(Artifact(run_id=run.id, node_run_id=nr.id, node_id="C02", type="TXT",
                           path=str(f), sha256=f"{i:064x}", bytes=16, meta_json={}))
        s.commit()
        return nr.id or 0, str(root)


def test_hit_without_artifacts_stays_valid(tmp_path):
    """门/分析类节点没有产物：命中判据不该把它们误判成失效。"""
    nr_id, _root = _prev_node_run(tmp_path, [])
    with Session(engine) as s:
        assert _cache_hit_is_material(s, s.get(NodeRun, nr_id), "C02") is True


def test_hit_with_files_on_disk_stays_valid(tmp_path):
    nr_id, _root = _prev_node_run(tmp_path, [tmp_path / "producer" / "a.txt"])
    with Session(engine) as s:
        assert _cache_hit_is_material(s, s.get(NodeRun, nr_id), "C02") is True


def test_hit_pointing_at_a_deleted_project_is_rejected(tmp_path):
    nr_id, root = _prev_node_run(tmp_path, [tmp_path / "producer" / "a.txt",
                                            tmp_path / "producer" / "b.txt"])
    import shutil
    shutil.rmtree(root)          # 模拟"清理验收残留项目"
    with Session(engine) as s:
        assert _cache_hit_is_material(s, s.get(NodeRun, nr_id), "C02") is False


def test_partially_missing_artifacts_are_rejected(tmp_path):
    """少一个文件也算失效：下游（C03 读 C02 的字体）只要一个路径是空的就跑不动。"""
    nr_id, _root = _prev_node_run(tmp_path, [tmp_path / "producer" / "a.txt",
                                             tmp_path / "producer" / "b.txt"])
    (tmp_path / "producer" / "b.txt").unlink()
    with Session(engine) as s:
        assert _cache_hit_is_material(s, s.get(NodeRun, nr_id), "C02") is False
