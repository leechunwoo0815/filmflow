# FilmFlow 技术方案（规格 §18 九项）

> 版本 v1.0 · S1 交付物 · 老板确认后进入 M0 编码（SDLC 硬规则）
> 与规格的关系：规格是宪法；本文是实现蓝图，冲突时以规格 §4.8 / §19 为准并回改本文。

---

## 0. 结论速览与默认决定（可否决）

已锁定（老板拍板）：Python 3.13 + FastAPI + SQLModel + SQLite / OpenAPI 3.1 / Next.js 15 深色工作台 / whisper ggml-medium / M0 全量。

本方案新增的默认决定（不同意请在确认时指出）：

| # | 默认决定 | 理由 |
|---|---|---|
| D1 | 风格 ID = `<集合前缀><集内序号>`（如 O88 = O 集第 88 个文件，按文件名排序），与规格夹具 L28/O88 对齐 | 夹具已依赖该形态 |
| D2 | 预演渲染用 **Playwright(Python) 驱动系统 Chrome 单实例**（channel=chrome），页面内队列 + CDP 截图 | 满足"常驻浏览器+页面内队列"，避免自写 CDP 客户端 |
| D3 | `riso` 引擎包从 rumor-39s 抽取（entry/still.html + film.html + 字体 embed + fixtures=out/stills） | 参考项目即 riso 实现，零重写 |
| D4 | 生产态 Next.js 用 `output: 'export'` 静态导出，FastAPI 挂载托管 → 单进程 :7860 | 满足"双击启动" |
| D5 | 索引文件写入库目录 `adapters/style-index.json`（目录只读时回落 `~/.filmflow/index/`） | 保持规格路径 |
| D6 | BDD 工具 = pytest-bdd，步骤绑定放 `server/tests/bdd/`，直接引用 `bdd/features/*.feature` | 与 Python 后端同工具链 |

---

## 1. 架构一页纸

### 1.1 进程与端口

```
开发态：  next dev :3000 (web) ──proxy /api──▶ uvicorn :7860 (api)
          uvicorn 按需 spawn：chrome(chrome-queue=1) / ffmpeg / whisper-cli / pyftsubset
发布态：  单进程 uvicorn :7860 = API + Next 静态导出（D4）
帧服务：  F01 独立监听 127.0.0.1:8787（规格硬约束，供 Chrome 渲染页面回传帧）
```

### 1.2 模块分层（server/）

```
api/          FastAPI 路由（projects drafts styles picks workflows runs gates artifacts jobs events audit）
engine/
  runengine   拓扑调度器：就绪集计算（边表+caps+门）→ 入队 → 派发
  scheduler   锁管理（chrome-queue=1, ffmpeg=1, port-8787, disk≥5GB）+ 2 并发分析池
  executors/  46 个执行器（§3 清单），一对一
  runner      子进程壳：spawn / NDJSON @@PROGRESS 解析 / SIGTERM→5s→SIGKILL / 退出码
  invalidation 失效传播（data 边 BFS）+ 门 content_hash + impact dry-run
services/
  style_index(A03) / token_parser(spike) / recommend / previs_jobs / engines(注册表)
  audio_align(whisper) / artifacts(内容寻址存储) / events(SSE fanout + JSONL)
models/       SQLModel 15 张表（§2.1）
```

### 1.3 关键数据流（一次节点执行）

```
UI 点 Run → POST /runs/:id/step → RunEngine.ready_set()
  → caps/minCap/trigger 校验 → 锁申请 → executor.run(workdir)
  → spawn 子进程 → stdout NDJSON(@@PROGRESS/log) → SSE 推送
  → 产物写 artifacts/<sha前2>/<sha>.<ext> + DB 登记
  → invalidation.propagate(节点) → 受影响节点 invalidated / 门 stale
  → SSE gate.stale / node.succeeded
```

### 1.4 锁与缓存（实现要点）

- 锁 = asyncio.Mutex 字典 + 等待队列；甘特图记录 lock_wait 时长。
- 缓存键 = `sha256(executorVersion|params|inputs.artifactSha|caps)`（JSON 规范化后哈希）；门键 = 输入 content_hash。
- 强制重跑 = 跳过键查询但仍登记 NodeRun。

---

## 2. 数据库 Schema 与 API 契约

### 2.1 表（SQLModel，15 张，列定义）

```
projects(id PK, name, root UNIQUE, created_at)
drafts(id PK, name, step int, payload_json JSON, created_at, materialized_run_id FK?)
styles(id PK, collection, family, sub_families_json, name, path, sha256, bytes, lines,
       has_cover bool, tokens_status enum(complete|incomplete), preview_status enum(cover|previs|no_preview|failed),
       engine_status enum(available|unavailable), search_text, license, available bool, indexed_at)
       索引: FTS5 虚表 styles_fts(search_text) tokenize='trigram'
style_previews(style_id FK, variant enum(thumb|detail), path, sha256, engine_sha, renderer_ver, created_at)
       唯一键(style_id, variant, engine_sha, renderer_ver)
style_picks(id PK, project_id FK?, draft_id FK?, run_id FK?, primary_id, alternates_json,
       per_scene_json, reason, author, created_at)
workflows(id PK, project_id FK, name, version, graph_json, created_at)
runs(id PK, workflow_id FK, status, caps_json, params_snapshot JSON, started_at, finished_at, parent_run_id?)
node_runs(id PK, run_id FK, node_id, status enum(idle|queued|running|succeeded|failed|canceled|blocked|stale|disabled|skipped),
       cache_key, started_at, finished_at, exit_code?, params_json)
artifacts(id PK, run_id FK, node_run_id FK, type, path, sha256, bytes, meta_json)
metrics(id PK, run_id FK, node_run_id FK, key, value float, unit)
events(id PK, run_id FK, node_id?, type, at, payload_json)     — 同时落 JSONL
approvals(id PK, run_id FK, gate_id, decision enum(approved|rejected|stale), authority,
       policy enum(inherit|reapprove), content_hash, author, note, checklist_json, created_at)
audit_log(id PK, actor, action, target, before_json, after_json, at)
jobs(id PK, kind, status, payload_json, result_json, created_at, finished_at)
workflow_versions(id PK, workflow_id FK, version, graph_json, created_at)
```

### 2.2 API 契约（端点全集见规格 §9.1，此处补契约细节）

- **信封**：成功直接返回资源；错误统一 `{"code": "<E_XXX>", "message": "...", "details": {...}}` + HTTP 4xx/5xx。
- **分页**：`?limit=&cursor=`，响应 `{items:[], next_cursor}`。
- **错误码枚举（首批）**：`E_PHASE_FORBIDDEN / E_PHASE_MISMATCH / E_ENGINE_UNAVAILABLE / E_MODEL_MISSING / E_ENV_MISSING / E_PORT_BUSY / E_DISK_FULL / E_VALIDATION / E_NOT_FOUND / E_CONFLICT`。
- **SSE 载荷**：`{event, run_id, node_id?, at, data}`，event ∈ `node.started|node.log|node.progress|node.succeeded|node.failed|gate.waiting|gate.stale|run.finished`。
- **关键请求体**：
  - `POST /api/style-picks {projectId?|draftId?, primary, alternates[], reason}`
  - `POST /api/gates/:gateId/decide {decision, author, note, checklist[]}`
  - `GET /api/runs/:id/impact?nodeId=&patch=` → `{nodes:[nodeId…], gates:[gateId…], stale_gates:[…], cache_hits:[…]}`
- **契约保障**：FastAPI 自动产出 `openapi.json`；CI 步骤 `openapi-typescript` 重新生成客户端并对 snapshot diff，漂移即红。

---

## 3. 46 节点执行器清单

> 输入/输出/自动校验以规格 §4 表为准，此处补齐 **执行器 / auth / minCap / 锁 / 超时 / 重试**。`内` = internal。

### A 立项

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| A01 | `ingest-copy` | logic_check | logic_check | — | 30s | 1 |
| A02 | `brief-form` | write_plan | logic_check | — | 10s | — |
| A03 | `style-index` | 内(index) | logic_check | — | 120s | 1 |
| A04 | `style-previs` | 内(previs) | logic_check | chrome-queue | 15s/张 | 2 |
| A05 | 人工门 | — | — | — | — | — |
| A06 | `token-extract` | logic_check | logic_check | — | 60s | 1 |
| A07 | `voice-plan` | write_plan | logic_check | — | 10s | — |
| A08 | `music-plan` | write_plan | logic_check | — | 10s | — |

### B 任务卡

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| B01 | `duration-budget` | logic_check | logic_check | — | 10s | — |
| B02 | `scene-graph` | write_plan | logic_check | — | 10s | — |
| B03 | `event-table` | write_plan | logic_check | — | 10s | — |
| B04 | `layout-tokens` | write_plan | logic_check | — | 10s | — |
| B05 | `type-spec` | write_plan | logic_check | — | 10s | — |
| B06 | `task-assemble` | write_plan | logic_check | — | 10s | — |
| B07 | `task-validate`(cmd: tools/validate_task.py) **自动门** | logic_check | logic_check | — | 120s | 1 |
| B08 | 人工门 | — | — | — | — | — |

### C 资产

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| C01 | `engine-compile` **自动门** | 内(compile) | logic_check | — | 300s | 1 |
| C02 | `font-fetch`(cmd: pnpm dlx @fontsource) | 内(fetch) | logic_check | — | 600s | 2 |
| C03 | `font-subset`(pyftsubset) **自动门** | 内(subset) | logic_check | — | 120s | 1 |
| C04 | `font-embed` | 内(embed) | logic_check | — | 30s | — |
| C05 | `tokens-lock` | 内(lock) | logic_check | — | 10s | — |

### D 静帧

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| D01 | `still-spec` | 内(build_spec) | logic_check | — | 10s | — |
| D02 | `chrome-still` | render_still | — | chrome-queue | 120s/张 | 1 |
| D03 | 人工查看 | 内(qa_still) | render_still | — | — | — |
| D04 | `still-qa` **自动门** | 内(qa_still) | render_still | — | 60s | — |
| D05 | 人工门 | — | — | — | — | — |

### E 分镜

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| E01 | `timeline-build` | 内(timeline) | render_still | — | 10s | — |
| E02 | `camera-curves` | 内(timeline) | render_still | — | 10s | — |
| E03 | `timeline-binding` | 内(timeline) | render_still | — | 30s | — |
| E04 | `transitions` | 内(timeline) | render_still | — | 10s | — |
| E05 | `chrome-proxy`(film?mode=proxy) | 内(previs) | render_still | chrome-queue | 12min/段 | 断点续跑 |
| E06 | `motion-qa` **自动门** | 内(qa_frames) | render_still | — | 120s | — |
| E07 | 人工门 | — | — | — | — | — |

### F 渲染编码

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| F01 | `frame-server` | render_video | — | port-8787 | 常驻 | — |
| F02 | `chrome-frames` | render_video | — | chrome-queue | 15min/段 | 断点续跑 |
| F03 | `frame-integrity` **自动门** | 内(qa_integrity) | render_video | — | 120s | — |
| F04 | `ffmpeg-encode` | 内(encode) | render_video | ffmpeg | 10min | 1 |
| F05 | `video-qa`(ffprobe+Y-SSIM) **自动门** | 内(qa_video) | render_video | — | 300s | — |
| F06 | 人工门 | — | — | — | — | — |

### G 音频交付

| ID | 执行器 | auth | minCap | 锁 | 超时 | 重试 |
|---|---|---|---|---|---|---|
| G01 | `voice-ingest` | 内(align) | render_video | — | 60s | — |
| G02 | `audio-align`(whisper-cli) | 内(align) | render_video | — | 600s | 1 |
| G03 | 人工门（音乐，generate_local_music） | — | — | — | — | — |
| G04 | `audio-beat` | 内(beat) | render_video | — | 120s | — |
| G05 | `audio-mix`(ffmpeg) | 内(mix) | render_video | ffmpeg | 300s | 1 |
| G06 | `audio-loudness` **自动门** | analyze_audio | — | — | 120s | — |
| G07 | `package` **人工门 reapprove** | 内(package) | render_video | ffmpeg | 600s | 1 |

---

## 4. M0 实施计划与文件结构

### 4.1 仓库结构

```
filmflow/
├─ server/
│  ├─ pyproject.toml            # uv 管理
│  ├─ app/
│  │  ├─ main.py                # FastAPI 工厂 + 静态挂载 + lifespan(调度器启动)
│  │  ├─ config.py              # 端口/路径/白名单
│  │  ├─ models/                # §2.1 的 15 张表
│  │  ├─ schemas/               # Pydantic 请求/响应
│  │  ├─ api/                   # 路由（每资源一个文件）
│  │  ├─ engine/                # runengine / scheduler / locks / invalidation / runner / edges.py
│  │  ├─ executors/             # §3 的 46 个执行器（按阶段分文件）
│  │  └─ services/              # style_index / token_parser / recommend / previs / engines / artifacts / events
│  ├─ tools/                    # vendored: validate_task.py、字体脚本
│  └─ tests/
│     ├─ unit/  integration/  bdd/   # pytest-bdd 绑定 bdd/features/
├─ web/                         # Next.js 15（pnpm）
│  └─ src/app/  (wizard)  (canvas/[projectId])  (monitor)  styles/
│     src/components/  src/lib/ (openapi 生成的 client + stores)
├─ engines/
│  └─ riso/  contract.json  entry/{still,film}.html  assets/  fixture/
├─ bdd/features/                # 已有 15 个
├─ scripts/                     # fixtures 生成器、种子数据
├─ docs/                        # 本文档等
├─ dev.sh  build.sh
└─ README.md
```

### 4.2 M0 任务序列（T01–T15，依赖有序）

| # | 任务 | 交付物 | 验收（对应 gherkin） |
|---|---|---|---|
| T01 | 脚手架 | FastAPI+SQLModel 建表、Next 深色壳、dev.sh、openapi→TS 客户端管线 | `./dev` 双端可起 |
| T02 | A03 索引器 | 扫描+哈希+`_统计.json` 交叉核对 + unavailable 检测 | style-indexing 全场景 |
| T03 | spike 解析器入库 | token_parser（6 字段）+ 分集适配器 + 119 补标队列 + 矩阵 169/24/53/95 落库 | style-indexing/发现 前置 |
| T04 | 引擎注册表 | Contract 校验 + engines/riso 登记（D3 抽取）+ fixture 校验 | engine-registry |
| T05 | drafts API + 向导 UI | 5 步向导、草稿、恢复、materialize | wizard 前 4 场景 |
| T06 | 导入参考项目 | 读 task.json→46 节点只读画布（@xyflow，7 组） | wizard 导入场景 |
| T07 | FTS5 搜索 + chips + 角标 | trigram 虚表、同义词、7 chips、状态角标 | style-discovery |
| T08 | 推荐 12 + 长尾 | 评分公式、冷启动、换一批/相似/随机 | style-discovery |
| T09 | 预演管线 | Playwright 常驻 Chrome + 页面内队列 + 缓存(含 engine_sha) + 占位 | previs |
| T10 | 对比托盘 + A05 门 | 托盘≤4、自定义标题重渲、tokens 摘要、impact 预估、主选规则 | style-selection |
| T11 | 任务卡编辑器骨架 | 四表只读渲染 + 校验按钮 + 导入导出 | task-card-editor 骨架场景 |
| T12 | 事件流 + 审计雏形 | SSE 通道、audit_log 落库 | platform SSE 场景 |
| T13 | 补标队列 UI | 119 条待补列表、逐条表单、完成后解锁 | style-selection 残缺场景 |
| T14 | M0 硬化 | 环境断言、错误页、性能回归线（首屏 1s/8s） | test-strategy §7 |
| T15 | M0 验收演示 | 按 §10 演示脚本跑给老板 | 规格 §13 M0 验收句 |

### 4.3 M0 出口条件

规格 §13 M0 验收句全绿 + 对应 6 个 .feature 文件场景全绿 + 演示通过 → `main` 打 tag `m0`。

---

## 5. 风格选择器方案

### 5.1 A03 索引与 ID（D1/D5）

- 扫描 `风格提示词/<10 个集合目录>/*.md`；`kind=prompt`；`示例/` 下条目 `kind=example`。
- ID = 集合前缀 + 文件名排序序号（`O88`、`L28`）；sha256/bytes/lines 逐条记录；`has_cover` = 同名 `.jpg`（同目录或 covers/ 子目录），**断言总数 = 193**，否则 A03 失败（与 `_统计.json` 双重核对）。
- 输出 `adapters/style-index.json` + `styles` 表；`entries=343` 断言。

### 5.2 语义族初始映射（粗映射，标注队列负责校准）

| 来源集 | 主族 | 副 | 备注 |
|---|---|---|---|
| O 奥斯卡98 | photo | print | 98 条全解析 ✓ |
| L Lemo | photo | print | 59 条全解析 ✓ |
| M 动态 | infographic | — | 仅 4/38 可解析 |
| K 卡通 | cartoon | — | 0/38，进补标 |
| X code-video | infographic | pixel | 31/31 ✓ |
| A-G 代码样片 | pixel | infographic | 9/26，17 条补标 |
| V mg-styles | infographic | print | 15/15 ✓ |
| Z 中国风 | ink | — | 1/15，进补标 |
| H 现成版式 | print | — | 5/12 |
| R 参考学来 | print | collage | 0/7，进补标 |

引擎映射：`riso→[print,collage]`、`code-video→[infographic,pixel]`、`ink→[ink]`；`photo/handdrawn/cartoon/threedee` 无引擎（photo 族 98+59 条虽然 tokens 完整但**当前不可主选**——这是引擎工期风险的直接体现，已列入 PRD R1）。

### 5.3 token 解析器（A06 前置）

- 字段：palette(hex 列表) / texture / screen(angle,period) / motion(pacing) / type / composition。
- 策略：通用启发式（hex 正则 + 关键词词典）+ **分集适配器**（L 的 11 英文小节、O 的技法/导演/分镜小节、A-G 的 JS 参考代码直接读常量）；解析 ≥3 字段 = complete。
- 适配器是纯函数：`parse(md_text, collection) -> tokens + evidence`；单测直接跑全库断言 spike 数字。

### 5.4 推荐 12（评分公式已由规格锁定）

`score = 0.55·BM25 + 0.20·briefOverlap + 0.15·constraintFit + 0.10·usagePrior − 0.10·familyRedundancy`

- BM25 用 FTS5 `bm25(styles_fts)`；briefOverlap = jieba 提取文案关键词与 search_text 交集占比；usagePrior 来自 style_picks 历史（无历史=0）；familyRedundancy = 同主族已入选 >3 时递减。
- 候选集 = `tokens_status=complete AND engine_status=available`；冷启动按 5 个可用族各 1–2 条。
- 理由模板：`命中关键词 {k1,k2} · 满足 {约束} · 与你历史选择 {风格} 相近`。

### 5.5 预演渲染（D2）

- Playwright(Python) 启动系统 Chrome 单实例常驻；页面内任务队列串行执行：`goto(engine.entry.film + ?mode=previs&tokens=<payload>)` → 等待 `window.__PREVIS_DONE__` → CDP 截图 512×288 / 1024×576。
- tokens payload = `tokens.lock` 同源数据（只读 visual_tokens），保证"预演即生产"。
- 与 A04 共用 chrome-queue；缓存键 `style.sha+engine.sha+rendererVer`。

### 5.6 对比托盘与长尾

- 托盘 ≤4，状态存 draft；「用我的标题重渲」= 取文案第一句 ≤12 字传入 previs 样片参数。
- 相似 = FTS5 bm25 top-8 排除自身；随机 = seeded RNG（种子入库，可复现），理由模板注明"随机探索：因 {标签/来源集} 与当前上下文相关"。

---

## 6. 首屏线框与交互状态

### 6.1 卡片状态机（8 态全覆盖）

| 状态 | 卡面表现 | 可主选 | 进推荐 |
|---|---|---|---|
| 加载 | 骨架屏（≤300ms） | — | — |
| 有封面 | jpg 直出 | ✓(还需引擎) | ✓ |
| 预演中 | 16:9 占位 + 细进度 | ✓(完成后) | ✓ |
| no_preview | 斜纹 +「无预演」 | ✗(残缺时) | ✗ |
| 预演失败 | 斜纹 +「重试中 2/2」 | 保守 ✗ | ✗ |
| 已选 | 金色描边 + 主风格角标 | — | — |
| 对比中 | 对比勾选角 + 托盘序号 | ✓ | ✓ |
| 引擎未就绪 | 灰角标「引擎未就绪」 | ✗ | ✗ |
| 待补标 | 黄角标「待补标」+ 缺失字段 tooltip | ✗ | ✗ |

### 6.2 空态与缺文件

- 搜索无结果：`未找到「xx」· 试试同义词：水墨↔中国风` + 最近浏览。
- 条目缺文件：卡片保留、角标「缺文件」、详情显示原 path；点击详情给重登记入口。
- 引擎未就绪族被筛选命中时：列表顶部横幅 `这些风格需要登记引擎（photo/cartoon/…）· [登记引擎]`。

### 6.3 键盘与焦点

`↑↓←→` 网格移动 / `Enter` 详情 / `C` 对比 / `S` 主选（弹确认含 impact 预估）/ `Esc` 逐层返回；焦点环可见，全部卡片 alt = `ID 名称 一行视觉语法`。

---

## 7. 引擎包方案

### 7.1 磁盘布局与 Contract（D3）

```
engines/riso/
  contract.json        # 规格 §3.3 的 Engine Contract 实例
  entry/still.html     # 抽自 rumor-39s/src/still.html
  entry/film.html      # 抽自 rumor-39s/src/film.html，新增 ?mode=previs|proxy
  assets/…             # shader/工具 js（含 base64 字体加载接口，运行时注入 embed.css）
  fixture/S01@6.45.png … fixture/meta.json   # 基准图 + 容差(如 SSIM≥0.99)
```

- C01 校验：加载 entry → WebGL2 编译/链接 → 用 fixture 参数渲 1 帧 → 与基准图比 SSIM ≥ 容差 → 写 `engine_build.json`（entry sha、capabilities、通过标志）。
- 字体注入：D02/E05 渲染前把 embed.css 注入页面（`?embed=<url>` 或 POST），引擎不硬编码字体。

### 7.2 首批三包与排期

| 引擎 | 族 | 交付 | 来源 |
|---|---|---|---|
| riso | print/collage | M0 | rumor-39s 抽取（D3） |
| code-video | infographic/pixel | M1 | 新写：终端网格/扫描线/等宽字 + glitch；fixtures 用 AG 样片基准 |
| ink | ink | M2 | 新写：宣纸底 + 墨晕 shader；fixtures 用 Z 集人工标注样例 |

### 7.3 timeline_binding.json（E03 产物）

```json
{
  "engine": "riso", "engine_sha": "…", "api_version": "1.0",
  "fps": 24, "frames": 948,
  "scenes": [{ "id": "S01", "startFrame": 0, "endFrame": 210,
               "camera": {"zoom":[…], "pan":[…], "anchor":[…]},
               "engineParams": {"plates": ["#3D5588"], "misregistration": {"dx": 2}} }],
  "events": [{ "at": 6.45, "role": "…", "allowSnap": true, "tolerance": 0.1 }],
  "transitions": [{ "atFrame": 210, "type": "shape_match", "note": "…" }]
}
```

引擎在 render/proxy/previs 三模式都只读 binding + tokens.lock，不读 task.json —— 引擎与业务解耦的边界线。

---

## 8. 代理 QA 口径（E06）

- 渲染：`?mode=proxy&fps=12&scale=0.25` → 480×270；帧数 = round(duration×12)（参考 474）。
- 实测标定（参考片）：均值 2.10 / p95 7.31 / 最大 28.61；切点 13.51 / 23.56 / 28.61；死开头 = 14 代理帧。
- 阈值表（medium，代理口径）：静态段 ≥6 帧 diff<0.20；切点 >8；首 6 帧需有变化；黑帧 lum<8 硬失败；超 p95 且无 transition → 警告。
- pacing 覆盖：slow 静态 12 帧/切点 6；fast 静态 4 帧/切点 12；覆盖写进报告。
- **E06 报告 schema**：

```json
{ "medium": "proxy", "thresholds_used": {…}, "pacing": "medium",
  "frameDiff": {"mean":2.1,"p95":7.31,"max":28.61},
  "cutSpikes": [{"frame":216,"diff":13.51,"hasTransition":false}],
  "staticRuns": [{"from":0,"to":13,"intentionalHold":false}],
  "pxPerFrame": [{"scene":"S01","px":4.2}], "blackFrames": [], "dupFrames": [] }
```

---

## 9. 失效图与 dry-run

### 9.1 边常量（edges.py，唯一权威，翻译规格 §4.8）

```python
EDGES = [
  ("A02","A01","data"), ("A04","A01","data"), ("A04","A02","data"), ("A04","A03","data"),
  ("A05","A04","data"), ("A06","A05","data"), ("A07","A02","data"), ("A08","A02","data"),
  ("B01","A01","data"), ("B01","A07","data"), ("B02","B01","data"), ("B03","B02","data"),
  ("B04","A06","data"), ("B04","B02","data"), ("B05","B04","data"),
  ("B06","B01","data"), ("B06","B02","data"), ("B06","B03","data"), ("B06","B04","data"),
  ("B06","B05","data"), ("B06","A05","data"), ("B06","A06","data"),
  ("B07","B06","data"), ("B08","B07","trigger"),
  ("C01","A06","data"), ("C01","B08","trigger"),
  ("C02","A06","data"), ("C03","C02","data"), ("C03","B06","data"), ("C04","C03","data"),
  ("C05","A06","data"), ("C05","B04","data"),
  ("D01","B06","data"), ("D01","C05","data"), ("D01","C01","data"), ("D01","B08","trigger"),
  ("D02","D01","data"), ("D02","C01","data"), ("D02","C04","data"),
  ("D03","D02","data"), ("D04","D02","data"), ("D04","D03","data"), ("D04","B06","data"),
  ("D05","D04","trigger"), ("D05","D03","trigger"),
  ("E01","B06","data"), ("E01","D05","trigger"),
  ("E02","E01","data"), ("E02","C05","data"),
  ("E03","E01","data"), ("E03","E02","data"), ("E03","C01","data"), ("E03","C04","data"), ("E03","C05","data"),
  ("E04","E03","data"), ("E04","B03","data"),
  ("E05","E03","data"), ("E05","C01","data"), ("E05","C04","data"), ("E05","C05","data"),
  ("E06","E05","data"), ("E07","E05","trigger"), ("E07","E06","trigger"),
  ("F01",None,"data"),   # 输入=项目目录
  ("F02","E03","data"), ("F02","C01","data"), ("F02","C04","data"), ("F02","C05","data"),
  ("F02","F01","data"), ("F02","E07","trigger"),
  ("F03","F02","data"), ("F04","F03","data"),
  ("F05","F04","data"), ("F05","F02","data"), ("F05","E06","data"), ("F06","F05","trigger"),
  ("G01",None,"data"), ("G02","G01","data"), ("G02","B06","data"),
  ("G03","A08","data"), ("G03","G02","data"), ("G04","G03","data"),
  ("G05","G01","data"), ("G05","G02","data"), ("G05","G04","data"),
  ("G06","G05","data"), ("G06","F06","order"),
  ("G07","G06","data"), ("G07","F04","data"), ("G07","F05","data"), ("G07","F06","data"), ("G07","D05","order"),
]
```

### 9.2 传播算法

1. 节点 X 产物/参数变化 → 以 X 为源沿 **data 边** BFS（方向 from→to）收集下游集 D。
2. D 中普通节点 → `invalidated`；门节点 → 计算 content_hash，与最近 approval 比对：不一致 → `stale`（下游继续沿门传播 blocked）。
3. trigger/order 边不传播内容失效，只参与就绪判定。
4. dry-run = 用 patch 后的假设哈希跑同一算法，**不落库**。

### 9.3 两个基准用例（fixture 级断言）

- `crf 17→19`：invalidated = {F04,F05,F06,G07}，stale_gates = {F06,G07}，G06 不动（order）。
- `A01 文案变更`：B 阶段起全链 invalidated；stale_gates = {B08,D05,E07,F06,G07}。

---

## 10. M0 验收演示脚本（老板亲手走）

1. `./dev` 起服务 → 打开 :3000 → 「新建项目」→ 5 步向导。
2. 第 3 步：搜「水墨」→ 命中 Z 集；看角标（待补标/引擎未就绪）；展开全部 341 滚动；矩阵数字 169/24/53/95 显示在库信息条。
3. 选 4 条进对比 → 同样片并排 → 选 1 条 riso 族设为主风格 → 看到 tokens 摘要。
4. 导入 rumor-39s → 46 节点只读画布 → 点 D02 看到 3 张静帧。
5. 选卡通族风格走第 5 步 → 生成按钮置灰 + E_ENGINE_UNAVAILABLE。
6. `./build` → 双击启动单进程 → 重复 1–2（发布形态检查）。

## 11. 需要老板确认的默认项

D1–D6（见 §0 表）。全部默认生效——你回复"确认"或指出要改的编号即可。**确认后我立即开始 T01（脚手架），并按 TDD 纪律推进 M0。**
