# ADR-0010 资产库与场景图片/字体/SFX

- 日期：2026-11-03
- 状态：已采纳（R3.0 FR-36 v1）
- 关联：FR-36、FR-25、FR-32、FR-35、FR-34；PRD-002 §6.3/§7.3/§10

## 背景

FR-36 要求图片/音频/字体/视频有地方放、能复用、可追溯、可替换；时间轴能插入图片与 SFX；
缺失资产在渲染前阻断；字体缺字在编辑器预警。现有 Scene DSL 只声明了 `image` 图层类型但渲染器
只画占位叉号，也没有资产表/存储/引用扫描。

## 决策

1. **资产表 `asset`**（SQLModel）字段按 PRD：`scope`（global/project）、`project_id`、`kind`
   （image/audio/font/video）、`path`、`sha256`、`bytes`、`meta_json`、`tags_json`、`license_json`、
   `archived`。同一作用域内 sha 唯一；项目导入与全局同 sha 时直接复用全局记录，不复制文件。
2. **存储**：
   - 全局：`~/.filmflow/assets/<sha[:2]>/<sha><ext>`；
   - 项目：`<project>/.filmflow/assets/<sha[:2]>/<sha><ext>`；
   - 缩略图与源文件同目录（`<sha>.thumb.jpg`），数据库 meta 记录相对路径。
   - 源文件只按 sha 命名，原始文件名只进元数据，避免路径穿越与重名覆盖。
3. **引用事实源是 timeline 文档，不建引用表**：扫描 `scene.layers[].assetSha`、
   `scene.fontSha`、`scene.audio_layers[].assetSha` 得到使用处；列表实时算
   `refCount`，删除被引用资产返回 409 `E_ASSET_IN_USE` 并列出场景/图层。
4. **Scene DSL 扩展**：
   - `scene.layers[]`：v1 只支持 `image`，字段 `assetSha/box/z/fit/opacity/name`；
   - `scene.fontSha`：可选字体资产 sha；编译时字体 family 来自字体元数据；
   - `scene.audio_layers[]`：SFX，字段 `assetSha/at/gainDb/fadeIn/fadeOut/name`（`at` 相对场景起点）。
   - 编译器把 sha 解析为可加载 URL；解析不到直接抛 `E_ASSET_MISSING`，节点/预览失败并给
     “重新链接”提示，不静默画占位。
5. **渲染 URL 双通道**：
   - 最终 D01/E03/F02 走 FrameServer：项目资产 `/project/.filmflow/assets/...`，全局资产
     `/global-assets/...`；FrameServer 只白名单这两个前缀。
   - 预览/9:16 交付由 `PreviewRenderer` 从 `file://` 加载，资产内联为 data URL，避免
     file:// 下 `/project/...` 解析错误与 canvas 跨源污染。
   - renderer 预加载图片与 `@font-face`（FontFace API），再同步绘制；新增 `preloadProgram(s)`。
6. **替换**：`POST /assets/:id/replace` 只重写 timeline 文档里的旧 sha（图片/字体/SFX），返回
   `affectedScenes`；未变化的场景 program 哈希不变，下一次 Run 只重渲相关场景。
7. **SFX**：G05 读取 Run 快照 timeline 的 `audio_layers`，解析资产路径，按绝对时间
   adelay/volume/fade 混成 `card/stems/sfx.wav`，再与 voice/music 混音；stems manifest 记录
   `sfxCount`。`G01/G05/G06/G07` 缓存键显式纳入 `card/audio.json`、`card/audio.mix.json` 与
   timeline 快照 sha，避免改设置仍命中旧产物。
8. **字体**：字体资产必须填许可来源/类型；`fontTools` 读 family/weight/cmap，提供
   `/assets/:id/font-check`；时间轴在选中字体时 400ms 防抖自动检查，缺字红色列出；不用等 C03。
9. **视频**：只作为素材入库/预览/许可，不进入 NLE 图层（避免把 46 节点推成剪辑器）。

## 后果

- 正面：资产可复用、引用可追溯、替换不复制；图片/字体/SFX 真正进入 final；缺资产不再静默；
  缓存键修正后改音频设置会正确重跑 G05。
- 代价：预览把资产内联 data URL，大图/字体会让 payload 变大；v1 不支持视频图层、智能裁切、
  字体子集重嵌（自定义字体走 FontFace 全量加载）；全局资产被替换时扫描所有项目 timeline。
- 边界：资产是本地文件，不上传云；项目删除时资产目录需随项目清理（暂无自动 GC）。

## 验证

- `scripts/verify_r3_assets.py`：50 图（2 内容）新增 2/去重 48；引用计数；删除 409；
  替换只返回 S01；缺资产预览 409；字体缺 2 字；全局复用；清理恢复。
- `scripts/e2e_assets.py`：UI 上传图片/SFX、字体缺字标红、时间轴插入、引用计数、删除阻断。
- project 211 / run 275（EXECUTOR_VERSION 2.9.1）：图片进入 D01/E03/F02 静帧与 final；
  G05 `sfxCount=1`，SFX stem 5.0s 且非静音；G06/G07 通过。
- 5s 黄金（project 223 / run 282）6 帧 SSIM 1.0，未因 renderer 扩展改变无资产项目视觉。
