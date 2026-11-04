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
    """P1-06 后统一走级联删除服务（foreign_keys=ON 下手工顺序会踩 FK）。"""
    from sqlmodel import Session

    from app.db import engine
    from app.services.project_cleanup import delete_project

    with Session(engine) as s:
        delete_project(s, pid, remove_dir=False)
    shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def throwaway(client, name: str, copy_text: str):
    """建一个临时项目，退出时删光它的库行、资产与目录。"""
    proj = create(client, name, copy_text)
    try:
        yield proj
    finally:
        destroy(client, proj["id"], proj["root"])


# ---------- 演示项目污染闸门（判官 P1-9 / §六 #9） ----------

DEMO_PROJECTS = {202: "r3-demo-20261103", 174: "r2_5-delivery40", 188: "r3-camera",
                 211: "r3-audio-v2", 215: "r2_5-delivery", 216: "golden-5s",
                 223: "golden-5s", 227: "FR37 模板演示"}


def require_scratch_project(client, argv_name: str, argv: list[str]) -> int:
    """验收脚本只允许跑在 `--project <id>` 指定的**非演示**项目上。

    判官实测：`e2e_takes.py`/`e2e_audio_v2.py` 写脏了演示 188/211 的时间轴版本链，
    而报告仍写"演示数据零污染"。默认拒绝比事后报警有用——没有显式给一个 scratch 项目，
    脚本就不该跑起来。
    """
    from app.services.project_cleanup import is_protected

    pid: int | None = None
    for i, a in enumerate(argv):
        if a == "--project" and i + 1 < len(argv):
            pid = int(argv[i + 1])
        elif a.startswith("--project="):
            pid = int(a.split("=", 1)[1])
    if pid is None:
        raise SystemExit(
            f"用法：{argv_name} --project <scratch 项目 id>\n"
            f"    这些脚本会改文档/建模板，不允许再打在演示项目上（判官 P1-9）。\n"
            f"    先自建一个：python scripts/_acceptance.py --create {argv_name.replace('.py', '')}"
            f"   （跑完用 DELETE /projects/<id>?confirm=true 清掉）")
    rows = client.get("/projects", params={"include_archived": "true"}).json().get("items", [])
    hit = next((x for x in rows if int(x.get("id") or -1) == pid), None)
    if hit is None:
        raise SystemExit(f"项目 {pid} 不在 /projects 列表里（不存在或已归档），拒绝继续")
    name = hit.get("name") or ""
    if pid in DEMO_PROJECTS or is_protected(name):
        raise SystemExit(f"拒绝在演示/保护项目上跑（{pid} / {name}）——用 --project 指向自建项目")
    return pid


if __name__ == "__main__":
    # 便捷入口：python scripts/_acceptance.py --create <name> [文案行数]
    # 打印一个自建 scratch 项目 id，供各 e2e/verify 脚本用 --project 指过去。
    import httpx

    args = sys.argv[1:]
    name = args[args.index("--create") + 1] if "--create" in args else "scratch"
    copy = "第一句要读完其实不容易。第二句同样需要更多时间才能读完。"
    with httpx.Client(base_url="http://127.0.0.1:7860/api", timeout=120, trust_env=False) as client:
        proj = create(client, name, copy)
    print(f"project={proj['id']} root={proj['root']} run={proj['run_id']}")
    print(f"用完请清掉：curl -X DELETE 'http://127.0.0.1:7860/api/projects/{proj['id']}?confirm=true'")
