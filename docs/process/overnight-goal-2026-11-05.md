# FilmFlow 整夜自主开发任务书（2026-11-05 夜 → 11-06 晨）

> 收件人：开发大模型（zcode goal 模式，几十轮自主循环）。
> 发件人：审查方（明天早上会做**端到端极限复审**，逐条复跑你申报的每个数字）。
> 目标：**把下面 Wave A–G 的全部任务做完**，不是"做多少算多少"。做不完的必须写清"为什么没做完 + 还差哪一步"，
> 不许沉默、不许把未跑的写成已跑。
> 前置阅读（必读，别跳）：[`docs/process/handoff-prompt-b9.md`](handoff-prompt-b9.md)（硬约束/坑/文件索引）、
> [`HANDOFF.md`](../../HANDOFF.md) §0.0/§0.4/§0.7/§6.5/§7.3/§7.4、[`AGENTS.md`](../../AGENTS.md) 门禁清单、
> [`docs/reviews/2026-11-03-expert-review-analysis.md`](../reviews/2026-11-03-expert-review-analysis.md)（专家账本原文）、
> [`docs/process/b9-close-report.md`](b9-close-report.md)（前两夜执行报告 + §9 勘误）、
> [`docs/prd/PRD-002-production-workbench.md`](../prd/PRD-002-production-workbench.md) §FR-40/FR-41（原文验收）。

---

## 0. 完成定义（DoD）——明早我按这个验，逐条复跑

一轮工作算"完成"当且仅当**全部**成立：

1. `cd server && uv run pytest tests -q` 全绿，**连跑两次**数字一致，且 0 skipped / 0 xfailed（有就必须写明理由）；
   跑完生产库计数不变（`conftest` 的守卫会自动判）。
2. `uv run --project server python scripts/verify_p1_governance.py` → 全项 ✓（**现值 18 项**：H3 加了第 18 项磁盘/库卫生棘轮；你再加守卫就更多）。
3. `uv run --project server python scripts/check_docs_consistency.py` → PASS。
4. `cd web && npx tsc --noEmit` 干净；`cd server && uv run ruff check .` **不高于 339**、仓库根 `uv run --project server ruff check .` **不高于 405**（只许降）。
5. 每个 Wave 的每条任务都有：**代码落点（file:line）+ 可复现实测输出 + 提交哈希**，写进台账 `docs/process/overnight-ledger-2026-11-05.md`（格式见 §6）。
6. 涉及渲染的改动，必须有**真渲染证据**（golden 或验收脚本实跑输出），不能只有单测。
7. 工作树干净、每轮一个提交（不许攒成一坨）、**不 push**（push 是老板的决策点，见 §7）。

**判定口径**：我明天会随机抽 10 条你申报的"已完成"，逐条复跑原始命令。复现不出来＝整批判为不可信。
所以：**每个数字都写上产生它的完整命令与 cwd**（ruff 的 353/424 之争就是 cwd 口径没写清造成的）。

---

## 1. 硬约束（违反任意一条即算失败）

- 仅本机 `127.0.0.1`；不上传文件；**不调用任何在线生成模型**；不新增联网点（现有唯一联网点是 C02 字体下载，已加 sha 钉，别再开第二个）。
- 文件操作只在已登记项目根白名单内；禁止任意 shell / 路径穿越；全仓不许 `shell=True`。
- **Chrome 全局串行 1 个**、ffmpeg 独占 → 任何两个渲染级验证**不许并行**（包括 pytest 与验收脚本同时跑）。
- 46 节点 / 7 阶段 / 93 边 / 8+8 门 / 7 caps / 三类边 / `content_hash` 语义**不变**；新能力走节点内部子流程。
- 改执行器行为**必须升 `EXECUTOR_VERSION`**（现 2.16.0）；改预览渲染器升 `RENDERER_VER`（现 preview-2.0.0）。
  升版后必须用 `golden_run.py --project 5s --resolution original` 复跑证明视觉未变（SSIM=1.000000）。
- 落盘一律 `atomicwrite.write_atomic`；文件响应一律 `security.file_response`；本地 httpx 客户端一律 `trust_env=False`（这三条都有守卫，回潮会红）。
- **演示/保护项目绝不动**：现存 11 个项目全部是演示或参考片（`rumor-39s`/`trace`/`rumor-clean-20261102`/`r2_5-audio`/
  `r2_5-delivery40`(174)/`r3-camera`(188)/`r3-demo-20261103`(202)/`r2_5-delivery`(206/215)/`r3-audio-v2`(211)/`FR37 模板演示`(227)）。
  验收只允许打自建 scratch 项目（`scripts/_acceptance.py` fail-closed，`scripts/_scratch_state.py` 自建前置态，用完自删）。
- 手工探针纪律：`TestClient(app)` 连的是**生产库**，只有必然被 422/400 挡在 handler 之前的请求可以用它；会写的一律走 scratch 项目或独立 `FILMFLOW_HOME`。
- 破坏性库写（删项目/删 draft/改 job 状态）：**先备份 `cp ~/.filmflow/filmflow.db ~/filmflow-backup-<stamp>.db`，删前确认无在飞作业，删后出计数对照**，并写进台账。
- 不许为了让测试变绿而**放宽断言/删测试/加 skip/加 xfail**。确有必要（例如上游行为变化）必须在台账里写明理由并给出证据。
- 文档里 `N passed`、版本号、DB 计数只写**当前实测**；历史值写中文描述。改完必跑文档守卫。
- git：一轮一个提交；不 `--amend` 已推送的提交；不 `--no-verify`；不 force push；**不 push**（除非 §7 的决策点被老板批准）。
- 不要把 341 风格库或 `vendor/fy-code-animation` 提交进 git / 加进 Python 包路径。

---

## 2. 环境与第一小时

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
git log --oneline -6 && git status --porcelain          # 应为 clean，HEAD=df5fbbb 或其后
./dev.sh                                                # 用工具的后台执行方式启动；别 nohup + 退出 shell（会被回收）
curl -s http://127.0.0.1:7860/api/health
cd server && uv run pytest tests -q                     # 基线：364 passed（0 skip 0 xfail；A8 已去除 8787 门控，dev 在跑同样 0 skip）
uv run --project server python scripts/verify_p1_governance.py    # 基线：16 项全 ✓
uv run --project server python scripts/check_docs_consistency.py  # 基线：PASS
```

**基线数字（2026-11-05 深夜，审查方实测/复核）**：
- pytest **396 collected**（unit 356 / integration 33 / BDD 7；361→364 是 A5 把污染闸门测试按 DEMO_PROJECTS 现网 11 项目重新参数化 +3）；整夜 R2 **364 passed ×2**（189.8s / 185.9s，0 skip 0 xfail，dev 在跑）。
- 治理 **17 项全 ✓**（第 17 项＝A3 lint 棘轮）；文档守卫 **PASS**（EXECUTOR=2.16.0 · 迁移 [1,2,3,4,5] · DB=11 项目 · 裸 dict 写端点 0）。
- ruff：**339**（`cd server` 口径）/ **405**（仓库根口径）——已入棘轮（治理第 17 项 + `docs/reports/lint-baseline.json`：BLE001 65/75、S110 1/1、F821 0，**只许降不许涨**）。
- DB：11 项目 / 47 draft（僵尸 0）/ 44 run / `retry_wait` **7** 条（整夜交接时是 12，其中 5 条已在深夜 dev 重启时按 72h 心跳被 `jobs.expire_parked` 自然收走——策略按设计工作，这正是 A7 要真实演练的机制；剩余 7 条全属 rumor-39s 与演示 188，是"等人工门"的正常态，**不许删**）；磁盘 1.6G；`~/.filmflow` 1.5G；自动备份 `filmflow-auto-20261105.db` 33.4MB。
- **25 个提交在本地未推送**（`origin/master` 停在 `8266f11`；此后一律以 `git rev-list --count origin/master..HEAD` 实时值为准）。
- 已知环境陷阱：本机 shell/dev 进程带 `NO_PROXY=…,[::1],::1`；全仓 httpx 客户端已补 `trust_env=False`（`dab7fe4`），
  回归测试 `server/tests/unit/test_f01_http_env.py`（含毒环境对照组）。**别再引入裸 httpx 客户端。**

---

## 3. Wave A —— 审查新发现的收口（先做，1–2 小时）

| # | 任务 | 落点 | 验收判据（我会复跑） |
|---|---|---|---|
| A1 | **黄金报告不再被覆写**：清库后 run id 会回落，`5s-original-run336.json` 已被 11-05 23:37 那次重跑**覆盖**（11-04 15:56 的原件没了）——证据可混淆 | `scripts/golden_run.py` 的 `--archive` 段（`REPORT_DIR / f"{project}-{resolution}-run{rid}.json"`） | 文件名带 UTC 时间戳（`{project}-{resolution}-run{rid}-{YYYYMMDDTHHMMSSZ}.json`）；已存在同名文件时**不覆写**；新增/维护 `docs/reports/golden/index.json`（每条：project/resolution/runId/at/executorVersion/ssim 最小值/status/reportFile）；用 `--project 5s --resolution original` 实跑一次，证明旧文件仍在、index 有两行 |
| A2 | **帧服务 token 从 query 挪到 header**：`?tok=` 会进访问日志/浏览器历史（P2-32 遗留） | `pipeline.py:160`（复用探针）、`:233/:234`（`_engine_url`）、`:301`（`_project_url`）、`FrameServer._needs_token/_authorized`（:61-96）、引擎侧发帧的 JS（`engines/riso/**`，POST `/frame`、`/pframe`、`/done`） | 数据面全部改 header（`X-FilmFlow-Token`）；引擎 JS 的 fetch 带 header；**真渲染复验**：golden 5s 原帧 SSIM=1.000000 ×6 + `verify_r3_camera` PASS（P2-32 那次教训：长命 Chrome 缓存页/旧 cookie 会 403 成黑帧，必须实跑证明没复发）；访问日志里不再出现 token（给一条 `grep -c tok= ~/.filmflow/logs/app.log` 类证据） |
| A3 | **BLE001 棘轮**：盲捕从 72 涨到 75，无人看守 | `scripts/verify_p1_governance.py`（新增第 17 项）或落一份 `docs/reports/lint-baseline.json` | 守卫读基线并断言（**仓库根口径**，`uv run --project server ruff check .`）`BLE001 <= 75`（现值 75；`cd server` 口径 65）、`S110 <= 1`、`F821 == 0`、总数 `<= 339/405`；超了即红；把当前值写进基线文件并提交 |
| A4 | **`_PROJECT_RUN_LOCKS` 无限增长**（按项目根累积，进程内） | `server/app/engine/runengine.py:684+` | Run 进入终态或项目删除时 `pop`；单测：造 3 个 Run 跑完后字典为空；`delete_project` 路径也清 |
| A5 | **守卫名单与现网脱节**：`_acceptance.DEMO_PROJECTS` 仍列 216/223（已删）、`project_cleanup._PROTECTED_NAMES` 仍含 `golden-5s`（已无该项目） | `scripts/_acceptance.py:152-154`、`server/app/services/project_cleanup.py:25-28` | 二选一并写理由：①清理已不存在的 id/name；②保留为"历史守卫"并在代码注释 + HANDOFF §7.4 注明。**同步 HANDOFF §7.4 的演示项目清单**（现网只有 11 个，逐个列出） |
| A6 | **`params_snapshot` 现网全空**（实测 0 行非空）→ 交付门禁那条形同虚设 | `routes.py` 的 `POST /runs`（`Run(params_snapshot=payload.params)`）、`delivery.py:378-383` | 二选一并给证据：①让 UI/脚本真的传 params（`web/src/app/canvas/page.tsx` 的 run 创建处 + `_scratch_state`），并造一条非空快照跑通门禁；②明确"空即跳过"并加单测钉住该语义 + 在 HANDOFF 写清"这条门禁现网不生效"。**不许沉默** |
| A7 | **`retry_wait` 回收策略只有单测，没有真实演练** | `server/app/services/jobs.py::expire_parked` | 在 scratch 项目上造一个 parked 作业（跑到门上 → park），把它的心跳改老（直接 SQL 或用小阈值调用），实跑 `expire_parked` 证明收成 `canceled/E_JOB_EXPIRED`，再证明签门后 `start_run` 能重建作业；输出贴台账。**不要动生产库那 7 条**（整夜交接时 12 条，5 条已被 `expire_parked` 按策略自然收走——A7 要在 scratch 项目上把这个机制再演练一遍并留证据） |
| A8 | **`test_p1_foundations.py:234` 的 8787 skip 门控**：帧服务端口已可配置，这个 skip 应该能去掉 | `server/tests/unit/test_p1_foundations.py` | 改用动态端口后删除该 skip；两次全量跑都 0 skipped（若仍必须保留，写清为什么） |

---

## 4. Wave B —— 专家账本剩余（P2 七条 + P1 两条半闭）

> 逐条都要"代码 + 测试 + 实测输出"。渲染类的必须真跑（Chrome 串行，别并行）。

| # | 任务 | 落点（审查方已定位） | 验收判据 |
|---|---|---|---|
| B1 | **P2-08** JSON 侧 load-modify-save 无锁（原子写≠防丢更新） | `services/review_comments.py:33/54`、`services/takes.py:22/35` | 加 CAS（读时记 hash/mtime，写时不符即 409 `E_DOC_CONFLICT` 同款语义）或文件锁；测试：**真并行**两客户端写同一文件，断言两侧都看到冲突且内容不丢（不许用顺序模拟） |
| B2 | **P2-12** 音频簇：单遍 loudnorm、无色彩标签、码率 | `services/audio.py:307`、`executors/pipeline.py:1329/:1332`（loudnorm）、`pipeline.py:1141`（`-crf`） | 两遍 loudnorm（先 measure 再 apply）；成片打 `bt709`/colorspace tags；验收：`verify_r3_audio_v2` 实跑 PASS 且 LUFS 更接近目标（现 -13.8 vs -14.0）、`ffprobe` 输出里能看到 color tags（贴原文） |
| B3 | **P2-13** 转场期文字淡出（text out fade 固定 `duration-0.4`，与转场无关） | `engine/scene/compiler.py:144` | 与转场窗口协同（转场期间文字不该先消失）；**必须建逐帧 SSIM harness**：转场窗口内取 N 帧，对比修改前后，给出"文字可见性"量化证据（不许只靠肉眼看一张图） |
| B4 | **P2-15** a11y 近零（全前端 `aria-*`/`role` 仅 **1** 处） | `web/src/app/**`（时间轴/播放器/资产库/QA/交付）+ 新建的命令面板与通知中心 | 关键交互全部有 `role`/`aria-*`/键盘可达；验收：写一条**纯键盘** e2e（与 FR-40 验收共用），并给出 `grep -ro "aria-[a-z]*\|role=\"" web/src --include="*.tsx" \| wc -l` 的前后数字（现值 1）。引入 `eslint-plugin-jsx-a11y` 前**先问老板**（新增 devDependency） |
| B5 | **P2-17** 资产删除无在飞守卫、无孤儿 GC | `services/assets.py:486`（`delete_asset`）、`api/routes.py:1756`（`DELETE /assets/{id}`） | 删除前查在飞作业（复用 `project_cleanup._job_is_live` 口径）；新增 `scripts/cleanup_assets.py`（默认只报告孤儿资产/无引用文件，`--confirm` 才删，前后出计数）；实跑报告模式并贴输出 |
| B6 | **P2-25** BDD 17 个 `.feature` 只有 2 个绑定 | **仓库根** `bdd/features/`（17 个文件）；绑定在 `server/tests/bdd/test_style_indexing_bdd.py` 与 `test_r2_workbench_bdd.py` | 二选一并写理由：①再绑 ≥8 个（真步骤实现，不许空壳）；②裁剪死规格并在 `docs/adr/` 写一份 ADR 记录"为什么这些规格不再执行"。**不许继续沉默** |
| B7 | **P2-26** e2e 固定 `wait_for_timeout`（`scripts/e2e_ui.py` 10 处，:23–:142，300–5000ms） | `scripts/e2e_*.py` | 改条件等待（`wait_for_selector`/`expect`/轮询 API）；给出前后 e2e 总耗时对比（`e2e_ui.py` 现约 15s） |
| B8 | **P1-20 CI 从未真跑**（23 个提交未 push，Actions 0 次执行） | `.github/workflows/ci.yml` | 若老板批准 push → 首跑必须绿，红了当场修；若不批 → 落一份 `scripts/ci_local.sh` 跑 CI 的同样四步（ruff / unit+BDD / tsc / 文档守卫），实跑并贴输出，作为"CI 语义已验证"的替代证据 |
| B9 | **P1-21 fresh-clone 未实测** | `scripts/bootstrap_fresh_clone.sh` | 在 `/tmp/filmflow-fresh-$$` 真跑：`git clone` 本地仓库 → 执行 bootstrap → 跑 `pytest -m "not slow"` + 文档守卫；把每一步输出贴台账；失败就修脚本，别改判据 |

---

## 5. Wave C —— 专家 §7 仍漏的测试（7 条，补齐或写明为何不补）

1. `_safe_join` **符号链接**用例（`server/tests` 里 `symlink` 命中数现在是 **0**）：造 symlink 指向白名单外，断言被拒。
2. **无体 POST 的鉴权**：若做 token 层（P0-1 可选第 3 层）就测；不做就在 HANDOFF 写清"不做 + 理由"。
3. **并发双客户端真并行保存同一文档**（不是顺序模拟）：断言两侧都看到 409 且本地内容不丢（与 B1 呼应，文档侧）。
4. **截断 PNG + `exists()` 续跑**：造半张帧，断言 F02 重脏而不是无限失败/黑帧。
5. **损坏资产 fixture**：截断 PNG / 非法 TTF / 0 字节 WAV / 伪装 SVG（内容是 HTML）→ 导入与渲染必须优雅降级并给可诊断错误（不许 500）。
6. **delivery 幂等并发实测**：`delivery.py:663` 已有守卫，补一个真并发两请求的测试，断言只有一个 job。
7. **QA 统计口径**：合成含 `failed` / `verified=False` 的数据，断言 `failed`/`successRate`/`verificationRate` 计数与比率（代码改了，测试仍是 0）。

---

## 6. Wave D —— P3 26 条：逐条判定，不许沉默

对 [`docs/reviews/2026-11-03-expert-review-analysis.md`](../reviews/2026-11-03-expert-review-analysis.md) §2.3 的 P3 清单，
**逐条**给判定：`修（附提交）` / `不修（附理由）` / `需要老板决策`。至少这些要给出实质处理或明确理由：

- 仓库**无 LICENSE**（老板决策项：选许可类型；未决前不要自己加）
- `server/app/api/routes.py` 已 **2764** 行 → 拆分方案（按域拆 router，保持路径与守卫不变；反射守卫必须仍覆盖全部写端点）
- 500MB base64 内存放大（音频/资产上传）→ 分块或落盘流式
- CDP 9222 可预测端口 + 可预测 Chrome profile → 随机化（注意 `preview.py:400/441`）
- `list_assets` O(项目×场景) 复杂度
- 模板变量缺失不阻断
- `qa.analyze` 重复执行/阻塞
- 前端轮询 → SSE（`/runs/{id}/events` 已有 SSE 通道）
- aware UTC 落库变 naive
- DB freelist 从未 VACUUM（现值实测后决定；VACUUM 属破坏性维护，先备份）
- `.DS_Store`（现网 `git ls-files` 命中 0，确认并加 `.gitignore` 兜底）
- 帧数计算散布（已统一到 `fpscalc`，确认无残留）

---

## 7. Wave E/F —— FR-40 与 FR-41（老板已点头，前置已满足）

> 原文验收在 PRD-002 §FR-40（第 912-928 行）/ §FR-41（第 932-950 行）。**按原文验收逐条打勾**，别自创判据。

### FR-40 命令面板 / 快捷键 / 通知（P1 / R3.5）
- `Cmd/Ctrl+K` 命令面板：跳转、运行、预览、批准、导出、切换档位、搜索场景/资产。
- 全局快捷键表：可自定义、冲突检测、`?` 查看。
- 通知中心：渲染完成/失败/门待批/许可到期/磁盘不足；点击跳转；不重复、可标记已读、失败带修复入口。
- 进度中心：所有 job 的进度/ETA/取消；后台运行不阻塞编辑。
- 离线可用；无推送、无邮件。
- **验收（原文三条，必须有证据）**：① 20 个核心命令可在面板搜到并执行；② **全流程纯键盘**（建项目→改→预览→跑→批门→导出）；③ 通知不重复/可已读/失败带修复入口。
- **证据形式**：新增 `scripts/e2e_fr40_keyboard.py`（系统 Chrome + **键盘输入**，React 19 的 `fill()` 不触发 onChange），
  真跑并贴逐步输出；命令清单与快捷键表落 `web/src/lib/commands.ts`（或等价）并可被测试枚举；
  通知去重/已读要既有单测也有 e2e 断言。后端若新增端点：**必须 Pydantic 请求模型**（反射守卫会拦裸 dict）。

### FR-41 本地规则式创作辅助（P1 / R3.5）
- 断句 / 场景建议（4–6 场，给理由）/ 组件建议（关键词→组件，给匹配词）/ 镜头建议（2–3 预设，不自动应用）/ 读时校验（建议时长 + 最短可读）/ 规则表可导出 / 建议以**草稿层**呈现，接受才写入、拒绝不留痕。
- **不生成内容、不联网、不写文案**；建议必须可解释、可拒绝。
- **验收（原文四条）**：① 粘贴 300 字 → **1s 内**给 4–6 场景建议 + 每场理由（要有计时证据）；② 每条可接受/拒绝/编辑，接受后只影响对应场景；③ 断网可用、进程无外部请求（给证据：单测断言无 socket / `lsof -i` 快照 / 代码审计三选一并说明）；④ 建议不改原文、只改结构（给 diff 证据）。
- **落点建议**：`server/app/services/authoring.py`（新）+ `/projects/{id}/suggest/*` 端点（Pydantic 模型）+ `web/src/app/editor` 或新页；规则表导出到项目 `card/authoring-rules.json`（走 `write_atomic`）。
- **口径纪律**：读时/语速必须复用 `timeline_ops.READ_CPS=5.2` 与 `engine/fpscalc`，**不许另立口径**；场景建议要能直接喂给 `build_timeline_doc` 而不产生 `E_SCENE_READ_OVERFLOW`。

---

## 8. Wave G —— 决策点（需要老板一个字批准，别自己决定）

1. **push**：23（届时更多）个本地提交推到 `git@github.com:leechunwoo0815/filmflow`。push 后 CI 首跑必须盯到绿。
2. **LICENSE 类型**（Wave D 第 1 条）。
3. **新增 devDependency**（如 `eslint-plugin-jsx-a11y`）。
4. **任何超出 §3–§7 范围的破坏性库写**（例如动那 7 条 `retry_wait`、VACUUM、删演示项目）。
5. **偏离规格端口/不变量**（`:7860`/`:3000`/`:8787` 语义、46/93/8+8/caps）。

未获批准前：把这些写进台账"待决策"段，继续做其它任务，不要停机等答复。

---

## 9. 每轮固定动作（goal 模式节奏）

每轮（一次任务或一组强相关任务）都走这个闭环，别攒批：

1. 读台账最后一条，确认接着做什么（按 Wave A → B → C → D → E/F 顺序；同 Wave 内按编号）。
2. 改代码 + 补测试。
3. 跑：受影响的最小测试集 → `cd server && uv run pytest tests -q`（渲染级改动另跑对应验收脚本）→ 治理 → 文档守卫 → ruff（两个 cwd 口径）→ tsc。
4. 文档同步（HANDOFF §0.0 实测行 / AGENTS 进度行 / 相关 §）。
5. **一个提交**，message 写清"修的是账本哪一条 + 关键证据数字"。
6. 追加台账 `docs/process/overnight-ledger-2026-11-05.md`：

```
### 轮 N · <Wave-X 编号> <标题> · <时间>
改了什么：<file:line> ×若干
实测：<完整命令（含 cwd）> → <关键输出/数字，贴原文片段>
真渲染证据：<有/无；有则给 run id + 报告路径>
没验的：<明确列出，或写"无">
提交：<hash> <message 首行>
遗留/待决策：<无 或 具体项>
```

7. 若一轮失败两次以上：停下，把失败现场（命令 + 完整错误 + 已排除的假设）写进台账，转下一条任务，**不要反复硬试**。

---

## 10. 明早审查方会怎么验（提前告诉你，别抱侥幸）

- 随机抽 10 条"已完成"，**逐条复跑你写的原始命令**（含 cwd 与环境）；复现不出＝该条判虚报。
- 复跑：`pytest tests -q` ×2、`verify_p1_governance.py`、`check_docs_consistency.py`、`ruff`（两口径）、`tsc`、
  `git log origin/master..HEAD | wc -l`、DB 计数（project/draft/run/job）、`du -sh` 磁盘、演示 docrevision（174=3/188=28/211=37/227=58 必须不变）。
- 检查台账是否**每轮都有**、是否有"没验的"诚实标注、是否有提交与之一一对应。
- 检查有没有**为了让测试变绿而放宽断言/删测试/加 skip**（我会 diff 测试文件）。
- 检查有没有新增联网点、新增裸 httpx 客户端、裸 `write_text/write_bytes`、裸 `FileResponse`、裸 `payload: dict`（四条都有守卫，但我会再扫一遍）。
- FR-40/41 按 PRD 原文验收逐条打勾，缺一条就算未完成。

**最后一句**：宁可少报，不可虚报。前两夜因为"数字没标环境边界"和"文档说闭了实测没闭"被逐条打回过；
这一夜的产出会被同等强度复核。做完全部 Wave 才算完成；做不完就把"差哪一步"写清楚。


---

## 11. Wave H —— 审查方 2026-11-06 复审新发现（今晚从这里接，8 条，按序）

> 我对整夜产出的独立复审：**Wave A–D 的申报基本全部复现**（396 passed 0 skip / 治理 17 项 / 守卫 PASS /
> lint 194·244·240 / tsc 干净 / 我自己重跑 golden 5s 原帧 SSIM 1.0×6·pHash 0×6 / 我自己跑 e2e_ui 8 步 7.0s·固定等待 0 /
> 我自己 fresh-clone bootstrap READY）。下面是**只有我没查出来、你没记**的八条。

| # | 严重度 | 发现 | 落点 | 今晚的验收判据 |
|---|---|---|---|---|
| H1 | **中** | **B5 删除判活语义没有测试钉住**，且留一个真空窗：`queued` 状态用 `created_at` 兜底判龄——**排队等 Chrome 锁超过 120s 的作业会被判"不在飞"**，于是资产可以在它即将执行时被删掉 | `server/app/services/assets.py:500-521`（`_inflight_jobs_using`） | `queued` 一律算在飞（只有 `leased/running` 用 120s 心跳窗，僵尸行靠 `recover` 清理）；补 2 条测试：①queued+老 created_at → 拒绝删除；②retry_wait（等门）→ 允许删除。测试名带 P2-17/H1 |
| H2 | **中** | **裸 httpx 客户端的守卫有洞**：只查 `httpx.Client(`/`AsyncClient(`，**不查模块级便捷函数** `httpx.get/post/head/...`。实测漏网 1 处：`scripts/e2e_timeline_100.py:41` 的 `httpx.get(...timeout=3)`——毒 `NO_PROXY` 环境下这条脚本会当场炸（与被修的 F01 同一类） | `scripts/e2e_timeline_100.py:41`；守卫落点 `verify_p1_governance.py` 第 17/18 项或新单测 | 修那一处 + 静态守卫扩到 `httpx\.(get|post|head|put|patch|delete)\(` 必须带 `trust_env=False`；守卫实跑证明把 `trust_env=False` 删掉会变红 |
| H3 | **中** | **磁盘/库卫生回归（两处）**：①孤儿项目目录 `r3-camera-260`（**65MB，无 DB 行**，11-05 23:18 遗留）；②僵尸 draft **3 条**（id 261/262/263，root 指向已删的 `.acceptance/b2-color-tags-*`）——那是 B2 探针三次在 `destroy` 前抛错留下的，账本说"清掉了"但 draft 行还在 | `~/cc-projects/ai-v/filmflow-projects/r3-camera-260`；`scripts/_acceptance.py::destroy` 的 draft 回收条件 | ①按磁盘纪律清孤儿目录（**先备份、出前后计数、需老板点头**）；②`cleanup_projects.py --stale-drafts --confirm` 清这 3 条；③把"孤儿目录数==0 且僵尸 draft==0"做成治理第 18 项（只报告也算，别让它再无声增长）；④`destroy()` 的回收条件改为按 draft 名/root 前缀**或** payload 里任一指向本项目根的键，补一条单测 |
| H4 | **小** | **B9 的措辞比证据强**：fresh-clone 实测是在**同一台机器**（风格库/rumor/Chrome/ffmpeg 都在），换一台真干净机器仍未验证。晨报写"fresh-clone 真闭"过满 | `scripts/bootstrap_fresh_clone.sh`；`docs/process/overnight-ledger-2026-11-05.md` 轮 8 | 措辞改为"本机 fresh-clone 实测 READY"；给 bootstrap 加 `--require-all`（缺任一外部依赖即 exit≠0 + `E_ENV_MISSING` 逐条点名），并在 CI 里加一步 `bootstrap --check-only`（这样缺依赖的机器会红而不是"READY"） |
| H5 | **小** | **`.git` 从 63M 涨到 68M**：B3 重锚一次就整批替换 6 张 1080p PNG，且 1824999 后每批视觉改动都会再涨 | `fixtures/golden/*/baseline_original/`、`docs/reports/golden/`（现 16+ 份） | 定一个"锚点/churn"策略：报告只保留最近 N=20 份 + `index.json` 记录被裁掉的哈希；锚点目录写 README 说明"整批替换是有意的、理由在 updateHistory"。**不要**上 LFS（不联网）。给一次 `du -sh .git` 前后数字 |
| H6 | **小** | **BLE001 只钉不降**：棘轮基线 65/75/77 只保证不涨，没有下降目标；`except Exception` 面广，出问题时最难定位（P2-30 的同类） | `docs/reports/lint-baseline.json` | 给"每批 −5"的下降目标（写进基线 JSON 的 `target` 字段 + 治理断言 `<= target`），首批挑 5 处最有价值的（渲染链与交付门禁里的盲捕）收窄成具体异常类型 |
| H7 | **小** | **台账可读性**：`轮 1 ·（开发模型从这里开始写）` 空占位与真正的轮 1 同号；轮 0b 之后编号跳 R1…R10 与"轮 N"混用 | `docs/process/overnight-ledger-2026-11-05.md:44` | 删空占位或改标 `轮 1（占位）`；后续统一"轮 N · <Wave 编号> <标题>"；在文件头加一张 R1–R10 → Wave → 提交哈希的索引表（明天我按这张表抽查） |
| H8 | **结构性缺口（最大的一块）** | **FR-40/FR-41 只有后端纵切**：`scripts/e2e_fr40_keyboard.py` 不存在；命令面板/快捷键表/`?` 帮助/铃铛面板/进度中心/通知 UI 全无；FR-41 草稿层 UI 全无；**a11y 现值仍是 1 处 aria/role**（这三条你们自己已在"诚实边界"里写明，我确认属实） | `web/src/lib/commands.ts`（待建）、`web/src/components/`（面板/快捷键/通知）、`server/app/services/{notifications,authoring}.py`（已就绪） | 今晚做 **FR-40 前端纵切优先**：①20 个命令注册表 + `Cmd/Ctrl+K` 面板（可搜、可执行、键盘可达、`role`/`aria`）；②快捷键表 + 冲突检测 + `?` 视图；③通知中心面板（去重展示、已读、失败通知带"修复入口"跳 QA/delivery）；④进度中心（job 进度/ETA/取消，不阻塞编辑）；⑤`scripts/e2e_fr40_keyboard.py` 真跑**全流程纯键盘**（建项目→改→预览→跑→批门→导出），每步贴输出；⑥a11y 现值从 1 涨到"关键路径全覆盖"并给前后计数。FR-41 前端（草稿层 UI + 接受/拒绝/编辑）次优先，PRD 四条判据里"断网抓包证据"用 `lsof -p <pid>` 快照代替并说明 |

**Wave H 之后仍然悬着的老板决策点（6 个，别自己拍）**：push（现 38 个提交未推）、LICENSE 类型、VACUUM、`?tok=`→header 已完成无需决策、devDependency（a11y lint）、**以及新出现的一个**：`expire_parked` 的 72h 策略在 11-05 22:56 的 dev 重启时**自动收走了 5 条 parked 作业**（4 条 rumor-39s + 1 条演示 188，`app.log` 可查 `expiredParked=[13,48,49,72,80]`，DB 里 `status=canceled/E_JOB_EXPIRED`）。行为符合设计、Run 未受影响（仍 blocked，签门时会重建作业），但**它动的是保护项目的行**——需要老板明确认可"策略可以自动改写保护项目的作业状态"，否则把阈值改成"只收非保护项目"并加守卫。


---

## 12. 老板决策（2026-11-06 中午，已生效——今晚按这个做，别再问）

1. **push 已执行**（`8266f11..2585b3b`，现 origin/master = 已同步；此后每轮提交**照旧 push**，不必再逐次请示）。
2. **顺序**：Wave H（H1→H8）→ FR-40 前端纵切 → FR-41 前端。FR-41 若时间不够，明写差哪一步。
3. **清理已执行**（孤儿目录 `r3-camera-260` 65MB + 4 条僵尸 draft；`filmflow-projects` 1.5G；僵尸/孤儿现值均为 0）。
   → 所以 **H3 现在只剩"把棘轮装上"**：治理第 18 项断言「孤儿目录==0 且 僵尸 draft==0」，并修 `destroy()` 的 draft 回收条件（漏掉"项目根被删后才变僵尸"的那条——实测就是它）。
4. **`expire_parked` 策略认可**（保护项目的 job.status 可被改写，其余仍全保护）——把这句口径写进 HANDOFF/AGENTS 的门禁清单，别让它再被当成疑点。
5. ~~**VACUUM / LICENSE / devDependency** 三项**仍未决**，继续挂在决策点，不要自行处理。~~
   → **2026-11-06 晚已裁决并全部执行，见 §14**。今晚不要再把这三项当悬案。

## 13. H9（新增，优先级最高之一）—— CI 首跑红：子集选择与环境依赖从未对齐

实测：`gh run view 42159751964 --log-failed` → `3 failed, 354 passed, 3 skipped, 3 errors`（33s）。

- 根因 (a)：`server/tests/unit/test_audio_v2.py` **没有 `pytestmark`**（0 个 `requires_ffmpeg`/`requires_chrome`），
  但 4 个用例里 3 个真调 ffmpeg → runner 上 `FileNotFoundError: 'ffmpeg'`。
  **这是测试卫生缺陷，无论选哪个方案都必须先补标记**（顺带全仓扫一遍还有没有别的"未标记却依赖环境"的用例：
  对照 `subprocess`/ffmpeg/Chrome/风格库 的调用点与 marker 交集）。
- 根因 (b)：BDD 风格库场景按我们的纪律在缺环境时**硬失败**，而 341 风格库不入 git → CI 天生缺。

**三个修法（老板尚未选，今晚若未选就先做"补标记 + 全仓审计未标记环境依赖"这一半，另一半等口径）**：
- 方案 1「真环境」：CI 里 `apt-get install ffmpeg`（+ Chrome），BDD 风格库那几条用 `--allow-missing-env` 显式 skip 并在 job summary 打印 skip 数；
- 方案 2「纯 CI 纪律」：CI 只跑 `-m "not requires_ffmpeg and not requires_chrome and not requires_style_library"`，零安装，但必须在文档写明"CI 覆盖面不含任何环境依赖用例"；
- 方案 3「双 job」：`ci-lean`（方案 2）+ `ci-env`（方案 1），信号最全，YAML 与时长翻倍。

**老板已选：方案 3「双 job」**（`ci-lean` 零安装必绿 + `ci-env` 真环境广覆盖）。
**push 策略已确认：整夜每轮都推**（`git push origin master`，不需要逐次请示；每轮推完 `gh run list --limit 1` 看一眼，红了当场修，别攒）。

### H9 的三个根因（审查方已用 CI 日志 + 本机代码定位，今晚照单做，别再自己摸）

| # | 根因 | 证据 | 要做的动作 |
|---|---|---|---|
| H9-a | `server/tests/unit/test_audio_v2.py` 里 **3 个用例真调 ffmpeg 却没有任何标记**（该文件 0 个 `pytestmark`） | CI 日志 `FileNotFoundError: 'ffmpeg'` ×3；本机因为有 ffmpeg 永远看不见 | 加 `pytestmark = [pytest.mark.requires_ffmpeg]`（或逐条），并在 `ci-lean` 里被 deselect、在 `ci-env` 里真跑 |
| H9-b | BDD 风格库场景在缺库时**按纪律硬失败**，而 341 风格库不入 git → CI 天生没有 | CI 日志 `E_ENV_MISSING: 风格库不存在 /home/runner/Documents/...` ×3 | `ci-env` 里造一个**最小合法风格库 fixture**（≥1 个可生产风格，目录结构齐）并把路径经 `FILMFLOW_STYLE_LIBRARY_ROOT` 注入；`ci-lean` 里 `-m "not requires_style_library"`。两种都要在 job summary 打印计数，别静默 |
| H9-c | **两处静默 skip 违反自己的纪律**：`server/tests/unit/test_assets.py:104-106` 要 macOS 系统字体 `/System/Library/Fonts/Supplemental/Arial.ttf`、`:117-119` 要 `~/.filmflow/cache/fonts/NotoSansSC[wght].ttf`，缺了就 `pytest.skip` | CI 的 `3 skipped` 就是这类；本机字体都在 → 永不触发，所以从没人发现 | 改成 `requires_chrome`/新 `requires_font_<name>` 标记 + 缺环境时走 `E_ENV_MISSING` 硬失败（`--allow-missing-env` 才 skip）；**顺带全仓扫一遍其余裸 `pytest.skip`**（已知站点：`test_assets.py` ×2）并同样处理 |

### H9 的完成判据（缺一即算没做完）

1. `ci-lean` job：零安装、必绿，且在 `test_audio_v2` 漏标记的情况下**必须变红**——用一次故意的反向验证证明 deselect 真的在起作用（贴 `gh run` 链接）。
2. `ci-env` job：`apt-get install -y ffmpeg`（+ 若跑渲染级则装 Chrome），风格库走最小 fixture；跑完在 job summary 写明「跑了多少 / skip 多少 / 为什么」。
3. 新增一个**静态守卫**（治理第 19 项或单测）：用 `ast` 扫 `server/tests/**`，凡出现 `subprocess.run/exec` 且 argv 含 `ffmpeg|ffprobe|chrome` 的测试模块，必须声明对应 `requires_*` 标记；凡出现裸 `pytest.skip(...)`（conftest 的 `--allow-missing-env` 分支除外）即红。**这条是 H9 的长期防线，比修当前三处更值钱。**
4. 本机对照：`cd server && uv run pytest tests -q` 仍 **401 passed / 0 skip / 0 xfail**（数字随 collected 现值走，不许为了通过把覆盖改薄）（改标记不许把本机覆盖变薄）。
5. 台账记 `gh run list --limit 3` 的输出（首绿的那一次）。

---

## 14. 老板第二轮决策（2026-11-06 晚，已生效）

上一节 §12 的第 5 条（VACUUM / LICENSE / devDependency 悬案）与 §11 尾段的 6 个悬着决策点，本轮全部给出，**今晚不要再问、也不要自行改口径**。

| # | 决策 | 老板选定 | 已执行到什么程度 | 证据 |
|---|---|---|---|---|
| 1 | LICENSE 类型 | **MIT** | ✅ 已落 `dc89f2c` | `LICENSE`（1078B，MIT 正文，"Copyright (c) 2026 FilmFlow contributors"）+ README「许可」节明写**三块不在 MIT 内**：`vendor/fy-code-animation/`（免费用/分享，禁包装成付费课程或付费 skill）、341 风格库（仓库外）、`rumor-39s` 参考片（仓库外）；ffmpeg/Chrome 是本机系统依赖，不构成分发传染。引用的两个第三方文件实测存在（`vendor/fy-code-animation/LICENSE.md`、库内 `许可与来源.md` + `第三方许可/`）。 |
| 2 | 今晚切到哪一层 | **全都要**：Wave H（H1→H8）+ H9 + FR-40 前端 + FR-41 前端 | 顺序与判据不变 | 见下"半件不算 done"纪律。 |
| 3 | 渲染环境漂移的防线怎么做 | **漂移即诊断 + 重锚流程**（不是硬失败） | ⏳ 未做 → 见 §15 **H10** | —— |
| 4 | 两个挂在待决的小项 | **现在做 VACUUM** + **加 a11y lint 依赖** | ✅ 两项均已执行 | VACUUM：先备份 `~/filmflow-backup-20261106-pre-vacuum.db`，`page_count` 9083→6349、文件 37,203,968B→26,005,504B，`integrity_check=ok`、`foreign_key_check` 0 行，project 11 / draft 53 / run 44 / artifact 1744 与演示 docrevision 174=3 / 188=28 / 211=37 / 227=58 **全部零变化**，dev 已重启载入。a11y：`web/eslint.config.mjs` + `scripts/lint_a11y.py` 棘轮（见下）。 |

**a11y 棘轮的实际口径**（今晚改前端时以它为准，别自造标准）：
`eslint 10.14.0` + `eslint-plugin-jsx-a11y 6.10.2` + `typescript-eslint 8.72.1` 只装 devDependency、不进运行时；
脚本**只计带 `ruleId` 的消息**（配置类 null-ruleId 噪声不算，`noInlineConfig` 已经挡掉仓库里引用未加载插件的内联 disable），
`error` 必须为 0，`warn` 只许降不许涨，基线 `docs/reports/lint-baseline.json["a11y"]["warn"] = 60`。
降了要 `python3 scripts/lint_a11y.py --update` 写回。**反向验证做过**：人为把基线写成 59 时脚本当场 `FAIL: a11y warn 涨了 59 → 60`，不是假绿。
> H8 说的"a11y 现值 1 处 aria/role"指的是**业务代码里的可访问性属性密度**，棘轮量的是**违规数**——两者不是一回事。
> 前端批次要同时把两边都推进：违规只降不涨，且关键路径（命令面板 / 通知面板 / 快捷键表）要有真的 `role`/`aria-*`/键盘可达。

**"全都要"的半件不算 done 纪律**（老板点名的历史毛病，本轮起硬执行）：
1. 每个 Wave 项在台账里只有两种合法状态：**闭合**（命令 + 输出 + 提交哈希）或 **差哪一步**（写明"代码在 X:Y，缺 Z 验证/接线，下一个动作是……"）。**不许出现"基本完成 / 大体就绪 / 已交付（部分）"。**
2. 优先级顺序固定：H1→H8 → H9（含 ast 静态守卫，这是长期防线，不许最后砍掉）→ FR-40 前端 → FR-41 前端。
   时间不够就**从队尾（FR-41）截断**，不许从中间跳着做半截。
3. 凡动了执行器行为 → 升 `EXECUTOR_VERSION`（现 **2.17.0**）；动了预览渲染器 → 升 `RENDERER_VER`（现 `preview-2.1.0`）；两个版本的现值处要跟着守卫走。
4. 每轮提交后 `git push origin master`（已确认每轮都推），推完 `gh run list --limit 1` 看一眼，红了当场修，别攒。

## 15. H10（新增，本轮决策 3 落地）—— 环境漂移：诊断 + 重锚流程，不做硬失败

**为什么现在必须做**：今晚的 CI 首跑与 golden 复跑已经证明——本机与 runner 的**环境不一致**会同时制造
"假绿"（本机有 ffmpeg/字体，runner 没有 → 未标记用例只在本机跑过）和"假红"（Chrome/字体/ffmpeg 版本变了 → SSIM 掉，代码却没问题）。
老板选的修法不是"漂了就 fail"，而是**先让人看得见漂移，再给一条可执行的重锚路**。

**要做的三件事（判据逐条对应）**：

1. **指纹补齐**：`scripts/golden_run.py` 的 `_environment(root)` 已记录 Chrome/ffmpeg/字体等；
   把 **RENDERER_VER、EXECUTOR_VERSION、字体缓存 sha 列表、fps 口径版本**一并写入每份报告的 `environment` 块，
   并让 `docs/reports/golden/index.json` 每条记录带上 `environment` 摘要（哪个 run 是在什么环境下锚的）。
   判据：任选两份历史报告 diff 出 `environment` 字段齐、可读。
2. **漂移即诊断**：`check_docs_consistency.py`（或新 `scripts/diagnose_environment_drift.py`，由文档守卫调用）
   比对**当前实测环境**与**最近一次锚点报告的 environment**，逐项输出 `一致 / 漂移（旧值→新值）`，
   漂移时打印一段**可直接照做的重锚指引**：
   `uv run --project server python scripts/golden_run.py --project 5s --resolution original --update --reason "<为什么环境变了、为什么新锚是对的>"`，
   并**exit 0**（诊断不是门禁——这是老板明确选的口径，别改成 fail-closed，否则环境一升级整夜循环就被锁死）。
   判据：本机人为改一个被采集项（例如临时替换 ffmpeg 版本字符串来源）→ 输出"漂移"行 + 重锚命令；
   还原后 → 输出全"一致"、PASS。**两种输出都要贴进台账。**
3. **重锚留痕**：`--update --reason` 已经强制给理由并写 `updateHistory`；
   再加一条断言（治理项或单测）：**凡 `updateHistory` 里 reason 提到环境/版本变化的记录，必须能在 `index.json` 找到对应的 environment 差异**——
   即"重锚的理由"与"当时真实的环境"互证，防止以后有人拿"环境漂了"当掩盖回归的借口。
   判据：正向过；反向（伪造一条 reason 与实际环境不符的记录）变红。

> H10 不与 H9 混淆：H9 修的是**测试子集与环境依赖从未对齐**（标记 / 双 job / ast 守卫），
> H10 修的是**渲染产出与环境的因果可见性**（指纹 / 诊断 / 重锚留痕）。两条都要做，做完各自贴证据。
