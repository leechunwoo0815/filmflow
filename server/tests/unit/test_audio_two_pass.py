"""B2/P2-12：两遍 loudnorm 的测量解析与回灌、f04 bt709 色彩标签。

修复前：单遍 loudnorm（-13.8 vs 目标 -14.0 偏差 ~0.2 LU）、成片无色彩标签。
"""
from __future__ import annotations

import math

from app.engine.executors.pipeline import _mix_filter
from app.services import audio as audio_svc

_STDERR = [
    "[Parsed_loudnorm_6 @ 0x7f8]",
    "{",
    "\t\"input_i\" : \"-13.82\",",
    "\t\"input_tp\" : \"-1.20\",",
    "\t\"input_lra\" : \"5.10\",",
    "\t\"input_thresh\" : \"-24.97\",",
    "\t\"output_i\" : \"-15.90\",",
    "\t\"output_tp\" : \"-1.51\",",
    "\t\"output_lra\" : \"4.90\",",
    "\t\"output_thresh\" : \"-26.90\",",
    "\t\"normalization_type\" : \"dynamic\",",
    "\t\"target_offset\" : \"0.15\"",
    "}",
    "size=N/A time=00:00:04.00",
]


def test_parse_loudnorm_extracts_measured_block():
    m = audio_svc.parse_loudnorm(_STDERR)
    assert m is not None
    assert math.isclose(m["input_i"], -13.82)
    assert math.isclose(m["target_offset"], 0.15)


def test_parse_loudnorm_rejects_silence_and_garbage():
    assert audio_svc.parse_loudnorm(["no json here"]) is None
    silent = [l.replace("-13.82", "-inf") for l in _STDERR]
    assert audio_svc.parse_loudnorm(silent) is None, "全静音 -inf 必须回退单遍，不许进第二遍"


def test_measured_loudnorm_linear_second_pass():
    m = audio_svc.parse_loudnorm(_STDERR)
    s = audio_svc.measured_loudnorm(-14.0, m)
    assert "I=-14.0" in s and "linear=true" in s
    assert "measured_I=-13.82" in s and "offset=0.15" in s


def test_processing_filter_two_pass_forms():
    measure = audio_svc.processing_filter({"normalize": True})
    assert "print_format=json" in measure, "第一遍必须带 print_format=json"
    second = audio_svc.processing_filter(
        {"normalize": True},
        {"input_i": -13.82, "input_tp": -1.2, "input_lra": 5.1,
         "input_thresh": -24.97, "target_offset": 0.15})
    assert "linear=true" in second and "print_format" not in second
    off = audio_svc.processing_filter({"highpass": True})
    assert "loudnorm" not in off


def test_mix_filter_measured_second_pass():
    m = {"input_i": -13.82, "input_tp": -1.2, "input_lra": 5.1,
         "input_thresh": -24.97, "target_offset": 0.15}
    first = _mix_filter(4.0, measured=None)
    second = _mix_filter(4.0, measured=m)
    assert "print_format=json" in first and "linear=true" not in first
    assert "linear=true" in second and "measured_I=-13.82" in second
