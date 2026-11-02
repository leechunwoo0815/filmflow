"""46 节点注册表与唯一权威边表（翻译规格 §4.1–4.8 与 tech-plan §9.1）。

本文件是 DAG 的唯一定义处；禁止在其他模块复制连线关系。
"""
from __future__ import annotations

STAGES = ["A", "B", "C", "D", "E", "F", "G"]
STAGE_TITLES = {"A": "立项", "B": "卡片", "C": "资产", "D": "静帧", "E": "分镜", "F": "渲染", "G": "音频交付"}

# auth 的 7 个技能动作（规格 §3.1，必须原样保留）
SKILL_ACTIONS = {"read", "write_plan", "logic_check", "render_still", "render_video",
                 "generate_local_music", "analyze_audio"}

# Node 定义字段：executor/auth/minCap/locks/timeout/retries/gate
# gate: None | "auto"（自动门）| "human"（人工门）
N: dict[str, dict] = {
    # ---- A 立项 ----
    "A01": dict(title="文案摄取",   executor="ingest-copy",    auth="logic_check", minCap=[], locks=[], timeout=30, retries=1, gate=None),
    "A02": dict(title="创作简报",   executor="brief-form",     auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "A03": dict(title="风格库索引", executor="style-index",    auth="internal",    minCap=[], locks=[], timeout=120, retries=1, gate=None),
    "A04": dict(title="风格预演与推荐", executor="style-previs", auth="internal",  minCap=[], locks=["chrome-queue"], timeout=0, retries=2, gate=None),  # timeout=0 → 每张 15s
    "A05": dict(title="风格选择（首屏）", executor="gate",      auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    "A06": dict(title="字体与视觉令牌", executor="token-extract", auth="logic_check", minCap=[], locks=[], timeout=60, retries=1, gate=None),
    "A07": dict(title="口播方案",   executor="voice-plan",     auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "A08": dict(title="音乐方案",   executor="music-plan",     auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    # ---- B 卡片 ----
    "B01": dict(title="时长预算",   executor="duration-budget", auth="logic_check", minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B02": dict(title="场景图",     executor="scene-graph",    auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B03": dict(title="事件表",     executor="event-table",    auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B04": dict(title="视觉系统与分章", executor="layout-tokens", auth="write_plan", minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B05": dict(title="排版规格",   executor="type-spec",      auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B06": dict(title="任务卡组装", executor="task-assemble",  auth="write_plan",  minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "B07": dict(title="任务卡校验", executor="task-validate",  auth="logic_check", minCap=[], locks=[], timeout=120, retries=1, gate="auto"),
    "B08": dict(title="卡片评审",   executor="gate",           auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    # ---- C 资产 ----
    "C01": dict(title="引擎包编译", executor="engine-compile", auth="internal",    minCap=[], locks=[], timeout=300, retries=1, gate="auto"),
    "C02": dict(title="字体获取",   executor="font-fetch",     auth="internal",    minCap=[], locks=[], timeout=600, retries=2, gate=None),
    "C03": dict(title="字体合并裁剪", executor="font-subset",  auth="internal",    minCap=[], locks=[], timeout=120, retries=1, gate="auto"),
    "C04": dict(title="字体内嵌",   executor="font-embed",     auth="internal",    minCap=[], locks=[], timeout=30, retries=0, gate=None),
    "C05": dict(title="视觉令牌锁定", executor="tokens-lock",  auth="internal",    minCap=[], locks=[], timeout=10, retries=0, gate=None),
    # ---- D 静帧 ----
    "D01": dict(title="静帧规格构建", executor="still-spec",   auth="internal",    minCap=[], locks=[], timeout=10, retries=0, gate=None),
    "D02": dict(title="静帧渲染",   executor="chrome-still",   auth="render_still", minCap=[], locks=["chrome-queue", "port-8787"], timeout=120, retries=1, gate=None),  # 每张 120s
    "D03": dict(title="静帧查看",   executor="still-view",     auth="internal",    minCap=["render_still"], locks=[], timeout=0, retries=0, gate="human"),
    "D04": dict(title="静帧 QA",    executor="still-qa",       auth="internal",    minCap=["render_still"], locks=[], timeout=60, retries=0, gate="auto"),
    "D05": dict(title="静帧批准",   executor="gate",           auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    # ---- E 分镜 ----
    "E01": dict(title="时间轴构建", executor="timeline-build", auth="internal",    minCap=["render_still"], locks=[], timeout=10, retries=0, gate=None),
    "E02": dict(title="相机曲线",   executor="camera-curves",  auth="internal",    minCap=["render_still"], locks=[], timeout=10, retries=0, gate=None),
    "E03": dict(title="场景运动绑定", executor="timeline-binding", auth="internal", minCap=["render_still"], locks=[], timeout=30, retries=0, gate=None),
    "E04": dict(title="接缝匹配",   executor="transitions",    auth="internal",    minCap=["render_still"], locks=[], timeout=10, retries=0, gate=None),
    "E05": dict(title="预演渲染与拼图", executor="chrome-proxy", auth="internal",   minCap=["render_still"], locks=["chrome-queue", "port-8787"], timeout=720, retries=0, gate=None),
    "E06": dict(title="运动 QA（代理帧）", executor="motion-qa", auth="internal",   minCap=["render_still"], locks=[], timeout=120, retries=0, gate="auto"),
    "E07": dict(title="分镜批准",   executor="gate",           auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    # ---- F 渲染 ----
    "F01": dict(title="帧服务",     executor="frame-server",   auth="render_video", minCap=[], locks=["port-8787"], timeout=0, retries=0, gate=None),
    "F02": dict(title="逐帧渲染",   executor="chrome-frames",  auth="render_video", minCap=[], locks=["chrome-queue", "port-8787"], timeout=900, retries=0, gate=None),
    "F03": dict(title="帧完整性 QA", executor="frame-integrity", auth="internal",  minCap=["render_video"], locks=[], timeout=120, retries=0, gate="auto"),
    "F04": dict(title="编码",       executor="ffmpeg-encode",  auth="internal",    minCap=["render_video"], locks=["ffmpeg"], timeout=600, retries=1, gate=None),
    "F05": dict(title="成片 QA",    executor="video-qa",       auth="internal",    minCap=["render_video"], locks=[], timeout=300, retries=0, gate="auto"),
    "F06": dict(title="画面锁定",   executor="gate",           auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    # ---- G 音频 ----
    "G01": dict(title="口播上传",   executor="voice-ingest",   auth="internal",    minCap=["render_video"], locks=[], timeout=60, retries=0, gate=None),
    "G02": dict(title="文案对齐",   executor="audio-align",    auth="internal",    minCap=["render_video"], locks=[], timeout=600, retries=1, gate=None),
    "G03": dict(title="音乐选择",   executor="gate",           auth="internal",    minCap=[], locks=[], timeout=0, retries=0, gate="human"),
    "G04": dict(title="拍点图",     executor="audio-beat",     auth="internal",    minCap=["render_video"], locks=[], timeout=120, retries=0, gate=None),
    "G05": dict(title="混音",       executor="audio-mix",      auth="internal",    minCap=["render_video"], locks=["ffmpeg"], timeout=300, retries=1, gate=None),
    "G06": dict(title="音频 QA",    executor="audio-loudness", auth="analyze_audio", minCap=[], locks=[], timeout=120, retries=0, gate="auto"),
    "G07": dict(title="交付打包",   executor="package",        auth="internal",    minCap=["render_video"], locks=["ffmpeg"], timeout=600, retries=1, gate="human"),
}

assert len(N) == 46, f"节点数必须是 46，当前 {len(N)}"
for _id, _n in N.items():
    assert _n["auth"] in SKILL_ACTIONS | {"internal"}, f"{_id} auth 非法"
    assert _id.startswith(_stage := _id[0]) and _stage in STAGES

# 唯一权威边表 (from, to, type)——from 是上游、to 是下游（规格 §4.8 的「A02 ← A01」即 A01→A02）
# from/to 为 None 表示外部输入（用户上传/项目目录/风格库），不进表
EDGES: list[tuple[str, str, str]] = [
    ("A01", "A02", "data"),
    ("A01", "A04", "data"), ("A02", "A04", "data"), ("A03", "A04", "data"),
    ("A04", "A05", "data"),
    ("A05", "A06", "data"),
    ("A02", "A07", "data"), ("A02", "A08", "data"),
    ("A01", "B01", "data"), ("A07", "B01", "data"),
    ("B01", "B02", "data"), ("B02", "B03", "data"),
    ("A06", "B04", "data"), ("B02", "B04", "data"),
    ("B04", "B05", "data"),
    ("B01", "B06", "data"), ("B02", "B06", "data"), ("B03", "B06", "data"), ("B04", "B06", "data"),
    ("B05", "B06", "data"), ("A05", "B06", "data"), ("A06", "B06", "data"),
    ("B06", "B07", "data"), ("B07", "B08", "trigger"),
    ("A06", "C01", "data"), ("B08", "C01", "trigger"),
    ("A06", "C02", "data"),
    ("C02", "C03", "data"), ("B06", "C03", "data"),
    ("C03", "C04", "data"),
    ("A06", "C05", "data"), ("B04", "C05", "data"), ("B05", "C05", "data"),
    ("B06", "D01", "data"), ("C05", "D01", "data"), ("C01", "D01", "data"), ("B08", "D01", "trigger"),
    ("D01", "D02", "data"), ("C01", "D02", "data"), ("C04", "D02", "data"),
    ("D02", "D03", "data"),
    ("D02", "D04", "data"), ("D03", "D04", "data"), ("B06", "D04", "data"),
    ("D04", "D05", "trigger"), ("D03", "D05", "trigger"),
    ("B06", "E01", "data"), ("D05", "E01", "trigger"),
    ("E01", "E02", "data"), ("C05", "E02", "data"),
    ("E01", "E03", "data"), ("E02", "E03", "data"), ("C01", "E03", "data"), ("C04", "E03", "data"), ("C05", "E03", "data"),
    ("E03", "E04", "data"), ("B03", "E04", "data"),
    ("E04", "E05", "data"), ("E03", "E05", "data"), ("C01", "E05", "data"), ("C04", "E05", "data"), ("C05", "E05", "data"),
    ("E05", "E06", "data"),
    ("E05", "E07", "trigger"), ("E06", "E07", "trigger"),
    ("E04", "F02", "data"), ("E03", "F02", "data"), ("C01", "F02", "data"), ("C04", "F02", "data"), ("C05", "F02", "data"),
    ("F01", "F02", "data"), ("E07", "F02", "trigger"),
    ("F02", "F03", "data"), ("F03", "F04", "data"),
    ("F04", "F05", "data"), ("F02", "F05", "data"), ("E06", "F05", "data"),
    ("F05", "F06", "trigger"),
    ("G01", "G02", "data"), ("B06", "G02", "data"),
    ("A08", "G03", "data"), ("G02", "G03", "data"),
    ("G03", "G04", "data"),
    ("G01", "G05", "data"), ("G02", "G05", "data"), ("G04", "G05", "data"),
    ("G05", "G06", "data"), ("F06", "G06", "order"),
    ("G06", "G07", "data"), ("F04", "G07", "data"), ("F05", "G07", "data"), ("F06", "G07", "data"), ("D05", "G07", "order"),
]

DATA_EDGES = [(f, t) for f, t, ty in EDGES if ty == "data"]
TRIGGER_EDGES = [(f, t) for f, t, ty in EDGES if ty == "trigger"]
ORDER_EDGES = [(f, t) for f, t, ty in EDGES if ty == "order"]

# 上游映射：node → {上游: 类型}
UPSTREAM: dict[str, dict[str, str]] = {nid: {} for nid in N}
for f, t, ty in EDGES:
    UPSTREAM[t][f] = ty

# 下游 data 邻接
DATA_DOWN: dict[str, list[str]] = {nid: [] for nid in N}
for f, t in DATA_EDGES:
    DATA_DOWN[f].append(t)

# 拓扑序（Kahn）
def topo_order() -> list[str]:
    indeg = {nid: len([f for f in UPSTREAM[nid] if UPSTREAM[nid][f] in ("data", "trigger", "order")]) for nid in N}
    order: list[str] = []
    ready = [nid for nid, d in indeg.items() if d == 0]
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for f, t, ty in EDGES:
            if f == nid:
                indeg[t] -= 1
                if indeg[t] == 0:
                    ready.append(t)
    assert len(order) == 46, "边表存在环！"
    return order


TOPOLOGY = topo_order()

# 数据边失效传播闭包：node → 全部 data 下游（含传递）
def data_descendants(root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        for nxt in DATA_DOWN.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


HUMAN_GATES = sorted([nid for nid, n in N.items() if n["gate"] == "human"])
AUTO_GATES = sorted([nid for nid, n in N.items() if n["gate"] == "auto"])
