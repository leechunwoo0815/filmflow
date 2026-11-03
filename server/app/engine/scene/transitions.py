"""转场枚举的唯一映射：preview 与 final 共用，禁止双实现。"""
from __future__ import annotations

TRANSITIONS = ("cut", "dissolve", "wipe", "push", "paper-slide", "ink-bleed",
               "glitch", "match-shape")

_LABELS = (("硬切", "cut"), ("溶解", "dissolve"), ("擦", "wipe"), ("推", "push"),
           ("滑", "paper-slide"), ("墨", "ink-bleed"), ("故障", "glitch"),
           ("匹配", "match-shape"))


def transition_type(text) -> str:
    t = str(text or "")
    if t in TRANSITIONS:
        return t
    for key, value in _LABELS:
        if key in t:
            return value
    return "match-shape"
