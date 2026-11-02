# FilmFlow · Agent 接手入口

> 给 Qoder / 任何新 Agent：先读这三份，再动手。
> 1. [`HANDOFF.md`](HANDOFF.md) —— **R2.0 当前状态、Phase 0.1–4 记录、证据、坑、Phase 5–8 设计、接手检查表**。
> 2. [`docs/prd/PRD-002-production-workbench.md`](docs/prd/PRD-002-production-workbench.md) —— v2 深化需求（30 条 FR、场景 DSL、两级执行、R2–R4）。
> 3. [`vendor/README.md`](vendor/README.md) —— 内置 `fy-code-animation` 技能与 341 风格库路径（76 MB 库不入库）。
> **老板已裁决 D1–D7（2026-11-02，[ADR-0005](docs/adr/ADR-0005-v2-ratification.md)）；R2.0 直接开工，不要再等确认。**
> **当前进度（2026-11-02）**：R2.0 Phase 0.1–4 已完成（FR-20/21/22/25；tag `r2-edge-fix`/`r2-scene-dsl`/`r2-incremental`，52 tests）。**下一步从 HANDOFF §6 Phase 5（PreviewService）开始，不要重做 Phase 1–4。**
> **完整接手 prompt**：[`QODER_PROMPT.md`](QODER_PROMPT.md)（历史 prompt；新 Agent 先看 HANDOFF §0/§6）。

## 这个仓库是什么

FilmFlow 是本地代码动画全生命周期工作台：46 节点 / 7 阶段 / 341 风格库 / 3 引擎（riso · code-video · ink）。参考片 rumor-39s 已跑通 46/46；R2.0 Phase 1–4 已打通 5s 新项目参数化出片、Run 快照与场景级增量。剩余 FR-23/24/29/30 见 `HANDOFF.md` §1/§6。

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
已完成：FR-20/21/22/25（Phase 1–4）；部分：FR-24（仅 final）；待做：FR-23/29/30。
第一验收：5 秒新项目全链出**用户文案**；改 S03 只渲 S03+邻接；单帧 p50 ≤2s；kill -9 后 ≤60s 恢复；rumor-39s 仍 46/46。
详见 `docs/prd/PRD-002-production-workbench.md` §7.2 / §8.1–8.8 与 `HANDOFF.md` §6。

## 先跑什么

```bash
./dev.sh
cd server && uv run pytest tests -q                       # 52 项（R2.0 Phase 4）
uv run --project server python scripts/e2e_ui.py          # UI 8 场景 ~15s
uv run --project server python scripts/smoke_m1.py        # API 冒烟：46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py  # Phase 4 5s 增量验收
```

验收标准：见 `HANDOFF.md` §10 检查表；任何“完成”申报必须附测试输出、真实产物路径、UI 截图、API curl。
