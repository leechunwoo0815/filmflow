# R2.5 能审能交（FR-26/27/28/31）

> 依据：PRD-002 §7.2/§8.6/§15.3；ADR-0005 D5/D7。R2.0 DoD 已通过，老板授权继续。

## 状态

| FR | 状态 | 证据 |
|---|---|---|
| FR-26 全场景静帧审阅 | **DONE**（tag `r2_5-review`） | D01 长场景 6 帧；D02 contact sheet/stills_manifest；D03 逐场门禁；D04 review_diff；`/review` 页；`verify_r2_5_review.py` |
| FR-27 音频工作台 v1 | **DONE**（tag `r2_5-audio`） | Take/录音、waveform 51ms、手动对齐、许可、sidechain、Stems、G06 TP/同步 |
| FR-28 交付 v1 | **DONE**（tag `r2_5-delivery`） | 16:9+9:16、SRT、双封面、manifest/qc/rights/zip；5s 26.1s |
| FR-31 新手引导 | **PARTIAL** | 3 模板/首页引导/帮助；音频占位/wizard 标题预演/只读示例待补 |

## FR-26 已落地

- `_still_times`：>=8s 场景 6 帧关键静帧，短场景 1 帧。
- D02：review/draft 全套 + `stills_manifest.json`（scene→times）+ 16 宫格 contact sheet。
- D03/D05：逐场查看门禁（新项目 5 场必须全看）；D05 pending 返回 stills/contactSheet/diff。
- D04：`review_diff.json` 与上一 Run 按场景 sha 集合比较，只标变化场景。
- `/review`：网格/contact sheet/100%/200%/A-B/键盘/批准 D03/D05。
- 验收：D03 未看全拒绝；5 场 contact sheet；S01/S04/S05 各 6 张；改 S03 diff 只标 S03。

## 后续顺序

1. FR-31 收尾：模板音频占位、wizard 用户标题预演、示例只读副本。
2. 40s 交付实测与 R2.5 总验收。
3. FR-31 模板/引导。
