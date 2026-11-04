"""P1-23 第三批：31 个 `payload: dict` 端点全部模型化后的入口校验（判官 §三-10）。

约定同第一批：这些请求**必然在 422 被挡在 handler 之前**，所以用 TestClient
（连的是 conftest 隔离的临时库）不会写脏任何数据；真正写状态的 happy-path
放在 `tests/integration/test_write_api_happy_paths.py`，那里走真 uvicorn + 独立工作区。
"""
from __future__ import annotations

import inspect
import sys
import typing
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from app.api.routes import router
from app.api.schemas import _AUDIO_B64_MAX
from app.errors import ErrorCode
from app.main import app
from app.services import audio as audio_svc

HEADERS = {"Origin": "http://127.0.0.1:3000"}
UNKNOWN = 999_999  # 不存在的 id：模型过关后由路由层给 404，正好用来证明「没被 422 挡住」


def client():
    from fastapi.testclient import TestClient
    return TestClient(app, base_url="http://127.0.0.1")


def _model_member(ann) -> bool:
    """注解是 BaseModel，或 `Model | None`（可选体）。"""
    if isinstance(ann, type):
        return issubclass(ann, BaseModel)
    return any(isinstance(a, type) and issubclass(a, BaseModel)
               for a in typing.get_args(ann))


def test_no_write_endpoint_takes_a_bare_dict():
    """守卫：任何 POST/PUT/PATCH 的请求体必须是 Pydantic 模型（判官 P1-23 的机检版）。

    反射而不是 grep：改名、退回 `dict`、把模型换成 TypedDict 都拦得住。
    """
    offenders = []
    modelled = 0
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if not set(route.methods) & {"POST", "PUT", "PATCH"}:
            continue
        hints = typing.get_type_hints(route.endpoint)
        for name, param in inspect.signature(route.endpoint).parameters.items():
            ann = hints.get(name, param.annotation)
            if name not in ("payload", "body"):
                continue
            modelled += 1
            if not _model_member(ann):
                offenders.append(f"{sorted(route.methods)} {route.path} → {name}: {ann}")
    assert not offenders, f"仍有未模型化的写端点：{offenders}"
    # 判官点名的 51 个（20 已有 + 31 补上）；少了说明有人把模型又退回 dict
    assert modelled >= 51, f"模型化端点数回落到 {modelled}"


def test_422_uses_api_error_envelope_for_batch3():
    with client() as c:
        r = c.post("/api/runs", json={"workflowId": "abc"}, headers=HEADERS)
        assert r.status_code == 422, r.text
        d = r.json()["detail"]
        assert d["code"] == ErrorCode.E_VALIDATION, d
        assert "workflowId" in d["message"], d
        assert d["details"]["errors"][0]["type"] == "int_parsing", d


def test_project_import_requires_root_and_typed_name():
    with client() as c:
        assert c.post("/api/projects/import", json={}, headers=HEADERS).status_code == 422
        assert c.post("/api/projects/import", json={"root": ""},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/import", json={"root": 1},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/import", json={"root": "/tmp", "name": 3},
                      headers=HEADERS).status_code == 422


def test_drafts_step_is_bounded_integer():
    with client() as c:
        for body in ({"name": "x", "step": 0}, {"name": "x", "step": 6},
                     {"name": "x", "step": "abc"}, {"name": "x", "payload": []}):
            assert c.post("/api/drafts", json=body, headers=HEADERS).status_code == 422, body
        assert c.patch("/api/drafts/1", json={"payload": "不是对象"},
                       headers=HEADERS).status_code == 422
        # 合法但草稿不存在 → 404，证明 step/payload 的边界没误伤
        assert c.patch(f"/api/drafts/{UNKNOWN}", json={"step": 3},
                       headers=HEADERS).status_code == 404


def test_template_endpoints_require_template_id():
    with client() as c:
        assert c.post("/api/projects/1/timeline/scene-template", json={},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/timeline/scene-template", json={"templateId": ""},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/template-upgrade",
                      json={"templateId": "saved:1", "confirm": "maybe"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/from-template", json={"name": "没有模板"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/series/from-template", json={"templateId": "saved:1", "items": "abc"},
                      headers=HEADERS).status_code == 422
        # 版本端点必须给 projectId（老代码缺失时落到 0，只在服务层报「项目不存在」）
        assert c.post("/api/templates/saved:1/version", json={"copy": "x"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/templates/saved:1/version", json={"projectId": 0},
                      headers=HEADERS).status_code == 422


def test_template_save_copy_is_length_bounded():
    with client() as c:
        r = c.post("/api/projects/1/save-template", json={"copy": "字" * 20001},
                   headers=HEADERS)
        assert r.status_code == 422, r.status_code
        assert r.json()["detail"]["code"] == ErrorCode.E_VALIDATION
        assert "string_too_long" in r.text, r.text


def test_orchestration_endpoints_require_numeric_ids():
    with client() as c:
        assert c.post("/api/workflows", json={"graph": {}}, headers=HEADERS).status_code == 422
        assert c.post("/api/runs", json={}, headers=HEADERS).status_code == 422
        assert c.post("/api/runs", json={"workflowId": 0}, headers=HEADERS).status_code == 422
        assert c.post("/api/runs", json={"workflowId": "abc"}, headers=HEADERS).status_code == 422
        assert c.put("/api/workflows/1", json={"graph": []}, headers=HEADERS).status_code == 422
        # 类型过关后：workflow/project 不存在都由路由层给 404（不再 KeyError → 500）
        assert c.post("/api/runs", json={"workflowId": UNKNOWN},
                      headers=HEADERS).status_code == 404
        assert c.post("/api/workflows", json={"projectId": UNKNOWN},
                      headers=HEADERS).status_code == 404


def test_audio_upload_checks_kind_length_and_size():
    """判官点名的那条：落盘前必须有大小/类型闸门。"""
    with client() as c:
        assert c.post("/api/projects/1/audio/upload", json={"filename": "a.wav"},
                      headers=HEADERS).status_code == 422  # data 必填
        assert c.post("/api/projects/1/audio/upload",
                      json={"filename": "a.wav", "data": "AAAA", "kind": "sine"},
                      headers=HEADERS).status_code == 422  # kind 枚举
        assert c.post("/api/projects/1/audio/upload",
                      json={"filename": "", "data": "AAAA"}, headers=HEADERS).status_code == 422
        over = "A" * (_AUDIO_B64_MAX + 1)
        r = c.post("/api/projects/1/audio/upload",
                   json={"filename": "big.wav", "data": over}, headers=HEADERS)
        assert r.status_code == 422, r.status_code
        assert "string_too_long" in r.text, r.text


def test_audio_b64_bound_tracks_service_max_bytes():
    """入口上限与服务层落盘上限必须同源，否则改一边会悄悄失真。"""
    expected = 4 * (audio_svc.MAX_BYTES // 3)
    assert _AUDIO_B64_MAX >= expected, (_AUDIO_B64_MAX, expected)
    assert _AUDIO_B64_MAX < expected + 8192


def test_audio_write_endpoints_require_ids():
    with client() as c:
        assert c.post("/api/projects/1/audio/primary", json={}, headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/audio/primary", json={"takeId": ""},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/audio/scene-primary", json={"takeId": "t"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/audio/markers", json={"markers": ["不是对象"]},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/audio/markers", json={"markers": "all"},
                      headers=HEADERS).status_code == 422


def test_audio_process_options_are_typed_booleans():
    with client() as c:
        assert c.post("/api/projects/1/audio/takes/t1/process", json={"denoise": "maybe"},
                      headers=HEADERS).status_code == 422
        # 未声明的处理键不再被静默忽略
        assert c.post("/api/projects/1/audio/takes/t1/process", json={"pitch": True},
                      headers=HEADERS).status_code == 422


def test_audio_process_model_forbids_unknown_keys():
    """`extra="forbid"`：拼错的效果键不再静默失效（老 dict 版本会连同未知键一起吞掉）。"""
    from app.api.schemas import AudioProcessIn

    with pytest.raises(ValidationError):
        AudioProcessIn.model_validate({"pitch": True})
    assert AudioProcessIn.model_validate({}).model_dump() == {
        "highpass": False, "denoise": False, "deesser": False,
        "eq": False, "trim": False, "normalize": False}


def test_review_endpoints_validate():
    with client() as c:
        assert c.post("/api/projects/1/review/comments", json={"frame": -1},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/review/comments", json={"time": "12点"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/review/comments",
                      json={"body": "字" * 4001}, headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/review/decisions", json={},
                      headers=HEADERS).status_code == 422
        assert c.patch("/api/projects/1/review/comments/x", json={"reply": 5},
                       headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/review/package", json={"videoId": 0},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/review/import", json={"review": "文本"},
                      headers=HEADERS).status_code == 422


def test_stills_viewed_and_font_check_types():
    with client() as c:
        assert c.post("/api/projects/1/stills/viewed", json={"scene": 12},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/stills/viewed", json={"scene": "S01", "time": "快"},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/assets/1/font-check", json={"text": 5},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/assets/1/font-check", json={"text": "字" * 20001},
                      headers=HEADERS).status_code == 422


def test_take_endpoints_validate():
    with client() as c:
        assert c.patch("/api/projects/1/takes/2", json={"score": "很高"},
                       headers=HEADERS).status_code == 422
        assert c.patch("/api/projects/1/takes/2", json={"hidden": "maybe"},
                       headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/takes/2/adopt-scene", json={},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/takes/2/adopt-scene", json={"sceneId": ""},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/projects/1/takes/2/branch", json={"author": 7},
                      headers=HEADERS).status_code == 422


def test_timeline_rebuild_accepts_empty_body():
    """`base_version` 用 None 区分「没传」，省略体仍然合法（老代码回退当前版本）。"""
    with client() as c:
        for body in ({}, {"base_version": None}, {"author": "editor"}):
            r = c.post(f"/api/projects/{UNKNOWN}/docs/timeline/rebuild", json=body,
                       headers=HEADERS)
            assert r.status_code == 404, (body, r.status_code)
        assert c.post(f"/api/projects/{UNKNOWN}/docs/timeline/rebuild",
                      json={"base_version": "v1"}, headers=HEADERS).status_code == 422


def test_label_submit_typed_fields():
    with client() as c:
        assert c.post("/api/labels/NOPE", json={"family": 5}, headers=HEADERS).status_code == 422
        assert c.post("/api/labels/NOPE", json={"labeled": "maybe"},
                      headers=HEADERS).status_code == 422
        # token 会进着色器：非 hex 调色 / 非数值 screen 必须在入口被拒（历史上是预览 500）
        bad = c.post("/api/labels/NOPE", json={"palette": ["高对比"]}, headers=HEADERS)
        assert bad.status_code == 422, bad.text
        assert "十六进制" in bad.text, bad.text
        assert c.post("/api/labels/NOPE", json={"screen": {"angle": "斜"}},
                      headers=HEADERS).status_code == 422
        assert c.post("/api/labels/NOPE", json={"palette": ["#FFF", "#3D5588"]},
                      headers=HEADERS).status_code == 404
        # 类型过关后：风格不存在是 404，不是 422
        assert c.post("/api/labels/NOPE", json={"texture": ["丝网"]},
                      headers=HEADERS).status_code == 404


def test_models_preserve_patch_presence_and_alias_keys():
    """PATCH 语义与别名校验：模型化不能改键存在性，也不能改前端的线上传输键名。"""
    from app.api.schemas import (
        DraftPatchIn,
        FromTemplateIn,
        ReviewCommentPatchIn,
        TakeUpdateIn,
        TemplateSaveIn,
        TemplateVersionIn,
    )

    assert TakeUpdateIn.model_validate({"score": None}).model_dump(exclude_unset=True) \
        == {"score": None}
    assert set(ReviewCommentPatchIn.model_validate({"status": "open"})
               .model_dump(exclude_unset=True)) == {"status"}
    assert DraftPatchIn.model_validate({}).model_dump(exclude_unset=True) == {}
    # 线上键名仍是 copy（前端与验收脚本都不用改），内部叫 copy_text 只为避开 BaseModel.copy
    assert TemplateSaveIn.model_validate({"copy": "第一句"}).copy_text == "第一句"
    assert TemplateVersionIn.model_validate({"projectId": 1, "copy": "x"}).copy_text == "x"
    assert FromTemplateIn.model_validate({"templateId": "saved:1", "copy": "y"}).copy_text == "y"
    for model in (TemplateSaveIn, TemplateVersionIn, FromTemplateIn):
        assert model.model_fields["copy_text"].alias == "copy"
