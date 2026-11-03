# FilmFlow 交接文档（HANDOFF）

> 更新时间：2026-11-03 · **R2.0/R2.5 已完成；R3.0 创作闭环 v1（FR-32/33/34/35/38）已交付；FR-36/37 下一批**
> 当前代码基线：R3.0 代码 `7a0ee2c`（tag `r3.0-audio`；`r3.0-takes`/`r3.0-creation` 为前序）；R2.5 基线 `b7591bd`。
> **先读本文 §0、§1、§5、§6；再读 `AGENTS.md`、`docs/process/r3_plan.md`、PRD-002、ADR-0005/0007/0008/0009。**
> 上下文压缩后继续开发时：从 §6.5 的 R3 下一批（FR-36 → FR-37）开始，不要回滚 R2/R3 已完成部分。

---

## 0. 下一个 Agent 从这里开始（15 分钟）

### 0.1 工作目录与服务

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
./dev.sh                  # API :7860 + Web :3000
curl -s http://127.0.0.1:7860/api/health
```

Web 入口：`/`（模板/项目）、`/wizard`、`/canvas?project=&run=`、`/editor`、`/timeline`、
`/review`、`/player`、`/takes`、`/audio`、`/delivery`、`/help`。
API 文档：`http://127.0.0.1:7860/api/docs`。

### 0.2 第一小时必做

```bash
cd server && uv run pytest tests -q                       # 123 passed
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
uv run --project server python scripts/verify_r3.py                 # R3 时间轴+审片
uv run --project server python scripts/verify_r3_camera.py          # 相机/文本/转场 final
uv run --project server python scripts/e2e_r3.py                    # R3 时间轴/审片 UI
uv run --project server python scripts/verify_r3_takes.py           # Take 对比/采纳/分支
uv run --project server python scripts/e2e_takes.py                 # Take UI 同步/差异
uv run --project server python scripts/verify_r3_audio_v2.py        # 音频 v2 全链
uv run --project server python scripts/e2e_audio_v2.py              # 音频 v2 UI
```

### 0.3 当前下一步（按优先级）

1. **明早验收**：R2.5 §6.4 全绿；R3.0 v1 §3.5 全绿。证据命令见 §0.2，计划见
   `docs/process/r3_plan.md`。
2. **R3 下一批**（未开始，不要虚报）：FR-36 资产库 → FR-37 模板/系列。
3. R3.0 v1 含 FR-32/33/34/35/38；`/timeline`、`/player`、`/takes`、`/audio` 已可用。
4. **不要开始 R4**（多规格矩阵/平台发布/批量/photo 引擎）。

### 0.4 不要做的事

- 不要重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑；46 节点/93 边不变。
- 不要新增 DAG 节点；R2.5 的审阅/音频/交付都在服务/页面层。
- 不要把新项目回退 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 不要改执行器行为却不升 `EXECUTOR_VERSION`（当前 **2.8.0**）。
- 不要用“页面能点”代替真实产物；完成申报必须附测试、产物路径/哈希、UI 截图/curl。
- 不要跑 `verify_r2_recovery.py` 时同时使用工作台（它会 kill -9 并重启 dev.sh）。

---

## 1. 当前状态

### 1.1 提交与标签

| 项 | 值 |
|---|---|
| R3.0 当前代码 | `7a0ee2c`（tag `r3.0-audio`；当前 HEAD 以 `git log` 为准） |
| R2.5 FR-26 tag | `r2_5-review` → `a37570d` |
| R2.5 FR-27 tag | `r2_5-audio` → `cd7312f` |
| R2.5 FR-28 tag | `r2_5-delivery` → `9c4ac00` |
| R2.5 FR-31 tag | `r2_5-onboarding` → `b7591bd` |
| R3.0 v1 tag | `r3.0-creation` → `7ecf84a` |
| R3.0 FR-38 tag | `r3.0-takes` → `1d2fcf6` |
| R3.0 FR-35 tag | `r3.0-audio` → `7a0ee2c` |
| R2.0 起始 tag | `r2-edge-fix` → `4f9e381` |
| R2.0 Scene DSL | `r2-scene-dsl` → `53e6462` |
| R2.0 增量 | `r2-incremental` → `07b5237` |
| R2.0 预览 | `r2-preview` → `25ff0d9` |
| R2.0 档位 | `r2-profiles` → `426aa20` |
| R2.0 Job/恢复 | `r2-jobs` → `f5d5de1` |
| R2.0 黄金 | `r2-golden` → `371ea4b` |
| 测试 | **123 passed**（unit 104 / integration 12 / BDD 7） |
| EXECUTOR_VERSION | **2.8.0**（R3 音频 v2；processed take/场景拼接/响度目标） |
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

### 3.5 R3.0 创作闭环 v1（FR-32/33/34/35/38）

- **FR-32 时间轴**：`/timeline`；V/T/C/A1/A2/A3/M 轨道；拖块排序、拖右边缘改时长 + ripple；
  分割/合并/复制；文本框自动保存；相机/转场 inspector；250ms 防抖静帧预览；撤销/重做 50；
  读时校验 409 + force；JKL/逐帧/入出点/缩放/吸附。
- **FR-33 审片**：`/player`；F04/master 视频；矩形/箭头/画笔/文字批注锚定 frame+sceneId；
  列表跳帧；resolve/回复/指派；场景与整片决议；JSON/CSV 导出导入；审片包 zip。
- **FR-34 相机/转场**：timeline scene `camera_keyframes`/`camera_anchor` + `text` override；
  E02/PreviewService 同一 camera；renderer 支持 rotate；7 预设；8 类转场 id；E04 接受 id。
- **FR-38 Take 对比**：`/takes`；`card/takes.json` 名称/评分/备注/current/hidden；
  A/B 视频同步（≤1 帧）、difference 差异叠加；场景采纳只改目标场景；promote 写 `out/CURRENT.json`；
  branch 复制 Run 快照 docs 并写 `parent_run_id`；当前 Take 删除 409。
- **FR-35 音频 v2**：`/audio`；每场景多 Take/A-B；`scenePrimary` + G01 adelay/amix 拼接；
  processed WAV（highpass/afftdn/deesser/EQ/silenceremove/loudnorm）、onset/拍点、
  −14/−16/−18 响度目标、Stems 增益；G05/G06/G07 共用 targetLufs。
- **验收（2026-11-02，EXECUTOR_VERSION 2.8.0）**：
  - `verify_r3.py`（project 201 / run 251）：S03 +2s ripple 40→42s/1008 帧；split/merge；
    读时 409 + force；相机 3 帧 motion preview 1.63s；30 文档版本恢复初始；
    10 条批注 export→clear→import；审片包 6.8MB / review.mp4 40.0s。
  - `verify_r3_camera.py`（project 208 / run 261，2.7.2）：D01 文本 override、E03 相机 3 帧、
    E04 4 类转场；同刻 preview vs final **SSIM 0.989483**。
  - `e2e_r3.py`（project 189 / run 238）：拖 S01 +2s、改字、相机预设、撤销、刷新恢复、
    批注跳帧 4.0s→4.000s、播放器新增批注。
  - `verify_r3_takes.py`（project 188，A=237/B=254）：视频 sha 不同；元数据/评分/当前/删除保护；
    branch → Run 255（parent 254）；采纳 S03 只改 S03。
  - `e2e_takes.py`：同步播放 1.324s vs 1.324s；帧步同秒；差异面板；提升 A→B；采纳 B 的 S03。
  - **修复二次 Run 数据源**：B02/B03 现在优先 Run 快照 timeline（2.7.2），否则第二次 Run 会读旧
    `card/task.json`，时间轴/相机修改不进入 final（实测 A/B 视频曾同 sha，修复后不同）。
  - `verify_r3_audio_v2.py`（project 211 / run 266）：G01 场景拼接 5.0s、G05 mix 5.0s、
    G06 **−13.8 LUFS**（target −14）、stems 5/5/5s、processed take、16 onsets。
  - `e2e_audio_v2.py`：A/B/processed/检测拍点/拼接试听/响度预设 −16↔−14。
  - 123 tests；`e2e_ui.py`/`e2e_onboarding.py`/`e2e_r3.py`/`e2e_takes.py`/`e2e_audio_v2.py` 全绿。
  - R2.5 回归（2.8.0）：5s 交付 **24.1s**（project 215/run 270）；干净 rumor **46/46**
    （run 272，256.1s）；5s 黄金 **SSIM 1.0**（project 216/run 271，视觉断言；无音频 G 链失败不影响）。

**磁盘清理说明（2026-11-03）**：R3 验收期间大量 project（如 201/208/189/155）已在磁盘清理中删除，
上面 ID 是证据记录，不是当前可打开的项目。当前保留的演示/证据项目见 §7.4；所有验收脚本可复现。

**R3.0 v1 的诚实边界**：撤销 30 步已用 30 个文档版本恢复验证，但 30 步 UI 连点未自动化；
100 场景服务端 ops <0.2s，浏览器 100 场景 60fps 未实测；FR-38 没有音频波形对齐/帧差图，
只做视频同步 + difference 叠加；FR-35 的 SFX 拖入依赖 FR-36；FR-36/37 未开始。

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
- 相机：`_camera()` 读 timeline `camera_keyframes`/`camera_anchor`；与 E02 共用 compiler。
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

### 4.5b R3.0 服务（创作闭环 v1）

- `server/app/services/timeline_ops.py`：resize/ripple、move、split/merge/duplicate、set_text、
  set_camera、camera_preset、set_transition；normalize/validate；`/projects/:id/timeline/ops` 乐观锁。
- `server/app/services/review_comments.py`：`review/review.json`；评论/回复/resolve/场景+整片决议；
  JSON/CSV 导出、按 id 去重导入、`review-package.zip`（review.mp4 + review.json + README）。
- 页面：`/timeline`（V/T/C/A1/A2/A3/M 轨道、拖拽/ripple、inspector、250ms 静帧预览）、
  `/player`（视频、批注覆盖、跳帧、决议、导出导入、审片包）。
- 数据源：timeline scene `text`/`camera_keyframes`/`camera_anchor`/`transition`；ADR-0008。

### 4.6 缓存/锁（必须理解）

- `EXECUTOR_VERSION=2.8.0`；改执行器必须升。
- `DOC_NODES` 缓存含 `doc_snapshot_sha`；`PROFILE_NODES` 含 `renderProfilesSha`；
  `PROJECT_LOCAL_NODES={D01,D02,E03,E04,E05,F02,F04,G01,G05,G07}` 含 `projectRoot`。
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

1. **EXECUTOR_VERSION**：改任何执行器行为必须升版；当前 2.8.0，否则缓存返回旧行为。
2. **task 快照回退**：B06 同文档缓存命中时不会写 `runs/<id>/docs/task.json`；`_task_path` 必须回退
   只读 `card/task.json`，否则 D01 空场景、D03/D04 失败。
3. **timeline 持久化**：materialize/首次快照落 timeline doc；编辑 script 不得重建 timeline，
   否则改一句导致全场景时长漂移、全量重渲。
4. **reading window**：`last_text_at=end-read_seconds`；B07 校验 `last_text_at+read_seconds≤end`；
   G06 用 `last_text_at+read_seconds` 作为句子对齐目标。
5. **项目本地缓存**：D01/D02/E03/E04/E05/F02/F04/G01/G05/G07 写项目文件，缓存键必须含 projectRoot；
   新增文件产物节点必须加入 `PROJECT_LOCAL_NODES`，否则 program/transitions/master/帧留在旧项目。
   R3 实测踩到 E04 跨项目命中导致新项目缺 `scenes/transitions.json`。
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
15. **相机预览同源**：PreviewService `_camera()` 必须读 timeline `camera_keyframes`；R3 曾因仍用默认
    缓推导致 preview vs final SSIM 0.85，修复后 0.9895。E02 与 PreviewService 都走同一 compiler。
16. **读时门禁范围**：改文本/时长/分割/合并受 `E_SCENE_READ_OVERFLOW` 阻断；相机/转场/排序
    不应被既有读时错误连带阻断（否则用户无法继续结构编辑）。
17. **scene.text**：时间轴 override 优先于 source_span/meaning；script 仍是口播/字幕/对齐事实源，
    改画面文字不要改 script。
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
- 代价：G07 QC 最初升到 2.6.6；当前总版本 2.8.0；普通 Run 只多一次 ffprobe/ebur128。

### 6.4 R2.5 DoD（收尾时逐项打勾）

- [x] FR-26 全场景静帧/逐场门禁/diff（DONE）
- [x] FR-27 音频 Take/波形/对齐/许可/Stems/G06（DONE）
- [x] FR-28 16:9+9:16+SRT+封面+QC+zip；R2.5 5s 26.2s / 40s 190.0s（2.8.0 5s 24.1s）
- [x] FR-31 模板音频占位/标题预演/只读示例/Studio 引导（DONE）
- [x] 102 tests、E2E、干净 rumor 46/46 回归（run 222，90.6s）
- [x] 交付与 G07 关系有明确记录（ADR-0007；G07 master QC + Delivery 显式作业）
- [x] R2.5 DoD 全绿；R3.0 v1 已开始且未回退 R2

### 6.5 R3.0 下一批（未开始）

1. **FR-36 资产库**：全局/项目作用域、sha 去重、引用计数、image/audio 图层、替换重链。
2. **FR-37 模板/系列**：项目另存模板、场景模板、变量替换、批量 CSV；依赖 R4 FR-46。
3. FR-35 的 SFX 拖入与资产库一起做；不要提前做 R4。

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

- 真实 DB：`~/.filmflow/filmflow.db`。2026-11-03 已清理为 12 个真实项目；重跑验收脚本会新建项目，
  完成后需按 §7.4 清理。
- 测试 DB：`/tmp/filmflow-test-home/filmflow.db`（可删，下次 pytest 重建）。
- 8787 是 FrameServer；EADDRINUSE 先查健康检查/残留进程。
- Chrome 残留：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`；启动恢复会清理。
- 预览缓存：`~/.filmflow/cache/preview/<project>`；交付：项目 `out/deliveries/<runId>`。
### 7.4 项目/磁盘清单（2026-11-03 清理后）

保留的 11 个 `filmflow-projects` 目录：
`r2_5-audio-160`、`r2_5-delivery-216`、`r2_5-delivery-224`、`r2_5-delivery40-185`、
`r3-audio-v2-221`、`r3-camera-199`、`r3-demo-20261103-1`、`golden-5s-217`、`golden-5s-225`、
`rumor-clean-20261102`、`trace-x`；另有仓库外参考项目 `rumor-39s`。
DB 共 12 个项目记录（含 rumor-39s）。重跑验收后按同一策略清理；不要直接 `rm -rf` 正在用的项目。

- 风格库 76MB 外置，不入 git。
- **磁盘现状（2026-11-03）**：`filmflow-projects` 约 1.0GB（11 个目录）、`~/.filmflow` 94MB、
  `ai-v` 总计约 2.7GB；验收项目保留 174/188/202/211/215/216 等，见 §7.4。
- **不要再让验收脚本无限建项目**：每次 40s 项目约 4.3GB（frames 2.7G + proxy 1.4G）；通过后
  删除 `out/frames`、`out/proxy`，只留 film/artifacts/stills/交付包。DB 备份在
  `~/.filmflow/backups/filmflow-before-orphan-cleanup-20261103-125802.db`（确认后可删）。

---

## 8. 硬约束（不要违反）

- 仅本机 `127.0.0.1`；不上传文件；不调用在线生成模型。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；边数 93。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占；预览不新开第二个浏览器。
- 新项目禁止 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 改执行器行为必须升 `EXECUTOR_VERSION`（2.8.0）。
- 路径白名单/禁止路径穿越；FrameServer 只服务 `/engine` 与 `/project`。
- 76MB 风格库/示例 mp4 不入 git；`vendor/fy-code-animation` 只查方法，不 import。
- R3.0 v1 只做 FR-32/33/34/35/38；FR-36/37 下一批；R4 不提前做。
- UI 自动化用系统 Chrome + 键盘输入（React 19 `fill()` 不触发 onChange）。

---

## 9. 已知限制/风险（交接必须知道）

1. **FR-31 已 DONE，但示例是仓库 fixture**：`fixtures/examples/` 只读源 + 克隆项目；不是可浏览的
   预置数据库项目。模板音轨是占位文件，不会生成假音频。
2. **FR-28 40s 已实测**：delivery 190.0s；比 5s（26.2s）慢主要来自 9:16 的 960 帧重渲。
3. **G07 与交付边界**：G07 做 master + 核心 QC；交付包是显式 post-run 作业，必须等 G07 通过（ADR-0007）。
4. **档位 UI 未接**：API/服务可用；时间轴/审片已用预览，编辑器内档位切换 UI 仍留后续。
5. **单 API worker**：Job 恢复/孤儿清理假设单进程；多 worker 不支持。
6. **whisper 缺失**：本机无 whisper CLI/model；G02 manual；R2.5 音频不伪装词级。
7. **golden baseline**：绑定 H2/1080p24/字体/风格库；换库需确认后 `--update`。
8. **40s golden**：run154 G01 因无音频失败，但 A–F/F02 成功；不要用 run 状态判断视觉回归。
9. **交付 9:16**：当前 Scene DSL 重排（非智能裁切/主体检测）；复杂版式可能 `approximate`。
10. **非 riso 新项目**：ink/code-video 仍 Contract 1.0，C01 阻断；R2.0/R2.5 范围外。
11. **测试污染真实 DB**：大量 `it-*`/`r2-*`/`golden-*` project/run；清理先确认引用。
12. **F02 固定 9222**：端口被占会启动失败；排查 `lsof -i :9222`。
13. **UI i18n**：新页面中文优先；不要破坏既有 zh/en 切换。
14. **R3 v1 未含**：FR-36/37；不要把这两项写成已完成。FR-35 已做，但 SFX 拖入等 FR-36。
15. **时间轴撤销**：UI 历史 50 步；30 步只验证了文档版本恢复；长链 UI 连点未自动化。
16. **时间轴性能**：100 场景 ops 服务端 <0.2s；浏览器 60fps 未实测。
17. **审片批注**：项目级 review.json（不按 Run 分桶）；Take 对比已做，但无音频波形对齐与帧差图。
18. **R3 版本**：EXECUTOR_VERSION 2.8.0；D01/E03/E04 已加入 project-local 缓存；
    新项目二次 Run 的 B02/B03 必须读 Run 快照 timeline，不能读旧 card/task.json。
19. **A03 扫描**：风格库扫描已改 `asyncio.to_thread`，但版本升级/首次索引仍可能耗时数分钟；
    不要把同步扫描塞回事件循环。
20. **音频 v2 边界**：拍点是数值/检测列表，没有波形拖拽；SFX 未做；G07/Delivery 的 LUFS 范围
    现在读 `card/audio.mix.json` 的 targetLufs（−14/16/18 ±1），别再写死 −16。

---

## 10. 接手检查表（第一小时）

- [ ] `./dev.sh`；`/api/health`、`:3000` 正常。
- [ ] `cd server && uv run pytest tests -q` → **123 passed**。
- [ ] `e2e_ui.py` 8 场景；`smoke_m1.py` 46/93。
- [ ] Phase 4/5/6/7/8 verifier 全绿（见 §0.2）。
- [ ] R2.5 review/audio/delivery verifier 全绿。
- [ ] `verify_r3.py`、`verify_r3_camera.py`、`e2e_r3.py` 全绿。
- [ ] 打开 `/timeline?project=202&run=252`、`/player?project=174&run=223`、`/takes?project=188`、`/audio?project=211`。
- [ ] 读 §5、§6、§9；确认下一步是 R3 下一批 FR-36→FR-37，不重做已完成 FR。
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
