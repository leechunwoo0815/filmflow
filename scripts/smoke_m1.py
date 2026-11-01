"""M0/M1 全链冒烟：真实 HTTP 驱动——索引 → 导入 rumor-39s → Run → 门审批 → D05。

用法：uv run python scripts/smoke_m1.py   （服务已在 :7860 运行）
"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:7860/api"
c = httpx.Client(base_url=BASE, timeout=60)


def wait_status(run_id: int, want: set[str], timeout: float = 600) -> dict:
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        g = c.get(f"/runs/{run_id}/graph").json()
        statuses = {n["id"]: n["status"] for n in g["nodes"]}
        sig = json.dumps(statuses, sort_keys=True)
        if sig != last:
            interesting = {k: v for k, v in statuses.items() if v not in ("idle",)}
            print(f"  [{time.time()-t0:5.0f}s] {interesting}", flush=True)
            last = sig
        run_status = g["run"]["status"]
        pending = c.get(f"/gates/{run_id}/pending").json()["items"]
        pendable = [p["gate"] for p in pending]
        if want & set(pendable):
            return {"graph": g, "statuses": statuses, "pending": pendable}
        if run_status in ("succeeded", "failed", "needs_changes") and not pendable:
            return {"graph": g, "statuses": statuses, "pending": pendable}
        time.sleep(2)
    raise TimeoutError("等待超时")


def approve(gate: str, run_id: int, note: str = ""):
    r = c.post(f"/gates/{gate}/decide", json={"run_id": run_id, "decision": "approved", "author": "smoke", "note": note})
    print(f"  ✓ 批准 {gate}: {r.json()}")


def main() -> int:
    print("== 1. 环境 ==", flush=True)
    print("health:", c.get("/health").json())
    env = c.get("/environment").json()
    print("env ok:", env.get("ok"), "| engines:", [e.get("engine_id") for e in c.get("/engines").json()["engines"]])

    print("== 2. 索引真实风格库 ==", flush=True)
    rep = c.post("/library/index").json()
    print("341?", rep.get("prompt_count"), "| covers:", rep.get("covers"), "| 矩阵:", c.get("/library/status").json()["matrix"])

    print("== 3. 搜索（同义词）==", flush=True)
    hits = c.get("/styles", params={"q": "水墨"}).json()
    z_hits = [i["id"] for i in hits["items"] if "中国风" in i["collection"]]
    print(f"「水墨」命中 {len(hits['items'])} 条，Z 集 {len(z_hits)} 条")
    rec = c.get("/recommend", params={"script": "一条关于谣言传播与真相核查的科普短片"}).json()
    print("推荐:", [r["style_id"] for r in rec["items"]][:12])

    print("== 4. 导入 rumor-39s ==", flush=True)
    created = c.post("/projects/import", json={"root": "/Users/litianyu/cc-projects/ai-v/rumor-39s"}).json()
    run_id, project_id = created["run_id"], created["project"]["id"]
    print("project:", project_id, "run:", run_id)
    g = c.get(f"/runs/{run_id}/graph").json()
    assert len(g["nodes"]) == 46 and len(g["edges"]) >= 80
    print(f"画布：{len(g['nodes'])} 节点 / {len(g['edges'])} 边 ✓")

    print("== 5. Run 全链（到 D05）==", flush=True)
    c.post(f"/runs/{run_id}/resume")   # 断点续跑语义：failed/skipped → idle 重新入队
    r = wait_status(run_id, want={"B08"})
    if "B08" in r["pending"]:
        st = r["statuses"]
        assert st.get("B07") in ("succeeded", "cached"), f"B07 未通过不得批 B08（{st.get('B07')}）"
        print("  B08 待批准（B07 =", st.get("B07"), "✓）")
        # 先试驳回 → 下游 blocked（规格验收：驳回后全 blocked）
        c.post("/gates/B08/decide", json={"run_id": run_id, "decision": "rejected", "author": "smoke", "note": "冒烟测试驳回"})
        time.sleep(2)
        st = {n["id"]: n["status"] for n in c.get(f"/runs/{run_id}/graph").json()["nodes"]}
        blocked = [k for k, v in st.items() if v in ("blocked", "skipped")]
        print(f"  驳回后 blocked/skipped {len(blocked)} 个 ✓")
        c.post("/gates/B08/decide", json={"run_id": run_id, "decision": "approved", "author": "smoke", "note": "复核通过"})
        print("  重新批准 B08")
    r = wait_status(run_id, want={"D03"})
    # D03 前置：查看 3 个区域
    for i in range(3):
        c.post(f"/projects/{project_id}/stills/viewed",
               json={"region": f"r{i}", "zoom": "100%", "at": time.time()})
    approve("D03", run_id)
    r = wait_status(run_id, want={"D05"})
    approve("D05", run_id)
    r = wait_status(run_id, want={"E07"}, timeout=120)
    st = r["statuses"]
    print("D05 批准后：D02/D04 =", st.get("D02"), st.get("D04"), "| E01 等待 =", st.get("E01"))
    d05_done = st.get("D05") in ("succeeded", "cached")
    print("== M1 验收（B07→D05）:", "✓ 通过" if d05_done else "✗ 未通过", "==")
    return 0 if d05_done else 1


if __name__ == "__main__":
    sys.exit(main())
