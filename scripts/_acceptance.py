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
import time
import uuid
from pathlib import Path
from typing import Self

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


# 需要被验收脚本主动取消的 Run 状态（闸门另有判定，见 _settle）
# blocked 也要取消：停在门上的 Run 会把作业 parked 成 retry_wait，心跳 120s 内
# 删除闸门判它"在飞"，不取消就得干等两分钟（实测踩过：验收脚本因此超时留下残留项目）。
BUSY_RUN = ("running", "queued", "paused", "needs_changes", "blocked")


def _settle(client, pid: int, timeout: float = 150.0) -> None:
    """取消本项目所有非终态 Run，并等到删除闸门不再报"在飞"。

    闸门看的是**作业**（心跳/started_at 120s 内的 kind=run 作业），不是 Run 状态；
    取消是异步的，所以必须轮询闸门自己的判定，而不是猜 Run 状态。
    """
    from app.db import engine
    from app.services.project_cleanup import plan_delete
    from sqlmodel import Session

    for r in (client.get(f"/projects/{pid}/runs").json().get("items") or []):
        if (r.get("status") or "") in BUSY_RUN:
            client.post(f"/runs/{r['id']}/cancel", json={})
    inflight: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        with Session(engine) as s:
            inflight = [b for b in plan_delete(s, pid)["blockers"] if "在飞" in b]
        if not inflight:
            return
        time.sleep(1.5)
    raise SystemExit(f"项目 {pid} 的作业在 {timeout:.0f}s 内没停（{inflight}）——拒绝强删")


def destroy(client, pid: int, root: Path) -> None:
    """P1-06 后统一走级联删除服务（foreign_keys=ON 下手工顺序会踩 FK）。

    同时回收向导留下的 `draft` 行：materialize 不删草稿，验收脚本若不收，
    每跑一次就在库里留一枚指向已删目录的僵尸草稿（实测一晚积了 6 条）。
    """
    from app.db import engine
    from app.models import Draft, Project
    from app.services.project_cleanup import delete_project
    from sqlmodel import Session, select

    _settle(client, pid)
    with Session(engine) as s:
        # confirm_name 用库行里的真名原样回显：自建项目撞上保护名单（如 golden_run 建
        # 的 golden-5s）时删除是**正确**被拦的，回显真名不算削弱保护——其它调用者仍必须
        # 显式给出 confirm_name（2026-11-05 golden_run 自删尾巴实测炸过一次 409）。
        proj = s.get(Project, pid)
        delete_project(s, pid, remove_dir=False,
                       confirm_name=(proj.name if proj else ""))
        stale = [d for d in s.exec(select(Draft)).all()
                 if str((d.payload_json or {}).get("root") or "").startswith(str(root))]
        for d in stale:
            s.delete(d)
        if stale:
            s.commit()
        print(f"  回收向导草稿 {len(stale)} 条", flush=True)
    shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def throwaway(client, name: str, copy_text: str):
    """建一个临时项目，退出时删光它的库行、资产与目录。"""
    proj = create(client, name, copy_text)
    try:
        yield proj
    finally:
        destroy(client, proj["id"], proj["root"])


class Cleanup:
    """登记本脚本建的项目，退出时（**含异常**）统一删掉；`--keep` 保留现场。

    为什么要有它：10 个 verify/golden 脚本此前建完不删，异常退出更是连成功路径的清理都跳过。
    实测一晚下来生产库里堆了 14 个残留项目、约 800MB（golden-5s ×6、r2-profiles ×4、
    r2-verify-5s ×2、r3-audio-v2 ×1、审计遗留 ×1），其中 541MB 的是一个 golden-5s。

    用法：
        clean = Cleanup(c, keep=args.keep)
        with clean:
            pid = clean.track(body["project"]["id"], root)
    """

    def __init__(self, client, keep: bool = False):
        self.client = client
        self.keep = keep
        self.tracked: list[tuple[int, Path]] = []

    def track(self, pid: int, root) -> int:
        self.tracked.append((int(pid), Path(root)))
        return int(pid)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.keep:
            for pid, root in self.tracked:
                print(f"  --keep：保留项目 {pid}（{root}）", flush=True)
            return False
        for pid, root in reversed(self.tracked):
            try:
                destroy(self.client, pid, root)
            except SystemExit as e:                     # _settle 等不到作业停时会 SystemExit
                print(f"  清理未完成 project={pid}: {e}", flush=True)
            except Exception as e:  # noqa: BLE001 —— 清理失败绝不能盖掉原始异常
                print(f"  清理失败 project={pid}: {type(e).__name__}: {e}", flush=True)
        self.tracked.clear()
        return False


def add_keep_flag(parser) -> None:
    """给验收脚本统一加 --keep（默认跑完自删）。"""
    parser.add_argument("--keep", action="store_true",
                        help="保留本脚本建的临时项目（默认跑完/失败都自删）")


# ---------- 演示项目污染闸门（判官 P1-9 / §六 #9） ----------

# 现网 11 个演示/参考项目（与 HANDOFF §7.4 逐个同步；2026-11-06 A5 复核）。
# 216/223 曾在列——golden_run 验证残留、2026-11-05 §7-3 已删，id 名单只留活项目。
# 静态扫描只匹配 \d{2,4} 的三种写法，id 1/4（单位数）不会被误报；运行时闸门按真 id 全护。
DEMO_PROJECTS = {1: "rumor-39s", 4: "trace", 115: "rumor-clean-20261102",
                 151: "r2_5-audio", 174: "r2_5-delivery40", 188: "r3-camera",
                 202: "r3-demo-20261103", 206: "r2_5-delivery", 211: "r3-audio-v2",
                 215: "r2_5-delivery", 227: "FR37 模板演示"}

# 按设计可以碰非自建项目的脚本（新增豁免必须写理由，这里是唯一登记处）：
#   cleanup_projects          —— 审计残留清理工具本身
#   verify_rumor_regression   —— rumor-39s 参考片回归（46/46 基线就在它身上）
#   drive_run                 —— 运维驱动器，Run/项目由操作者显式指定
#   probe_profile_ssim_offset —— 只读探针
#   smoke_m1                  —— 导入 rumor-39s 证明 46 节点画布；参考片不是演示项目
POLLUTION_EXEMPT = {"cleanup_projects.py", "verify_rumor_regression.py", "drive_run.py",
                    "probe_profile_ssim_offset.py", "smoke_m1.py",
                    # B5：资产孤儿清理工具（删文件/死行，不建项目不写演示）
                    "cleanup_assets.py",
                    # B7：UI 驱动器——自建入口是向导 UI 本身（5 步 materialize 走界面），
                    # 项目在收尾自删（created_pid → DELETE），不走 API 故 SELFBUILT_TOKENS 看不见
                    "e2e_ui.py"}

# 自建入口：命中任意一个就说明项目/状态是本脚本造的
SELFBUILT_TOKENS = ("require_scratch_project", "scratch_project", "throwaway(",
                    "build_take_state", "build_review_source", "build_template_source",
                    "build_golden_project", "from-template", '"/drafts"', '"/projects"')
_WRITER_TOKENS = ('"POST"', '"PUT"', '"PATCH"', '"DELETE"',
                  ".post(", ".put(", ".patch(", ".delete(")


def audit_script_pollution(scripts_dir) -> tuple[list[str], list[str]]:
    """静态扫描验收脚本：返回 (写了演示项目的行, 会写状态却没有自建入口的文件)。

    `verify_p1_governance.py` 的第 14 项和单测共用这一份判据，避免两边漂移。
    """
    import re
    from pathlib import Path

    scripts_dir = Path(scripts_dir)
    demo_ids = set(DEMO_PROJECTS)
    demo_lines: list[str] = []
    unguarded: list[str] = []
    skip = set(POLLUTION_EXEMPT) | {"verify_p1_governance.py", "_acceptance.py", "_scratch_state.py"}
    for py in sorted(scripts_dir.glob("*.py")):
        if py.name.startswith("_") or py.name in skip:
            continue
        lines = py.read_text(encoding="utf-8").splitlines()
        body = "\n".join(lines)
        for n, line in enumerate(lines, 1):
            code = line.split("#", 1)[0]
            ids = {int(x) for x in re.findall(r"(?:PID|SOURCE|PROJECT_ID|PROJ) = '?(\d{2,4})'?", code)}
            ids |= {int(x) for x in re.findall(r"/projects/(\d{2,4})", code)}
            ids |= {int(x) for x in re.findall(r"[?&]project=(\d{2,4})", code)}
            if ids & demo_ids:
                names = "/".join(sorted(DEMO_PROJECTS[i] for i in ids & demo_ids))
                demo_lines.append(f"{py.name}:{n}: {code.strip()}（{names}）")
        if any(tok in body for tok in _WRITER_TOKENS) \
                and not any(tok in body for tok in SELFBUILT_TOKENS):
            unguarded.append(py.name)
    return demo_lines, unguarded


# 建项目但按设计不自删的脚本（新增豁免必须写理由，这里是唯一登记处）：
#   cleanup_projects.py         —— 清理工具本身，只按 --id 删，不建项目
#   smoke_m1.py                 —— 导入既有 rumor-39s 参考片，不新建项目目录
#   verify_rumor_regression.py  —— 同上，46/46 基线就在 rumor 上
#   drive_run.py                —— 运维驱动器，Run/项目由操作者显式指定
#   probe_profile_ssim_offset.py —— 只读探针
#   e2e_ui.py / e2e_onboarding.py / e2e_error_visibility.py —— 走 UI，只读既有演示页面
TEARDOWN_EXEMPT = {"cleanup_projects.py", "smoke_m1.py", "verify_rumor_regression.py",
                   "drive_run.py", "probe_profile_ssim_offset.py", "e2e_ui.py",
                   "e2e_onboarding.py", "e2e_error_visibility.py"}

_CREATOR_TOKENS = ('"/projects/import"', '"/projects"', "create_project(",
                   '"/drafts"', "build_golden_project(")
_TEARDOWN_TOKENS = ("Cleanup(", "throwaway(", "scratch_project(", "destroy(",
                    "destroy_project(", "build_take_state(", "build_review_source(",
                    "build_template_source(")
# 或者显式对项目发 DELETE（e2e_timeline_100 走的是这条）
_TEARDOWN_RE = (r"\.delete\(\s*f?[\"']/projects/", r"[\"']DELETE[\"'],\s*f?[\"']/projects/")


# 已知"建项目但不自删"的存量脚本：改造一个就从这里删一个，**新脚本不许进这个名单**。
# 实测代价：一晚积了 14 个残留项目 / 约 800MB（其中一个 golden-5s 541MB）。
# 2026-11-05 §7-3：9 个存量全部接上 Cleanup 自删，棘轮归零——名单保留空集是为了
# 让"再次出现 offender"时报错而不是静默通过。
TEARDOWN_PENDING: set[str] = set()


def audit_script_teardown(scripts_dir) -> list[str]:
    """建了项目却没有自删入口的脚本——生产库里残留项目的唯一来源。

    与 `audit_script_pollution` 共用一份判据风格：静态扫描，`verify_p1_governance.py`
    的第 16 项和单测都调它，避免两边漂移。
    """
    import re
    from pathlib import Path

    scripts_dir = Path(scripts_dir)
    offenders: list[str] = []
    skip = set(TEARDOWN_EXEMPT) | {"verify_p1_governance.py", "_acceptance.py",
                                   "_scratch_state.py"}
    for py in sorted(scripts_dir.glob("*.py")):
        if py.name.startswith("_") or py.name in skip:
            continue
        body = py.read_text(encoding="utf-8")
        if not any(tok in body for tok in _CREATOR_TOKENS):
            continue
        if any(tok in body for tok in _TEARDOWN_TOKENS):
            continue
        if any(re.search(pat, body) for pat in _TEARDOWN_RE):
            continue
        offenders.append(py.name)
    return offenders


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
