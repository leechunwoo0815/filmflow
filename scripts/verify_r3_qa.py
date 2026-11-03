"""FR-39 QA 验收：溢出分类→扩场景→即时验证→多步 LIFO 撤销；许可修复；缺资产/资产许可定位。

自建自删临时项目（scripts/_acceptance.py），不再改写演示项目（P1-19）。
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _acceptance import throwaway  # noqa: E402

BASE = "http://127.0.0.1:7860/api"
COPY = "第一句话要读完其实不容易。第二句话同样需要更多时间才能读完。"
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")).decode()
c = httpx.Client(base_url=BASE, timeout=120, trust_env=False)


def req(method: str, pid: int, path: str, payload: dict | None = None):
    r = c.request(method, f"/projects/{pid}{path}", json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def api(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    with throwaway(c, "qa-verify", COPY) as proj:
        pid = proj["id"]
        qa = lambda: req("GET", pid, "/qa")  # noqa: E731
        tl_doc = req("GET", pid, "/docs/timeline")
        scenes = tl_doc["content"]["scenes"]
        assert len(scenes) >= 2, scenes
        s1, s2 = str(scenes[0]["id"]), str(scenes[1]["id"])

        def overflow_issue(sid: str):
            """把场景文案逐步加长到刚刚溢出（超过 0.19s 一档即可，保证 +0.5s 能修好）。"""
            for n in range(1, 80):
                text = "这句话需要" + "很" * n + "时间才读完。"
                req("POST", pid, "/timeline/ops", {"op": "set_text", "sceneId": sid,
                                                   "text": text, "force": True})
                issue = next((i for i in qa()["issues"] if i["category"] == "text_overflow"
                              and i["location"]["sceneId"] == sid), None)
                if issue:
                    return issue
            raise AssertionError(f"{sid} 造不出读时溢出")

        issue_a = overflow_issue(s1)
        issue_b = overflow_issue(s2)
        tl_before = req("GET", pid, "/docs/timeline")["content"]

        fix_a = req("POST", pid, "/qa/fix", {"issueId": issue_a["id"], "action": "extend_scene",
                                             "payload": {"sceneId": s1, "delta": 0.5}})["fix"]
        assert fix_a["verified"] is None and fix_a["documentVerified"] is True, fix_a
        assert fix_a["requiresRerun"] is True and fix_a["nextAction"] == "run_new", fix_a
        assert fix_a["afterHash"], "修复必须记录结果哈希，撤销链才有依据"
        issue_b = next(i for i in qa()["issues"]
                       if i["category"] == "text_overflow" and i["location"]["sceneId"] == s2)
        fix_b = req("POST", pid, "/qa/fix", {"issueId": issue_b["id"], "action": "extend_scene",
                                             "payload": {"sceneId": s2, "delta": 0.5}})["fix"]
        prof = req("GET", pid, "/docs/profile")["content"]
        tl = req("GET", pid, "/docs/timeline")["content"]
        assert abs(prof["duration"] - float(tl["duration"])) < 1e-6, (prof, tl)
        print("✓ 1. 两处溢出 → 连续两次扩场景 → timeline/profile 同步", flush=True)

        r = c.post(f"/projects/{pid}/qa/undo", json={"fixId": fix_a["id"]})
        assert r.status_code >= 400 and "倒序" in r.text and fix_b["id"] in r.text, r.text
        req("POST", pid, "/qa/undo", {"fixId": fix_b["id"]})
        req("POST", pid, "/qa/undo", {"fixId": fix_a["id"]})
        tl2 = req("GET", pid, "/docs/timeline")["content"]
        assert tl2 == tl_before, "两次撤销后 timeline 必须逐字段回到修复前"
        prof2 = req("GET", pid, "/docs/profile")["content"]
        # 修复前没有 profile 文档行 → 撤销后也不该留下残缺固化文档
        assert prof2.get("duration") in (None, float(tl2["duration"])), (prof2, tl2["duration"])
        assert any(i["category"] == "text_overflow" for i in qa()["issues"])
        print("✓ 2. 多步撤销按 LIFO：抢跑被拒并点名先撤项，倒序逐级回到原状", flush=True)

        lic = next(i for i in qa()["issues"] if i["category"] == "license_missing")
        lic_fix = req("POST", pid, "/qa/fix", {
            "issueId": lic["id"], "action": "fill_license",
            "payload": {"source": "自制", "license": "CC0", "authorized": True, "expires": ""}})["fix"]
        assert lic_fix["verified"] is True
        assert not any(i["category"] == "license_missing" for i in qa()["issues"])
        spec = next(s for s in lic["suggestions"] if s["action"] == "fill_license")
        assert spec["kind"] == "confirm" and "authorized" not in (spec.get("params") or {})
        req("POST", pid, "/qa/undo", {"fixId": lic_fix["id"]})
        print("✓ 3. 许可修复需显式授权，建议不再预置 authorized", flush=True)

        cur = req("GET", pid, "/docs/timeline")
        req("POST", pid, "/timeline/ops", {"op": "add_image", "baseVersion": cur["version"],
                                          "sceneId": s1, "assetSha": "0" * 64,
                                          "box": [10, 10, 100, 100]})
        miss = next((i for i in qa()["issues"] if i["category"] == "missing_asset"), None)
        assert miss and miss["location"]["sceneId"] == s1
        print("✓ 4. missing_asset 定位到场景/图层", flush=True)

        asset = api("POST", "/assets", {"scope": "project", "projectId": pid, "filename": "qa.png",
                                        "data": PNG, "name": "许可检查图",
                                        "license": {"source": "自制", "type": "CC0"}})["asset"]
        api("PATCH", f"/assets/{asset['id']}", {"license": {"source": "", "type": ""}})
        cur = req("GET", pid, "/docs/timeline")
        req("POST", pid, "/timeline/ops", {"op": "add_image", "baseVersion": cur["version"],
                                          "sceneId": s2, "assetSha": asset["sha256"],
                                          "box": [10, 10, 100, 100]})
        bad = next((i for i in qa()["issues"] if i["category"] == "asset_license_missing"), None)
        assert bad and bad["location"]["sceneId"] == s2, qa()["issues"]
        api("PATCH", f"/assets/{asset['id']}", {"license": {"source": "自制", "type": "CC0"}})
        assert not any(i["category"] == "asset_license_missing" for i in qa()["issues"])
        print("✓ 5. 资产缺许可被 QA 分类，补齐后消失", flush=True)

        report = req("GET", pid, "/qa/report")
        assert report["attempts"] == 3 and report["undone"] == 3, report
        assert report["successRate"] == 1.0, report
        print(f"✓ 6. QA 报告 attempts={report['attempts']} undone={report['undone']} "
              f"successRate={report['successRate']}（临时项目，无演示污染）", flush=True)
    print("PASS: FR-39 QA 修复建议验收通过（项目/文档/资产已自删）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
