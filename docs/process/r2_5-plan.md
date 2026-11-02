# R2.5 能审能交（FR-26/27/28/31）

> 依据：PRD-002 §7.2/§8.6/§15.3；ADR-0005 D5/D7。R2.0 DoD 已通过，老板授权继续。

## 状态

| FR | 状态 | 证据 |
|---|---|---|
| FR-26 全场景静帧审阅 | **DONE**（tag `r2_5-review`） | D01 长场景 6 帧；D02 contact sheet/stills_manifest；D03 逐场门禁；D04 review_diff；`/review` 页；`verify_r2_5_review.py` |
| FR-27 音频工作台 v1 | **DONE**（tag `r2_5-audio`） | Take/录音、waveform 51ms、手动对齐、许可、sidechain、Stems、G06 TP/同步 |
| FR-28 交付 v1 | **DONE**（tag `r2_5-delivery`） | 16:9+9:16、SRT、双封面、manifest/qc/rights/zip；5s 26.2s、40s 190.0s；G07 master QC + Delivery gate（ADR-0007） |
| FR-31 新手引导 | **DONE** | 3 模板 + 音频占位、示例只读/克隆、向导用户标题 3 候选、Studio 5 步引导、`/help`；`verify_r2_5_onboarding.py` + `e2e_onboarding.py` |

## FR-26 已落地

- `_still_times`：>=8s 场景 6 帧关键静帧，短场景 1 帧。
- D02：review/draft 全套 + `stills_manifest.json`（scene→times）+ 16 宫格 contact sheet。
- D03/D05：逐场查看门禁（新项目 5 场必须全看）；D05 pending 返回 stills/contactSheet/diff。
- D04：`review_diff.json` 与上一 Run 按场景 sha 集合比较，只标变化场景。
- `/review`：网格/contact sheet/100%/200%/A-B/键盘/批准 D03/D05。
- 验收：D03 未看全拒绝；5 场 contact sheet；S01/S04/S05 各 6 张；改 S03 diff 只标 S03。

## FR-31 已落地

- 模板 materialize 写 `card/audio.placeholder.json`（kind/duration/source），`GET /projects/:id/audio`
  返回占位；首次上传/录音后占位自动移除（不生成假音频）。
- `GET /wizard/titles?copy=` 本地切 3 个候选标题（无在线模型）；向导第 3 步用所选风格图叠加
  用户标题预演，候选可切换；`brief.title` 写进 materialize。
- `fixtures/examples/catalog.json` 两个只读示例；`GET /examples` + `POST /examples/:id/clone`
  复制出独立项目根，路径全部在工作区内。
- Studio 首次进入显示 5 步引导（场景列表/单帧/改一句/diff/draft），可跳过、header「引导」重看、
  localStorage 记忆；不阻塞画布。
- 验收：15s 模板 → draft 预览 960×540/12/15.0s，墙钟 38.2s；UI 冒烟覆盖首页 3 模板/2 示例、
  引导显隐与记忆、标题预演切换。

## 后续顺序

1. R2.5 总验收（§6.4 全部已通过）：102 tests、UI E2E、5s/40s 交付、G07 QC 负向单测、干净 rumor 46/46。
2. 签收后再进入 R3；不提前做时间轴/审片/音频 v2/资产库/批量。

## 验收快照（2026-11-02，EXECUTOR_VERSION 2.6.6）

- `pytest tests -q`：**102 passed**（unit 83 / integration 12 / BDD 7）。
- `e2e_ui.py`：8 场景全绿（17s）；`e2e_onboarding.py`：4 组全绿。
- FR-31：15s 模板 draft 960×540/12/15.0s，38.2s；占位清除、示例克隆、标题切换均验证。
- FR-28 5s：delivery 26.2s；40s：delivery 190.0s，9 文件/QC 全绿，master 40.000s 双版本。
- 干净 rumor：run 222 **46/46**、90.6s、master 39.5s。
- 未开始 R3/R4。
