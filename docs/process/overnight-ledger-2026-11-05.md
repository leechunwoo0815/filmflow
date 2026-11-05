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
