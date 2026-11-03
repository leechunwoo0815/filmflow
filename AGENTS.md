# FilmFlow · Agent 接手入口

> 给 Qoder / 任何新 Agent：先读这三份，再动手。
> 1. [`HANDOFF.md`](HANDOFF.md) —— **R2.0 验收 + R2.5 当前状态、证据、坑、剩余工作、接手检查表**。
> 2. [`docs/prd/PRD-002-production-workbench.md`](docs/prd/PRD-002-production-workbench.md) —— v2 深化需求（30 条 FR、场景 DSL、两级执行、R2–R4）。
> 3. [`vendor/README.md`](vendor/README.md) —— 内置 `fy-code-animation` 技能与 341 风格库路径（逻辑约 75MiB；mp4 为稀疏文件，磁盘分配约 9.3MiB；库不入 git）。
> **老板已裁决 D1–D7（2026-11-02，[ADR-0005](docs/adr/ADR-0005-v2-ratification.md)）；R2.0 直接开工，不要再等确认。**
> **当前进度（2026-11-03 20:00）**：R2.0/R2.5/R3.0 v1（FR-32–38）/R3.5 FR-39 已交付；**专家审查 P0 Gate 全部关闭**（P0-4b 的 40s 增量、15s/40s 原帧 baseline 仍未实跑）；**P1 治理已完成 14 项**（02/03/04/05/07/08/13/14/15/16/17/18/22 + 06/19/23 部分）。完整 `pytest server/tests -q` **201 passed**（unit 169 + integration 13 + BDD 7），`EXECUTOR_VERSION=2.10.0`、preview `1.8.0`。FR-40/41 已满足准入（等老板点头）；P1 剩余顺序见 `HANDOFF.md` §6.5，状态表 §0.6、破坏性语义 §0.6.1、运维坑 §0.7。R4 不做。
> **完整接手 prompt**：[`QODER_PROMPT.md`](QODER_PROMPT.md)（历史 prompt；新 Agent 先看 HANDOFF §0/§6）。

## 这个仓库是什么

FilmFlow 是本地代码动画全生命周期工作台：46 节点 / 7 阶段 / 341 风格库 / 3 引擎（riso · code-video · ink）。参考片 rumor-39s 已跑通 46/46；R2.0 已交付 5s/15s/40s 参数化出片、快照、增量、预览、档位、恢复与黄金回归；R2.5 已交付审阅/音频/交付/新手引导。结论见 `docs/process/r2-acceptance.md` / `r2_5-plan.md`。

## 本轮新增的门禁（撞到不是 bug，别绕）

- 资产入库必须给 `license.source` + `license.type`，`expires` 须为未过期 ISO 日期 → 否则 400 `E_ASSET_LICENSE`。
- 资产被任何 timeline/文档/模板/Run 快照引用时不许清空或削弱许可（防洗白）。
- `rights.json` 是 `filmflow.rights/2`，内容由 Run 快照真实资产引用生成；有许可缺口 → `E_LICENSE_MISSING` 拒交付。
- 非导入项目交付前要求「当前 timeline 哈希 == 所选 Run 快照哈希」→ 否则 `E_DELIVERY_GATE`（演示 188/211 的部分 Run 当前就漂移）。
- QA 多步修复必须**倒序撤销**（`afterHash` 链顶判定）；文档级修复 `verified=null` + `documentVerified=true`。
- 9 个高风险写端点已用 Pydantic 请求模型（非法输入 422）；`/projects/import` 与 drafts materialize 是**直接函数调用** `projects_create(ProjectCreateIn(...))`，别再传 dict。

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
- **不要**把风格库（逻辑约 75MiB；`示例/` mp4 约 60MiB，稀疏文件）提交进 git；**不要**把技能目录加进 Python 包路径。

## 范围与当前进度（已裁决）

已完成：R2.0（FR-20/21/22/23/24/25/29/30）、R2.5（FR-26/27/28/31）、
R3.0 v1（FR-32–38）+ R3.5 FR-39。下一批：FR-40/41；不提前做 R4。
第一验收：5 秒新项目全链出**用户文案**；改 S03 只渲 S03+邻接；单帧 p50 ≤2s；kill -9 后 ≤60s 恢复；rumor-39s 仍 46/46。
预览验收：F02 运行中附加预览 p50 1.50s / p95 1.92s；5s 片段 13.2s；缓存 5ms（HANDOFF §2.3）。
档位验收（2026-11-03 重跑，run 309）：D02 review/draft 混排不崩、E05 720p/24、F02 only-final、切档不重跑；draft vs final SSIM 稳定段最差 0.998663（≥0.98）、切点/入场 0.5s 窗口最差 0.952097（≥0.90）——旧口径只报 0.9987 稳定段，已修正（HANDOFF §2.4）。
恢复验收：F02 中 kill -9，22.3s 恢复、frames=120、单 Job attempts=1（HANDOFF §2.5）。
审阅验收：D03 逐场门禁、contact sheet、改 S03 diff 只标 S03（HANDOFF §3.1）。
音频验收：waveform 49ms、手动对齐、许可、Stems 5s、LUFS -16/TP -10.5（HANDOFF §3.2）。
交付验收：9 文件、QC 全绿、9:16 1080×1920、zip（HANDOFF §3.3）。
黄金验收：5s/15s/40s 6 帧 SSIM 1.0；干净 rumor 46/46、master 39.5s（HANDOFF §2.6）。
下一步：R3.5 FR-40/41；不要开始 R4。详见 `HANDOFF.md` §6.5。

## 先跑什么

> 专家整夜自主循环（goal 模式）的提示词：`docs/process/expert-overnight-goal-prompt.md`（先证伪交接声明，再按优先级补 P1/P2，每轮必须提交并留证据）。

```bash
./dev.sh
cd server && uv run pytest tests -q                       # 219 项（含 integration 真实出片冒烟 + P0/P1 回归；foreign_keys=ON）
uv run --project server python scripts/e2e_ui.py          # UI 8 场景 ~15s
uv run --project server python scripts/e2e_onboarding.py  # FR-31 UI 冒烟
uv run --project server python scripts/smoke_m1.py        # API 冒烟：46 / 93
uv run --project server python scripts/verify_r3.py       # R3 时间轴+审片
uv run --project server python scripts/verify_r3_camera.py # R3 相机/文本/转场
uv run --project server python scripts/e2e_r3.py          # R3 UI 冒烟
uv run --project server python scripts/verify_r3_takes.py # Take 对比验收
uv run --project server python scripts/e2e_takes.py       # Take UI 冒烟
uv run --project server python scripts/verify_r3_audio_v2.py # 音频 v2 全链
uv run --project server python scripts/e2e_audio_v2.py   # 音频 v2 UI 冒烟
uv run --project server python scripts/verify_r3_assets.py # 资产库/图片/字体/SFX
uv run --project server python scripts/e2e_assets.py      # 资产库 UI 冒烟
uv run --project server python scripts/verify_r3_templates.py # 模板/场景/系列
uv run --project server python scripts/e2e_templates.py   # 模板 UI 冒烟
uv run --project server python scripts/verify_p1_governance.py # ★ 一条命令复核本轮 8 项 P1 门禁
uv run --project server python scripts/verify_r3_qa.py    # QA 验收（自建自删临时项目，6 步）
uv run --project server python scripts/e2e_qa.py          # QA UI 冒烟
uv run --project server python scripts/verify_r2_incremental.py --project 5s  # Phase 4 增量验收（支持 5s/15s/40s）
uv run --project server python scripts/verify_r2_preview.py         # Phase 5 预览验收
uv run --project server python scripts/verify_r2_profiles.py        # Phase 6 档位验收（SSIM 分窗口，会建 5s 项目）
uv run --project server python scripts/verify_r2_recovery.py        # Phase 7 恢复验收
uv run --project server python scripts/golden_run.py --project 5s --resolution original    # Phase 8 黄金回归（原帧 SSIM + 报告归档）
uv run --project server python scripts/verify_r2_5_review.py        # R2.5 FR-26 审阅验收
uv run --project server python scripts/verify_r2_5_audio.py         # R2.5 FR-27 音频验收
uv run --project server python scripts/verify_r2_5_delivery.py      # R2.5 FR-28 交付验收
```

验收标准：见 `HANDOFF.md` §10 检查表；任何“完成”申报必须附测试输出、真实产物路径、UI 截图、API curl。
手工探针纪律：`TestClient(app)` 连的是生产库 —— 只有必然被 422/400 挡在 handler 之前的请求可以用它；
会写的验证一律走 `scripts/_acceptance.py` 临时项目或独立 `FILMFLOW_HOME`（详见 `HANDOFF.md` §0.7）。
