# 专家夜以继日目标模式 Prompt（FilmFlow · 2026-11-03 交接后）

> 用法：整段作为 goal 提示给专家大模型（zcode goal 模式，不限轮次，整晚循环）。
> 工作目录：`/Users/litianyu/cc-projects/ai-v/filmflow`（master 已同步到 `git@github.com:leechunwoo0815/filmflow`，HEAD `b9ac7dc`）。

---

## GOAL（唯一目标）

把 FilmFlow 从"功能全绿但过程可能有雷"推进到**可被第三方独立审计的成品**：
你接手 `HANDOFF.md` 声称的一切，**逐项亲自证伪或证实**，把证实不了的当成 bug 修掉；
补完 §6.5 剩余的 P1 治理项与高优先 P2；对我不信任的地方优先做对抗性挖掘。
不要相信交接文档里的任何一句话——**以代码、产物、命令输出为准**。

## 收敛判据（"完美"的操作化定义，全部满足才允许停）

1. **证伪清单归零**：`docs/process/expert-runlog.md` 里每一条 `UNVERIFIED` / `FALSE-CLAIM` 都被
   关闭（修好或按事实改文档），没有遗留。
2. **连续两轮对抗性审计无新增 P0/P1 级发现**（同一轮内新增发现 >0 就继续下一轮，并重新计时轮次）。
3. `cd server && uv run pytest tests -q` 连跑两次全绿且两次 `GET /api/projects` 计数一致（当前基线 189 项 / 35 项目）。
4. `uv run --project server python scripts/verify_p1_governance.py` 8 步全 ✓。
5. §0.2 列出的所有验收脚本在**当前代码**下各跑通一次，输出摘要 + 产物路径 + sha 落到 runlog；
   明确跳过项必须写"为什么跳过 + 影响面 + 复现命令"，不许留空。
6. 每个改动批次满足 **DoD**：代码 + 测试 + 真实产物证据 + 文档（HANDOFF/AGENTS/r3_plan）同步 + 单独提交。
7. 最后一次 `pnpm --dir web exec tsc --noEmit` 干净；`uv run --project server ruff check server`
   的 error 数比基线 **504**（2026-11-03 实测：187 个可 `--fix`、86 个需 `--unsafe-fixes`）下降，
   并把下降数字与新剩余数写进 runlog。

不达判据不要停；达到了就写"最终报告"收尾，不要无限加戏。

## 第一步（必须按顺序做完再开工）

1. 读 `AGENTS.md` → `HANDOFF.md` §0（§0.5 审查结论、§0.6 状态表、§0.6.1 破坏性语义、§0.6.2 没做的事、
   §0.6.3 一键复核、§0.7 运维坑）→ §5 踩坑清单 → §6.5 剩余项 → §9 已知限制。
2. 再读 `docs/reviews/2026-11-03-expert-review-analysis.md`（344 行，脱敏复核）与
   `docs/prd/PRD-002-production-workbench.md`、ADR-0005/0007/0008/0009/0010/0011/0012。
3. 起服务并跑基线（这是你的"上帝视角快照"）：
   ```bash
   cd /Users/litianyu/cc-projects/ai-v/filmflow
   pkill -f 'dev.sh'; lsof -nP -iTCP:7860 -iTCP:3000 -sTCP:LISTEN -t | xargs kill; sleep 3
   nohup ./dev.sh > /tmp/ff-dev.log 2>&1 & sleep 14
   curl -s http://127.0.0.1:7860/api/health
   cd server && uv run pytest tests -q          # 期望 189 passed
   cd .. && uv run --project server python scripts/verify_p1_governance.py   # 期望 8 步 ✓
   ```
   `./dev.sh` **不带 --reload**：改完 Python 必须按上面配方重启，否则你验的是旧代码。
4. 备份一次工作数据库并在 runlog 记录路径：
   `cp ~/.filmflow/filmflow.db ~/.filmflow/filmflow-before-expert-$(date +%Y%m%d-%H%M%S).db`

## 证伪阶段（先做，别急着写新功能）

对下面每一条，你要**亲手构造反例或复跑证据**，结论写进 runlog（`CONFIRMED` / `FALSE-CLAIM` / `UNVERIFIED`）：

- **本轮 P1 修复的可信度**（这是最可疑的部分，因为我也是人）：
  - 交付门禁：找或造一个"Run 之后改文案"的项目，确认交付真的被 `E_DELIVERY_GATE` 拦；
    再确认一致态能放行。攻击点：只比 timeline 没比 script/profile/caps、快照缺失时静默跳过、
    `imported` 分支绕过、比的是内存 dict 还是持久化后的内容。
  - 许可门禁：过期/空字段/大小写/纯空格/非 ISO 日期；`PATCH` 绕过（部分更新、嵌套字段、
    先清空再引用）；`update_asset` 只查"被引用"是否可被"取消引用后清空再挂回去"洗白；
    `rights.json` 里资产与真实画面是否一致（模板引用、Run 快照与实际帧）。
  - QA 撤销链：三步以上 LIFO、跨 timeline/profile/mix/license 混合撤销、撤销后再修复、
    `undo` 与手工编辑交错的竞态；深拷贝是否在所有路径都生效（`set_lufs`/`fill_license` 分支）。
  - 资产引用面：`walk_refs` 对深层嵌套/`assetShas` 去重是否会漏（数组里套对象、`fontSha` 在场景外、
    Run 快照文件损坏/半写）；大项目扫描的耗时（列出退化数字）。
  - 请求模型：422 之外是否改变了合法请求的行为（字段别名 `baseVersion`/`base_version`、
    多态 `timeline/ops` 的 extra 透传、默认值与服务层不一致导致静默行为变化）。
  - 迁移登记处：`MIGRATIONS` 与既有 DB 版本冲突、迁移抛错后的半应用状态、启动顺序与 `create_all` 竞态。
  - 档位验收口径：SSIM 分窗口的阈值是"合理放宽"还是"藏问题"——独立测一次同刻
    preview vs final 在切点/入场动画的真实差异，给出你自己的判断和建议阈值。
- **交接文档里我自己标注的边界**：40s 增量未实跑、15s/40s 原帧 golden 未生成、
  `foreign_keys` 未开、P1-09/10/11/12/21 未做、P1-19 只迁了 1 个脚本、P1-23 只做了 9/51。
- **老交付证据**（`docs/reports/**`、`fixtures/golden/**`）：随便抽 3 份，按报告里的 run 号
  重跑或核对产物 hash，验证"证据没被事后改写"。

## 建设阶段（按优先级，每项走完 DoD 再进下一项）

1. **P1-12 非整数 fps**：先写一个失败测试（23.976/25/30 下帧网格、时长、SRT、增量 range 漂移），
   再统一定点/取整口径（建议单一 `frames_for(duration, fps)` 工具函数）；**必须升 `EXECUTOR_VERSION`**
   并重跑 `golden_run.py --project 5s --resolution original` + `verify_r2_profiles.py`。
2. **P1-09 多步写事务**：对 `templates._materialize_first`、`takes` branch/adopt、`assets` replace、
   `qa` extend_scene（已有补偿）做**故障注入测试**（第二次 commit / 写文件抛错），断言不留半成品；
   再决定事务边界或补偿策略。
3. **P1-06 收尾**：先补级联/删除顺序（含 `projectdoc/docrevision/run/noderun/artifact/metric/approval`
   与磁盘目录），加"删项目"服务函数（并给 `DELETE /projects/{id}` 端点，带白名单与确认位），
   然后才开 `foreign_keys=ON`；把 `_acceptance.py` 的清理改走该服务函数。
4. **P1-19 全部验收脚本自包含**：`e2e_takes/e2e_assets/verify_r3_assets/verify_r3_templates/`
   `verify_r3_camera/verify_r3_takes/verify_r3_audio_v2/verify_rumor_regression` 迁到
   `scripts/_acceptance.py`（或给 `--project` 参数并默认自建），跑完 DB 计数必须回到初始值；
   大产物跑完自动清 `out/frames`、`out/proxy`。
5. **P1-10 / P1-11 前端**：`error.tsx` + `global-error.tsx` + 裸 `.then()` 补 catch；
   先做 100 场景/60fps 的真实测量（Playwright 计时 + 长任务记录），有数据再决定虚拟化。
6. **P1-23 剩余 42 个 `payload: dict`**：按危险度排序（写文件/删数据/触发作业优先），
   每组一批提交；模型化后必须跑 integration（内部直接函数调用是坑，见 §0.6.1 第 6 条）。
7. **P2 高优先簇**（35 条见分析文档 §2.3）：媒体一致性（P2-10 QC 硬编码 24fps、P2-12 响度/色彩/码率、
   P2-13 转场期文字淡出、P2-14 相机 anchor/ease、P2-35 字体 CSS 优先级）→ 缓存正确性（P2-01/03/06）→
   数据完整性（P2-07/08/09）→ 可观测性（P2-28 服务级日志、P2-26 CI）。
8. **P3（26 条）**：只挑安全/数据正确性相关（`/api/artifacts/{id}/file` 白名单、SVG 上传 + CSP/nosniff、
   500MB base64 内存放大、Chrome profile 可预测/CDP 9222、Asset 绝对路径）；其余留清单。
9. **磁盘/DB 残留**：**不要自行删除** project 228–245 等审计残留（老板未点头）。你要做的是
   写一个 `scripts/cleanup_projects.py --dry-run`（默认只报告，需 `--confirm` + 引用面检查才真删），
   并在 runlog 给出建议清单。

## 硬约束（违反任何一条即判失败）

- 仅 `127.0.0.1`；不上传任何文件；**不调用任何在线生成模型**；不引入需要联网构建的依赖。
- 所有文件操作必须在登记的项目根白名单内（`FILMFLOW_WORKSPACE_ROOTS`）；禁止任意 shell / 路径穿越；
  不要新增能执行外部命令的端点。
- 46 节点 / 7 阶段 / 93 边 / 8+8 门 / caps / 三类边 / `content_hash` 语义不变；新能力只走节点内部子流程。
- 改执行器行为**必须升 `EXECUTOR_VERSION`**（当前 2.9.3），否则缓存返回旧行为；改预览渲染升 `RENDERER_VER`（当前 preview-1.8.0）。
- Chrome 全局串行 1 个、ffmpeg 独占：不要并行跑两个渲染类任务。
- 不要把 341 风格库（约 75MiB）或 `rumor-39s` 产物提交进 git；不要把密钥/本机绝对路径/局域网信息写进仓库
  （公开仓库只放脱敏内容；原始专家报告 `~/.filmflow/reviews/2026-11-03-expert-review.raw.md` 保持本地）。
- **不做 R4**（多规格矩阵 / 平台发布 / 批量 CSV / photo 引擎），不动已完成 FR 的实现方向。

## 反作弊与诚实条款（这条比代码重要）

- **禁止为通过而降低阈值**：不许改断言常量、不许 skip、不许把窗口/容差悄悄放大。要放宽必须写出理由 +
  影响面 + 单测覆盖，并在 runlog 标 `THRESHOLD-CHANGE`。
- **禁止把"没跑"写成"通过"**：每个申报必须带命令、输出片段、产物路径与 sha 或 UI 截图。
- **文档以代码为准**：发现 `HANDOFF.md`/`AGENTS.md` 的声明与代码不符，先复现，再改文档，并在 runlog
  记录"原文说 X / 实测 Y / 处置 Z"。已知的两处口径先复核：档位 SSIM 的 run 号（应为 309）与
  draft/final 分窗口阈值（稳定段 0.98 / 切点与入场 0.5s 窗口 0.90，实测最低 0.952097）。
- 破坏性操作（删库/删项目/`git reset --hard`/`force push`/改历史）一律**不做**，改为写进 runlog 的建议。
- 遇到需要产品/范围决策的问题（要不要开 token 鉴权、要不要清 DB、阈值定多严），写进
  `docs/process/expert-open-questions.md` 并继续做不受阻塞的部分，**不要停下等人**。

## 每轮循环协议（一整晚就按这个跑）

```
选 1 个最高优先项（或 1 组同类小项）
 → 先写能失败/能证伪的测试或探针脚本
 → 实现最小闭环（不顺手重构无关代码）
 → 跑：目标测试 → 全量 pytest → 相关验收脚本 → tsc（若动 web）
 → 需要真实渲染的，先跑 5s，再评估是否值得跑 15s/40s（磁盘！跑完清 frames/proxy）
 → 更新 HANDOFF/AGENTS/r3_plan + docs/reports 归档
 → 单独提交（fix|feat|test|docs(scope): 中文一句话 + 为什么）+ push
 → 在 runlog 追加一条：时间 / 动作 / 证据 / 下一步 / 遗留风险
 → 回到开头
```
每完成 3 个批次，做一次"回看"：重跑 §0.6.3 一键复核 + 全量测试，确认没有互相踩踏；
若发现回归，先修回归再继续。

## 收尾产物（凌晨必须留下这些）

1. `docs/process/expert-runlog.md`：整晚的时间线（每条带证据），含未关闭项与建议下一步。
2. `docs/process/expert-final-report.md`：收敛判据 7 条逐条自检（附命令输出摘要）、
   本轮新增能力/修复缺陷清单、剩余风险 TOP10（含你判断的严重度）、以及"如果只有半天，先做什么"。
3. 最后一次 `git log --oneline` 尾部批次 + 测试计数 + `verify_p1_governance.py` 输出，作为快照签名。

现在开始：先跑"第一步"的基线，然后进入证伪阶段。不要问我，不要等确认，按优先级推进直到收敛判据全部满足。
