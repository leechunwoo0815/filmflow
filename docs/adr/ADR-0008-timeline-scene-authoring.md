# ADR-0008：时间轴场景文本 / 相机作为渲染事实源

- 状态：Accepted
- 日期：2026-11-02
- 关联：PRD-002 FR-32/34；ADR-0005

## 背景

R2 的 `timeline.doc` 场景只有 `source_span`，文本来自 script；相机由 E02 固定生成 1.0→1.03
缓推。R3 时间轴/相机编辑器需要在不重建整份 script、不新增 DAG 节点的前提下修改单场文本和
相机关键帧，并让预览、D01/E03、F02/final 使用同一份数据。

## 决策

1. **scene.text override**：timeline scene 可带 `text`；`compile_scene().scene_text()` 优先使用
   `text`，其次 `source_span`，最后 `meaning`。时间轴改字只改 timeline doc，不重建 script。
2. **camera_keyframes**：timeline scene 存 `camera_keyframes`/`camera_anchor`；E02 直接透传，
   compiler 归一化 `t/zoom/x/y/rotate`；PreviewService 的 `_camera()` 使用同一字段。
   renderer `cameraAt` 增加 `rotate`（默认 0，旧项目视觉不变）。
3. **转场 id**：timeline scene 的 `transition` 使用 8 类 id；E04 同时接受 id 与既有中文别名。
4. **时间轴操作服务端化**：`timeline_ops.py` 纯函数 + `/projects/:id/timeline/ops`，沿用 docs
   乐观锁；读时不足返回 409 `E_SCENE_READ_OVERFLOW`，UI 二次确认后 force。
5. **缓存**：D01/E03/E04 写项目文件，加入 `PROJECT_LOCAL_NODES`；执行器版本升 2.7.1。

## 后果

- 改一场文本只影响该场 program/hash；改时长 ripple 会改变后续场景时间与 hash（预期）。
- 相机预览与 final 同源；R3 验收实测同刻 SSIM 0.989483（draft 预览 vs final）。
- script 仍是口播/字幕/对齐的事实源；时间轴 override 只影响画面文字，不改 script 文本。
- 导入项目没有 `text`/`camera_keyframes` 时行为与 R2 完全一致。
