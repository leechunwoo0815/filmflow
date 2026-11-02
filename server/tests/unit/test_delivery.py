"""FR-28：SRT 换行/时间码/QC 辅助。"""
from app.services.delivery import _srt, _ts, _wrap


def test_wrap_respects_fullwidth_limit():
    text = "风从纸上起，慢慢穿过整条街。"
    lines = _wrap(text, 8).splitlines()
    assert lines and all(len(x) <= 8 for x in lines)
    assert "".join(lines) == text


def test_srt_format_and_metrics():
    text, meta = _srt([{"text": "风从纸上起。", "start": 0, "end": 2.24},
                       {"text": "纸不动，风先动。", "start": 2.24, "end": 5.0}])
    assert "00:00:00,000 --> 00:00:02,240" in text
    assert "00:00:02,240 --> 00:00:05,000" in text
    assert meta["count"] == 2 and meta["maxLineChars"] <= 16
    assert meta["maxCharsPerSec"] <= 9


def test_timestamp_rounding():
    assert _ts(65.5) == "00:01:05,500"
