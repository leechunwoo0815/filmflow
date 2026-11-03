# R3.0 创作闭环 v1（FR-32/33/34/35/36/37/38）+ R3.5 FR-39

> 代码：R3.0 v1 前序 `7a0ee2c` / tag `r3.0-audio`；FR-36 `r3.0-assets`；FR-37 `f887424` /
> tag `r3.0-templates`；FR-39 `3bb81a0` / tag `r3.5-qa`；**专家审查 P0 修复后 `EXECUTOR_VERSION=2.9.3`、preview `1.8.0`**。

> 依据：PRD-002 §7.3；R2.5 已收口（tag `r2_5-onboarding`）。R3.0 v1 已于 2026-11-03 验收。
> 本文覆盖 FR-32/33/34/35/36/37/38 与 R3.5 FR-39；FR-40/41 与 R4 未开始，不虚报。

## 本轮范围

| FR | 交付 |
|---|---|
| FR-32 时间轴编辑器 | `/timeline`：V/T/C/A1/A2/A3/M 轨道、拖拽/改时长/ripple、分割/合并/复制、吸附、播放头/JKL/缩放、场景文本编辑、250ms 静帧预览、自动保存、撤销 50、读时校验 |
| FR-33 审片播放器 | `/player`：F04/review/master 视频、逐帧/JKL/循环/全屏/安全区、矩形/箭头/画笔/文字批注、帧+场景锚点、回复/resolve、场景决议、review.json/CSV 导出导入、审片包 zip |
| FR-34 镜头语言 v1 | 时间轴相机 inspector：keyframes（t/zoom/x/y/rotate）、7 预设、曲线缩略图；转场 8 类+时长；program 更新走同一编译器 |
| FR-38 Take 对比 | `/takes`：Run 列表/评分/当前、A/B 视频同步、差异叠加、场景采纳、promote/branch/软删除保护；`card/takes.json` |
| FR-35 音频 v2 | `/audio`：多 Take/场景 Take 拼接、processed WAV（高通/降噪/齿音/EQ/静音裁剪/响度归一）、A/B 试听、onset/拍点、−14/−16/−18 响度预设、Stems 增益；`card/audio.mix.json`/`markers.json` |
| FR-36 资产库 | `/assets`：全局/项目作用域、sha 去重、引用计数与使用处、许可/标签、图片/音频/字体/视频元数据与缩略图/波形、替换/删除保护、字体缺字；`scene.layers` 图片、`scene.fontSha`、`scene.audio_layers` SFX；G05 真实 SFX stem |
| FR-37 模板/系列 | `/templates`：项目另存模板、场景模板（标题/论点/证据/结论/行动 + 自定义）、`{{title}}/{{number}}/{{accent}}` 变量、≤5 项小系列、模板锁/版本/diff/显式升级；模板源资产复制到新项目 |
| FR-39 QA 修复建议 | `/qa`：失败分类/定位/影响、扩场景/字号/换行/LUFS/许可一键修复、即时验证、撤销、修复报告；manual 动作不自动执行 |

## 关键技术决策

1. **场景文本 override**：timeline scene 增加 `text` 字段；`compile_scene` 优先用它，其次 `source_span`，
   最后 `meaning`。时间轴改字无需重建 script 文档，C03 字集仍从整份 timeline JSON 取字。
2. **相机 keyframes**：timeline scene 存 `camera_keyframes`/`camera_anchor`；E02 直接透传，
   compiler 归一化；renderer 增加 rotate（默认 0，视觉回归不变）。
3. **时间轴操作在服务端**：`timeline_ops.py` 纯函数 + `/projects/:id/timeline/ops`，乐观锁
   沿用 docs `base_version`；所有变更即时落 ProjectDoc，刷新可恢复。
4. **预览**：时间轴用 PreviewService 单帧（draft），250ms 防抖；整片预览仍走 preview/film，
   不写 out/frames、不产生审批。
5. **审片批注本地文件**：`review/review.json`（评论/回复/场景决议/整片决议）；导出 JSON/CSV，
   审片包 = review 视频 + review.json + README，不引入云/账号。
6. **Take 元数据本地文件**：`card/takes.json`（名称/评分/备注/current/hidden）+ `out/CURRENT.json`；
   分支复制 Run 快照 script/timeline/profile 并新建 `parent_run_id`；采纳只替换目标场景文本/相机。
7. **二次 Run 数据源**：新项目 B02/B03 优先 Run 快照 timeline，修复第二次 Run 读旧
   `card/task.json` 导致时间轴修改不进入 final（2.7.2）。
8. **音频 v2**：`card/audio.json.scenePrimary` 映射场景 Take；G01 有映射时按 scene start
   adelay+amix 拼成整条 voice.wav；processedFile 优先；`card/audio.mix.json` 的 targetLufs
   同时驱动 G05 loudnorm、G06 和 G07 QC；onset 用 5ms 能量 flux 本地检测，不引外部模型。
9. **资产表与存储**：`asset` 表（scope/project_id/kind/path/sha256/bytes/meta/tags/license）；
   全局 `~/.filmflow/assets/<sha2>/<sha><ext>`，项目 `<root>/.filmflow/assets/...`；
   同作用域 sha 去重；项目引用全局同 sha 直接复用全局记录，不复制。
10. **使用处扫描 timeline**：不建引用表；扫描 `scene.layers[].assetSha`、`scene.fontSha`、
    `scene.audio_layers[].assetSha`；删除被引用资产 409 `E_ASSET_IN_USE` + 使用处；
    替换只重写旧 sha 并返回 `affectedScenes`。
11. **Scene DSL 资产解析**：compiler 通过 `asset_resolver` 把 sha 变成 URL；缺失抛
    `E_ASSET_MISSING`（预览 409、节点失败），不静默降级。最终渲染走 FrameServer
    `/project`/`/global-assets`；预览/9:16 从 `file://` 加载，内联 data URL 并预加载图片/字体。
12. **SFX**：G05 读取 Run 快照 `audio_layers`，按绝对时间 adelay/volume/fade 生成
    `card/stems/sfx.wav`，再与 voice/music 混音；stems manifest 记录 `sfxCount`。
13. **缓存修正**：G01/G05/G06/G07 的缓存键纳入 `card/audio.json`、`card/audio.mix.json`
    与 timeline 快照 sha；否则改响度/SFX 设置仍命中旧产物（实测 G05 cached 曾静音）。
14. **字体**：字体资产许可来源/类型必填；fontTools 读 family/weight/cmap；编辑器选中字体后
    400ms 防抖自动查缺字，红色列出。
15. **模板快照**：`Template` 表存 profile/结构/风格/交付/文案；场景只存 duration 与视觉字段，
    不存绝对时间/文本；实例化重建 timeline 并重新分配 script 句子区间。
16. **模板资产**：模板记录 `sourceProjectId/assetShas`；实例化/场景插入时复制源项目本地资产，
    全局资产复用 sha；避免新项目引用别的项目目录。
17. **模板版本/升级**：项目写 `card/template.lock.json`；版本更新显式；diff 后 confirm 升级只覆盖
    已有场景视觉字段，保留文本/时长/id；系列 v1 同步 ≤5 项，CSV/队列/R4 FR-46 未做。
18. **QA 分析**：`services/qa.py` 聚合 timeline 校验、NodeRun 消息、E06 motion 指标、资产/许可；
    issue 稳定 id；`/qa` 与 `/qa/fix|undo|report`。安全动作只做扩场景/字号/换行/LUFS/许可/
    重跑失败节点；改文案/删场景/换风格/重做对齐仅给 manual 链接。
19. **QA 撤销**：`card/qa_fixes.json` 保存 before/after/afterVersion/verified；timeline 撤销若
    版本已变化则拒绝自动覆盖；误报率待下一次成功 Run 复核，不伪造。

## 验收结果（2026-11-03，FR-39 当时 EXECUTOR_VERSION 2.9.2）

- [x] S03 +2s：S04/S05 自动后移，duration 40→42、frames 1008；`verify_r3.py` project 201。
- [x] 分割 S02 → S02/S02b（transition=cut，文本独立），合并可还原；`verify_r3.py`。
- [x] 改一句自动保存 + 静帧预览：`e2e_r3.py`；相机+文本 motion preview 1.63s（≤3s）。
- [~] 撤销：UI 历史 50 步 + e2e 单步撤销；30 个文档版本已实测可恢复初始（`verify_r3.py`）；
      30 步 UI 连点未自动化，如实标部分。
- [x] 相机 3 keyframes + 文本 override + 4 种转场：project 208/run 261，D01/E03/E04 产物正确；
      同刻 preview vs final **SSIM 0.989483**。8 类转场由 `test_timeline_ops.py` 覆盖。
- [x] 100 场景 ops <0.2s（`test_timeline_ops.py`）；浏览器 100 场景 60fps 未实测。
- [x] 10 条批注（含框选）在不同帧；点击跳帧 4.0s→4.000s；export→clear→import 恢复 10 条；
      审片包 6.8MB、内含 40.0s review.mp4 + review.json + README（`verify_r3.py` + `e2e_r3.py`）。
- [x] **137 tests（FR-39 当时）**；`e2e_ui.py`/`e2e_onboarding.py`/`e2e_r3.py`/`e2e_takes.py` 全绿；R2.5 回归（2.8.0）：
      5s 交付 24.1s（project 215/run 270）、干净 rumor 46/46（run 272，256.1s）、
      5s 黄金 SSIM 1.0（project 216/run 271；无音频 G 链失败不影响视觉断言）、相机 preview/final SSIM 0.989483（project 208/run 261）。
- [x] FR-38：project 188 A=237 / B=254；视频 sha 不同；同步播放 1.324s vs 1.324s；差异面板；
      元数据/评分/当前/删除保护；分支 Run 255（parent 254）；采纳 S03 只改 S03。
- [x] FR-35：project 211/run 266，G01 场景拼接 5.0s、G05 mix 5.0s、G06 **−13.8 LUFS**
      （target −14）、stems 5/5/5s；processed take、16 onsets、markers 1；`verify_r3_audio_v2.py`。
- [x] `e2e_audio_v2.py`：Take/A-B/已处理标记、检测拍点、拼接试听、响度预设 −16↔−14。
- [x] **FR-36**：`verify_r3_assets.py` 50 图新增 2/去重 48；引用计数；删除 409 使用处；
      替换只标记 S01；缺资产预览 409；字体缺 2 字；全局 sha 复用。`e2e_assets.py` UI 上传/
      字体标红/时间轴插入/引用计数/删除阻断全绿。
- [x] **FR-36 final 证据**：project 211 / run 275：D01/E03/F02 图片图层进入 final；G05
      `sfxCount=1`，`card/stems/sfx.wav` 5.0s 非静音；G06/G07 通过。5s 黄金 project 223/run 282
      6 帧 SSIM 1.0。
- [x] FR-36 v1 已完成。
- [x] FR-37：`verify_r3_templates.py` 另存模板→变量实例化（文案/结构/资产复制/锁）→场景模板
      插入→模板 v2 diff/confirm 升级→系列 2 项；`e2e_templates.py` UI 全绿。
      模板 1/2 为当前演示（project 227），CSV/10 行队列/R4 FR-46 未做。
- [x] FR-39：`verify_r3_qa.py` text_overflow 扩场景→即时验证→撤销、许可修复/撤销、
      缺资产定位、报告（**attempts=8/undone=8/successRate=1.0**；注意 successRate 当前口径
      存在结构性失真，见专家审查 P2-21）；`e2e_qa.py` UI 全绿。
      执行器 2.9.2（text_scale，FR-39 当时），preview-1.7.0。

## 磁盘说明

2026-11-03 曾清理验收项目；随后专家全量审计又新增 13 条 project（228–240）与 8 个测试目录，
当前 DB 27 项目 / 21 目录。清理前先备份 DB、确认无运行 Job，只删审计残留；不要动演示项目。
详见 `HANDOFF.md` §0.5/§7.4。文中 project 201/208/189 等 ID 是证据记录，目录已删除。
当前演示项目：时间轴 202、审片/40s 174、Take 188、音频/资产 211（run 275）、5s 交付 215、
黄金 216；FR-36 新增黄金 223/run 282（状态 failed，不作成功证据）；脚本可复现全部结果。

## 复现命令

```bash
cd server && uv run pytest tests -q                       # 137
cd .. && uv run --project server python scripts/verify_r3.py
uv run --project server python scripts/verify_r3_camera.py
uv run --project server python scripts/verify_r3_takes.py
uv run --project server python scripts/e2e_r3.py
uv run --project server python scripts/e2e_takes.py
uv run --project server python scripts/verify_r3_audio_v2.py
uv run --project server python scripts/e2e_audio_v2.py
uv run --project server python scripts/verify_r3_assets.py
uv run --project server python scripts/e2e_assets.py
uv run --project server python scripts/verify_r3_templates.py
uv run --project server python scripts/e2e_templates.py
uv run --project server python scripts/verify_r3_qa.py
uv run --project server python scripts/e2e_qa.py
```

## 明确不做（下一批）

- FR-36 v1 边界：视频只入库不进入 NLE 图层；无智能裁切/主体检测；自定义字体走 FontFace
  全量加载，不做按项目子集重嵌；大图/字体在预览 payload 内联 data URL；资产目录暂无自动 GC。
- FR-37 v1 边界：系列最多 5 项、同步创建；CSV/10 行队列/批量 zip/失败重试依赖 R4 FR-46；
      模板升级不自动增删场景/迁移文案；模板源资产复制会增加磁盘；视频仍只入库。
- FR-40/41（R3.5）与任何 R4 能力未开始。

## 专家审查阻塞（2026-11-03，先修再开 FR-40/41）

全量审查基线 `82c992b`，结论 **Conditional Go**；完整复核见
`docs/reviews/2026-11-03-expert-review-analysis.md`，原始未脱敏报告仅本地
`~/.filmflow/reviews/2026-11-03-expert-review.raw.md`。

必须先修：

1. **P0-1** Next dev 绑全网卡 + 反代零鉴权 API（`dev.sh`/`next.config.mjs`；Host/Origin 校验）。
2. **P0-2** preview/final 转场 7/8 分叉（抽公共 `_transition_type` + 8 类参数化测试 + 转场窗口 SSIM）。
3. **P0-3** integration 直连生产 `:7860`、污染 DB；skipif 静默（独立 uvicorn/HOME/端口 + 环境硬断言）。
4. **P0-5** QA 修复只改 timeline，profile/Run 快照未变，`verified=true` 但成片未变；
   `retry_run` 复用旧 snapshot（同步 profile 或 fork 新 Run + 渲染级验证）。
5. **P0-4a** 3s/12 帧最小真实出片冒烟（Chrome+ffmpeg+SSIM）；P0-4b 再做 40s 增量脚本/原分辨率 SSIM/证据归档。

准入：上述完成，且 `divergent 0/8`、连续两次 pytest 生产 DB 不变、LAN/Origin/Host 探测失败、
QA 新 Run 时长增加且尾部场景存在、3s 冒烟绿。

### P0 Gate 已完成（2026-11-03）

- **P0-1**：Next dev 改 `127.0.0.1`；后端 Host/Origin 中间件；实测 LAN 000、错误 Host 400、跨源写 403。
- **P0-2**：转场映射抽到 `server/app/engine/scene/transitions.py`，preview/final/schema/timeline_ops 共用；
  `divergent 0/8`，新增 17 项测试。
- **P1-02/03/04**：A01/A03/F01/G01 外部指纹进键；C01 `enginePackSha`；G02/G04 项目输入入键；
  新增缓存失效测试；`EXECUTOR_VERSION=2.9.3`、preview `1.8.0`。
- **P0-3**：integration 使用独立临时 uvicorn/HOME/workspace；删除硬编码 skipif，缺风格库默认失败；
  连续 pytest 生产 DB 不变。
- **P0-5**：`extend_scene` 同步 timeline + profile（失败补偿回滚）；QA `verified=null/documentVerified=true/requiresRerun=true`；`retry_run` fork 新 Run；撤销同步恢复 profile；报告增加 `pendingRerun`。
- **P0-4a**：新增 `test_render_smoke.py`，真实 Chrome + ffmpeg + SSIM，断言 1s draft 输出 960×540/12fps/12 帧且帧一致性 ≥0.95。
- **测试**：完整 `pytest server/tests -q` **177 passed**（unit 157 + integration 13 + BDD 7），连跑生产 DB 不变。
- **P0-4b 已补齐**：`verify_r2_incremental.py --project 5s|15s|40s`、`golden_run.py --resolution original`、`docs/reports/` JSON 归档；已实跑 5s 增量和 5s 原帧 golden。15s/40s 原帧 baseline 按需生成，本次未跑 40s。
- **P1-13 交付门禁**：`run_delivery` 先比对当前 timeline 哈希与所选 Run 快照哈希，漂移即 `E_DELIVERY_GATE` 拒绝出片（2 项单测）。
- **P1-08 时间轴冲突保稿**：409 `E_DOC_CONFLICT` 保留本地草稿并弹出「只看服务端 / 保留本地并重试」，冲突期间暂停自动保存。
- **P1-15 资产引用面**：`scan_usages` 通用递归扫全部项目文档 + `Template.content_json` + Run 快照；`delete_asset` 含历史快照；`/assets` 标注来源；真实 HTTP 验证「仅剩模板引用时删除被 409 拦」。
- **P1-16/P1-18 许可强制**：所有资产种类入库都要 source+type（到期日须未过期）；被引用资产不可清空许可；`rights.json` 由 Run 快照真实资产生成并有缺口即拒交付；QA 新增 `asset_license_missing`，`fill_license` 去掉 `authorized` 预置、UI 需显式 YES。
- **P1 基础批次已开始**：A05 守卫、SQLite WAL/同步、workspace roots env、pytest 每次独立临时 DB；foreign_keys 暂不开启。
- **下一步**：P1 数据/缓存/媒体治理；FR-40/41 可选择开工。
