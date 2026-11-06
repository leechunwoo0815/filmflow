"""H5：黄金证据 churn 策略的判据单测（裁剪在 tmp 里跑，**绝不碰真实报告目录**）。

这一族测试防的是三件事，每件都对应一次真实风险：
1. 裁剪逻辑把"最新 N 份"理解反（按 mtime 升序 → 留下最旧的、裁掉最新的，等于销毁当期证据）；
2. 被裁的报告**没有留下哈希**（消失的证据无法自证曾经存在，复审时就只有一句"没了"）；
3. 有人为了 CI 变绿去动 `fixtures/golden/*/baseline_original/`（那是回归锚本身）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
ROOT = SERVER.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cleanup_golden_reports as cgr


def _fake_tree(tmp: Path, n: int = 6) -> tuple[Path, Path, Path]:
    reports = tmp / "docs/reports/golden"
    reports.mkdir(parents=True)
    items = []
    for i in range(n):
        name = f"5s-original-run{300 + i}.json"
        # 时间戳故意做成"数字越大越新"，与文件名顺序一致，方便验证排序方向
        (reports / name).write_text(json.dumps({"runId": 300 + i}), encoding="utf-8")
        items.append({"project": "5s", "resolution": "original", "runId": 300 + i,
                      "at": f"2026-11-0{i % 6 + 1}T00:00:0{i}Z", "reportFile": name})
    (reports / "index.json").write_text(
        json.dumps({"schema": cgr.SCHEMA, "items": items, "pruned": []}), encoding="utf-8")
    return reports, reports / "index.json", tmp / ".trash/golden-reports"


@pytest.fixture()
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(cgr, "ROOT", tmp_path)
    monkeypatch.setattr(cgr, "REPORT_DIR", tmp_path / "docs/reports/golden")
    monkeypatch.setattr(cgr, "INDEX", tmp_path / "docs/reports/golden/index.json")
    monkeypatch.setattr(cgr, "TRASH", tmp_path / ".trash/golden-reports")
    return tmp_path


def test_prune_keeps_newest_and_records_hashes(patched):
    tmp_root = patched
    """反向验证的核心：留最新 keep 份，其余移动到 .trash 并在 index.pruned 里留 sha256。"""
    reports, index, trash = _fake_tree(patched, n=6)
    keep, doomed = cgr.plan(3)
    assert len(keep) == 3 and len(doomed) == 3, (keep, doomed)
    # 排序方向必须对：被裁的是 run300/301/302（旧的），留下 run303..305（新的）
    assert sorted(p.stem.split("run")[1] for p in doomed) == ["300", "301", "302"], doomed
    assert sorted(p.stem.split("run")[1] for p in keep) == ["303", "304", "305"], keep

    assert _main_apply(keep=3, reason="单测演练") == 0
    remaining = sorted(p.name for p in reports.glob("5s-original-run*.json"))
    assert remaining == ["5s-original-run303.json", "5s-original-run304.json", "5s-original-run305.json"], remaining
    moved = sorted(trash.glob("*.json"))
    assert len(moved) == 3, moved
    idx = json.loads(index.read_text(encoding="utf-8"))
    assert len(idx["pruned"]) == 3
    for e in idx["pruned"]:
        assert len(e["sha256"]) == 64, e
        assert e["reason"] == "单测演练"
        src = Path(tmp_root) / e["movedTo"]
        assert hashlib.sha256(src.read_bytes()).hexdigest() == e["sha256"], "哈希必须对得上被裁的字节"


def test_prune_is_idempotent_and_untouchable_when_under_limit(patched):
    """第二次跑没有新东西可裁；未超保留数时**一份都不动**（幂等，防止反复搬运改时间戳）。"""
    reports, _index, trash = _fake_tree(patched, n=3)
    before = sorted(p.name for p in reports.glob("*.json"))
    _keep, doomed = cgr.plan(20)
    assert doomed == []
    assert _main_apply(keep=20) == 0
    assert sorted(p.name for p in reports.glob("*.json")) == before
    assert not trash.exists()


def test_keep_floor_is_enforced(patched):
    """`--keep 0` 必须被拒：证据台账不许被裁空。"""
    _fake_tree(patched, n=4)
    sys.argv = ["cleanup_golden_reports.py", "--keep", "0", "--apply"]
    with pytest.raises(SystemExit, match="至少为 1"):
        cgr.main()


def test_anchors_are_never_in_scope(tmp_path):
    """裁剪面只有 `docs/reports/golden/*.json`；回归锚 PNG 与 spec.json 不在任何路径里。"""
    files = [p.name for p in _real_report_files()]
    assert all(f.endswith(".json") for f in files)
    anchors = list((ROOT / "fixtures/golden").glob("*/baseline_original/*.png"))
    assert anchors, "回归锚本身不见了——这条断言的意义就是拦住那一次"
    for d in (ROOT / "fixtures/golden").glob("*/baseline_original"):
        assert len(list(d.glob("*.png"))) >= 6, d
    assert (ROOT / "fixtures/golden/README.md").is_file(), "整批替换的理由必须写在锚点目录旁边"


def _real_report_files():
    return [p for p in (ROOT / "docs/reports/golden").glob("*.json") if p.name != "index.json"]


def _main_apply(keep: int, reason: str = "") -> int:
    argv = ["cleanup_golden_reports.py", "--keep", str(keep), "--apply"]
    if reason:
        argv += ["--reason", reason]
    sys.argv = argv
    return cgr.main()


def test_governance_item_19_is_wired():
    """第 19 项必须真实存在并复用同一份判据（不是文档里的口头承诺）。"""
    src = (ROOT / "scripts" / "verify_p1_governance.py").read_text(encoding="utf-8")
    assert 'ok("19 黄金证据 churn 策略"' in src, "第 19 项的 ok() 标签丢了——守卫数步数会退回 18"
    assert "check_golden_churn()" in src, "第 19 项没有接进 main()"
    assert "from cleanup_golden_reports import" in src, "第 19 项必须复用脚本里的同一份判据"
