# R3.0 创作闭环 v1（FR-32/33/34/35/38）

> 代码：`1d2fcf6` + FR-35 增量；EXECUTOR_VERSION 2.8.0。tag 见 `git log`。

> 依据：PRD-002 §7.3；R2.5 已收口（tag `r2_5-onboarding`）。老板要求继续后续开发，明早验收。
> 本文覆盖 FR-32/33/34/35/38；FR-36 资产库、FR-37 模板/系列留到下一批，
> 不虚报为 R3.0 全量。

## 本轮范围

| FR | 交付 |
|---|---|
| FR-32 时间轴编辑器 | `/timeline`：V/T/C/A1/A2/A3/M 轨道、拖拽/改时长/ripple、分割/合并/复制、吸附、播放头/JKL/缩放、场景文本编辑、250ms 静帧预览、自动保存、撤销 50、读时校验 |
| FR-33 审片播放器 | `/player`：F04/review/master 视频、逐帧/JKL/循环/全屏/安全区、矩形/箭头/画笔/文字批注、帧+场景锚点、回复/resolve、场景决议、review.json/CSV 导出导入、审片包 zip |
| FR-34 镜头语言 v1 | 时间轴相机 inspector：keyframes（t/zoom/x/y/rotate）、7 预设、曲线缩略图；转场 8 类+时长；program 更新走同一编译器 |
| FR-38 Take 对比 | `/takes`：Run 列表/评分/当前、A/B 视频同步、差异叠加、场景采纳、promote/branch/软删除保护；`card/takes.json` |
| FR-35 音频 v2 | `/audio`：多 Take/场景 Take 拼接、processed WAV（高通/降噪/齿音/EQ/静音裁剪/响度归一）、A/B 试听、onset/拍点、−14/−16/−18 响度预设、Stems 增益；`card/audio.mix.json`/`markers.json` |

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

## 验收结果（2026-11-02，EXECUTOR_VERSION 2.8.0）

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
- [x] **119 tests**；`e2e_ui.py`/`e2e_onboarding.py`/`e2e_r3.py`/`e2e_takes.py` 全绿；R2.5 回归（2.7.2）：
      5s 交付 24.1s（project 215/run 270）、干净 rumor 46/46（run 272，256.1s）、
      5s 黄金 SSIM 1.0（project 216/run 271；无音频 G 链失败不影响视觉断言）、相机 preview/final SSIM 0.989483（project 208/run 261）。
- [x] FR-38：project 188 A=237 / B=254；视频 sha 不同；同步播放 1.324s vs 1.324s；差异面板；
      元数据/评分/当前/删除保护；分支 Run 255（parent 254）；采纳 S03 只改 S03。
- [x] FR-35：project 211/run 266，G01 场景拼接 5.0s、G05 mix 5.0s、G06 **−13.8 LUFS**
      （target −14）、stems 5/5/5s；processed take、16 onsets、markers 1；`verify_r3_audio_v2.py`。
- [x] `e2e_audio_v2.py`：Take/A-B/已处理标记、检测拍点、拼接试听、响度预设 −16↔−14。
- [x] 明确未做 FR-36/37，见下节。

## 复现命令

```bash
cd server && uv run pytest tests -q                       # 123
cd .. && uv run --project server python scripts/verify_r3.py
uv run --project server python scripts/verify_r3_camera.py
uv run --project server python scripts/verify_r3_takes.py
uv run --project server python scripts/e2e_r3.py
uv run --project server python scripts/e2e_takes.py
uv run --project server python scripts/verify_r3_audio_v2.py
uv run --project server python scripts/e2e_audio_v2.py
```

## 明确不做（下一批）

- FR-36 图片/字体资产库与 image 图层（需要 renderer/DSL 扩展）；FR-35 的 SFX 拖入因此未做。
- FR-37 模板另存/系列/批量（依赖 FR-46 R4 批量），本轮不做。
- 任何 R4 能力。
