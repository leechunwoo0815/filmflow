# R2.0 开工计划（能出片）

> 2026-11-02 · 接手基线审计后制定 · 依据 `QODER_PROMPT.md`、`docs/prd/PRD-002-production-workbench.md`、`docs/adr/ADR-0005-v2-ratification.md`
> 范围：FR-20/21/22/23/24/25/29/30。不做时间轴、审片、音频 v2、资产库、批量、photo 引擎。
> 冻结项：46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；只加 3 条 data 边。
> **进度（2026-11-02）**：Phase 0.1–8 已完成，R2.0 DoD 通过（见 `docs/process/r2-acceptance.md`）；R2.5 FR-26 已完成（见 `r2_5-plan.md`）。5s 新项目已跑通参数化静帧与 E03–F06；改 S02 文案后新 Run 只渲 66/120 帧（S01 复用，0..53 帧哈希不变），40s 实测改 S03 只渲 93/960=9.69%、F02 墙钟 13.05%。Phase 5 预览（attached p50 1.31s/p95 1.44s，片段 12.7s，缓存 5ms）与 Phase 6 档位（D02 review/draft、E05 720p/24、F02 only-final、切档不重跑）与 Phase 7 恢复（kill -9 后 22.3s、attempts=1）与 Phase 8 黄金（5s/15s/40s SSIM 1.0、干净 rumor 46/46）已完成。R2.0 收尾，不自行开始 R2.5。

---

## 0. 基线审计（2026-11-02 实测）

| 项 | 结果 |
|---|---|
| API / Web | `127.0.0.1:7860` / `:3000` 均在运行 |
| `pyproject` 单测 | **28 collected**；修复前干净首跑 **25 passed / 3 failed**（BDD `no such table: style`）；Phase 0.1 修 `conftest` 后 **28 passed**（2 项向导集成需 API 在跑） |
| UI E2E | 8 场景 / 9 检查全绿（20s） |
| API 冒烟 | 通过；46 节点全 cached（0s/节点），画布 **46 节点 / 90 边** |
| 参考成片 | `rumor-39s/out/film/master.mp4` 1920×1080 / 24fps / 948 帧 / 39.500s / AAC 48kHz mono |
| 边表 | E04 出边为空；C05 上游只有 A06/B04；总数 90（目标 93） |

结论：**执行底座是可靠的；“新项目出片”链路不是“差一点”，而是多处断点串成的 P0。** 交接文档的方向正确，但低估了场景文本生成、短项目渲染退出、非 riso 引擎入口三处问题。

---

## 1. P0 问题（按修复顺序）

### P0-1 新项目渲染参考片（已知，但比文档更深）
- `pipeline.py:201` D02 用 `entry.still`；`:316` E05、`:420` F02 用 `entry.film`。
- D02 即使改投 `still_spec.html`，URL 也没有传 `spec=`（`:201` 只有 `scene=&t=`）→ 参数化入口仍拿不到 D01 规格。
- `still_spec.html:48-50` 缺 program 时回退 `s.meaning` / `'风'`，违反“缺 program → `E_PROGRAM_INVALID`，不回退”。
- `film.html:24` 写死 `FPS=24, FRAMES=948`；`:947` 写死 rumor 的 `ALL_TEXT`；5 个场景函数 s01–s05 全部写死 rumor 文案与版式。
- `film.html:983` 只有 `end >= FRAMES` 才 POST `/done`。5s 项目 `end=120 < 948` → 永不 DONE；F02 等待 1800s 超时。**这是当前 5s 新项目 F02 的直接死因。**
- 非 riso 引擎 `contract.entry.film` 指向 `entry/previs.html`（静态预演页，无 `mode=render/proxy` 循环）→ ink/code-video 新项目会挂住或渲染错内容；当前没有 `E_ENGINE_API_UNSUPPORTED` 阻断。

### P0-2 新项目场景生成丢文案（交接文档未提）
- `__init__.py:216-234` B02 用 B01 的 `per_sentence` 只算时长，**没有把句子写进场景**：`meaning/operation` 为空（`:232-233`）。
- 2 句「风从纸上起。纸不动，风先动。」实测生成 4 个场景、总长 5.6s（不是 profile 的 5s）：S01 0.8 / S02 0.8 / S03 2.0（默认填充）/ S04 2.0；且 4 场全部无文本。
- 后果：即使 D02/F02 接上参数化入口，画面也没有用户文案。**必须先把 `script.doc → scenes.source_span → program.layers` 打通。**

### P0-3 F02 只要帧存在就提前成功
- `pipeline.py:414-418`：`out/frames` 齐全 → 直接返回“无需重渲”。
- 改文案/改场景后帧文件仍在 → F02 永不重渲，F03 也检查不出内容错误。这是“改一句等半小时”之外更严重的正确性问题，也是 FR-22 的前置。

### P0-4 边表缺陷
- `edges.py:105-106` E04 仅入边；`transitions.json` 无人消费。
- `edges.py:96` C05 上游缺 B05；`__init__.py:442` C05 只锁 A06/B04，改排版不失效。
- 规格 `../filmflow-web-agent-prompt.md` §4.8 仍是 90 边旧表，必须同步为 93 边并记录。

### P0-5 `task.json` 仍是侧信道
- 编辑器 `routes.py:794-815` 直接 PUT；B02/B03/B06/D01/E01 直接读；B06 又写（`__init__.py:281-306`）。
- `task.json` 不在缓存键里；改文档后 Run 可能命中旧缓存。
- 没有 `script.doc` / `timeline.doc` / 版本 / 409 / diff / 撤销；Run 启动没有文档快照。

### P0-6 预览在现有架构下不可能达标
- F02 一次性持有 `chrome-queue` 跑完整个 Chrome 进程；预览请求只能等整片结束，p50 ≤2s 不可能。
- 没有独立的 PreviewService、优先级队列、预览缓存、PREVIEW 水印、取消/防抖。
- 要让预览在 F02 运行中达标，必须让批渲染在**帧边界**让位；仅靠加锁排队做不到。

### P0-7 档位 / final 校验缺失
- 只有 `project.profile.json`，没有 `render.profile.json`；F02 固定 1920×1080/24。
- E05 固定 12fps/480p；draft/review/final 未建模；G07 不校验 F02 是否 `profile=final`。

### P0-8 队列 / 崩溃恢复缺失
- `models.py:171-179` `Job` 只有模型，全仓无写入；`runengine.py:22-23` `ACTIVE/CANCELS` 是内存态。
- `main.py:16-19` 启动只 `init_db()`，不扫描 `running/leased`，不清理孤儿 Chrome/8787/ffmpeg。
- Chrome profile `/tmp/ff-chrome-{node_id}` / `/tmp/ff-{node_id}` 不含 run/job，互相踩踏风险。

### P1 问题（随阶段顺手修，不扩范围）
- **测试隔离**：`conftest.py` 只在 `isolated_db` 里 `init_db()`，BDD 不用该 fixture → 干净环境首跑必红。
- **路径安全**：`pipeline.py:43-50` 的 `translate_path` 未做 `..` 归一化；`routes.py:258` 用字符串 `startswith` 做根白名单，存在同前缀兄弟目录绕过。
- **文档失真（Phase 0.1 已修）**：README 已澄清“参考片全链已通 / 新项目参数化进行中”；测试计数已更新为 52；交接文档已补齐 B02 丢文案、film.html 短片挂起、非 riso 引擎入口等新坑（见 `HANDOFF.md` §5）。
- **D02 只渲前 3 场**（`pipeline.py:185`）属 FR-26（R2.5），R2.0 的 5s 样片若 4 场需明确取舍。
- **G05/G06**：`amix duration=first` 会把音乐截到口播长度；G06 同步偏差是 `min(abs(start-0))` 伪计算。R2.5 FR-27 处理；R2.0 的 final QA 不得再用它“假通过”，至少要显式标注 `approximate`。
- **UI**：编辑器无自动保存/撤销/版本/冲突；向导默认 39.5s，没有 5s 预设。
- **黄金基线缺失**：没有 `fixtures/golden/`、`golden_run.py`、视觉回归和 BDD 新场景。

---

## 2. 关键架构决定：RendererSession（拟记 ADR-0006）

**决定**：R2.0 新项目渲染统一走一个常驻 Playwright 驱动的系统 Chrome 会话（`RendererSession`），由 Python 侧调度：
- 页面暴露 `window.__FF_RENDER__(i)`：按帧号绘制并 POST 到 8787 `/frame`；预览单帧返回 dataURL。
- 批渲染（F02）逐帧调用，每帧之间检查预览队列；预览优先，批渲染让位但不失败。
- 预览/静帧/片段共用同一个 Chrome 与 `chrome-queue=1`，不新开浏览器。
- imported 项目继续走现有 Chrome CLI legacy 路径（`entry.still`/`entry.film`），保证 rumor-39s 回归零风险。
- `E05` 的 proxy 与 `F02` 的 final 都走 RendererSession；`mode=render/proxy` 参数保留在 `film_spec.html` URL 上。

**理由**：现有“整片持锁 + 页面内循环”无法满足 FR-23 的 p50 ≤2s；Playwright 已是依赖，previs 已有常驻 Chrome 经验；单 Chrome 会话同时满足串行约束与帧间抢占。

**风险与退路**：先做 120 帧 spike 基准（Phase 3 末）。若 p95 >6s，退路是“10 帧一批的 Chrome CLI + 锁释放”，再不行升级为 CDP attach；任一方案都必须保住 rumor legacy 路径。

**需要记录**：该决定写入 ADR-0006，并在实现前用 5s/120 帧基准数据支撑。

---

## 3. 阶段计划

### Phase 0.1 · 基线修复（0.5d）
- `server/tests/conftest.py`：session 级 autouse `init_db()`；BDD/集成/单测共享同一临时 home。
- 重跑 `pytest tests -q`，目标 28 passed；更新 HANDOFF/README 的测试计数与状态表述。
- 产出：基线报告；不改业务代码。

### Phase 1 · 边表 / Contract / 安全（1–1.5d）
- `edges.py`：加 `E04→E05`、`E04→F02`、`B05→C05` 三条 data 边；保持 46 节点、93 边。
- `test_dag_core.py`：断言 E04 有出边、C05 上游含 B05、拓扑无环、`data_descendants` 正确、边数 93。
- `cachekey.py`：`EXECUTOR_VERSION = "2.0.0"`。
- `errors.py`：补 `E_PROGRAM_INVALID` / `E_ENGINE_API_UNSUPPORTED` / `E_DOC_CONFLICT` / `E_FINAL_REQUIRED` 等 R2.0 错误码。
- Contract：`api_version: "2.0"`，`entry.still_spec/film_spec`，`legacy_entry.still/film`；C01 校验 v2 能力 + entry 文件。
- 安全：`FrameServer.translate_path` 做 `Path.resolve().is_relative_to(root)`；`projects_create` 用 `is_relative_to`。
- 同步 `../filmflow-web-agent-prompt.md` §4.8/§17/§19；PR 单列 3 条边。
- 出口：`pytest tests/unit/test_dag_core.py -q` 全绿；tag `r2-edge-fix`。

### Phase 2 · 文档模型与 Run 快照（FR-25，3–4d）
- `models.py`：`ProjectDoc`、`DocRevision`、`SchemaMigration`；`db.init_db()` 幂等迁移（SQLite）。
- 文档事实源：A01 写 `script.doc`；B02 写 `timeline.doc`（scenes/events + `source_span`）；B06 只导出 `task.json` 快照；materialize 初始化 docs；imported 从 task.json 迁移为只读。
- API：`GET/PUT /projects/:id/docs/:kind`（`base_version`，409）、`versions`、`restore`、`diff`。
- `POST /runs/:id/start` 前生成 `runs/<id>/docs/` + `snapshot.json`（文档、tokens.lock、字体/引擎 sha、profile、资产清单）。
- `node_cache_key += snapshot_sha`；运行时 B02/B03/B06/D01/E01 只读快照，不读可编辑文档。
- B06 新项目只导出 `runs/<id>/docs/task.json`；imported 保留项目根 task.json。
- 编辑器：自动保存 2s、undo 50、版本列表、保存前影响预估；最小改造，不重写 UI。
- 测试：两标签页 409、改文档→节点失效、手改 task.json 不影响新项目、imported 例外。
- 出口：5s 新项目改一句后 D01/E03 的 snapshot_sha 变化；无文档侧信道读取。

### Phase 3 · Scene DSL + 参数化渲染（FR-20/21，8–10d）
- 新模块 `server/app/engine/scene/`：`schema.py`、`canonical.py`、`compiler.py`、`components.py`。
- `engines/riso/assets/scene-kit.js`：12 组件（paper-card/headline/body-block/stamp/arrow-grow/hand-pointer/roller/halftone-field/registration-cross/evidence-card/chart-bar/count-up）+ fixture。
- `engines/riso/entry/film_spec.html`：读 `binding.programs[] + transitions[]`，支持 `start/end/total`、`mode=render|proxy|preview`、`profile`、`embed`；暴露 `__FF_RENDER__(i)`。
- `still_spec.html`：读 `program`；**删除** `meaning/operation` 默认文字；缺 program → `E_PROGRAM_INVALID`。
- D01：全场景编译 `base.program`；D02 传 `?spec=<url>&scene=&t=`；D02 不再只取前 3 场（至少支持 `D02 scopes` 参数，5s 全场景）。
- E03：同一编译器重编 base + 合并 E02 相机 → `motion.program`；静态部分与 base 逐字节一致。
- E04：8 转场库 + 时长/方向/参数 → `transitions.json`。
- E05/F02：`engine_api>=2` 且 program 存在 → `film_spec`；imported → `legacy_entry`；缺 film_spec → `E_ENGINE_API_UNSUPPORTED`，绝不回退。
- B01/B02：按 profile 目标时长反推；场景写 `source_span`（指向 `script.doc` 句子），不生成文案；D01 编译为 `text` 图层。
- C03：字集包含 program 全部文字（含组件标签）。
- Contract v2 + `C01` capability 校验；12 组件 schema/默认 props/fixture。
- 测试：5s 新项目 D02 文字断言；base/motion 静态部分逐字节一致；12 组件 fixture 三次渲染 sha 一致；ink/code-video 缺 film_spec 被阻断。
- 出口：5s 新项目 D02/F02 画面是用户文案；tag `r2-scene-dsl`。

### Phase 4 · 场景级增量渲染（FR-22，3–4d）
- `render.manifest.json`（profile 维度）+ `SceneState` 表。
- F02：plan（prev manifest 对比/hash/时长/顺序/转场）→ 只渲 dirty 帧范围；clean 帧保留；失败隔离。
- F03：按 manifest 聚合 missing/black/dup，定位 sceneId。
- 复用：dirty 场景 + 相邻转场重叠帧；时长/顺序变化 → 该场到片尾 dirty；转场变化 → 前后两场 dirty。
- 测试：改 S03 文字/时长/转场；kill -9 后 resume；`renderedFrames ≤25%`、墙钟 ≤20%。
- 出口：tag `r2-incremental`。

### Phase 5 · PreviewService（FR-23，4–5d）——[DONE] tag `r2-preview`
- `PreviewRenderer` + `server/app/services/preview.py`：F02 运行中 CDP 附加 9222；空闲时按 `chrome-queue`
  启动临时 Chrome；still 优先（`_INTERACTIVE` 帧间让位）、`_PAGE_SEM=2`。
- API：`POST /projects/:id/preview/still|segment|film`、`GET/DELETE /preview/jobs/:id`、
  `GET /preview/jobs/:id/file`、`GET /projects/:id/preview/cache`。
- 缓存 `~/.filmflow/cache/preview/<project>/<hash>/<key>.png`，LRU 500MB；不写 `out/frames`、不产生 Artifact/Approval。
- 防抖 250ms + latest-wins（20 并发只留最后 1 个）；等待 >3s → `E_PREVIEW_BUSY`；门前 `PREVIEW` 水印。
- 实测：attached p50 1.25s/p95 1.31s；5s 片段 12.7s；缓存 5ms；单帧归一化 SSIM 0.9987。
- 出口：`scripts/verify_r2_preview.py` 全绿；ADR-0006 落盘。

### Phase 6 · 档位与 final 校验（FR-24，3–4d）——[DONE] tag `r2-profiles`
- `render.profile.json`：draft 960×540/12、review 1280×720/24、final 1920×1080/24；profile 进 scene_hash。
- F02 只跑 final；E05 跑 review；D02 出 draft+review 静帧；draft/review 整片走 PreviewService。
- QA 阈值按 profile；G07 校验最新 F02 manifest `profile=final`，缺失 → `E_FINAL_REQUIRED`。
- 顺手修正 G05 `amix duration=first` 与 G06 伪同步（若 golden 含 G；否则明确标注 `approximate`，留给 R2.5）。
- 测试：40s draft/review/final 耗时；G07 拒绝 review 交付。

### Phase 7 · 持久化 Job + 崩溃恢复（FR-29，4–5d）——[DONE] tag `r2-jobs`
- `Job` 扩展：priority/attempts/lease_until/heartbeat_at/parent_id/cancel_requested/progress/eta/error。
- 状态机 + 租约 30s/心跳 5s；启动扫描过期租约 → queued；Run/Job 状态落库。
- 队列 API `/jobs`、`/queue`、`cancel`、`retry`；孤儿清理 `/tmp/ff-chrome-*`、8787 无主服务、孤立 ffmpeg；Chrome profile 带 run_id/job_id。
- 测试：kill -9 后 ≤60s 恢复；连续 3 次崩溃；预览优先级不被批渲染饿死。

### Phase 8 · 黄金项目与回归（FR-30，3–4d）——[DONE] tag `r2-golden`
- `fixtures/golden/5s|15s|40s/`：文案、风格、profile、期望帧/manifest。
- `scripts/golden_run.py`：建项目 → F06 → 6 帧 SSIM/pHash + program 文字断言 → 报告。
- 5s 必跑；15s/40s nightly；BDD 4 场景；失败输出 diff 图与 scene/layer。
- 全量验收：28+ 新旧测试、UI E2E 8 场景、rumor-39s 46/46、master 39.5s。

**关键路径**：0.1 → 1 → 2 → 3 → 4 → 5 → 6 → 8；7 可在 2 之后并行。总量约 30–40 人日。

---

## 4. 测试与证据纪律

每个 Phase 必须附：
1. 改动文件清单与 ADR（如有）。
2. 测试命令 + 真实输出（passed 数）。
3. 真实产物路径 + sha/时长（ffprobe）。
4. UI 截图（涉及界面时）。
5. `EXECUTOR_VERSION` / 边表 / 规格同步检查。
6. 未验证项明确写“未验证”，禁止“应该可以”。

回归门禁：
- `cd server && uv run pytest tests -q` → 全绿（干净临时 home 首跑也要绿）。
- `uv run --project server python scripts/e2e_ui.py` → 8 场景绿。
- `uv run --project server python scripts/smoke_m1.py` → 46 节点。
- rumor-39s 重跑（或受控缓存）→ 46/46，master 39.5s。
- 黄金 5s → 文字断言 + SSIM ≥0.98。

---

## 5. 风险登记

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | RendererSession 逐帧 CDP 太慢，F02 超时 | 中 | 高 | Phase 3 末 120 帧基准；退路 10 帧批 + 锁释放 / CDP attach |
| R2 | 改动渲染链破坏 rumor legacy 回归 | 中 | 高 | imported 走 `legacy_entry` 独立分支；golden 回归门禁 |
| R3 | 文档模型迁移破坏导入项目 | 中 | 高 | 迁移器 dry-run；imported task.json 只读兼容；备份 db |
| R4 | DSL 表达力不足，12 组件覆盖不了真实镜头 | 高 | 中 | v1 固定 12 组件/8 转场；`text/shape/image` 兜底；超纲记 v1.1 |
| R5 | 预览抢占导致 F02 饥饿 | 中 | 中 | 每帧检查 + 预览预算 ≤20% 时间片；等待上限 3s |
| R6 | 测试隔离/Chrome 残留再次污染基线 | 中 | 中 | session 级 init_db；孤儿清理；每次 golden 前清 profile |
| R7 | 路径穿越/白名单绕过 | 低 | 高 | Phase 1 修 `is_relative_to` + resolve；单测覆盖 |
| R8 | 范围膨胀到 R2.5/R3 | 中 | 高 | 冻结 8 个 FR；任何新增先记 ADR 并拒绝 |

---

## 6. R2.0 验收清单（与 QODER_PROMPT §7 一致）

- [ ] 5s 新项目「风从纸上起。纸不动，风先动。」→ A–F 跑通；D02/F02 文字 100% 是用户文案，无 rumor 句子。
- [ ] 40s 改 S03 一句 → 只渲 S03 + 邻接；renderedFrames ≤25%；F02 墙钟 ≤全量 20%。
- [ ] 单帧预览 p50 ≤2s / p95 ≤6s（F02 运行中）；5s 片段 ≤20s；缓存 ≤300ms。
- [ ] 40s draft ≤8min；review ≤18min；final ≤30min；G07 拒绝 review 交付。
- [ ] kill -9 API → ≤60s 恢复 running；无孤儿 Chrome；帧数正确。
- [ ] rumor-39s 46/46；master 39.5s；黄金帧 SSIM ≥0.98。
- [ ] 原有测试 + 新增单测/集成/BDD 全绿；UI E2E 8 场景绿；干净环境首跑绿。
- [ ] 规格 §4.8/§17 同步 93 边；`EXECUTOR_VERSION=2.0.0`；README/HANDOFF 状态更新。

---

## 7. 执行顺序与第一个动作

1. Phase 0.1：修 `conftest.py` 建表，重跑基线（不改业务代码）。
2. Phase 1：边表 + Contract + 安全 + 规格同步，打 `r2-edge-fix`。
3. Phase 2：文档模型与快照。
4. Phase 3：Scene DSL + film_spec + 12 组件，打 `r2-scene-dsl`。
5. Phase 4：增量，打 `r2-incremental`。
6. Phase 5–8 全部完成；R2.0 DoD 通过；等待老板验收后再申请 R2.5。

**第一个失败测试**（Phase 1 之前）：
`server/tests/unit/test_dag_core.py::test_edge_table_has_r2_repairs` —— 断言 93 边、E04 出边、C05 含 B05、拓扑无环；先红后绿。