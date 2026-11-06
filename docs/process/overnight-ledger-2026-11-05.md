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

---

### 轮 9 · Wave C 七条补齐（含两个真 bug）+ lint 全仓 --fix 一次性清底 · 2026-11-06 05:4x

改了什么：
- **C1** `_safe_join` 符号链接越界测试（白名单根内 symlink 指向根外必须拒）。
- **C2** 无体 POST token 层：裁定**不做**（仅本机绑定 + Host/Origin 校验 + 写端点全模型化
  已覆盖；理由入 HANDOFF §8，未来引入则补测）——按任务书"不做就写清理由"。
- **C3** 并发双客户端真并行保存 doc：base_version CAS 冲突→409→重读重试，40 保存零丢失、
  版本链连续（**save_doc 本就有乐观并发**，此前无测试钉住）。
- **C4** 截断 PNG：f03 帧扫描对"存在但坏"的文件**按缺失计**（触发重脏/报缺失），
  不裸崩不当有效帧——pipeline try/except 包住 PIL open。
- **C5** 坏资产四件套 → **揪出两个真 bug 并修**：①损坏文件的元数据探测让 PIL/原始异常
  冒成 500 → import_asset 统一转 4xx 可诊断错误；②空文件（0 字节）被静默收下 → 明确拒。
  伪装 SVG 按既有裁定**优雅降级**（收下+无尺寸+CSP 服务面），断言其不 500。
- **C6** delivery 幂等：create_job 的防重是 check-then-act，真并发会双入队 → **flock 按
  run_id 串行化检查+入队**；真并发两请求实测只落 1 个作业。
- **C7** QA 统计口径：failed/applied/verified 混合数据 → successRate=2/3、
  verificationRate=1/2（failed 不冒充 verified）钉死。
- **lint 一次性清底**：`ruff --fix`（safe）清光全仓可自动修复项；**基线一次性下调
  322→314 / 388→364 / 387→360**（余量为 B008=FastAPI Depends 惯用法等 idiom 类，
  棘轮照钉防涨）；pipeline 四处顺手真修（PIE810 元组、两处 noqa 带理由、PLC0206 items()）。

实测（命令含 cwd）：
- `pytest tests/unit/test_expert_gaps.py tests/unit/test_assets.py -q` → **20 passed**
- `cd server && uv run pytest tests -q` ×2 → **384 passed ×2**（183.07s/179.47s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**（collected=384 · DB=11）；棘轮 **314/364/360** 全 ✓；tsc 0

真渲染证据：无（本轮无渲染路径改动；最新为轮 7 的 golden 2.17.0 + harness）。

没验的：C6 的跨进程并发（flock 语义即跨进程；进程内真并行已实测）。

提交：见下一条 git log（test(wave-c)）

遗留/待决策：无

---

### 轮 10 · B6 ADR-0014 + Wave D 26 条判定 + FR-40/41 后端纵切 · 2026-11-06 06:5x

改了什么：
- **B6/P2-25**：ADR-0014（不造假绑定不删规格）——15 个未绑定 feature 头部加 `@unbound`
  标记与逐个理由；待绑优先级 gates > cache-invalidation > resume 留真绑批次。
- **Wave D**：`docs/process/p3-judgments-2026-11-06.md` **26 条逐条判定**（修 3 / 决策 3 /
  不修+理由 20）。真修：.gitignore 补 .DS_Store；F02 预热 Chrome profile 加随机后缀。
- **FR-40 后端纵切**：`services/notifications.py`（本地 JSON + flock + **(kind,ref) 未读去重** +
  容量修剪不丢未读 + **失败通知带修复入口**）；runengine 三处接线（成功/失败/等门→
  gate_pending，通知尽力而为不致败 Run）；API 三端点（GET list / {id}/read / read-all）。
- **FR-41 后端纵切**：`services/authoring.py`（断句+转折词二次切分、4–6 场聚合带理由、
  组件关键词映射、镜头 2–3 预设不自动应用、读时校验**复用 timeline_ops.READ_CPS=5.2**、
  规则表可导出）；API：POST /projects/{id}/suggest（Pydantic 模型）+ GET /authoring/rules。
  纯本地规则零网络依赖（代码审计断言）。
- **lint 大幅下调**：B008（Depends 出现在参数默认值）与 FastAPI 核心惯用法冲突 →
  **配置级忽略**（server/pyproject [tool.ruff.lint]，126 处全是路由声明——配置裁定非代码
  放宽）；routes.py 四处手修。**基线 314/364/387 → 194/244/240**。

实测（命令含 cwd）：
- `pytest tests/unit/test_notifications.py tests/unit/test_authoring.py -q` → **12 passed**
  （去重/已读/修剪/修复入口/API/接线 + ①300 字 1s 内 4–6 场带理由 ②草稿层 ③零网络
  ④断句重组逐字等于原文）
- `cd server && uv run pytest tests -q` ×2 → **396 passed ×2**（181.62s/179.77s，0 skip）
- 治理 **17 项全 ✓**；守卫 **PASS**（collected=396）；棘轮 **194/244/240** 全 ✓；tsc 0；DB 11

真渲染证据：无（本轮无渲染路径改动）。

没验的（诚实边界）：
- **FR-40 前端（铃铛面板/命令面板 Cmd+K/20 命令可搜/纯键盘 e2e_fr40_keyboard.py）未做**——
  还差：web/src/lib/commands.ts 命令注册表、通知面板组件（role=alert/aria-live）、
  面板/快捷键接线、e2e_fr40_keyboard 真跑。后端 API 已就绪（三端点全测试）。
- **FR-41 前端（建议面板 UI/接受-拒绝交互/断网抓包证据）未做**——还差：编辑器内建议
  草稿层 UI、接受→build_timeline_doc 落草稿、lsof/抓包证据。后端建议引擎+验收①③④
  的纯本地证据已就绪。
- **B4 a11y**：新增后端无 UI 面；前端 aria 计数仍是 1——随 FR-40 前端批一起做。

提交：见下一条 git log（feat(fr40/fr41-backend)）

遗留/待决策：push（22 个本地提交）、LICENSE 类型、devDependency（a11y lint）、
VACUUM、ffmpeg 许可口径——全部 §8，等老板。

### 轮 11 · 老板第二轮决策四则落地（MIT / VACUUM / a11y 棘轮 / 范围「全都要」+ 新 H10）· 2026-11-06 晚

> 本轮由**审查方亲手执行**（不是开发模型）：老板以选择题给出四项决策，其中两项当场做完，
> 另两项写成今晚的活（§14 范围 + §15 H10）。轮 10 尾行的「遗留/待决策」五项**全部清零**。

**决策 → 动作 → 实测**

1. **LICENSE = MIT**
   - 新增 `LICENSE`（1078B，MIT 正文，`Copyright (c) 2026 FilmFlow contributors`）。
   - README 新增「许可」节，明写**三块不受 MIT 覆盖**：`vendor/fy-code-animation/`（免费用/分享、**禁包装成付费课程或付费 skill**）、
     341 风格库（仓库外）、`rumor-39s` 参考片（仓库外）；ffmpeg/系统 Chrome 是本机依赖、不构成分发传染（这就把轮 10 挂着的「ffmpeg 许可口径」一并答了）。
   - 引用真实性核验（不是写了就完）：`vendor/fy-code-animation/LICENSE.md` 存在；
     库内 `许可与来源.md` 与 `第三方许可/` 存在（路径取自 `vendor/style-library.path`）。
2. **VACUUM 现在做**
   - 前置备份 `~/filmflow-backup-20261106-pre-vacuum.db`（`sqlite3 .backup`，WAL 安全）。
   - `PRAGMA page_count` **9083 → 6349**；库文件 **37,203,968B → 26,005,504B**。
   - 不变量逐条对照（`integrity_check=ok`、`foreign_key_check` **0 行**）：
     project **11** / draft **53** / run **44** / artifact **1744** 前后一致；
     演示 docrevision **174=3 / 188=28 / 211=37 / 227=58** 前后一致（保护面零接触）。
   - dev 双服务重启载入，随后治理/守卫/全量测试全在新库上复跑通过。
3. **a11y lint 依赖（devDependency）+ 棘轮装上**
   - `web/eslint.config.mjs`：`eslint 10.14.0` + `eslint-plugin-jsx-a11y 6.10.2` + `typescript-eslint 8.72.1`（`pnpm ls --depth 0` 实测版本，只进 devDependencies，不进运行时 bundle）。
     `linterOptions.noInlineConfig` 是**必须的**：仓库里有引用未加载插件的内联 `eslint-disable`（`@next/next/no-img-element`），否则 9 条 "rule not found" **error** 假红。
   - `scripts/lint_a11y.py`：**只计带 `ruleId` 的消息**（配置类 null-ruleId 不计，否则基线被 9 条噪声灌成 69），`error` 必须 0，`warn` 走「只降不涨」棘轮，降了 `--update` 写回。
   - 基线：`docs/reports/lint-baseline.json["a11y"] = {warn: 60, error: 0}`；`web/package.json` 加 `"lint:a11y"`。
   - **反向验证（防假绿）**：人为把基线改成 59 → `FAIL: a11y warn 涨了 59 → 60`；还原 → `PASS`。
     实测分布：`label-has-for` 28 / `control-has-associated-label` 14 / `no-static-element-interactions` 7 /
     `click-events-have-key-events` 6 / `media-has-caption` 5（其余为长尾）。
   - 口径区分（写清免得 H8 误读）：棘轮量的是**违规数**，H8 说的「a11y 现值 1」量的是**业务代码里 aria/role 属性密度**——两件事，前端批要同时推进两边。
4. **今晚范围 = 全都要**（Wave H + H9 + FR-40 前端 + FR-41 前端）→ 任务书 §14 落成硬纪律：
   固定顺序、时间不够**从队尾 FR-41 截断**、台账每项只有「闭合」或「差哪一步」两种状态（禁「基本完成」）。
5. **漂移防线 = 诊断 + 重锚，不是硬失败** → 新增 **H10**（任务书 §15）：环境指纹补齐（含 `RENDERER_VER`/`EXECUTOR_VERSION`/字体缓存 sha）→
   守卫逐项打印「一致 / 漂移（旧值→新值）」并给出可直接照做的 `golden_run.py --update --reason` 命令 → **exit 0**
   （明写不许改成 fail-closed：环境一升级就把整夜循环锁死不是老板选的口径）→ `updateHistory` 的理由与当时真实环境互证，伪造即红。

**棘轮第一次咬住本轮自己**（这是它该干的事，不是事故）：新脚本 `scripts/lint_a11y.py` 带 1 处 `F541`（无占位符 f-string）→
`repoRootCwd 244→245`、`ciScope 240→241` 当场变红。**修代码不抬基线**，改完回 194/244/240。

**文档同步**（现值处只写当前实测，历史写中文）：
- HANDOFF 顶部：`EXECUTOR_VERSION` 由残留的 **2.16.0 修成 2.17.0**（含升版理由）、ruff 由 **339/405 修成 194/244/240** 三口径、
  加 a11y 第四口径、加「2026-11-06 晚 老板第二轮决策四则」块；H9 那句「三个方案待老板选」改成**已选双 job**。
- AGENTS 门禁清单：加「许可（MIT + 三块豁免）」与「a11y 棘轮」两条；`364 passed` 修成 **396 passed**（本轮实测）；
  fresh-clone 措辞按 H4 收窄为「本机干净 clone 实测 READY，真干净机器未验证」；FR-40/41 改成「后端纵切已交付 / 前端＝H8」；
  「下一步」由作废的「§六 未闭项 → 才谈 FR-40/41」改成 §11→§13→§15→FR-40 前端→FR-41 前端。
- 任务书 §12 第 5 条（VACUUM/LICENSE/devDependency 悬案）划废并指向 §14；新增 §14（决策表）+ §15（H10）。

实测（命令含 cwd）：
- `cd server && uv run pytest tests -q` → **396 passed**，220.63s，**0 skip / 0 xfail**
- `uv run --project server python scripts/verify_p1_governance.py` → **17 项全 ✓**（`PASS: P1 治理复核全部通过`）
- `uv run --project server python scripts/check_docs_consistency.py` → **PASS**
  （`EXECUTOR=2.17.0 · 迁移[1..5] · collected=396 · governance=17 · DB=11 · 裸 dict=0`）
- `python3 scripts/lint_a11y.py` → **error=0 · warn=60（基线 ≤60）· PASS**
- `cd web && npx tsc --noEmit` → **0 错误**
- push：`4650cd0..dc89f2c`（`git rev-list --count origin/master..HEAD` → **0**）；本轮 docs 批次随后再推一次。

真渲染证据：无（本轮无渲染路径改动；VACUUM 只动库文件布局，golden/锚点未重跑——
若要视觉级结论请跑 `golden_run.py --project 5s --resolution original`，那是 H10 的活）。

没验的（诚实边界）：
- **H10 未实现**（本轮只写下判据，代码一行没动）。
- **Wave H1–H8 / H9 双 job 未动**——本轮只做老板当场可执行的两项 + 把另两项变成可验收的任务书条目。
- a11y 棘轮装上后**没有修任何一条现存违规**（60 条原样入基线）：这是「先止血再治」的刻意选择，
  真降要随 FR-40 前端批做，否则就是无谓 churn。
- `pnpm-lock.yaml` +1902 行是 eslint 依赖树（`pnpm ls` 已核版本）；未审每个传递依赖的许可，
  若老板要 SPDX 级清单，那是独立一次 `pnpm licenses` 导出。

提交：`dc89f2c`（feat: MIT + a11y 棘轮）与本轮 docs 提交（docs(decisions): 轮 11）。

---

### 轮 12 · Wave H 开工：H1 在飞判据 + H2 httpx 守卫（goal 模式第一轮）· 2026-11-06 05:1x

**开工即撞出一个必须入账的库事实**：为 VACUUM 重启 dev 那次（12:40:29），`jobs.expire_parked` 依 72h 策略
又收走了 **2 条** parked 作业（`app.log`：`expiredParked=[85, 86]`；同批 startup 还 `removedProfiles: 10`，属正常清理）。
于是 **retry_wait 现值 7 → 5**（job 130/131/132/133 = rumor-39s 的 run 317–320，job 147 = run 335），
文档里"现存 7 条 retry_wait 未动"两处按现值改写并注明成因。行为仍符合老板已认可的策略，**没有新越权**——
但它动的是保护项目的行，所以照纪律入账。

#### H1 · `_inflight_jobs_using` 的 queued 真空窗（真缺陷，不是口径偏好）

旧实现 `stamp = heartbeat_at or started_at or created_at` + `now - stamp > 120 → 不在飞`：
一条 **queued 排队等 Chrome 锁**超过 120s 的作业被判"不在飞"，于是资产可以在它**即将执行的瞬间**被删掉，
Run 当场 `E_ASSET_MISSING`。这与 `project_cleanup._job_is_live` 也不一致（后者 stamp None 视为在飞）。

新三条判据（每条都写进 docstring 的理由，不是"看起来对"）：
- **queued 一律在飞**，不看时间；
- **leased/running 只看心跳/开始时间的 120s 窗**（同 `_job_is_live`，僵尸行交给 `jobs.recover`）；
- **retry_wait 不在飞**（等人工门可以停几天；恢复时本就要重走 E_ASSET_MISSING 检查）。

测试 2 条（`server/tests/unit/test_assets.py`）：
- `test_h1_queued_job_blocks_delete_even_when_old`：queued + `created_at` 推到 10 分钟前 → 仍 409，
  `detail["details"]["inflightJobs"] == [job.id]`；
- `test_h1_retry_wait_and_zombie_rows_do_not_block_delete`：retry_wait（心跳新鲜）+ running（心跳 600s 前）
  → `_inflight_jobs_using == []` 且删除放行（钉住 R8 那次"parked 挡死删除"的教训不许回退）。

**踩到并修的测试卫生问题**：`_png()` 是确定性字节 → 两个测试的资产 **sha 相同**，前一个测试留下的 queued 行
被后一个测试看见（首跑就是靠这个假失败暴露的）。改成各测试不同像素色 + `finally` 清自己的 Job 行。

**反向验证**：把 `alive = True` 换回 `created_at` 兜底 120s → `DID NOT RAISE ApiError`（测试红）；还原 → 20 passed。

#### H2 · 本机 httpx 守卫补上"模块级便捷函数"这个洞

F01 类缺陷（毒 `NO_PROXY` 带 IPv6 条目 → httpx 默认客户端解析即 `InvalidURL`）此前**没有任何静态防线**：
`test_f01_http_env.py` 只测行为，不扫调用点，所以 `httpx.get(...)` 这种自己内部建 Client 的写法完全漏网。
- 修 `scripts/e2e_timeline_100.py:41`：`httpx.get(f"{BASE}/health", timeout=3)` → 补 `trust_env=False`（实测全仓**只有这一处**漏网）。
- 新守卫 `server/tests/unit/test_h2_http_trust_env_guard.py`（3 条，**用 `ast` 不是 grep**）：
  扫 `scripts/**/*.py` + `server/app/**/*.py`，`httpx.{Client,AsyncClient}` 与 `httpx.{get,post,head,put,patch,delete,request,options}`
  凡无 `trust_env` 关键字即点名；扫描面 `assert len(files) > 40` 防"扫描目录被误改空"式的假绿；
  一条自证测试用合成样例证明**真调用会被抓到、带 trust_env 的放行、注释里的假调用不误报**。
- **反向验证**：把那处 `trust_env=False` 删掉 → `test_no_httpx_call_without_explicit_trust_env` FAIL；还原 → PASS。

实测（命令含 cwd）：
- `cd server && uv run pytest tests -q` → **401 passed**（215.23s，**0 skip / 0 xfail**；396 → +5 = H1×2 + H2 守卫×3；
  unit 361 / integration 33 / BDD 7 逐目录 collect 实测）
- `uv run --project server python scripts/lint_ratchet.py` → **194 / 244 / 240 全 ✓**
  （新代码首跑 +2/+2：两处 `RUF059` 未用解包变量——修代码不抬基线）
- `uv run --project server python scripts/check_docs_consistency.py` → **PASS**（collected=401）
- 文档现值同步 7 处（HANDOFF×4 + AGENTS×2 + 任务书 H9 判据×1），另加 retry_wait 现值 2 处。

没验的（诚实边界）：
- H1 的新语义**没有真渲染级验证**（不涉渲染路径，判据靠 2 条单测 + 反向验证）。
- **两处判活面仍不是同一份实现，且 retry_wait 上故意不同**（本轮实测差异，写清免得以后误当 bug）：
  `project_cleanup._ACTIVE_JOB_STATUSES` **含** `retry_wait`，再过 `_job_is_live` 的 120s 心跳窗 →
  刚 park 下（心跳新鲜）的作业会**挡住项目删除**（可 `force=true`）；
  `assets._inflight_jobs_using` 则**永不**把 retry_wait 算在飞（等门期间允许整理资产，恢复时重走 E_ASSET_MISSING）。
  queued / leased / running 三条现在口径一致。收成公共函数是卫生工作，本轮没做，也没动 `project_cleanup`（它现在是对的）。
- H2 守卫只扫 `httpx`；`urllib.request` / `aiohttp` 之类不在面内（实测全仓无 aiohttp，`urllib` 用于本地文件路径解析，不建连接）。


---

### 轮 13 · H3 磁盘/库卫生棘轮（治理第 18 项，fail-closed 而非"只报告"）· 2026-11-06 05:2x

**为什么不做成"报告模式"**：同类残留一夜里漏过两次（65MB 孤儿目录 `r3-camera-260`、4 条僵尸 draft），
台账当时都写着"已清"。报告没人天天看，等于没有防线——所以第 18 项**直接 fail-closed**：
以后谁漏了，治理当场红。（任务书 H3 允许"只报告也算"，这里按更严的口径做，理由入 docstring。）

**三处改动**：
- `scripts/cleanup_projects.py`：新增 `orphan_dirs(session)`（`filmflow-projects/` 下没有任何 Project 行指向的目录；
  排除 `.acceptance`，那条由第 14 项管）与 `hygiene_counts(session)`（僵尸 draft + 孤儿目录 + 可核对的 id/name 清单）。
  路径来自 `settings.workspace_roots[0] / "filmflow-projects"`，**不硬编码主目录**（P1-19 的口径）。
- `scripts/verify_p1_governance.py`：新增第 **18** 项 `check_disk_hygiene()`，放在 `check_no_demo_writes` 之后
  （孤儿/僵尸计数只有在自建项目全部回收之后才有意义），**判据复用 `cleanup_projects.hygiene_counts`**
  ——守卫和清理工具不许各写一套判据（历史上这类分叉就是"守卫说没事、工具说有 4 条"的来源）。
- `scripts/_acceptance.py`：draft 回收条件从"只读 `payload["root"]`"改为 `_draft_points_at()`——
  递归扫 payload 任意深度的路径值命中项目根（含子目录）即算本项目草稿，兼容原样/`resolve()` 两种写法。
  **刻意不按 `draft.name` 匹配**并在 docstring 写明理由：草稿名就是项目标题，自建项目允许与真实项目同名
  （`golden-5s` 既是脚本名也是演示名），按名删会误删别人的草稿，比漏删更糟。
  诚实标注：生产库 8 个 payload 键里**目前**只有 `root` 是路径，所以这条今天行为等价，它是防"键名漂移"，
  不是宣称修好了某个正在发生的泄漏。

**踩到并当场修的自己的编辑事故 ×2**：
① 插入函数时吞掉了 `def _parked_jobs(...)` 后的换行 → `IndentationError`（由测试收集阶段暴露，不是靠肉眼）；
② 一处 docstring 把"向导把路径塞进别的键"写成了既成事实 → 先查生产库 `json_each(payload_json)` 的键分布，
   发现只有 `root` 是路径，**改成诚实表述 + 标明这是防御性改动**。

**测试**（`server/tests/unit/test_h3_hygiene_ratchet.py`，6 条）：
孤儿目录识别（含"登记成行以后就不该再报"）、僵尸 draft 计数与 id 清单、
`_draft_points_at` 覆盖嵌套/列表路径 + **拒绝前缀相似陷阱**（`/a/scratch-1` vs `/a/scratch-10`，
误命中就会删掉别人项目的草稿）、治理第 18 项接线断言（`ok("18` 标签 + `check_disk_hygiene()` 调用 + 同源判据），
以及**反向验证**：tmp 里造一个"目录在、行不在"的孤儿 → `pytest.raises(AssertionError, match="孤儿目录")` 真的红。

**这条测试自己返工两次，两次都是"测试写错"而不是"代码写错"——值得入账**：
① 第一版断言绝对计数 `zombieDrafts == 1`，单跑绿、**全量红**（366 passed / 1 failed）：
   unit 库跨测试共享，别的测试也会留下指向已删目录的草稿。改成**增量断言**（`after == before + 1`），
   判据照样钉死，但不依赖执行顺序。
② 改增量后**单跑也红**了：`alive.mkdir()` 写在取基线**之前**，基线里已经含了那个孤儿 →
   `1 == 1 + 1` 必然失败。把 mkdir 挪到取基线之后，并在那行加注释「基线必须在造任何东西之前取，
   否则增量断言自己骗自己」。
教训：**新写的"计数类"测试必须在 `tests/unit` 全目录跑一遍再宣布绿**，只跑单文件会漏掉顺序依赖。

实测（命令含 cwd）：
- `cd server && uv run pytest tests/unit/test_h3_hygiene_ratchet.py -q` → **6 passed**
- `uv run --project server python scripts/verify_p1_governance.py` → **18 项全 ✓**，
  新增行 `✓ 18 磁盘/库卫生棘轮：孤儿目录 0 个、僵尸 draft 0 条（判据与 cleanup_projects 同源）`
- `uv run --project server python scripts/lint_ratchet.py` → **194 / 244 / 240 全 ✓**
  （新代码首跑 +6：两处 I001 + 四处 RUF100 `noqa E402` 在 scripts 口径不生效——`--fix` 清掉，不抬基线；
  改完测试后又咬住 1 处 F401（去掉 `s.exec(select(...))` 后 `select` 变未用）——**棘轮这一轮共红过两次，两次都是我的新代码**）
- `cd server && uv run pytest tests -q` → **407 passed**（collected 407 = unit 367 / integration 33 / BDD 7，0 skip / 0 xfail）
- 文档同步 10 处：`17 项`→`18 项`（HANDOFF §0.6.3、AGENTS 顶部实测行 + 先跑什么注释、任务书 §2）；
  `401`→`407`（HANDOFF ×4、AGENTS ×2，均写成中文说明"+11 是 H1×2 + H2 守卫×3 + H3×6"）。守卫 **PASS**。

真渲染证据：无（本轮纯治理/卫生面）。

没验的（诚实边界）：
- 第 18 项**没有对"生产库真实泄漏"做过现场演练**（现在生产库是 0/0，无法在不破坏纪律的前提下造泄漏）。
  反向验证是在 tmp + 隔离测试库里做的，能证明判据与抛出行为，不能证明"CI/治理真跑时也会红"——
  下一次任何脚本真留孤儿时那才是首次实战。
- `orphan_dirs` 只看顶层目录，不看嵌套在项目根内的残留（那是 `delete_project` 的 `remove_dir` 面）。
- `_draft_points_at` 的行为等价性已说明；**`destroy()` 的端到端回收没有在真验收脚本上复跑**
  （验收脚本会在 H9 之后的 CI 里被更严格覆盖，届时 `verify_r3_templates` 的"回收 N 条"输出是它的自然证据）。
- 治理步数 17→18 后，任何还在引用"17 项"的旧台账轮次条目按历史保留（守卫只认现值处）。

---

### 轮 14 · H9：CI 双 job + 测试环境依赖的静态防线 · 2026-11-06 05:4x

**先做了一次"本机复刻 CI"的探针**（这一步改变了整批做法）：
`env PATH=/usr/bin:/bin:/usr/sbin:/sbin uv run pytest tests/unit tests/bdd -m "not requires_*"` ——
`uv` 用绝对路径、PATH 里不留 homebrew，`shutil.which("ffmpeg")` 就跟 runner 一样解析不到。
结果精确复现 CI 的三条红：`test_audio_v2.py` ×3 `FileNotFoundError: 'ffmpeg'`，**且全仓只有这三条**
（367 passed / 10 deselected / 3 failed）。这意味着不用等 CI 就能验证 `ci-lean` 会不会绿。

**四处对齐**（H9-a/b/c）：
| 动作 | 落点 | 为什么这样而不是别的做法 |
|---|---|---|
| `pytestmark = pytest.mark.requires_ffmpeg` | `server/tests/unit/test_audio_v2.py` | 本文件每个用例都经模块级 `_wav()` 真调 ffmpeg；逐条加标记会漏掉以后新增的用例，模块级才是对的粒度 |
| 两处静默 skip → `@pytest.mark.requires_system_font` / `requires_cached_font` | `test_assets.py:101/116` | 原写法"字体不在就 skip"在本机永远不触发、在 CI 上少跑两条没人知道；改成缺环境**硬失败**，只有 `--allow-missing-env` 才可见 skip |
| 第三处同类 | `test_c02_font_pin.py:29` → `requires_cached_font` | 同上（干净机器走下载路径由 sha 钉把关，逻辑不变） |
| conftest 注册两个新 marker + `_env_guard` 加两条判定 | `server/tests/conftest.py:63-127` | 判定路径与用例真正读的字体路径同源（`_PROD_HOME`/系统绝对路径），防止门禁和测试说两套话 |

**静态防线（长期值钱的那半条）**：`server/tests/unit/test_h9_env_marker_guard.py`，3 条，用 `ast` 不用 grep：
1. `test_env_dependent_tests_declare_markers`——凡模块里出现 `subprocess.{run,Popen,call,check_output,check_call}`
   且 argv 字面量含 ffmpeg/ffprobe（或 chrome 类），该模块的 `pytestmark` 或**每个能走到那次调用的测试函数**必须有 `requires_*`。
   **关键设计**：还追一层"模块内辅助函数"——`test_audio_v2` 的三个用例本身不写 subprocess，只调 `_wav()`；
   只查函数体就正好漏掉我们要防的那个案例。
2. `test_no_bare_pytest_skip_outside_env_gate`——裸 `pytest.skip` 只许在 conftest 的 `--allow-missing-env` 分支
   或**显式豁免表**（`SKIP_EXEMPT`，键相对 `server/tests/`，每项必须带理由）里。
3. `test_skip_exempt_table_is_not_stale`——反向过期检测：豁免表里登记的文件如果已经没有裸 skip，**必须删掉登记**。
   没有这条，豁免表会变成永久停车场。

**反向验证（两条都真做过，不是"应该能抓到"）**：
- 造一个临时 `test_zz_reverse_probe_tmp.py`：模块级 `_mk()` 调 ffmpeg、测试函数无标记
  → 守卫红：`unit/test_zz_reverse_probe_tmp.py:11 … 调了 ['requires_ffmpeg'] 却没有标记`；删掉文件 → 3 passed。
- 探针本身（PATH 剥 ffmpeg）就是"标记缺失会红"的现场证据，见上面 3 failed。

**CI 改成双 job**（`.github/workflows/ci.yml`）：
- `ci-lean`：lint 棘轮 + tsc + `pytest -m "not requires_ffmpeg and not requires_chrome and not requires_style_library and not requires_system_font and not requires_cached_font"`，
  **零安装**——它绿才叫绿，任何未标记的环境依赖会在这里红。
- `ci-env`：`apt-get install ffmpeg` 后跑 unit+bdd 带 `-rs --allow-missing-env`，把跑了多少/skip 多少与原因写进 `$GITHUB_STEP_SUMMARY`。
- `scripts/ci_local.sh` 从四步改五步，**第 2 步在本机就复刻 ci-lean**（绝对路径 uv + 剥 PATH + 风格库指向不存在），
  以后不必 push 才知道 CI 会不会红。

**一处刻意不做（诚实边界，不是偷懒）**：H9-b 原本要求给 `ci-env` 造一个"最小合法风格库 fixture"。
实测该 feature 断言的是真库的**十个来源集计数**与**库版本哈希**——造假库等于造假绑定，
正是老板在 B6/ADR-0014 里明确禁止的那件事。所以风格库三条在 `ci-env` 走**可见 skip**（`-rs` + summary 写明理由），
不写成"已覆盖"。这一条已写进 ci.yml 的注释，防止下一个人顺手把假 fixture 加回来。

实测（命令含 cwd）：
- `bash scripts/ci_local.sh` 五步 → **1 ✓ 棘轮 / 2 ✓ 367 passed + 10 deselected（无 ffmpeg 环境）/ 3 ✓ 377 passed（unit+bdd 真环境）/ 4 ✓ tsc / 5 守卫**
- `cd server && uv run pytest tests -q` → **410 passed**（237.65s，0 skip / 0 xfail；collected 410 = unit 370 / integration 33 / BDD 7）
- `uv run --project server python scripts/verify_p1_governance.py` → 18 项全 ✓（本轮无新增治理步骤）
- `uv run --project server python scripts/check_docs_consistency.py` → **PASS**（先 FAIL 4 处 407→410，按现值同步后过）
- `uv run --project server python -m ruff check …`（新文件）→ 首跑 1 处语法错（中文串里用了直引号）+ 2 处路径口径 bug（`TESTS.parents[1]` 拼错、
  AnnAssign 分支写了没用的代码）→ 全部改对，棘轮 **194/244/240** 未抬基线

没验的（诚实边界）：
- **`ci-lean` / `ci-env` 的首次真绿要看这次 push 之后的 `gh run`**——本机复刻只证明" deselect 集合在无 ffmpeg 环境下自洽"，
  不能证明 runner 上没有别的差异（例如 Ubuntu 的 `/System/Library/Fonts` 本就不存在 → 那两条 marker 会 deselect，符合预期；
  但 `sqlite`/`libGL` 一类依赖只有真跑才知道）。推完必须 `gh run list` 核对并贴链接。
- `ci-env` 的 Chrome 类用例：本机 `detect_chrome()` 走 `/Applications` 绝对路径，**无法在 macOS 上模拟"没有 Chrome"**，
  所以"未标记却依赖 Chrome"的漏网面只有 runner 能证明。若 `ci-lean` 真跑出这类红，当场修并补记一轮。
- `-rs` 的 skip 计数进 summary 只在 `ci-env` 里做；本机 `ci_local.sh` 第 3 步也带 `-rs`，但输出没落进任何台账（下一轮如需要可 tee 到文件）。

---

### 轮 15 · H9 的 CI 首绿 + H4 fresh-clone 体检双口径 · 2026-11-06 05:5x

**H9 的完成判据 1 已经拿到（这是本轮最值钱的一行）**：
push `4766e27` 触发 run **42170418486** →
`ci-lean（零安装必绿：lint 棘轮 + tsc + 无环境依赖用例） → completed success`。
`gh run view 42170418486 --json jobs` 原文可复核；`ci-env` 在本轮提交时仍 `in_progress`，
它的结果（跑了多少 / skip 多少）留到下一条记录，不在这里替它宣布。
本机复刻（轮 14 第 2 步）与 runner 实测**两侧都绿**，才算这条判据闭合。

**H4：`scripts/bootstrap_fresh_clone.sh` 拆成两个口径**（复审原话是"措辞比证据强"，那就把措辞与证据绑进退出码）：
- `--require-all`（默认，本机口径）：任一外部依赖缺失 → `exit 1`，且每条缺失都打印
  `✗ E_ENV_MISSING: <项>` 并汇总成机器可读清单。"READY"这个词现在只在 exit 0 时才会出现。
- `--check-only`（CI 口径）：同样逐条点名，但**恒 `exit 0`**。
  理由写进脚本头注：runner 上没有系统 Chrome / macOS 字体 / 341 风格库是本项目的**已知事实**，
  不是回归；把它做成必然红的步骤，只会让真信号（ci-lean 的红）被淹没——H9 首跑就是靠人肉读日志摸根因的。
- 未知参数 → `exit 2` + 用法（防"拼错 flag 静默按默认跑"）。
- `ci-lean` 新增一步 `bootstrap --check-only`，缺失清单进 `$GITHUB_STEP_SUMMARY`。

四种退出码**全部实测**（含反向）：
| 命令 | 期望 | 实测 |
|---|---|---|
| `bash scripts/bootstrap_fresh_clone.sh` | READY + 0 | `exit=0`，打印 4 条建议验收命令 |
| `env PATH=/usr/bin:/bin:/usr/sbin:/sbin bash … ` | 缺失 → 1 | `exit=1`，**13 条** `E_ENV_MISSING`（首三条：uv / ffmpeg / python 3.13 未检出） |
| 同上 + `--check-only` | 报告不红 → 0 | `exit=0`，尾部打印"已知缺失，报告进 summary" |
| `bash … --bogus` | 用法 → 2 | `exit=2` + `用法：… [--require-all\|--check-only]` |

措辞同步：AGENTS 顶部早前已改成"**本机**干净 clone 实测 READY；换一台真干净机器仍未验证"（轮 11），
本轮把 `--require-all` 指为拿到该结论的唯一途径，`--check-only` 明确不许被当成 READY 证据。

实测（命令含 cwd）：
- 上表四行即全部证据（同一台机器、同一份 clone、无网络动作）。
- `gh run view 42170418486 --json jobs` → ci-lean `success`；ci-env `in_progress`（提交时点）。

没验的（诚实边界）：
- **`--check-only` 在真 Linux runner 上的输出还没落地**（这一步随本轮 push 才第一次进 CI，
  结果在 run 42170418486 之后的那一次里）。本机只证明了退出码与清单文本。
- bootstrap 的检查项仍偏 macOS（Chrome 候选路径是 `/Applications/...`）；Linux 上的
  `chromium` 包路径没进候选——这属于"渲染级 CI"那一批的活（要先把字体/风格库指纹参数化），本轮不扩面。
- H4 的"文档措辞收窄"只覆盖 AGENTS 与脚本头注；`HANDOFF.md` 里 B9 时期的历史叙述按日期标记保留。
