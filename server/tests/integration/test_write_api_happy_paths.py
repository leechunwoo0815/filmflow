"""P1-23 判官 §三-10 / §六 #3：模型化写端点的 **happy path**（不是只测 422）。

跑真 uvicorn（`isolated_api` 夹具）+ 独立 FILMFLOW_HOME/工作区，所以这里写的都是
一次性数据，绝不碰生产库或演示项目。断言口径：
* `2xx` = 请求穿过模型、进入服务层并真的产生了业务效果（读回验证）；
* 需要真实出片/真实前置态才能全绿的几条（review/package、take branch/adopt、
  delivery），断言的是**服务层的业务码**（404/409 + 中文理由），证明请求已过模型层、
  没有被字段名/类型问题打回；真正的端到端由 `scripts/verify_r2_5_*.py`、
  `scripts/verify_r3_takes.py` 实跑覆盖（HANDOFF §0.0 有 run 号）。
"""
from __future__ import annotations

import base64
import json
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

COPY = "真相会显形。谣言会散。"
# S01 需要约 2.3s 读完、场景只有 2.0s：溢出 < 0.5s，所以一次 extend_scene 就能修好
LONG_COPY = "谣言要经得起第二次查看。真相会在静默里显形。"


def _req(client: httpx.Client, method: str, path: str, payload=None, **kw):
    r = client.request(method, path, json=payload, **kw)
    assert r.status_code < 400, f"{method} {path} -> {r.status_code} {r.text[:400]}"
    return r.json()


def _wizard_project(client: httpx.Client, workspace: Path, name: str, *,
                    copy: str = COPY, duration: float = 4.0) -> dict:
    """5 步向导 materialize：只有这条路会写 profile + style pick + 初始文档。"""
    root = workspace / f"hp-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True)
    (root / "card" / "copy.txt").write_text(copy, encoding="utf-8")
    style = client.get("/styles?chips=可生产&family=print&limit=1").json()["items"][0]["id"]
    d = _req(client, "POST", "/drafts", {"name": name, "step": 1})
    _req(client, "PATCH", f"/drafts/{d['id']}", {
        "step": 5, "payload": {"root": str(root), "copy": copy,
                               "profile": {"width": 1920, "height": 1080, "fps": 24,
                                           "duration": duration},
                               "pick": {"primary": style, "alternates": [], "reason": "hp"},
                               "brief": {"title": name}}})
    m = _req(client, "POST", f"/drafts/{d['id']}/materialize", {})
    pid = int(m["project"]["id"])
    tl = _req(client, "GET", f"/projects/{pid}/docs/timeline")
    return {"pid": pid, "root": root, "run_id": int(m["run_id"]),
            "workflow_id": int(m["workflow_id"]), "style": style,
            "scenes": [s["id"] for s in tl["content"]["scenes"]],
            "tl_version": tl["version"]}


@pytest.fixture(scope="module")
def proj(api_client, isolated_api) -> dict:
    _base, workspace = isolated_api
    p = _wizard_project(api_client, workspace, "hp-main")
    yield p
    api_client.delete(f"/projects/{p['pid']}", params={"confirm": "true"})


def test_drafts_lifecycle(api_client):
    """DraftCreateIn / DraftPatchIn：step 边界 + payload **合并**语义（模型化不许改）。"""
    d = _req(api_client, "POST", "/drafts", {"name": "hp-draft", "step": 1})
    assert d["step"] == 1 and d["name"] == "hp-draft"
    p = _req(api_client, "PATCH", f"/drafts/{d['id']}", {"step": 3, "payload": {"copy": COPY}})
    assert p["step"] == 3 and p["payload_json"]["copy"] == COPY
    p2 = _req(api_client, "PATCH", f"/drafts/{d['id']}", {"payload": {"title": "只改标题"}})
    assert p2["payload_json"]["copy"] == COPY, "PATCH 必须合并而不是覆盖"
    assert p2["step"] == 3, "没传 step 就不该动 step"


def test_project_import_happy(api_client, isolated_api):
    """ProjectImportIn：导入项目写 meta/params，name 可省（回退目录名）。"""
    _base, workspace = isolated_api
    root = workspace / f"hp-import-{uuid.uuid4().hex[:8]}"
    (root / "card").mkdir(parents=True)
    (root / "card" / "task.json").write_text(json.dumps(
        {"fps": 24, "phase": "card", "film": {"duration": 2, "frames": 48},
         "scenes": [{"id": "S01", "start": 0, "end": 2, "meaning": "导入的场景。",
                     "operation": "保留"}], "events": [],
         "stills": {"frames": [{"id": "S01"}]}}), encoding="utf-8")
    created = _req(api_client, "POST", "/projects/import", {"root": str(root)})
    assert created["project"]["name"] == root.name
    wf = _req(api_client, "GET", f"/workflows/{created['workflow_id']}")
    assert wf["graph_json"]["meta"]["imported"] is True
    assert wf["graph_json"]["params"]["D02"] == {"scenes": ["S01"]}
    # 导入项目才允许写任务卡（TaskPutIn 的 happy path）
    _req(api_client, "PUT", f"/projects/{created['project']['id']}/task",
         {"task": {"phase": "card", "actions": ["read", "write_plan"], "scenes": []},
          "author": "hp"})
    saved = json.loads((root / "card" / "task.json").read_text(encoding="utf-8"))
    assert saved["actions"] == ["read", "write_plan"]
    api_client.delete(f"/projects/{created['project']['id']}", params={"confirm": "true"})


def test_orchestration_happy(api_client, proj):
    """WorkflowCreateIn / WorkflowPutIn / RunCreateIn。"""
    bad = api_client.post("/workflows", json={"projectId": 999_999})
    assert bad.status_code == 404, bad.text  # 外键开着：缺项目给 404，不再是 KeyError → 500
    w = _req(api_client, "POST", "/workflows",
             {"projectId": proj["pid"], "graph": {"nodes": [], "edges": []}})
    assert w["graph_json"] == {"nodes": [], "edges": []} and w["version"] == 1
    updated = _req(api_client, "PUT", f"/workflows/{w['id']}",
                   {"graph": {"nodes": [{"id": "A01"}], "edges": []}})
    assert updated["version"] == 2 and updated["graph_json"]["nodes"] == [{"id": "A01"}]
    kept = _req(api_client, "PUT", f"/workflows/{w['id']}", {})
    assert kept["graph_json"]["nodes"] == [{"id": "A01"}], "不传 graph 必须保留原图"
    run = _req(api_client, "POST", "/runs", {"workflowId": proj["workflow_id"],
                                             "params": {"B06": {"mode": "import"}}})
    assert run["params_snapshot"] == {"B06": {"mode": "import"}}


def test_label_submit_persists(api_client, proj):
    """LabelSubmitIn：键存在性决定改哪些 token；补标必须真的写进库。

    这条 happy path 顺带抓出一个真缺陷：tokens_json 是原地改的 dict，
    SQLAlchemy 不标脏就不写库——补标历史上会静默丢失。
    """
    queue = _req(api_client, "GET", "/labels/queue")["items"]
    # 刻意避开 proj 用的风格：token 会进着色器，补标测试不该把在产风格改脏
    style = next((s["id"] for s in queue if s["id"] != proj["style"]), None)
    assert style, "补标队列为空，无法验证"
    r = _req(api_client, "POST", f"/labels/{style}",
             {"family": "print", "palette": ["#F4EEE2", "#3D5588"], "labeled": True})
    assert r["tokens"]["palette"] == ["#F4EEE2", "#3D5588"], r
    again = _req(api_client, "POST", f"/labels/{style}",
                 {"texture": ["丝网"], "screen": {"angle": 22.5, "period": 6}})
    assert again["tokens"]["palette"] == ["#F4EEE2", "#3D5588"], "没传 palette 不该被清掉"
    assert "丝网" in again["tokens"]["texture"], again
    assert again["tokens"]["screen"]["angle"] == 22.5, again
    # 读回（换新请求，绕过任何会话缓存）才算真的落库
    refetched = _req(api_client, "GET", f"/styles/{style}")
    assert refetched["tokens"]["palette"] == ["#F4EEE2", "#3D5588"], refetched
    assert "丝网" in refetched["tokens"]["texture"], refetched
    # 入口闸门：非 hex 调色不会再写进在产风格（写进去就是预览 500）
    rejected = api_client.post(f"/labels/{style}", json={"palette": ["高对比"]})
    assert rejected.status_code == 422 and "十六进制" in rejected.text, rejected.text
    assert _req(api_client, "GET", f"/styles/{style}")["tokens"]["palette"] == \
        ["#F4EEE2", "#3D5588"], "被拒的请求不该改动任何 token"


def test_timeline_ops_and_rebuild(api_client, proj):
    """TimelineOpIn（baseVersion 乐观锁）与 TimelineRebuildIn（省略即回退当前版本）。"""
    pid, s01 = proj["pid"], proj["scenes"][0]
    doc = _req(api_client, "POST", f"/projects/{pid}/timeline/ops",
               {"op": "set_text", "sceneId": s01, "text": "改过的短句。",
                "baseVersion": proj["tl_version"]})
    assert doc["version"] == proj["tl_version"] + 1
    assert any(s["id"] == s01 and s.get("text") == "改过的短句。" for s in doc["content"]["scenes"])
    stale = api_client.post(f"/projects/{pid}/timeline/ops",
                            json={"op": "set_text", "sceneId": s01, "text": "x。",
                                  "baseVersion": proj["tl_version"]})
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "E_DOC_CONFLICT", stale.text

    rebuilt = _req(api_client, "POST", f"/projects/{pid}/docs/timeline/rebuild", {"author": "hp"})
    assert rebuilt["version"] > doc["version"], "省略 base_version 要回退到当前版本"
    assert rebuilt["content"]["scenes"], "重建后时间轴不该是空的"


def test_docs_save_restore_and_render_profile(api_client, proj):
    """DocSaveIn / DocRestoreIn / RenderProfileUpdateIn。"""
    pid = proj["pid"]
    prof = _req(api_client, "PUT", f"/projects/{pid}/render-profile",
                {"profiles": {"draft": {"width": 960, "height": 540, "fps": 12}}})
    assert prof["draft"]["width"] == 960 and prof["final"]["width"] == 1920
    script = _req(api_client, "GET", f"/projects/{pid}/docs/script")
    saved = _req(api_client, "PUT", f"/projects/{pid}/docs/script",
                 {"content": {"text": "第一句。\n第二句。"}, "base_version": script["version"],
                  "author": "hp"})
    assert saved["version"] == script["version"] + 1
    restored = _req(api_client, "POST", f"/projects/{pid}/docs/script/restore",
                    {"version": script["version"], "author": "hp"})
    assert restored["content"]["text"] == script["content"]["text"]
    ro = api_client.put(f"/projects/{pid}/task", json={"task": {"phase": "card"}})
    assert ro.status_code == 409 and "只读快照" in ro.text, ro.text


def test_assets_import_update_fontcheck_replace(api_client, proj):
    """AssetImportIn / AssetUpdateIn / FontCheckIn / AssetReplaceIn（替换须同类型）。"""
    import io

    from PIL import Image

    def png_b64(color) -> str:
        buf = io.BytesIO()
        Image.new("RGB", (16, 9), color).save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()

    lic = {"source": "自制", "type": "CC0"}
    a = _req(api_client, "POST", "/assets", {"scope": "global", "filename": "hp-a.png",
                                             "data": png_b64((200, 30, 40)), "kind": "image",
                                             "name": "hp 图", "tags": ["hp"],
                                             "license": lic})["asset"]
    assert a["bytes"] > 0 and a["license"]["type"] == "CC0"
    upd = _req(api_client, "PATCH", f"/assets/{a['id']}", {"tags": ["hp", "改过"],
                                                           "name": "hp 图 2"})
    assert set(upd["asset"]["tags"]) == {"hp", "改过"} and upd["asset"]["name"] == "hp 图 2"

    b = _req(api_client, "POST", "/assets", {"scope": "global",
                                             "filename": "hp-b.png", "data": png_b64((10, 90, 200)),
                                             "kind": "image", "name": "hp 替身",
                                             "license": lic})["asset"]
    rep = _req(api_client, "POST", f"/assets/{a['id']}/replace", {"assetId": b["id"]})
    assert rep["old"]["id"] == a["id"] and rep["new"]["id"] == b["id"], rep
    assert rep["projects"] == [] and rep["affectedScenes"] == [], \
        "没有时间轴引用旧 sha 时不该改任何文档"

    font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if font.exists():
        fa = _req(api_client, "POST", "/assets", {"scope": "global", "filename": "hp.ttf",
                                                 "data": base64.b64encode(font.read_bytes())
                                                 .decode(), "kind": "font", "name": "hp 字体",
                                                 "license": lic})["asset"]
        chk = _req(api_client, "POST", f"/assets/{fa['id']}/font-check", {"text": "abc ABC"})
        assert chk["total"] == 6 and chk["covered"] == 6 and chk["ok"] is True, chk
        assert _req(api_client, "POST", f"/assets/{fa['id']}/font-check", {})["total"] == 0
        missing = _req(api_client, "POST", f"/assets/{fa['id']}/font-check",
                       {"text": "😀A"})
        assert missing["missing"] == ["😀"], missing
    api_client.delete(f"/assets/{a['id']}", params={"force": "true"})
    api_client.delete(f"/assets/{b['id']}", params={"force": "true"})


def test_templates_series_and_clone(api_client, proj):
    """TemplateSaveIn / TemplateVersionIn / SceneTemplate*In / TemplateUpgradeIn /
    SeriesCreateIn / FromTemplateIn / ExampleCloneIn 的一条完整回路。"""
    pid = proj["pid"]
    saved = _req(api_client, "POST", f"/projects/{pid}/save-template",
                 {"name": "hp 模板", "description": "描述",
                  "copy": "{{title}}：第一句。第二句。"})["template"]
    assert saved["kind"] == "project" and saved["version"] == 1
    tid = saved["id"]

    v2 = _req(api_client, "POST", f"/templates/{tid}/version",
              {"projectId": pid, "copy": "{{title}}：改过的文案。", "name": "hp 模板 v2"})["template"]
    assert v2["version"] == 2 and v2["name"] == "hp 模板 v2"

    dry = _req(api_client, "POST", f"/projects/{pid}/template-upgrade",
               {"templateId": tid, "confirm": False})
    assert dry["applied"] is False and "diff" in dry
    applied = _req(api_client, "POST", f"/projects/{pid}/template-upgrade",
                   {"templateId": tid, "confirm": True})
    assert applied["applied"] is True and applied["lock"]["version"] == 2

    scene = _req(api_client, "POST", f"/projects/{pid}/scenes/{proj['scenes'][0]}/save-template",
                 {"name": "hp 场景", "keepText": True, "description": "场景模板"})["template"]
    before = _req(api_client, "GET", f"/projects/{pid}/docs/timeline")
    inserted = _req(api_client, "POST", f"/projects/{pid}/timeline/scene-template",
                    {"templateId": scene["id"], "afterSceneId": proj["scenes"][0],
                     "baseVersion": before["version"]})
    assert inserted["sceneId"]
    assert len(inserted["content"]["scenes"]) == len(before["content"]["scenes"]) + 1
    assert inserted["content"]["scenes"][1]["id"] == inserted["sceneId"]

    created = []
    from_tpl = _req(api_client, "POST", "/projects/from-template",
                    {"templateId": tid, "name": "hp 派生", "variables": {"title": "标题"}})
    created.append(from_tpl["project"]["id"])
    assert from_tpl["project"]["name"] == "hp 派生"

    series = _req(api_client, "POST", "/series/from-template",
                  {"templateId": tid, "name": "hp 系列",
                   "items": [{"name": "hp 系列 01", "variables": {"title": "甲"}},
                             "纯字符串条目"]})
    assert series["created"] == 2 and series["failed"] == 0, series
    created += [x["project"]["id"] for x in series["items"]]

    examples = _req(api_client, "GET", "/examples")["items"]
    assert examples, "内置示例为空——FR-31 夹具没带进来？"
    cloned = _req(api_client, "POST", f"/examples/{examples[0]['id']}/clone",
                  {"name": "hp 示例克隆"})
    assert cloned["example"] == examples[0]["id"] and cloned["project"]["name"] == "hp 示例克隆"
    created.append(cloned["project"]["id"])

    for extra in created:
        assert api_client.delete(f"/projects/{extra}", params={"confirm": "true"}).status_code == 200
    for x in (tid, scene["id"]):
        api_client.delete(f"/templates/saved:{x}")


@pytest.mark.requires_ffmpeg
def test_audio_workbench(api_client, isolated_api, proj):
    """AudioUploadIn / AudioPrimaryIn / AudioScenePrimaryIn / AudioProcessIn / AudioMarkersIn
    + 第二批的 AudioMixSaveIn / AudioLicenseSaveIn / AudioAlignmentSaveIn。"""
    _base, workspace = isolated_api
    pid, scene = proj["pid"], proj["scenes"][0]
    wav = workspace / f"hp-audio-{uuid.uuid4().hex[:6]}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=220:duration=1", "-ac", "1", "-ar", "48000", str(wav)],
                   check=True, capture_output=True, timeout=120)
    data = base64.b64encode(wav.read_bytes()).decode()

    t1 = _req(api_client, "POST", f"/projects/{pid}/audio/upload",
              {"filename": "hp.wav", "data": data, "kind": "voice",
               "sceneId": scene, "name": "hp 口播"})["take"]
    assert t1["kind"] == "voice" and t1["duration"] > 0 and t1["primary"] is True
    music = _req(api_client, "POST", f"/projects/{pid}/audio/upload",
                 {"filename": "hp-music.wav", "data": data, "kind": "music",
                  "name": "hp 音乐"})["take"]
    assert _req(api_client, "POST", f"/projects/{pid}/audio/primary",
                {"takeId": t1["id"]})["primary"]["id"] == t1["id"]
    assert _req(api_client, "POST", f"/projects/{pid}/audio/scene-primary",
                {"sceneId": scene, "takeId": t1["id"]})["takeId"] == t1["id"]
    assert _req(api_client, "POST", f"/projects/{pid}/audio/scene-primary",
                {"sceneId": scene, "takeId": ""})["takeId"] is None

    processed = _req(api_client, "POST", f"/projects/{pid}/audio/takes/{t1['id']}/process",
                     {"denoise": True, "normalize": False})["take"]
    assert processed["processing"]["denoise"] is True and processed["processedFile"]
    cleared = _req(api_client, "POST", f"/projects/{pid}/audio/takes/{t1['id']}/process", {})["take"]
    assert not cleared.get("processing"), cleared

    mk = _req(api_client, "POST", f"/projects/{pid}/audio/markers",
              {"markers": [{"id": "m1", "time": 0.5, "label": "拍点"}]})
    assert mk["markers"][0]["time"] == 0.5 and mk["markers"][0]["label"] == "拍点"
    assert _req(api_client, "POST", f"/projects/{pid}/audio/markers",
                {"markers": []})["markers"] == []

    mix = _req(api_client, "POST", f"/projects/{pid}/audio/mix",
               {"preset": "-16", "stems": {"voice": 0, "music": -8, "sfx": -120}})
    assert mix["targetLufs"] == -16
    lic = _req(api_client, "POST", f"/projects/{pid}/audio/license",
               {"source": "自制", "license": "CC0", "authorized": True, "note": "hp"})
    assert lic["license"]["source"] == "自制" and lic["license"]["license"] == "CC0", lic
    align = _req(api_client, "POST", f"/projects/{pid}/audio/alignment",
                 {"segments": [{"text": "真相会显形。", "start": 0.0, "end": 1.9},
                               {"text": "谣言会散。", "start": 2.0, "end": 3.9}],
                  "author": "hp"})
    assert align["source"] == "manual" and align["author"] == "hp", align
    assert [s["end"] for s in align["segments"]] == [1.9, 3.9], align
    bad_align = api_client.post(f"/projects/{pid}/audio/alignment",
                                json={"segments": [{"start": 2.0, "end": 1.0}]})
    assert bad_align.status_code == 400 and "非法" in bad_align.text, bad_align.text
    assert music["kind"] == "music"


def test_review_workbench(api_client, proj):
    """ReviewCommentAddIn / ReviewCommentPatchIn / ReviewDecideIn / ReviewImportIn /
    StillsViewedIn / ReviewPackageIn。"""
    pid, scene = proj["pid"], proj["scenes"][0]
    c = _req(api_client, "POST", f"/projects/{pid}/review/comments",
             {"frame": 12, "time": 0.5, "sceneId": scene, "kind": "text", "category": "must",
              "body": "字太小。", "geometry": {"x": 1, "y": 2}, "author": "hp"})
    assert c["frame"] == 12 and c["status"] == "open" and c["category"] == "must"

    patched = _req(api_client, "PATCH", f"/projects/{pid}/review/comments/{c['id']}",
                   {"status": "resolved", "reply": "已改"})
    assert patched["status"] == "resolved" and len(patched["replies"]) == 1
    untouched = _req(api_client, "PATCH", f"/projects/{pid}/review/comments/{c['id']}",
                     {"assignee": "me"})
    assert untouched["body"] == "字太小。", "没传 body 不该清空"
    assert untouched["status"] == "resolved", "没传 status 不该回退"

    dec = _req(api_client, "POST", f"/projects/{pid}/review/decisions",
               {"decision": "pass", "sceneId": scene, "note": "ok"})
    assert dec["scenes"][scene]["decision"] == "pass"
    overall = _req(api_client, "POST", f"/projects/{pid}/review/decisions",
                   {"decision": "approved"})
    assert overall["overall"]["decision"] == "approved"
    bad = api_client.post(f"/projects/{pid}/review/decisions", json={"decision": "随便"})
    assert bad.status_code == 400 and "决议必须是" in bad.text, bad.text

    imp = _req(api_client, "POST", f"/projects/{pid}/review/import",
               {"review": {"comments": [
                   {"id": "hp1", "frame": 1, "time": 0.1, "sceneId": scene, "kind": "text",
                    "category": "suggest", "body": "导入的批注"},
                   {"id": "hp1", "frame": 1, "body": "重复 id 应跳过"}]}})
    assert imp["added"] == 1 and imp["skipped"] == 1, imp

    viewed = _req(api_client, "POST", f"/projects/{pid}/stills/viewed",
                  {"scene": scene, "time": 0.5})
    assert viewed["regions"] >= 1
    again = _req(api_client, "POST", f"/projects/{pid}/stills/viewed",
                 {"sceneId": proj["scenes"][-1], "t": 1.0})
    assert again["regions"] == viewed["regions"] + 1
    vp = json.loads((proj["root"] / "card" / "viewed.json").read_text(encoding="utf-8"))
    assert vp["regions"][-1]["scene"] == proj["scenes"][-1], "sceneId 别名要落成 scene"
    assert vp["regions"][-1]["time"] == 1.0, "t 别名要落成 time"

    # 没有 MP4 产物时包不了：服务层的 409 业务码，证明请求已过模型层
    pkg = api_client.post(f"/projects/{pid}/review/package", json={"videoId": None})
    assert pkg.status_code == 409 and "先跑 E05/F04" in pkg.text, pkg.text


def test_takes_metadata_promote_and_guards(api_client, proj):
    """TakeUpdateIn / RunPromoteIn / TakeBranchIn / AdoptSceneIn。"""
    pid, run = proj["pid"], proj["run_id"]
    other = _req(api_client, "POST", "/runs", {"workflowId": proj["workflow_id"]})["id"]

    t = _req(api_client, "PATCH", f"/projects/{pid}/takes/{run}",
             {"name": "Take 甲", "score": 4, "note": "节奏更好"})
    assert t["name"] == "Take 甲" and t["score"] == 4 and t["note"] == "节奏更好"
    cleared = _req(api_client, "PATCH", f"/projects/{pid}/takes/{run}",
                   {"score": None, "note": ""})
    assert cleared["score"] is None and cleared["note"] == ""
    assert _req(api_client, "PATCH", f"/projects/{pid}/takes/{other}",
                {"hidden": True})["hidden"] is True

    assert _req(api_client, "POST", f"/runs/{run}/promote", {"takeName": "甲版"}) == {"ok": True}
    assert json.loads((proj["root"] / "out" / "CURRENT")
                      .read_text(encoding="utf-8"))["run_id"] == run
    # Take 面的 current 由 takes/promote 决定（RunPromoteIn 只写交付标记文件）
    _req(api_client, "POST", f"/projects/{pid}/takes/{run}/promote", {})
    cur = api_client.patch(f"/projects/{pid}/takes/{run}", json={"hidden": True})
    assert cur.status_code == 409 and "当前 Take 不能删除" in cur.text, cur.text

    # 分支/采纳需要真实 Run 快照（runs/<id>/docs/…）；没出过片时服务层给可解释的码
    branch = api_client.post(f"/projects/{pid}/takes/{run}/branch", json={})
    assert branch.status_code == 409 and "没有可复制的 timeline 快照" in branch.text, branch.text
    adopt = api_client.post(f"/projects/{pid}/takes/{run}/adopt-scene", json={"sceneId": "S99"})
    assert adopt.status_code == 404, adopt.text


def test_qa_fix_and_undo(api_client, isolated_api):
    """QaFixIn / QaUndoIn 的真回路：文案溢出 → 扩场景 → 撤销退得回去。"""
    _base, workspace = isolated_api
    p = _wizard_project(api_client, workspace, "hp-qa", copy=LONG_COPY, duration=4.0)
    pid = p["pid"]
    try:
        issues = _req(api_client, "GET", f"/projects/{pid}/qa", params={"runId": p["run_id"]})
        overflow = [i for i in issues["issues"] if i["category"] == "text_overflow"]
        assert overflow, [i["category"] for i in issues["issues"]]
        target = overflow[0]
        assert target["fixable"] is True, target
        fix = _req(api_client, "POST", f"/projects/{pid}/qa/fix",
                   {"issueId": target["id"], "action": "extend_scene", "payload": {},
                    "runId": p["run_id"]})
        entry = fix["fix"]
        assert entry["result"] == "applied", entry
        assert entry["documentVerified"] is True and entry["requiresRerun"] is True, entry
        assert entry["verified"] is None, f"文档级修复不该自称即时验证：{entry['verified']}"
        assert entry["seq"] == 1 and entry["undoKind"] == "timeline", entry
        undone = _req(api_client, "POST", f"/projects/{pid}/qa/undo", {"fixId": entry["id"]})
        assert undone["fix"]["undone"] is True
        back = [i["id"] for i in undone["qa"]["issues"]]
        assert target["id"] in back, f"撤销后 {target['id']} 必须重新出现：{back}"
        again = api_client.post(f"/projects/{pid}/qa/undo", json={"fixId": entry["id"]})
        assert again.status_code == 409 and "已撤销" in again.text, again.text
    finally:
        api_client.delete(f"/projects/{pid}", params={"confirm": "true"})


def test_preview_models_accept_aliases(api_client, proj):
    """PreviewStillIn / PreviewSegmentIn / PreviewFilmIn：别名与档位字段进得了服务层。
    真出帧由 test_render_smoke.py（真 Chrome）覆盖。"""
    pid, scene = proj["pid"], proj["scenes"][0]
    for body in ({"sceneId": scene, "time": 0.5, "profile": "draft", "watermark": False,
                  "debounce": False},
                 {"scene_id": scene, "profile": "review"}):
        r = api_client.post(f"/projects/{pid}/preview/still", json=body)
        assert r.status_code in (200, 502), r.text[:200]  # 服务层失败也不是 422
    jobs = []
    seg = api_client.post(f"/projects/{pid}/preview/segment",
                          json={"sceneId": scene, "start": 0.0, "end": 0.5,
                                "profile": "draft", "watermark": False})
    assert seg.status_code in (200, 202), seg.text[:200]
    if seg.status_code == 202:
        jobs.append(seg.json()["jobId"])
    film = api_client.post(f"/projects/{pid}/preview/film",
                           json={"profile": "draft", "watermark": False})
    assert film.status_code in (200, 202, 409), film.text[:200]
    if film.status_code in (200, 202):
        jobs.append(film.json()["jobId"])
    for jid in jobs:
        api_client.post(f"/preview/jobs/{jid}/cancel", json={})


def test_delivery_gate_and_ownership(api_client, proj):
    """DeliveryIn 的归属校验 + GateDecideIn 的上游门判定（都在服务层，不是 422）。"""
    pid = proj["pid"]
    run = _req(api_client, "POST", "/runs", {"workflowId": proj["workflow_id"]})["id"]
    bad = api_client.post(f"/projects/{pid}/delivery", json={"runId": run + 10_000})
    assert bad.status_code == 409, bad.text[:300]  # 不归属本项目的 Run 不许交付
    assert bad.json()["detail"]["code"] == "E_DELIVERY_GATE", bad.text[:300]
    assert "不属于项目" in bad.text, bad.text[:300]
    own = api_client.post(f"/projects/{pid}/delivery", json={"runId": run, "profile": "final"})
    # 没出过片的 Run：要么被交付门禁挡住（409），要么排队开工（202）；两种都不是 422
    assert own.status_code in (202, 409), own.text[:300]
    if own.status_code == 202:
        jid = own.json()["jobId"]
        cancel = api_client.post(f"/jobs/{jid}/cancel", json={})
        assert cancel.status_code in (200, 404), cancel.text[:200]
        print(f"delivery job {jid} 已排队（Run 无产物，终局由作业层判定）")
    gate = api_client.post("/gates/D03/decide", json={"run_id": run, "decision": "approved"})
    assert gate.status_code == 400 and "上游" in gate.text, gate.text
