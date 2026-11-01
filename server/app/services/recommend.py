"""推荐 12（T08）：评分公式由规格 §3.2 锁定，不许即兴。

score = 0.55*BM25 + 0.20*briefKeywordOverlap + 0.15*constraintFit + 0.10*usagePrior - 0.10*familyRedundancy
"""
from __future__ import annotations

import random

import jieba.analyse
from sqlmodel import Session, select

from ..models import Style, StylePick


def _keyword_overlap(script: str, search_text: str) -> float:
    if not script or len(script.strip()) < 4:
        return 0.0
    kws = [k for k, _w in jieba.analyse.extract_tags(script, topK=12, withWeight=True)]
    if not kws:
        return 0.0
    hit = sum(1 for k in kws if k in search_text)
    return hit / len(kws)


def _constraint_fit(style: Style, constraints: dict | None) -> float:
    c = constraints or {}
    score = 1.0
    if c.get("require_chinese_legible") and not _chinese_friendly(style):
        score -= 0.6
    max_plates = c.get("max_plates")
    if max_plates is not None and style.family == "print":
        palette = (style.tokens_json or {}).get("palette") or []
        if len(palette) > max_plates:
            score -= 0.5
    lic = c.get("license")
    if lic and style.license and style.license not in lic:
        score -= 0.5
    return max(score, 0.0)


def _chinese_friendly(style: Style) -> bool:
    """中文友好：tokens.type 或 name/正文含中文可承载线索（人工标注可覆盖）。"""
    t = " ".join((style.tokens_json or {}).get("type") or [])
    return any(w in t for w in ("黑体", "宋体", "900", "Noto", "中文", "han")) or any(
        "\u4e00" <= ch <= "\u9fff" for ch in style.name)


def _usage_prior(session: Session, style_id: str) -> float:
    rows = session.exec(
        select(StylePick).where(StylePick.primary_id == style_id)  # type: ignore[arg-type]
    ).all()
    return min(len(rows) / 5.0, 1.0)


def recommend(session: Session, script: str, brief: dict | None = None,
              profile_constraints: dict | None = None, seed: int = 0, limit: int = 12) -> list[dict]:
    """只从可生产集合抽取（tokens 完整 + 引擎可用）；冷启动按可用语义族铺开。"""
    candidates = session.exec(
        select(Style).where(Style.tokens_status == "complete", Style.engine_status == "available",
                            Style.available == True)  # noqa: E712
    ).all()
    if not candidates:
        return []
    scored = []
    for st in candidates:
        bm25_proxy = 1.0 if (script and any(w in st.search_text for w in jieba.cut_for_search(script[:120]) if len(w) > 1)) else 0.0
        s = (0.55 * bm25_proxy
             + 0.20 * _keyword_overlap(script, st.search_text)
             + 0.15 * _constraint_fit(st, profile_constraints)
             + 0.10 * _usage_prior(session, st.id))
        scored.append((s, st))
    scored.sort(key=lambda x: x[0], reverse=True)

    cold = not script or len(script.strip()) < 20
    picked: list[Style] = []
    if cold:
        by_family: dict[str, list[Style]] = {}
        for _s, st in scored:
            by_family.setdefault(st.family, []).append(st)
        fams = sorted(by_family)
        rnd = random.Random(seed)
        rnd.shuffle(fams)
        for f in fams:
            for st in by_family[f][:2]:
                picked.append(st)
        picked = picked[:limit]
        # 不足用高分补齐
        for _s, st in scored:
            if len(picked) >= limit:
                break
            if st not in picked:
                picked.append(st)
    else:
        fam_count: dict[str, int] = {}
        for _s, st in scored:
            if len(picked) >= limit:
                break
            c = fam_count.get(st.family, 0)
            if c >= 3:
                continue
            picked.append(st)
            fam_count[st.family] = c + 1

    out = []
    for st in picked:
        reason = _reason(script, st, profile_constraints)
        out.append({"style_id": st.id, "score": round(next(s for s, x in scored if x.id == st.id), 4), "reason": reason})
    return out


def _reason(script: str, st: Style, constraints: dict | None) -> str:
    kws = [k for k in jieba.cut_for_search(script[:120]) if len(k) > 1 and k in st.search_text][:3]
    parts = []
    if kws:
        parts.append(f"命中关键词 {('、'.join(kws))}")
    if _chinese_friendly(st):
        parts.append("中文友好")
    parts.append(f"语义族 {st.family}")
    return " · ".join(parts) or "高覆盖风格"


def similar(session: Session, style_id: str, limit: int = 8) -> list[dict]:
    """相似风格：BM25 代理（共享关键词计数），排除自身。"""
    me = session.get(Style, style_id)
    if not me:
        return []
    kws = set(w for w in jieba.cut_for_search(me.search_text[:800]) if len(w) > 1)
    scored = []
    for st in session.exec(select(Style).where(Style.available == True)).all():  # noqa: E712
        if st.id == style_id:
            continue
        k2 = set(w for w in jieba.cut_for_search(st.search_text[:800]) if len(w) > 1)
        if not kws or not k2:
            continue
        j = len(kws & k2) / len(kws | k2)
        scored.append((j, st.id))
    scored.sort(reverse=True)
    return [{"style_id": sid, "score": round(j, 4)} for j, sid in scored[:limit]]


def random_explainable(session: Session, seed: int) -> dict:
    """随机但可解释：种子入库可复现，理由注明探索依据。"""
    cands = session.exec(select(Style).where(Style.available == True, Style.tokens_status == "complete")).all()  # noqa: E712
    if not cands:
        return {}
    rnd = random.Random(seed)
    st = rnd.choice(cands)
    return {"style_id": st.id, "seed": seed,
            "reason": f"随机探索（seed={seed}）：来自 {st.collection}，tokens 完整，可用于对比或主选"}
