"""判官 §六 #9：验收脚手架的"演示污染"判据必须能在 pytest 里回归。

这些测试**不打 API、不写库**——它们审的是脚本本身：
1. 任何 scripts/*.py 里出现演示项目 id 就失败；
2. 会写项目状态的脚本必须有自建入口；
3. `require_scratch_project()` 对缺参/演示 id/不存在 id 三种情况都必须拒绝（fail-closed）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

from _acceptance import (
    DEMO_PROJECTS,
    POLLUTION_EXEMPT,
    audit_script_pollution,
    require_scratch_project,
)


class _Resp:
    def __init__(self, items):
        self._items = items

    def json(self):
        return {"items": self._items}


class _StubClient:
    """只模拟 /projects 列表；闸门不应该发别的请求，发了就说明判据写错了。"""

    def __init__(self, items):
        self._items = items

    def get(self, path, params=None):
        assert path == "/projects", f"闸门不该请求 {path}（没有 GET /projects/{{id}} 路由）"
        return _Resp(self._items)


def test_no_demo_project_literals_left_in_scripts():
    demo_lines, _unguarded = audit_script_pollution(ROOT / "scripts")
    assert not demo_lines, f"验收脚本又写回演示项目了：{demo_lines}"


def test_state_writing_scripts_have_selfbuild_entry():
    _demo_lines, unguarded = audit_script_pollution(ROOT / "scripts")
    assert not unguarded, f"这些脚本会写状态但没有自建入口：{unguarded}"


def test_exempt_list_is_small_and_named():
    """豁免是显式登记的：新增必须同时在这里写理由，否则这项测试会红。"""
    assert POLLUTION_EXEMPT == {
        "cleanup_projects.py",              # 清理工具本身
        "verify_rumor_regression.py",       # 参考片回归
        "drive_run.py",                     # 运维驱动器（参数指定项目）
        "probe_profile_ssim_offset.py",     # 只读探针
        "smoke_m1.py",                      # 导入 rumor-39s 证明 46 节点画布
    }


def test_guard_refuses_without_project_flag():
    with pytest.raises(SystemExit) as e:
        require_scratch_project(_StubClient([]), "e2e_demo.py", [])
    assert "用法" in str(e.value)


@pytest.mark.parametrize("demo_id", sorted(DEMO_PROJECTS))
def test_guard_refuses_every_demo_project(demo_id):
    items = [{"id": demo_id, "name": DEMO_PROJECTS[demo_id]}]
    with pytest.raises(SystemExit) as e:
        require_scratch_project(_StubClient(items), "e2e_demo.py", ["--project", str(demo_id)])
    assert "拒绝" in str(e.value)


def test_guard_refuses_unknown_id_and_accepts_scratch():
    with pytest.raises(SystemExit) as e:
        require_scratch_project(_StubClient([]), "e2e_demo.py", ["--project", "999999"])
    assert "不在" in str(e.value)

    items = [{"id": 777, "name": "scratch-thing"}]
    got = require_scratch_project(_StubClient(items), "e2e_demo.py", ["--project=777"])
    assert got == 777


def test_guard_refuses_protected_names_even_with_new_id():
    """保护名单按名字判：换个 id 但名字是 rumor 前缀也照样拒（删除面同一套规则）。"""
    items = [{"id": 778, "name": "rumor-39s-clone"}]
    with pytest.raises(SystemExit) as e:
        require_scratch_project(_StubClient(items), "e2e_demo.py", ["--project", "778"])
    assert "拒绝" in str(e.value)
