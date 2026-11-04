# 内置技能与 341 风格库（Qoder / 新 Agent 先读这里）

> 本目录解决一件事：**技能随项目走，341 风格库不随项目走，但路径必须能被下一位 Agent 找到。**
> 更完整的接手说明见 [`../HANDOFF.md`](../HANDOFF.md)；产品深化需求见 [`../docs/prd/PRD-002-production-workbench.md`](../docs/prd/PRD-002-production-workbench.md)。

---

## 1. 内置技能：fy-code-animation

| 项 | 值 |
|---|---|
| 目录 | `vendor/fy-code-animation/` |
| 原始位置 | `/Users/litianyu/.trae-cn/skills/fy-code-animation` |
| 复制日期 | 2026-11-02 |
| 体积 / 文件数 | 984 KB / 147 个文件（已排除 `.DS_Store`） |
| 入口 | [`vendor/fy-code-animation/SKILL.md`](fy-code-animation/SKILL.md) |
| 许可 | [`vendor/fy-code-animation/LICENSE.md`](fy-code-animation/LICENSE.md)（免费使用/分享；禁止包装成付费课程或付费 skill 出售） |

**它是什么**：中文代码动画的创作方法包——语义分镜、341 画风库检索、气势词/中文动态文字、活的背景、动作物理、镜头运动、转场接缝、角色表演、像素/卡通/手绘/3D 分支、图表地图 UI、音乐四案、Remotion 落地、检查返修、跨 Agent 交接。

**它不是什么**：它不是 FilmFlow 的运行时依赖。FilmFlow 的 46 节点执行器**不 import 它**；它是给写代码的 Agent 查方法/配方/验收标准用的。不要把它加进 Python 包路径，也不要让服务端启动时加载它。

**技能内的 `adapters/style-index.json` 只是索引**（343 条记录，`prompt_count: 341`，`content_included: false`）。**341 条 prompt 正文不在技能里**，在下面这个外部库。

---

## 2. 341 风格库（逻辑约 75MiB，不提交进 git）

> **体积口径**：下表的 MB 是 `du` 逻辑大小；**磁盘实际分配约 9.3MiB**——`示例/` 的
> 3 个 mp4 是**稀疏文件**（逻辑 59.8MiB，物理占块极小），所以"体积 8 倍失实"类判断
> 必须区分这两个口径（详见 `docs/reviews/2026-11-03-expert-review-analysis.md` §2.4）。

**真实路径**（也写在 [`style-library.path`](style-library.path)）：

```
/Users/litianyu/Documents/fy-style-library/代码动画_341种风格提示词
```

| 子目录/文件 | 体积 | 内容 |
|---|---:|---|
| `风格提示词/` | 15 MB | **341 个 `.md` 提示词** + 193 张同名 `.jpg` 静帧；10 个分类目录 |
| `示例/` | 61 MB | 3 个实测 mp4（B6 两个版本、X7 一个版本）+ 截图；**不建议入库** |
| `风格挑选.html` | 472 KB | 离线挑选网页（可搜索/筛选/看静帧/导出清单） |
| `adapters/style-index.json` | 178 KB | 库自带的索引快照 |
| `_统计.json` / `说明.md` / `许可与来源.md` / `第三方许可/` | <20 KB | 计数、说明、许可 |

**分类计数**：O 98 · L 59 · M 40 · K 38 · X 31 · A-G 26 · Z 15 · V 15 · H 12 · R 7 = **341**。

**路径记录在三个地方**：

1. `vendor/style-library.path`（纯文本，给 Agent 最快读取）
2. `vendor/fy-code-animation/adapters/style-library.config.json` 的 `root`
3. FilmFlow 服务端默认值：`server/app/config.py:13`（`settings.style_library_root`）

> 三处当前指向同一个目录。换机器/换库时三处都要改，或统一用环境变量覆盖：
> - FilmFlow：`FILMFLOW_STYLE_LIBRARY_ROOT`
> - 技能脚本：`FY_STYLE_LIBRARY_ROOT`

---

## 3. 常用命令

在项目根目录执行：

```bash
LIB="$(cat vendor/style-library.path)"

# 技能自检：库是否定位、索引是否过期、缺什么
python3 vendor/fy-code-animation/scripts/doctor.py --root "$LIB"

# 库更新后重建技能索引（只写相对路径 + SHA，不复制原文）
python3 vendor/fy-code-animation/scripts/style_library.py build --root "$LIB"

# 检索 / 读取完整提示词（示例）
python3 vendor/fy-code-animation/scripts/style_library.py search --query "水墨"
python3 vendor/fy-code-animation/scripts/style_library.py get --query Z5 --kind prompt

# FilmFlow 重建 341 索引（服务在跑时）
curl -s -X POST http://127.0.0.1:7860/api/library/index
```

如果 `doctor.py` 报 `LIBRARY_ROOT_NOT_FOUND`，先检查 `vendor/style-library.path` 是否指向真实存在的目录；不要把 341 正文复制进技能目录来“修”它。

---

## 4. FilmFlow 里谁在用这个库

| 位置 | 用途 |
|---|---|
| `server/app/config.py:13` | `settings.style_library_root` 默认值 |
| `server/app/services/style_index.py` | A03 扫描 341 条、断言计数/封面、生成 `adapters/style-index.json` |
| `server/app/services/token_parser.py` | 解析 prompt 的 tokens |
| `server/app/services/search.py` / `recommend.py` | FTS5 检索/推荐 |
| `server/app/api/routes.py` | `/api/styles`、`/api/styles/{id}/preview`、`/api/library/status` |

**运行时只读 341 库，不读 `vendor/fy-code-animation`。** 技能目录是给人/Agent 看的，不是给服务端加载的。

---

## 5. 不要做的事

- **不要**把 76 MB 库复制进 `vendor/` 再提交（尤其 `示例/` 的 61 MB mp4；示例视频的再分发授权不明确）。
- **不要**把 `vendor/fy-code-animation` 加进 `server` 的 Python 包/`PYTHONPATH`。
- **不要**修改技能里的 `adapters/style-index.json` 来“适配”FilmFlow；FilmFlow 有自己的 A03 索引。
- **不要**在公开仓库/付费内容里重新分发 341 原文或示例 mp4；许可只允许免费使用/分享，禁止包装成付费课程/付费 skill 出售。
- **不要**把绝对路径硬编码进执行器；统一走 `settings.style_library_root` 或环境变量。

---

## 6. 给下一位 Agent 的最短路径

1. 读 [`../HANDOFF.md`](../HANDOFF.md) §1/§9/§10（状态、硬缺口、路线图）。
2. 读 [`../docs/prd/PRD-002-production-workbench.md`](../docs/prd/PRD-002-production-workbench.md) §1/§2/§7（诊断、原则、30 条 FR）。
3. 要改渲染/分镜/字体/转场时，按需读 `vendor/fy-code-animation/SKILL.md` 的能力路由，再下钻 `modules/`、`recipes/`。
4. 要动风格库时，先 `cat vendor/style-library.path`，再跑 `doctor.py`。
5. 任何“完成”的申报附测试输出、真实产物路径、UI 截图、API curl（HANDOFF §11.5）。
