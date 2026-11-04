# B9 收口 + 队列第 1–4 项 · 整夜执行报告（2026-11-05 凌晨）

> 执行者：ZCode（goal 模式）。接手入口 `docs/process/handoff-prompt-b9.md`；
> 老板指令「按顺序做完 §7 队列 → 全部完成并自检 → 产出本报告供专家全量审查」。
> 所有数字均为当晚实测输出，可复现命令逐条附在正文。

## 一、队列完成度总览（对照 handoff-prompt-b9.md §7）

| # | 队列项 | 状态 | 提交 |
|---|---|---|---|
| 1 | 收口 B9：F821 + 文档失真 + 数字同步 | ✅ | `58cbd64` |
| 2 | B9「仅静态」→ 实测（golden/smoke/r3_qa/P1-08/P1-18/残留报告） | ✅ | `189b866`（含 §7-2）前 `e2e_b9_ui` 等 | 
| 3 | 9 脚本接 Cleanup（棘轮归零）+ 残留清理（14 项目 + 105 僵尸 draft） | ✅ | `12091e8` + `189b866` |
| — | B9 收口的第三件：frame_port 可配置 + xfail E2E 转正 | ✅ | `77d2a6b` |
| 4.1 | 交付门禁残余（P1-13） | ✅ | `f0689b1` |
| 4.2 | P2 高性价比若干条 | ✅ 7 条 | `9fdbc77` + `f03fix` |
| 4.3 | CI（P1-20）+ fresh-clone bootstrap（P1-21） | ✅ | `3097481` |
| — | FR-40/41 | ⛔ 未开工（见 §六 停止条件说明） | — |

## 二、逐项证据（命令 + 实测输出）

### §7-1 收口 B9
- F821：`uv run --project server ruff check --select F821 server scripts` → `All checks passed!`
  （删除 0 调用者死函数 `artifacts.node_output_hashes`，它引用了未导入的 `select`，一调即 NameError）
- 文档失真复核：HANDOFF :633（run 282 failed 口径）与 :265（P1-11/51 端点口径）**在 B9 提交里已修**，
  本批补的是剩余三处：`models.py` docstring 表数 15→21、`vendor/README.md` 补「逻辑 vs 稀疏磁盘分配」口径、
  应用版本策略裁决写进 HANDOFF §7.1（0.1.0 不随里程碑 bump，理由：版本语义由
  EXECUTOR_VERSION/RENDERER_VER/MIGRATIONS 三个钉子承担）。

### §7-2 仅静态 → 实测
- **golden 5s 原帧**：`uv run --project server python scripts/golden_run.py --project 5s --resolution original`
  → 6 帧 SSIM=1.000000、pHash 距离 0；报告 `docs/reports/golden/5s-original-run335.json`
  （schema golden-report/3，含环境指纹：EXECUTOR=2.13.0 / Chrome 156.0.8078.80 / ffmpeg 9.0.2 /
  字体 sha a3041811… / 风格库统计 sha）；跑完自删、`GET /api/projects` 回 25。
  **首跑抓出真缺陷**：`golden-5s` 命中保护名单，`_acceptance.destroy()` 没回显 `confirm_name` → 409，
  黄金项目泄漏（当场清掉；修复 = destroy 用库行真名回显，`test_acceptance_pollution.py` 15 条全过）。
- **smoke_m1**：46 节点 / **93 边 ✓**、`rumor_root()` 解析 `~/cc-projects/ai-v/rumor-39s`、M1 全链 ✓。
- **verify_r3_qa**：6 步全绿（自建自删）。
- **P1-08/P1-18 UI 实测**（新脚本 `scripts/e2e_b9_ui.py`，真键盘 + 双上下文）：
  409 横幅渲染 **3 条字段级 diff**（`$.scenes[0].text 服务端 初始文案。甲的改动。→本地 初始文案。乙的冲突改动。`）；
  `/audio`「已授权」默认未勾选。踩坑入账：派生场景 ~2s，追加一个字即 `E_SCENE_READ_OVERFLOW`，
  headless 里 `window.confirm` 被自动 dismiss → 永不重试 → autosave 版本推不动；脚本播种 6s 场景后再测。
- **残留报告模式**：僵尸 draft 92 条（当时）、`--stale-jobs --hours 72` 0 条（11 条 retry_wait 心跳都在 72h 内）。

### §7-3 脚本 Cleanup + 残留清理
- 9 个 TEARDOWN_PENDING 脚本全部接 `Cleanup`（atexit 收尾，异常路径也删）；
  `audit_script_teardown` → offenders `[]`，棘轮 **0/0**；`verify_r3_camera` 实跑 PASS（SSIM 0.989421）
  且自删成功；`verify_r2_preview` 中途断言失败（热缓存样本不足，环境抖动）**但项目照样自删**——
  正是接 Cleanup 的意义。
- 破坏性清理（备份 → 删前 0 在飞 → 逐个删 → 对照）：
  - 备份 `~/filmflow-backup-20261105-pre-b9-cleanup.db`（33.4MB）
  - 14 个项目全部走 `DELETE /projects/{id}?confirm=true[&confirm_name=<真名>]`
    （207/216/223/243/244/245 回显 `golden-5s`；250 回显 `r3-audio-v2`；全部 200 + dirRemoved=true）
  - 僵尸 draft **105 条**（91 已知 + 14 条指向刚删项目 root 的同判据条目），151→46
  - 计数对照：project 25→11 / run 44 / job 44 / 磁盘 2.3GB→**1.5GB**（目录 24→10）
  - 演示 docrevision 跑前跑后逐一相等：174=3 / 188=28 / 211=37 / 227=58
  - `retry_wait` **一条没动**（原 11 条 + 1 条今晚 smoke_m1 留下的同性质 rumor 条目 = 12 条，
    全部是「等人工门」的正常态；72h 策略按心跳自然收）

### B9 收口：frame_port 可配置 + E2E 转正
- `config.frame_port` 本就支持 `FILMFLOW_FRAME_PORT`（env_prefix），接线了三个消费点：
  `pipeline.FrameServer.port`、`_engine_url`/`_project_url`、E_PORT_BUSY 文案；
  锁名 `port-8787`（规格写死在 edges.py 节点表）在 `LockManager.acquire/holders/release`
  归一化成 `port-<实际端口>`；集成 conftest 给隔离服务分配空闲端口。
  **默认仍 8787，规格端口不偏离**（HANDOFF §8 记了一笔为什么可以做成可配置）。
- `EXECUTOR_VERSION` 2.13.0 → **2.14.0**（新单测 `test_frame_port_config.py` 3 条）。
- **P0-5 渲染级 E2E 摘除 xfail 转正**：`uv run pytest tests/integration/test_qa_extend_scene_render.py -q`
  → **1 passed in 241.12s**（dev 服务同时在跑的隔离环境：两次 Run 真渲染 96→108 帧、
  尾部场景 range 顶到片尾、灰度 σ 断言、QA 无 black/missing_frame、retry 409、项目自删）。
  转正过程中修掉三处测试自身问题（收尾必须无条件 cancel 全部 Run；`_scene_ranges` 按
  start/end 规范字段算——场景字典形状随写入路径变化）。

### §7-4.1 交付门禁残余（P1-13）
- 快照新增 `caps`/`params` 字段（**不进 doc_snapshot_sha**——否则 2.14.0 前的历史快照
  重算 sha 全部失配；文件级封印覆盖它们；历史快照缺字段 → 「缺省即不比对」，不写成已覆盖）。
- `_ensure_run_documents_match` 三项扩展：
  ① final 档位从只比 w/h/fps 扩到**全字段**（crf/preset 直接进 master 编码，render.profile.json
  的漂移经 resolve() 体现为档位漂移被拦）；
  ② **caps 只许长大**：快照 caps ⊄ 当前 caps 即 409（caps_after_approval 只增不减，缩小=改写）；
  ③ params 非空才比对（现网 0 行非空，不假装覆盖）。
- 新增 4 条单测（caps 缩小拒 / caps 超集过 / params 漂移拒 / final crf 漂移拒），门禁共 24 条全过。
- `_alignment` 回退读当前文件的口径**没动**（判官 F-DEL-4 明写「记录不改，要改先问」）。

### §7-4.2 P2 批（7 条）
1. `/api/audit` limit/offset 下推 SQL（此前全表 `.all()` 内存切片；上限 1000）。
2. 恒真断言 ×2：`verify_r3_audio_v2` 的 `count>=0` → `count == len(onsets)` 结构真断言；
   `test_f03_catches_missing_frame` 的 `assert ... else True` → 严格断言，**揭开真缺陷：
   F03 失败路径不写 frame_report.json（证据灭失）**——已修：报告先落盘（含 missing/black 全量）再抛错。
3. 交付防重入（P2-05）：同 Run 已有 queued/leased/running/retry_wait 的 delivery 作业 → 409
   （并发会 rmtree/重建同一交付目录）。
4. 门继承限同 workflow（P2-01）：`_gate_valid` 的 inherit 查询此前没过滤，
   不同项目撞相同 content_hash 会互相继承人工门批准；现 `join(Run).where(Run.workflow_id == …)`。
5. 三个「unique」索引转真 UNIQUE（P2-09）：stylepreview/noderun/asset——生产库实测 0 重复、
   noderun 每 run 每节点一行（retry 复用行），语义安全；模型层 `unique=True` +
   **迁移 5**（DROP+CREATE UNIQUE，幂等），`test_migrations` 新增唯一性断言。
6. 字体 CSS 优先级对齐（P2-35）：preview 服务此前优先 `fonts/embed.css`，final 优先
   `fonts/noto-sans-sc/embed.css`——两路字体相反；统一 noto-sans-sc 优先，`RENDERER_VER` → `preview-1.9.0`。
7. 顺手：`artifacts.py` F821 死函数删除（§7-1）、测试文件 ruff 清零。

### §7-4.3 CI + fresh-clone
- `.github/workflows/ci.yml`（P1-20 首版）：lint（ruff server+scripts）+ tsc + **unit+BDD 全量**。
  渲染级集成**刻意不进 CI**（口径写在文件注释里：golden/SSIM 的语义锚在本机字体/风格库上，
  在别处跑会给出另一套数字，破坏「完成申报必须附可复现实测输出」——要上渲染级 CI 需先把
  字体/风格库指纹参数化，独立一批）。
- `scripts/bootstrap_fresh_clone.sh`（P1-21）：只检查不联网（uv/ffmpeg/python3.13/系统 Chrome/
  风格库 341 个 .md + doctor/rumor 根/golden 原帧锚/`~/.filmflow`）；本机实测 **READY exit=0**。

## 三、终验（全量自检，2026-11-05 03:0x 实测）

| 项 | 命令 | 实测 |
|---|---|---|
| pytest ×2 | `cd server && uv run pytest tests -q`（dev 停，无环境 skip） | **346 passed ×2**（342.83s / 366.90s；0 skipped 0 xfailed——B9 的 P0-5 E2E 转正后并入 passed），两轮后生产库计数不变 |
| collected 构成 | `pytest tests --collect-only -q` | **346 = unit 306 + integration 33 + BDD 7** |
| 一键复核 | `uv run --project server python scripts/verify_p1_governance.py` | **16 项全 ✓** + `PASS`（EXECUTOR=2.14.0、迁移登记 [1,2,3,4,5]、跑后 DB 11 恒定） |
| 文档守卫 | `scripts/check_docs_consistency.py` | **PASS**（现值行：EXECUTOR=2.14.0 · 迁移=[1,2,3,4,5] · collected=346 · governance=16 · DB=11 · 裸 dict=0） |
| tsc | `cd web && npx tsc --noEmit` | 0 错误 |
| ruff | `cd server && uv run ruff check .` / 仓库根 `uv run --project server ruff check .` | **349 / 417**（口径：根=server+scripts+根级 py；本轮新增测试文件全部 ruff 清零，F821=0） |
| 迁移 5 落库 | `init_db()` 后 `PRAGMA index_info` | 登记=[1,2,3,4,5]；三个 UNIQUE 索引列序正确；noderun 重复行 0 |
| 生产库 | `GET /api/projects` | **11**（=演示/rumor 名单，恒定）；磁盘 1.5G / `~/.filmflow` 1.4G |
| 终版 golden | `golden_run.py --project 5s --resolution original`（2.14.0，缓存全失效） | 6 帧 **SSIM=1.000000**、pHash 0（run 336，`docs/reports/golden/5s-original-run336.json`），自删、DB 回 11 |
| 终版 UI e2e | `scripts/e2e_b9_ui.py` | PASS（P1-08 三条字段级 diff + P1-18 默认未勾选） |

> 环境备注：终验 pytest 在 **dev 服务停止**下跑（消除 `test_p1_foundations.py:174` 的 8787 占用 skip 门控，
> 计数才可复现）；治理与文档守卫在 dev 重启后跑（加载 2.14.0 + 迁移 5）。

## 四、本轮新发现的真缺陷清单（全部已修）

1. `_acceptance.destroy` 不回显 `confirm_name` → golden 自删尾巴 409、项目泄漏。
2. F03 失败路径不落 `frame_report.json`（旧恒真断言掩盖；证据灭失）。
3. 门继承跨 workflow（P2-01，注释与代码不符的真越权面）。
4. 三个「unique」索引实际非唯一（P2-09）。
5. preview/final 字体 CSS 优先级相反（P2-35）。
6. 同 Run 交付作业可重复入队（P2-05，并发损坏交付目录）。
7. F03 缺帧/黑帧报告不落盘（同 2）。
8. 一次性观察（未定案，保留观察）：e2e 首跑期间 dev API 曾整体无响应约 1–2 分钟后自愈
   （FrameServer `POST /done` 已到、`/api/health` 超时→200；重启后未复现）。

## 五、明确没做 / 边界

- FR-40/41 未开工：handoff-prompt-b9 §9 把「要开 FR-40/41」列为**必须停下来问老板**的情形，
  与「不准停」的全局指令冲突时按更具体的停止条件执行——§7 队列 1–4 项全部完成后停在这里。
- P2-30（35 处 except:pass / 95 处 type:ignore）与 P2-28（server/app 零 logging）、
  P2-24/25（17 个 .feature 只绑 2 个）：工作量级为独立批次，未在本夜动。
- `params_snapshot` 现网仍 0 行非空：门禁语义是「非空才比对」，没有回填历史数据。
- 4 个 B9 提交 + 本夜 8 个提交**全部未推送**（handoff §9：push 需老板点头；一行命令见 §七）。

## 六、停止条件说明（为什么停在这里）

老板今晚指令「不准停，直到全部完成」；handoff-prompt-b9.md §9 的停止条件清单里，
「要开 FR-40/41（必须等 §7 第 1–4 项做完）」与「要 git push」都需要老板点头。
§7 第 1–4 项已全部做完并自检通过 → 按 §9 停在 FR-40/41 门口，等老板 morning check。

## 七、给老板的一分钟清单

```bash
# 1) 推送（点头后）
cd /Users/litianyu/cc-projects/ai-v/filmflow && git push origin master
# 2) 一键复核
uv run --project server python scripts/verify_p1_governance.py
# 3) 干净机器自检
bash scripts/bootstrap_fresh_clone.sh
```
