# FilmFlow 交接文档（HANDOFF）

> 更新时间：2026-11-02 · R2.0 Phase 0.1–4 已完成
> 当前基线：Phase 4 代码 `07b5237` / tag `r2-incremental`；交接文档提交见 `git log` 最新一条。
> 本文是**唯一权威接手入口**；规格 `../filmflow-web-agent-prompt.md` 仍是宪法，v2 需求以
> `docs/prd/PRD-002-production-workbench.md` + `docs/adr/ADR-0005-v2-ratification.md` 为准。
> **先读本文 §0、§1、§6，再读 `AGENTS.md`、PRD-002、ADR-0005、`vendor/README.md`。**

---

## 0. 下一个 Agent 从这里开始（15 分钟）

### 0.1 工作目录与服务

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
./dev.sh                  # API :7860 + Web :3000
curl -s http://127.0.0.1:7860/api/health
```

如果 API/Web 已在跑，直接检查；如果 `dev.sh` 退出，先看是否 macOS 自带 bash 3.2 的
`wait -n` 问题（已修，当前脚本用 `kill -0` 轮询）。

### 0.2 第一小时必做

```bash
cd server && uv run pytest tests -q                       # 52 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # UI 8 场景
uv run --project server python scripts/smoke_m1.py         # API 冒烟：46 节点 / 93 边
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量验收
```

`verify_r2_5s_incremental.py` 会真实建项目、跑到 F06、改 S02、再跑一个新 Run，并断言
`renderedFrames < total`、S01 hash 不变、S02 hash 变化、前一场帧哈希不变。第一次跑约 1.5 分钟。

### 0.3 当前下一步

**从 Phase 5（PreviewService / FR-23）开始，不要重做 Phase 1–4。**
推荐方案与验收见本文 §6.1；不要新开第二个浏览器，不要把预览写进 `out/frames` 或产生 Approval。

### 0.4 不要做的事

- 不要重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑。
- 不要新增 DAG 节点；46 节点/7 阶段/93 边不变。
- 不要把新项目回退到 `legacy_entry`；只有 `meta.imported=true` 的旧项目可走 v1 harness。
- 不要改执行器行为却不升 `EXECUTOR_VERSION`（当前 `2.1.2`）。
- 不要把 76MB 风格库/示例 mp4 提交进 git；不要把 `vendor/fy-code-animation` import 进服务端。
- 不要调用在线生成模型、上传文件、开第二个 Chrome。
- 不要用“页面能点”代替真实产物；所有完成申报必须附测试输出 + 产物路径/sha/时长 + curl/截图。

---

## 1. 当前状态（R2.0）

### 1.1 版本、提交、标签

| 项 | 值 |
|---|---|
| Phase 4 代码 | `07b5237`（tag `r2-incremental`）；当前 HEAD 以 `git log` 为准 |
| Phase 1 tag | `r2-edge-fix` → `4f9e381` |
| Phase 3 tag | `r2-scene-dsl` → `53e6462` |
| Phase 4 tag | `r2-incremental` → `07b5237` |
| 测试 | **52 passed**（unit 37 / integration 12 / BDD 3） |
| UI E2E | 8 场景 / 9 检查全绿（约 16–20s） |
| API 冒烟 | 46 节点 / **93 边**通过 |
| EXECUTOR_VERSION | **2.1.2**（`server/app/engine/cachekey.py`） |

### 1.2 R2.0 八个 FR 的真实状态

| FR | 状态 | 说明 |
|---|---|---|
| FR-20 参数化渲染链 | [DONE] | 5s 新项目 `风从纸上起。纸不动，风先动。` 已跑通 D02 静帧与 E03–F06；画面文字来自 `source_span`/program，不再渲染 rumor 内容。 |
| FR-21 场景组件库 v1 | [DONE，视觉回归待补] | `scene-kit.js` 12 组件 + Python schema + `fixture/scene-kit.json`；组件 fixture 的 SSIM/视觉回归留 Phase 8。 |
| FR-22 场景级增量 | [DONE，40s 实测待补] | manifest + SceneState + F02 只渲 dirty；5s/2 场实测 66 渲/54 复用；40s/5 场规划单测 204/948=21.5%。 |
| FR-23 PreviewService | [TODO] | 未实现；F02 目前整片持锁，预览必须在 Phase 5 与 F02 共享同一个 Chrome。 |
| FR-24 draft/review/final | [PARTIAL] | `film_spec` 已支持 `profile` 参数，但 F02 固定 `final`；无 draft/review 产物、无 G07 `E_FINAL_REQUIRED`。 |
| FR-25 文档模型/快照 | [DONE] | ProjectDoc/DocRevision、409、版本/diff/回滚、Run 快照、新项目 task.json 只读、DocsEditor 自动保存/撤销/影响预估。 |
| FR-29 持久化 Job/恢复 | [TODO] | `Job` 表仍未写入；`ACTIVE/CANCELS` 仍是内存态；无启动恢复/孤儿清理。 |
| FR-30 黄金项目 | [TODO] | 无 `fixtures/golden/`、`golden_run.py`、SSIM/pHash 回归、BDD 新场景。 |

**重要诚实项**：
- `smoke_m1.py` 的 46/46 是 **run #1 的旧状态/缓存**，不是 v2 代码上的全新 rumor 重渲。
- Phase 8 必须用**干净项目副本**（或删掉 `out/frames` 并强制全量）新建 Run，验证 imported legacy
  仍 46/46、master 39.5s；不要只看旧 NodeRun 的 succeeded。
- 5s 项目的 66/120=55% 是因为 S02 占全片 66 帧；40s/5 场的 204/948=21.5% 才对应 FR-22 的 25% 指标。

### 1.3 环境

- 本机：macOS · Python 3.13 · uv · Node ≥22 · pnpm · 系统 Chrome · ffmpeg。
- 真实 DB：`~/.filmflow/filmflow.db`；测试 DB：`/tmp/filmflow-test-home/filmflow.db`
  （`conftest.py` 在导入前设置 `FILMFLOW_HOME`）。
- 参考项目：`/Users/litianyu/cc-projects/ai-v/rumor-39s`（无 v2 program；imported）。
- 当前 5s 验收项目：`/Users/litianyu/cc-projects/ai-v/filmflow-projects/r2-verify-79`
  （project 52 / run 56 / run 57，manifest 66/54）。
- Phase 3 5s 项目：`/Users/litianyu/cc-projects/ai-v/filmflow-projects/r2-v2r4-67`
  （run 38，120 帧 / 1920×1080 / 5.000s / intermediate.mp4）。
- Phase 4 手工项目：`/Users/litianyu/cc-projects/ai-v/filmflow-projects/r2-p4-75`
  （project 47 / run 51，manifest 66/54）。

---

## 2. 可直接复核的验收证据

### 2.1 5s 参数化出片（Phase 3）

- 输入：「风从纸上起。纸不动，风先动。」
- 运行：A–F 真实执行，D02 走 `entry.still_spec`，F02 走 `entry.film_spec`；
  `out/frames` 120 帧，`out/film/intermediate.mp4`：
  - 1920×1080 / 24fps / 120 帧 / **5.000s**
  - F05（Y-SSIM）通过。
- D02 两张静帧 sha 不同且 lum≈233、dark%≈1.8–2.2；程序标题层内容为
  `风从纸上起。` / `纸不动，风先动。`。
- `scenes/S01.base.program.json` 与 `S01.program.json` 去掉 camera/transitions/program_sha 后
  逐字节一致；motion 含 camera。

### 2.2 5s 增量（Phase 4，脚本可复现）

`scripts/verify_r2_5s_incremental.py` 实测输出：

```
manifest1 rendered=120 reused=0
manifest2 rendered=66 reused=54
S01 hash same=True  S02 changed=True
frames 0..53 unchanged=True; 54..119 changed=61
PASS: R2.0 Phase 4 5s 增量验收通过
```

- manifest 路径：`<project>/renders/final/manifest.json`
- F02/F03/F04/F05/F06 全 succeeded；G01 因无口播失败，不影响 A–F 验收。
- 40s/5 场规划单测：改 S03 → dirty S03 + 离场转场帧，204/948=21.5% ≤25%
  （`server/tests/unit/test_render_manifest.py`）。

### 2.3 回归

```bash
cd server && uv run pytest tests -q                       # 52 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # 8 场景
uv run --project server python scripts/smoke_m1.py         # 46 / 93
```

---

## 3. R2.0 Phase 0.1–4 实施记录

### Phase 0.1 · 基线修复（提交 `4f9e381` 的一部分）

- `server/tests/conftest.py`：session 级 autouse `init_db()`，修复 BDD 在干净库首跑
  `no such table: style`；现在 52 项干净环境首跑全绿。
- `dev.sh`：macOS 自带 bash 3.2 不支持 `wait -n`，改为 `kill -0` 轮询；否则脚本启动即退出。
- 文档同步测试计数。

### Phase 1 · 边表 / Contract / 安全（tag `r2-edge-fix`）

- `edges.py` 新增三条 data 边：`E04→E05`、`E04→F02`、`B05→C05`；90→93，节点仍 46。
- 新建 `test_edge_table_has_r2_repairs`；`test_wizard_flow` 断言 93 边。
- `EXECUTOR_VERSION` 升到 2.x 系列；Contract v2 骨架：
  `api_version 2.0`、`scene_schema`、`legacy_entry`、capabilities 12 组件/8 转场、limits。
- C01 对**新项目**阻断非 2.x 引擎（`E_ENGINE_API_UNSUPPORTED`）；imported 不阻断。
- 安全：FrameServer `translate_path` 用 `resolve()+is_relative_to`；项目根白名单改
  `Path.is_relative_to`；补 `test_security_paths.py`。
- C05 真正锁入 B05 `type_spec`（只加边不消费是无效修复）。
- 规格 `../filmflow-web-agent-prompt.md` §4.8/§17/§19 已同步 93 边（该文件在仓库外，不在 git 里）。

### Phase 2 · 文档模型 / Run 快照 / 编辑器（提交 `b1d12d4`）

- 新表：`ProjectDoc`、`DocRevision`、`SchemaMigration`；`db.init_db()` 幂等记录 schema 1/2。
- 文档 API：`GET/PUT /projects/:id/docs/:kind`（`base_version` 冲突 409）、`versions`、
  `restore`、`diff`、`timeline/rebuild`；支持 `script/timeline/profile/...`。
- `save_doc` 对 `script` 由 `text` 重建 sentences/source_span；用 Core `UPDATE ... WHERE version`
  做乐观锁，两个标签页后保存者 409。
- Run 快照：`runs/<id>/docs/snapshot.json` + script/timeline/task 快照；
  `doc_snapshot_sha` 进 `node_cache_key`；`DOC_NODES` 含 A01/B02/B03/B06/D01/E01/E03。
- B02/B03/B06/D01/E01 只读快照；新项目 `card/task.json` 只读导出（`PUT /task` 返回
  `E_DOC_READONLY`）；imported 仍可写。
- B06 写 `doc_version`/`doc_hash`；B07 校验 Run 快照 task。
- 5s 新项目场景按句数构建（`build_timeline_doc`），场景带 `source_span`，不再丢用户文案。
- 编辑器：新项目走 `DocsEditor.tsx`（2s 自动保存、undo 50、版本/diff/回滚、影响预估）；
  imported 保留原任务卡编辑器。
- 修复：SQLAlchemy JSON 原地修改不落库（`flag_modified`）——曾导致 `meta.imported`、
  materialize 的 A01/A02/A04/B06 params 全部丢失。
- 修复：C02 跨项目缓存导致 C03 找不到 `fonts/src`；C03 改为读 C02 产物。
- 测试：`test_project_docs.py`、`test_docs_api.py`、快照不可变、409/回滚/只读/导入 meta。

### Phase 3 · Scene DSL + 参数化渲染（tag `r2-scene-dsl`）

- 新包 `server/app/engine/scene/`：
  - `canonical.py`（canonical JSON/hash）
  - `components.py`（12 组件 schema/defaults）
  - `schema.py`（program 校验：层/组件/文本长度/禁止 JS）
  - `compiler.py`（`compile_scene`；text 来自 `source_span`；base 无 camera，motion 合并 E02 camera）
- `engines/riso/assets/scene-kit.js`：12 组件；`fixture/scene-kit.json` 12 条 fixture。
- `engines/riso/assets/scene-render.js`：共享 program 渲染器；camera、layers、transitions、
  RISO 可复用 compositor。
- `engines/riso/assets/riso-core.js`：新增 `createCompositor`（shader 不变），供逐帧复用。
- `engines/riso/entry/still_spec.html` 重写为 v2：读 `program`，缺 program → `STILL_ERR
  E_PROGRAM_INVALID`，不再回退 meaning/`风`。
- 新增 `engines/riso/entry/film_spec.html`：`mode=render|proxy|preview`、`start/end/total`、
  `binding/transitions`、内联 `program_inline`；每次渲染结束都发 `/done`（短项目不再挂 1800s）。
- D01：全场景 base program + `scenes/still_spec.json` + `still_t`（场景中段）供 D02。
- D02：新项目 `entry.still_spec?spec=...&scene=&t=`；imported 走 `legacy_entry.still`。
- E03：motion program + `scenes/timeline_binding.json`；binding 内联 base/motion program。
- E04：8 转场类型，输出 `scenes/transitions.json` 与 artifact。
- E05/F02：新项目 `entry.film_spec`（proxy/render），imported 走 `legacy_entry.film`。
- C01 v2 校验组件声明/fixture；C03 字集补数字/标点；B06 `task_id` 进缓存键。
- 实测 5s 全链：D02 用户文案、F02 120 帧/5.000s、F05 通过。

### Phase 4 · 场景级增量（tag `r2-incremental`）

- 新 `server/app/engine/render_manifest.py`：
  - `scene_ranges`、`transitions_for_scene`、`scene_hash`、`build_plan`、`plan_dirty`、
    `dirty_ranges`、`build_manifest`。
  - 脏区间 = 本场 range + **离场转场** out-overlap；进入转场帧已在本场 range 内，不向前扩。
- `SceneState` 表：run/scene/hash/status/range/ms/qa。
- F02 v2：
  - 读 E03/E04 **artifact**（不依赖项目文件）；program 缺文件时用 inline 写入。
  - 对比 `renders/final/manifest.json`，只渲 dirty；clean 帧保留；删除超出新时长的旧帧。
  - 写 manifest（原子替换）、SceneState；失败场景 `E_SCENE_FAILED`。
  - manifest 的 `font_sha` 用 **C02 源字体**，不能用 C04 子集 CSS（否则改一个字脏全片）。
- F03：按 manifest 聚合 `scene_report`（missing/black/dups 定位场景），并回写 SceneState qa。
- API：`GET /api/runs/:id/render-manifest`。
- 稳定性修复：
  - FrameServer 是全局单例：D02/E05/F02 加 `port-8787` 锁，防止别的 Run 切换根目录。
  - `ProcessRunner` 正常退出后取消 `_watch_cancel`，否则永久挂起；`test_runner.py` 回归。
  - `FrameServer.log_message` 不能对 HTTPStatus/int 做 `in`；改为 `fmt % args`。
  - 失败/skipped/canceled 不再自动重排；`/retry`/`/resume` 显式重置。
  - 跨 Run 继承的批准补发 caps（否则 F01/F02 无门可等却永远 idle）。
  - 无就绪节点且非终态 → Run `blocked`，不再假装 running。
- 实测：5s 改 S02 → 66 渲/54 复用；40s 规划 204/948=21.5%。

---

## 4. 当前 v2 架构（必须理解）

### 4.1 新项目数据流

```
docs(script/timeline/profile)
  → Run 快照 runs/<id>/docs（snapshot.json + doc_snapshot_sha）
  → A01 script.doc
  → B02 timeline.doc（source_span；不再生成文案）
  → B06 Run 快照 task.json + card/task.json 只读导出
  → B07 校验快照
  → C01 contract v2（只有 2.x 引擎可跑新项目）
  → D01 编译 scenes/<sid>.base.program.json + card/still_spec.json
  → D02 entry.still_spec（program → 静帧；still_t=场景中段）
  → D05
  → E01/E02/E03 编译 scenes/<sid>.program.json + scenes/timeline_binding.json（内联 program）
  → E04 scenes/transitions.json
  → E05 entry.film_spec mode=proxy
  → E07
  → F01 8787 帧服务
  → F02 entry.film_spec mode=render + renders/final/manifest.json + SceneState
  → F03 scene_report
  → F04 ffmpeg → F05 QA → F06
  → G...
```

### 4.2 imported 旧项目

- `Workflow.graph_json.meta.imported=true`（`projects_import` 现在会持久化，已修 `flag_modified`）。
- D02/E05/F02 走 `legacy_entry.still/film`（rumor 原版 harness）。
- 不生成 v2 program；D01 保留 v1 `still_spec`；G 链保持原样。
- 新项目**禁止**回退 legacy；缺 film_spec → `E_ENGINE_API_UNSUPPORTED`。

### 4.3 缓存

- `EXECUTOR_VERSION=2.1.2`，任何执行器行为变化必须升。
- 节点缓存键 = version + params + 上游产物 sha + caps + `doc_snapshot_sha`（DOC_NODES）。
- 场景 manifest hash = program + tokens lock + engine sha + **C02 源字体** + profile + 邻接 transitions。
- 跨项目缓存注意：E03 binding 已内联 program；F02 读 E03/E04 artifacts；C02/C03 有产物路径回退；
  B06 `task_id` 已进缓存键。

### 4.4 锁

- `chrome-queue=1`：所有 Chrome 渲染串行。
- `ffmpeg=1`。
- `port-8787=1`：F01 与 **D02/E05/F02** 都持有；任何一个渲染节点运行期间，FrameServer 根不能被
  别的 Run 切换。Phase 5 预览若在 F02 运行中，必须通过同一 Chrome/同一 8787 根，不得绕过此锁。
- F02 Chrome profile：`/tmp/ff-F02`；Phase 5 将加 `--remote-debugging-port=9222` 供预览 CDP 附加。

### 4.5 关键文件

| 想改什么 | 去哪 |
|---|---|
| 节点/边/锁 | `server/app/engine/edges.py`（同步规格 §4.8） |
| 调度/门/caps/缓存/恢复 | `server/app/engine/runengine.py` |
| 子进程壳 | `server/app/engine/runner.py` |
| 执行器 | `server/app/engine/executors/{__init__,pipeline}.py` |
| Scene DSL | `server/app/engine/scene/*` |
| 增量规划 | `server/app/engine/render_manifest.py` |
| Run 快照 | `server/app/engine/snapshot.py` |
| 文档模型/API | `server/app/services/project_docs.py`、`server/app/api/routes.py` |
| 引擎页 | `engines/riso/entry/{still_spec,film_spec}.html`、`assets/{scene-kit,scene-render,riso-core}.js` |
| 编辑器 | `web/src/app/editor/page.tsx`、`web/src/components/DocsEditor.tsx` |
| 文档 | `docs/prd/PRD-002-production-workbench.md`、`docs/adr/ADR-0005-v2-ratification.md` |

---

## 5. R2.0 新增踩坑（按优先级）

1. **`EXECUTOR_VERSION`**：改任何执行器行为不升版 = 缓存返回旧行为。当前 `2.1.2`。
2. **doc 快照**：A01/B02/B03/B06/D01/E01/E03 的缓存键必须含 `doc_snapshot_sha`；新增读文档的
   执行器要加入 `DOC_NODES`，否则改文档不失效。
3. **字体 hash**：manifest `font_sha` 用 **C02 源字体**，不要用 C04 子集 CSS（随文案变化会让
   所有场景 dirty，增量失效）。
4. **scene hash**：包含 program/tokens/engine/font/profile/邻接 transitions；脏区间用
   `out_overlap`，不要向前多扩进入转场帧；改这些先跑 `test_render_manifest.py`。
5. **F02 只跑 final**：manifest 路径 `renders/final/manifest.json`；draft/review 不能写 F02 产物链，
   否则 F06 会 stale（Phase 6）。
6. **F02 失败终态**：failed/skipped/canceled 不再自动重排；用 `POST /runs/:id/retry` 或
   `/resume`。不要再让 `_ready_set` 把 failed 当可运行。
7. **8787 全局单例**：D02/E05/F02 必须持 `port-8787`；否则别的 Run 的 F01 会切换根目录，
   帧/DONE 写到错误项目。
8. **`ProcessRunner`**：进程正常退出后要取消 `_watch_cancel`；否则 `run()` 永久挂住。
   对应 `test_runner.py`。
9. **FrameServer 日志**：`log_message(self, fmt, *args)` 里对 `args[0]` 做 `in` 会在 404/204 时
   收到 HTTPStatus/int 而抛 `TypeError`；用 `fmt % args` 判断 `/frame`/`/pframe`。
10. **继承门 caps**：跨 Run `inherit` 的批准只让门 succeeded，旧逻辑不补 caps；`_ready_set`
    必须在终态门和有效门处调用 `caps_after_approval`，否则 F01/F02 永远 idle。
11. **SQLAlchemy JSON**：`graph = wf.graph_json; graph[...] = ...; wf.graph_json = graph` 可能
    不标脏；用 `flag_modified(wf, "graph_json")`。`projects_import`/`drafts_materialize` 已修。
12. **B06 task_id**：默认 `Path(project_root).name` 现在注入 params；否则任务卡跨项目缓存，
    C03/C04 会去当前项目找字体失败。
13. **E03/E04 缓存**：E03 binding 内联 program；F02 从 `_upstream_json(["E03","E04"])` 读
    binding/transitions，不依赖项目文件；E04 缓存时项目 `scenes/transitions.json` 可能不存在。
14. **C02/C03**：C02 跨项目缓存时源字体在旧项目 artifacts；C03 优先读
    `font_fetch_report.artifact_path` 或 DB C02 TXT artifact，再回退 `fonts/src`。
15. **D02 静帧时刻**：`last_text_at` 是 validator 的阅读窗起点（=start），不是拍照时刻；
    v2 用 `still_t = start + max(0.8, dur*0.5)`，否则拍到 reveal 前空纸。
16. **新项目 task.json 只读**：`PUT /projects/:id/task` 对新项目返回 `E_DOC_READONLY`；
    imported 例外。运行时只读 Run 快照。
17. **film_spec DONE**：短项目必须发 `/done`；不要在页面里用固定 `FRAMES=948` 判断。
18. **Chrome 进程**：F02 用 `/tmp/ff-F02`；Phase 5 预览 CDP 附加前要确认 `9222` 可连接；
    不要启动第二个 Chrome 做预览。
19. **`dev.sh`**：macOS bash 3.2 不支持 `wait -n`；当前用 `kill -0` 轮询。
20. **调度 deadlock**：无 runnable、无 pending 门但不是终态时 Run 标 `blocked`；不要静默
    running。排查先看 caps 和 failed 节点。

---

## 6. 未完成 R2.0：Phase 5–8 可直接开工

### 6.1 Phase 5 · PreviewService（FR-23）

**目标**：F02 运行中单帧 p50 ≤2s / p95 ≤6s；5s 片段 ≤20s；缓存命中 ≤300ms；
预览不写 `out/frames`、不产生 Approval；门前 `PREVIEW` 水印。

**推荐设计（CDP 附加，不重写 F02）**：
1. `_chrome_render_argv` 给 F02 Chrome 加 `--remote-debugging-port=9222`
   （`--remote-debugging-address=127.0.0.1`）。
2. 新增 `server/app/services/preview.py`：
   - 若 9222 可连接：`playwright.chromium.connect_over_cdp`，在**同一个 Chrome**里新建 page；
     加载 `engines/riso/entry/film_spec.html?payload=<base64 inline>&mode=preview&t=...&embed=<file css>`；
     等 `__PREVIEW_DONE__`，取 `__PREVIEW_PNG__`，关 page（不关浏览器）。
   - F02 不在跑：按 `chrome-queue` 启动一个 Chrome，渲染完关闭（不要常驻第二个浏览器）。
   - payload 内联 `binding.programs[]`（含 `program_inline`）+ transitions + profile，避免 8787 根切换。
   - still 缓存：`~/.filmflow/cache/preview/<project>/<scene_hash>/<time>.png`；
     简单 LRU/容量 500MB；命中直接返回。
   - 水印：PIL 在右上角叠 `PREVIEW`（半透明），无论门前后都先加水印；不写 final。
3. `film_spec.html` 增强：
   - `payload` base64 内联模式；`program_inline` 优先；
   - `window.__FF_RENDER_ONE__(i)` 返回 dataURL；
   - `window.__PREVIEW_PNG__`/`__PREVIEW_DONE__`（mode=preview）。
4. API（`routes.py`）：
   - `POST /api/projects/:id/preview/still` `{sceneId,time,profile}` → PNG 或 202；
   - `POST /api/projects/:id/preview/segment` `{sceneId,start,end,profile}` → `{jobId}`；
   - `POST /api/projects/:id/preview/film` `{profile:"draft"|"review"}` → `{jobId}`；
   - `GET/DELETE /api/preview/jobs/:id`；`GET /api/projects/:id/preview/cache`。
   - 预览 job 内存字典即可（Phase 7 再接 Job 表）；取消只在帧边界。
5. 防抖/优先级：
   - 同项目/同 scene 的新 still 请求取消旧请求（latest wins）；250ms 防抖。
   - F02 运行中，预览通过 CDP 页并发生成，不抢 `chrome-queue`；若 9222 不可用，最多等 3s，
     返回 `E_PREVIEW_BUSY` + ETA。
6. 测试：
   - 5s/40s F02 运行中连续请求 still，记录 p50/p95；
   - 20 次拖动只保留最后一次；同参数二次 ≤300ms；
   - 预览 PNG 有 `PREVIEW` 水印；`/runs/:id/artifacts` 不新增预览产物、Approvals 不增加；
   - 5s 片段 mp4 ≤20s。

**退路**：若 CDP 页 p95 >6s，改为 F02 每 10 帧分块、块间释放 `chrome-queue`/`port-8787`，
让预览独立启动 Chrome；仍必须单个 Chrome 串行。

### 6.2 Phase 6 · 档位 draft/review/final（FR-24）

- 新增 `render.profile.json` 或项目 profile 字段：
  - draft 960×540/12、review 1280×720/24、final 1920×1080/24。
- **F02 只跑 final**；E05 跑 review proxy；D02 出 draft+review 静帧；整片 draft/review 走
  PreviewService `/preview/film`，不写 `out/frames`。
- `scene_hash` 包含 profile；不同 profile 缓存不共享。
- G07 前检查最新 F02 manifest `profile=final` 且 run 匹配；缺失 → `E_FINAL_REQUIRED`。
- QA 阈值按 profile（draft 只查 missing/black；review 运动/同步；final 全量）。
- 测试：40s draft/review/final 耗时；G07 拒绝 review；切档不重跑已完成 final。
- 注意：G05/G06 当前 `amix duration=first`/伪同步是 R2.5 范围；R2.0 final QA 不得让它假通过。

### 6.3 Phase 7 · 持久化 Job + 崩溃恢复（FR-29）

- 扩展 `Job`：priority/attempts/lease_until/heartbeat_at/parent_id/cancel_requested/progress/eta/
  error_code/error_msg；迁移用 `schema_migrations`（SQLite 幂等）。
- 状态机：queued→leased→running→succeeded/failed/canceled/retry_wait；租约 30s/心跳 5s；
  启动扫描过期租约 → queued；`attempts>=max` → failed。
- 队列 API：`GET /jobs`、`GET /queue`、`POST /jobs/:id/cancel|retry`；优先级 preview 100 /
  interactive 80 / batch 40 / delivery 20。
- RunEngine 的 `ACTIVE/CANCELS` 落库；启动恢复 running Run。
- 孤儿清理：`/tmp/ff-chrome-*`、8787 无主服务、已结束 run 的 ffmpeg；Chrome profile 带
  run_id/job_id，避免并发 Run 共用 `/tmp/ff-F02`。
- 测试：F02 kill -9 → 重启 ≤60s 回 running；连续 3 次崩溃；无孤儿 Chrome；帧数正确。

### 6.4 Phase 8 · 黄金项目与视觉回归（FR-30）

- `fixtures/golden/5s|15s|40s/`：文案、风格、profile、期望静帧/关键帧、manifest。
- `scripts/golden_run.py`：建项目 → F06 → 6 帧 SSIM/pHash + program 文字断言 → 报告。
- 5s 必跑；15s/40s nightly；BDD 4 场景（参数化出片、单场景增量、预览优先级、交付 final）。
- **必须真实跑 40s**：验证 `renderedFrames ≤25%`、F02 墙钟 ≤全量 20%、draft ≤8min。
- **必须用干净 rumor 副本**重新跑 imported legacy：46/46、master 39.5s；不要复用旧 NodeRun 状态。
- 视觉回归阈值 SSIM ≥0.98、pHash 汉明 ≤6；失败给 diff 图 + scene/layer 定位。
- R2.0 全部 DoD 通过后再申请 R2.5；不要自行扩范围。

---

## 7. 命令、环境、复现

### 7.1 开发与测试

```bash
./dev.sh                                                   # API 7860 + Web 3000
cd server && uv run pytest tests -q                        # 52 passed
cd .. && uv run --project server python scripts/e2e_ui.py   # UI 8 场景
uv run --project server python scripts/smoke_m1.py          # 46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量
uv run --project server python scripts/drive_run.py <run> <project>  # 旧全链驱动
```

### 7.2 常用检查

```bash
curl -s http://127.0.0.1:7860/api/health
curl -s http://127.0.0.1:7860/api/engines
curl -s -X POST http://127.0.0.1:7860/api/engines/riso/validate
curl -s http://127.0.0.1:7860/api/runs/<id>/render-manifest
```

### 7.3 数据/清理

- 真实 DB：`~/.filmflow/filmflow.db`；当前有大量测试 project/run，属正常。
- 测试 DB：`/tmp/filmflow-test-home/filmflow.db`；删掉后下次 `pytest` 自动重建。
- 821? 无；8787 是 FrameServer；如果 `EADDRINUSE`，先查健康检查/残留进程。
- Chrome 残留：`/tmp/ff-F02`、`/tmp/ff-chrome-*`；确认无正在跑的 Run 后可清理。
- 76MB 风格库路径：`cat vendor/style-library.path`；不入 git。

---

## 8. 硬约束与范围（不要违反）

- 仅 `127.0.0.1`；不上传文件；不调用在线生成模型。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；边数 93。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占；预览不能新开第二个浏览器。
- 新项目禁止 `legacy_entry`；只有 `meta.imported=true` 旧项目可用 v1 harness。
- 改执行器行为必须升 `EXECUTOR_VERSION`。
- 路径白名单/禁止路径穿越；FrameServer 只服务 `/engine` 与 `/project`。
- 76MB 风格库与示例 mp4 不入 git；`vendor/fy-code-animation` 只给 Agent 查方法，不 import。
- R2.0 只做 FR-20/21/22/23/24/25/29/30；R3 时间轴/审片/音频 v2/资产库/批量/photo 不做。
- UI 自动化用系统 Chrome + 键盘输入（React 19 的 `fill()` 不触发 `onChange`）。

---

## 9. 已知限制 / 风险（交接时必须知道）

1. **40s 实测未跑**：5s 已过；40s 的 25% 指标目前只有规划单测（204/948=21.5%），Phase 8 必须真跑。
2. **rumor 新 Run 未在 v2 上重渲**：smoke 的 46/46 是旧 run #1 状态；Phase 8 用干净副本验证
   imported legacy；F02 legacy 若 `out/frames` 齐全会提前返回，必须清帧或复制项目。
3. **Preview 未实现**：F02 运行中无预览；Phase 5 是下一步。
4. **FR-24 只有 final 硬编码**：draft/review、G07 `E_FINAL_REQUIRED` 未做。
5. **Job 未落库**：kill -9 只能人工 resume；无租约/心跳/孤儿清理。
6. **黄金项目/视觉回归未建**：组件 fixture 只有 schema/JSON，未做 SSIM/pHash。
7. **非 riso 新项目被 C01 阻断**：ink/code-video 仍是 Contract 1.0，R2.0 不支持新项目；
   UI 仍可能选到这些风格，C01 会报 `E_ENGINE_API_UNSUPPORTED`。若要做，需先升它们的 Contract v2。
8. **音频 G 链不参与 5s 验收**：G01 无口播会失败；R2.0 A–F 验收不要求 G；R2.5 做音频。
9. **DocsEditor 只做了 script/时间轴只读**：时间轴拖拽/审片/音频 UI 是 R3。
10. **DB 迁移是 create_all + schema 1/2 记录**：若 Phase 7 加 Job 字段，需要真正的 SQLite ALTER
    幂等迁移，不要只 create_all。
11. **Chrome 进程语义**：`chrome-queue` 串行的是渲染操作；A04 previs 的常驻浏览器可能空闲存在，
    但 F02/预览不得新开第二个浏览器；Phase 5 必须用 CDP 或复用。
12. **跨项目缓存**：已修 C02/C03/B06/E03/E04 的已知路径；新增执行器若读项目相对文件，先检查
    缓存命中时文件是否存在，必要时用 artifact/inline。
13. **测试项目污染真实 DB**：大量 `it-*`/`r2-*` project/run；不影响运行，清理时先确认无引用。
14. **i18n**：DocsEditor/新提示目前中文为主；R2.0 不强制双语页面，但不要破坏原有 i18n。

---

## 10. 接手检查表（第一小时）

- [ ] `./dev.sh` 起服务；`/api/health`、`:3000` 正常。
- [ ] `cd server && uv run pytest tests -q` → **52 passed**（干净库首跑）。
- [ ] `uv run --project server python scripts/e2e_ui.py` → 8 场景全绿。
- [ ] `uv run --project server python scripts/smoke_m1.py` → 46 节点 / 93 边。
- [ ] `uv run --project server python scripts/verify_r2_5s_incremental.py` → PASS（66/54）。
- [ ] 打开 run #1 画布，确认 46 绿 + 审批历史；`out/film/master.mp4` 39.5s。
- [ ] 读本文 §5/§6/§9；确认从 Phase 5 开始，不重做 Phase 1–4。
- [ ] 任何“完成”申报附：测试输出、真实产物路径+sha/时长、UI 截图（如涉及）、API curl。

---

## 附录 A · v1 已验证能力（背景）

- 341 条风格真实索引（10 集计数、193 封面、矩阵 173/20/45/103）。
- 推荐 12、预演（riso/code-video/ink）、风格选择器完整交互。
- 46 节点 DAG 全链跑通（rumor-39s，46/46 succeeded，master 39.5s，AAC）。
- 音频：voice ingest → whisper/手动回退 → loudnorm −16LUFS → master。
- G07 门后打包；断点续跑；门控活同步；双语 UI/昼夜主题。
- v1 的 46 节点/caps/门/三类边/content_hash 是已验证底座，不要重写。

## 附录 B · v1 时期 16 条坑（仍适用）

1. `EDGES` 方向是 `(from 上游, to 下游, type)`；写反会让整张失效图反向。改边先跑 `test_dag_core`。
2. SQLModel 表名是单数小写（`noderun`，不是 `node_runs`）。
3. React 19 + Playwright `fill()` 不触发 `onChange`；用 `click + keyboard.type`，并等水合。
4. GLSL ES 3.0 无 int→float 隐式转换；shader 数值用 `.toFixed(1)`。
5. Chrome 渲染页不会自动退出；靠 `out/DONE` 早退 + 超时兜底。8787 端口支持健康检查复用。
6. 改执行器不升 `EXECUTOR_VERSION` = 缓存返回旧行为。
7. `task.json` 曾是绕过缓存键的侧信道；v2 已改为 Run 快照只读，不要再让执行器读可编辑 task.json。
8. D01(base) 在 E03(motion) 之前；E03 用同一编译器内部重编 base，不依赖 D01 产物。
9. F02 只跑 final；draft/review 走 PreviewService/E05，否则 F06 会被预览重渲打 stale。
10. G06 音画同步要用 `alignment.segment.end` vs `scene.last_text_at` 真算；旧 `min(abs(start-0))` 是伪计算。
11. G05 `amix duration=first` 会把音乐截到口播长度；v2 以片长为准，不足循环/淡出。
12. E04 旧版无出边；Phase 1 已补 `E04→E05/F02`，不要再写成死端。
13. Chrome 全局串行；PreviewService 不能开第二个浏览器。
14. E2E 的 `localStorage` 语言/主题会残留；测试前清 `ff.lang`/`ff.theme`。
15. `dev.sh` 的 `wait -n` 在 macOS bash 3.2 不可用；已改为 `kill -0` 轮询。
16. FrameServer 是全局单例：D02/E05/F02 必须持 `port-8787`；否则根目录被别的 Run 切换。
17. `ProcessRunner` 正常退出后必须取消 `_watch_cancel`；否则永久挂起。
18. SQLAlchemy JSON 原地修改用 `flag_modified`；不要只重新赋值同一个 dict。
19. 失败/skipped/canceled 是终态；重试走 `/retry`/`/resume`，不要在 `_ready_set` 里自动重排。
20. 继承的批准要补 caps；否则 F01/F02 会无门可等却 idle。

---

## 附录 C · 参考文档与 ADR

| 文档 | 说明 |
|---|---|
| `AGENTS.md` | Agent 入口与硬约束 |
| `docs/prd/PRD-002-production-workbench.md` | v2 30 FR / 两级执行 / 交付矩阵 |
| `docs/adr/ADR-0005-v2-ratification.md` | D1–D7 冻结裁决 |
| `docs/process/r2-plan.md` | R2.0 阶段计划（Phase 0.1–8） |
| `docs/tech-plan.md` | v1 技术方案 |
| `../filmflow-web-agent-prompt.md` | 宪法；§4.8 边表/§17/§19 已同步 93 边（仓库外，不在 git） |
| `vendor/README.md` | fy-code-animation 技能与 341 库路径 |
| `QODER_PROMPT.md` | 原始 R2.0 prompt（新 Agent 先看本文 §0/§6，不要从 Phase 0 重做） |

---

*任何“完成”的申报必须附测试输出、真实产物路径（sha/时长）、UI 截图、API curl。没有证据就写“未验证”。*
