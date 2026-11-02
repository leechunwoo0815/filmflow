# ADR-0006 · PreviewService：同一 Chrome 附加、全分辨率降采样与预览缓存

- 状态：**已接受**（R2.0 Phase 5，2026-11-02）
- 背景：FR-23 要求编辑时单帧 p50 ≤2s / p95 ≤6s、5s 片段 ≤20s、缓存 ≤300ms；F02 是唯一权威出片节点，
  运行期间持有 `chrome-queue` 与 `port-8787`。若预览另起浏览器，违反“Chrome 全局串行 1 个”；
  若预览写 `out/frames` 或登记 Artifact，会让 F06/交付链误判。
- 决定：
  1. **F02 运行中**：F02 Chrome 暴露 `--remote-debugging-port=9222`（仅 127.0.0.1）；
     PreviewService 用 Playwright `connect_over_cdp` 在同一 Chrome 新建临时 page，渲染完只关 page；
     attached 模式禁止 `browser.close()`，`playwright.stop()` 只断开驱动，不杀 F02 Chrome。
  2. **F02 空闲**：预览按 `chrome-queue` 获取锁后启动临时 Chrome，渲染完关闭；不常驻第二个浏览器。
  3. **数据内联**：预览 page 打开本地 `film_spec.html?mode=preview`，通过 `evaluate` 注入
     programs/transitions/fontCss；不依赖 8787 根目录，避免跨 Run 切换。
  4. **质量与速度**：单帧 native（1920×1080）渲染 → Lanczos 降到 960×540 → `PREVIEW` 水印；
     片段/整片 native 渲染 → JPEG q0.98 传输 → Lanczos 降采样 → 水印。直接 960p 渲染会改变
     RISO 半调网点相位（SSIM 仅 ~0.80），不可接受。
  5. **缓存**：`~/.filmflow/cache/preview/<project>/<hash>/<key>.png`；key 含 scene/film hash、
     时间、profile、尺寸、水印、`RENDERER_VER`；项目 LRU 500MB。片段 mp4 写项目 `out/preview/`。
  6. **优先级/取消**：still 250ms 防抖 + `(project,scene)` generation；新请求使旧请求返回
     429 `E_PREVIEW_BUSY {superseded:true}`；job 每帧检查交互计数，still 优先；取消只在帧边界。
  7. **审计边界**：预览不写 `out/frames`、不登记 Artifact、不产生 Approval；job 创建写 AuditLog。
- 后果：
  - 实测 F02 运行中 attached p50 1.25s / p95 1.31s；5s 片段 12.7s；缓存 5ms；单帧归一化 SSIM 0.9987。
  - 片段 mp4（draft crf28）抽帧与 final 归一化 SSIM≈0.974，属编码损失；单帧 PNG 0.9987。
  - F02 每个渲染区间启动一次 Chrome，区间之间 9222 短暂不可用；预览最多等 3s 后返回 `E_PREVIEW_BUSY`。
  - 预览 UI 接线留 R3 编辑器；当前 API/服务已完整可用。
- 参考：`HANDOFF.md` §2.4/§5/§6.1；`docs/prd/PRD-002-production-workbench.md` FR-23/§8.3；
  `scripts/verify_r2_preview.py`。
