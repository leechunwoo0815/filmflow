"""验收脚手架：脚本自建自删项目，不再改写/删除演示数据（专家审查 P1-19）。

用法：
    from _acceptance import throwaway
    with throwaway(client, "qa-verify", "第一句。\\n第二句。") as proj:
        pid = proj["id"]
"""
from __future__ import annotations

import contextlib
import shutil
import sys
import uuid
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

ACCEPT_ROOT = Path.home() / "cc-projects" / "ai-v" / "filmflow-projects" / ".acceptance"


def create(client, name: str, copy_text: str) -> dict:
    root = ACCEPT_ROOT / f"{name}-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True, exist_ok=True)
    (root / "card" / "copy.txt").write_text(copy_text, encoding="utf-8")
    body = client.post("/projects", json={"name": name, "root": str(root)}).json()
    return {"id": int(body["project"]["id"]), "root": root,
            "workflow_id": body.get("workflow_id"), "run_id": body.get("run_id")}


def destroy(client, pid: int, root: Path) -> None:
    for asset in (client.get("/assets", params={"scope": "project", "projectId": pid})
                  .json().get("items") or []):
        client.delete(f"/assets/{asset['id']}", params={"force": "true"})
    from sqlalchemy import delete as sa_delete
    from sqlmodel import Session, SQLModel, select

    from app.db import engine
    from app.models import Project, Run, Workflow

    with Session(engine) as s:
        wf_ids = [w.id for w in s.exec(select(Workflow).where(
            Workflow.project_id == pid)).all()]
        run_ids = [r.id for r in s.exec(select(Run).where(Run.workflow_id.in_(wf_ids))).all()] if wf_ids else []
        for table in SQLModel.metadata.sorted_tables:
            cols = {c.name for c in table.columns}
            if "project_id" in cols:
                s.exec(sa_delete(table).where(table.c.project_id == pid))
            elif "run_id" in cols and run_ids:
                s.exec(sa_delete(table).where(table.c.run_id.in_(run_ids)))
        p = s.get(Project, pid)
        if p:
            s.delete(p)
        s.commit()
    shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def throwaway(client, name: str, copy_text: str):
    """建一个临时项目，退出时删光它的库行、资产与目录。"""
    proj = create(client, name, copy_text)
    try:
        yield proj
    finally:
        destroy(client, proj["id"], proj["root"])
