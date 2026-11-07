"""H8 真跑抓到的一类新缺陷：**前置态构造器与请求模型分叉**。

`scripts/_scratch_state.py` 是验收脚本的"自建前置态"，它发出去的每个 body 都要过
B8 之后那套 Pydantic 模型。老写法给 `audio/upload` 的非 voice 传了 `sceneId=None`，
而模型声明的是 `sceneId: str = ""` → 422 ——这条只有真跑到才会露出来（本批 e2e 就是在那里炸的）。

所以这里不测行为、只测**形状**：把构造器给出的 body 直接喂给端点用的模型。
不需要 ffmpeg、不需要起服务，CI 也能跑；一旦有人再往构造器里塞模型不收的值，这里先红。
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2]
ROOT = SERVER.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _scratch_state as ss

from app.api.schemas import AudioLicenseSaveIn, AudioScenePrimaryIn, AudioUploadIn


def test_audio_upload_body_is_model_legal_for_both_kinds():
    """voice 带场景 id、music 带空串——两种都不许是 None。"""
    voice = AudioUploadIn.model_validate(ss.audio_upload_body("voice", "S01", 0, "AAAA"))
    music = AudioUploadIn.model_validate(ss.audio_upload_body("music", "", 2, "AAAA"))
    assert voice.sceneId == "S01" and voice.kind == "voice"
    assert music.sceneId == "" and music.name == "music take 2", music.name
    # 构造器自己不许产出 None（422 的根因就在这）
    assert ss.audio_upload_body("music", "", 2, "AAAA")["sceneId"] == ""


def test_audio_upload_body_rejects_none_like_values_at_the_model():
    """反向：证明这条判据不是空的——把 None 塞回模型必须被拒。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AudioUploadIn.model_validate(ss.audio_upload_body("music", "", 2, "AAAA") | {"sceneId": None})


def test_scene_primary_and_license_bodies_match_models():
    """前置态另外两个 body 同样按模型形状校验（它们和 upload 在同一条链上）。

    `takeId` 是 **manifest 里的字符串 id**（`audio.py` 用 `uuid4().hex[:12]`），不是数据库自增 id：
    `_take()` 用 `t.get("id") == take_id` 比对，所以传数字不只会 422，即使放过去也永远找不到 Take。
    这条断言就是把那个坑写死，省得下一个 builder 再按"id 一定是 int"的直觉写。
    """
    import pytest
    from pydantic import ValidationError

    AudioScenePrimaryIn.model_validate({"sceneId": "S01", "takeId": "1a2b3c4d5e6f"})
    AudioLicenseSaveIn.model_validate({"source": "本地 ffmpeg 合成", "license": "CC0",
                                       "authorized": True, "expires": "2099-12-31"})
    with pytest.raises(ValidationError):
        AudioScenePrimaryIn.model_validate({"sceneId": "S01", "takeId": 7})
    # 清除场景 Take 走的是"空串"，不是 null
    assert AudioScenePrimaryIn.model_validate({"sceneId": "S01", "takeId": ""}).takeId == ""
