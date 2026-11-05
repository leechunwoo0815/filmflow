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
2. `uv run --project server python scripts/verify_p1_governance.py` → 全项 ✓（现在 16 项，你新增守卫就更多）。
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
- 改执行器行为**必须升 `EXECUTOR_VERSION`**（现 2.15.0）；改预览渲染器升 `RENDERER_VER`（现 preview-2.0.0）。
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
cd server && uv run pytest tests -q                     # 基线：361 passed（0 skip 0 xfail；dev 在跑时是 360+1skip——test_p1_foundations.py:234 的 8787 门控，见台账轮 0 与任务 A8）
uv run --project server python scripts/verify_p1_governance.py    # 基线：16 项全 ✓
uv run --project server python scripts/check_docs_consistency.py  # 基线：PASS
```

**基线数字（2026-11-05 深夜，审查方实测/复核）**：
- pytest **361 collected**（unit 321 / integration 33 / BDD 7）；第二夜自述 **361 passed ×2**（214.5s / 188.1s，0 skip 0 xfail）。
- 治理 **16 项全 ✓**；文档守卫 **PASS**（EXECUTOR=2.15.0 · 迁移 [1,2,3,4,5] · DB=11 项目 · 裸 dict 写端点 0）。
- ruff：**339**（`cd server` 口径）/ **405**（仓库根口径）；S110 剩 **1** 处（`server/tests/unit/test_multi_step_writes.py:50`）；BLE001 **75**（无棘轮）。
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
