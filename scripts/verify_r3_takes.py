"""FR-38 验收：元数据/当前 Take/删除保护/分支/场景采纳（project 188 A=237 B=254）。"""
from __future__ import annotations

import sys

import httpx

c = httpx.Client(base_url="http://127.0.0.1:7860/api", timeout=120, trust_env=False)
PID = 188


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    data = req("GET", f"/projects/{PID}/takes").json()
    takes = {x["runId"]: x for x in data["items"]}
    assert 237 in takes and 254 in takes, takes.keys()
    assert takes[237]["videos"] and takes[254]["videos"]
    assert takes[237]["videos"][0]["sha256"] != takes[254]["videos"][0]["sha256"]
    print("✓ A/B 视频 sha 不同", takes[237]["videos"][0]["sha256"][:12],
          takes[254]["videos"][0]["sha256"][:12], flush=True)

    a = req("PATCH", f"/projects/{PID}/takes/237",
            {"name": "A版-验收", "score": 5, "note": "原始"}).json()
    b = req("PATCH", f"/projects/{PID}/takes/254",
            {"name": "B版-验收", "score": 4, "note": "B02 修复"}).json()
    assert a["score"] == 5 and b["score"] == 4
    req("POST", f"/projects/{PID}/takes/254/promote", {})
    assert req("GET", f"/projects/{PID}/takes").json()["currentRunId"] == 254
    r = c.delete(f"/projects/{PID}/takes/254")
    assert r.status_code == 409 and "当前 Take 不能删除" in r.text
    req("DELETE", f"/projects/{PID}/takes/253")
    print("✓ 元数据/评分/当前/删除保护", flush=True)

    branch = req("POST", f"/projects/{PID}/takes/254/branch", {}).json()
    assert branch["parentRunId"] == 254 and branch["runId"] > 254
    print("✓ 分支 Run", branch, flush=True)

    before = req("GET", f"/projects/{PID}/docs/timeline").json()["content"]
    a_doc = req("POST", f"/projects/{PID}/takes/237/adopt-scene", {"sceneId": "S03"}).json()
    assert a_doc["content"]["scenes"][2]["text"] == "改写三。"
    assert [a_doc["content"]["scenes"][i] == before["scenes"][i] for i in (0, 1)]
    b_doc = req("POST", f"/projects/{PID}/takes/254/adopt-scene", {"sceneId": "S03"}).json()
    assert b_doc["content"]["scenes"][2]["text"] == "B版三。"
    assert [b_doc["content"]["scenes"][i] == a_doc["content"]["scenes"][i] for i in (0, 1, 3, 4)]
    assert b_doc["validation"]["ok"]
    print("✓ 采纳 S03：只有 S03 变化，S01/S02/S04/S05 不变", flush=True)
    print("PASS: FR-38 Take 对比/采纳/提升/分支验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
