"""能力（caps）机制 —— 规格 §3.1。Run 从初始集开始，随门批准单调递增。"""
from __future__ import annotations

from .edges import SKILL_ACTIONS, N

INIT_CAPS = ["read", "write_plan", "logic_check"]

# 门批准授予的能力（规格 §3.1）
GATE_GRANTS: dict[str, list[str]] = {
    "B08": ["render_still"],
    "E07": ["render_video", "analyze_audio", "generate_local_music"],
}


def initial_caps() -> list[str]:
    return list(INIT_CAPS)


def caps_after_approval(caps: list[str], gate_id: str) -> list[str]:
    out = list(caps)
    for g in GATE_GRANTS.get(gate_id, []):
        if g not in out:
            out.append(g)
    return out


def check_allowed(node_id: str, caps: list[str]) -> tuple[bool, str]:
    """执行前校验。返回 (ok, 拒绝原因)。规格 §3.1：auth∈7 需 caps 含该动作；internal 需 caps ⊇ minCap。"""
    node = N[node_id]
    caps_set = set(caps)
    auth = node["auth"]
    if auth in SKILL_ACTIONS:
        if auth not in caps_set:
            blockers = [g for g, grants in GATE_GRANTS.items() if auth in grants]
            hint = f"等待 {'/'.join(blockers)} 批准" if blockers else "能力不足"
            return False, f"E_PHASE_FORBIDDEN: 需要 {auth}（{hint}）"
        return True, ""
    min_cap = node["minCap"]
    missing = [c for c in min_cap if c not in caps_set]
    if missing:
        blockers = [g for g, grants in GATE_GRANTS.items() if any(m in grants for m in missing)]
        hint = f"等待 {'/'.join(blockers)} 批准" if blockers else "能力不足"
        return False, f"E_PHASE_FORBIDDEN: internal 节点缺能力 {missing}（{hint}）"
    return True, ""
