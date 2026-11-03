"""失效传播（data 边 BFS）与 impact dry-run（tech-plan §9.2）。

纯逻辑模块：不直接查库，通过哈希/门状态注入，便于单元测试与 dry-run。
门的内容哈希覆盖 data+trigger 上游（B08 要为 B07 校验过的任务卡签字）。
"""
from __future__ import annotations

from .cachekey import gate_content_hash
from .edges import EDGES, UPSTREAM, N, data_descendants


def propagate(node_id: str, params_by_node: dict[str, dict],
              input_hashes_by_node: dict[str, dict[str, str]],
              current_gate_hashes: dict[str, str]) -> dict:
    """节点内容变化后的失效计算。

    返回 {
      invalidated: [nodeId…]        # data 下游全部（含人门节点的 data 路径）
      stale_gates: [gateId…]        # content_hash 变化（或上游将变化）的人工门
      blocked_downstream: [nodeId…] # stale 门引起的调度阻塞下游
    }
    """
    invalidated = data_descendants(node_id)
    stale: list[str] = []
    blocked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for gid, node in N.items():
            if node["gate"] != "human" or gid in stale:
                continue
            old = current_gate_hashes.get(gid)
            if old is None:
                continue  # 从未批准的门只是 blocked，谈不上 stale
            new_hash = gate_content_hash(gid, params_by_node.get(gid, {}),
                                         input_hashes_by_node.get(gid, {}))
            upstream_will_change = any(
                up in invalidated or up in blocked
                for up, ty in UPSTREAM[gid].items() if ty in ("data", "trigger")
            )
            if old != new_hash or upstream_will_change:
                stale.append(gid)
                blocked.add(gid)
                changed = True
        for f, t, _ty in EDGES:
            if f in blocked and t not in blocked:
                blocked.add(t)
                changed = True
    return {
        "invalidated": sorted(invalidated),
        "stale_gates": sorted(stale),
        "blocked_downstream": sorted(blocked - invalidated - {node_id}),
    }


def impact_preview(node_id: str, patch_params: dict | None,
                   params_by_node: dict[str, dict],
                   input_hashes_by_node: dict[str, dict[str, str]],
                   current_gate_hashes: dict[str, str],
                   assume_input_change: bool = True) -> dict:
    """GET /api/runs/:id/impact —— 不落库的失效预估。

    assume_input_change=True 表示上游产物将变化（默认）。
    """
    params = dict(params_by_node.get(node_id, {}))
    if patch_params:
        params.update(patch_params)
    p2 = dict(params_by_node)
    p2[node_id] = params
    h2 = {k: dict(v) for k, v in input_hashes_by_node.items()}
    if assume_input_change:
        for up, ty in UPSTREAM[node_id].items():
            if ty == "data":
                h2.setdefault(node_id, {})[up] = "*" + h2.get(node_id, {}).get(up, "")
    result = propagate(node_id, p2, h2, current_gate_hashes)
    result["source"] = node_id
    return result
