"""来源集 → 语义族 初始映射（tech-plan §5.2，M0 粗映射，人工标注负责校准）。"""

# 目录名前缀 → (主族 slug, 副族列表, 中文名)
# 语义族 slug：print 印刷丝网 / collage 拼贴档案 / handdrawn 手绘笔触 / cartoon 卡通角色 /
#             pixel 像素游戏 / threedee 3D渲染 / photo 摄影电影 / ink 东方水墨 / infographic 信息图实验
COLLECTION_FAMILY: dict[str, dict] = {
    "O":  {"family": "photo",       "sub": ["print"],              "label": "O_奥斯卡98部"},
    "L":  {"family": "photo",       "sub": ["print"],              "label": "L_Lemo-Opuscar"},
    "M":  {"family": "infographic", "sub": [],                     "label": "M_动态风格"},
    "K":  {"family": "cartoon",     "sub": [],                     "label": "K_卡通画风"},
    "X":  {"family": "infographic", "sub": ["pixel"],              "label": "X_code-video"},
    "AG": {"family": "pixel",       "sub": ["infographic"],        "label": "A-G_代码样片"},
    "V":  {"family": "infographic", "sub": ["print"],              "label": "V_mg-styles-15"},
    "Z":  {"family": "ink",         "sub": [],                     "label": "Z_中国风"},
    "H":  {"family": "print",       "sub": [],                     "label": "H_现成版式"},
    "R":  {"family": "print",       "sub": ["collage"],            "label": "R_照参考学来的"},
}

FAMILY_LABELS = {
    "print": "印刷/丝网", "collage": "拼贴/档案", "handdrawn": "手绘/笔触", "cartoon": "卡通/角色",
    "pixel": "像素/游戏", "threedee": "3D/渲染", "photo": "摄影/电影", "ink": "东方/水墨",
    "infographic": "信息图/实验", "uncategorized": "未分类",
}

EXPECTED_COLLECTION_COUNTS = {"O": 98, "L": 59, "M": 40, "K": 38, "X": 31, "AG": 26, "V": 15, "Z": 15, "H": 12, "R": 7}
