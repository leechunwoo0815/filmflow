"""FR-38 验收：元数据/当前 Take/删除保护/分支/场景采纳。

判官 §六 #9：前置态（两次已完成 Run + 两条不同 S03 文案）由 `scripts/_scratch_state.py`
自建自删，**不再**写死演示项目 188 / Run 237/254——那正是本脚本当年把演示写脏的原因。
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scratch_state import (
    build_take_state,
    destroy_project,
    own_runs,
    req,
    wait_api,
)

BASE = "http://127.0.0.1:7860/api"


def main() -> int:
    wait_api()
    keep = "--keep" in sys.argv
    with httpx.Client(base_url=BASE, timeout=900, trust_env=False) as c:
        st = build_take_state(c, "takes-verify", keep_on_error=keep)
        pid, run_a, run_b = st["pid"], st["run_a"], st["run_b"]
        s03, text_a, text_b = st["scene"], st["text_a"], st["text_b"]
        print(f"自建：project={pid} A={run_a} B={run_b} "
              f"wall A={st['wall_a']}s B={st['wall_b']}s", flush=True)
        try:
            data = req(c, "GET", f"/projects/{pid}/takes")
            takes = {x["runId"]: x for x in data["items"]}
            assert run_a in takes and run_b in takes, takes.keys()
            assert takes[run_a]["videos"] and takes[run_b]["videos"]
            sha_a = takes[run_a]["videos"][0]["sha256"]
            sha_b = takes[run_b]["videos"][0]["sha256"]
            assert sha_a != sha_b, "两个 Take 的成片哈希相同"
            print("✓ A/B 视频 sha 不同", sha_a[:12], sha_b[:12], flush=True)

            a = req(c, "PATCH", f"/projects/{pid}/takes/{run_a}",
                    {"name": "A版-验收", "score": 5, "note": "原始"})
            b = req(c, "PATCH", f"/projects/{pid}/takes/{run_b}",
                    {"name": "B版-验收", "score": 4, "note": "B02 修复"})
            assert a["score"] == 5 and b["score"] == 4
            req(c, "POST", f"/projects/{pid}/takes/{run_b}/promote", {})
            assert req(c, "GET", f"/projects/{pid}/takes")["currentRunId"] == run_b
            r = c.delete(f"/projects/{pid}/takes/{run_b}")
            assert r.status_code == 409 and "当前 Take 不能删除" in r.text
            req(c, "DELETE", f"/projects/{pid}/takes/{run_a}")
            print("✓ 元数据/评分/当前/删除保护", flush=True)

            branch = req(c, "POST", f"/projects/{pid}/takes/{run_b}/branch", {})
            assert branch["parentRunId"] == run_b and branch["runId"] > run_b
            assert branch["runId"] in own_runs(c, pid), "分支 Run 没落到本项目名下"
            # 分支会把新 Run 留在 running：不取消的话删除闸门会按 P1-06 拒绝（实测撞过）
            req(c, "POST", f"/runs/{branch['runId']}/cancel", {})
            print("✓ 分支 Run", branch, flush=True)

            before = req(c, "GET", f"/projects/{pid}/docs/timeline")["content"]
            a_doc = req(c, "POST", f"/projects/{pid}/takes/{run_a}/adopt-scene", {"sceneId": s03})
            assert a_doc["content"]["scenes"][2]["text"] == text_a, a_doc["content"]["scenes"][2]
            assert all(a_doc["content"]["scenes"][i] == before["scenes"][i] for i in (0, 1))
            b_doc = req(c, "POST", f"/projects/{pid}/takes/{run_b}/adopt-scene", {"sceneId": s03})
            assert b_doc["content"]["scenes"][2]["text"] == text_b, b_doc["content"]["scenes"][2]
            assert all(b_doc["content"]["scenes"][i] == a_doc["content"]["scenes"][i] for i in (0, 1))
            assert b_doc["validation"]["ok"]
            print(f"✓ 采纳 {s03}：A→{text_a} / B→{text_b}，其余场景逐字节不变", flush=True)
            print("PASS: FR-38 Take 对比/采纳/提升/分支验收通过（全自建状态）")
            return 0
        finally:
            if not keep:
                destroy_project(c, pid, st["root"])
                print("自建状态已清理")
            else:
                print(f"保留：project={pid} root={st['root']}")


if __name__ == "__main__":
    sys.exit(main())
