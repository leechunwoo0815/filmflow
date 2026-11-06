"""H10 的防线单测：环境漂移**诊断**（不是门禁）与"重锚理由 ↔ 当时真实指纹互证"。

老板 2026-11-06 选的修法很明确：漂移要看得见、要给出下一步动作，但**不许把整夜循环锁死**。
所以这一族断言分两半，缺一不可：
- 漂移被检出时：打印 `⚠ 漂移` + 可直接照做的 `--update --reason` 命令，**返回码仍是 0**；
- 理由站不住时：`corroborate` 必须点名——而且**代码升版**与**环境变化**是两类声称，各自验各自的。
  这条区分来自真实数据：B3 那条重锚理由写的是 `EXECUTOR 2.17.0 / RENDERER preview-2.1.0`，
  若把它当"环境变了"去要求 Chrome/ffmpeg 有差异，就是把正确行为判成违规（我第一版就写错了）。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
ROOT = SERVER.parent
sys.path.insert(0, str(ROOT / "scripts"))

import diagnose_environment_drift as ded

FULL_ENV = {
    "executorVersion": "2.17.0", "rendererVersion": "preview-2.1.0",
    "chrome": "Google Chrome 156.0.8078.80", "ffmpeg": "ffmpeg version 9.0.2",
    "fontSha256": "a304" + "0" * 60, "styleLibraryStatsSha256": "8902" + "0" * 60,
    "fpscalcSha256": "49a2" + "0" * 60, "os": "Darwin 27.2.0 (arm64)", "python": "3.13.2",
}


def _with(**changes) -> dict:
    cur = dict(FULL_ENV)
    cur.update(changes)
    return cur


# ----------------------------------------------------------- 漂移判定（纯函数三面）

def test_no_drift_when_environment_identical():
    drifted, unknown = ded.diff_environment(dict(FULL_ENV), dict(FULL_ENV))
    assert drifted == [] and unknown == []


def test_drift_detected_per_key():
    cur = _with(chrome="Google Chrome 157.0.0000.00", ffmpeg="ffmpeg version 10.0")
    drifted, unknown = ded.diff_environment(cur, dict(FULL_ENV))
    assert {k for k, _, _ in drifted} == {"chrome", "ffmpeg"}, drifted
    assert unknown == []


def test_missing_key_in_anchor_is_not_drift():
    """历史报告字段比现在少（老报告没记 rendererVersion/fpscalcSha256）→ 记为信息不足，不记为漂移。

    把它当漂移的话，每加一个采集项都会炸出一片假红，然后就会有人去把诊断关掉。
    """
    anchor = {k: v for k, v in FULL_ENV.items() if k not in ("rendererVersion", "fpscalcSha256")}
    drifted, unknown = ded.diff_environment(dict(FULL_ENV), anchor)
    assert drifted == [], drifted
    assert set(unknown) == {"rendererVersion", "fpscalcSha256"}


# ----------------------------------------------------------- 声称分类（语义纠正那一刀）

def test_code_version_reason_is_not_an_environment_claim():
    """真实那条 B3 重锚理由：`EXECUTOR 2.17.0 / RENDERER preview-2.1.0` 属于**代码升版**。"""
    real = json.loads((ROOT / "fixtures/golden/5s/baseline_original/baseline_original.json")
                      .read_text(encoding="utf-8"))
    hist = real.get("updateHistory") or []
    assert hist, "真实重锚记录不见了——这条测试的前提就是它存在"
    reason = str(hist[0].get("reason") or "")
    assert not ded.reason_claims_environment(reason), f"代码改动型理由被误判成环境声称：{reason[:70]}"
    assert ded.reason_claims_code_change(reason), "写了 EXECUTOR/RENDERER 就该算代码声称"


def test_chrome_upgrade_reason_is_an_environment_claim():
    assert ded.reason_claims_environment("Chrome 升级到 157，字形宽度变了，重新打锚")


# ----------------------------------------------------------- 互证（正反双向 + 豁免边界）

def test_corroborate_flags_env_claim_without_evidence():
    history = [{"at": "2026-11-06T06:00:00Z", "reason": "ffmpeg 换版，重打锚点"}]
    seq = [("2026-11-06T05:00:00Z", dict(FULL_ENV)), ("2026-11-06T07:00:00Z", dict(FULL_ENV))]
    problems, unverifiable = ded.corroborate(history, seq)
    assert len(problems) == 1 and "环境项逐项相同" in problems[0], problems
    assert unverifiable == []
    # 正向对照：环境真的变了 → 没问题
    assert ded.corroborate(history, [("2026-11-06T05:00:00Z", dict(FULL_ENV)),
                                     ("2026-11-06T07:00:00Z", _with(ffmpeg="ffmpeg version 10.0"))])[0] == []


def test_corroborate_flags_version_claim_without_version_change():
    history = [{"at": "2026-11-06T06:00:00Z",
                "reason": "文字淡出对齐出转场窗口，EXECUTOR 2.17.0 / RENDERER preview-2.1.0 重锚"}]
    seq = [("2026-11-06T05:00:00Z", dict(FULL_ENV)), ("2026-11-06T07:00:00Z", dict(FULL_ENV))]
    problems, _ = ded.corroborate(history, seq)
    assert len(problems) == 1 and "都没变" in problems[0], problems
    # 正向对照：版本确实升了 → 这条重锚有依据
    assert ded.corroborate(history, [
        ("2026-11-06T05:00:00Z", _with(executorVersion="2.16.0", rendererVersion="preview-2.0.0")),
        ("2026-11-06T07:00:00Z", dict(FULL_ENV))])[0] == []


def test_corroborate_grandfathers_pre_h10_records():
    """H10 之前的历史记录旁边没有对照锚点：进"无法验证"，不判成违规（豁免写进签名，不悄悄放宽）。"""
    history = [{"at": "2026-11-05T19:13:36Z", "reason": "ffmpeg 换版"}]
    problems, unverifiable = ded.corroborate(history, [("2026-11-05T19:13:36Z", dict(FULL_ENV))])
    assert problems == [], problems
    assert len(unverifiable) == 1 and "不足以对照" in unverifiable[0]


def test_corroborate_reports_insufficient_sequence_after_cutoff():
    """过了 `strict_from` 还没有对照锚点的就是问题——豁免不往后开。"""
    history = [{"at": "2026-11-06T06:00:00Z", "reason": "ffmpeg 换版"}]
    problems, unverifiable = ded.corroborate(history, [("2026-11-06T06:00:00Z", dict(FULL_ENV))])
    assert len(problems) == 1 and "不足以对照" in problems[0], problems
    assert unverifiable == []


def test_corroborate_on_real_records_is_not_a_false_positive():
    """拿真实 updateHistory 跑互证：不许有"问题"级结果（那条记录早于 H10，属无法验证）。"""
    real = json.loads((ROOT / "fixtures/golden/5s/baseline_original/baseline_original.json")
                      .read_text(encoding="utf-8"))
    hist = real.get("updateHistory") or []
    claims = [h for h in hist
              if ded.reason_claims_environment(str(h.get("reason") or ""))
              or ded.reason_claims_code_change(str(h.get("reason") or ""))]
    seq = [(str(h.get("at")), h.get("environment") or {}) for h in hist]
    problems, unverifiable = ded.corroborate(claims, seq)
    assert problems == [], problems
    assert len(unverifiable) == len(claims), (unverifiable, claims)


# ----------------------------------------------------------- 真跑 main()（正反两个现场）

def _newest_name(dst: Path) -> str:
    idx = json.loads((dst / "index.json").read_text(encoding="utf-8"))
    return max(idx["items"], key=lambda i: str(i.get("at") or ""))["reportFile"]


@pytest.fixture()
def tampered_reports(tmp_path, monkeypatch):
    """把真实报告目录拷进 tmp 并改掉 chrome/ffmpeg——用真脚本代码路径跑漂移，不只测纯函数。"""
    dst = tmp_path / "golden"
    shutil.copytree(ROOT / "docs/reports/golden", dst)
    monkeypatch.setattr(ded, "REPORT_DIR", dst)
    monkeypatch.setattr(ded, "INDEX", dst / "index.json")
    name = _newest_name(dst)
    rep = dst / name
    data = json.loads(rep.read_text(encoding="utf-8"))
    data["environment"]["chrome"] = "Google Chrome 999.0.0000.00 (演练篡改)"
    data["environment"]["ffmpeg"] = "ffmpeg version 999.0.2 (演练篡改)"
    rep.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return dst, name


def test_main_reports_drift_and_still_exits_zero(tampered_reports, monkeypatch, capsys):
    """判据：检出漂移 → 打印 `⚠ 漂移` + 重锚命令，**但 exit 0**（老板选的口径，不许改成门禁）。"""
    monkeypatch.setattr(ded, "current_environment", lambda: dict(FULL_ENV))
    monkeypatch.setattr(sys, "argv", ["diagnose_environment_drift.py", "--project", "5s"])
    assert ded.main() == 0
    out = capsys.readouterr().out
    assert "⚠ 漂移 chrome" in out, out
    assert "⚠ 漂移 ffmpeg" in out, out
    assert "--update --reason" in out, "漂移输出必须自带下一步动作，否则等于只说一句『环境不一样』"
    assert "不是门禁" in out, "要写明为什么不返回非零，否则下一个人会顺手把它改成 fail-closed"


def test_main_after_restore_reports_consistency(tampered_reports, monkeypatch, capsys):
    """反向现场：锚点没被改时同一个脚本必须打印一致，且不出现漂移段。"""
    dst, name = tampered_reports
    real = json.loads((ROOT / "docs/reports/golden" / name).read_text(encoding="utf-8"))
    (dst / name).write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
    anchor = dict(real.get("environment") or {})
    monkeypatch.setattr(ded, "current_environment", lambda: {k: anchor.get(k) for k in ded.ENV_KEYS})
    monkeypatch.setattr(sys, "argv", ["diagnose_environment_drift.py", "--project", "5s"])
    assert ded.main() == 0
    out = capsys.readouterr().out
    assert "⚠ 漂移" not in out, out
    assert "✓ chrome" in out, out


def test_docs_guard_prints_diagnosis_but_does_not_gate():
    """文档守卫里的诊断段**不许影响返回值**——这是"漂移即诊断"最容易失守的地方。"""
    src = (ROOT / "scripts" / "check_docs_consistency.py").read_text(encoding="utf-8")
    assert "diagnose_environment_drift" in src, "守卫里必须真的调用诊断"
    seg = src[src.index("H10：环境漂移"):src.index("if problems:")]
    assert "return 1" not in seg and "return 0" not in seg, "诊断段里出现 return——那会把诊断变成门禁"
