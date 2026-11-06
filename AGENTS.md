# FilmFlow · Agent 接手入口

> 给 Qoder / 任何新 Agent：先读这三份，再动手。
> 1. [`HANDOFF.md`](HANDOFF.md) —— **R2.0 验收 + R2.5 当前状态、证据、坑、剩余工作、接手检查表**。
> 2. [`docs/prd/PRD-002-production-workbench.md`](docs/prd/PRD-002-production-workbench.md) —— v2 深化需求（30 条 FR、场景 DSL、两级执行、R2–R4）。
> 3. [`vendor/README.md`](vendor/README.md) —— 内置 `fy-code-animation` 技能与 341 风格库路径（逻辑约 75MiB；mp4 为稀疏文件，磁盘分配约 9.3MiB；库不入 git）。
> **老板已裁决 D1–D7（2026-11-02，[ADR-0005](docs/adr/ADR-0005-v2-ratification.md)）；R2.0 直接开工，不要再等确认。**
> **当前进度（2026-11-05 第二夜，P2 账本又清 15 条，报告 `docs/process/b9-close-report.md`）**：P0-5 渲染级 E2E 已转正；P2-02 节点 timeout/retries 强制执行、P2-03 同项目 Run 互斥、P2-32 帧服务 token（只护数据面；A2 起 X-FilmFlow-Token header + URL #fragment 携带，?tok= 已废除、0 处 URL 构造残留）、P2-28 服务日志（`~/.filmflow/logs/app.log`）、P2-30 except:pass 清零、P2-34 启动每日自动备份、P2-18/19/20 模板三连、P2-21/22/23 QA 结构化、P2-14 相机三路径统一+引擎 ease、P2-16 死依赖移除、P2-06 ADR-0013。：R2.0/R2.5/R3.0 v1（FR-32–38）/R3.5 FR-39 已交付；判官复核（`docs/process/judge-review-2026-11-04.md`）判整夜循环未完成，其 **§六 #1–#11 与 §三-10（P1-23）现已全部关闭**：删除面 `7d5b6e4`、NTSC fps `9dfdff9`、422 信封 `dbc208a`、交付归属+QA 链序号 `fb15d58`、**存储型脚本面+原子写+版本链保 v1+异步失败可见 `a324415`**、**快照库内封印+撤销前置态+未知 Run 404 `63d37c0`**、**15s/40s 原帧 golden `8ca3e01`**、**100 场景有效重测 `7b06432`**、**文档一致性守卫 `77c1ab5`**、**验收脚本 fail-closed `e896a78`**、**自建前置态 builder + 第 14 项守卫 `a8818b9`**、**31 个裸 dict 写端点清零 + 51 端点逐条 happy-path + 第 15 项守卫 `36411bf`**。实测（**2026-11-06 整夜 R2**，dev 在跑）：**364 passed**（collected **396** = unit 356 / integration 33 / BDD 7，两轮 200.1s/199.2s，0 skipped——A8 已把 `test_p1_foundations.py:234` 的 8787 占用门控改成绑空闲端口；历史口径见台账轮 0）、`verify_p1_governance.py` **17 项全绿**（第 17 项＝A3 lint 棘轮，基线 `docs/reports/lint-baseline.json`）、`check_docs_consistency.py` **PASS**、迁移登记（B8 当时 `[1,2,3,4]`，现 `[1,2,3,4,5]`）、`EXECUTOR_VERSION` 现 **2.17.0**（2.13.0 C02 字体 sha 钉、2.14.0 帧端口可配置、2.15.0 timeout/retries+Run 互斥、2.16.0 B2 两遍 loudnorm + f04 bt709 色彩标签、2.17.0 B3 文字淡出对齐出转场窗口）、`foreign_keys=ON`、tsc 干净、ruff **339**（`cd server && uv run ruff check .` 口径）/ **405**（仓库根口径；差异来自 `scripts/` 不继承 `line-length=110`，报数字必须写 cwd）；DB **11 项目 / 11 目录 / 1.5GB**，VACUUM 后库文件 26,005,504B（2026-11-05 §7-3 删 14 个验收残留项目 + 105 条僵尸 draft，备份 `~/filmflow-backup-20261105-pre-b9-cleanup.db`；2026-11-06 再清孤儿目录 `r3-camera-260` 65MB + 4 条僵尸 draft 并 VACUUM，备份 `~/filmflow-backup-20261106-pre-vacuum.db`；现存 11 个全部是演示/rumor 名单，见 HANDOFF §7.4）。B7 之后**验收脚本不再碰演示项目**（实测跑完 9 个脚本，演示 docrevision 计数零变化：188=28 / 211=37 / 227=58 / 174=3）；#6 结论：100 场景 × 4s 两次独立重跑（首屏 951/1640ms、ops p95 13.3–19.3ms、autosave 758–775ms、rAF 50.6 次/秒）→ **暂不虚拟化**（保留意见：headless rAF ≠ 用户 vsync 帧率，要下用户体验结论需 headed 复跑）。剩余工程债：~~交付门禁 `render.profile.json`/`caps_json`/`params_snapshot`~~（✅ `f0689b1`：caps 只许长大、params 非空才比对、render profile 走 `resolve()` 等价比对；`_alignment` 仍按判官 F-DEL-4「记录不改」；**注意 `params_snapshot` 现网 0 行非空，该条形同虚设 → 任务书 A6**）、~~僵尸 draft / verify 脚本缺 teardown~~（✅ 2026-11-05：9 脚本全接 Cleanup 自删、棘轮归零、残留已清）、CI（已 push、**首跑真跑即红**：`3 failed, 354 passed, 3 skipped, 3 errors`——未标记的 ffmpeg 用例 ×3 + 风格库纪律失败 ×3 + `test_assets.py` 两处静默 skip，根因与三个修法见任务书 H9，老板选定**双 job**：`ci-lean` 必绿 + `ci-env` 真环境）、fresh-clone（`scripts/bootstrap_fresh_clone.sh` 已落但**未在干净目录实测**）。FR-40/41 老板已点头，按整夜任务书 Wave E/F 做；R4 不做。
> **整夜自主开发任务书（现行，2026-11-05 夜）**：[`docs/process/overnight-goal-2026-11-05.md`](docs/process/overnight-goal-2026-11-05.md)——Wave A–G 全量任务 + 完成定义 + 纪律 + 审查方式；进度真源是 [`docs/process/overnight-ledger-2026-11-05.md`](docs/process/overnight-ledger-2026-11-05.md)（每轮追加）。
> **完整接手 prompt（B9 中途交接）**：[`docs/process/handoff-prompt-b9.md`](docs/process/handoff-prompt-b9.md)——B9 中途换模型的完整交接：角色/硬约束/当前状态/已改逐条（含验证状态）/没做完的三件/队列/12 个坑/汇报格式/停止条件。历史 prompt 见 [`QODER_PROMPT.md`](QODER_PROMPT.md)；仓库状态看 `HANDOFF.md` §0/§6。

## 这个仓库是什么

FilmFlow 是本地代码动画全生命周期工作台：46 节点 / 7 阶段 / 341 风格库 / 3 引擎（riso · code-video · ink）。参考片 rumor-39s 已跑通 46/46；R2.0 已交付 5s/15s/40s 参数化出片、快照、增量、预览、档位、恢复与黄金回归；R2.5 已交付审阅/音频/交付/新手引导。结论见 `docs/process/r2-acceptance.md` / `r2_5-plan.md`。

## 本轮新增的门禁（撞到不是 bug，别绕）

- 资产入库必须给 `license.source` + `license.type`，`expires` 须为未过期 ISO 日期 → 否则 400 `E_ASSET_LICENSE`。
- 资产被任何 timeline/文档/模板/Run 快照引用时不许清空或削弱许可（防洗白）。
- `rights.json` 是 `filmflow.rights/2`，内容由 Run 快照真实资产引用生成；有许可缺口 → `E_LICENSE_MISSING` 拒交付。
- 非导入项目交付前要求「当前 timeline 哈希 == 所选 Run 快照哈希」→ 否则 `E_DELIVERY_GATE`（演示 188/211 的部分 Run 当前就漂移）；交付还必须**归属该项目**、final 档位与 Run 快照一致（B4）。
- QA 多步修复必须**按链序号倒序撤销**（`undoKind`+`seq`，内容哈希作二次守卫）；既无 `seq` 又无 `afterHash` 的历史记录拒绝自动撤销；文档级修复 `verified=null` + `documentVerified=true`。
- 帧率唯一口径 `server/app/engine/fpscalc.py`：NTSC 吸附精确有理数（24000/1001…）、有 duration 就现算帧数、final 只放行 `is_delivery_fps()` 白名单 → `EXECUTOR_VERSION=2.11.0`。
- 删除项目只走 `DELETE /projects/{id}`：项目根必须是白名单**真子目录**且不含 `.git`（登记时就拒），保护名单（`rumor*` + 演示项目名精确）需回显 `confirm_name`，有在飞作业（心跳/`started_at` 120s 内）需 `force=true`；先校验后动数据、库删单事务、之后才删目录。
- **51 个写端点全部收 Pydantic 请求模型**（非法输入 **422 也走 ApiError 信封** `{code,message,details}`；守卫＝反射，一键复核第 **15** 项 + `server/tests/unit/test_request_models_batch3.py::test_no_write_endpoint_takes_a_bare_dict`，`routes.py` 里 `payload: dict` 必须为 0）。三条约好的语义别破坏：**PATCH 语义**的服务层（`takes.update`/`review_comments.update`/`drafts_patch`/`label_submit`）只能收 `model_dump(exclude_unset=True)`，"没传"与"传了 null"不同；**透传语义**（批注、草稿 payload、审片 JSON）保留 `extra="allow"`，模型化不许丢键；`copy` 在线上传输键名不变、内部叫 `copy_text`（避开 `BaseModel.copy`）。`/projects/import` 与 drafts materialize 是**直接函数调用** `projects_create(ProjectCreateIn(...))`，别再传 dict。
- **人工补标的 token 会直接进 WebGL 着色器**：`POST /labels/{style_id}` 的 `palette` 必须是 `#RGB`/`#RRGGBB`、`screen` 必须是数值（实测非 hex 会让 `preview/still` 抛 shader 编译错误 → 500）；补标写入必须 `flag_modified(st, "tokens_json")`，否则原地改 dict 不标脏、**补标静默丢失**（B8 实测到的老缺陷）。音频上传的 base64 长度上限与服务层 `audio.MAX_BYTES` 同源换算，改一边要同步另一边（单测会钉住）。
- **文件响应只按白名单内联**：一律走 `security.file_response`——`INLINE_MEDIA` 之外（HTML/XML/JS/未知后缀）强制 `application/octet-stream` + `attachment`；SVG 保留 `image/svg+xml` 但响应带 `CSP sandbox`；`:8787` 的 `/project`、`/global-assets` 拒绝 HTML/JS（`/engine` 必须能跑自己的脚本，别加 CSP）。**别再写裸 `FileResponse(p)`。**
- **落盘一律 `atomicwrite.write_atomic`**（唯一临时名 + fsync + `os.replace`）：`server/app` 里裸 `write_text/write_bytes` 已归零，一键复核第 11 项 + 单测会拦回潮；改执行器写行为要升版（现 **2.14.0**）。
- **交付门禁现在认三道**：快照内 `run_id` 必须是所选 Run、`doc_snapshot_sha` 能自洽重算、快照文件 sha 等于 `run.snapshot_sha`（迁移 4；新快照写时即封印，历史 Run 首次通过内容校验时补封印）。QA 撤销走 `audio.restore_license`/`restore_mix`（原样回退、不跑提交校验），残缺前置态也退得回去。
- **验收脚本不许打在演示项目上，也不许借演示的前置态**：`scripts/_acceptance.py` 的 `require_scratch_project()` 是 fail-closed——不给 `--project` 就拒绝启动，命中演示 id 或 `is_protected(name)` 也拒绝；**状态本身由 `scripts/_scratch_state.py` 自建**（`build_take_state` 真跑到 F04 出片两次、`build_audio_state`、`build_asset_state`、`build_template_source`、`build_review_source`），所以 `--build` 一条命令就能跑完整冒烟，不必再人工喂一个"已有 Take 的项目"。`_acceptance.destroy()` 收尾时会取消在飞作业、轮询删除闸门、并回收向导留下的 `draft` 行。守卫＝一键复核第 **14** 项 + `server/tests/unit/test_acceptance_pollution.py`（静态扫演示 id、写状态脚本必须有自建入口、豁免名单必须显式登记）。自建入口：`python scripts/_acceptance.py --create <name>`。
- **文档版本链保留 v1 + 最新 99 条**，`/docs/{kind}/versions` 输出 `truncated`/`keptFirst`；**异步失败由 `api()` 广播到全局 `ApiFailureBanner`**（`error.tsx` 抓不到 promise 拒绝），不想要弹窗的调用传 `silent: true`。

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
- **许可（2026-11-06 老板选定 MIT）**：顶层 `LICENSE` 只覆盖**本项目代码**；`vendor/fy-code-animation/`（免费使用/分享、禁止包装成付费课程或付费 skill 出售）、341 风格库（仓库外）、`rumor-39s` 参考片（仓库外）**不在 MIT 内**，各按自己条款——别把这些原文/示例 mp4 重新分发进公开仓库。ffmpeg/Chrome 是本机系统依赖，不构成分发传染。边界见 README「许可」。
- **a11y 棘轮（P2-15）**：`python3 scripts/lint_a11y.py` 断言 jsx-a11y warn 只许降不许涨（基线在 `docs/reports/lint-baseline.json` 的 `a11y` 段，2026-11-06 建立于 **60**）；配置在 `web/eslint.config.mjs`（规则全降为 warn，`noInlineConfig` 忽略历史内联指令）。为跑它新增了 3 个 devDependency：`eslint`、`eslint-plugin-jsx-a11y`、`typescript-eslint`（只装前两个会得到 9 个 `Definition for rule ... was not found`——tsx 需要 TS parser，且源码里存在 `@next/next/*`、`react-hooks/*` 的内联指令）。
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
黄金验收：**5s/15s/40s 原帧都已实跑**（15s run 334、40s run 336 各 6 帧 SSIM=1.000000、pHash 距离 0，当时 `EXECUTOR_VERSION` 是 2.12.0（现 2.14.0，升版后原帧锚已于 2026-11-05 复跑 SSIM=1.000000）；锚在 `fixtures/golden/*/baseline_original/`）；干净 rumor 46/46、master 39.5s（HANDOFF §2.6）。原帧锚是**同版本两次独立 Run**自洽，不是与外部母带比对。
NTSC 验收：`verify_r2_5_delivery.py --fps 23.976 --duration 2` → run 333 两画幅同 48 帧/2.0s、`qc` 全绿（40s NTSC 长片未跑）。
下一步：**判官 §六 未闭项（HANDOFF §0.0 清单）→ 才谈 FR-40/41**；不要开始 R4。详见 `HANDOFF.md` §0.0/§6.5。

## 先跑什么

> 专家整夜自主循环（goal 模式）的提示词：`docs/process/expert-overnight-goal-prompt.md`（先证伪交接声明，再按优先级补 P1/P2，每轮必须提交并留证据）。

```bash
./dev.sh
cd server && uv run pytest tests -q                       # 396 passed（collected 396 = unit 356 + integration 33 + BDD 7；2026-11-06 整夜 R2 两轮 200.1s/199.2s，dev 在跑也 0 skipped——A8 已去除 8787 门控）；foreign_keys=ON
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
uv run --project server python scripts/verify_p1_governance.py # ★ 一条命令复核本轮 17 项 P1 门禁
uv run --project server python scripts/e2e_error_visibility.py  # 异步失败必须可见（真机）
uv run --project server python scripts/e2e_timeline_100.py      # 100 场景有效重测（正向播放 + 真 ops/autosave）
uv run --project server python scripts/check_docs_consistency.py # 文档与代码/库/脚本一致性（改完必跑）
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
