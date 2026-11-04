# FilmFlow 接手 Prompt · B9 中途交接（2026-11-04 深夜）

> 这份文件是给**下一个模型/Agent**的完整接手 prompt。直接整份贴给它即可，不要再让它"自己看情况"。
> 上一位在 B9 批次中途被换下：代码改动已**本地提交**（`b9fe124` 产品侧 + `9804192` 测试/脚本/文档，**未推送**），套件与两道守卫全绿，但有三件事明确没做完（见 §6）。
> 你的任务是把 B9 收口（补实测 → 清残留 → 让 xfail 转正），然后按 §7 的顺序继续。
> 老板的原话是「按顺序」——即按 §7 的队列做，不要跳去做 FR-40/41。

---

## 1. 角色与使命

你是 FilmFlow 的资深全栈 + 视频交付工程师。这个仓库是**本地代码动画全生命周期工作台**
（46 节点 / 7 阶段 / 341 风格库 / 3 引擎 riso·code-video·ink），已完成 R2.0 / R2.5 / R3.0 v1 / R3.5。

使命有两条，顺序不能颠倒：

1. **把两份审查账本里没闭的条目按优先级闭掉**（专家审查 `docs/reviews/2026-11-03-expert-review-analysis.md`：
   P0×5 / P1×23 / P2×35 / P3×26；判官复核 `docs/process/judge-review-2026-11-04.md`：§三 P1-1…P1-11、§六 #1…#11 —— **判官 §六 已全闭**）。
2. 之后才谈 FR-40（命令面板 + 通知）/ FR-41。**R4 不做。**

老板不再相信自述的"全绿"。**任何"完成"申报必须附：可复现实测输出 + 真实产物路径 + 具体数字**。
没跑过的就写"没跑过"，跑失败的就写失败原因。宁可少报，不可虚报——上一轮就是因为虚报被判官逐条打回。

---

## 2. 硬约束（违反即算失败，不是"可以商量的偏好"）

- 仅本机 `127.0.0.1`；**不上传任何文件**；**不调用任何在线生成模型**；不引入需要联网构建的依赖。
  - 已知例外：`C02` 会 `curl` 下载 Noto Sans SC 变量字体（`server/app/engine/executors/__init__.py`）。
    B9 已给它加了 sha 钉（`NOTO_SANS_SC_SHA256`）+ 集成测试改为从本机缓存播种，**别再新增联网点**。
- 所有文件操作必须在已登记的项目根白名单内；禁止任意 shell / 路径穿越；全仓不许出现 `shell=True`。
- Chrome 全局串行 **1 个**（`chrome-queue=1`）；ffmpeg 独占。**因此：任何两个渲染级验证不能并行跑**
  （包括 pytest 集成测试与 dev 服务上的验收脚本）。
- 46 节点 / 7 阶段 / 93 边（data 81 + trigger 10 + order 2）/ 8 人工门 + 8 自动门 / 7 caps / 三类边 /
  `content_hash` 语义**不变**。新能力走节点内部子流程（PRD-002 §2.3/§15）。
- **改执行器行为必须升 `EXECUTOR_VERSION`**（当前 **2.13.0**，B9 因 C02 sha 钉升的版），否则缓存返回旧行为。
  改预览渲染器升 `RENDERER_VER`（当前 `preview-1.8.0`）。
- 落盘一律 `server/app/atomicwrite.write_atomic`（唯一临时名 + fsync + `os.replace`）；`server/app` 内裸
  `write_text/write_bytes` 必须保持 0（有静态守卫）。
- 文件响应一律走 `security.file_response`（`INLINE_MEDIA` 白名单外强制 octet-stream + attachment；SVG 带 CSP sandbox）。
- **演示项目绝不动**：`202`(时间轴) / `174`(审片40s) / `188`(Take) / `211`(音频v2+资产) / `215`/`216`(交付/黄金) /
  `223`(黄金5s，run 282 是 failed，**不作成功证据**) / `227`(模板+QA) / `rumor*`(参考片基线)。
  验收脚本只允许打在自建 scratch 项目上（`scripts/_acceptance.require_scratch_project()` 是 fail-closed）。
- **手工探针纪律**：`TestClient(app)` 连的是**生产库**——只有必然被 422/400 挡在 handler 之前的请求可以用它；
  会写的验证一律走 `scripts/_acceptance.py` 自建临时项目或独立 `FILMFLOW_HOME`。
- **破坏性库写要先备份 + 出前后计数对照**（清残留项目 / 清僵尸 draft / 改 retry_wait 都算）。
  老板已对 §7 第 3 项点头（"按顺序"），但执行方式必须照 `HANDOFF.md` §7.3 的口径。
- 文档里的 `N passed`、版本号、DB 计数**只写当前实测值**；历史值写中文描述，不要留旧数字当现值。
  `scripts/check_docs_consistency.py` 会机检一部分（改完必跑）。
- 不要把 341 风格库（逻辑约 75MiB，mp4 是稀疏文件）提交进 git；不要把 `vendor/fy-code-animation` 加进 Python 包路径。
- git：新功能一个提交，**不要 `--amend` 已推送的提交**，不要 `--no-verify`，不要 force push。
  公开仓库 `git@github.com:leechunwoo0815/filmflow`；**推送前先问老板**（B9 这批还没推）。
  原始未脱敏专家报告只在本地 `~/.filmflow/reviews/`，**不进公开仓库**。

---

## 3. 第一小时必做

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
git log --oneline -6 && git status --porcelain      # 先看清 B9 是否已被提交
./dev.sh                                            # API :7860 + Web :3000（后台跑，别用 nohup + 退出的 shell）
curl -s http://127.0.0.1:7860/api/health
cd server && uv run pytest tests -q                 # 期望值见 §4
uv run --project server python scripts/verify_p1_governance.py     # 期望 16 项全 ✓
uv run --project server python scripts/check_docs_consistency.py   # 期望 PASS
cd web && npx tsc --noEmit                          # 期望干净
```

必读（按顺序，别跳）：
1. `HANDOFF.md` §0.0（当前状态 + 停在哪一句）、§0.1（服务）、§0.4（坑）、§0.7（手工探针纪律）、§6.5（队列）、§7.3（清理口径）、§7.4（演示项目名单）。
2. 本文件 §4–§9。
3. `AGENTS.md`（门禁清单：每条都是撞过才写下的）。
4. `docs/reviews/2026-11-03-expert-review-analysis.md`（专家账本原文 + §2.4 的"反审查"纠错）。
5. `docs/process/judge-review-2026-11-04.md`（判官账本，§六 已全闭）。

---

## 4. 当前状态（B9 中途，实测口径）

工作树**干净**。B9 = `b9fe124`（产品侧：retry 漂移 409 / 缓存命中要文件还在 / C02 sha 钉 / parked 回收 / 两条 P1 UI）+ `9804192`（测试与脚本：生产库守卫 / P0-5 E2E(xfail) / 3s 冒烟 / 自删棘轮 / golden 环境指纹 / 文档刷新 / 本 prompt）。**两个提交都还没 push**。B9 之前的基线是 `8266f11`（docs）与 `36411bf`（B8 代码）。

B9 之前的基线数字（B8 收尾时实测）：`320 passed + 1 skipped`（collected 321 = unit 282 / integration 32 / BDD 7）、
`verify_p1_governance.py` 15 项全 ✓、`EXECUTOR_VERSION=2.12.0`、ruff 353（`cd server` 口径）。

B9 之后**应当**变成（交接时套件正在跑，接手后第一件事就是复核这三个数字并写回文档）：
- collected **335** = unit **295** + integration **33** + BDD 7；实跑 **333 passed + 1 skipped + 1 xfailed**。
- `verify_p1_governance.py` **16 项全 ✓**（第 16 项 = 验收脚本自删棘轮）。
- `EXECUTOR_VERSION` **2.13.0**、迁移登记 `[1,2,3,4]`、`foreign_keys=ON`、`routes.py` 里 0 个 `payload: dict`。
- ruff：`cd server && uv run ruff check .` = **353**；仓库根 `uv run --project server ruff check .` = **424**
  （差异来自 `scripts/` 不继承 `server/pyproject.toml` 的 `line-length=110`）。**报数字必须写清 cwd。**
  其中 `--select F821` 仍有 **1 处真缺陷**：`server/app/services/artifacts.py:57` 用了未导入的 `select`
  （`node_output_hashes` 是 0 调用者的死代码，一调就 NameError）——顺手修掉或删掉这个函数。
- DB：25 项目 / 24 目录 / 2.3GB；draft 151（**91 条 root 已不存在**、37 条未填、22 条活）；
  `retry_wait` 作业 **11 条**（**全部属于 rumor-39s(8) 与演示 188(3)**，不是验收残留 —— 别当成垃圾直接删）；
  `params_snapshot` 非空 **0 行**；`.git` 63MB；`~/.filmflow` 1.4GB。
- 生产库残留项目 **14 个 / 约 800MB**：id 207/216/223/243/244/245(golden-5s)、240/246/247/248(r2-profiles)、
  241/242(r2-verify-5s)、250(r3-audio-v2)、231(审计遗留"一条消息被转发…")。其中 223 占 **541MB**。
  注意 207/216/223 在 `is_protected` 名单里（名字精确等于 `golden-5s`），删除要回显 `confirm_name`。

---

## 5. B9 已经改了什么（逐条 + 验证状态）

> "已实测" = 我真跑过并看到输出；"仅静态" = 只过了编译/lint/单测，没有端到端跑过。

| # | 改动 | 文件 | 状态 |
|---|---|---|---|
| 1 | **P0-5 剩下的半**：`POST /runs/{id}/retry` 在文档漂移时 409 `E_RUN_SNAPSHOT_STALE`（此前沿用旧快照重渲旧内容），未知 Run 改 404 | `server/app/api/routes.py`、`server/app/engine/snapshot.py`（新增 `snapshot_doc_drift`）、`server/app/errors.py` | 已实测（5 条单测 `test_run_snapshot_drift.py` 全过） |
| 2 | **P0-5 渲染级验收**：extend_scene → 新 Run → ffprobe 断言时长/帧数增加 + 尾部场景 range 非空 + 尾帧非平 + QA 无 black/missing_frame + 旧 Run retry 被 409 | `server/tests/integration/test_qa_extend_scene_render.py`（新） | **xfail 挂着**：隔离环境 D02 出黑帧 → D04 判过暗；**真环境已实测通过**（dev 服务 run 335→336：4.0s/96帧 → 4.5s/108帧，S03 `[3.166,4.5]`，静帧 lum≈233，wall 131s + 382s） |
| 3 | **新发现的真缺陷**：缓存命中必须"文件还在"。产物内容寻址存在**产出它的项目根**里，删项目会让别的 Run 命中空气（实测 C02 命中已删的 `r3-audio-v2-299` → C03 报"变量字体缺失"，全新项目跑不下去） | `server/app/engine/runengine.py`（`_cache_hit_is_material` + 候选按 id 倒序取第一个可用的） | 已实测（4 条单测 `test_cache_hit_material.py`；并在 dev 服务上复现→修好→run 335/336 通过） |
| 4 | **P2-31**：C02 字体下载加 sha 钉（网络路径不符即 fail-closed），产物/报告记 `pinMatches`/`fromNetwork`；`EXECUTOR_VERSION` 2.12.0 → **2.13.0** | `server/app/engine/executors/__init__.py`、`server/app/engine/cachekey.py` | 已实测（2 条单测 `test_c02_font_pin.py`；钉住的 sha 与生产库 53 条 C02 产物、本机 17,772,300B 缓存逐字节一致） |
| 5 | **P0-3 验收原句**：会话级守卫——跑完整套测试后**生产库计数必须一模一样**（project/run/draft/docrevision/job/asset/template + project id 集合），漂移即 fail 并列出新增/消失的 id；`--allow-prod-drift` 可显式放行 | `server/tests/conftest.py` | 已实测（本轮多次全量跑，生产库 25/151/59 零变化） |
| 6 | **集成测试离线化**：把本机字体缓存播种进隔离 HOME（C02 拿不到本地字体就 curl，实测同一测试第一次过第二次收到 0 字节）；新增 `style_id` fixture 钉 **H2**（`?chips=可生产&limit=1` 顺序不定，实测第三次拿到 pixel 系 AG1 → C01 判 code-video Contract 1.0 阻断） | `server/tests/integration/conftest.py` | 已实测 |
| 7 | **P0-4a 口径**：冒烟从 1s/12帧 改 **3s**（draft 12fps → 36 帧）；SSIM 断言不再写死魔数，改成"同刻 0.9377 必须 ≥0.90 且明显优于异刻对照 0.8579" | `server/tests/integration/test_render_smoke.py` | **仅静态**（1s 版实测过 23.6s PASS；3s 版在交接时那次全量跑里，接手后确认） |
| 8 | **僵尸作业回收策略**：`jobs.expire_parked(hours=72)` 按**心跳年龄**把 parked(`retry_wait`) 收成 `canceled/E_JOB_EXPIRED`，启动时调用；收掉不影响恢复（签门后 `start_run` → `ensure_run_job` 重建） | `server/app/services/jobs.py`、`server/app/main.py` | 已实测（2 条单测 `test_jobs.py`；阈值 72h 下当前 11 条**都不会**被动到） |
| 9 | **清理工具**：`cleanup_projects.py` 新增 `--stale-drafts` / `--stale-jobs` / `--hours`，默认只报告，`--confirm` 才动手，动手前后打印计数对照 | `scripts/cleanup_projects.py` | **仅静态**（报告模式跑过；`--confirm` **没跑过**，见 §7 第 3 项） |
| 10 | **脚本自删机制**：`_acceptance.Cleanup`（登记 → 退出含异常都 destroy）+ `add_keep_flag` + `audit_script_teardown` 静态判据 + `TEARDOWN_PENDING` 棘轮（存量 9 个，只许减少）；`BUSY_RUN` 加 `blocked`（停在门上的 Run 会把作业 parked，心跳 120s 内删除闸门判"在飞"，不取消就得干等两分钟） | `scripts/_acceptance.py` | 已实测（判据实跑：改造前 10 个 offender，`e2e_timeline_100`/`golden_run` 已识别为自删） |
| 11 | **golden 治理（P0-4b）**：报告加 `environment` 指纹（EXECUTOR/OS/python/Chrome/ffmpeg/字体 sha/风格库及其统计 sha）；`--update` **必须**给 `--reason`，并把理由+环境写进基线 `updateHistory`（schema 升 `golden-baseline/2`、报告升 `golden-report/3`）；跑完**自删**黄金项目（`--keep` 保留） | `scripts/golden_run.py` | **仅静态**（没实跑；实跑一次 5s 约 3–5 分钟，见 §7 第 2 项） |
| 12 | **P1-08**：时间轴 409 冲突面板渲染服务端 `details.diff`（此前只读 `current_version`，diff 被丢掉） | `web/src/app/timeline/page.tsx`（`fmtDiff` + `data-testid="timeline-conflict-diff"`） | 仅静态（tsc 干净；**没有 UI 实测**，见 §7 第 4 项） |
| 13 | **P1-18**：音频页许可 `authorized` 默认**不勾选**（原来默认 true），读回也改成 `=== true` | `web/src/app/audio/page.tsx` | 仅静态（tsc 干净）。注意：QA 页**本来就**要求用户输入 YES 才置 authorized（`qa/page.tsx:46-50`），那半条早已闭，别重复改 |
| 14 | **P1-15 结论修正**：`card/audio.json` **不是**资产引用面（里面是 Take 自己的 `sha256`，全仓无 `assetSha`；Take 是独立副本，删资产不会断音频链，算进去只会造假阳性）——写进 `scan_usages` docstring 作为实证结论 | `server/app/services/assets.py` | 已实测（读了真实 audio.json 结构 + grep 全仓无 assetSha） |
| 15 | **P1-19 另半句**：`verify_r3_assets.py` 的字体样本改仓库相对 glob（原来写死 `/Users/litianyu/.../next@15.5.28_.../noto-sans-v27-...ttf`）；`smoke_m1.py` 的 rumor 根改 `rumor_root()`（工作区白名单推导 + `FILMFLOW_RUMOR_ROOT` 覆盖 + 找不到就 `E_ENV_MISSING` 硬失败），边数断言 `>=80` → `==93` | `scripts/verify_r3_assets.py`、`scripts/smoke_m1.py` | 已实测（glob 命中同一个文件；`rumor_root()` 解析出 `/Users/litianyu/cc-projects/ai-v/rumor-39s`） |

**B9 里被回滚的东西**：有个子代理改了 `verify_r2_5_audio.py` / `verify_r2_5_delivery.py` 加 Cleanup，
我没验证就回滚了，补丁存在 `~/filmflow-handoff-b9-agent-teardown.patch`（245 行，可参考但**必须自己复核**）。

---

## 6. 明确没做完的三件事（别当成已完成）

1. **B9 已本地提交但没推送**（`b9fe124` + `9804192`）。先复核 §4 的三个数字对不对得上（`336 collected / 334 passed + 1 skipped + 1 xfailed`、`16 项全 ✓`、`EXECUTOR_VERSION=2.13.0`），再问老板要不要 push；顺手修 §4 提到的 F821（`artifacts.py:57`）和 §7 第 1 项列的文档失真。
2. **`test_qa_extend_scene_render.py` 还挂着 xfail**。转正的前置是把帧服务端口做成可配置：
   `server/app/config.py:37 frame_port = 8787`（注释写"规格硬约束 8787"）、`server/app/engine/locks.py:22 "port-8787"`、
   `server/app/engine/executors/pipeline.py:35 self.port = 8787`、`:120 E_PORT_BUSY`、`:179 embed=…:8787/…`。
   要改成 env 可覆盖（如 `FILMFLOW_FRAME_PORT`）+ 集成 conftest 分配空闲端口 + 锁名跟着端口走，
   **然后确认 dev 服务与测试服务并存时不再出黑帧**，再去掉 xfail。改端口属于执行器行为 → 要升 `EXECUTOR_VERSION`。
   （注意：`:8787` 是规格里的硬约束，改可配置前先在 HANDOFF 里记一笔为什么可以偏离。）
3. **9 个验收脚本还没接 `Cleanup`**（`TEARDOWN_PENDING` 里那 9 个），**残留清理也没执行**（14 项目 / 91 僵尸 draft）。

---

## 7. 接下来的队列（老板已点头「按顺序」，不要乱序）

### 第 1 项 · 收口 B9 并留下证据（0.5–1 小时）
- 复核 §4 三个数字；把 `EXECUTOR_VERSION=2.13.0`、collected/passed、`16 项`、DB 计数同步进
  `HANDOFF.md`（§0.0 实测行、:80 命令注释、:379 表格、:384 版本历史、:751/:789/:986/:1016、:1069-1071 检查表）、
  `AGENTS.md`（:8 进度行、:71 命令注释、:86 governance 步数）、`docs/process/r3_plan.md`。
  改完 `check_docs_consistency.py` 必须 PASS。
- 顺手修 §4 提到的 F821（`artifacts.py:57`）。
- 顺手改掉两处**文档失真**（本轮审计抓到、还没改）：
  - `HANDOFF.md:633`：仍写"5s 黄金（project 223 / run 282）：6 帧 SSIM 1.0"，而 :975 自己写 run 282 是 failed。
    正确口径：原帧锚是 run 306/312/334（5s）、333/334（15s）、335/336（40s），报告在 `docs/reports/golden/`。
  - `HANDOFF.md:265`：仍写"P1-11 未完成（时间轴虚拟化 + 实测）"和"20 个模型化端点只有 3 个有 happy-path"，
    与同文件 :27/:41/:187/:902 自相矛盾，且 B8 之后是 **51/51**。
  - 另外 `server/app/models.py:1` 仍写"15 张表"（实际 21 个 `table=True`）、`vendor/README.md` 仍写 76MB/61MB
    没有"逻辑大小 vs 磁盘分配（稀疏文件）"说明、`main.py`/`pyproject.toml` 版本恒 `0.1.0`
    （专家 §7 要求"决定是否随里程碑 bump"——决定并把理由写进 HANDOFF §7 即可，不必真 bump）。
- 提交（不推送，除非老板点头）。

### 第 2 项 · 把 B9 的"仅静态"变成实测（1–2 小时，Chrome 独占，串行跑）
按这个顺序，每跑完一个就把输出贴进 HANDOFF：
1. `uv run --project server python scripts/golden_run.py --project 5s --resolution original`
   —— 验证环境指纹 + 自删（跑完 DB 项目数应回到 25）；顺便证明升版 2.13.0 后原帧 SSIM 仍 1.000000。
2. `uv run --project server python scripts/smoke_m1.py` —— 验证 `rumor_root()` 与 `edges == 93`。
3. `uv run --project server python scripts/verify_r3_qa.py` —— QA 脚本回归（自建自删，6 步）。
4. UI 实测 P1-08：开两个浏览器窗口改同一项目时间轴，制造 409，确认横幅里**列出字段级 diff**
   （`data-testid="timeline-conflict-diff"`）；P1-18：确认 `/audio` 页"已授权"默认未勾选。
   UI 自动化用系统 Chrome + 键盘输入（React 19 的 `fill()` 不触发 onChange）。
5. `cleanup_projects.py --stale-drafts` / `--stale-jobs --hours 72` **只跑报告模式**，把输出贴进 HANDOFF。

### 第 3 项 · 9 个脚本接 Cleanup + 残留清理（破坏性，按 §2 的口径）
1. 逐个把 `TEARDOWN_PENDING` 里的 9 个脚本改成 `with Cleanup(c, keep=args.keep) as clean:` +
   `clean.track(pid, root)`（`verify_r2_recovery.py` 特殊：它会 kill -9 并重启 dev 服务，
   teardown 必须用重启后仍然有效的 client）。改一个就从 `TEARDOWN_PENDING` 删一个，守卫会逼你别漏。
   每个改完至少 `py_compile` + ruff 不比 HEAD 差；能便宜实跑的（`verify_r2_preview`、`verify_r3_camera`）真跑一次。
2. 残留清理（**先备份**：`cp ~/.filmflow/filmflow.db ~/filmflow-backup-<日期>-pre-b9-cleanup.db`）：
   - 项目：走 `DELETE /projects/{id}?confirm=true`（保护名单里的还要 `&confirm_name=golden-5s`），
     逐个删 §4 列的 14 个；**删前确认无在飞作业**；删完出计数对照 + `du -sh` 前后对比。
   - 僵尸 draft：`cleanup_projects.py --stale-drafts --confirm`（91 条 root 已不存在的）。
   - `retry_wait` 11 条：**不要动**——它们全属 rumor-39s 与演示 188，是"等人工门"的正常态；
     72h 策略会在启动时自然收（`expire_parked`）。要提前收必须老板单独点头。
3. 把结果写进 HANDOFF §0.0 的数据现状行。

### 第 4 项 · 原工程债队列（B9 之后）
1. **交付门禁残余（P1-13）**：`render.profile.json` / `caps_json` / `params_snapshot` 参与比对；
   `_alignment` 仍回退读当前 `card/alignment.manual.json`（判官 F-DEL-4 明写"记录不改"，要改先问）。
   注意 `params_snapshot` 现网**所有 Run 都是空**（实测 0 行非空）——要么补写入，要么明确"空即不比对"，别写成已覆盖。
2. **P2 里性价比高的几条**（本轮审计实测仍未动）：`/api/audit` limit 下推 SQL（现在全表 `.all()` 再内存切片）、
   P2-09 三个"unique"索引其实没 `unique=True`（`models.py:65/114/143`）、P2-01 门继承查询注释写"查同 workflow"
   但代码没过滤（`runengine.py:241-245`）、P2-05 delivery 不幂等（并发两次会 rmtree 同一目录）、
   P2-24/P2-25（17 个 .feature 只有 2 个绑定）、P2-27 恒真断言（`verify_r3_audio_v2.py:89 onsets>=0`、
   `test_frame_fixtures.py:55 … else True`）、P2-35 preview/final 字体 CSS 优先级相反、
   P2-28 `server/app` 零 logging、P2-30 `except: pass` 35 处 / `type: ignore` 95 处（比审查时更多）。
3. **CI（P1-20）+ fresh-clone bootstrap（P1-21）**：无 `.github/`、无 pytest-xdist；
   原帧锚已入 git，缺风格库/rumor-39s/Chrome/ffmpeg 的接线脚本。
   注意 `unit/test_p1_foundations.py:171,181` 把 FrameServer 端口写死 8787 且忙时 skip —— 这是 `pytest -n` 的唯一真冲突点。
4. 之后才是 **FR-40（命令面板 + 通知）/ FR-41**。R4 不做。

---

## 8. 已知坑（每一个都是这轮真撞过的，别重复撞）

1. **`:8787` 帧服务是全局单例**：dev 服务在跑时，集成测试的隔离 server 会跟它抢/共用 → 引擎取不到
   program/贴图 → **静帧全黑** → D04 报 `lum_mean=17.9 < 40`。这就是 §6 第 2 条 xfail 的原因。
   跑渲染级集成测试前，最好确认没有别的 server 在用 8787（或先把 dev 服务停掉）。
2. **删项目会让别的 Run 挂掉**（B9 已修，但要理解机制）：产物内容寻址存在**产出它的项目根**里，
   跨项目缓存命中只登记绝对路径不复制文件。清理残留项目之后，如果出现"C03 变量字体缺失：先运行 C02"
   这类莫名失败，先查 `artifact` 表里那条路径是否还存在。根治方案是把产物库搬到全局
   （`~/.filmflow/artifacts`），那是独立一个批次，别顺手做。
3. **风格选择不能用 `?chips=可生产&limit=1`**：顺序不定，实测同一测试第一次拿到 print 系、第三次拿到
   pixel 系 `AG1` → C01 判 `E_ENGINE_API_UNSUPPORTED`（code-video 还是 Contract 1.0）。用 `style_id` fixture（钉 H2）。
4. **H2 + 2.0s/3 场会撞 D04 过暗**：每场只有 0.67s，静帧采在入场动画里。**4.0s/3 场是验收脚本实测能过的口径**
   （`_scratch_state.COPY_3` + duration 4.0）。
5. **删除闸门看的是作业心跳（120s 窗口）**：停在门上的 Run 会把作业 parked 成 `retry_wait`，
   刚 park 完心跳还新 → 删除被 409 拦。`_acceptance.destroy` 现在会先取消 `blocked` 的 Run（`BUSY_RUN` 已含 blocked）。
6. **冷缓存的时间预算**：F02 渲 120 帧约 5 分钟；`verify_r3_audio_v2` 的 wall 上限已放到 600s；
   `verify_r3` 的 `pv_ms < 3.2` 在抢占下会假失败（冷 4.25s / 热 0.02s）。别在别的渲染在跑时并行验证。
7. **人工补标的 token 直接进 WebGL 着色器**：`POST /labels/{style_id}` 的 `palette` 必须 hex、`screen` 必须数值，
   否则 `preview/still` 抛 shader 编译错误 → 500；写补标必须 `flag_modified(st, "tokens_json")`，否则静默丢失。
8. **人工补标/音频上传的长度上限与服务层同源**：`schemas._AUDIO_B64_MAX` 由 `audio.MAX_BYTES` 换算，改一边要同步（有单测钉住）。
9. **别用 `nohup ./dev.sh &`**：Bash 工具调用结束时 shell 退出会把服务带走（实测 `Connection reset by peer`）。
   用工具的后台执行参数启动。
10. **集成测试 500 排错**：隔离 uvicorn 是 `--log-level critical` + stderr PIPE，真出 500 时把 stderr 落到文件再看。
11. **PATCH 语义**：`takes.update` / `review_comments.update` / `drafts_patch` / `label_submit` 只能收
    `model_dump(exclude_unset=True)`；"没传"与"传了 null"不同。透传语义（批注/草稿 payload/审片 JSON）保留 `extra="allow"`。
12. **`copy` 是保留字**：线上传输键名不变，模型内部叫 `copy_text` + `alias="copy"`。

---

## 9. 汇报与停止条件

**每完成一项**，按这个格式报（不要长篇叙事）：
```
第 N 项 · <标题>
改了什么：<文件:行> ×若干
实测：<命令> → <关键输出/数字>（贴真输出，别转述）
没验的：<明确列出>
提交：<hash> <message>（推送了没有）
```

**必须停下来问老板的情形**：
- 要动演示项目 / rumor 基线 / 已推送的历史提交；
- 要 `git push`（B9 这批还没推）；
- 要执行 §7 第 3 项之外的任何破坏性库写，或清理范围超出 §4 列的 14 个项目 + 91 条僵尸 draft；
- 要偏离 46 节点/93 边/8+8 门/caps/`content_hash` 语义，或偏离 `:8787`、`:7860`、`:3000` 这些规格端口；
- 发现"文档说闭了、实测没闭"的新条目（先报，再改）；
- 要开 FR-40/41（必须等 §7 第 1–4 项做完）。

**本轮审计的总账（供你判断优先级，别重复审计）**：专家账本 P0–P2 共 63 条 →
真闭 26（41%）/ 半闭 13（21%）/ 未动 23（37%）/ 无法验 1；P3 26 条未逐条核对（抽查 3 条已顺带闭：
`/artifacts/{id}/file` 白名单、SVG CSP、版本链上限；仍未闭：`routes.py` 已涨到 2711 行、仓库无 LICENSE）。
专家 §7 建议的 12 条测试：补齐 5 条、漏 7 条（漏的是：DB 不变量断言→B9 已补、extend_scene 渲染级 E2E→B9 已补但 xfail、
`_safe_join` 符号链接用例、无体 POST 要 token（token 层根本没做）、并发双客户端真并行保存、截断 PNG 续跑、
损坏资产 fixture、delivery 幂等、QA 统计口径合成 failed 数据）。
6 处文档失真见 §7 第 1 项。

---

## 10. 关键文件索引

- 服务与配置：`dev.sh`、`server/app/main.py`（lifespan：`cleanup_orphans` → `recover` → `expire_parked`）、
  `server/app/config.py`（`frame_port`、`style_library_root`、`workspace_roots`）、`server/app/db.py`（`MIGRATIONS`、WAL/FK）、
  `server/app/security.py`（`LocalOriginMiddleware`、`file_response`、FrameServer 响应策略）、`server/app/errors.py`（错误码 + ApiError 信封）。
- 引擎：`server/app/engine/edges.py`（46 节点/93 边/门表）、`runengine.py`（调度、缓存命中、门继承、`start_run`/`cancel_run`/`resume_run`）、
  `cachekey.py`（`EXECUTOR_VERSION`）、`snapshot.py`（`ensure_run_snapshot`/`snapshot_doc_drift`）、`fpscalc.py`（NTSC 唯一口径）、
  `executors/__init__.py`（C02 字体等）、`executors/pipeline.py`（D01/D02/D04/E05/F01/F02/F04、`FrameServer`、`_still_times`）。
- 服务层：`services/qa.py`（`analyze`/`apply_fix`/`_apply` 的 extend_scene + profile 同步 + LIFO 撤销 + `report`）、
  `delivery.py`（交付门禁 + rights/2 + QC）、`assets.py`（`scan_usages`/许可门禁）、`audio.py`（`MAX_BYTES`/Take/loudnorm）、
  `project_docs.py`（CAS + `diff_docs` + 版本链裁剪）、`timeline_ops.py`（`READ_CPS=5.2`、`TRANSITIONS`）、
  `project_cleanup.py`（`plan_delete`/`_job_is_live`/`is_protected`）、`jobs.py`（`park_job`/`expire_parked`）、`preview.py`。
- 验收脚手架：`scripts/_acceptance.py`（`create`/`destroy`/`throwaway`/`Cleanup`/`require_scratch_project`/
  `audit_script_pollution`/`audit_script_teardown`/`DEMO_PROJECTS`/`POLLUTION_EXEMPT`/`TEARDOWN_PENDING`）、
  `scripts/_scratch_state.py`（`create_project`/`drive_to(F04)`/`build_take_state`/`build_audio_state`/
  `build_asset_state`/`build_template_source`/`build_review_source`/`scratch_project`）、
  `scripts/verify_p1_governance.py`（16 项一键复核）、`scripts/check_docs_consistency.py`（文档机检）、
  `scripts/cleanup_projects.py`（残留/僵尸报告与回收）。
- 测试：`server/tests/conftest.py`（隔离 HOME、`E_ENV_MISSING` 硬失败、**生产库不变量守卫**、marker 注册）、
  `server/tests/integration/conftest.py`（随机端口独立 uvicorn、字体缓存播种、`style_id`、`project_root`）、
  `unit/test_run_snapshot_drift.py`、`unit/test_cache_hit_material.py`、`unit/test_c02_font_pin.py`、
  `unit/test_acceptance_pollution.py`（含自删棘轮）、`unit/test_request_models_batch3.py`（51 端点反射守卫）、
  `integration/test_render_smoke.py`（3s 真出片）、`integration/test_qa_extend_scene_render.py`（P0-5 渲染级，xfail）、
  `integration/test_write_api_happy_paths.py`（14 条 happy-path）。
- 证据：`docs/reports/golden/*.json`（7 份）、`docs/reports/r2-incremental/*.json`（含 40s-run311）、
  `docs/reports/p1-11-timeline-100.json`、`fixtures/golden/{5s,15s,40s}/baseline_original/`。
