"""DAG 核心单元测试：节点表/边表/caps/缓存键/失效传播/锁。对应规格 §3.1 §4.8 §5.2 §5.3。"""
import asyncio

import pytest

from app.engine import caps as caps_mod
from app.engine import edges
from app.engine.cachekey import gate_content_hash, node_cache_key
from app.engine.invalidation import impact_preview, propagate
from app.engine.locks import LockManager
from app.engine.runner import parse_progress_line


def test_46_nodes_and_7_stages():
    assert len(edges.N) == 46
    assert edges.STAGES == list("ABCDEFG")
    assert len(edges.HUMAN_GATES) == 8   # A05 B08 D03 D05 E07 F06 G03 G07
    assert len(edges.AUTO_GATES) == 8    # B07 C01 C03 D04 E06 F03 F05 G06


def test_edge_table_no_cycle_and_full_coverage():
    order = edges.TOPOLOGY
    assert len(order) == 46
    pos = {n: i for i, n in enumerate(order)}
    for f, t, _ty in edges.EDGES:
        assert pos[f] < pos[t], f"边 {f}->{t} 违反拓扑序"


def test_data_descendants_crf_change():
    # 规格 §7.5 基准：改 F04 crf → data 失效 F05/G07；F06 经 trigger 门 stale（见 propagate 测试）
    assert set(edges.data_descendants("F04")) == {"F05", "G07"}
    assert "G06" not in edges.data_descendants("F04")


def test_data_descendants_copy_change_reaches_all():
    d = edges.data_descendants("A01")
    assert {"B01", "B06", "B07", "C01", "D02", "E06", "F02", "G07", "A04", "A02"} <= d
    # B08 是 B07 的 trigger 下游：不进 data 失效集，但会经门 stale 生效
    assert "B08" not in d


def test_g06_not_invalidated_by_f04():
    # 规格 §7.5：G06 只经 order 边依赖 F06，改 crf 不失效
    assert "G06" not in edges.data_descendants("F04")
    assert edges.UPSTREAM["G06"]["F06"] == "order"


def test_edge_table_has_r2_repairs():
    """R2.0 三处边表修复：E04 转场出边、B05 排版进 C05；节点数仍 46。"""
    assert len(edges.N) == 46
    assert len(edges.EDGES) == 93
    assert ("E04", "E05", "data") in edges.EDGES
    assert ("E04", "F02", "data") in edges.EDGES
    assert ("B05", "C05", "data") in edges.EDGES
    assert set(edges.DATA_DOWN["E04"]) == {"E05", "F02"}
    assert edges.UPSTREAM["C05"]["B05"] == "data"
    assert "C05" in edges.data_descendants("B05")
    # 拓扑序仍覆盖 46 节点且无环
    assert len(edges.TOPOLOGY) == 46


def test_gate_trigger_edges_restored():
    # B08/D05 必须有出边（门控规则落点）——from 是上游门，to 是下游节点
    assert ("B08", "C01", "trigger") in edges.EDGES
    assert ("B08", "D01", "trigger") in edges.EDGES
    assert ("D05", "E01", "trigger") in edges.EDGES


def test_caps_initial_and_progression():
    caps = caps_mod.initial_caps()
    assert set(caps) == {"read", "write_plan", "logic_check"}
    # D02 未批准 → 拒绝
    ok, msg = caps_mod.check_allowed("D02", caps)
    assert not ok and "E_PHASE_FORBIDDEN" in msg and "B08" in msg
    # B08 批准 → render_still 解锁
    caps = caps_mod.caps_after_approval(caps, "B08")
    ok, _ = caps_mod.check_allowed("D02", caps)
    assert ok
    # E01（internal, minCap render_still）解锁
    ok, _ = caps_mod.check_allowed("E01", caps)
    assert ok
    # F02 仍拒绝
    ok, msg = caps_mod.check_allowed("F02", caps)
    assert not ok and "E07" in msg
    caps = caps_mod.caps_after_approval(caps, "E07")
    ok, _ = caps_mod.check_allowed("F02", caps)
    assert ok


def test_cache_key_stable_and_sensitive():
    a = node_cache_key("F02", "1.0", {"crf": 17}, {"frames": "aa"}, ["read"])
    b = node_cache_key("F02", "1.0", {"crf": 17}, {"frames": "aa"}, ["read"])
    assert a == b
    c = node_cache_key("F02", "1.0", {"crf": 19}, {"frames": "aa"}, ["read"])
    d = node_cache_key("F02", "1.0", {"crf": 17}, {"frames": "bb"}, ["read"])
    e = node_cache_key("F02", "1.0", {"crf": 17}, {"frames": "aa"}, ["read", "render_video"])
    assert len({a, c, d, e}) == 4
    # params 顺序不影响键
    f = node_cache_key("F02", "1.0", {"crf": 17, "fps": 24}, {"frames": "aa"}, ["read"])
    g = node_cache_key("F02", "1.0", {"fps": 24, "crf": 17}, {"frames": "aa"}, ["read"])
    assert f == g


def test_gate_content_hash_ignores_time_and_author():
    h1 = gate_content_hash("B08", {}, {"task": "x"})
    h2 = gate_content_hash("B08", {}, {"task": "x"})
    assert h1 == h2
    assert gate_content_hash("B08", {}, {"task": "y"}) != h1


def _hashes():
    return {
        "F04": {"F03": "h_f03"},
        "F05": {"F04": "h_f04", "F02": "h_f02", "E06": "h_e06"},
        "F06": {"F05": "h_f05"},
        "G06": {"G05": "h_g05"},
        "G07": {"G06": "h_g06", "F04": "h_f04", "F05": "h_f05", "F06": "h_f06"},
    }


def test_propagate_crf_change_matches_spec():
    params = {"F04": {"crf": 17}}
    hashes = _hashes()
    hashes["F06"] = {"F05": "h_f05_new"}   # F05 重算后的新产物
    gate_hashes = {"F06": gate_content_hash("F06", {}, {"F05": "h_f05_old"}),
                   "G07": gate_content_hash("G07", {}, {"F04": "h_f04_old", "F05": "h_f05_old", "F06": "h_f06_old", "G06": "h_g06"})}
    r = propagate("F04", params, hashes, gate_hashes)
    # data 失效 = F05 与 G07（G06 只经 order 边，永不失效）
    assert r["invalidated"] == ["F05", "G07"]
    # F06 经 trigger 上游 F05 变化 → stale；G07 内容变化 → stale
    assert set(r["stale_gates"]) == {"F06", "G07"}
    assert "G06" not in r["invalidated"]


def test_propagate_copy_change_stales_all_gates():
    hashes = {
        "B01": {"A01": "c1", "A07": "v"}, "B06": {"B01": "b", "A05": "s", "A06": "t"},
        "B07": {"B06": "x"}, "D04": {"B06": "x", "D02": "st", "D03": "v"},
        "E01": {"B06": "x"}, "G02": {"B06": "x"},
        "F05": {"F02": "f"}, "G07": {"F04": "f4", "F05": "f5", "F06": "f6", "G06": "g6"},
    }
    gate_hashes = {g: gate_content_hash(g, {}, hashes.get(g, {})) for g in ["B08", "D05", "E07", "F06", "G07"]}
    h2 = {k: dict(v) for k, v in hashes.items()}
    h2["B01"]["A01"] = "c2"  # 文案变化
    r = propagate("B01", {}, h2, gate_hashes)
    # 门为 data+trigger 上游签字：B08（经 B07）→ 文案变化传导
    assert {"B08", "D05", "E07", "F06", "G07"} <= set(r["stale_gates"])


def test_impact_preview_reports_nodes_and_gates():
    params = {"F04": {"crf": 17}}
    hashes = _hashes()
    gate_hashes = {"F06": gate_content_hash("F06", {}, {"F05": "h_f05"})}
    r = impact_preview("F04", {"crf": 19}, params, hashes, gate_hashes)
    assert r["source"] == "F04"
    assert set(r["invalidated"]) == {"F05", "G07"}
    assert "F06" in r["stale_gates"]   # trigger 上游 F05 将变化 → 门 stale


async def test_lock_manager_serializes_chrome():
    lm = LockManager()
    order: list[str] = []

    async def worker(name):
        await lm.acquire("chrome-queue", name)
        order.append(f"start:{name}")
        await asyncio.sleep(0.05)
        order.append(f"end:{name}")
        lm.release("chrome-queue", name)

    await asyncio.gather(worker("A"), worker("B"))
    # 严格串行：A 的 start/end 必须相邻
    assert order.index("start:A") < order.index("end:A") < order.index("start:B") or \
           order.index("start:B") < order.index("end:B") < order.index("start:A")
    assert lm.stats[0].acquisitions == 2


def test_progress_line_parsing():
    assert parse_progress_line('@@PROGRESS {"pct":0.42,"msg":"frame 400/948"}') == (0.42, "frame 400/948")
    assert parse_progress_line("hello") is None
    assert parse_progress_line('@@PROGRESS {bad json') is None


def test_all_nodes_have_executors():
    from app.engine import executors as ex
    for nid, node in edges.N.items():
        assert node["executor"] in ex.REGISTRY, f"{nid} 的执行器 {node['executor']} 未注册"
