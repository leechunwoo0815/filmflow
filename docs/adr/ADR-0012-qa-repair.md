# ADR-0012 QA 修复建议与可撤销安全动作

- 日期：2026-11-03
- 状态：已采纳（R3.5 FR-39 v1）
- 关联：FR-39、FR-30、FR-32、FR-35、FR-25

## 背景

现有 QA 失败只给节点 `message`：读时溢出、字体缺字、黑/缺帧、运动/静态、LUFS/TP、同步、
许可、引擎/资产错误没有统一的分类、定位、建议和可撤销修复。FR-39 要求把失败变成
“原因 + 位置 + 1–3 个动作 + 影响范围”，安全动作可一键执行，危险动作只给建议。

## 决策

1. **分析层 `services/qa.py`**：不新增 DAG 节点；读取 ProjectDoc timeline/script、NodeRun 失败消息、
   E06 `motion_metrics.json`、资产表与音频许可，生成稳定 issue：
   `id=category:scene|node`，含 `title/reason/location/suggestions/impact/fixable`。
   分类覆盖 PRD 的 11 类 + `missing_asset`/`qa_generic`。
2. **位置/影响**：校验错误带 sceneId；节点消息带 nodeId；E06 帧号映射到场景；影响给
   `scenes/nodes/gates/seconds`（粗粒度估算，不承诺精确耗时）。
3. **安全动作**（`kind=auto`）：
   - `extend_scene`：+0.5s，force 允许短期读时溢出，下一次读时校验兜底；
   - `scale_text`：场景 `text_scale` −10%（0.7–1.3），compiler 只缩 title size；
   - `wrap_text`：在标点附近插入换行，不改文案字素；
   - `set_lufs`：写 `card/audio.mix.json` target（−16 / TP 用 −18），下一次 G05–G07 生效；
   - `fill_license`：显式提交来源/类型/authorized 后写许可；
   - `retry_run`：重置 failed NodeRun 并调用 RunEngine 重跑（黑/缺帧）。
   危险动作（改文案/删场景/换风格/重新对齐）仅 manual href，不自动执行。
4. **撤销**：`card/qa_fixes.json` 记录 before/after/afterVersion/verified；timeline 修复可用
   `POST /qa/undo` 恢复 before 内容；若 afterVersion 后时间轴又变化则拒绝自动撤销。
   mix/license 也保存 before。`verified` 为即时重分析结果；需要下一次成功 Run 的标记为 null。
5. **报告**：`/qa/report` 统计 attempts/applied/active/verified/unverified/undone/successRate/
   verificationRate/byAction；**falsePositive 需下一次成功 Run 复核**，不伪造为 0。
6. **UI** `/qa`：问题卡、位置/影响、自动按钮、manual 跳转、修复记录与撤销。
7. **执行器版本**：text_scale 改变编译结果，`EXECUTOR_VERSION` 从 2.9.1 → **2.9.2**；
   preview renderer `preview-1.7.0`。46 节点/边/content_hash 语义不变。

## 后果

- 正面：QA 失败可解释、可定位、可安全修复/撤销；扩场景与字号修复立即验证；
  许可/LUFS 修复落到项目文件；报告可追踪修复质量。
- 代价：impact 时间为粗估；视觉溢出没有独立检测，字号动作主要服务排版建议；
  修复日志保存 before 快照；retry_run 仍受 RunEngine/锁/门约束；误报率需成功 Run 复核。
- 边界：不自动改文案/删场景/换风格/重做对齐；不绕过门；导入项目只读；R4 未开始。

## 验证

- `test_qa.py`：text_overflow→extend→verified→undo、license 修复、分类映射。
- `verify_r3_qa.py`：project 227 text_overflow 修复/撤销、许可修复/撤销、缺资产定位、报告；
  attempts=8、undone=8、successRate=1.0。
- `e2e_qa.py`：`/qa` 问题卡、扩场景按钮、即时验证、UI 撤销。
- 137 tests（QA 后）；黄金 5s 与 R3 既有证据保持；`EXECUTOR_VERSION=2.9.2`。
