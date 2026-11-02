# ADR-0007：G07 master QC 与交付包的职责边界

- 状态：Accepted
- 日期：2026-11-02
- 关联：PRD-002 FR-28；ADR-0005 D5/D7

## 背景

FR-28 要求「QC 任一失败 → G07 阻断并给修复建议」，但交付包里的 9:16 变体、SRT、双封面和 zip
只能在 master 之后生成。把整套交付塞进 G07 会让每次 Run 都多渲一遍 9:16、拉长 DAG 并挤占
F06/G07 的 600s 超时，也会让普通 Run 意外产出交付包。

## 决策

1. **G07 仍是 DAG 内的最终打包门**，但增加 master 核心 QC：
   - 时长、分辨率、fps 与项目 final profile 一致；
   - 必须有音轨；
   - LUFS 在 −18..−14、真峰 ≤ −1.0 dBTP；
   - 失败以 `E_QC_DURATION/RESOLUTION/FPS/AUDIO/LUFS/TRUE_PEAK` 阻断，并带修复建议。
   - G07 不渲染 9:16、不生成 zip。
2. **DeliveryService 是显式 post-run 执行体**（API `/projects/:id/delivery` + `/delivery` 页）：
   - 非导入项目必须已有 G07 `succeeded/cached`，否则 `E_DELIVERY_GATE`；
   - 自己执行完整包 QC（两个 master、时长、音轨、LUFS/TP、字幕、封面），失败则 Job 失败；
   - manifest 记录 runId、审批、G07 master sha 与全部交付文件 sha，能反查 master 来源。
3. **9:16 是 Scene DSL 重排**，不做智能裁切；导入项目保持 legacy 路径，G07 跳过严格 master QC。

## 后果

- 普通 Run 只多做一次 ffprobe/ebur128，不增加渲染量；交付页仍是用户显式动作。
- LUFS 不达标会在 G07 就失败，不必等到交付包；交付包 QC 仍独立兜底。
- 改 G07 行为已升 `EXECUTOR_VERSION` 2.6.5（缓存必须失效）。
- 交付耗时与是否交付解耦；40s 的 9:16 渲染只发生在点击交付后。
