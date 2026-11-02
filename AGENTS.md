# FilmFlow · Agent 接手入口

> 给 Qoder / 任何新 Agent：先读这三份，再动手。
> 1. [`HANDOFF.md`](HANDOFF.md) —— **R2.0 当前状态、Phase 0.1–8 记录、证据、坑、R2.0 验收结论、接手检查表**。
> 2. [`docs/prd/PRD-002-production-workbench.md`](docs/prd/PRD-002-production-workbench.md) —— v2 深化需求（30 条 FR、场景 DSL、两级执行、R2–R4）。
> 3. [`vendor/README.md`](vendor/README.md) —— 内置 `fy-code-animation` 技能与 341 风格库路径（76 MB 库不入库）。
> **老板已裁决 D1–D7（2026-11-02，[ADR-0005](docs/adr/ADR-0005-v2-ratification.md)）；R2.0 直接开工，不要再等确认。**
> **当前进度（2026-11-02）**：R2.0 Phase 0.1–8 全部完成并通过 DoD；**R2.5 已获老板授权，FR-26 全场景静帧审阅已完成**（tag `r2_5-review`，86 tests）。下一步 R2.5 · FR-27 音频工作台。详见 `docs/process/r2_5-plan.md`。
> **完整接手 prompt**：[`QODER_PROMPT.md`](QODER_PROMPT.md)（历史 prompt；新 Agent 先看 HANDOFF §0/§6）。

## 这个仓库是什么

FilmFlow 是本地代码动画全生命周期工作台：46 节点 / 7 阶段 / 341 风格库 / 3 引擎（riso · code-video · ink）。参考片 rumor-39s 已跑通 46/46；R2.0 已交付 5s/15s/40s 参数化出片、快照、增量、预览、档位、恢复与黄金回归；R2.5 已交付全场景静帧审阅。结论见 `docs/process/r2-acceptance.md` / `r2_5-plan.md`。

## 硬约束（不要违反）

- 仅本机 `127.0.0.1`；不上传文件；**不调用任何在线生成模型**。
- 所有文件操作在已登记项目根白名单内；禁止任意 shell / 路径穿越。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；新增能力走节点内部子流程（PRD-002 §2.3/§15）。
- 改执行器行为**必须升 `EXECUTOR_VERSION`**，否则缓存返回旧行为。
- UI 自动化用系统 Chrome + 键盘输入（React 19 的 `fill()` 不触发 onChange）。

## 341 风格库

- 路径：`cat vendor/style-library.path`
- 技能配置：`vendor/fy-code-animation/adapters/style-library.config.json`
- FilmFlow 默认：`server/app/config.py:13`
- 环境变量：`FILMFLOW_STYLE_LIBRARY_ROOT`（App）/ `FY_STYLE_LIBRARY_ROOT`（技能）
- 自检：`python3 vendor/fy-code-animation/scripts/doctor.py --root "$(cat vendor/style-library.path)"`
- **不要**把 76 MB 库（尤其 `示例/` 的 61 MB mp4）提交进 git；**不要**把技能目录加进 Python 包路径。

## R2.0 开工范围（已裁决）

只做 FR-20/21/22/23/24/25/29/30；R3 时间轴/审片/音频 v2/交付矩阵等 R2.0 验收后再开。
R2.0：FR-20/21/22/23/24/25/29/30 全部；R2.5：FR-26 完成，FR-27/28/31 待做。
第一验收：5 秒新项目全链出**用户文案**；改 S03 只渲 S03+邻接；单帧 p50 ≤2s；kill -9 后 ≤60s 恢复；rumor-39s 仍 46/46。
预览验收：F02 运行中附加预览 p50 1.31s / p95 1.44s；5s 片段 12.7s；缓存 5ms（见 HANDOFF §2.4）。
档位验收：D02 review/draft、E05 720p/24、F02 only-final、切档不重跑、draft vs final SSIM 0.9987（HANDOFF §2.5）。
恢复验收：F02 中 kill -9，22.3s 恢复、frames=120、单 Job attempts=1（HANDOFF §2.6）。
审阅验收：D03 逐场门禁、contact sheet、改 S03 diff 只标 S03（HANDOFF §2.8）。
黄金验收：5s/15s/40s 6 帧 SSIM 1.0；干净 rumor 46/46、master 39.5s（HANDOFF §2.7）。
详见 `docs/prd/PRD-002-production-workbench.md` §7.2 / §8.1–8.8 与 `HANDOFF.md` §6。

## 先跑什么

```bash
./dev.sh
cd server && uv run pytest tests -q                       # 86 项（R2.5 FR-26）
uv run --project server python scripts/e2e_ui.py          # UI 8 场景 ~15s
uv run --project server python scripts/smoke_m1.py        # API 冒烟：46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量验收
uv run --project server python scripts/verify_r2_preview.py         # Phase 5 预览验收
uv run --project server python scripts/verify_r2_profiles.py        # Phase 6 档位验收
uv run --project server python scripts/verify_r2_recovery.py        # Phase 7 恢复验收
uv run --project server python scripts/golden_run.py --project 5s    # Phase 8 黄金回归
uv run --project server python scripts/verify_r2_5_review.py        # R2.5 FR-26 审阅验收
```

验收标准：见 `HANDOFF.md` §10 检查表；任何“完成”申报必须附测试输出、真实产物路径、UI 截图、API curl。
