# ADR-0009：音频 v2 的 Take/处理/响度数据模型

- 状态：Accepted
- 日期：2026-11-03
- 关联：PRD-002 FR-35；FR-27/FR-36

## 背景

R2.5 音频只有一条全局 voice 主 Take、固定 −16 LUFS、处理不可追溯；FR-35 需要每场景多 Take、
A/B、拼接、降噪/EQ、拍点和响度预设，同时保持 G01/G05/G06/G07 的可复现与缓存语义。

## 决策

1. **Take 元数据留在 `card/audio.json`**：`takes[]` + `scenePrimary{sceneId: takeId}`；
   全局 `primary` 仍存在，场景映射优先，未映射时回退全局主 Take。
2. **processed WAV 不改原文件**：`card/audio/<takeId>.processed.wav` + `processedFile`/`processedSha`/
   `processing`；G01 优先 processedFile。原始 Take 可用于 A/B 回退。
3. **场景拼接在 G01**：有 scenePrimary 时按 `scene.start` 用 `adelay`+`amix` 生成整条 voice.wav；
   空场留静音，时长按 profile；没有映射时保持原有单 Take 转码路径。
4. **响度单一事实源**：`card/audio.mix.json` 的 `targetLufs`（−14/−16/−18）驱动 G05 loudnorm、
   G06 校验、G07 master QC 和 Delivery QC；Stems 增益也在同一文件。
5. **拍点本地算**：5ms 能量 flux + 阈值/间隔，不引在线模型；markers/onsets 存
   `card/markers.json`。SFX 拖入等 FR-36 资产库。

## 后果

- 改 processing 或 scenePrimary 只影响 G01/G05 缓存键（执行器版本 2.8.0）。
- −14 预设时 G07/G06 用目标±1，不再写死 −18..−14；−20 仍会阻断。
- 音频 Take 与视频场景解耦：用户可以同一句录多次，只把选中版本拼进最终 voice。
- 仍未做词级对齐/onset 拖拽可视化/SFX 资产库；这些留给后续。
