# FilmFlow 接手 Prompt · H8 收口交接（2026-11-06 晚，给 zcode）

> 这份文件是给**接任者（zcode / 任何下一个 Agent）**的完整接手 prompt。整份贴给它，不要让它"自己看情况"。
> 上一位（Qoder）在 H8 批次收口前被老板喊停：`先停，我回家后再做`，所以**goal 已置为 blocked**，
> 需要老板一句 `/goal resume` 或"继续"才恢复自动循环。
> 代码与守卫都写完了，实测跑到了历史最远（42 步全绿 + Run succeeded + 交付作业 #98 succeeded），
> **只差一条测试自己的键名 bug**（§5）。工作区**整批未提交**——接手第一件事就是把 §5 → §6 → §7 → §8 走完。
> 老板的原话是「能做到哪儿算哪儿，把所有全做好」——**别把这条收口做成半件**。

---

## 1. 角色与使命

你是 FilmFlow 的资深全栈 + 视频交付工程师。仓库是**本地代码动画全生命周期工作台**
（46 节点 / 7 阶段 / 93 边 / 8 人工门 + 8 自动门 / 341 风格库 / 3 引擎 riso·code-video·ink）。
R2.0 / R2.5 / R3.0 v1（FR-32–38）/ R3.5 FR-39 已交付；本轮做的是 **Wave H（H1→H10）+ FR-40/FR-41 前端**。

使命按顺序：

1. **闭掉 H8 收口**：§5 那条键名 bug → 复跑键盘 e2e 到真 PASS → §6 全套实测 → §7 文档同步 → §8 提交推送。
2. 顺手接上 §5b（A05 那道人工门为什么从未进入待办——8+8 门不变量上的真实疑问，量完向老板报告，不许改门表让它消失）。
3. 之后按任务书队列继续：`docs/process/overnight-goal-2026-11-05.md` §11（Wave H 表）→ §13（H9）→ §15（H10）→
   各条目里明写的"诚实边界"。**R4 不做。**

老板**不信自述的全绿**。任何"完成"必须附：可复现命令 + 真实输出 + 具体数字。
没跑过就写"没跑过"，跑失败就写失败原因。宁可少报，不可虚报——历史上因虚报被判官逐条打回
（`docs/process/judge-review-2026-11-04.md`）。

---

## 2. 硬约束（违反即算失败，不是偏好）

- 仅本机 `127.0.0.1`；**不上传文件**；**不调用任何在线生成模型**；不引入需联网构建的依赖。
- 文件操作只在已登记项目根白名单内；禁止任意 shell / 路径穿越；全仓不许 `shell=True`。
- Chrome 全局串行 **1 个**（`chrome-queue=1`）；ffmpeg 独占 → **任何两个渲染级验证不能并行**
  （包括 pytest 集成测试与验收脚本同时跑）。
- 46 节点 / 7 阶段 / 93 边 / 8+8 门 / caps / 三类边 / `content_hash` 语义**不变**。
- 改执行器行为必须升 `EXECUTOR_VERSION`（现 **2.17.0**）；改预览渲染器升 `RENDERER_VER`（现 `preview-2.1.0`）。
  本轮 H8 **没动执行器**，所以没升版——如果接手后要动，记得升。
- 落盘一律 `atomicwrite.write_atomic`；文件响应一律 `security.file_response`；本地 httpx 客户端一律 `trust_env=False`。
- **演示项目绝不动**：现存 11 个项目全部是演示/rumor 名单。验收脚本只许打在自建 scratch 项目上
  （`scripts/_acceptance.py::require_scratch_project()` 是 fail-closed）。
- **手工探针纪律**：`TestClient(app)` 连的是**生产库**；只有必然被 422/400 挡在 handler 之前的请求可用，
  会写的验证走 `scripts/_acceptance.py` 自建项目或独立 `FILMFLOW_HOME`。
- 破坏性库写：先备份 + 前后计数对照 + 老板点头。5 条 `retry_wait` 僵尸 run 作业是老板已裁决的
  **72h parked**，不要顺手清（`docs/process/overnight-goal-2026-11-05.md` §12/§14）。
- 文档里的 `N passed` / 版本号 / DB 计数**只写当前实测值**，历史值用中文表述。`check_docs_consistency.py` 机检一部分。
- git：不 `--amend` 已推送提交、不 `--no-verify`、不 force push。**推送老板已授权且"每轮都推"**；
  但**本轮老板明确说了"先停"**，所以在他回来说继续之前不要 push。
- 原始未脱敏专家报告只留本地 `~/.filmflow/reviews/`，不进公开仓库；341 风格库与示例 mp4 不进 git；
  `vendor/fy-code-animation` 不进 Python 包路径。

### 本轮新增的"环境类"硬约束（踩过才知道的，务必照做）

| # | 事实 | 后果与正确做法 |
|---|---|---|
| E1 | `dev.sh` 里的 uvicorn **没有 `--reload`** | 改了 `server/app/**` 后**必须重启 API** 才生效；否则你在测旧代码 |
| E2 | `dev.sh` 的 `trap ... EXIT` 会**连坐杀另一个子进程** | 若 API/next 是 `./dev.sh` 起的，只 kill 其中一个会两个都死（本轮实测：kill API → :3000 也 down → e2e `ERR_CONNECTION_REFUSED`）。手动起的那个进程不受此影响 |
| E3 | 当前这台机上两个 dev 进程**是手动起的，不是 dev.sh 的子进程** | API：`cd server && uv run uvicorn app.main:app --host 127.0.0.1 --port 7860`；Web：`cd web && NEXT_TELEMETRY_DISABLED=1 nohup pnpm dev`。重启 API 不会牵连 Web |
| E4 | 键盘 e2e 批门期间**必须让出 Chrome**（`_close_page()` 再等渲染） | 否则自己的 Playwright 占着全局串行槽，Run 永远不动（实测卡死 240s） |
| E5 | `sqlite3 -readonly ~/.filmflow/filmflow.db` 表名是**单数**（`job`/`project`/`run`/`noderun`） | `select … from jobs` 直接 `no such table` |
| E6 | 端点返回体是 `table_dict(model)` → **列名**（`error_code`/`result_json`/`payload_json`） | 用驼峰或 `result`/`payload` 读会拿到 None，把成功读成失败（本轮已踩三次，§5 就是第三处） |

---

## 3. 接手第一小时（全部是只读核验，别先改代码）

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
git status --short          # 实测：21 个 M + 10 个 ?? = 31 个未提交文件（含本交接文档与实测报告），HEAD=ae2548c
git log --oneline -3        # ae2548c h10 / 17d5550 h6 / 75c430a h5-h7
curl -s -m 5 -o /dev/null -w "web=%{http_code}\n" http://127.0.0.1:3000/          # 期望 200
curl -s -m 5 -o /dev/null -w "api=%{http_code}\n" http://127.0.0.1:7860/api/projects  # 期望 200
sqlite3 -readonly ~/.filmflow/filmflow.db "select count(*) from project;"          # 期望 11（全是演示名单）
sqlite3 -readonly ~/.filmflow/filmflow.db "select id,status from job where kind='delivery' order by id desc limit 1;"  # 98|succeeded（⚠ 2026-11-07 审计更正：98 是受保护演示项目 215 r2_5-delivery 在 11-03 的旧作业，此行只当「世界未变」快照；**不是** attempt 13 的交付——那条已被脚本登记的 cleanup 连库行删掉，见 §5）
cd server && uv run pytest tests/unit/test_h8_fr40_fr41_frontend.py tests/unit/test_h8_scratch_state_bodies.py -q
# 期望 13 passed —— 这两个文件就是 H8 的静态防线，先确认它们仍绿
```

任何一条对不上，先回来问老板，不要自己"顺手修一下"。（历史上有过一次：交接声明与工作区不符，判官逐条打回。）

---

## 4. 已完成（都有证据，别重做）

### 4.1 Wave H 的已提交部分（H1–H7、H9、H10；**H8 未提交，见 §4.3**）

| 项 | 内容 | 提交 | 关键证据 |
|---|---|---|---|
| H1 | 资产删除的"在飞"判据修正（queued 永远算在飞；leased/running 看 120s 心跳；retry_wait 不算） | `ffd8db4` 同批 | `server/tests/unit/test_assets.py` 两条新用例 |
| H2 | httpx `trust_env` 静态守卫补模块级函数 | 同批 | `tests/unit/test_h2_http_trust_env_guard.py` |
| H3 | 治理第 **18** 项：磁盘/库卫生棘轮（孤儿目录、僵尸 draft 必须 0，fail-closed） | `8c6e2ef` | `scripts/verify_p1_governance.py::check_disk_hygiene` |
| H4 | fresh-clone 双口径 `--require-all` / `--check-only` | `ba6bac3` | bootstrap 四种退出码实测 |
| H5 | 黄金证据 churn（治理第 **19** 项，keep=20，只裁报告不碰锚） | `75c430a` | `scripts/cleanup_golden_reports.py` + `fixtures/golden/README.md` |
| H6 | BLE001 **下降目标** 54/64/64 + 回填基线自身失真 | `17d5550` | `scripts/lint_ratchet.py`、`docs/reports/lint-baseline.json` |
| H7 | 台账索引表（轮次→Wave→提交→证据一句话） | `75c430a` | `docs/process/overnight-ledger-2026-11-05.md:9` |
| H9 | CI 双 job（`ci-lean` 必绿 + `ci-env` 真环境可见 skip）+ ast 环境标记守卫 | `4766e27` `ba6bac3` | run 42171682684 双绿；`tests/unit/test_h9_env_marker_guard.py` |
| H10 | 环境漂移**诊断**（恒 exit 0，不是门禁）+ 重锚理由与当时指纹互证 | `ae2548c` | `scripts/diagnose_environment_drift.py` + 13 条单测 |

### 4.2 FR-40 / FR-41 后端（已提交，`ae51f62` `1824999` 批次）

`services/notifications.py`（JSON store + flock、(kind,ref) 去重、已读、失败带修复入口）、
`services/authoring.py`（本机规则引擎：断句 / 4–6 场 / 组件 / 镜头 / 读时，读速复用 `timeline_ops.READ_CPS=5.2`）、
端点 `GET /notifications`、`POST /notifications/{id}/read`、`/read-all`、`POST /projects/{id}/suggest`、
`GET /queue`、`POST /jobs/{id}/cancel`、`GET /jobs/{id}`。

### 4.3 H8 前端纵切 + FR-41 前端（**本批，全在工作区未提交**）

新文件：

| 文件 | 职责 | 关键点 |
|---|---|---|
| [`web/src/lib/commands.ts`](file:///Users/litianyu/cc-projects/ai-v/filmflow/web/src/lib/commands.ts) | **24 条命令的唯一真源**（面板/快捷键表/冲突检测/全局键位全部从它派生） | `currentProjectId()` 读 `?project=`（`web/src/lib/commands.ts:187`）；`goWithProject`/`goWithRun`（:52 / :61）给需要上下文的页面补参数；`nav.review`/`nav.canvas` 用 `goWithRun`（:113 / :120），`nav.audio` 用 `goWithProject`（:114） |
| `web/src/components/CommandPalette.tsx` | ⌘K/Ctrl+K 面板 | combobox + `aria-activedescendant` 挂在**输入框**上；键位处理同时挂 input 与 listbox |
| `web/src/components/NotificationsBell.tsx` | 通知中心 + 进度中心 + ToastHost | 读 `/notifications`·`/queue`，取消走 `/jobs/{id}/cancel`；`role="progressbar"`；`aria-live="polite"`；toast 4s 自消失 |
| `web/src/components/WorkbenchChrome.tsx` | 挂进根布局的壳层 | 全局键位**遍历注册表分发**；打字时裸键（`?`）让位给输入框 |
| `web/src/components/SuggestionPanel.tsx` | FR-41 草稿层 | 全部采纳 / **单场采纳** / 忽略（不留痕）/ 逐场改停留时长；`pushed` 本地真源防"第二次采纳用旧 brief 覆盖第一次" |
| `scripts/e2e_fr40_keyboard.py` | **零鼠标**全流程验收 | `tab_to`/`tab_to_nth` 焦点链断言；未覆盖判据记入 `boundaries` 并 `return 2`（不许假绿） |
| `server/tests/unit/test_h8_fr40_fr41_frontend.py` | 10 条静态防线 | 每条都对应下§4.3 改动表里的一行"为什么"；跑法见 §3 |
| `server/tests/unit/test_h8_scratch_state_bodies.py` | 3 条"构造器↔请求模型"形状守卫 | 起因见下表 `_scratch_state.py:231` 那一行与 §9 坑 3 |

改动文件（每条都是真跑抓出来的，不是重构）：

| 位置 | 改了什么 | 为什么（实测现象） |
|---|---|---|
| `server/app/api/routes.py:1575` `:1578` | `gates_pending` 未知 run/workflow → **404** | 原来 AttributeError 冒到 **500**（本批实测发现） |
| `server/app/api/routes.py:1639` | pending 每一项带 `item["precheck"] = _gate_precheck(...)` | 批准前置与 decide 用**同一个函数**算，UI 只显示不判断（判据不分叉） |
| `server/app/api/routes.py:2816` | 新增 `POST /authoring/suggest`（无项目入口，复用同一引擎） | 向导第 1 步还没有项目 id；两个路由指向同一个 `authoring.suggest()` |
| `server/app/engine/runengine.py:582` | `_project_ref()`，通知事件带 project id | 通知链接原来是 `?projectId=&runId=` 且 id 空 → **能看不能用** |
| `server/app/services/notifications.py:116` | `_canvas_link(project_id, run_id)` → `/canvas?project=&run=` | 与页面读的口径同源；缺 id 时退化成只带 run（有单测钉住） |
| `web/src/app/canvas/page.tsx:112` `:145` `:151` `:166` `:172` | 画布 Tab 焦点陷阱修复 + 门面板前置显示 | 93 条可聚焦边把 `gate-approve-*` 挤出 60 次 Tab；`edgesFocusable={false}` + `skip-to-gates` + `gate-panel tabIndex={-1}`；`precheck` 非空时按钮 `disabled`（也因此不进 Tab 序）并写明缺什么 |
| `web/src/app/review/page.tsx:33` `:53` `:132` `:143-154` | 新增 `loaded` 三态；已看/未看与按钮都改读 `precheck` | 数据到手前 `missing=[]` → 页头谎报"全场景已看"、批准可点 → 后端 400（键盘 e2e 第一次撞的就是它） |
| `web/src/app/review/page.tsx`（view 效应） | 每看完一场后重取 `pending` | 屏幕上曾同时出现"全场景已看"与"批准前置未满足：未查看场景 S01…"——两处不同步的自相矛盾 |
| `web/src/app/audio/page.tsx` | 保存按钮加 `data-testid="audio-save-alignment"` | 键盘路径要能锚定；也是 G02 免 whisper 的入口 |
| `web/src/components/StylePicker.tsx` | 风格卡 `<div onClick>` → `<button aria-pressed>` + 搜索/设主风格 testid | 向导第 3 步**键盘根本走不到风格**（e2e 当场卡住）；a11y warn 60 → **58** |
| `web/src/app/wizard/page.tsx`、`web/src/app/layout.tsx`、`web/src/lib/theme.tsx` | 挂 SuggestionPanel / 挂 WorkbenchChrome / 主题切换单一入口 | FR-41 与 FR-40 的接入口 |
| `scripts/_acceptance.py:153` `:170` `:64` | `Cleanup.track_draft()` / `_drop_drafts()` / `_draft_points_at()` | 向导第 1 步的草稿没有 `root`，`destroy()` 收不到 → 实测漏 5 行（53→58 已清，备份见 HANDOFF）；删除要先 null 掉 `stylepick.draft_id`（真 FK） |
| `scripts/_scratch_state.py:231` | 抽出 `audio_upload_body()`，非 voice 传 `""` 不再传 `None` | `AudioUploadIn.sceneId: str` → 原来 422；**前置态构造器与请求模型分叉**只有真跑才暴露 |
| `dev.sh`、`web/next.config.mjs` | `NEXT_TELEMETRY_DISABLED=1` + `telemetry:{enabled:false}` | 产品侧两条零网络判据（浏览器非环回请求 0 / API 进程外呼 0）已绿；**`next dev` 到 npm registry 的版本检查外呼仍在**，如实记录在 `docs/reports/h8-fr40-keyboard-e2e.md` 文末，脚本对它只打印不判绿 |
| `docs/reports/lint-baseline.json` | a11y 60 → **58**（带 provenance） | 风格卡改真 button 降下来，棘轮跟着降 |

**本轮新增测试合计 18 条**（13 条在两个新文件 + 5 条加在既有文件：
`test_run_snapshot_drift.py::test_gates_pending_404_for_unknown_run`、
`test_notifications.py` 两条链接契约、`test_h3_hygiene_ratchet.py` 两条草稿回收）。

---

## 5. 唯一未闭合项（H8 就差这一步）——**attempt 14 已把这一步查明并修完，见 5a**

`scripts/e2e_fr40_keyboard.py:641` 原来的断言读驼峰键（`errorCode`/`errorMsg`/`result`），
而 `GET /jobs/{id}` 返回 `table_dict(Job)` 的**列名**（`error_code`/`error_msg`/`result_json`，
`server/app/models.py:287`）→ 把真实原因吞成 `None None`。

**attempt 14（2026-11-07 晨）实测推翻了本文件最初的前提**「产品没问题，是测试自己在猜形状」：
键名修好后第一次复跑，43 步全绿（含两条 A05 断言现场通过），但交付**真的失败了**——
`E_DELIVERY_FAILED E_DELIVERY_QC: ['captions']`（作业 #158）。根因是本批加的「3s 压缩」：
292 字旁白 ÷ 3 秒 ≈ 97 字/秒，`delivery.MAX_CAPTION_CPS=9` 必挂；attempt 13 的
「交付成功」是同一断言语义被读反（`assert status=="succeeded"` 挂掉时渲染的正是驼峰键
`None None`，当时 status 就是 failed）。

### 5a. 修法（已全部进脚本，attempt 15 起生效）

1. **断言修成列名** + body 头部 200 字进断言（本次真跑的价值：第一次让人看见 `E_DELIVERY_QC`）；
2. **去掉 3s 压缩**，保留自然时长（292 字 ÷ 9 cps ⇒ 片长须 ≥33s；自然 39.5s ≈ 7.4 cps 在判据内；
   混音 `apad=whole_dur` + 音乐床铺满全片，长片 LUFS 无忧——`pipeline._mix_filter`）；
3. **键盘保存手动对齐后，把每段 start/end 按 ≤8 字/秒重排**（UI 默认槽位按场次均分时间线，
   字多的场必超 cps；292 字 ⇒ ~36.5s ≤ 39.5s 片长）——把测试数据修进产品判据，不是放宽判据；
4. **三处等待按 948 帧口径抬高**（240→900、420→900/1500，含交付的 9:16 变体重渲染）；
5. **A05 两条断言**（见 §5b，attempt 14 已现场通过：`note=对比后选定 · H_现成版式`）。

复跑（attempt 15，约 20–35 分钟，独占 Chrome/ffmpeg，期间**不要并行跑 pytest**）：

```bash
cd server && uv run python ../scripts/e2e_fr40_keyboard.py
```

**PASS 的判据**：日志末尾出现
`PASS: e2e_fr40_keyboard（… 步全绿，判据①②③与 FR-41 ①②③④ 均现场覆盖）`；
出现 `PARTIAL: 有判据未覆盖 → …` 就是 exit 2，**必须照实贴出来**，不许改成 PASS。

---

## 5b. 交接的第二条线索（不是 H8 收口项，但必须有人接）

**2026-11-07 审计已验：是设计，不是缺陷。** 两个候选解释都没全中——真正的机制是它们之外的第三条路径：

- A05（风格选择）在 A04 完成后由 `runengine.py:510` 的 `_carry_a05_approval` **在本 Run 内自动种子批准**：
  工作流 `meta.style_decision` 非空（向导 materialize 携带用户在第 3 步亲手做的选择）或项目是导入时，
  直接写 `Approval(gate_id="A05", decision="approved", policy="inherit", author="local",
  note="导入继承原风格")` 并 emit `gate.decided … auto=True`（`runengine.py:524-529`）。
  它不是跨 Run 复用旧 Approval（候选②的 `runengine.py:245` 那条 inherit 通道是另一回事，也真实存在）。
- 库证（2026-11-07 实测）：`approval` #502（run 335）/ #447（run 317）/ #402（run 275）/ #394（run 273）
  全是 A05 + policy=inherit + author=local + note「导入继承原风格」。
  attempt 13 在第 18 步键盘走完了风格选择 → style_decision 必在 meta → A05 被自动携带，
  从不进 `/gates/336/pending`，键盘签出 7 道**正是期望行为**。
- 边界说明：run 336 / project 228 的库行已被脚本登记的 cleanup 删掉，run 级复核只能靠机制 + 上述旁证；
  所以 §5 修法里加的那两条 A05 断言（`/runs/{run_id}/report` 的 `approvals`，列名键）就是
  下次真跑时把它钉死的地方。

8+8 门表不动（`edges.py:168` 实测 `HUMAN_GATES` 仍是 8 道）、不放宽任何断言——
§5 的两条新断言是**加强**不是放宽。结论按本节原要求报老板裁定：**设计**
（风格选择已在向导第 3 步被用户确认过，不该在 Run 里二次打断同一决定）。



## 6. 收口顺序（§5 复跑绿了之后，按序做完，一步都别跳）

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow

# 1) 全量回归（collected 已实测 446 = unit 406 / integration 33 / BDD 7；passed 必须真跑出来，不许推算）
cd server && uv run pytest tests -q                       # 期望 0 skipped 0 xfailed
uv run python scripts/verify_p1_governance.py            # 期望 19 项全绿
uv run python scripts/lint_ratchet.py                     # 三口径；routes.py/runengine.py 改过，可能新涨 → 涨了就修代码，不许抬基线
uv run python scripts/check_docs_consistency.py           # 会报 collected/版本/DB 计数不一致 → 见 2)
cd .. && python3 scripts/lint_a11y.py                     # 期望 warn 58 / error 0

# 2) 文档同步（下面 §7 是逐句清单，check_docs_consistency 会兜住数字类）
# 3) git add + commit + push（清单见 §8）
```

---

## 7. 文档同步清单（逐句，照做）

| 文件 | 位置 | 要做什么 |
|---|---|---|
| [`AGENTS.md`](file:///Users/litianyu/cc-projects/ai-v/filmflow/AGENTS.md) | 顶部"当前进度"长句 | 换成 H8 收口后的实测数字（collected/passed、ruff 三口径、a11y、治理项数）；把"FR-40/41 前端未提交"改成"已提交 `<hash>`" |
| `HANDOFF.md` | §0 开头"我停在哪一句"、§6.5 下一批 | 写明：goal blocked（老板 2026-11-06 晚"先停"）；H8 唯一未闭 = 键盘 e2e 交付断言键名，修法见 `docs/process/handoff-prompt-h8.md` §5 |
| `HANDOFF.md` / `AGENTS.md` | **`428 passed` 共 6 处**：`HANDOFF.md:133`、`:432`、`:943`、`:1131`、`AGENTS.md:8`、`AGENTS.md:75` | 全量复跑后全部改成实测值。**现在 `--collect-only` 已实测 collected=446**（=428+18），所以 `check_docs_consistency.py` 此刻必然是红的——这是它在做该做的事，不是新 bug；**2026-11-06 深夜已实跑确认**：`FAIL: 文档漂移 4 处`，恰好 `HANDOFF.md:133/432/943` + `AGENTS.md:75`（另 2 处含「→」被 `HISTORIC` 豁免，照样要改），同一行还显示 H10 诊断在守卫里正常工作（`与锚点 … 逐项一致（锚点报告未记录 2 项：rendererVersion,fpscalcSha256）`，不影响退出码）。守卫会强制其中 4 处（HANDOFF 133/432/943 + AGENTS 75）；`HANDOFF:1131` 与 `AGENTS:8` 因为行内含「→」被 `HISTORIC`（`当时\|旧版\|历史\|→\|（20xx-`）豁免，**但照样要照实改，别利用豁免留着旧数字**。组合口径写清：`446 = unit 406 / integration 33 / BDD 7`（本批 +18：静态防线 13 + 既有文件 5）。要写历史值就按约定写成中文 |
| `docs/process/overnight-goal-2026-11-05.md` | §11 H8 行、§7 Wave E/F 验收清单 | H8 从"待办"改成"已交付+证据"；FR-40 三条 / FR-41 四条**逐条打勾**并各配一句实测（24 条命令命中、27ms、S01 被拒不留痕、brief 外逐键相等、浏览器非环回请求 0、API 进程外呼 0） |
| `docs/process/overnight-ledger-2026-11-05.md` | 文末新增 **轮 19**；索引表（`:9`）补 **轮 17 / 轮 18 / 轮 19** 三行 | ⚠ 索引表目前只到轮 16——轮 17（H6）与轮 18（H10）的正文有、索引行漏了，这是**上一批留下的真实缺口**，接手时补上并在轮 19 里说明。轮 19 正文要含：本批 8 类缺陷清单（§5+§4.3 的"为什么"列）、18 条新测试、attempt 10→14 的逐步演进、`next dev` 外呼边界；以及 **2026-11-07 审计的两条结论**（§5b A05＝自动携带属设计，含库证 approval #502/#447/#402/#394；job#98 交付证据指针更正——98 是 11-03 演示项目 215 的旧作业，attempt 13 自己那条已被 cleanup 自删） |
| `docs/reports/h8-fr40-keyboard-e2e.md`（本批新增） | 文末 | 把 attempt 14 的最终输出补进去（现在记的是 attempt 13 + 那条未闭合断言） |

数字纪律：所有 `N passed` / `X 项` / DB 计数一律**跑出来的**；历史数字写成"上次实测 428（2026-11-06 晚）"这种带时间口径，不留旧值当现值。

---

## 8. 提交与推送

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
git add AGENTS.md HANDOFF.md dev.sh \
        docs/reports/h8-fr40-keyboard-e2e.md docs/reports/lint-baseline.json \
        docs/process/overnight-goal-2026-11-05.md docs/process/overnight-ledger-2026-11-05.md \
        docs/process/handoff-prompt-h8.md \
        scripts/_acceptance.py scripts/_scratch_state.py scripts/e2e_fr40_keyboard.py \
        server/app/api/routes.py server/app/engine/runengine.py server/app/services/notifications.py \
        server/tests/unit/test_h3_hygiene_ratchet.py server/tests/unit/test_h8_fr40_fr41_frontend.py \
        server/tests/unit/test_h8_scratch_state_bodies.py server/tests/unit/test_notifications.py \
        server/tests/unit/test_run_snapshot_drift.py \
        web/next.config.mjs web/src/app/audio/page.tsx web/src/app/canvas/page.tsx \
        web/src/app/layout.tsx web/src/app/review/page.tsx web/src/app/wizard/page.tsx \
        web/src/components/CommandPalette.tsx web/src/components/NotificationsBell.tsx \
        web/src/components/StylePicker.tsx web/src/components/SuggestionPanel.tsx \
        web/src/components/WorkbenchChrome.tsx web/src/lib/commands.ts web/src/lib/theme.tsx
git status --short   # 必须只剩 0 个 ??（本批文件全进）；有多的先看清楚是什么再决定，别 git add -A
git commit -m "feat(h8): FR-40/41 前端纵切——命令注册表单一真源 + 键盘可达性 + 门前置同源"
git push   # 推送已获老板长期授权，但本轮他说过"先停"——回来点头之后再 push
```

Commit message 草案（可按实测结果调整，别写没发生的事）：
标题 ≤70 字符；正文要点：① 24 条命令唯一真源 + ⌘K 面板/快捷键表/通知中心/进度中心；
② FR-41 草稿层逐条采纳/忽略/改时长，库侧回读；③ 真跑抓出并修 8 类缺陷（含 `gates/pending` 500→404、
门前置同源、审片页空真绿灯、草稿回收 + FK、构造器↔模型分叉、键盘可达性两处、通知链接口径）；
④ 证据 `docs/reports/h8-fr40-keyboard-e2e.md`；⑤ 18 条新测试。

---

## 9. 本轮踩过的坑（每一条都是真金白银的时间，别再踩）

1. **接口返回形状不许猜**：`payload` vs `payload_json`、`errorCode` vs `error_code`、`result` vs `result_json`。
   三次都是"把成功读成失败"或"把失败读成成功"。写断言前先 `curl` 看一眼真实 JSON。
2. **URL 参数名全站是 `?project=` 不是 `?projectId=`**（11 个页面全是 `project`）。面板里读错 → 命令拿到 null，
   还礼貌地提示一句"没有项目上下文"，看起来像绿的实际一个请求都没发。
3. **`page.wait_for_selector('[data-testid^="toast-"]')` 是假断言**：toast 容器一直在 DOM 里，任何一条历史提示都能让它过。
   要看**文字内容**，而且要有**第二个独立信号**（库侧计数/队列计数）。
4. **disabled 按钮不进 Tab 序** → `tab_to` 会报"焦点到不了"，看不出真原因是前置未满足。
   所以先断言 `gate-precheck-<门>` 不存在，再数 Tab。
5. **"0 张 / 全场景已看"是空真**：数据没到手时 `missing=[]`，绿灯和可点按钮都是假的。三态（载入中/未看全/已看全）。
6. **验收脚本不能借产品没准备好的状态**：这条链上"键盘跑不到交付"的真相是①G01 要口播音频
   （文件选择框是 OS 对话框，不属于网页键盘 → 用 `_scratch_state.build_audio_state` 自建）
   ②G02 没 whisper 模型（本机没有且不许下载 → 用产品自己的"手动对齐优先"路径，`pipeline.py::g02`）。
   这两步**写进脚本**才算覆盖，写"跳过"就是假绿。
7. **`lsof` 判据的主语是产品进程，不是整台机器**：不带 `-a -p` 会把 Qoder/OrbStack 的连接算进来，
   得到一个与 FilmFlow 无关的 False。正确口径：浏览器请求日志（`page.on("request")`）+ 按 pid 查 API 进程。
8. **goal 模式下 `sleep` 别超过 120s**（Bash 工具默认 2 分钟超时，会把你的 sleep 打掉）；
   长任务用 `run_in_background` + 事后 `Read` 日志。
9. 改 `server/app/**` 忘了重启 = 测旧代码（§2 E1）。

---

## 10. 汇报格式与停止条件

**每轮固定动作**（任务书 §9）：改代码 → 加/改守卫 → **实测** → 台账追加一轮（含失败与自错勘误）→ 提交 → 推送。

老板要求的汇报粒度：数字 + 命令 + 产物路径。例如
"`cd server && uv run pytest tests -q` → **NNN passed**（0 skipped 0 xfailed，用时 Xs）"。

**停止条件**（撞到就停下来问，不要绕）：

* 需要动执行器行为（要升 `EXECUTOR_VERSION`）或动 46/93/8+8 不变量；
* 需要下载任何在线资源（含 whisper 模型）；
* 需要破坏性库写或动演示项目；
* 键盘 e2e 复跑仍然不到 PASS，且原因**指向产品缺陷而不是测试**（此时按 §7 如实记为边界，不要放宽断言）；
* 需要新增 devDependency 或改 CI 门禁口径。

**绝对不许**为了让测试变绿而：放宽断言 / 删测试 / 加 `skip` / 加 `xfail` / 抬 lint 基线（ADR-0014、任务书纪律）。

---

## 11. 真源索引（想知道某个数，去哪里看）

| 想知道 | 看这里 |
|---|---|
| 本轮做到哪了 | 本文件 §4–§6 + `docs/process/overnight-ledger-2026-11-05.md` 轮 19 |
| 键盘验收的真实输出 | `docs/reports/h8-fr40-keyboard-e2e.md`（原始日志在 `/tmp/e2e_fr40_final1[0-4].log`，重启机器会没，别依赖） |
| 测试总数 | 实跑 `cd server && uv run pytest tests -q` |
| 19 项治理门禁 | `scripts/verify_p1_governance.py` |
| lint / a11y 口径与基线 | `docs/reports/lint-baseline.json` + `scripts/lint_ratchet.py` + `scripts/lint_a11y.py` |
| 命令与快捷键 | `web/src/lib/commands.ts`（面板、`?` 表、全局键位分发都从它派生） |
| 服务日志 | `~/.filmflow/logs/app.log`（`run parked`/`node failed` 都在这里，比猜快） |
| 库状态 | `sqlite3 -readonly ~/.filmflow/filmflow.db`（表名单数，§2 E5） |
| 老板的裁决与边界 | `docs/process/overnight-goal-2026-11-05.md` §12 / §14 |
