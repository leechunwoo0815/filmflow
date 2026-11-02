# FilmFlow 交接文档（HANDOFF）

> 更新时间：2026-11-02 · R2.0 Phase 0.1–8 已完成；R2.5 FR-26/27/28 完成、FR-31 部分
> 当前基线：R2.5 代码 `65ba92a` / tag `r2_5-delivery`（FR-28）；FR-31 部分未打 tag；交接文档提交见 `git log` 最新一条。
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
cd server && uv run pytest tests -q                       # 93 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # UI 8 场景
uv run --project server python scripts/smoke_m1.py         # API 冒烟：46 节点 / 93 边
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量验收
```

`verify_r2_5s_incremental.py` 会真实建项目、跑到 F06、改 S02、再跑一个新 Run，并断言
`renderedFrames < total`、S01 hash 不变、S02 hash 变化、前一场帧哈希不变。第一次跑约 1.5 分钟。

### 0.3 当前下一步

**R2.0 已验收；R2.5 已获授权并完成 FR-26/27/28，下一步收尾 FR-31（音频占位/wizard 标题预演/示例只读副本）与 40s 交付实测。**
R2.0 证据见 §2.4–2.7/`docs/process/r2-acceptance.md`；R2.5 计划与证据见
`docs/process/r2_5-plan.md` / §2.8–2.11。不要开始 R3/R4，也不要重做 R2.0。

### 0.4 不要做的事

- 不要重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑。
- 不要新增 DAG 节点；46 节点/7 阶段/93 边不变。
- 不要把新项目回退到 `legacy_entry`；只有 `meta.imported=true` 的旧项目可走 v1 harness。
- 不要改执行器行为却不升 `EXECUTOR_VERSION`（当前 `2.4.2`）。
- 不要把 76MB 风格库/示例 mp4 提交进 git；不要把 `vendor/fy-code-animation` import 进服务端。
- 不要调用在线生成模型、上传文件、开第二个 Chrome。
- 不要用“页面能点”代替真实产物；所有完成申报必须附测试输出 + 产物路径/sha/时长 + curl/截图。

---

## 1. 当前状态（R2.0）

### 1.1 版本、提交、标签

| 项 | 值 |
|---|---|
| R2.5 代码 | `65ba92a`（FR-28 tag `r2_5-delivery`；FR-31 部分未打 tag） |
| Phase 1 tag | `r2-edge-fix` → `4f9e381` |
| Phase 3 tag | `r2-scene-dsl` → `53e6462` |
| Phase 4 tag | `r2-incremental` → `07b5237` |
| Phase 5 tag | `r2-preview` → `25ff0d9` |
| Phase 6 tag | `r2-profiles` → `426aa20` |
| Phase 7 tag | `r2-jobs` → `f5d5de1` |
| Phase 8 tag | `r2-golden` → `371ea4b` |
| R2.5 FR-26 tag | `r2_5-review` → `a37570d` |
| R2.5 FR-27 tag | `r2_5-audio` → `cd7312f` |
| R2.5 FR-28 tag | `r2_5-delivery` → `9c4ac00` |
| 测试 | **93 passed**（unit 74 / integration 12 / BDD 7） |
| UI E2E | 8 场景 / 9 检查全绿（约 16–20s） |
| API 冒烟 | 46 节点 / **93 边**通过 |
| EXECUTOR_VERSION | **2.6.2**（`server/app/engine/cachekey.py`） |

### 1.2 R2.0 八个 FR 的真实状态

| FR | 状态 | 说明 |
|---|---|---|
| FR-20 参数化渲染链 | [DONE] | 5s 新项目 `风从纸上起。纸不动，风先动。` 已跑通 D02 静帧与 E03–F06；画面文字来自 `source_span`/program，不再渲染 rumor 内容。 |
| FR-21 场景组件库 v1 | [DONE，视觉回归待补] | `scene-kit.js` 12 组件 + Python schema + `fixture/scene-kit.json`；组件 fixture 的 SSIM/视觉回归留 Phase 8。 |
| FR-22 场景级增量 | [DONE，40s 实测待补] | manifest + SceneState + F02 只渲 dirty；5s/2 场实测 66 渲/54 复用；40s/5 场规划单测 204/948=21.5%。 |
| FR-23 PreviewService | [DONE，UI 待接] | CDP 附加 F02 Chrome；单帧/片段/整片 job、PREVIEW 水印、500MB 缓存、latest-wins。F02 运行中 p50 1.25s/p95 1.31s，5s 片段 12.7s，缓存 5ms，不写 `out/frames`、不产生 Artifact/Approval。预览 UI 留 R3。 |
| FR-24 draft/review/final | [DONE，UI 待接] | `render.profile.json` + API；D02 review/draft 静帧；E05 720p/24 代理；F02 只跑 final 且 manifest 写 `profileSpec`；F05/G07 `E_FINAL_REQUIRED`；Preview draft/review；切档不重跑 final。 |
| FR-25 文档模型/快照 | [DONE] | ProjectDoc/DocRevision、409、版本/diff/回滚、Run 快照、新项目 task.json 只读、DocsEditor 自动保存/撤销/影响预估。 |
| FR-29 持久化 Job/恢复 | [DONE，单进程] | Job 表/租约/心跳/尝试次数/队列 API/启动恢复/孤儿清理；kill -9 后 F02 22.3s 恢复。预览 Job 不自动重试。 |
| FR-30 黄金项目 | [DONE] | 5s/15s/40s fixture + baseline；`golden_run.py` 6 帧 SSIM≥0.98/pHash≤6 + diff；BDD 4 场景；干净 rumor 46/46。 |

**重要诚实项**：
- `smoke_m1.py` 的 46/46 仍是旧 run #1 状态；Phase 8 已用**干净副本** `rumor-clean-20261102`
  run 150 重渲：46/46 succeeded、master 39.5s（manual 对齐）。
- 40s 已实测：改 S03 只渲 93/960=9.69%，F02 墙钟 13.05%；不再用 204/948 的规划数字。
- 5s 项目的 66/120=55% 是因为 S02 占全片 66 帧；40s 的 9.69% 才是 FR-22 的正式证据。

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
- Phase 5 验收项目：`/Users/litianyu/cc-projects/ai-v/filmflow-projects/r2-preview-98`
  （project 76 / run 86→87；预览缓存 75 文件 / 63MB；`out/preview/segment_S01_0.0_5.0_draft.mp4`）。
- Phase 6 档位项目：`filmflow-projects/r2-profiles-109`（run 111）。
- Phase 7 恢复项目：`filmflow-projects/r2-recovery-120`（run 134）。
- Phase 8 黄金：`filmflow-projects/golden-{5s,15s,40s}-*`（40s run 154→155）。
- 干净 rumor：`filmflow-projects/rumor-clean-20261102`（run 150；master 39.5s）。

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
cd server && uv run pytest tests -q                       # 93 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # 8 场景
uv run --project server python scripts/smoke_m1.py         # 46 / 93
```

---

### 2.4 Phase 5 预览验收（脚本可复现）

`scripts/verify_r2_preview.py` 实测输出（2026-11-02，project 76 / run 86→87 /
`filmflow-projects/r2-preview-98`）：

```
still idle: 1270ms chrome=owned size=(960, 540) watermark=True
still cache: 5ms cache=hit
during-F02 samples=14 attached=12
attached p50=1253ms p95=1314ms max=1314ms
preview vs final normalized SSIM=0.998717
latest-wins: 200=1 429=19
segment: succeeded 12.7s frames=60 rendered=60 reused=0 chrome=owned
segment meta={'width': 960, 'height': 540, 'fps': 12.0, 'frames': 60, 'duration': 5.0}
frame_delta=0 cache=75 files/63716KB artifacts 37->37 approvals 6->6
PASS: R2.0 Phase 5 PreviewService 验收通过
```

- F02 运行中预览样本全部 `X-Preview-Chrome: attached`；F02/F03/F04/F05/F06 未因预览失败。
- 片段二次请求：`reused=60`，0.5s（仅 ffmpeg 封装）；整片 draft 5s：13.2s。
- 单帧缓存 5MB 上限 500MB/项目；`GET /api/projects/:id/preview/cache` 可查。

### 2.5 Phase 6 档位验收（脚本可复现）

`scripts/verify_r2_profiles.py` 实测输出（2026-11-02，project 93 / run 115 /
`filmflow-projects/r2-profiles-112`）：

```
D02 stills: [('draft', (960, 540)), ('review', (1280, 720))]
E05 proxy frames=120 size=(1280, 720)
F02 manifest: profile=final profileSpec={1920×1080, 24, crf17}
preview film draft: succeeded 13.3s frames=60 960×540/12
preview film review: succeeded 32.5s frames=120 1280×720/24
draft vs final worst SSIM=0.998663（6 帧，motion program，归一化 960×540）
render profile override: draft 640×360/10；F02 status/cache_key 不变
PASS: R2.0 Phase 6 档位验收通过
```

- 导入 legacy 回归：rumor-39s 跑 E05/E06 → 474 帧 480×270/12fps，E06 `profile=legacy`、
  `static_len=6`，未被 review 档位误伤。
- `verify_r2_preview.py` 最终回归仍通过（attached p50 1.31s / p95 1.44s，5s 片段 12.7s）。
- `G07`/`F05` 的 `E_FINAL_REQUIRED` 由单测覆盖（缺 manifest / profile=review / Run 不匹配）。

### 2.6 Phase 7 崩溃恢复验收（脚本可复现）

`scripts/verify_r2_recovery.py` 实测（2026-11-02，project 102 / run 134 /
`filmflow-projects/r2-recovery-120`）：

```
api restarted in 3.6s; waiting F02 recover
F02 recovered after 22.3s
F05=succeeded frames=120 jobs=[(24, 'failed', 1)]
PASS: R2.0 Phase 7 崩溃恢复验收通过
```

- F02 运行中 kill -9 API；重启后单 Job attempts=1（崩溃只在恢复时计数），`out/frames` 补到 120 帧，
  F05 成功；无 `ff-F02-<run>` Chrome 残留。
- 单测覆盖：schema v3 ALTER、租约/心跳、retry_wait 复用同一 Job、attempts≥3 失败、
  preview Job 重启标 `E_JOB_INTERRUPTED`、队列优先级排序。
- 连续运行时 `verify_r2_5s_incremental` / `verify_r2_preview` / `verify_r2_profiles` 仍通过
  （预览 attached p50 1.50s / p95 1.92s，5s 片段 13.2s）。

### 2.7 Phase 8 黄金项目与视觉回归（脚本可复现）

`scripts/golden_run.py` 实测（H2 / 1920×1080 / 24fps，baseline 480×270）：

```
5s  (run 152): 6/6 SSIM=1.000000 pHashDist=0
15s (run 153): 6/6 SSIM=1.000000 pHashDist=0
40s (run 154): 6/6 SSIM=1.000000 pHashDist=0
40s 增量 (run 154→155): rendered=93 reused=867 / 960（9.69%）
  full F02 wall=108.48s；incremental F02 wall=14.15s（13.05%）
40s draft 预览：480 帧 / 100.3s（≤8min）
40s review 预览：960 帧 / 245.6s（≤18min）
```

- 5s/15s/40s fixture 与 baseline 在 `fixtures/golden/`；40s 5 场，改 S03 后只脏 93 帧。
- 干净 rumor 副本（`filmflow-projects/rumor-clean-20261102`，run 150）：
  **46/46 succeeded**、0 failed/skipped；`out/film/master.mp4` 70,204,586 bytes、39.500s、H.264+AAC。
  本机无 whisper CLI/model，按 ADR D7 使用 **manual alignment**（reference 的 5 段人工打点）；G02 `source=manual`。
- BDD 新增 4 场景（参数化出片/单场景增量/预览优先级/交付 final），共 7 个 BDD；全量 **83 tests**。
- 40s golden 全链约 4:25；最终 40s 增量在 2.4.2 上重测为 93/960、13.05%。

### 2.8 R2.5 FR-26 静帧审阅验收

`scripts/verify_r2_5_review.py` 实测（project 119 / run 163→164）：

```
D03 blocked before viewing: 未查看场景 S01..S05
D05 review scenes: S01=6 S02=1 S03=1 S04=6 S05=6
contact sheet 1920×1080 / scenes S01..S05
runB diff changed: ['S03']，其余 unchanged
PASS: R2.5 FR-26 静帧审阅验收通过
```

- `/review` Playwright 冒烟：22 张图、contact sheet 可见、全场景已看、100/200% 键盘可用。
- 修复：B06 同文档缓存命中不写 Run 快照 task.json，`_task_path` 回退只读 `card/task.json`。

### 2.9 R2.5 FR-27 音频工作台验收

`scripts/verify_r2_5_audio.py` 实测（project 140 / run 184）：

```
waveform 1200 peaks in 51ms
G01/G02/G05/G06/G07 = succeeded
audio metrics lufs=-15.0 true_peak=-9.5 sync_dev_s=0.0 sync_verified=True
stem voice/music/sfx = 5.0 / 5.0 / 5.0s
master 5.000s + audio stream
PASS: R2.5 FR-27 音频工作台验收通过
```

- 上传/录音 Take、主 Take、waveform、手动对齐、音乐许可均有 API；`/audio` 页面 Playwright 冒烟通过。
- G05 已改 sidechaincompress + 音乐循环/淡出；G06 使用 true peak 与 0.15s 同步阈值。
- 关键修复：G04 stdout 管道死锁；G07 批准后必须回 idle 才能执行 package。

### 2.10 R2.5 FR-28 交付验收

`scripts/verify_r2_5_delivery.py` 实测（project 142 / run 186）：

```
delivery job succeeded wall 26.1s
qc {master16/9/duration/audio/lufs/truePeak/captions/covers} 全 true
master16 1920×1080/24 + audio；master9 1080×1920/24 + audio，均 5.000s
9 文件 + zip（README/manifest/qc/rights）
PASS: R2.5 FR-28 交付 v1 验收通过
```

### 2.11 R2.5 FR-31 部分交付

- 首页 3 模板（口播 15s / 观点 30s / 产品 40s）→ `POST /projects/from-template` 一键建项目；
  冒烟 project 143/run 187。
- 空项目 5 步引导卡（可跳过）、`/help` 快捷键/Scene DSL/QA 错误。
- 待补：模板音频占位、wizard 标题预演、示例只读副本；因此 FR-31 仍为 PARTIAL。

## 3. R2.0 Phase 0.1–8 实施记录

### Phase 0.1 · 基线修复（提交 `4f9e381` 的一部分）

- `server/tests/conftest.py`：session 级 autouse `init_db()`，修复 BDD 在干净库首跑
  `no such table: style`；现在干净环境首跑全绿（当前 83 项）。
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

### Phase 5 · PreviewService（tag `r2-preview`）

- F02 Chrome 加 `--remote-debugging-port=9222 --remote-debugging-address=127.0.0.1`；
  `PreviewRenderer` 检测 `chrome-queue` holder 是否以 `:F02` 结尾：
  - F02 运行中：`playwright.chromium.connect_over_cdp`，在同一 Chrome 新建临时 page，渲染完只关 page，
    **不关浏览器**（`playwright.stop()` 已验证不会杀掉 F02 Chrome）。
  - F02 空闲：按 `chrome-queue` 启动临时 Chrome，渲染完关闭；不常驻第二个浏览器。
- `server/app/services/preview.py`：上下文解析（当前 docs/时间轴/tokens/engine/font/transitions）、
  base/motion program 编译、水印、缓存、job、latest-wins、交互优先。
- 单帧：native 1920×1080 渲染 → Lanczos 降到 960×540 → `PREVIEW` 水印；
  与 final 同刻帧归一化 SSIM 0.9987（直接 960 渲染会改变半调网点相位，仅 0.80）。
- 片段/整片：native 渲染后返回 JPEG q0.98 → Lanczos 降到目标尺寸 → 水印 → 写 `out/preview`；
  5s/60 帧 12.7s；二次请求 60 帧全缓存复用 0.5s。
- 缓存：`~/.filmflow/cache/preview/<project>/<hash>/<key>.png`；key 含 scene/film hash、时间、profile、
  尺寸、水印、`RENDERER_VER`；项目 LRU 500MB。
- 防抖/latest-wins：still 250ms 防抖 + `(project,scene)` generation；20 并发只保留最后 1 个，
  其余 429 `E_PREVIEW_BUSY {superseded:true}`。job 每帧检查 `_INTERACTIVE`，still 优先。
- 审计：`preview.segment`/`preview.film` 写 AuditLog；**不写 Artifact/Approval**。
- `film_spec.html` 新增 `__FF_PREVIEW_INIT__/__FF_PREVIEW_FRAME__/__FF_PREVIEW_FRAME_JPEG__/__FF_PREVIEW__`；
  preview 模式不 POST `/done`。
- 同时修复：F05/G07 读取 F04 跨项目缓存产物路径；C02 改异步 curl + 本地字体缓存，
  避免同步下载阻塞整个事件循环。

### Phase 6 · draft/review/final 档位（tag `r2-profiles`）

- 新 `server/app/services/render_profiles.py`：默认 draft 960×540/12 crf28、review 1280×720/24 crf22、
  final 1920×1080/24 crf17；`render.profile.json` 可覆盖 draft/review 与编码；
  final 尺寸/fps 由 `project.profile.json` 决定，不允许在 render profile 里改。
- `GET/PUT /api/projects/:id/render-profile`；PUT 校验后原子写文件并审计；导入项目允许低于 1080p。
- Run 快照新增 `render_profiles`；`PROFILE_NODES`（D02/E05/E06/F02/F03/F04/F05/G07）缓存键加入
  `renderProfilesSha`。切档只影响后续 Run/预览，不会重跑已完成 final。
- D02：新项目每个场景 native 渲染一次 → review 1280×720 + draft 960×540 两张；D04 按档位校验
  尺寸/亮度/场景覆盖；imported 仍只产 legacy 静帧。
- E05：review 代理 1280×720/24（`film_spec` proxy 支持 outW/outH/proxy_fps）；legacy 仍 480×270/12。
- E06：`profile=review/legacy`、`fps`、`policy`；`static_len=0.5s*fps`。
- F02：仍只跑 final；manifest 写 `profileSpec`；F04 使用 final crf/preset；F03 输出 `profile/policy`
  （draft 不查重复帧）。
- F05/G07：非导入项目必须存在 final manifest（profile/fps/frames/Run 匹配），否则
  `E_FINAL_REQUIRED`；导入项目跳过。
- PreviewService：draft/review 尺寸与编码来自项目 `render.profile.json`；单帧新增 `motion` 参数
  （E03 运动 program，用于与 final 同刻对比；默认仍用 D01 base program）。
- G06 改为真实口径：`alignment.segment.end vs scene.last_text_at`，输出 `sync_verified/sync_basis/
  approximate`；无对齐时不再伪报 `sync_dev_s=0`（G05/G06 完整修复仍属 R2.5）。

### Phase 7 · 持久化 Job / 崩溃恢复（tag `r2-jobs`）

- `Job` 表扩展（schema v3 幂等 ALTER）：priority/run_id/parent_id/attempts/max_attempts/
  lease_until/heartbeat_at/started_at/updated_at/cancel_requested/progress/eta/error_code/error_msg/lease_owner。
- RunEngine：每个 Run 落一个 `kind=run` Job；启动 running、5s 心跳、30s 租约；门等待/needs_changes
  停 `retry_wait` 并复用（不重复建 Job、不计崩溃 attempts）；成功/失败/取消落终态。
- 启动恢复 `services/jobs.py:recover`：中断的 run Job → queued（attempts+1，≥3 失败）；
  中断/排队的 preview Job → failed `E_JOB_INTERRUPTED`；无 Job 的幽灵 running Run → blocked；
  恢复后 `main.lifespan` 自动 `start_run`。
- 孤儿清理：`ps` 精确匹配 `/tmp/ff-` Chrome 与项目 out/frames|proxy ffmpeg；清理 >1h 的 profile。
  Chrome profile 改 `/tmp/ff-{node}-{run_id}`，避免并发 Run 共用。
- 队列 API：`GET /jobs`、`GET /queue`、`POST /jobs/:id/cancel|retry`；
  优先级 preview 100 / interactive 80 / batch 40 / delivery 20。
- PreviewService：segment/film Job 落库（priority 100），进度镜像；CDP 竞态回退临时 Chrome/429。
- Phase 7 结束时 EXECUTOR_VERSION 2.4.0；78 tests（Phase 8 后为 2.4.2/83）。

### Phase 8 · 黄金项目/视觉回归（tag `r2-golden`）

- `fixtures/golden/{5s,15s,40s}/spec.json` + `baseline/`（6 帧 480×270 PNG + pHash baseline）。
- `scripts/golden_run.py`：建项目 → F06 → 文案断言（场景 meaning 覆盖所有句）→ 6 帧 SSIM≥0.98/pHash≤6
  → 失败写 `out/golden_diff_<i>.png`；`--update` 生成 baseline。
- 40s fixture：5 句/5 场，S03 为短句（3.39s），改 S03 理论脏 93/960=9.69%。
- `scripts/verify_r2_recovery.py` 与 golden 一起作为 Phase 7/8 可复现证据。
- BDD `bdd/features/r2-workbench.feature` + `server/tests/bdd/test_r2_workbench_bdd.py` 4 场景。
- 修复（Phase 8 发现）：
  - `timeline` doc 在 materialize 初始化、旧项目首次快照补持久化；改文案不再重建时间轴。
  - D02/E05/F02/F04/G01/G05/G07 缓存加入项目根，避免文件产物留在旧项目（G07 master 曾不落新项目）。
  - B05/compiler 去掉 font-family 字重后缀（`Noto Sans SC 900/500` 导致 Canvas 文字不渲染）。
- 干净 rumor：手动对齐回退（无 whisper 模型）→ 46/46、master 39.5s。
- EXECUTOR_VERSION 2.4.2；83 tests（unit 64 / integration 12 / BDD 7）。

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
  → D02 entry.still_spec（native → review 720p + draft 540p；still_t=场景中段）
  → D05
  → E01/E02/E03 编译 scenes/<sid>.program.json + scenes/timeline_binding.json（内联 program）
  → E04 scenes/transitions.json
  → E05 entry.film_spec mode=proxy（review 720p/24）
  → E07
  → F01 8787 帧服务
  → F02 entry.film_spec mode=render（只 final）+ renders/final/manifest.json（profileSpec）+ SceneState
  → F03 scene_report（profile/policy）
  → F04 ffmpeg（final crf/preset）→ F05 QA（final 校验）→ F06
  → G...（G07 再校验 final manifest）
```

预览旁路（不新增节点、不进 DAG）：

```
docs(当前) + tokens/font/engine
  → PreviewService.resolve_context
  → compile base/motion program
  → F02 运行中? CDP attach 9222 : 临时 Chrome（chrome-queue）
  → 单帧 native render → Lanczos → PREVIEW 水印 → 缓存 → PNG
  → 片段/整片 native render(JPEG q0.98) → Lanczos → 水印 → out/preview/*.mp4
```

### 4.2 imported 旧项目

- `Workflow.graph_json.meta.imported=true`（`projects_import` 现在会持久化，已修 `flag_modified`）。
- D02/E05/F02 走 `legacy_entry.still/film`（rumor 原版 harness）。
- 不生成 v2 program；D01 保留 v1 `still_spec`；G 链保持原样。
- 新项目**禁止**回退 legacy；缺 film_spec → `E_ENGINE_API_UNSUPPORTED`。

### 4.3 缓存

- `EXECUTOR_VERSION=2.4.2`，任何执行器行为变化必须升。
- 节点缓存键 = version + params + 上游产物 sha + caps + `doc_snapshot_sha`（DOC_NODES）。
  `PROFILE_NODES` 额外加入 `renderProfilesSha`；改 `render.profile.json` 不会复用旧档位产物。
  `PROJECT_LOCAL_NODES`（D02/E05/F02/F04/G01/G05/G07）额外加入 `projectRoot`，文件产物不会跨项目复用。
- 场景 manifest hash = program + tokens lock + engine sha + **C02 源字体** + profile + 邻接 transitions。
- 跨项目缓存注意：E03 binding 已内联 program；F02 读 E03/E04 artifacts；C02/C03 有产物路径回退；
  B06 `task_id` 已进缓存键。

### 4.4 锁

- `chrome-queue=1`：所有 Chrome 渲染串行。
- `ffmpeg=1`。
- `port-8787=1`：F01 与 **D02/E05/F02** 都持有；任何一个渲染节点运行期间，FrameServer 根不能被
  别的 Run 切换。预览不读 8787：F02 运行中通过 CDP 附加同一 Chrome；空闲时临时 Chrome 只用 `chrome-queue`。
- F02 Chrome profile：`/tmp/ff-F02`；已加 `--remote-debugging-port=9222` 供预览 CDP 附加。
  F02 每个渲染区间启动一次 Chrome；区间之间 9222 可能短暂不可用，PreviewService 最多等 3s，
  超时返回 `E_PREVIEW_BUSY`（不会另起第二个 Chrome）。
- PreviewService 空闲时自己拿 `chrome-queue` 启动临时 Chrome；不使用 `port-8787`（payload 内联 + `file://` 页面）。

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
| 预览服务 | `server/app/services/preview.py`；API 在 `routes.py` 的 `preview/*` |
| 渲染档位 | `server/app/services/render_profiles.py`、项目 `render.profile.json` |
| 持久化 Job/恢复 | `server/app/services/jobs.py`、`main.py` lifespan、`runengine.py` |
| 黄金项目/回归 | `fixtures/golden/`、`scripts/golden_run.py`、`server/tests/bdd/test_r2_workbench_bdd.py` |
| 文档模型/API | `server/app/services/project_docs.py`、`server/app/api/routes.py` |
| 引擎页 | `engines/riso/entry/{still_spec,film_spec}.html`、`assets/{scene-kit,scene-render,riso-core}.js` |
| 编辑器 | `web/src/app/editor/page.tsx`、`web/src/components/DocsEditor.tsx` |
| 文档 | `docs/prd/PRD-002-production-workbench.md`、`docs/adr/ADR-0005-v2-ratification.md` |

---

## 5. R2.0 新增踩坑（按优先级）

1. **`EXECUTOR_VERSION`**：改任何执行器行为不升版 = 缓存返回旧行为。当前 `2.4.2`。
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
18. **Chrome 进程**：F02 用 `/tmp/ff-F02` 且暴露 9222；预览附加前要确认 `9222` 可连接；
    不要启动第二个 Chrome 做预览（F02 空闲时临时 Chrome 例外，必须持有 `chrome-queue`）。
19. **`dev.sh`**：macOS bash 3.2 不支持 `wait -n`；当前用 `kill -0` 轮询。
20. **调度 deadlock**：无 runnable、无 pending 门但不是终态时 Run 标 `blocked`；不要静默
    running。排查先看 caps 和 failed 节点。
21. **F04 跨项目缓存**：F04 命中旧 Run 时 `out/film/intermediate.mp4` 只在旧项目内容寻址目录；
    F05/G07 必须用 `_upstream_file(ctx,"F04","MP4",...)`，不要直接读当前项目路径（否则 ffprobe 失败）。
22. **C02 禁止同步下载**：同步 `subprocess.run(curl)` 会阻塞 FastAPI 事件循环（health 都超时）；
    已改 `ctx["runner"].run` + `--max-time 120` + `~/.filmflow/cache/fonts` 与既有 C02 产物回退。
23. **预览分辨率/网点**：直接 960p 渲染会改变 RISO 半调网点相位，与 final 归一化 SSIM 仅 ~0.80；
    单帧/片段统一 native 渲染后 Lanczos 降采样（单帧 PNG；片段 JPEG q0.98 再降采样），SSIM 0.9987。
24. **F02 CDP 生命周期**：9222 只在 F02 每个渲染区间存在；预览仅在 `chrome-queue` holder 以 `:F02`
    结尾时附加，最多等 3s；不可用返回 `E_PREVIEW_BUSY`，**不得**另起第二个 Chrome。
25. **Playwright 附加关闭**：attached 模式只 `page.close()+playwright.stop()`，**不要** `browser.close()`；
    后者可能关闭 F02 浏览器。已实测 `pw.stop()` 不会杀 Chrome。
26. **预览优先级**：job 每帧检查 `_INTERACTIVE` 并让位 still；`_PAGE_SEM=2` 限制同时求值页面；
    still 250ms 防抖 + generation 丢弃旧请求。不要为 job 长期占住 page semaphore，否则编辑预览被批处理堵住。
27. **预览不落 final**：预览只写 `out/preview/` 与 `~/.filmflow/cache/preview`；绝不写 `out/frames`、
    不登记 Artifact、不产生 Approval；`film_spec` preview 模式不发 `/done`。
28. **final 尺寸锁定**：`render.profile.json` 的 final width/height/fps 必须与 `project.profile.json`
    一致；要改 final 分辨率先改项目 profile。导入项目允许低 final（allow_low_final）。
29. **D02 档位静帧**：新项目每场 artifact meta 必须带 `profile=review|draft`；D04 依赖它校验尺寸与
    全场景覆盖。imported 的 meta 是 `legacy`，不要套 review/draft 覆盖检查。
30. **E05 帧率分歧**：新项目 review 代理是 1280×720/24；imported legacy 仍是 480×270/12。
    不要把 review 的帧数/static_len 套到 imported，否则 E05 会缺帧、E06 阈值漂移。
31. **final 门禁**：F02 只跑 final；F05/G07 调 `ensure_final_ready`，manifest 缺失/非 final/
    run 不匹配 → `E_FINAL_REQUIRED`。G07 人工门批准前也会检查；imported 跳过。
32. **档位快照**：Run 快照的 `render_profiles` 不可变；`PROFILE_NODES` 缓存键含 `renderProfilesSha`。
    修改 `render.profile.json` 只影响后续 Run/预览，不得让已完成 final 重跑或失效。
33. **预览一致性口径**：单帧默认 D01 base program；与 final 同刻对比要传 `motion=true`（E03 运动
    program），并避开转场帧。draft mp4 是 crf28，H.264 会把抽帧 SSIM 拉到 ~0.95；原始 PNG 为 0.9987。
34. **验收脚本时序**：门可能在缓存/继承下直接 succeeded，`wait_status(want=...)` 会永久等 pending；
    脚本应先看状态，只对仍 pending 的门签字。`smoke_m1.py` 与 Phase 4/5/6 verifier 已按此修。
35. **attempts 语义**：`attempts` 只在启动恢复遇到中断 Job 时 +1；`start_job` 不得自增，
    否则每个门批准重启都会消耗重试预算。≥max_attempts → Job failed + Run failed。
36. **门等待复用 Job**：Run 因等门/needs_changes 退出时 Job 停 `retry_wait`（不是 failed），
    门批准 `start_run` 复用同一 Job；不要每次重启都新建 Job。
37. **启动恢复边界**：单进程假设。恢复会杀掉 `/tmp/ff-*` Chrome/项目 ffmpeg，并重启中断 Run；
    不要同时跑两个 API worker，否则会互相杀进程/抢 8787。
38. **Job 迁移**：`create_all` 不会给旧表补列；`db._migrate_job_table` 用幂等 ALTER + schema v3。
    新增 Job 字段必须同时改模型、迁移和 `test_jobs`。
39. **preview Job 不自动重试**：预览参数在内存，重启后统一标 `E_JOB_INTERRUPTED`；用户重新请求。
    Run Job 才自动恢复。
40. **Chrome profile**：渲染 profile 用 `/tmp/ff-{node}-{run_id}`；预览 CDP 附加可能遇到 F02
    区间结束，服务会先等 0.4s：F02 已空闲改临时 Chrome，仍忙返回 429。
41. **队列优先级是元数据**：`GET /queue` 排序 preview>interactive>batch>delivery；真正的抢占仍由
    PreviewService 的 `_INTERACTIVE` 帧间让位实现，不要以为改 priority 就会抢占 RunEngine。
42. **恢复验收**：`verify_r2_recovery.py` 会杀/重启 `dev.sh`；不要在有人正在用工作台时跑。
    恢复时间从 kill -9 计，实测 22.3s（API 重启 3.6s）。
43. **timeline 必须持久化**：materialize 要初始化 script/profile/timeline 文档；旧项目首次快照会补
    timeline。否则改一句会按新句长重建时间轴，所有场景时长漂移 → 全量重渲。
44. **项目本地文件节点**：D02/E05/F02/F04/G01/G05/G07 的缓存键必须含 projectRoot；否则命中旧项目
    产物会留在旧项目，消费者按当前项目路径找不到（G07 master 曾因此缺失）。
45. **font-family 不能带字重**：A06 的 type 可能是 `Noto Sans SC 900/500`；B05/compiler 必须剥成
    `Noto Sans SC`，否则 Canvas `ctx.font` 非法、文字完全不渲染（画面只剩纸纹）。
46. **golden baseline**：只有有意改视觉时才 `--update`；baseline 与 H2/1920×1080/24fps 绑定。
    机器/字体/风格库变化会触发 SSIM/pHash 回归，先看 `out/golden_diff_<i>.png`。
47. **40s fixture 的 S03 是短句**：这是为了让「改 S03」脏帧 ≤25% 的可复现设计；改文案/时长后
    必须重算 dirty 预期并更新 baseline。
48. **干净 rumor 无 whisper**：本机没有 whisper CLI/model，G02 用 reference 的人工打点（source=manual，
    ADR D7 允许）；不要伪报 whisper。G 链完整音频修复仍属 R2.5。
49. **golden 只看 A–F**：5s/15s/40s 黄金项目没有口播，G01 会失败；golden_run 以 F06 为完成点，
    只对 D/E/F 失败报错。不要用 G 状态判断黄金通过。
50. **BDD 不启动 Chrome**：4 个 R2 BDD 场景是服务级（编译/规划/队列/final 校验）；真实出片由
    golden_run 与 Phase 4/5/6/7 verifier 覆盖。

---

## 6. R2.0 Phase 6–8：Phase 5–6 已完成，Phase 7–8 可直接开工

### 6.1 Phase 5 · PreviewService（FR-23）——[DONE]

**已完成**（tag `r2-preview`，证据见 §2.4）：F02 运行中单帧 p50 1.25s / p95 1.31s；
5s 片段 12.7s；缓存 5ms；不写 `out/frames`、不产生 Artifact/Approval；`PREVIEW` 水印。
下面是已落地的设计与测试项，后续改预览行为先看 §5 的 21–27 条坑。

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
   - 预览 job 内存字典 + Phase 7 已落 Job 表（priority=100）；取消只在帧边界。
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

### 6.2 Phase 6 · 档位 draft/review/final（FR-24）——[DONE]

- 新增 `render.profile.json` 或项目 profile 字段：
  - draft 960×540/12、review 1280×720/24、final 1920×1080/24。
- **F02 只跑 final**；E05 跑 review proxy；D02 出 draft+review 静帧；整片 draft/review 走
  PreviewService `/preview/film`，不写 `out/frames`。
- `scene_hash` 包含 profile；不同 profile 缓存不共享。
- G07 前检查最新 F02 manifest `profile=final` 且 run 匹配；缺失 → `E_FINAL_REQUIRED`。
- QA 阈值按 profile（draft 只查 missing/black；review 运动/同步；final 全量）。
- 测试：5s draft 13.2s / review 31.6s / final 全链约 1 分钟；40s 计时留 Phase 8。
  G07 拒绝 review、切档不重跑已完成 final 已由 `verify_r2_profiles.py` + 单测覆盖。
- 注意：G05 `amix duration=first` 属 R2.5；G06 已在 Phase 6 改为真实口径并输出
  `sync_verified/approximate`（无对齐不伪报 0），但尚未设硬阈值/失败门，Phase 8 标定。

### 6.3 Phase 7 · 持久化 Job + 崩溃恢复（FR-29）——[DONE]

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

### 6.4 Phase 8 · 黄金项目与视觉回归（FR-30）——[DONE]

- `fixtures/golden/5s|15s|40s/`：文案、风格、profile、期望静帧/关键帧、manifest。
- `scripts/golden_run.py`：建项目 → F06 → 6 帧 SSIM/pHash + program 文字断言 → 报告。
- 5s 必跑；15s/40s nightly；BDD 4 场景（参数化出片、单场景增量、预览优先级、交付 final）。
- **必须真实跑 40s**：验证 `renderedFrames ≤25%`、F02 墙钟 ≤全量 20%、draft ≤8min。
- **必须用干净 rumor 副本**重新跑 imported legacy：46/46、master 39.5s；不要复用旧 NodeRun 状态。
- 视觉回归阈值 SSIM ≥0.98、pHash 汉明 ≤6；失败给 diff 图 + scene/layer 定位。
- R2.0 全部 DoD 通过后再申请 R2.5；不要自行扩范围。

### 6.5 R2.0 DoD 验收结论（2026-11-02）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 5s 新项目全链出用户文案 | PASS | `fixtures/golden/5s`；run 152 |
| 5s 改 S02 只渲 S02+邻接 | PASS | 66/120；Phase 4 verifier |
| 40s 改 S03 只渲脏场景 | PASS | 93/960=9.69%；F02 墙钟 13.05%（run 154→155） |
| 预览 F02 中 p50/p95 | PASS | 1.50s / 1.92s；片段 13.2s；缓存 5ms |
| 档位 D02/E05/F02/G07 | PASS | D02 双静帧、E05 720p/24、F02 only-final、`E_FINAL_REQUIRED` |
| 40s draft/review/final 耗时 | PASS | draft 100.3s / review 245.6s / final F02 108.5s（全链 4:25） |
| Job kill -9 ≤60s | PASS | F02 22.3s 恢复；frames=120；attempts=1 |
| 黄金 5s/15s/40s | PASS | 6 帧 SSIM 1.0 / pHash 0；40s baseline 已入库 |
| 干净 rumor imported legacy | PASS | 46/46；master 39.500s H.264+AAC；manual 对齐 |
| BDD / 测试 | PASS | BDD 7（R2 4 场景）；83 tests |

结论：**R2.0 Phase 0.1–8 DoD 通过**。未开始 R2.5；UI 接线（预览/档位/时间轴）与 G05/G06
完整音频修复属于后续阶段，详见 §9。

### 6.6 R2.5 计划与进度（老板已授权）

| FR | 状态 | 说明 |
|---|---|---|
| FR-26 全场景静帧审阅 | **DONE**（tag `r2_5-review`） | D01 长场景 6 帧、D02 contact sheet/stills_manifest、D03 逐场门禁、D04 review_diff、`/review` 页 |
| FR-27 音频工作台 v1 | **DONE**（tag `r2_5-audio`） | Take/录音、peaks、手动对齐、许可、sidechain、Stems、G06 TP/同步 |
| FR-28 交付 v1 | **DONE**（tag `r2_5-delivery`） | 9 文件、SRT、双封面、QC/zip；5s 26.1s |
| FR-31 新手引导 | **PARTIAL** | 3 模板/首页引导/帮助已做；音频占位/wizard 标题预演/只读示例待补 |

详见 `docs/process/r2_5-plan.md`。不要开始 R3/R4；FR-27/28/31 全部验收前不得宣称 R2.5 DoD。

---

## 7. 命令、环境、复现

### 7.1 开发与测试

```bash
./dev.sh                                                   # API 7860 + Web 3000
cd server && uv run pytest tests -q                        # 93 passed
cd .. && uv run --project server python scripts/e2e_ui.py   # UI 8 场景
uv run --project server python scripts/smoke_m1.py          # 46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量
uv run --project server python scripts/verify_r2_preview.py         # Phase 5 预览验收
uv run --project server python scripts/verify_r2_profiles.py        # Phase 6 档位验收
uv run --project server python scripts/verify_r2_recovery.py        # Phase 7 kill -9 恢复验收
uv run --project server python scripts/golden_run.py --project 5s    # Phase 8 黄金回归（5s/15s/40s）
uv run --project server python scripts/verify_r2_5_review.py        # R2.5 FR-26 审阅验收
uv run --project server python scripts/verify_r2_5_audio.py         # R2.5 FR-27 音频验收
uv run --project server python scripts/verify_r2_5_delivery.py      # R2.5 FR-28 交付验收
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
- Chrome 残留：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`；启动恢复会自动清理。
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

1. **40s 已实测**：改 S03 只渲 93/960=9.69%，F02 墙钟 14.15/108.48=13.05%；
   40s draft 100.3s、review 245.6s、final 全链 4:25。15s/40s 建议 nightly，5s 必跑。
2. **干净 rumor 已验证**：`rumor-clean-20261102` run 150 为 46/46 succeeded、master 39.5s；
   本机无 whisper，G02 使用 manual 对齐（source=manual，ADR D7），不是 whisper 实测。
3. **Preview 已完成但 UI 未接**：API/服务与验收已完成；DocsEditor/编辑器还没有预览按钮（R3）。
   片段 mp4 是 draft crf28，抽帧与 final 归一化 SSIM≈0.974（H.264 损失）；单帧 PNG 为 0.9987。
   Phase 6 的单帧新增 `motion=true`，用于与 final 同刻对比（默认仍是 D01 base program）。
4. **FR-24 已完成但无档位 UI**：API `GET/PUT /render-profile` 与预览/交付链路可用；页面顶部切档、
   「预计 X 分钟 / 复用 Y 帧」留 R3。draft mp4 crf28 抽帧 vs final SSIM ~0.95，原始 PNG 0.9987。
5. **Job 已落库但单进程**：Job/租约/心跳/恢复/孤儿清理已完成；只支持单个 API worker，不支持多 worker 抢占同一 Run。预览 Job 重启后不自动重试。
6. **黄金项目已建**：5s/15s/40s fixture + 6 帧 baseline；但 baseline 与 H2/1920×1080/24fps 和
   当前字体/风格库绑定，换风格库或 H2 tokens 会触发回归，需确认是有意变化再 `--update`。
7. **非 riso 新项目被 C01 阻断**：ink/code-video 仍是 Contract 1.0，R2.0 不支持新项目；
   UI 仍可能选到这些风格，C01 会报 `E_ENGINE_API_UNSUPPORTED`。若要做，需先升它们的 Contract v2。
8. **音频 G 链不参与 5s 验收**：G01 无口播会失败；R2.0 A–F 验收不要求 G；R2.5 做音频。
9. **DocsEditor 只做了 script/时间轴只读**：时间轴拖拽/审片/音频 UI 是 R3。
10. **DB 迁移是 create_all + 幂等 ALTER**：Job 已有 schema v3 `_migrate_job_table`；后续加字段仍需
    同时改模型、迁移与 `test_jobs`，不要只 create_all。
11. **Chrome 进程语义**：`chrome-queue` 串行的是渲染操作；A04 previs 的常驻浏览器可能空闲存在。
    F02 运行中预览必须 CDP 附加 9222（已实现）；F02 空闲时可临时启动一个 Chrome，但不得常驻第二个浏览器。
12. **跨项目缓存**：C02/C03/B06/E03/E04 用 artifact/inline；D02/E05/F02/F04/G01/G05/G07 已按
    projectRoot 隔离。新增执行器若写项目文件，必须加入 `PROJECT_LOCAL_NODES`，否则会丢产物。
13. **测试项目污染真实 DB**：大量 `it-*`/`r2-*` project/run；不影响运行，清理时先确认无引用。
14. **i18n**：DocsEditor/新提示目前中文为主；R2.0 不强制双语页面，但不要破坏原有 i18n。
15. **F02 固定 9222**：若本机已有其他进程占用 9222，F02 的新 Chrome 可能启动失败；排查先
    `lsof -i :9222`。后续可改为 `--remote-debugging-port=0` + `DevToolsActivePort` 发现端口。
16. **BDD 是服务级**：R2 的 4 个 BDD 不启动 Chrome；真实出片由 golden_run 和 verifier 覆盖。
17. **40s golden fixture 的 S03 短句**：为满足 ≤25% 脏帧的可复现设计；改 fixture 文案/时长要同步
    更新 baseline 与增量预期。

---

## 10. 接手检查表（第一小时）

- [ ] `./dev.sh` 起服务；`/api/health`、`:3000` 正常。
- [ ] `cd server && uv run pytest tests -q` → **93 passed**（干净库首跑）。
- [ ] `uv run --project server python scripts/e2e_ui.py` → 8 场景全绿。
- [ ] `uv run --project server python scripts/smoke_m1.py` → 46 节点 / 93 边。
- [ ] `uv run --project server python scripts/verify_r2_5s_incremental.py` → PASS（66/54）。
- [ ] `uv run --project server python scripts/verify_r2_preview.py` → PASS（attached p50/p95、片段 ≤20s、缓存 ≤300ms）。
- [ ] `uv run --project server python scripts/verify_r2_profiles.py` → PASS（D02 双静帧、E05 720p、F02 final、切档不重跑）。
- [ ] `uv run --project server python scripts/verify_r2_recovery.py` → PASS（F02 中 kill -9，≤60s 恢复、frames=120）。
- [ ] `uv run --project server python scripts/golden_run.py --project 5s` → PASS（6 帧 SSIM/pHash；15s/40s 可选）。
- [ ] `uv run --project server python scripts/verify_r2_5_review.py` → PASS（逐场查看/contact sheet/diff）。
- [ ] `uv run --project server python scripts/verify_r2_5_audio.py` → PASS（波形/对齐/许可/Stems/G06）。
- [ ] `uv run --project server python scripts/verify_r2_5_delivery.py` → PASS（9 文件、QC、zip、9:16）。
- [ ] 打开 run #1 画布，确认 46 绿 + 审批历史；`out/film/master.mp4` 39.5s。
- [ ] 读本文 §5/§6/§9；确认从 Phase 6 开始，不重做 Phase 1–5。
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
| `docs/adr/ADR-0006-preview-service.md` | PreviewService：同一 Chrome/CDP、全分辨率降采样、缓存与边界 |
| `docs/process/r2-plan.md` | R2.0 阶段计划（Phase 0.1–8） |
| `docs/process/r2-acceptance.md` | **R2.0 验收报告（DoD/证据/复现命令/已知缺口）** |
| `docs/process/r2_5-plan.md` | **R2.5 能审能交计划与 FR-26 状态** |
| `docs/tech-plan.md` | v1 技术方案 |
| `../filmflow-web-agent-prompt.md` | 宪法；§4.8 边表/§17/§19 已同步 93 边（仓库外，不在 git） |
| `vendor/README.md` | fy-code-animation 技能与 341 库路径 |
| `QODER_PROMPT.md` | 原始 R2.0 prompt（新 Agent 先看本文 §0/§6，不要从 Phase 0 重做） |

---

*任何“完成”的申报必须附测试输出、真实产物路径（sha/时长）、UI 截图、API curl。没有证据就写“未验证”。*
