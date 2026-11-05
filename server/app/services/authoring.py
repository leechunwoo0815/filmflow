"""FR-41 本地规则式创作辅助（R3.5）：断句/场景/组件/镜头建议 + 读时校验。

硬边界（PRD §FR-41）：**不生成内容、不调用在线模型、不写文案**；全部规则在本地、
可解释（每条建议带 reason）、可拒绝；建议是**草稿层**——只给结构（ids/时长/组件/
镜头预设），原文一个字不改（见 suggest 的返回不含任何改写文本）。
"""
from __future__ import annotations

import re

from .timeline_ops import READ_CPS

SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])")
# 转折/递进词 → 强制断点（句群边界信号）
BREAK_HINTS = ("但是", "然而", "不过", "可是", "却", "于是", "后来", "突然", "直到", "其实")
# 组件关键词 → 组件 id（scene-kit 组件登记处）
COMPONENT_HINTS = (
    ("证据", "evidence-card"), ("卡片", "evidence-card"),
    ("增长", "count-up"), ("下降", "count-up"), ("数字", "count-up"), ("百分比", "count-up"),
    ("图表", "chart-bar"), ("走势", "chart-bar"),
    ("对比", "compare"), ("相比", "compare"), ("vs", "compare"),
    ("时间线", "timeline"), ("流程", "timeline"), ("步骤", "timeline"),
    ("名单", "list-reveal"), ("清单", "list-reveal"),
    ("地图", "map-pan"), ("位置", "map-pan"),
)
# 镜头预设（不自动应用，PRD 行为 4）
CAMERA_PRESETS = {
    "narration": [{"zoom": 1.0, "note": "锁定"}, {"zoom": 1.05, "note": "缓推 5%"},
                  {"pan": "left", "note": "横移"}],
    "data": [{"zoom": 1.0, "note": "锁定"}, {"zoom": 1.12, "note": "推近数据区"}],
    "quote": [{"zoom": 1.0, "note": "锁定"}, {"zoom": 1.03, "note": "极缓推"}],
}
TARGET_SCENES = (4, 6)
MIN_SCENE_SECONDS = 2.0


def split_sentences(text: str) -> list[dict]:
    """断句：句末标点切分 + 转折词二次切分；给读时估算。"""
    out = []
    for raw in SENT_SPLIT.split((text or "").strip()):
        s = raw.strip()
        if not s:
            continue
        for hint in BREAK_HINTS:
            idx = s.find(hint, 2)     # 句首的转折词不切
            if idx > 2:
                head, tail = s[:idx], s[idx:]
                out.append(head.strip())
                s = tail
                break
        out.append(s.strip())
    return [{"text": s, "readSeconds": round(len(s.replace("\n", "")) / READ_CPS, 3),
             "chars": len(s.replace("\n", ""))}
            for s in out if s]


def scene_suggestions(text: str) -> dict:
    """4–6 场建议：句群聚合到目标场景数，每场带理由（句数/读时/转折词）。"""
    sents = split_sentences(text)
    if not sents:
        return {"schema": "filmflow.authoring/1", "scenes": [], "sentences": []}
    n_scenes = max(TARGET_SCENES[0], min(TARGET_SCENES[1],
                                         (len(sents) + 1) // 2 or 1))
    per = max(1, (len(sents) + n_scenes - 1) // n_scenes)
    scenes, cur, reasons = [], [], []
    for s in sents:
        cur.append(s)
        if len(cur) >= per:
            scenes.append(cur)
            cur = []
    if cur:
        (scenes[-1] if scenes else scenes).extend(cur) if scenes else scenes.append(cur)
    scenes = [g for g in scenes if g]
    out = []
    for i, group in enumerate(scenes):
        text_joined = "".join(x["text"] for x in group)
        read = round(sum(x["readSeconds"] for x in group), 2)
        hint = next((h for h in BREAK_HINTS
                     if any(x["text"].startswith(h) or h in x["text"][:4] for x in group)), None)
        reason = (f"第 {i + 1}/{len(scenes)} 组：{len(group)} 句、读时 {read}s"
                  + (f"、含转折「{hint}」开句" if i > 0 and hint and
                     any(x["text"].startswith(hint) for x in group) else ""))
        out.append({"id": f"S{i + 1:02d}", "sentences": [x["text"] for x in group],
                    "suggestedSeconds": read, "reason": reason,
                    "kind": _scene_kind(text_joined)})
    return {"schema": "filmflow.authoring/1", "sentences": sents, "scenes": out,
            "readCps": READ_CPS}


def _scene_kind(scene_text: str) -> str:
    if any(k in scene_text for k in ("增长", "数字", "百分比", "图表")):
        return "data"
    if any(k in scene_text for k in ("说", "指出", "认为", "？")):
        return "quote"
    return "narration"


def component_suggestions(scene_text: str) -> list[dict]:
    """关键词 → 组件建议（给匹配词，PRD 行为 3）。"""
    out = []
    for keyword, comp in COMPONENT_HINTS:
        if keyword in scene_text:
            out.append({"keyword": keyword, "component": comp,
                        "reason": f"文本命中关键词「{keyword}」"})
    return out


def camera_suggestions(kind: str) -> list[dict]:
    """2–3 个镜头预设（不自动应用）。"""
    return CAMERA_PRESETS.get(kind, CAMERA_PRESETS["narration"])


def read_check(scene_text: str, duration: float) -> dict:
    """读时校验：建议时长（5.2 cps）与最短可读（0.35s/字下限取整）对比。"""
    suggested = round(len(scene_text.replace("\n", "")) / READ_CPS, 3)
    chars = len(scene_text.replace("\n", ""))
    min_readable = round(max(1.0, chars * 0.18), 2)
    return {"chars": chars, "suggestedSeconds": suggested, "givenSeconds": round(duration, 2),
            "minReadable": min_readable,
            "verdict": ("ok" if duration >= suggested * 0.9 and duration >= min_readable
                        else "too_short" if duration < min_readable else "tight")}


def suggest(text: str) -> dict:
    """一次性建议包：断句 + 场景 + 每场的组件/镜头建议 + 读时校验。纯本地规则。"""
    pack = scene_suggestions(text)
    for sc in pack["scenes"]:
        joined = "".join(sc["sentences"])
        sc["components"] = component_suggestions(joined)
        sc["cameraPresets"] = camera_suggestions(sc["kind"])
        sc["readCheck"] = read_check(joined, sc["suggestedSeconds"])
    return pack
