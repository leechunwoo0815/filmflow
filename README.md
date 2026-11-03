# FilmFlow

本地代码动画全生命周期 Web 工作台。**46 节点 / 7 阶段 / 341 条风格库 / 3 个渲染引擎（riso · code-video · ink）/ 中英双语。**

## 当前状态：参考片全链已贯通 ✅ · R2.0/R2.5/R3.0 v1 + R3.5 FR-39 已完成 ✅ · 下一批 FR-40/41

```
文案 → 索引 341 → 预演/推荐 → 风格门 → tokens → 任务卡+校验门 → 引擎编译
 → 字体子集(0缺字) → 静帧渲染(真实 Chrome) → 查看门 → QA门 → 批准门
 → 时间轴/代理帧474 → 运动QA → 分镜门 → 帧服务 → 逐帧渲染948 → 完整性
 → ffmpeg编码 → Y-SSIM QA → 画面锁定 → 口播/对齐/音乐/混音(loudnorm)
 → 响度QA(−16LUFS±1) → 交付门 → master.mp4 (39.500s, AAC 音轨)
```

实测（rumor-39s 导入全链，Run #1）：46/46 节点 succeeded · 49 产物 · 9 条审批记录（含驳回→重批历史）· master.mp4 = 69.9MB · 三引擎可生产 61 条。

> ⚠️ 以上是**导入参考片**的实测。R2.0 参数化链路正在按 [docs/process/r2-plan.md](docs/process/r2-plan.md) 实施：
> Phase 1 边表/Contract v2、Phase 2 文档模型与 Run 快照、Phase 3 5s 新项目参数化静帧 + `film_spec` 逐帧渲染（120 帧 / 5.000s / F05 通过）、Phase 4 场景级增量（改 S02 只渲 66/120 帧，S01 复用）、Phase 5 PreviewService（F02 运行中 CDP 附加 p50 1.31s/p95 1.44s，5s 片段 12.7s，缓存 5ms）、Phase 6 draft/review/final 档位（D02 双静帧、E05 720p/24、F02 only-final、切档不重跑）、Phase 7 持久化 Job 与 kill -9 恢复（F02 22.3s 恢复）、Phase 8 黄金项目/视觉回归（5s/15s/40s SSIM 1.0，干净 rumor 46/46）已完成；R2.0 DoD 通过。R2.5 已完成 FR-26 全场景静帧审阅（contact sheet/逐场门禁/review diff）、FR-27 音频工作台（waveform/对齐/许可/G05 Stems）、FR-28 交付 v1（5s 26.2s / 40s 190.0s，9 文件/QC/zip/9:16）与 FR-31 新手引导（模板音频占位/标题预演/只读示例/Studio 引导）。**R3.0 创作闭环 v1** 已交付 FR-32 时间轴（拖拽/ripple/分割/相机/转场/250ms 预览）、FR-33 审片播放器（帧锚定批注/导出导入/审片包）、FR-34 相机关键帧、FR-35 音频 v2（多 Take/处理/拼接/拍点/响度/Stems）、FR-38 Take 对比（评分/当前/同步/差异/采纳/分支）、FR-36 资产库（全局/项目 sha 去重、引用/替换、图片/字体/SFX、缺资产阻断）、FR-37 模板/系列（项目/场景模板、变量、模板锁/升级、≤5 小系列）、FR-39 QA 修复建议（分类/定位/扩场景/字号/换行/LUFS/许可/撤销/报告）；下一批 FR-40/41。

## 快速开始

```bash
./dev.sh        # 开发态：API :7860 + Web :3000
./build.sh      # 发布态：Next 静态导出 + FastAPI 单进程 :7860
```

- 首页 http://localhost:3000 → 导入 `~/cc-projects/ai-v/rumor-39s` 或走 5 步向导
- API 文档 http://127.0.0.1:7860/api/docs

## 测试

```bash
cd server
uv run pytest tests -q   # 123（干净环境首跑；部分集成需 API 在跑）
uv run --project server python scripts/smoke_m1.py    # M0/M1 API 全链冒烟（需服务在跑）
uv run --project server python scripts/e2e_ui.py      # Playwright UI E2E（8 场景，需 ./dev.sh 在跑）
uv run --project server python scripts/verify_r2_5s_incremental.py  # R2.0 5s 参数化 + 增量验收
uv run --project server python scripts/verify_r2_preview.py         # R2.0 Phase 5 预览验收
uv run --project server python scripts/verify_r2_profiles.py        # R2.0 Phase 6 档位验收
uv run --project server python scripts/verify_r2_recovery.py        # R2.0 Phase 7 恢复验收
uv run --project server python scripts/golden_run.py --project 5s    # R2.0 Phase 8 黄金回归
uv run --project server python scripts/verify_r2_5_review.py        # R2.5 FR-26 审阅验收
uv run --project server python scripts/verify_r2_5_audio.py         # R2.5 FR-27 音频验收
uv run --project server python scripts/verify_r2_5_delivery.py      # R2.5 FR-28 交付验收
uv run --project server python scripts/verify_r2_5_onboarding.py    # R2.5 FR-31 新手引导验收
uv run --project server python scripts/verify_r2_5_delivery_40s.py  # FR-28 40s 全链交付实测
uv run --project server python scripts/verify_r3.py                 # R3 时间轴+审片
uv run --project server python scripts/verify_r3_camera.py          # R3 相机 final 一致性
uv run --project server python scripts/e2e_r3.py                    # R3 UI 冒烟
uv run --project server python scripts/verify_r3_takes.py           # Take 对比验收
uv run --project server python scripts/e2e_takes.py                 # Take UI 冒烟
uv run --project server python scripts/verify_r3_audio_v2.py        # 音频 v2 全链
uv run --project server python scripts/e2e_audio_v2.py              # 音频 v2 UI
uv run --project server python scripts/drive_run.py <run> <project>   # 全链驱动（自动批门）
```

## 文档地图

| 文档 | 说明 |
|---|---|
| **[AGENTS.md](AGENTS.md)** | **Qoder / 新 Agent 入口（3 份必读 + 硬约束）** |
| **[QODER_PROMPT.md](QODER_PROMPT.md)** | **给 Qoder 的完整接手 prompt（复制到对话框）** |
| **[HANDOFF.md](HANDOFF.md)** | **接手入口（交接文档：状态/坑/缺口/路线图）** |
| **[vendor/README.md](vendor/README.md)** | **内置 fy-code-animation 技能 + 341 风格库路径（76MB 库不入库）** |
| `../filmflow-web-agent-prompt.md` | 技术规格（§4.8 边表 / §19 裁决表为宪法） |
| `../filmflow-prd.md` | v1 PRD（FR-1~14 / US-01~10 / 风险） |
| **[docs/prd/PRD-002-production-workbench.md](docs/prd/PRD-002-production-workbench.md)** | **v2 补充 PRD（30 FR / 场景 DSL / 两级执行 / 交付矩阵 / R2–R4 路线图）** |
| `docs/tech-plan.md` | §18 九项技术方案 |
| `docs/process/` | SDLC / Feature 拆分 / 测试策略 / **R2.0 验收报告 / R2.5 计划 / R3 计划与验收** |
| `bdd/features/` | 16 个中文 Gherkin 特性文件（自动化 3 场景 + 手动验收拆分） |
| `docs/adr/` | ADR-0001 技术栈 · ADR-0002 实测矩阵 · ADR-0003 embed 上限 · ADR-0004 白天主题 · **ADR-0005 v2 裁决 D1–D7** · **ADR-0006 PreviewService** |

## 已知边界（诚实清单）

- ~~Playwright UI E2E~~ → 已交付（`scripts/e2e_ui.py`：8 场景 15s 全绿——首页→向导 5 步→风格选择器搜索/设主风格→生成→46 节点画布→EN 切换→导入）。
- **补标队列 123 条**：标注 UI 已交付（/labeling），标注本身需人工完成（约 4 小时）。
- **whisper 对齐**：模型未下载时走手动打点回退（规格允许）；下载 ggml-medium 后自动启用词级对齐。
- ~~ink 引擎~~ → 已交付（`engines/ink/` 含基准 fixture，producible 61）。
- ~~英文 i18n~~ → 已交付（`web/src/lib/i18n.tsx`：zh/en 双词典 + 语言切换，全页面接入）。

## 实现期裁决（已录规格 §19）

F03 重复帧按 §6.2 降为警告 · G07 门后真实打包 · embed 上限 profile 化 · 门控调度活同步。
