"""token 解析器（T03）：从风格 md 启发式抽取 6 字段，带分集适配器。

≥3 字段可解析 → tokens_status=complete（规格 §3.2 spike 口径）。
纯函数 + 可测：parse(md_text, collection_prefix) -> {"tokens": {...}, "fields": [...], "evidence": [...]}
"""
from __future__ import annotations

import re

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

TEXTURE_WORDS = ["纸纹", "颗粒", "网点", "噪点", "纹理", "磨砂", "做旧", "斑驳", "针孔", "漏印",
                 "grain", "texture", "noise", "paper", "halftone", "risograph", "riso", "印刷", "丝网"]
MOTION_WORDS = {"slow": ["慢", "缓慢", "静止", "停顿", "晕染", "slow", "still", "calm", "淡入"],
                "fast": ["快", "急速", "闪烁", "跳切", "抖动", "glitch", "fast", "rapid", "snap", "闪"],
                "medium": ["滚动", "缩放", "推近", "平移", "滑动", "生长", "展开", "pan", "zoom", "wipe"]}
TYPE_WORDS = ["等宽", "mono", "monospace", "衬线", "serif", "黑体", "宋体", "手写", "圆体", "像素字",
              "font", "typeface", "字形", "900", "700", "大字号", "标题字"]
COMPOSITION_WORDS = ["网格", "三栏", "两栏", "居中", "对角", "满版", "留白", "边框", "分栏", "叠加",
                     "grid", "layout", "构图", "版式", "symmetry", "asymmetric", "海报"]
SCREEN_RE = re.compile(r"(?:网角|angle)[^\d]{0,6}(\d{1,2})\s*°?", re.I)
PERIOD_RE = re.compile(r"(?:周期|period|间距)[^\d]{0,6}(\d(?:\.\d)?)\s*(?:px|像素)?", re.I)

# A-G 代码样片：JS 常量直接读
JS_CONST_RE = re.compile(r"(?:const|var|let)\s+([A-Za-z_][\w]*)\s*=\s*([\[\]{\}#\d'\",\s\.\w\-]+?);")


def _norm_hex_list(found: list[str]) -> list[str]:
    seen, out = set(), []
    for h in found:
        h = h.upper()
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:6]


def _adapter_AG(text: str, tokens: dict, evidence: list[str]) -> None:
    """A-G 代码样片：JS 常量 → palette / screen。"""
    for name, val in JS_CONST_RE.findall(text):
        if "COLOR" in name.upper() or "PALETTE" in name.upper() or "INK" in name.upper():
            hexes = HEX_RE.findall(val)
            if hexes and not tokens.get("palette"):
                tokens["palette"] = _norm_hex_list(hexes)
                evidence.append(f"JS 常量 {name}")
        m = re.search(r"(?:PERIOD|period|GAP)\D{0,4}(\d(?:\.\d)?)", name + "=" + val)
        if m and not tokens.get("screen", {}).get("period"):
            tokens["screen"]["period"] = float(m.group(1))


def _adapter_L(text: str, tokens: dict, evidence: list[str]) -> None:
    """L_Lemo-Opuscar：英文小节标题后的内容加权。"""
    for kw in ("palette", "color"):
        m = re.search(rf"{kw}\s*:?\s*([^\n]{{0,120}})", text, re.I)
        if m:
            hexes = HEX_RE.findall(m.group(1))
            if hexes and not tokens.get("palette"):
                tokens["palette"] = _norm_hex_list(hexes)
                evidence.append(f"小节 {kw}")


def parse(md_text: str, collection_prefix: str = "") -> dict:
    text = md_text
    low = text.lower()
    tokens: dict = {"palette": [], "texture": [], "screen": {}, "motion": {}, "type": [], "composition": []}
    evidence: list[str] = []

    hexes = _norm_hex_list(HEX_RE.findall(text))
    if hexes:
        tokens["palette"] = hexes
        evidence.append(f"hex×{len(hexes)}")

    tex = [w for w in TEXTURE_WORDS if w in low or w in text]
    if tex:
        tokens["texture"] = tex[:5]
        evidence.append("texture 词")

    for pacing, words in MOTION_WORDS.items():
        hit = [w for w in words if w in low or w in text]
        if hit:
            tokens["motion"]["pacing"] = pacing
            tokens["motion"]["words"] = hit[:5]
            evidence.append(f"motion={pacing}")
            break

    m = SCREEN_RE.search(text)
    if m:
        tokens["screen"]["angle"] = int(m.group(1))
        evidence.append("网角")
    m = PERIOD_RE.search(text)
    if m and "period" not in tokens["screen"]:
        tokens["screen"]["period"] = float(m.group(1))

    typ = [w for w in TYPE_WORDS if w in low or w in text]
    if typ:
        tokens["type"] = typ[:5]
        evidence.append("type 词")

    comp = [w for w in COMPOSITION_WORDS if w in low or w in text]
    if comp:
        tokens["composition"] = comp[:5]
        evidence.append("composition 词")

    if collection_prefix == "AG":
        _adapter_AG(text, tokens, evidence)
    elif collection_prefix == "L":
        _adapter_L(text, tokens, evidence)

    fields = [k for k, v in tokens.items() if v]  # 非空字段
    status = "complete" if len(fields) >= 3 else "incomplete"
    return {"tokens": tokens, "fields": fields, "status": status, "evidence": evidence}


def search_text_of(name: str, md_body: str) -> str:
    """FTS search_text：名称 + 去代码块的 md 正文 + jieba 预分词（规格 §12）。"""
    import jieba
    no_code = re.sub(r"```.*?```", " ", md_body, flags=re.S)
    no_code = re.sub(r"<[^>]+>", " ", no_code)
    seg = " ".join(jieba.cut_for_search(no_code[:4000]))
    return f"{name} {no_code[:2000]} {seg}"
