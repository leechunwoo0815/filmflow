# 整夜自主开发台账（2026-11-05 夜 → 11-06 晨）

> 任务书：[`docs/process/overnight-goal-2026-11-05.md`](overnight-goal-2026-11-05.md)（Wave A–G + DoD + 纪律 + 审查方式）。
> 本文件是**唯一进度真源**：每轮追加一条，格式见任务书 §9-6。审查方明早逐条复跑。
> 规则：宁可少报不可虚报；没验的必须写"没验的"；一轮一个提交；不 push（决策点见任务书 §8）。

---

### 轮 0 · 基线（审查方交接时实测，2026-11-05 深夜）

改了什么：无（只读复核 + 落这份任务书与台账）

实测（命令含 cwd）：
- `cd /Users/litianyu/cc-projects/ai-v/filmflow/server && uv run pytest tests -q`
  → **360 passed + 1 skipped**（collected **361** = unit 321 / integration 33 / BDD 7；213.44s）。
  那 1 条 skip 是 `tests/unit/test_p1_foundations.py:234`「8787 已被 dev 服务占用」——
  **dev 服务在跑就会 skip，停掉 dev 就是 361 passed / 0 skipped**（第二夜报告的 ×2 全绿是在 dev 停止下测的，
  报告 §127 已注明，口径成立）。任务书 A8 要求把这个门控去掉。
- `uv run --project server python scripts/verify_p1_governance.py` → **16 项全 ✓ PASS**
- `uv run --project server python scripts/check_docs_consistency.py` → **PASS**
  （EXECUTOR=2.15.0 · 迁移 [1,2,3,4,5] · collected=361 · governance=16 步 · DB=11 项目 · 裸 dict 写端点 0）
- ruff：`cd server && uv run ruff check .` → **339**；仓库根 `uv run --project server ruff check .` → **405**；
  `--statistics` 里 **S110=1**（`server/tests/unit/test_multi_step_writes.py:50`）、**BLE001=75**（无棘轮）、**F821=0**
- `cd web && npx tsc --noEmit` → 干净
- 复核第二夜的修复：`grep -rn "httpx.Client(\|httpx.AsyncClient(" server/app scripts --include="*.py" | grep -v trust_env=False`
  → **0 行**（裸客户端已清零）；`server/tests/unit/test_f01_http_env.py` 是真的（毒环境对照组 + F01 真起帧服务拿 200）
- DB/磁盘：11 项目 · 47 draft（僵尸 0）· 44 run · `retry_wait` 12（全属 rumor-39s 与演示 188，**不许删**）·
  `filmflow-projects` 1.6G · `~/.filmflow` 1.5G · 自动备份 `filmflow-auto-20261105.db` 33,411,072B
- 演示 docrevision：174=3 / 188=28 / 211=37 / 227=58（与前两夜一致，零变化）
- git：HEAD `df5fbbb`，工作树干净，`origin/master..HEAD` = **23 个未推送提交**（origin 停在 `8266f11`）

真渲染证据：无（本轮只读）。第二夜留下的最新一份是 `docs/reports/golden/5s-original-run336.json`
（schema `/3`、status pass、ssim [1.0×6]、环境指纹齐全；**注意它是 11-05 23:37 覆写的，11-04 那份原件已丢** → 任务书 A1）。

没验的：`bootstrap_fresh_clone.sh` 未在干净目录实测；CI 从未执行（未 push）；
FR-40/FR-41 未开工；Wave B/C/D 全部未开工。

提交：本文件 + 任务书（见下条 git log）

遗留/待决策：push、LICENSE 类型、是否新增 devDependency（a11y lint）、VACUUM/动 12 条 retry_wait —— 全部需老板点头。

---

### 轮 1 · （开发模型从这里开始写）

---

### 轮 0b · 审查方锚点复核与修正（2026-11-06 凌晨——任务书落盘 ≠ 任务书可信，逐条复核后修 12 处）

改了什么：任务书 [`overnight-goal-2026-11-05.md`](overnight-goal-2026-11-05.md) 修正 12 处——
① 行号漂移（`dab7fe4` trust_env 提交使 pipeline.py 后移 5 行）：A2 `:228/230/296`→`:160/:233/:234/:301`、
B2 `:1270-1273`→`:1329/:1332`、`:1082`→`:1141`；② 事实修正：B5→`assets.py:486`（`delete_asset`）+`routes.py:1756`、
B6→**仓库根** `bdd/features/`（17 个，绑定文件名写明）、B7→10 处（:23–:142，300–5000ms）、Wave D routes.py→2764 行；
③ 基线数字更新：`retry_wait` **12→7**（5 条按 72h 心跳被 `expire_parked` 在深夜 dev 重启时自然收走，策略按设计工作；
剩余 7 条不许删）、未推送 23→25、A3 加 cwd 口径注（仓库根 BLE001=75 / `cd server` 65）、§2 pytest 基线标注
dev 在跑时 360+1skip；④ 同步守卫看不见的入口文档失真：HANDOFF `test_p1_foundations.py:174`→`:234`、
draft 46/10 目录 1.5GB→47 draft/11 目录 1.6G + retry_wait 7。

实测（命令含 cwd）：
- `git rev-list --count origin/master..HEAD` → **25**（HEAD `62b32e0`）；remote `git@github.com:leechunwoo0815/filmflow.git`，origin 停在 `8266f11`
- `sqlite3 ~/.filmflow/filmflow.db "select count(*) …"`（表名**单数** project/draft/run/job）→ project **11** / draft **47** / run **44** / job(retry_wait) **7**
- `ls -d /Users/litianyu/cc-projects/ai-v/filmflow-projects/*/ | wc -l` → **11**；`du -sh` → **1.6G**（HANDOFF:7 旧值"10 目录 1.5GB"是 11-05 夜的快照，已按实刷新）
- `find . -name "*.feature" -not -path "*/node_modules/*" -not -path "*/vendor/*" -not -path "*/.git/*"` → **17 个，全部在仓库根 `bdd/features/`**（`server/` 下 0 个——B6 原锚点会把开发模型引去空目录）；绑定 2 个：`server/tests/bdd/test_style_indexing_bdd.py`、`test_r2_workbench_bdd.py`
- `grep -ro "aria-[a-z]*\|role=\"" web/src --include="*.tsx" | wc -l` → **1**（B4 现值属实）；`grep -rn symlink server/tests | wc -l` → **0**（C1 现值属实）
- ruff `--statistics`：`cd server` 口径 BLE001=**65** / S110=**1**；仓库根口径 BLE001=**75**；`uv run --project server ruff check .`（仓库根）→ Found **405**（DoD §0-4 的调用口径可复现 ✓）
- PRD-002 §FR-40（**912–928 行**）/ §FR-41（**932–950 行**）验收原文与任务书引文**逐字吻合**（3+4 条）
- A1 证据：`scripts/golden_run.py:321` 的归档名 `REPORT_DIR / f"{args.project}-{rr['resolution']}-run{rid}.json"`；`docs/reports/golden/5s-original-run336.json` mtime **Nov 5 23:37:10**（11-04 原件确被覆写）
- 其余锚点核验为真：A4 `runengine.py:685`、A5 `_acceptance.py:152-154`（216/223 在列）+`project_cleanup.py:25-28`（`golden-5s` 在列）、A6 `routes.py:1148` + `delivery.py:378-383`（连"现网全部为空"注释都在）、A7 `jobs.py:150`、B1 `review_comments.py:33/54` + `takes.py:22/35`、B3 `compiler.py:144`（`duration-0.4` 淡出）、`preview.py:400/441`（CDP）、专家分析 §2.3 "P3 共 26 条"、`git ls-files | grep -c DS_Store` → 0

真渲染证据：无（本轮只读 + 文档修正）。

没验的：剩余 7 条 retry_wait 的归属未逐条查（沿用 §7-3 的性质结论）；A8"skip 可去掉"的可行性未预验（由开发模型按 A8 实现并证明）。

提交：本条 + 任务书 12 处修正 + HANDOFF 两处（见下一条 git log）

遗留/待决策：不变（任务书 §8 五个决策点仍待老板点头）。

---

### 轮 1 · A1 黄金报告防覆写 · 2026-11-06 00:3x

改了什么：`scripts/golden_run.py` 归档段（原 :319-326）——归档名加 UTC 时间戳
（`{project}-{resolution}-run{rid}-{YYYYMMDDTHHMMSSZ}.json`）、同名/同秒重跑**绝不覆写**（后缀 -2/-3 递进）、
新增并维护 `docs/reports/golden/index.json`（schema `filmflow.golden-index/1`，每条
project/resolution/runId/at/executorVersion/ssimMin/status/reportFile；**首次落盘自动回填既有 9 份历史归档**）；
归档写盘改 `write_atomic`（原为裸 `write_text`）。

实测：
- 真跑 `uv run --project server python scripts/golden_run.py --project 5s --resolution original`
  → **SSIM=1.000000 ×6 / pHashDist=0**（run 336，EXECUTOR=2.15.0 · Chrome 156.0.8078.80 · ffmpeg 9.0.2 ·
  font=a3041811…），`archived report: …/5s-original-run336-20261105T162717Z.json`，
  `golden index: …/index.json（10 条）`，跑完自删、DB 12→**11** 恒定。
- **旧文件仍在**：`5s-original-run336.json`（11-05 23:37 那份）mtime 未变；新档是独立时间戳文件——覆写问题闭环。
- `cd server && uv run pytest tests -q` ×2 → **360 passed + 1 skipped**（188.98s/182.33s；
  skip= `test_p1_foundations.py:234` 8787 门控，dev 在跑所致——**A8 将去除**，两轮数字一致）
- `verify_p1_governance.py` → **16 项全 ✓ PASS**；`check_docs_consistency.py` → **PASS**
- ruff：server **339** / 仓库根 **405**（不高于基线）；`cd web && npx tsc --noEmit` → 0 错

真渲染证据：有——run 336，SSIM [1.0×6]，报告 `docs/reports/golden/5s-original-run336-20261105T162717Z.json`。

没验的：`--update` 分支下归档路径未实跑（代码同一分支，`--update` 判据在台账里注明）。

提交：见下一条 git log（fix(a1)）

遗留/待决策：无

---

### 轮 2 · A8+A3+A5 测试门控去除 / lint 棘轮 / 守卫名单同步 · 2026-11-06 01:0x

改了什么：
- **A8** `server/tests/unit/test_p1_foundations.py:236-241`——`test_frameserver_writes_frames_atomically`
  弃用写死 8787 + skip 门控，改绑空闲端口（帧端口 2.14.0 起可配置）；dev 在跑也 0 skipped。
- **A3** `scripts/verify_p1_governance.py` 新增 `check_lint_ratchet()`（第 17 项）+ 新基线
  `docs/reports/lint-baseline.json`（schema `filmflow.lint-baseline/1`）：两口径 total/BLE001/S110/F821
  逐项断言 `current <= baseline`，**只许降不许涨**，上调必须先修代码并在台账给理由。
- **A5** `scripts/_acceptance.py` `DEMO_PROJECTS` **补全为现网 11 个**（1/4/115/151/206 原先漏登记，
  216/223 已删移除）；`project_cleanup._PROTECTED_NAMES` 的 `golden-5s` **保留**并注释理由
  （golden_run 仍按 `golden-5s-*` 自建自删，按名保护防误碰）；HANDOFF §7.4 目录数刷为
  11 目录 1.6G（2026-11-06 复测）。
- 文档现值刷新（361→364 / 16 项→17 项）：HANDOFF §0.0 实测行、§0.6.3、§6、§9、接手检查表；
  AGENTS 进度行 + 快速命令；任务书 §0 DoD-2 与 §2 基线。

实测（命令含 cwd）：
- `cd server && uv run pytest tests -q` ×2 → **364 passed ×2，0 skipped 0 xfailed**（188.71s / 186.20s，
  **dev 在跑**——A8 生效；361→364 = A5 把污染闸门测试按 11 项目重新参数化 +3）
- 定向：`pytest tests/unit/test_p1_foundations.py tests/unit/test_acceptance_pollution.py -q` → 42 passed
- `uv run --project server python scripts/verify_p1_governance.py` → **17 项全 ✓ PASS**，
  第 17 项输出：`serverCwd total=339/339 BLE001=65/65 S110=1/1 F821=0；repoRootCwd total=405/405 BLE001=75/75 S110=1/1 F821=0`
- `check_docs_consistency.py` → **PASS**（collected=364 · governance=17 步 · DB=11）
- ruff 两口径 339/405（= 棘轮基线，未涨）；`cd web && npx tsc --noEmit` → 0
- 治理第 14 项（零演示污染）在 DEMO_PROJECTS 扩容后仍 PASS——静态扫描无新增命中

真渲染证据：无（本轮无渲染路径改动；A1 的 golden 仍是最新渲染证据）。

没验的：无。

提交：见下一条 git log（feat(a3/a5/a8)）

遗留/待决策：无

---

### 轮 3 · A4+A6+A7 锁生命周期 / params 语义钉死 / expire_parked 真实演练 · 2026-11-06 01:3x

改了什么：
- **A4** `runengine.py`：`_PROJECT_RUN_HOLDERS` 登记计数（排队等锁也在册）+ 最后退出者
  pop 锁与计数；`start_run` 创建任务前 retain；`_run_loop_locked` finally release；
  `drop_project_run_lock()` 供删除面强制清；`project_cleanup.delete_project` 接线调用。
  **EXECUTOR_VERSION 不升（2.15.0）**：只动进程内字典卫生，节点执行/调度结果逐字节等价，
  同 trust_env 的产出等价裁决（b9-close-report §9.1）。
- **A6** 语义钉死（选②）：新增 `test_delivery_empty_params_snapshot_skips_and_match_passes`
  ——**快照侧** params 为空（生产实况）完全不比对（run 侧带什么都放行）、快照非空且一致放行；
  非空漂移已由 `test_delivery_rejects_params_drift` 钉死。HANDOFF/AGENTS 的"形同虚设"注记
  改为"语义已钉死 + 单测"。
- **A7** 新脚本 `scripts/verify_expire_parked.py`：**隔离实例真实演练**（独立
  FILMFLOW_HOME/白名单/DB + 进程内真实 uvicorn 线程——TestClient 的 per-request portal
  没有持久事件循环，start_run 的任务永远不推进，实测否决）。自建 scratch 跑到 B08 →
  作业 park 成 retry_wait → 心跳拨老 73h → 真调 `expire_parked()`（72h 默认）→ 断言
  **只收本演练作业** → 签门 + start_run → 断言作业重建。生产库那 7 条分毫未动
  （job#85 心跳距 72h 红线仅 ~2h，绝不能在生产库上跑这个函数——这正是选隔离实例的原因）。
- 测试 +3：`test_run_lock_slots_evicted_after_runs_finish`、
  `test_run_lock_slot_survives_while_sibling_waits`（兄弟等锁时不许清锁）、
  `test_delete_project_clears_run_lock`（macOS /var→/private/var 符号链接按 resolved 比）。

实测（命令含 cwd）：
- `uv run --project server python scripts/verify_expire_parked.py` →
  `✓ 1) B08 待批，作业 1 park 成 retry_wait` → `✓ 3) expire_parked 收走作业 1：
  canceled / E_JOB_EXPIRED（其余 retry_wait：0 条）` → `✓ 4) 作业重建：新作业 2（retry_wait）≠
  被收的 1` → `PASS: … wall 129.6s，生产库零接触`（连跑两次稳定，第一次暴露
  门标记↔作业置态的毫秒级竞态，已改为轮询到 park 为止）
- `cd server && uv run pytest tests -q` ×2 → **368 passed ×2**（189.78s/185.86s，0 skip，dev 在跑）
- 治理 **17 项全 ✓**（第 17 项棘轮在 R3 第一跑就咬住了自己：+1 server / +8 root，
  全部修回，未抬基线）；守卫 **PASS**（collected=368）；ruff **339/405**；tsc 0
- 生产库：project **11** / retry_wait **7**（分毫未动）

真渲染证据：无（本轮无渲染路径改动；最新渲染证据仍是轮 1 的 golden SSIM 1.0×6）。

没验的：无。

提交：见下一条 git log（feat(a4/a6/a7)）

遗留/待决策：无

---

### 轮 4 · A2 帧服务凭据 header 化（?tok= 废除）+ 黑帧回归当场抓出当场修 · 2026-11-06 02:2x

改了什么：
- **服务端** `pipeline.py`：`_authorized` 改读 `X-FilmFlow-Token` header（**query tok 一律不再接受**，
  有回归钉测试）；复用探针改带 header（URL 不再携带凭据）；`_engine_url` 的 embed 参数改传
  **相对路径**（token-free）且 token 改走 **URL `#fragment`**（fragment 不进任何 HTTP 请求/日志/
  服务器记录；Chrome 缓存按无 fragment 的 URL 键控 → 缓存页照样从新 hash 读到轮换后的新 token——
  这正是 P2-32 的 8.4 教训要求的缓存存活性）；`_project_url` 不再把 token 拼进 URL
  （**顺带修掉"token 被持久化进 artifact JSON"的旧泄漏**）。
- **引擎侧 4 个入口页全部改造**（侦察时只看到 2 个，真渲染抓出第 4 个——见下）：
  `film.html`/`film_spec.html`/`still_spec.html`/`still.html`——TOK 从 `#fragment` 读、
  fetch 带 `FH()` header、embed css 改 **fetch+`<style>` 注入**（`<link>` 带不了 header；
  embed.css 是 data:URL 自包含的，注入即生效）；`previs.html` 纯内联 payload 无取数，豁免。
- **测试**：`test_frameserver_auth.py` 重写为 header 语义（含"query tok 必须 403"的回归钉）；
  `test_p1_foundations` 帧上传改 header。
- config.py 注释同步。

**黑帧回归（任务书预警的那次）当场抓出当场修**：改造后首轮全量 pytest，渲染级 E2E 立即
`D04 静帧过暗 lum_mean=17.9 < 40`。隔离探针复现 + 留存现场：静帧内容是引擎错误屏
`E_PROGRAM_INVALID — Unexpected token '<'`（fetch 拿到 403 的 HTML）——根因：D02 走的是
**第四个入口页 `still_spec.html`**（侦察时漏掉），未改造仍按旧方式取数。补改后全绿。
证据：`/tmp/a2-stills/S01_0.896_draft.png`（错误屏现场照）。

实测（命令含 cwd）：
- `cd server && uv run pytest tests -q` ×2 → **368 passed ×2**（197.25s/197.99s，0 skip，dev 在跑）
- **真渲染双验**（dedup 修复后复跑）：`golden_run.py --project 5s --resolution original` →
  **SSIM=1.000000 ×6 / pHashDist=0**（run 336，归档 `5s-original-run336-20261105T181346Z.json`，
  index 12 条，自删，DB 11 恒定）；`verify_r3_camera.py` → **PASS**
  （D01 文本 override / E03 相机 3 帧 / E04 4 种转场 / preview vs final SSIM 0.989483——
  与 P2-32 修复后基线逐字一致）
- **日志无 token 实证**：临时 FrameServer + 带 header 取 `/project/a.txt` →
  `127.0.0.1 - - "GET /project/a.txt HTTP/1.1" 200`，响应 `ok`，
  `token 出现在日志: False`；代码面 `grep -rn "tok=" server/app engines/riso` → **0 处 URL 构造**
  （只剩注释）；"token 进 artifact" 的旧泄漏同轮关闭
- 治理 **17 项全 ✓**（第 14 项还抓掉了我第一轮探针留下的 `.acceptance/a2probe-1` 孤儿目录——已清）；
  守卫 PASS；ruff **339/405**；tsc 0
- EXECUTOR/RENDERER **均不升**：URL/凭据管道改动，产出逐字节等价（golden SSIM 1.0 ×6 双轮实证），
  同 trust_env 产出等价裁决

真渲染证据：golden run 336 SSIM [1.0×6]（报告 `docs/reports/golden/5s-original-run336-20261105T181346Z.json`）
+ verify_r3_camera PASS（SSIM 0.989483）。

没验的：`previs.html`（纯内联 payload，无 fetch）未做浏览器级验证——它不发起任何数据请求，豁免。

提交：见下一条 git log（feat(a2)）

遗留/待决策：无

---

### 轮 5 · B1/P2-08 JSON 读改写并发安全（flock 全程锁）+ 真并行测试 · 2026-11-06 02:5x

改了什么：
- `services/review_comments.py`：`_mutation()` flock 上下文（review/.review.lock）；
  `add/update/decide/import_json` 4 个变更函数改为薄包装（公开签名不变，内部 `_name` 持锁执行）。
- `services/takes.py`：同款（card/.takes.lock）；`update/promote/delete` 3 个包装。
- 原子写只保证不留半文件，不保证不丢更新——两个并发客户端都 load v1 再各自 save，
  后写覆盖先写（专家 P2-08）。flock 对**跨线程**（各开各的 fd）与**跨进程**都互斥；
  变更函数内部无嵌套加锁（读路径不锁），无自锁。选锁而非 CAS 409：并发用户排队
  优于报错（任务书允许可选"或文件锁"）。
- 新测试 `tests/unit/test_json_cas.py`：**真线程并行**（ThreadPoolExecutor 4×25 条批注、
  4 线程混合写 takes），断言零丢失——连跑 3 次稳定。修复前此场景必丢数据。

实测（命令含 cwd）：
- `pytest tests/unit/test_json_cas.py -q` ×3 → 全过（竞态不可复现）
- `cd server && uv run pytest tests -q` ×2 → **370 passed ×2**（196.72s/195.51s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**（collected=370）；`cd web && npx tsc --noEmit` → 0
- ruff：**322 / 388**（低于基线 339/405）——修 B1 时 I001 棘轮咬出 5 个文件的潜在导入排序
  存量（含 routes.py/pipeline.py），`--fix` 清掉；**基线随之只降**（lint-baseline.json 已下调
  并注明理由）；S110=1/BLE001=65·75/F821=0 不变
- EXECUTOR 不升：文件锁语义，节点产出不变

真渲染证据：无（无渲染路径改动）。

没验的：跨进程并发未单测（flock 语义即跨进程互斥；进程内真并行已实测）。

提交：见下一条 git log（feat(b1)）

遗留/待决策：无

---

### 轮 6 · B2/P2-12 两遍 loudnorm + f04 成片 bt709 色彩标签 · EXECUTOR 2.16.0 · 2026-11-06 03:1x

改了什么：
- `services/audio.py`：新增 `parse_loudnorm()`（解析 ffmpeg stderr 的 print_format=json 实测块；
  **input_i 非有限值（全静音 -inf）/解析失败一律返回 None → 调用方回退单遍，绝不让坏测量进第二遍**）、
  `measured_loudnorm()`（第二遍 linear=true 回灌）；`processing_filter(opts, measured=)` 双形态；
  `process_take` normalize 走两遍。
- `pipeline.py`：`_mix_filter(..., measured=)` 双形态（G05 mix 两遍：同图 null 输出测量 → 回灌编码）；
  **f04 成片 `-x264-params colorprim=bt709:transfer=bt709:colormatrix=bt709`**——实验钉过：
  ffmpeg 的 `-colorspace/-color_primaries/-color_trc` 三个输出标志**只有 color_space 会进流**
  （/tmp/t1.mp4 实验），x264 VUI 三参数才全落 ffprobe（/tmp/t2.mp4 三标签齐）。
- **EXECUTOR_VERSION 2.15.0 → 2.16.0**（这次是真行为变化：mix/take 编码参数与成片容器标签都变，
  不是产出等价——规则照章升版）；cachekey 历史注释登记。
- 新测试 `tests/unit/test_audio_two_pass.py` ×5（测量解析/静音拒绝/回灌串/双形态/版本下限沿用）。

实测（命令含 cwd）：
- **`verify_r3_audio_v2.py` 真跑 PASS ×2**（2.16.0 下）：`G06 -13.9 LUFS target -14.0`
  （修复前 -13.8——**偏差 0.2→0.1，两遍生效**）；G01/G05/G06/G07 全绿、stems 5/5/5s
- **ffprobe 色彩标签实证**（scratch 跑到 F04 后探测）：
  `{"color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709"}`
- **golden 5s 原帧**（2.16.0 全新链重渲）：**SSIM=1.000000 ×6 PASS**（归档 184819Z，自删，DB 11）
  ——视觉逐字节等价，升版无视觉回归
- `cd server && uv run pytest tests -q` ×2 → **375 passed ×2**（199.57s/194.39s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**（EXECUTOR=2.16.0 · collected=375）；ruff **322/388**（基线持平）；
  tsc 0
- 棘轮两次咬住自己（+1 潜在 SIM103/PIE810 被 B2 编辑的缓存失效暴露）——当场修（_needs_token
  改直返条件），未抬基线

真渲染证据：golden run 336 SSIM [1.0×6]（报告 `docs/reports/golden/5s-original-run336-20261105T184819Z.json`，
EXECUTOR=2.16.0 指纹）+ verify_r3_audio_v2 PASS（G06 -13.9 LUFS）+ ffprobe bt709 三标签。

没验的：Take 处理（process_take 两遍）的 LUFS 数值未单独验收——verify_r3_audio_v2 的
processed take 段已覆盖其执行路径（PASS）。

提交：见下一条 git log（feat(b2)）

遗留/待决策：无

---

### 轮 7 · B3/P2-13 文字淡出与出转场窗口对齐 + 逐帧量化 harness · EXECUTOR 2.17.0 / RENDERER preview-2.1.0 · 2026-11-06 03:5x

改了什么：
- `scene/compiler.py`：新增 `out_transition_of(scenes, scene_id)`（**出转场时长 = 下一场的
  transition_duration**，缺省 0.5——与 E04 同口径；末场 0）与 `_text_out_fx()`——文字 out
  从固定 `duration-0.4/0.4s` 改为：**有出转场 → 满显到场景末尾、随转场窗口一起淡出；
  末场/无出转场 → 旧行为不变**。转场窗口内 renderer 以 t>duration 继续画本场景
  （scene-render.js renderFrameAt），旧固定淡出在窗口起点就把文字收掉——背景在
  crossfade、文字提前没了（专家 P2-13）。
- 三处 compile_scene 调用全部贯通（C05 静态 program / E04 base+motion / preview
  build_programs——预览与 final 同源，P2-14 的教训不再犯）。
- 新 harness `scripts/verify_transition_text.py`：scratch 真渲到 F04（S02 文字清空让
  度量只测 S01 出场文字），转场窗 [2.0,2.5) 前后逐帧抽帧，**标题区暗像素数**为文字
  在场度量（H2 纸色卡片上的深墨文字；亮像素会被卡片本体淹没——实测选型）。
- **EXECUTOR 2.16.0→2.17.0、RENDERER preview-2.0.0→preview-2.1.0**（program 字节与
  预览渲染都变，照章双升）；**golden 基线按 P0-4b 程序更新**（`--update --reason` 写明
  B3 视觉变化；旧行为的 t=2.917 锚帧在窗内、必然不同——这正是修复目的），随后
  非 update 复跑 SSIM 1.0 ✓。
- 新测试 ×2（test_scene_compiler）：out_fx 双形态 + out_transition_of 口径。

实测（命令含 cwd）：
- **`verify_transition_text.py` 真跑 PASS**：逐帧暗像素表
  `t=1.8→2.2 全部 1811（满显平台）→ t=2.3 682 → t=2.4 560 → t=2.5 410 → t=2.6 234（地板）`
  ——**t=2.0（窗口起点）文字满显**（旧行为此处已衰减到地板）、窗口内平滑衰减、窗后归零
- **golden 基线更新后复跑 SSIM=1.0 PASS**（报告 `…-20261105T191336Z.json` + 复验，index 14 条）
- **verify_r3_camera 真跑 PASS**：D01/E03/E04 全过，preview vs final SSIM **0.989879**
  （B3 前基线 0.989483——同刻差 0.0004，预览/final 仍同源一致）
- `cd server && uv run pytest tests -q` ×2 → **377 passed ×2**（200.06s/199.19s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**（EXECUTOR=2.17.0 · collected=377 · DB=11）；ruff **322/388**；tsc 0

真渲染证据：verify_transition_text 逐帧量化表 + golden 2.17.0 SSIM 1.0（新基线）+ camera 0.989879。

没验的：8 种转场类型逐一过窗（harness 用默认 match-shape；out_fx 在 compiler 层与转场类型无关，
类型差异由 drawTransition 既有实现承担）。

提交：见下一条 git log（feat(b3)）

遗留/待决策：无

---

### 轮 8 · B5 资产在飞守卫+GC / B7 e2e 条件等待 / B8 ci_local / B9 fresh-clone 实测 · 2026-11-06 04:4x

改了什么：
- **B5** `assets.py`：`_inflight_jobs_using()`（执行中作业 payload 引用该资产 → 409；
  判活同 project_cleanup 120s 心跳窗；**retry_wait 不算在飞**——等人工门是正常态，
  恢复时自有 E_ASSET_MISSING 检查；无心跳僵尸行用 created_at 兜底判龄——全量套件
  两次红才定位到生产库 job 1/2 无心跳僵尸）；delete_asset 接线。新脚本
  `cleanup_assets.py`（默认报告孤儿文件/死行，--confirm 才删、库行删除先备份）。
- **B7** `e2e_ui.py`：10 处固定 wait_for_timeout **全部条件化**（expect to_have_value/
  to_be_enabled/networkidle/wait_for_function 计数条件）；顺带抓出并修 **e2e_ui 每跑
  一次泄漏一个向导项目**（228/229 两个泄漏已清）——收尾自删 created_pid。
- **B8** 新 `scripts/lint_ratchet.py`（三口径棘轮独立脚本：serverCwd/repoRootCwd/
  **ciScope=`ruff check server scripts`**）——**实测发现 ci.yml 的 lint 步是死的**
  （裸 `ruff check server scripts` 在 387 存量上必然红，首推必挂），ci.yml 改跑
  棘轮；治理第 17 项改为同源调用；新 `scripts/ci_local.sh`（CI 四步本地等价）。
- **B9** fresh-clone 实测：`git clone → bootstrap → clone 内跑测试`。

实测（命令含 cwd）：
- **B9**：`/tmp/filmflow-fresh` clone（HEAD 40202e3）→ `bootstrap_fresh_clone.sh` →
  **READY exit=0**（uv/ffmpeg/py3.13/Chrome/风格库 341+doctor/rumor/golden 锚/~/.filmflow
  全 ✓）；clone 内 `pytest tests/unit tests/bdd` → **344 passed**（主仓 345，差 1 =
  未提交的 B5 测试，提交后即齐）——P1-21 从"未实测"转**真闭**
- **B7**：`e2e_ui.py` 8 场景全过、**6.6s**（旧固定等待 ~15s → **2.3x**）、
  `wait_for_timeout` 剩 **0** 处、向导项目自删实证（project=228 → 已自删 200 → DB 11）
- **B8**：`bash scripts/ci_local.sh` → 四步全过（棘轮三口径 / unit+bdd **345 passed** /
  tsc / 守卫）
- `cd server && uv run pytest tests -q` ×2 → **378 passed ×2**（180.69s/180.65s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**；ruff **321/386**（PLW1510 全量 check=False 显式化 +
  SVG/base64 盲捕收窄，基线下调锁定）；tsc 0；DB 11 恒定

真渲染证据：无（本轮无渲染路径改动；最新为轮 7 的 harness + golden 2.17.0）。

没验的：cleanup_assets 的 --confirm 分支未真删（当前 0 孤儿 0 死行，没有可删对象——
报告模式已实证；首次出现孤儿时跑 --confirm 即为验收）。

提交：见下一条 git log（feat(b5/b7/b8/b9)）

遗留/待决策：无
