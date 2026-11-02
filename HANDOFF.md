# FilmFlow 交接文档（HANDOFF）

> 更新时间：2026-11-02 · **R2.0 已验收；R2.5 FR-26/27/28/31 全部完成并通过实测**
> 当前代码基线：R2.5 代码 `64e6898` + FR-31/G07 QC 未提交改动；文档基线见 `git log` 最新一条。
> **先读本文 §0、§1、§5、§6；再读 `AGENTS.md`、`docs/process/r2_5-plan.md`、PRD-002、ADR-0005/0007。**
> 上下文压缩后继续开发时：从 §6.4 的 R2.5 总验收开始，不要回滚或重做 R2.0/R2.5 已完成部分。

---

## 0. 下一个 Agent 从这里开始（15 分钟）

### 0.1 工作目录与服务

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
./dev.sh                  # API :7860 + Web :3000
curl -s http://127.0.0.1:7860/api/health
```

Web 入口：`/`（模板/项目）、`/wizard`、`/canvas?project=&run=`、`/review?project=&run=`、
`/audio?project=`、`/delivery?project=&run=`、`/help`。
API 文档：`http://127.0.0.1:7860/api/docs`。

### 0.2 第一小时必做

```bash
cd server && uv run pytest tests -q                       # 102 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # UI 8 场景 ~16s
uv run --project server python scripts/e2e_onboarding.py   # FR-31 UI 冒烟
uv run --project server python scripts/smoke_m1.py         # 46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py
uv run --project server python scripts/verify_r2_preview.py
uv run --project server python scripts/verify_r2_profiles.py
uv run --project server python scripts/verify_r2_recovery.py   # 会杀/重启 dev.sh
uv run --project server python scripts/golden_run.py --project 5s
uv run --project server python scripts/verify_r2_5_review.py
uv run --project server python scripts/verify_r2_5_audio.py
uv run --project server python scripts/verify_r2_5_onboarding.py
uv run --project server python scripts/verify_r2_5_delivery.py
uv run --project server python scripts/verify_r2_5_delivery_40s.py
uv run --project server python scripts/verify_rumor_regression.py   # 干净 rumor 46/46
```

### 0.3 当前下一步（按优先级）

1. **R2.5 总验收**：逐项打勾 §6.4，附测试输出、产物路径/哈希、UI 截图/curl；全部已通过，
   可直接向老板申请 R2.5 签收。
2. 40s 交付已实测（190.0s，9 文件/QC 全绿）；干净 rumor 2.6.6 已 46/46。
3. G07 与交付包的边界已定：G07 只做 master + 核心 QC；交付包是显式 post-run 作业，
   必须等 G07 通过（[ADR-0007](docs/adr/ADR-0007-g07-qc-and-delivery.md)）。
4. 签收前**不要开始 R3/R4**（时间轴/审片/音频 v2/资产库/批量/photo 引擎）。

### 0.4 不要做的事

- 不要重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑；46 节点/93 边不变。
- 不要新增 DAG 节点；R2.5 的审阅/音频/交付都在服务/页面层。
- 不要把新项目回退 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 不要改执行器行为却不升 `EXECUTOR_VERSION`（当前 **2.6.6**）。
- 不要用“页面能点”代替真实产物；完成申报必须附测试、产物路径/哈希、UI 截图/curl。
- 不要跑 `verify_r2_recovery.py` 时同时使用工作台（它会 kill -9 并重启 dev.sh）。

---

## 1. 当前状态

### 1.1 提交与标签

| 项 | 值 |
|---|---|
| R2.5 当前代码 | `64e6898`（FR-27/交付修复；当前 HEAD 以 `git log` 为准） |
| R2.5 FR-26 tag | `r2_5-review` → `a37570d` |
| R2.5 FR-27 tag | `r2_5-audio` → `cd7312f` |
| R2.5 FR-28 tag | `r2_5-delivery` → `9c4ac00` |
| R2.0 起始 tag | `r2-edge-fix` → `4f9e381` |
| R2.0 Scene DSL | `r2-scene-dsl` → `53e6462` |
| R2.0 增量 | `r2-incremental` → `07b5237` |
| R2.0 预览 | `r2-preview` → `25ff0d9` |
| R2.0 档位 | `r2-profiles` → `426aa20` |
| R2.0 Job/恢复 | `r2-jobs` → `f5d5de1` |
| R2.0 黄金 | `r2-golden` → `371ea4b` |
| 测试 | **102 passed**（unit 83 / integration 12 / BDD 7） |
| EXECUTOR_VERSION | **2.6.6**（`server/app/engine/cachekey.py`；G07 master QC） |
| UI E2E | 8 场景全绿（约 16s）；FR-31 冒烟另 4 组 |

### 1.2 R2.0（已验收，8 FR）

| FR | 状态 | 关键实现 |
|---|---|---|
| FR-20 参数化渲染链 | DONE | docs → snapshot → base/motion program → still_spec/film_spec |
| FR-21 场景组件库 v1 | DONE | 12 组件 + fixture；视觉回归在 golden |
| FR-22 场景级增量 | DONE | manifest + SceneState；40s 改 S03 只渲 93/960=9.69% |
| FR-23 PreviewService | DONE | CDP 附加 F02、still/segment/film、水印、缓存、latest-wins |
| FR-24 draft/review/final | DONE | render.profile.json、D02 双静帧、E05 720p、F02 only-final、E_FINAL_REQUIRED |
| FR-25 文档/快照 | DONE | ProjectDoc/DocRevision、409、versions/diff/restore、Run 快照只读 |
| FR-29 Job/恢复 | DONE | Job 表、租约/心跳、retry_wait、启动恢复、队列 API、孤儿清理 |
| FR-30 黄金项目 | DONE | 5s/15s/40s fixture+baseline；SSIM 1.0；干净 rumor 46/46 |

### 1.3 R2.5（能审能交）

| FR | 状态 | 证据 |
|---|---|---|
| FR-26 全场景静帧审阅 | **DONE** | D01 长场景 6 帧、D02 contact sheet、D03 逐场门禁、D04 review_diff、`/review` |
| FR-27 音频工作台 v1 | **DONE** | Take/录音、waveform 49–51ms、手动对齐、许可、sidechain、Stems、G06 TP/同步 |
| FR-28 交付 v1 | **DONE（5s）** | 9 文件、16:9+9:16、SRT、双封面、manifest/qc/rights/zip；5s 26.1s |
| FR-31 新手引导 | [DONE] | 3 模板+音频占位、只读示例/克隆、向导用户标题 3 候选预演、Studio 5 步引导、`/help`；`verify_r2_5_onboarding.py` + `e2e_onboarding.py`。 |

### 1.4 环境与验收项目

- macOS · Python 3.13 · uv · Node ≥22 · 系统 Chrome · ffmpeg 9.x。
- 真实 DB：`~/.filmflow/filmflow.db`；测试 DB：`/tmp/filmflow-test-home/filmflow.db`。
- 风格库：`cat vendor/style-library.path`（76MB 外置，不入 git）。
- 40s 黄金/增量：`filmflow-projects/golden-40s-134`（project 119；run 154→155）。
- R2.5 审阅：同 project 119；run 163→164（D05 后 cancel）。
- R2.5 音频最终：`filmflow-projects/r2_5-audio-160`（project 151 / run 198）。
- R2.5 交付：`filmflow-projects/r2_5-delivery-153`（project 142 / run 186；
  `out/deliveries/186/`）。
- 干净 rumor：`filmflow-projects/rumor-clean-20261102`（project 115 / **run 222**；
  `out/film/master.mp4` 39.5s / 70,542,684B；2.6.6 复跑 **46/46**，90.6s）。
- FR-31 验收：project 155 / run 202（模板 15s draft），project 156 / run 203（示例克隆）。
- 40s 交付：`filmflow-projects/r2_5-delivery40-185`（project 174 / **run 223**，2.6.6 一次通过）；
  旧证据 `r2_5-delivery40-177`（project 166 / run 213，G07 parser 修复前 retry）。

---

## 2. 可复核证据（R2.0）

### 2.1 5s 参数化出片

`verify_r2_5s_incremental.py`：run1 120 帧、`out/film/intermediate.mp4` 1920×1080/24/5.000s；
D02 用户文案；F05 Y-SSIM 通过。

### 2.2 40s 增量

```
manifest2 rendered=93 reused=867 / 960 (9.69%)
full F02 wall=108.48s；incremental F02 wall=14.15s (13.05%)
```

- 改 S03 只脏 S03 + 离场转场帧；前两场帧哈希不变。
- 40s golden：`fixtures/golden/40s`，6 帧 SSIM 1.0 / pHash 0。

### 2.3 预览（FR-23）

- F02 运行中 attached p50 **1.50s** / p95 **1.92s**；5s 片段 **13.2s**；缓存 **5ms**。
- 20 并发拖动只留最后 1 个（1×200 + 19×429）。
- 不写 `out/frames`、不产生 Artifact/Approval；PREVIEW 水印。
- 单帧默认 D01 base；`motion=true` 用 E03 motion program 做同刻对比（SSIM 0.9987）。

### 2.4 档位（FR-24）

- D02 review 1280×720 + draft 960×540；E05 review 720p/24；F02 only-final。
- F05/G07 `ensure_final_ready`：manifest 缺失/非 final/Run 不匹配 → `E_FINAL_REQUIRED`。
- 切档不重跑已完成 final；40s draft 100.3s / review 245.6s。

### 2.5 Job/恢复（FR-29）

- F02 中 kill -9 API：**22.3s** 恢复；frames=120；单 Job attempts=1；无 Chrome 残留。
- 单 API worker 假设；预览 Job 重启标 `E_JOB_INTERRUPTED`，不自动重试。

### 2.6 黄金与干净 rumor（FR-30）

- 5s/15s/40s golden：6 帧 SSIM **1.000000** / pHash **0**。
- 干净 rumor（run 222，2.6.6）：**46/46 succeeded**、0 failed/skipped、90.6s；
  master **39.500s / 70,542,684B** H.264+AAC；G07 QC imported 路径只查音轨。
  历史 run 194 为 2.6.4 证据。
- 本机无 whisper，G02 用 manual alignment（source=manual，ADR D7）。

---

## 3. 可复核证据（R2.5）

### 3.1 FR-26 审阅

`verify_r2_5_review.py`（project 119 / run 163→164）：

```
D03 blocked before viewing: 未查看场景 S01..S05
D05 review scenes: S01=6 S02=1 S03=1 S04=6 S05=6
contact sheet 1920×1080 / scenes S01..S05
runB diff changed: ['S03']，其余 unchanged
PASS: R2.5 FR-26 静帧审阅验收通过
```

- `/review` Playwright：22 张图、contact sheet、全场景已看、100/200%、A/B、键盘、批准 D03/D05。
- 修复：B06 同文档缓存命中不写 Run 快照 task；`_task_path` 回退只读 `card/task.json`。

### 3.2 FR-27 音频

`verify_r2_5_audio.py`（project 151 / run 198）：

```
waveform 1200 peaks in 49ms
G01/G02/G05/G06/G07 = succeeded
audio metrics lufs=-16.0 true_peak=-10.5 sync_dev_s=0.0 sync_verified=True
stem voice/music/sfx = 5.0 / 5.0 / 5.0s
master 5.000s + audio
PASS: R2.5 FR-27 音频工作台验收通过
```

- `/audio` Playwright：Take/波形/对齐/许可 UI 正常。
- 关键修复：G04 解码改临时文件（stdout 64KB 死锁）；G07 批准后回 idle 执行 package；
  G05 `alimiter=limit=0.7:level=false`（否则自动拉响度到 −13.7LUFS/+0.1dBTP）。

### 3.3 FR-28 交付（5s + 40s）

**5s 回归**（project 173 / run 221，2026-11-02）：

```
G chain G05/G06/G07 = succeeded
delivery job succeeded wall 26.2s
QC {master16/9,duration,audio,lufs,truePeak,captions,covers}=true
master16 1920×1080/24 + audio；master9 1080×1920/24 + audio，均 5.000s
PASS: R2.5 FR-28 交付 v1 验收通过
```

**40s 实测**（project 174 / run 223 / `filmflow-projects/r2_5-delivery40-185`，2.6.6 全新一次通过）：

```
run wall 305.4s  E05/F02/F04/G05/G06/G07 = succeeded
G07 qc {duration:40.0,1920x1080,24fps,audio:true,lufs:-15.9,truePeak:-10.5}
delivery job succeeded wall 190.0s
qc {master16/9,duration,audio,lufs,truePeak,captions,covers}=true
master16 1920×1080/24 + audio 40.000s 7,588,145B
master9  1080×1920/24 + audio 40.000s 6,616,460B
captions 5 cues / maxLineChars 16 / maxCharsPerSec 2.31 / source=manual
covers 1920×1080 + 1080×1920；9 文件 + zip
g07Master sha256=089419501e35acbb...（delivery manifest 可反查）
PASS: R2.5 FR-28 40s 交付验收通过（run 305.4s / delivery 190.0s）
```

- **审批口径**：run 223 的 delivery manifest 记录 **7 条 run-local 审批**（A05/B08/D03/D05/E07/F06/G07）；
  G03 因内容哈希与 run 213 相同走了既有 `inherit` 策略，没有本 Run 的 Approval 行。
  DAG 实际是 **8 个人工门**（8+8 门），PRD 写的「9 条审批」与当前门数不一致；没有伪造第 9 条。
  需要严格逐 Run 审计时，应在 R3 把 inherit 范围收窄到同 workflow 并把继承审批写进 manifest。
- 包：`out/deliveries/<runId>/`：两个 master、`captions.zh.srt`、`cover_16x9.jpg`、`cover_9x16.jpg`、
  `manifest.json`、`qc.json`、`rights.json`、`FilmFlow-delivery.zip`。
- 9:16 由 Scene DSL 重排（不裁切 16:9）；封面取中间场景 reveal 完成后的帧。
- G07 master QC：`E_QC_LUFS/TRUE_PEAK/DURATION/RESOLUTION/FPS/AUDIO`；LUFS −20 由单测
  `test_master_qc.py` 证明阻断并给「重新混音到 −16」建议。
- 复现：`verify_r2_5_delivery.py`（5s）与 `verify_r2_5_delivery_40s.py`
  （全链或 `--project 174 --run 223 --root ...` 复用 G07 产物）。

### 3.4 FR-31 新手引导（DONE）

- 首页「做第一条片」3 模板（口播 15s / 观点 30s / 产品 40s）→ `POST /projects/from-template`。
- 模板 materialize 写 `card/audio.placeholder.json`（kind/duration/source）；`GET /projects/:id/audio`
  返回 `placeholder`；上传/录音后自动清除，不生成假音频。
- `fixtures/examples/catalog.json` 只读示例（voice15/product40）；`GET /examples` +
  `POST /examples/:id/clone` 复制为独立项目，路径全在工作区。
- `GET /wizard/titles?copy=` 本地切 3 个候选标题；向导第 3 步用所选风格预览图叠加用户标题，
  可切候选；`brief.title` 写入 materialize（项目名不再固定「向导草稿」）。
- Studio 首次进入显示 5 步引导（场景列表/单帧/改一句/diff/draft），可跳过、header「引导」重看、
  localStorage 记忆，不阻塞画布。
- 验收（2026-11-02）：
  - `verify_r2_5_onboarding.py`：project 155 / run 202；`audio.placeholder.json` 15s；
    15s draft 预览 960×540/12.0/15.0s，墙钟 **38.2s**；上传后占位清除；示例 project 156/run 203。
  - `e2e_onboarding.py`：首页 3 模板 + 2 只读示例；Studio 引导可跳过/重看/刷新不反弹；
    向导标题预演使用用户文案（`很多工作不是难，是重复`），3 候选可切换。
  - 修复 StylePicker 少 `min-h-0` 导致 640px 网格溢出压住标题预演的真实 UI bug。

---

## 4. 架构与关键文件

### 4.1 46 节点主链（未变）

```
docs → Run 快照 → A01 → B02/B06/B07 → C01/C02/C03/C04/C05
 → D01（program）→ D02（review/draft 静帧 + contact sheet）→ D03（逐场查看）→ D04（QA/diff）→ D05
 → E01/E02/E03（motion）→ E04（transitions）→ E05（review proxy）→ E06 → E07
 → F01（8787）→ F02（only final）→ F03 → F04 → F05 → F06
 → G01/G02/G03/G04/G05/G06 → G07
```

- D01/D02/E05/F02/F04/F05/G07 的 final/profile/项目本地缓存约束见 §5。
- 46/7/8+8/93 是硬约束；R2.5 新能力不新增节点。

### 4.2 预览（FR-23）

- `server/app/services/preview.py`：上下文解析、base/motion 编译、CDP/临时 Chrome、水印、500MB 缓存、
  latest-wins、segment/film job。
- F02 Chrome：`--remote-debugging-port=9222`；F02 运行中只附加同一 Chrome，空闲时临时 Chrome。
- 页面：`/review`、`/audio` 不依赖预览页；预览 API 独立。

### 4.3 档位（FR-24）

- `server/app/services/render_profiles.py`：draft/review/final；final 尺寸/fps 由项目 profile 锁定。
- Run 快照写入 `render_profiles`；`PROFILE_NODES` 缓存键含 `renderProfilesSha`。
- API：`GET/PUT /projects/:id/render-profile`。

### 4.4 Job/恢复（FR-29）

- `server/app/services/jobs.py`：Job 表、租约 30s/心跳 5s、retry_wait、启动恢复、孤儿清理、队列 API。
- `runengine.py`：每个 Run 一个 Job；阻塞停 retry_wait；包执行门（G07）批准后回 idle。
- `main.py` lifespan：cleanup_orphans + recover + start_run。
- 优先级：preview 100 / interactive 80 / batch 40 / delivery 20。
- **单进程假设**；不要同时跑两个 API worker。

### 4.5 R2.5 服务

- 审阅：D01 多 times；D02 `stills_manifest.json`（scene→times）+ 16 宫格 contact sheet；
  D03 逐场 viewed；D04 `review_diff.json`；D05 pending 返回 stills/contactSheet/diff。
- 音频：`server/app/services/audio.py`：Take 导入（base64→ffmpeg WAV）、主 Take、
  `card/audio.json`、waveform、`card/alignment.manual.json`、`card/music_license.json`。
  G01 读取主 voice Take；G02 manual 优先；G04/G05 读取主 music Take；G05 sidechain + loop + stems。
- 交付：`server/app/services/delivery.py`：9:16 variant compiler、frames render、SRT、covers、QC、
  manifest/rights、zip、Job。
- 页面：`/review`、`/audio`、`/delivery`、`/help`；首页模板与引导。

### 4.6 缓存/锁（必须理解）

- `EXECUTOR_VERSION=2.6.6`；改执行器必须升。
- `DOC_NODES` 缓存含 `doc_snapshot_sha`；`PROFILE_NODES` 含 `renderProfilesSha`；
  `PROJECT_LOCAL_NODES={D02,E05,F02,F04,G01,G05,G07}` 含 `projectRoot`。
- `chrome-queue=1`；`ffmpeg=1`；`port-8787=1`（F01/D02/E05/F02）。
- Chrome profile：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`。

### 4.7 文件地图

| 想改什么 | 去哪 |
|---|---|
| 节点/边/锁 | `server/app/engine/edges.py` |
| 调度/门/caps/缓存 | `server/app/engine/runengine.py` |
| 子进程 | `server/app/engine/runner.py` |
| D–G 执行器 | `server/app/engine/executors/pipeline.py`、`__init__.py` |
| Scene DSL | `server/app/engine/scene/*` |
| 增量 | `server/app/engine/render_manifest.py` |
| Run 快照 | `server/app/engine/snapshot.py` |
| 文档 | `server/app/services/project_docs.py` |
| 预览 | `server/app/services/preview.py` |
| 档位 | `server/app/services/render_profiles.py` |
| Job/恢复 | `server/app/services/jobs.py`、`main.py` |
| 音频 | `server/app/services/audio.py` |
| 交付 | `server/app/services/delivery.py` |
| UI | `web/src/app/{review,audio,delivery,help,page.tsx}`、`canvas/page.tsx` |
| 黄金 | `fixtures/golden/`、`scripts/golden_run.py` |

---

## 5. 踩坑清单（按优先级，必须看）

1. **EXECUTOR_VERSION**：改任何执行器行为必须升版；当前 2.6.6，否则缓存返回旧行为。
2. **task 快照回退**：B06 同文档缓存命中时不会写 `runs/<id>/docs/task.json`；`_task_path` 必须回退
   只读 `card/task.json`，否则 D01 空场景、D03/D04 失败。
3. **timeline 持久化**：materialize/首次快照落 timeline doc；编辑 script 不得重建 timeline，
   否则改一句导致全场景时长漂移、全量重渲。
4. **reading window**：`last_text_at=end-read_seconds`；B07 校验 `last_text_at+read_seconds≤end`；
   G06 用 `last_text_at+read_seconds` 作为句子对齐目标。
5. **项目本地缓存**：D02/E05/F02/F04/G01/G05/G07 写项目文件，缓存键必须含 projectRoot；
   新增文件产物节点必须加入 `PROJECT_LOCAL_NODES`，否则 master/帧留在旧项目。
6. **G07 门**：G07 是 human+package；gate_decide 必须把 NodeRun 置 idle（不是 succeeded），
   否则 package 永远不执行、master 缺失。G07 前 `ensure_final_ready`；imported 跳过。
7. **G05 音频**：必须 sidechaincompress + 音乐循环/淡出到片长；`alimiter=limit=0.7:level=false`
   （默认 level=true 会自动拉响度）；mix WAV 有多份（mix/voice/music/sfx），取 `meta.mix` 或
   `card/mix.wav`，不要取最后一个 WAV。
8. **G04 解码**：ffmpeg 输出必须落临时文件，不能写 stdout 管道（大音频 64KB 死锁）。
9. **F02 CDP**：9222 仅在 F02 渲染区间可用；预览附加需 3s 重试，F02 结束竞态回退临时 Chrome/429；
   attached 模式只关 page，不关浏览器。
10. **预览质量**：单帧 native→Lanczos；片段 native JPEG q0.98→Lanczos；直接 960p 会让半调网点
    相位错位（SSIM 0.80）。缓存键含 out spec/RENDERER_VER。
11. **D02/D04**：contact sheet 是 PNG 但 D04 必须跳过（`meta.contact_sheet`）；D02 review/draft
    meta.profile 必须存在；D03 新项目逐场查看、imported 保持 ≥3 区域。
12. **job attempts**：只在启动恢复时 +1；gate 重启/retry_wait 不自增；≥max 才失败。
13. **SQLAlchemy JSON**：原地改 `graph_json` 后必须 `flag_modified`。
14. **C02 字体**：异步 runner + 本地 cache/既有 artifact 回退；禁止同步 subprocess curl 阻塞事件循环。
15. **F04 跨项目**：即使已有 projectRoot，消费者仍优先用 `_upstream_file`（内容寻址）兜底。
16. **FrameServer**：8787 全局单例；D02/E05/F02 持 `port-8787`；否则根目录被别的 Run 改。
17. **ProcessRunner**：正常退出后 cancel `_watch_cancel`；否则永久挂起。
18. **字体 family**：B05/compiler 去掉 `900/500` 字重后缀，否则 Canvas 文字不渲染。
19. **golden baseline**：与 H2/1920×1080/24/字体绑定；只有有意改视觉才 `--update`；失败看 diff。
20. **交付封面**：9:16 封面取中间场景 reveal 完成后的帧，不要取转场/未揭示帧；16:9 取 D02 review。
21. **交付 QC**：LUFS −16±1、TP≤−1.5、字幕行宽≤16/速度≤9、封面精确尺寸；失败 `E_DELIVERY_QC`。
22. **React 19 UI**：Playwright 用 click+keyboard.type，`fill()` 不触发 onChange。
23. **manual alignment**：whisper 缺失必须显式 `manual`，不要伪装词级；本机无 whisper model。
24. **单进程 Job**：启动恢复会杀 `/tmp/ff-*` Chrome/项目 ffmpeg；不要多 worker。
25. **非法范围**：不要开始 R3（时间轴/审片/音频 v2/资产库/批量/photo）；R2.5 收尾优先。

---

## 6. 剩余工作（R2.5 收尾）

### 6.1 FR-31 新手引导（PARTIAL → DONE）

1. **模板音频占位**：`/projects/from-template` 生成 15/30/40s 占位 voice + music（或提供
   “填充占位音频”按钮），写 `card/audio.json`/license/alignment；确保 G06 能过（不要纯静音）。
2. **wizard 标题预演**：当前 `/styles/:id/preview` 使用风格自带图；Step 3 需用用户标题渲染
   3 个候选标题的缩略图（可复用 previs 渲染器/标题文本参数），避免固定「风」。
3. **示例只读副本**：示例项目 `meta.example=true`；所有写 API 阻断；提供
   `POST /projects/:id/clone` 复制为我的项目；路径仍须 project root 内。
4. **Studio 引导**：首次进入 editor/canvas 的 5 步 overlay（场景→单帧→改一句→diff→draft），
   可跳过/重看，不阻塞老用户。
5. **10 分钟走查**：新模板→改文案→音频占位→draft→审阅→交付，记录耗时与截图。

### 6.2 40s 交付实测（FR-28，已通过）

- 40s 项目（project 174 / run 223）全链到 G07（305.4s），`POST /projects/:id/delivery` 成功；
  delivery **190.0s**，9 文件 + zip，QC 全绿，两个 master 均 40.000s/带音轨。
- 9:16 960 帧、SRT 5 cues（≤16 字/行、2.31 字/秒）、封面 1920×1080/1080×1920。
- 证据与复现命令见 §3.3；`verify_r2_5_delivery_40s.py` 支持全链与 `--project/--run` 复用 G07。
- 注意：run 223 manifest 有 7 条 run-local 审批（G03 继承），DAG 实际 8 个人工门；PRD「9 条审批」
  与当前 8+8 门口径不一致，未伪造第 9 条（见 §3.3 审批口径）。

### 6.3 G07 与交付包整合决策（已定）

- 决策记录：[ADR-0007](docs/adr/ADR-0007-g07-qc-and-delivery.md)。
- **G07**：DAG 内最终打包门，输出 master，并做核心 QC（时长/分辨率/fps/音轨/LUFS/TP）；
  失败 `E_QC_*` 阻断并给修复建议；不渲染 9:16、不生成 zip。
- **DeliveryService**：显式 post-run 作业（API/页面）；非导入项目必须已有 G07 `succeeded/cached`，
  否则 `E_DELIVERY_GATE`；完整包 QC 失败则 Job 失败；manifest 记录 G07 master sha + 全部文件 sha。
- 代价：改 G07 已升 `EXECUTOR_VERSION=2.6.6`；普通 Run 只多一次 ffprobe/ebur128。

### 6.4 R2.5 DoD（收尾时逐项打勾）

- [x] FR-26 全场景静帧/逐场门禁/diff（DONE）
- [x] FR-27 音频 Take/波形/对齐/许可/Stems/G06（DONE）
- [x] FR-28 16:9+9:16+SRT+封面+QC+zip；5s 26.2s / **40s 190.0s**
- [x] FR-31 模板音频占位/标题预演/只读示例/Studio 引导（DONE）
- [x] 102 tests、E2E、干净 rumor 46/46 回归（run 222，90.6s）
- [x] 交付与 G07 关系有明确记录（ADR-0007；G07 master QC + Delivery 显式作业）
- [x] 未开始 R3/R4

---

## 7. 命令、环境、复现

### 7.1 开发/测试

```bash
./dev.sh
cd server && uv run pytest tests -q
cd .. && uv run --project server python scripts/e2e_ui.py
uv run --project server python scripts/smoke_m1.py
uv run --project server python scripts/verify_r2_5s_incremental.py
uv run --project server python scripts/verify_r2_preview.py
uv run --project server python scripts/verify_r2_profiles.py
uv run --project server python scripts/verify_r2_recovery.py
uv run --project server python scripts/golden_run.py --project 5s
uv run --project server python scripts/verify_r2_5_review.py
uv run --project server python scripts/verify_r2_5_audio.py
uv run --project server python scripts/verify_r2_5_delivery.py
```

### 7.2 常用 API

```bash
curl -s http://127.0.0.1:7860/api/health
curl -s http://127.0.0.1:7860/api/templates
curl -s http://127.0.0.1:7860/api/runs/<id>/render-manifest
curl -s http://127.0.0.1:7860/api/projects/<id>/audio
curl -s http://127.0.0.1:7860/api/projects/<id>/deliveries/<run>
curl -s http://127.0.0.1:7860/api/queue
```

### 7.3 数据/清理

- 真实 DB：`~/.filmflow/filmflow.db`（测试 project/run 很多，属正常）。
- 测试 DB：`/tmp/filmflow-test-home/filmflow.db`（可删，下次 pytest 重建）。
- 8787 是 FrameServer；EADDRINUSE 先查健康检查/残留进程。
- Chrome 残留：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`；启动恢复会清理。
- 预览缓存：`~/.filmflow/cache/preview/<project>`；交付：项目 `out/deliveries/<runId>`。
- 风格库 76MB 外置，不入 git。

---

## 8. 硬约束（不要违反）

- 仅本机 `127.0.0.1`；不上传文件；不调用在线生成模型。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；边数 93。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占；预览不新开第二个浏览器。
- 新项目禁止 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 改执行器行为必须升 `EXECUTOR_VERSION`（2.6.6）。
- 路径白名单/禁止路径穿越；FrameServer 只服务 `/engine` 与 `/project`。
- 76MB 风格库/示例 mp4 不入 git；`vendor/fy-code-animation` 只查方法，不 import。
- R2.5 只做 FR-26/27/28/31；R3/R4 不做。
- UI 自动化用系统 Chrome + 键盘输入（React 19 `fill()` 不触发 onChange）。

---

## 9. 已知限制/风险（交接必须知道）

1. **FR-31 已 DONE，但示例是仓库 fixture**：`fixtures/examples/` 只读源 + 克隆项目；不是可浏览的
   预置数据库项目。模板音轨是占位文件，不会生成假音频。
2. **FR-28 40s 已实测**：delivery 190.0s；比 5s（26.2s）慢主要来自 9:16 的 960 帧重渲。
3. **G07 与交付边界**：G07 做 master + 核心 QC；交付包是显式 post-run 作业，必须等 G07 通过（ADR-0007）。
4. **预览/档位 UI 未接**：API/服务可用；编辑器内预览按钮、档位切换 UI 留 R3。
5. **单 API worker**：Job 恢复/孤儿清理假设单进程；多 worker 不支持。
6. **whisper 缺失**：本机无 whisper CLI/model；G02 manual；R2.5 音频不伪装词级。
7. **golden baseline**：绑定 H2/1080p24/字体/风格库；换库需确认后 `--update`。
8. **40s golden**：run154 G01 因无音频失败，但 A–F/F02 成功；不要用 run 状态判断视觉回归。
9. **交付 9:16**：当前 Scene DSL 重排（非智能裁切/主体检测）；复杂版式可能 `approximate`。
10. **非 riso 新项目**：ink/code-video 仍 Contract 1.0，C01 阻断；R2.0/R2.5 范围外。
11. **测试污染真实 DB**：大量 `it-*`/`r2-*`/`golden-*` project/run；清理先确认引用。
12. **F02 固定 9222**：端口被占会启动失败；排查 `lsof -i :9222`。
13. **UI i18n**：新页面中文优先；不要破坏既有 zh/en 切换。

---

## 10. 接手检查表（第一小时）

- [ ] `./dev.sh`；`/api/health`、`:3000` 正常。
- [ ] `cd server && uv run pytest tests -q` → **102 passed**。
- [ ] `e2e_ui.py` 8 场景；`smoke_m1.py` 46/93。
- [ ] Phase 4/5/6/7/8 verifier 全绿（见 §0.2）。
- [ ] R2.5 review/audio/delivery verifier 全绿。
- [ ] 打开 `/review?project=119&run=163`、`/audio?project=151`、`/delivery?project=142&run=186`。
- [ ] 读 §5、§6、§9；确认下一步是 R2.5 总验收，不重做 R2.0/FR-26/27/28/31。
- [ ] 申报完成必须附：测试输出、产物路径+sha/时长、UI 截图/curl。

---

## 附录 · 参考文档

| 文档 | 说明 |
|---|---|
| `AGENTS.md` | Agent 入口与硬约束 |
| `docs/process/r2_5-plan.md` | R2.5 计划/FR 状态 |
| `docs/process/r2-acceptance.md` | R2.0 验收报告 |
| `docs/prd/PRD-002-production-workbench.md` | v2 30 FR / 两级执行 / 交付矩阵 |
| `docs/adr/ADR-0005-v2-ratification.md` | D1–D7 冻结裁决 |
| `docs/adr/ADR-0006-preview-service.md` | 预览服务设计 |
| `docs/process/r2-plan.md` | R2.0 阶段计划 |
| `fixtures/golden/` | 5s/15s/40s 黄金 fixture/baseline |
| `../filmflow-web-agent-prompt.md` | 规格宪法（仓库外） |

*任何“完成”申报必须附测试输出、真实产物路径（sha/时长）、UI 截图、API curl。没有证据就写“未验证”。*
