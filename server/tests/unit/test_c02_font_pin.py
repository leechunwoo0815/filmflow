"""P2-31：C02 的字体下载必须有 sha 钉。

字体是视觉产出的一部分（黄金基线也绑在它身上），而 C02 会 `curl` 一个 CDN 上的
可变字体；此前只校验"大于 5MB"，上游换文件不会有人发现——渲染照跑，产出悄悄变。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.engine import executors as ex


def _cache_font() -> Path:
    home = Path(os.environ.get("FILMFLOW_PROD_HOME") or (Path.home() / ".filmflow"))
    return home / "cache" / "fonts" / "NotoSansSC[wght].ttf"


def test_download_path_is_pinned():
    src = Path(ex.__file__).read_text(encoding="utf-8")
    assert src.count("NOTO_SANS_SC_SHA256") >= 4, "钉住的摘要要同时用于校验与记录"
    assert "摘要不符" in src, "网络下载路径必须在不符时 fail-closed"
    assert "pinMatches" in src, "报告/产物元数据要留下摘要是否对得上的痕迹"


def test_pin_matches_the_font_on_this_machine():
    font = _cache_font()
    if not font.exists():
        pytest.skip(f"本机没有字体缓存（{font}）：干净机器上 C02 走下载路径，由钉住的摘要把关")
    got = hashlib.sha256(font.read_bytes()).hexdigest()
    assert got == ex.NOTO_SANS_SC_SHA256, (
        f"本机字体与钉住的摘要不符：{got} != {ex.NOTO_SANS_SC_SHA256}；"
        "要么缓存被换过，要么上游改版——核对后再更新常量，别直接改测试")
