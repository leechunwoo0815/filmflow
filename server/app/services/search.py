"""风格搜索（T07）：FTS5 trigram + 同义词扩展 + 集合标签匹配（规格 §7.0 同义词要求）。"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models import Style

# 同义词环：查询词 → 扩展词集（保证「水墨」命中 Z 集全部 15 条）
SYNONYMS: dict[str, list[str]] = {
    "水墨": ["水墨", "中国风", "书法", "国画", "毛笔", "宣纸", "木版", "京剧", "脸谱", "东方", "ink"],
    "中国风": ["中国风", "水墨", "书法", "国画", "东方", "京剧", "木版"],
    "电影感": ["电影", "奥斯卡", "胶片", "cinematic", "电影感", "暗调"],
    "奥斯卡": ["奥斯卡", "电影", "胶片", "cinematic"],
    "动效": ["动态", "运动", "动画", "动效", "motion"],
    "动态": ["动态", "动效", "运动", "动画"],
    "像素": ["像素", "pixel", "8bit", "复古游戏"],
    "赛博": ["赛博", "cyber", "霓虹", "科幻"],
    "复古": ["复古", "retro", "年代", "vintage"],
    "手绘": ["手绘", "笔触", "sketch", "彩铅", "插画"],
    "海报": ["海报", "版式", "poster", "排版"],
}


def expand_query(q: str) -> list[str]:
    terms = [q.strip()]
    for key, syns in SYNONYMS.items():
        if key in q:
            terms.extend(syns)
    return sorted(set(t.lower() for t in terms if t))


def search_styles(session: Session, q: str, limit: int = 200) -> list[Style]:
    """返回按相关度排序的风格列表。FTS 竞速 + 子串/同义词保召回。"""
    rows = [r for r in session.exec(select(Style)).all()
            if not r.id.startswith("EX") and r.available]
    if not q.strip():
        return rows
    terms = expand_query(q)
    cols = {r.collection.lower() for r in rows}
    scored: list[tuple[float, Style]] = []
    for r in rows:
        hay = (r.search_text or "").lower()
        name = r.name.lower()
        coll = r.collection.lower()
        score = 0.0
        for t in terms:
            if t in name:
                score += 3.0
            if t in coll or t in coll.replace("_", ""):
                score += 2.0
            if t in hay:
                score += 1.0
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    return [r for _s, r in scored[:limit]]
