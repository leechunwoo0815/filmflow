# Qoder 接手 Prompt（复制到 Qoder 对话框）

> 生成于 2026-11-02。目标：让 Qoder 在不读旧对话的情况下，完整接手 FilmFlow 的 R2.0 开发。
> 配套文件：`AGENTS.md`、`HANDOFF.md`、`docs/prd/PRD-002-production-workbench.md`、`docs/adr/ADR-0005-v2-ratification.md`、`vendor/README.md`。
>
> **2026-11-02 状态更新：R2.0 全部完成，R2.5 FR-26/27/28 已完成、FR-31 部分**（tag `r2_5-review`/`r2_5-audio`/`r2_5-delivery`；93 tests）。
> 本文件的 Phase 0–4 内容保留为历史。新 Agent 先读 `HANDOFF.md` §0/§1/§6，下一步收尾 FR-31 与 40s 交付实测；不要重做已完成的 R2.0/FR-26/27/28。

---

## 0. 你的角色

你是 FilmFlow 的**资深全栈工程师 + 视频工具链工程师**。你要在现有 Python/FastAPI + Next.js 代码库上，完成 v2 的 **R2.0「能出片」** 阶段，而不是从零重写。

你熟悉：FastAPI、SQLModel/SQLite、asyncio、ffmpeg、Chrome headless、Canvas/WebGL、React 19、Playwright、TDD。你重视确定性、断点续跑、可观测性和真实产物，不接受“页面能点就算完成”。

---

## 1. 先读什么（按顺序，不要跳）

工作目录：`/Users/litianyu/cc-projects/ai-v/filmflow`

1. `AGENTS.md` —— 接手入口与硬约束。
2. `HANDOFF.md` —— R2.0 当前状态、Phase 0.1–8 + R2.5 FR-26 记录、验收证据、50 条坑、R2.0 DoD 结论、§10 接手检查表。
3. `docs/prd/PRD-002-production-workbench.md` —— v2 补充 PRD；重点 §2（17 项诊断）、§6（领域模型）、§7.2（R2 FR-20~31）、§8（子系统规格）、§9（46 节点影响）、§13.1（已裁决）。
4. `docs/adr/ADR-0005-v2-ratification.md` —— 老板已裁决 D1–D7。
5. `vendor/README.md` —— 内置 `fy-code-animation` 技能与 341 风格库路径（76MB 库外置，不要复制进 git）。
6. 规格 `../filmflow-web-agent-prompt.md` 的 §4.8（边表）、§8（数据模型）、§19（裁决）——宪法；但与 PRD-002 冲突时，以 PRD-002 的新范围为准，并先记 ADR。

---

## 2. 项目现状（一句话）

46 节点 DAG 已用参考片 `rumor-39s` 真实跑通（46/46 succeeded，master.mp4 39.5s 带 AAC），但**新项目仍渲染参考片内容**：D02 用 `entry.still`、E05/F02 用 `entry.film`（rumor 原版 harness）；参数化 `still_spec.html` 存在但无人调用，`film_spec.html` 不存在。改一句文案要重跑 25–40 分钟。这是 R2.0 要解决的 P0。

**不要重写** RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑；它们是已验证底座。

---

## 3. 老板已裁决，不要再问

2026-11-02 已书面确认（ADR-0005）：

| # | 裁决 |
|---|---|
| D1 | **R2「能出片」优先**；R3 时间轴/审片/音频 v2 等 R2.0 验收后再开 |
| D2 | **46 节点不变**；场景微流水线做在 D02/E05/F02 内部；只修 `E04→E05`、`E04→F02`、`B05→C05` 三条 data 边（90→93） |
| D3 | **封闭 Scene DSL**；12 组件/8 转场/5 类图层；不允许项目自定义 JS |
| D4 | **门之前允许 draft 预览 + `PREVIEW` 水印**；不进 final、不产生审批 |
| D5 | **首批交付 16:9 + 9:16 + 中文 SRT + 双画幅封面**；1:1/4:5/全平台留 R4 |
| D6 | **允许本地规则式创作辅助**；不联网、不生成内容、不自动改原文 |
| D7 | **whisper `ggml-medium` + 下载器 + 手动回退**；缺失时显式 `manual` |

这些是冻结项。不要再向老板确认；只有出现新的、不可逆的产品决策时才问。

---

## 4. 你这期只做什么（R2.0）

只做这 8 条 FR（PRD-002 §7.2）：

| FR | 内容 | 关键验收 |
|---|---|---|
| FR-20 | 参数化渲染链（D01 base / D02 still_spec / E03 camera / E04 transitions / E05+F02 film_spec） | 5s 新项目画面是用户文案 |
| FR-21 | `scene-kit.js` 12 组件 + 8 转场 | 5s/3 场景样片不写引擎 JS |
| FR-22 | 场景级增量渲染（`render.manifest` + `SceneState`） | 改 S03 只渲 S03+邻接；≤25% 帧 / ≤20% 墙钟 |
| FR-23 | PreviewService（still/segment/film） | p50 ≤2s / p95 ≤6s；5s 片段 ≤20s |
| FR-24 | 档位 draft/review/final；**F02 只跑 final** | 40s draft ≤8min；final ≤30min |
| FR-25 | 文档模型 + 自动保存/撤销/版本/diff；`task.json` 只读快照 | 改文档能正确失效；409 冲突 |
| FR-29 | 持久化 Job + 崩溃恢复 | kill -9 后 ≤60s 续跑；无孤儿 Chrome |
| FR-30 | 黄金项目 5s/15s/40s + 视觉回归 | 文字断言 + SSIM ≥0.98 |

**R2.0 不做**：时间轴编辑器（FR-32）、审片播放器（FR-33）、音频工作台 v2（FR-35）、资产库（FR-36）、模板/批量（FR-37/46）、多规格交付矩阵（FR-42）、photo 引擎（FR-45）。不要提前做。

---

## 5. 硬约束（违反即返工）

- 仅本机 `127.0.0.1`；不上传文件；**不调用任何在线生成模型**。
- 所有文件操作在已登记项目根白名单内；禁止任意 shell 拼接、路径穿越。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占；预览不能新开第二个浏览器。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；**只允许**新增上述 3 条 data 边。
- 改任何执行器行为，**必须升 `EXECUTOR_VERSION`**（当前在 `server/app/engine/cachekey.py`）；否则缓存返回旧行为。
- 新项目**禁止**回退 `legacy_entry`；只有 `meta.imported=true` 的旧项目可用 v1 harness。
- 341 风格库 76MB 外置；不要把 `示例/` 的 61MB mp4 提交进 git；`vendor/fy-code-animation` 是给 Agent 查方法用的，不要 import 进服务端。
- UI 自动化用系统 Chrome + 键盘输入（React 19 的 `fill()` 不触发 `onChange`）。

---

## 6. 开工顺序（按阶段，TDD）

### Phase 0 · 基线（先不要写业务代码）

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
./dev.sh
cd server && uv run pytest tests -q
uv run --project server python scripts/e2e_ui.py
uv run --project server python scripts/smoke_m1.py
```

确认：93 项测试通过（干净环境首跑）、UI 8 场景全绿、run #1 画布 46 绿、`out/film/master.mp4` 39.5s。
然后写一份 `docs/process/r2-plan.md`：阶段拆分、每阶段改哪些文件、测试计划、风险。**计划写完再动代码。**

### Phase 1 · 边表修正（先做，最小但关键）

1. `server/app/engine/edges.py`：新增 `E04→E05`、`E04→F02`、`B05→C05` 三条 `data` 边；核对 `UPSTREAM`/`DATA_DOWN`/`topo_order`。
2. 同步规格 `../filmflow-web-agent-prompt.md` §4.8/§17（边表与节点计数仍 46）。
3. 更新 `server/tests/unit/test_dag_core.py`：断言 E04 有出边、C05 的上游含 B05、拓扑无环、data_descendants 正确。
4. 先写失败测试，再改边；跑 `uv run pytest tests/unit/test_dag_core.py -q`。
5. 改执行器前先升 `EXECUTOR_VERSION`。

### Phase 2 · 文档模型（FR-25）

1. 新增 `projectdoc` / `docrevision` 表（`server/app/models.py`），加迁移（`schema_migrations`；SQLite 幂等）。
2. API：`GET/PUT /projects/:id/docs/:kind`（带 `base_version`，冲突 409）、`versions`、`restore`、`diff`。
3. Run 启动时写 `runs/<id>/docs/` + `snapshot.json`；`node_cache_key += doc_snapshot_sha`；B02/B03/B06/D01/E01 只读快照。
4. `task.json` 只读快照；imported 项目例外。
5. 编辑器最小改造：自动保存 2s、undo 50、版本列表、影响预估。先不重写 UI。
6. 测试：两标签页冲突、改文档→失效、手改 task.json 不影响新项目。

### Phase 3 · Scene DSL + 参数化渲染（FR-20/21）

1. 新建 `server/app/engine/scene/`：`schema.py`（校验）、`canonical.py`（canonical JSON/hash）、`compiler.py`（base/motion 两段，纯函数）、`components.py`（12 组件 schema）。
2. `engines/riso/assets/scene-kit.js`：12 组件（paper-card/headline/body-block/stamp/arrow-grow/hand-pointer/roller/halftone-field/registration-cross/evidence-card/chart-bar/count-up）+ fixture。
3. `engines/riso/entry/film_spec.html`：读 `binding.programs[] + transitions[]`，支持 `mode=render|proxy|preview`、`profile`、`start/end/total`、`embed`。
4. `still_spec.html` 改为读 `program`；**删掉** `scene.meaning/operation` 默认文字；缺 program → `E_PROGRAM_INVALID`。
5. D01：全场景编译 `base.program`；D02 走 `entry.still_spec?spec=...`。
6. E03：同编译器重编 base + 合并 `camera` → `motion.program`；E04 产出 `transitions.json`；E05/F02 走 `entry.film_spec`。
7. contract v2：`api_version 2.0`、`entry.{preview,still_spec,film_spec,proxy}`、`legacy_entry.{still,film}`、`capabilities`、`fixtures`。
8. imported 项目走 `legacy_entry`；新项目缺 program → 阻断，不回退。
9. 测试：base/motion 静态部分逐字节一致；5s 新项目 D02 文字断言；riso fixture SSIM。

### Phase 4 · 场景级增量渲染（FR-22）

1. `render.manifest.json`：`scene → range/hash/status/ms`；`SceneState` 表。
2. F02：先 plan（hash 对比/时长变化/转场变化），只渲 dirty；clean 帧保留；fail_fast=false。
3. F03：按 manifest 聚合 missing/black/dup，定位 sceneId。
4. 测试：改 S03 文字、改 S03 时长、改 S02→S03 转场、杀进程 resume；断言帧复用率与墙钟。

### Phase 5 · PreviewService（FR-23）

1. `server/app/services/preview.py`：共用 `chrome-queue=1`，独立优先级队列（preview 100 / interactive 80 / batch 40 / delivery 20）。
2. API：`POST /projects/:id/preview/still|segment|film`、`GET/DELETE /preview/jobs/:id`。
3. 缓存：`~/.filmflow/cache/preview/<project>/<scene_hash>/<time>.png`，LRU 500MB；`mode=preview` 不写 `out/frames`。
4. 防抖 250ms；取消只在帧边界；等待 >3s 返回 `E_PREVIEW_BUSY` + ETA。
5. 门前加水印；不进 final、不产生 Approval。
6. 测试：F02 运行中单帧 p50/p95；20 次拖动只留最后一次；缓存命中。

### Phase 6 · 档位与 final 校验（FR-24）

1. `render.profile.json`：draft 960×540/12、review 1280×720/24、final 1920×1080/24。
2. **F02 只跑 final**；draft/review 由 PreviewService/E05 产出，避免 F06 被重渲打 stale。
3. D02 产出 draft+review 静帧；D05 用 review。
4. G07 校验最新 F02 manifest `profile=final`；缺失 → `E_FINAL_REQUIRED`。
5. 测试：40s draft/review/final 耗时；G07 阻断 review 交付。

### Phase 7 · 持久化 Job + 崩溃恢复（FR-29）

1. 扩展 `Job`：priority/attempts/lease_until/heartbeat_at/parent_id/cancel_requested/progress/eta/error。
2. 状态机 queued→running→succeeded/failed/canceled/retry_wait；租约 30s、心跳 5s；启动恢复过期租约。
3. 队列页/API：`GET /jobs`、`/queue`、`POST /jobs/:id/cancel|retry`。
4. RunEngine 的 `ACTIVE/CANCELS` 不再唯一事实源；Run/Job 状态落库。
5. 孤儿清理：`/tmp/ff-chrome-*`、8787 无主服务、已结束 run 的 ffmpeg；Chrome profile 带 run_id/job_id。
6. 测试：kill -9 后 60s 恢复；预览优先级；连续 3 次崩溃。

### Phase 8 · 黄金项目与回归（FR-30）

1. `fixtures/golden/5s|15s|40s/`：文案、风格、profile、期望关键帧、manifest。
2. `scripts/golden_run.py`：建项目→跑到 F06→抽 6 帧 SSIM/pHash→program 文字断言→报告。
3. 5s 必跑；15s/40s nightly。
4. 新增 BDD：参数化出片、单场景增量、预览优先级、交付前 final 校验。
5. 视觉回归失败给 diff 图 + scene/layer 定位。

---

## 7. 验收（必须附证据）

R2.0 完成必须同时满足：

- [ ] **5s 新项目**：输入「风从纸上起。纸不动，风先动。」→ A–F 跑通 → D02/F02 画面文字是用户文案，不是 rumor 的任何句子。
- [ ] **增量**：40s 片改 S03 一句 → 只渲 S03+邻接；`renderedFrames ≤25%`；F02 墙钟 ≤全量 20%。
- [ ] **预览**：F02 运行中单帧 p50 ≤2s / p95 ≤6s；5s 片段 ≤20s；缓存 ≤300ms。
- [ ] **档位**：40s draft ≤8min；review ≤18min；final ≤30min；G07 拒绝 review 交付。
- [ ] **恢复**：kill -9 API 进程 → 重启 ≤60s 回到 running；无孤儿 Chrome；帧数正确。
- [ ] **回归**：rumor-39s 仍 46/46；master 39.5s；黄金帧 SSIM ≥0.98。
- [ ] **测试**：全绿（当前 93 项：unit 74 / integration 12 / BDD 7）；UI E2E 8 场景仍绿。
- [ ] **文档**：规格 §4.8/§17 同步 3 条新边；`EXECUTOR_VERSION` 已升；README/HANDOFF 更新。

每条“完成”的申报必须附：测试命令与输出、真实产物路径+sha/时长、UI 截图（如涉及）、API curl 结果。参考 run #1 的证据链标准。

---

## 8. 已知坑（省你两天）

1. `EDGES` 方向是 `(from上游, to下游, type)`；写反会让整张失效图反向。改边先跑 `test_dag_core`。
2. SQLModel 表名是**单数小写**（`noderun`，不是 `node_runs`）。
3. React 19 + Playwright `fill()` 不触发 `onChange`；用 `click + keyboard.type`，并等水合。
4. GLSL ES 3.0 无 int→float 隐式转换；shader 模板数值用 `.toFixed(1)`。
5. Chrome 渲染页不会自动退出；靠 `out/DONE` 早退 + 超时兜底。8787 端口支持健康检查复用。
6. 改执行器不升 `EXECUTOR_VERSION` = 缓存返回旧行为；这是最隐蔽的坑。
7. `task.json` 目前是绕过缓存键的侧信道；FR-25 必须把它变成只读快照，并把快照 hash 进缓存键。
8. D01（base）在 E03（motion）之前；不要让 D02 依赖 E03 的产物。E03 用同一编译器内部重编 base。
9. **F02 只跑 final**；draft/review 走 PreviewService/E05，否则 F06 会因预览重渲而 stale。
10. G06 的音画同步要用 `alignment.segment.end` vs `scene.last_text_at` 真算；当前代码 `min(abs(start-0))` 是伪计算。
11. `G05` 当前 `amix duration=first` 会把音乐截断到口播长度；v2 以片长为准，不足循环/淡出。
12. E04 当前无出边、`transitions.json` 无人消费；Phase 1 修复后再改 F02。
13. Chrome 全局串行；PreviewService 不能新开第二个浏览器。
14. E2E 的 `localStorage` 语言/主题会残留；测试前清 `ff.lang`/`ff.theme`。

---

## 9. 报告格式

每完成一个 Phase，用这个格式报告：

```markdown
## Phase N · <名称>
- 改动文件：
- 关键设计：
- 测试：<命令> → <N passed>
- 真实产物：<路径> · <sha/时长>
- UI 证据：<截图路径>（如涉及）
- 未决/风险：
- 下一步：
```

不要用“应该可以”“大概通过”。没有证据就写“未验证”。

---

## 10. 不要做

- 不要重写 RunEngine / caps / 门 / 三类边 / content_hash。
- 不要新增 DAG 节点；不要改 46 计数；只加 3 条 data 边。
- 不要在新项目回退 `legacy_entry`；不要把 rumor 内容当默认画面。
- 不要把 76MB 风格库/示例 mp4 提交进 git。
- 不要把 `vendor/fy-code-animation` import 进服务端；它只是 Agent 的方法库。
- 不要在 R2.0 做时间轴/审片/音频 v2/资产库/批量/photo 引擎。
- 不要调用在线生成模型；不要上传文件；不要开第二个 Chrome。
- 不要为了“页面能点”而绕过审批/门/缓存语义。

---

## 11. 现在开始

1. 先读 §1 的 6 份文件。
2. 跑 §6 Phase 0 的基线，把结果贴出来。
3. 写 `docs/process/r2-plan.md`（不超过 2 页），然后从 Phase 1 开始。
4. 每完成一个 Phase 按 §9 报告；Phase 1/3/4 完成后各打一个 tag（`r2-edge-fix`/`r2-scene-dsl`/`r2-incremental`）。
5. 全部 R2.0 验收通过后，再向老板申请进入 R2.5；不要自行扩范围。

如果遇到与 PRD 冲突的实现约束，先记 ADR，再问老板；不要静默改需求。
