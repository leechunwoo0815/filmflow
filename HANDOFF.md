# FilmFlow 交接文档（HANDOFF）

> 写于 2026-11-02 · 交接人：开发 Agent（v0.1.3）· 接手人：下一位 Agent / 编辑器
> 本文件是**唯一权威的接手入口**。规格（`../filmflow-web-agent-prompt.md`）是宪法，但**已经落后于实现**的地方以本文 §9 为准。
> **深化需求**：v2 补充 PRD 见 [docs/prd/PRD-002-production-workbench.md](docs/prd/PRD-002-production-workbench.md)（30 FR / 场景 DSL / 两级执行 / R2–R4 路线图）。

---

## 1. 一句话状态

FilmFlow 是一个**本地代码动画"印厂控制台"**：46 节点 DAG 把「文案 → 风格 → 任务卡 → 静帧 → 分镜 → 948 帧渲染 → 音频 → 交付」全流程真实跑通（参考片 rumor-39s 实测 46/46 succeeded，master.mp4 39.5s 带音轨）。**它是可靠的"执行与审批引擎"，但还不是创作者的工作台**——缺口见 §10。

| 项 | 值 |
|---|---|
| 版本 | v0.1.3（tags: `m0`/`v0.1.0`/`v0.1.1`/`v0.1.2`/`v0.1.3`） |
| 仓库 | `~/cc-projects/ai-v/filmflow/` |
| 规格/PRD | `../filmflow-web-agent-prompt.md` · `../filmflow-prd.md` |
| 测试 | 26 自动化 + Playwright UI E2E 8 场景（全绿） |
| 主题 | **白天默认**、夜间可切（ADR-0004） |
| 双语 | zh/en（`web/src/lib/i18n.tsx`） |

---

## 2. 五分钟上手

```bash
cd ~/cc-projects/ai-v/filmflow
./dev.sh          # API :7860 + Web :3000
# 浏览器 http://localhost:3000
# API 文档 http://127.0.0.1:7860/api/docs
```

环境依赖：macOS · Chrome 156（`CHROME_PATH` 可覆盖）· ffmpeg 9 · Python 3.13 · uv · pnpm（Node ≥22）。

冒烟验证（服务在跑时）：

```bash
cd server && uv run pytest tests -q                      # 26 项
cd .. && uv run --project server python scripts/e2e_ui.py # UI 8 场景 ~15s
uv run --project server python scripts/smoke_m1.py        # API 全链冒烟
uv run --project server python scripts/drive_run.py <runId> <projectId>  # 全链驱动（自动批门）
```

---

## 3. 已验证能力（有实证）

| 能力 | 证据 |
|---|---|
| 341 条风格真实入库（10 集计数、193 封面直出、矩阵 173/20/45/103） | `tests/integration/test_style_index.py` + API |
| 「水墨」同义词搜索命中 Z 集 15 条 | BDD `style-indexing.feature` + UI E2E |
| 推荐 12（评分公式、冷启动、长尾） | `/api/recommend` |
| 预演渲染（riso/code-video/ink 三引擎，同源 shader，缓存键含 engine sha） | 实测渲染 + `engines/*/fixture` |
| 风格选择器完整交互（搜索/chips/对比托盘/设主风格/角标/详情） | UI E2E 场景 4-5 |
| 5 步向导 → 46 节点画布（drafts 作用域 + materialize） | UI E2E 场景 1-6 + `test_wizard_flow.py` |
| RunEngine：caps / 锁 / 门活同步 / content_hash 失效 / 断点续跑 | 真实全链（run #1 经 10+ 次 resume） |
| 真实渲染：948 帧 Chrome → ffmpeg → Y-SSIM QA → 代理帧 474 帧运动 QA | run #1（49 产物） |
| 音频：voice ingest → 对齐（whisper 缺失时手动回退）→ 混音 loudnorm → −16LUFS 过审 → master 带 AAC | run #1 |
| G07 门后真实打包（manifest + 哈希 + 审批） | run #1 `out/film/master.mp4` |
| 双语 UI + 昼夜主题 | E2E + 截图 |
| 缺帧/黑帧/引擎未就绪/审批阻断夹具 | `test_frame_fixtures.py` 等 |

**未验证/仅表面成立**：见 §9「已知硬缺口」——尤其**新项目真实出片**（参数化 film 未接入，见 9.1）。

---

## 4. 架构导览

### 4.1 目录地图

```
filmflow/
├─ server/                  Python 3.13 + FastAPI + SQLModel
│  ├─ app/
│  │  ├─ main.py            app 工厂（/api/docs、静态托管 web/out）
│  │  ├─ config.py          路径/端口/Chrome 探测/whisper 探测
│  │  ├─ db.py              engine（pool 20+40）
│  │  ├─ models.py          15 张表（注意：SQLModel 表名是单数小写，如 noderun）
│  │  ├─ events.py          SSE 广播 + JSONL + DB
│  │  ├─ api/routes.py      ★ 全部 REST/SSE 端点（~800 行，唯一 API 文件）
│  │  ├─ engine/
│  │  │  ├─ edges.py        ★ 46 节点表 + 90 条边（唯一权威，改动须同步规格 §4.8）
│  │  │  ├─ caps.py         auth/minCap/门授权
│  │  │  ├─ cachekey.py     EXECUTOR_VERSION（改执行器行为必须升版！）
│  │  │  ├─ invalidation.py data 边 BFS + dry-run
│  │  │  ├─ locks.py        chrome-queue/ffmpeg/port-8787
│  │  │  ├─ runner.py       子进程壳（@@PROGRESS、SIGTERM→KILL）
│  │  │  ├─ runengine.py    ★ 调度/门活同步/缓存/续跑（~450 行）
│  │  │  └─ executors/      ★ 46 执行器（__init__.py A-C + pipeline.py D-G）
│  │  └─ services/          style_index/token_parser/recommend/search/previs/engines
│  ├─ tools/validate_task.py  vendored 校验器
│  └─ tests/                unit / bdd（中文 gherkin 绑定）/ integration
├─ web/                     Next.js 15（App Router，深/浅双主题）
│  └─ src/
│     ├─ app/               page(首页)/wizard/canvas/editor/labeling/monitor
│     ├─ components/StylePicker.tsx
│     └─ lib/               api.ts / i18n.tsx / theme.tsx
├─ engines/                 riso / code-video / ink（Engine Contract + 基准 fixture）
├─ bdd/features/            16 个中文 Gherkin（style-indexing 3 场景已自动化绑定）
├─ scripts/                 smoke_m1.py / drive_run.py / e2e_ui.py
└─ docs/                    tech-plan / process / adr（ADR-0001~0004）
```

### 4.2 运行时

- **开发**：`next dev :3000`（rewrites `/api` → :7860）+ `uvicorn :7860`；Chrome/ffmpeg/whisper 由执行器 spawn；F01 帧服务在 API 进程内线程监听 **8787**。
- **发布**：`./build.sh` → Next 静态导出 `web/out` → FastAPI 挂载，单进程 :7860。
- **锁**：`chrome-queue=1`（全局串行）、`ffmpeg=1`、`port-8787`（可复用已有服务）。
- **缓存**：键 = sha256(executorVersion|params|输入产物 sha|caps)；门键 = content_hash（含 data+trigger 上游）。
- **门**：人工门 8（A05 B08 D03 D05 E07 F06 G03 G07）+ 自动门 8。门状态由 `_ready_set` **活同步**；批准后 `gate.decide` 自动重启调度；`resume` 把级联 skip 的门回队。

### 4.3 数据

- DB：`~/.filmflow/filmflow.db`（SQLite）。表名注意：`noderun` / `stonepick` 样式为**单数**。
- 产物内容寻址：`<项目>/artifacts/<sha2>/<sha>.<ext>`；项目内 `card/` `fonts/` `out/` `runs/`。
- 风格库：`~/Documents/fy-style-library/代码动画_341种风格提示词/`；索引由 A03 首次扫描生成 `adapters/style-index.json`。
- 参考项目：`~/cc-projects/ai-v/rumor-39s`（已导入 run #1，产物真实）。

### 4.4 关键文件→职责速查

| 想改什么 | 去哪 |
|---|---|
| 节点/边（增删节点、改依赖） | `server/app/engine/edges.py` + 规格 §4.8 + 别忘同步 executor 注册测试 |
| 执行器行为 | `server/app/engine/executors/{__init__,pipeline}.py`；**改完必须升 `EXECUTOR_VERSION`** |
| 调度/门逻辑 | `runengine.py`（`_ready_set` / `execute_node` / `_gate_valid`） |
| API | `api/routes.py` 单文件 |
| 风格库/解析/推荐 | `services/style_index.py`、`token_parser.py`、`recommend.py`、`search.py` |
| 预演 | `services/previs.py`（Playwright 常驻 Chrome）+ `engines/*/entry/previs.html` |
| UI | `web/src/app/*`、`components/StylePicker.tsx`、`lib/i18n.tsx` |
| 主题色 | `web/src/app/globals.css`（CSS 变量）+ `tailwind.config.ts` |

---

## 5. 关键裁决台账

| # | 裁决 | 出处 |
|---|---|---|
| ADR-0001 | Python 全栈 + OpenAPI + 深色（后改白天） | `docs/adr/ADR-0001-tech-stack.md` |
| ADR-0002 | 解析器实测矩阵 173/20/45/103（替代 spike 参考值） | `docs/adr/ADR-0002-matrix-measured.md` |
| ADR-0003 | embed.css 上限 profile 化（默认 512KB） | `docs/adr/ADR-0003-embed-limit.md` |
| ADR-0004 | 默认白天主题，夜间可切 | `docs/adr/ADR-0004-theme-light-default.md` |
| §19 补录 | F03 重复帧=警告；G07 门后真实打包；门控活同步；style-index 为 A03 产物 | 规格 §19 |

**待老板书面追认**：ADR-0002 / 0003 + 上述 §19 四项（已于交付报告提请）。

---

## 6. 测试体系

- 单元 15：DAG 核心（边方向/拓扑/caps/缓存键/失效/锁/进度解析/执行器注册完整性）。
- 集成 11：A03 真实库（341/193/计数/ID/矩阵/S 同义词）；向导 materialize（含 E_ENGINE_UNAVAILABLE）；缺帧/黑帧/干净项目夹具。
- BDD 3：`style-indexing.feature` 自动化绑定（pytest-bdd 中文 parsers）。
- UI E2E 1 脚本 8 场景：首页→向导→选择器搜索→设主风格→生成→46 节点画布→EN→导入。
- 手工脚本：`smoke_m1.py`（API 链）、`drive_run.py`（全链驱动，自动批门）。

**纪律**：改任何行为先改/加测试；改执行器必须升 `EXECUTOR_VERSION`；改节点/边必须同步规格与 `test_dag_core`。

---

## 7. 踩坑清单（血泪 16 条，接手续命）

1. **边表方向**：`EDGES` 是 `(from上游, to下游, 类型)`。当初全写反过，被测试抓住。改边先跑 `test_dag_core`。
2. **React 19 + Playwright `fill()` 不触发 onChange**（原生 setter 绕过）。自动化输入用 `click + keyboard.type`。
3. **Next dev 水合竞态**：fill 早于水合会被 React 回写。等 800ms+ 或键盘输入。
4. **SQLModel 表名是单数**（`noderun` 不是 `node_runs`）。
5. **SQLAlchemy 连接池**：曾 15 连接超时（内联 `Session(engine)` 泄漏已修）；池已扩 20+40。
6. **GLSL ES 3.0 无 int→float 隐式转换**：shader 模板数值必须 `toFixed(1)`。
7. **WebGL quad 顶点**：两三角形 6 顶点写错一个会黑半屏。
8. **GitHub raw 的 NotoSansSC 是 LFS/截断（401KB）**：用 jsdelivr（16.9MB，30890 字形）。
9. **fontsource 是 unicode-range 切片**，且无拉丁字形；pyftmerge 合切片会炸（表不兼容）。正解：变量字体 instancer → subset。
10. **子集化字符集要剔控制符**（`\n` 永不进 cmap，否则永远“缺字”）。
11. **门状态不会自己变**：`_ready_set` 活同步（valid→succeeded / 无效→blocked+gate.stale），批准后 `gate.decide` 自动重启调度；resume 要回队被 skip 的门。
12. **G07 双身份**：既是 reapprove 人工门又是打包执行体；“纯门”executor 是 `gate`（noop），有执行体的门批准后要走真实执行。
13. **F02/E05 渲染页不自动退出**：headless Chrome 渲染完挂住，靠 `out/DONE` 标记早退 + 超时兜底。
14. **8787 端口复用**：历史进程残留会 EADDRINUSE；实现已支持“健康检查通过则复用”。
15. **F03 重复帧**：参考片有意停顿占 28.8%，硬门会误杀→按 §6.2 降为警告（缺失/黑帧仍硬失败）。
16. **预演是 Playwright 常驻 Chrome（channel=chrome）**，与生产渲染共享 `chrome-queue=1`；`executable_path` 必传系统 Chrome，否则报“Executable doesn't exist”。

---

## 8. 如何复现一次完整出片（给下一个 Agent 的冒烟路线）

```bash
# 1. 导入 + 启动驱动（自动批门、准备音频、注入手动对齐回退）
curl -s -X POST http://127.0.0.1:7860/api/projects/import -H 'Content-Type: application/json' \
  -d '{"root":"/Users/litianyu/cc-projects/ai-v/rumor-39s"}'
# 返回 run_id/project_id 后：
uv run --project server python scripts/drive_run.py <run_id> <project_id> --timeout 2700
# 约 25-40 分钟（948 帧 SwiftShader）：DONE 后检查 out/film/master.mp4 与 /api/runs/<id>/report
```

---

## 9. 已知硬缺口（诚实、按严重度）

### 9.1 🔴 P0：新项目「真实出片」是断的
- `D02` 用 `entry.still`（rumor 原版 still.html），`F02/E05` 用 `entry.film`（rumor 原版 film.html）——**内容写死**。
- 参数化入口 `entry/still_spec.html` 已存在（spec 驱动：文字块/版色/相机/套准）但**没有任何执行器调用它**；`film.html` 没有参数化版本。
- 结论：向导里选 AG/M 等新风格 → 预演正确，但 D02/F02 会渲染出 rumor 的画面。**修复是下一阶段第一优先级**（见 §10 P0-1）。
- 另：`_engine_url` 的 `embed` 参数已按项目字体解析（`fonts/noto-sans-sc/embed.css` 优先）。

### 9.2 🟠 P1：创作迭代不是"秒级"
- 改一句文案 → 需重跑 C03/C04 → D01/D02 → E01-E07，分钟级。缺"当前句单帧热预览"。
- 任务卡编辑器是表格；无分镜/时间轴可视化编辑；改完只能靠 next() 保存（无 autosave/undo）。

### 9.3 🟠 P1：审片与音频工具是"过门"而非"创作"
- 无全屏放映/逐帧批注/批注导出（时间码）。
- 音频：G02 手动打点=JSON；无波形↔事件对齐 UI、无拍点吸附、whisper 模型无首跑下载器（只有 E_MODEL_MISSING）。

### 9.4 🟡 P2：引擎与风格覆盖
- photo 族 157 条 tokens 完整但无引擎；`producible=61/341`。
- M 集解析 4/40、K 0/38、R 0/7 —— 补标队列 123 条需人工（UI 已备）。
- 场景语法仍是硬编码（手/箭头/滚轮写在 rumor harness 里）——无"图形组件库"。

### 9.5 🟡 P2：交付链路
- 无多比例导出（9:16/1:1）、无 SRT/VTT 字幕、无封面帧、无平台规格检查（时长/码率/响度/封面）、无"交付包"发布预设（manifest 有，zip 打包执行器在 G07 内已产 manifest）。

### 9.6 ⚪ P3：工程鲁棒性
- 长任务进程崩溃后 Chrome 残留（cancel 路径覆盖，崩溃路径未清理）；渲染队列未持久化（重启后节点回队但 Chrome 需手动清）。
- 监控页仅表格（帧差曲线数据在 E06 报告里，未画图）。
- 无磁盘配额管理（F02 只查 ≥5GB）。

---

## 10. 深化路线图（资深视频创作者视角，按生产力价值排序）

> 原则：**不动已稳定的执行/门/缓存内核**（它是可靠底座），所有扩展围绕"创作循环"与"交付闭环"。
> 详细需求、验收标准与 6 个待裁决决策见 [docs/prd/PRD-002-production-workbench.md](docs/prd/PRD-002-production-workbench.md)（本节的展开版）。

### P0-1 参数化渲染链（让新项目真出片）
1. `D02`：项目有 `still_spec.json` → 改走 `entry.still_spec`（需把 spec 作为 URL 可访问的 artifact，如 `http://127.0.0.1:8787/project/artifacts/...json`）。
2. 新写 `entry/film_spec.html`：读 `card/timeline_binding.json`（场景/事件/相机/转场），逐帧渲染（同 riso-core shader），支持 `mode=render|proxy`。
3. `E05/F02`：绑定存在 → 走 `film_spec`；`meta.imported` 项目保留原版 harness。
4. 验收：用 AG1 建 5 秒新项目 → 全链跑通 → 成片里是**用户文案**而非 rumor 内容。（新增 BDD 场景）

### P0-2 秒级创作循环
- 海报级"单帧热预览"：编辑器右上角"预览当前句"→ `still_spec` 直渲 1 帧（复用已缓存字体，~2s，走 chrome-queue）。
- 文案改动的"影响预估"已有 dry-run，接进编辑器（保存前显示 N nodes / M gates）。

### P1-1 审片播放器（导演模式）
- 全屏播放 master/intermediate；逐帧步进；帧上批注（框选+文字+时间码）；批注列表导出 JSON/CSV（可回灌到时间轴高亮）。

### P1-2 时间轴编辑器
- 可视化轨道：场景块（拖拽改 start/end）＋事件标记＋音频波形（解码 card/voice.wav 与 music.wav 画 canvas 波形）＋拍点。
- 与 task.json 双向绑定；保存走现有 `PUT /projects/:id/task` + validator。

### P1-3 音频工作台
- G02 波形对齐 UI（拖字幕段落对齐语音）；whisper 首跑下载器（ggml-medium，带 sha）；loudness 目标可调（−14/−16 平台预设）。

### P2-1 引擎扩容与图形语法库
- `photo` 引擎（剧照式：图片/渐变/文字/电影调色 + 颗粒）；复用 Engine Contract。
- `assets/scene-kit.js`：纸页、箭头生长、印章、网点块、错版抖动——参数化组件，供 still_spec/timeline_binding 引用；riso 参考片的手/滚轮等实体迁移为组件。
- 补标队列推进（老板已指派人？）：M/K/R/Z 集 123 条。

### P2-2 交付与发布
- 导出预设：1920×1080 / 1080×1920 / 1080×1080（同 binding 不同画幅重渲或智能裁切）；SRT/VTT 由 alignment.json 生成；封面帧（D02 静帧选用）；平台检查清单（时长、码率、LUFS、封面、字幕）。
- G07 扩展：生成交付 zip（成片+字幕+封面+manifest+审批报告）。

### P2-3 模板与系列
- 项目模板（profile+tokens+task 骨架）；"同风格批量"：文案数组 → 多条 Run 排队 → 批量导出。

### P3 工程
- 渲染防抖/崩溃清理（启动时扫描孤儿 Chrome profile 与 8787 服务）；监控图表（E06/E05 数据可视化）；磁盘配额与清理策略。

---

## 11. 接手工作守则

1. **规格 §19 + ADR 是宪法**；本文件 §9 是规格的勘误补丁。任何与既有裁决冲突的改动，先记录 ADR 再动手。
2. **TDD**：行为改动先写失败测试；执行器改动必须升 `EXECUTOR_VERSION`（否则缓存会返回旧行为，这是本仓库最容易踩的隐蔽坑）。
3. **文档同步三件套**：改节点/边→规格 §4.8+§17；改行为→对应 `.feature`；改数据/接口→tech-plan §2。
4. **UI 自动化**：Playwright 用系统 Chrome + 键盘输入（见 §7-2/3）。
5. **验收**：任何"完成"的申报必须附：测试输出、真实产物路径（sha/时长）、UI 截图、API curl 结果。参考 `run #1` 的证据链标准。
6. **不要推倒重来**：执行引擎/门/缓存/QA 是已验证底座；深化应叠加在它上面。

---

## 12. 交接检查表（接手第一小时）

- [ ] `./dev.sh` 起服务；`/api/health`、`:3000` 正常
- [ ] `uv run pytest tests -q` → 26 passed
- [ ] `uv run --project server python scripts/e2e_ui.py` → 8 场景全绿
- [ ] 打开 run #1 画布，确认 46 绿 + 审批历史（含 B08 驳回→重批）
- [ ] `out/film/master.mp4` 39.5s 带音轨
- [ ] 读 §9 缺口 + §10 路线图，与老板确认下一阶段 P0 范围（建议 P0-1 参数化渲染链）
