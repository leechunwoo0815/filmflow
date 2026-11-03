"""FR-39 QA 验收：读时溢出分类→扩场景→即时验证→撤销；许可修复；缺资产定位。"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:7860/api"
PID = 227
c = httpx.Client(base_url=BASE, timeout=120, trust_env=False)


def req(method: str, path: str, payload: dict | None = None):
    r = c.request(method, path, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:500]}")
    return r.json()


def qa() -> dict:
    return req("GET", f"/projects/{PID}/qa")


def restore_doc(kind: str, original: dict) -> dict:
    cur = req("GET", f"/projects/{PID}/docs/{kind}")
    if cur["content"] == original["content"]:
        return cur
    return req("PUT", f"/projects/{PID}/docs/{kind}", {
        "content": original["content"], "base_version": cur["version"],
        "author": "qa-verify-cleanup"})


def restore(original: dict, original_profile: dict | None = None) -> None:
    restore_doc("timeline", original)
    if original_profile is not None:
        restore_doc("profile", original_profile)


def main() -> int:
    if c.get("/health", timeout=3).status_code != 200:
        raise SystemExit("API 未就绪")
    original = req("GET", f"/projects/{PID}/docs/timeline")
    original_profile = req("GET", f"/projects/{PID}/docs/profile")
    scene_id = original["content"]["scenes"][0]["id"]
    try:
        long_text = "这一句话需要再多一点时间读。"
        req("POST", f"/projects/{PID}/timeline/ops", {
            "op": "set_text", "sceneId": scene_id, "text": long_text, "force": True})
        analysis = qa()
        issues = [i for i in analysis["issues"] if i["category"] == "text_overflow"]
        assert issues, analysis["issues"]
        issue = issues[0]
        assert issue["location"]["sceneId"] == scene_id
        assert any(s["action"] == "extend_scene" for s in issue["suggestions"])
        fix = req("POST", f"/projects/{PID}/qa/fix", {
            "issueId": issue["id"], "action": "extend_scene",
            "payload": {"sceneId": scene_id, "delta": 0.5}})["fix"]
        assert fix["verified"] is None and fix["documentVerified"] is True, fix
        assert fix["requiresRerun"] is True and fix["nextAction"] == "run_new", fix
        assert not any(i["category"] == "text_overflow" for i in qa()["issues"])
        prof = req("GET", f"/projects/{PID}/docs/profile")["content"]
        tl = req("GET", f"/projects/{PID}/docs/timeline")["content"]
        assert abs(prof["duration"] - float(tl["duration"])) < 1e-6, (prof, tl)
        print("✓ 1. text_overflow → 扩场景 0.5s → 文档/ profile 同步，成片待新 Run 验证", flush=True)

        req("POST", f"/projects/{PID}/qa/undo", {"fixId": fix["id"]})
        assert any(i["category"] == "text_overflow" for i in qa()["issues"])
        prof2 = req("GET", f"/projects/{PID}/docs/profile")["content"]
        assert abs(prof2["duration"] - float(original_profile["content"]["duration"])) < 1e-6
        print("✓ 2. 修复可撤销，timeline/profile 同步恢复", flush=True)

        lic = next((i for i in qa()["issues"] if i["category"] == "license_missing"), None)
        assert lic, qa()["issues"]
        lic_fix = req("POST", f"/projects/{PID}/qa/fix", {
            "issueId": lic["id"], "action": "fill_license",
            "payload": {"source": "自制", "license": "CC0", "authorized": True,
                        "expires": ""}})["fix"]
        assert lic_fix["verified"] is True
        assert not any(i["category"] == "license_missing" for i in qa()["issues"])
        req("POST", f"/projects/{PID}/qa/undo", {"fixId": lic_fix["id"]})
        print("✓ 3. license_missing → 填许可 → 验证 → 撤销", flush=True)

        cur = req("GET", f"/projects/{PID}/docs/timeline")
        req("POST", f"/projects/{PID}/timeline/ops", {
            "op": "add_image", "baseVersion": cur["version"], "sceneId": scene_id,
            "assetSha": "0" * 64, "box": [10, 10, 100, 100]})
        miss = next((i for i in qa()["issues"] if i["category"] == "missing_asset"), None)
        assert miss and miss["location"]["sceneId"] == scene_id
        print("✓ 4. missing_asset 定位到场景/图层", flush=True)
        cur = req("GET", f"/projects/{PID}/docs/timeline")
        lid = cur["content"]["scenes"][0]["layers"][-1]["id"]
        req("POST", f"/projects/{PID}/timeline/ops", {
            "op": "remove_layer", "baseVersion": cur["version"],
            "sceneId": scene_id, "layerId": lid})
        report = req("GET", f"/projects/{PID}/qa/report")
        assert report["attempts"] >= 2 and report["undone"] >= 2
        assert report["successRate"] is not None
        print(f"✓ 5. QA 报告 attempts={report['attempts']} undone={report['undone']} "
              f"successRate={report['successRate']}", flush=True)
        print("PASS: FR-39 QA 修复建议验收通过")
        return 0
    finally:
        restore(original, original_profile)


if __name__ == "__main__":
    sys.exit(main())
