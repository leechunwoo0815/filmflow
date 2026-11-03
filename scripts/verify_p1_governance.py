"""P1 治理复核：一条命令复现本轮关闭的门禁与语义（自建自删，不改演示数据）。

用法：
    uv run --project server python scripts/verify_p1_governance.py
覆盖：安全边界 / 转场单实现 / 缓存键外部输入 / 资产许可门禁与引用面 / 交付一致性门禁 /
rights 真实化 / QA 多步 LIFO 撤销 / 迁移登记处 / 请求模型 422。
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import httpx
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / "server"))

from _acceptance import throwaway  # noqa: E402

BASE = "http://127.0.0.1:7860/api"
HEADERS = {"Origin": "http://127.0.0.1:3000"}
COPY = "第一句话要读完其实不容易。第二句话同样需要更多时间才能读完。"


def png(color) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (16, 9), color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ok(step: str, detail: str = "") -> None:
    print(f"✓ {step}{('：' + detail) if detail else ''}", flush=True)


def check_security(c: httpx.Client) -> None:
    raw = httpx.Client(base_url=BASE, timeout=10, trust_env=False)
    bad_host = raw.get("/projects", headers={"Host": "attacker.example"})
    bad_origin = raw.post("/drafts", json={"name": "x", "step": 1},
                          headers={"Origin": "http://evil.example"})
    local = c.get("/health")
    raw.close()
    assert bad_host.status_code == 400, bad_host.status_code
    assert bad_origin.status_code == 403, bad_origin.status_code
    assert local.status_code == 200
    ok("1 安全边界", "错误 Host 400 / 跨源写 403 / 本机 200")


def check_transitions() -> None:
    from app.engine.scene import transitions as tr
    from app.services import preview as pv
    assert pv._transition_type is tr.transition_type, "preview 仍在用自己的转场映射"
    mapped = {label: tr.transition_type(label) for label in tr.TRANSITIONS}
    mapped.update({e: tr.transition_type(e) for e in tr.TRANSITIONS})
    assert len(set(mapped.values())) == len(tr.TRANSITIONS), mapped
    assert tr.transition_type("淡入淡出") == tr.transition_type("fade")
    ok("2 转场单实现", f"{len(tr.TRANSITIONS)} 类中英文标签同源、无分叉")


def check_cache_inputs() -> None:
    from app.engine import runengine as re_mod
    from app.engine.cachekey import EXECUTOR_VERSION
    assert EXECUTOR_VERSION == "2.9.3", EXECUTOR_VERSION
    assert {"A01", "A03", "F01", "G01"} <= set(re_mod._EXTERNAL_FILES), sorted(re_mod._EXTERNAL_FILES)
    probe = re_mod._external_input_hashes("/nonexistent-ff-root", "A01")
    assert list(probe) == ["_external:A01"] and probe["_external:A01"], probe
    assert {"G02", "G04"} <= set(re_mod._PROJECT_INPUTS), sorted(re_mod._PROJECT_INPUTS)
    assert "C01" in re_mod.ENGINE_NODES
    ok("3 缓存键", f"EXECUTOR={EXECUTOR_VERSION}；A01/A03/F01/G01 外部指纹入键、"
                  "G02/G04 项目输入入键、C01 引擎包入键")


def check_license_and_usage(c: httpx.Client, pid: int) -> int:
    no_lic = c.post("/assets", json={"scope": "project", "projectId": pid,
                                     "filename": "a.png", "data": png((1, 2, 3))})
    expired = c.post("/assets", json={"scope": "project", "projectId": pid, "filename": "b.png",
                                      "data": png((1, 2, 4)),
                                      "license": {"source": "买断", "type": "商业授权",
                                                  "expires": "2020-01-01"}})
    good = c.post("/assets", json={"scope": "project", "projectId": pid, "filename": "c.png",
                                   "data": png((1, 2, 5)),
                                   "license": {"source": "自制", "type": "CC0"}})
    assert no_lic.status_code == 400 and no_lic.json()["detail"]["code"] == "E_ASSET_LICENSE"
    assert expired.status_code == 400 and "已过期" in expired.json()["detail"]["message"]
    assert good.status_code == 200, good.text
    aid = good.json()["asset"]["id"]

    tl = c.get(f"/projects/{pid}/docs/timeline").json()
    content = tl["content"]
    content["scenes"][0]["layers"] = [{"id": "img1", "type": "image",
                                       "assetSha": good.json()["asset"]["sha256"],
                                       "box": [0, 0, 100, 100]}]
    saved = c.put(f"/projects/{pid}/docs/timeline",
                  json={"content": content, "base_version": tl["version"]})
    assert saved.status_code == 200, saved.text
    stripped = c.patch(f"/assets/{aid}", json={"license": {"source": "", "type": ""}})
    assert stripped.status_code == 400 and "正被引用" in stripped.json()["detail"]["message"]
    tpl = c.post(f"/projects/{pid}/save-template", json={"name": "引用面模板", "description": ""})
    assert tpl.status_code == 200, tpl.text
    template_id = tpl.json()["template"]["templateId"]
    tl2 = c.get(f"/projects/{pid}/docs/timeline").json()
    tl2["content"]["scenes"][0]["layers"] = []
    c.put(f"/projects/{pid}/docs/timeline",
          json={"content": tl2["content"], "base_version": tl2["version"]})
    blocked = c.delete(f"/assets/{aid}")
    sites = blocked.json()["detail"]["details"]["usages"]
    assert blocked.status_code == 409 and any(u["source"] == "template" for u in sites), sites
    ok("4 许可门禁 + 引用面", "无/过期许可入库被拒；引用中不许清空；仅剩模板引用时删除 409")
    return template_id


def check_rights_and_delivery_gate(c: httpx.Client, pid: int) -> None:
    import json as _json

    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Project, Run, Workflow
    from app.services import delivery

    with Session(engine) as s:
        proj = s.get(Project, pid)
        wf = s.exec(select(Workflow).where(Workflow.project_id == pid)).first()
        run = s.exec(select(Run).where(Run.workflow_id == wf.id).order_by(Run.id.desc())).first()
        assert run is not None, "临时项目应有 Run"
        snap = delivery._ensure_run_documents_match(s, run, Path(proj.root), pid)
        assert ((snap.get("docs") or {}).get("timeline") or {}), "快照应含 timeline 文档"
        items, gaps = delivery._asset_rights(s, snap)
        assert all("sha256" in i and "type" in i for i in items)
        ok("5 交付一致性 + rights", f"同 Run 快照放行；rights 逐项真实资产（当前 {len(items)} 项、"
                                   f"缺口 {len(gaps)}）")

        # 合成漂移：当前 timeline 与快照不一致必须被拦
        drifted = _json.loads(_json.dumps(snap))
        scenes = drifted["docs"]["timeline"]["content"].get("scenes") or []
        scenes.append({"id": "S99", "start": 99.0, "end": 99.5})
        real = delivery.ensure_run_snapshot
        delivery.ensure_run_snapshot = lambda *_: drifted
        try:
            try:
                delivery._ensure_run_documents_match(s, run, Path(proj.root), pid)
                raise AssertionError("漂移未被拦")
            except RuntimeError as e:
                assert "E_DELIVERY_GATE" in str(e), str(e)
        finally:
            delivery.ensure_run_snapshot = real
        ok("6 漂移拦截", "timeline 与 Run 快照不一致 → E_DELIVERY_GATE")


def check_qa_undo_chain(c: httpx.Client, pid: int) -> None:
    def overflow_scene_id():
        for issue in c.get(f"/projects/{pid}/qa").json()["issues"]:
            if issue["category"] == "text_overflow":
                return issue
        return None

    def grow(sid: str):
        for n in range(1, 60):
            text = "这句话需要" + "很" * n + "时间才读完。"
            r = c.post(f"/projects/{pid}/timeline/ops",
                       json={"op": "set_text", "sceneId": sid, "text": text, "force": True})
            assert r.status_code == 200, r.text
            issue = next((i for i in c.get(f"/projects/{pid}/qa").json()["issues"]
                          if i["category"] == "text_overflow"
                          and i["location"]["sceneId"] == sid), None)
            if issue:
                return issue

    tl = c.get(f"/projects/{pid}/docs/timeline").json()["content"]
    sids = [str(s["id"]) for s in tl["scenes"]][:2]
    assert len(sids) == 2, tl["scenes"]
    issue_a = grow(sids[0])
    issue_b = grow(sids[1])
    fix_a = c.post(f"/projects/{pid}/qa/fix", json={"issueId": issue_a["id"],
                                                    "action": "extend_scene",
                                                    "payload": {"sceneId": sids[0],
                                                                "delta": 0.5}}).json()["fix"]
    fix_b = c.post(f"/projects/{pid}/qa/fix", json={"issueId": issue_b["id"],
                                                    "action": "extend_scene",
                                                    "payload": {"sceneId": sids[1],
                                                                "delta": 0.5}}).json()["fix"]
    assert fix_a["documentVerified"] is True and fix_a["verified"] is None, fix_a
    assert fix_a["afterHash"] and fix_b["afterHash"], "修复必须记录结果哈希"
    early = c.post(f"/projects/{pid}/qa/undo", json={"fixId": fix_a["id"]})
    assert early.status_code >= 400 and "倒序" in early.text and fix_b["id"] in early.text, early.text
    assert c.post(f"/projects/{pid}/qa/undo", json={"fixId": fix_b["id"]}).status_code == 200
    assert c.post(f"/projects/{pid}/qa/undo", json={"fixId": fix_a["id"]}).status_code == 200
    restored = c.get(f"/projects/{pid}/qa").json()["issues"]
    assert any(i["category"] == "text_overflow" for i in restored), restored
    ok("7 QA 多步撤销", "抢跑被拒且点名先撤项；倒序两级撤回到原状")


def check_migrations_and_validation(c: httpx.Client) -> None:
    from sqlmodel import Session, select

    from app.db import MIGRATIONS, apply_migrations, engine
    from app.models import SchemaMigration
    with Session(engine) as s:
        before = sorted(m.version for m in s.exec(select(SchemaMigration)).all())
    assert apply_migrations(MIGRATIONS, engine) == [], "已登记的迁移不得重跑"
    with Session(engine) as s:
        after = sorted(m.version for m in s.exec(select(SchemaMigration)).all())
    assert before == after, (before, after)
    bad = c.post("/projects", json={"name": "只有名字"})
    assert bad.status_code == 422, bad.status_code
    ok("8 迁移登记 + 422", f"登记 {after} 幂等；非法请求体 422 不进服务层")


def main() -> int:
    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=120, trust_env=False) as c:
        if c.get("/health").status_code != 200:
            raise SystemExit("API 未就绪：先 ./dev.sh")
        check_security(c)
        check_transitions()
        check_cache_inputs()
        template_id = None
        try:
            with throwaway(c, "p1-governance", COPY) as proj:
                pid = proj["id"]
                template_id = check_license_and_usage(c, pid)
                check_rights_and_delivery_gate(c, pid)
                check_qa_undo_chain(c, pid)
        finally:
            if template_id:
                c.delete(f"/templates/saved:{template_id}")
        check_migrations_and_validation(c)
    print("PASS: P1 治理复核全部通过（临时项目/模板/资产已自删）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
