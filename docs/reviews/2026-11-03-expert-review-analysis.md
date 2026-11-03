# FilmFlow 专家审查复核与整改分析（2026-11-03）

> 审查基线：HEAD `82c992b`（`r3.5-qa-4-g82c992b`），代码验收 tag `r3.5-qa` → `3bb81a0`；分支 `master`；复核时工作区 clean。
> 审查范围：R1 核心 DAG、R2.0（FR-20–25/29/30）、R2.5（FR-26/27/28/31）、R3.0 v1（FR-32–38）、R3.5 FR-39；前端、后端、引擎、脚本、测试、文档、数据与运维。
> 原始未脱敏专家报告：`~/.filmflow/reviews/2026-11-03-expert-review.raw.md`（仅本地保存，不随公开仓库发布）。
> **修复进展（2026-11-03）**：P0-1、P0-2、P0-3、P0-5、P0-4a 已完成并通过回归；当前 `EXECUTOR_VERSION=2.9.3`、preview `1.8.0`。本文 §1/§2 的 `2.9.2`/`1.7.0` 是审查基线，不是当前版本；最新状态见 `HANDOFF.md` §0.5/§0.6。
> 本文是复核后的工程判断，不是对专家报告的逐字复述；两者冲突处，以本文标注的实测/代码证据为准。

## 0. 一页结论

**总体判断：Conditional Go（有条件通过）。**

当前基线不是“脚本全绿”的虚假繁荣：46/7/93/8+8/caps 不变量、版本纪律、JSON 原子写、路径白名单、内容寻址、乐观锁、DB 完整性这些硬骨头总体成立。但专家指出的三类系统性缺口是真实的：

1. **安全边界**：Next dev 监听全网卡并把 `/api/*` 反代到零鉴权后端；后端无 Host/Origin 校验。局域网可读写项目，任意网页可触发无体 POST/DELETE。
2. **preview/final 双实现漂移**：8 类转场中 7 类在 preview 退化为 `match-shape`，成片却正确；产品“预览即可信”的核心承诺被击穿。
3. **回归安全网缺失**：integration 测试直连生产 `:7860` 并污染真实 DB；Chrome 截帧、ffmpeg 合成、SSIM、响度达标在 pytest 内基本零覆盖；关键验收证据已灭失或不可移植。

**FR-40/41 准入：先修 P0，再开新功能。**

- 必须修完：P0-1（局域网/鉴权边界）、P0-2（转场映射统一）、P0-3（测试隔离）、P0-5（QA 修复接通渲染管线）。
- 必须至少完成 P0-4a：3s/12 帧最小真实出片冒烟（Chrome + ffmpeg + SSIM）。
- P0-4b（40s 增量可复现脚本、原分辨率 SSIM、证据归档）可与 FR-40/41 并行，但必须在下一轮验收前完成。
- FR-40（纯前端命令面板/通知）风险较低，可在 P0-1/P0-3 后并行；FR-41（会新增内容生成路径）应在 P0-2/P0-5 后开工。

**五个 P0 的规模**：P0-1 S、P0-2 S、P0-3 M、P0-5 M、P0-4a S–M、P0-4b L。专家给出的“3–5 人日”量级合理。

## 1. 复核基线与方法

本次复核只读代码、运行只读探测、使用 `--collect-only`，**没有修改代码**；没有重跑完整 pytest，避免在 P0-3 未修前继续污染生产 DB。专家已在审计中跑过 `137 passed in 29.02s`；本次用 `pytest --collect-only` 确认收集数仍为 **137**（unit 118 / integration 12 / BDD 7）。

| 项 | 本次实测 | 结论 |
|---|---|---|
| HEAD / tag | `82c992b` / `r3.5-qa-4-g82c992b` | 与专家一致 |
| 工作区 | clean | 一致 |
| 测试收集 | 137（118/12/7） | 一致 |
| `EXECUTOR_VERSION` | 2.9.2 | 一致 |
| preview 版本 | `preview-1.7.0` | 一致 |
| 路由 | 140 个 `@router.` | 一致 |
| 请求模型 | 51 处 `payload: dict`，0 个 Pydantic 请求模型 | 一致 |
| DB | 27 项目 / 1702 NodeRun / 1680 Artifact；`integrity_check=ok` | 专家审计后状态 |
| DB pragma | `journal_mode=delete`、`foreign_keys=0`、`synchronous=2` | 一致 |
| 项目目录 | 21 个 | 专家审计后状态 |
| 磁盘 | `filmflow-projects` 2.6G；`~/.filmflow` 418M | 专家审计后状态 |
| 监听 | Next `*:3000`；API `127.0.0.1:7860`；FrameServer `127.0.0.1:8787` | P0-1 关键证据 |
| 风格库 | 分配 9.3M；逻辑 74.7MiB；mp4 逻辑 59.8MiB、分配 0 | 专家此处有口径误判，见 §2.4 |
| Git | 381 个跟踪文件；`.git` 16.38MiB；62 个提交 | 无 secret/大 blob（抽查） |

## 2. 专家结论核验

### 2.1 P0 核验

| ID | 专家结论 | 本次复核 | 状态 |
|---|---|---|---|
| P0-1 | Next dev 全网卡 + 反代零鉴权 API | `lsof` 显示 `*:3000`；局域网 `:3000/api/projects` 返回 200；同 IP 直连 `:7860` 返回 000；无 Host/Origin 中间件 | **确认，E1** |
| P0-2 | 8 类转场 7 类 preview/final 分叉 | 遍历 `TRANSITIONS`，`preview._transition_type` 对英文枚举全部落到 `match-shape`，final 正确；输出 `divergent 7 / 8` | **确认，E1** |
| P0-3 | integration 直连生产服务，污染 DB；skipif 静默 | `conftest.py` 只隔离 `FILMFLOW_HOME`；integration 使用 `http://127.0.0.1:7860/api`；DB 中 228–240 共 13 条审计残留；4 处 skipif 硬编码风格库/服务存活 | **确认，E1/E2** |
| P0-4 | 出片核心链 pytest 零覆盖；证据灭失 | `pytest` 内无 Chrome/SSIM；唯一真实 ffmpeg 调用是 `test_audio_v2`；golden 在 480×270 缩略图上算；40s 增量无脚本；run 282 为 `failed` | **确认覆盖缺口，E2；P0-4 是工程债务而非功能错误** |
| P0-5 | QA 修复与渲染管线脱节 | `_apply` 的 `extend_scene` 只保存 timeline；`_profile(ctx)` 优先读 Run 快照；`retry_run` 复用旧 `snapshot.json`；`verified` 只做文档级 `analyze` | **确认，E2** |

### 2.2 P1 核验

| ID | 标题 | 复核状态 | 关键证据 |
|---|---|---|---|
| P1-01 | 无 CSRF/Origin/Host 校验 | **确认，E1** | 带恶意 `Origin` 的 GET 返回 200；`Host: attacker.example.com` 返回 200；无 `CORSMiddleware`/`TrustedHostMiddleware` |
| P1-02 | `_external_fingerprint` 根节点不可达 | **确认，E2** | A01/A03/F01/G01 的 `UPSTREAM` 全为空；唯一调用点在遍历 `UPSTREAM` 的循环内 |
| P1-03 | 引擎包/渲染器 JS 不在缓存键 | **确认，E2** | `compute_pack_sha` 6 处调用均不在 `node_cache_key` 路径；C01 键只含 params/A06/B08 sha/caps |
| P1-04 | G02 手动对齐、G04 音乐 take 未入缓存键 | **确认，E2** | G02 读 `card/alignment.manual.json`、G04 读音乐 take；`projectInputs` 仅 G01/G05/G06/G07 |
| P1-05 | A05 人工门无条件自动批准 | **确认，E2/E1** | `_auto_approve_a05` 不检查 `imported`/`style_decision`；DB 24 条 A05 全部 `author=local, policy=inherit` |
| P1-06 | SQLite 无 WAL、外键未强制 | **确认，E1** | `journal_mode=delete`、`foreign_keys=0`、`synchronous=2` |
| P1-07 | 无通用迁移框架 | **确认，E2** | `init_db` 只 `create_all` + `_migrate_job_table`；`SchemaMigration` 仅记录 1/2/3 |
| P1-08 | timeline 409 静默丢弃未保存文案 | **确认，E2** | 409 分支 `await load()`；`useEffect` 以 `selectedId/version/script` 重置 `textDraft`；忽略 `details.diff` |
| P1-09 | 多步写无事务 | **部分确认，E2** | materialize/branch/replace 确有多 commit/文件写交错；本次未构造失败注入，未复现半成品 |
| P1-10 | 零 ErrorBoundary；页面静默失败 | **确认，E2** | 无 `error.tsx`/`global-error.tsx`；monitor/player 多处裸 `.then()`/无 catch |
| P1-11 | 100 场景 60fps 声明无实现支撑 | **部分确认，E2/E3** | 时间轴全量 `.map()` 渲染；无虚拟化；60fps 未实测 |
| P1-12 | 非整数 fps 被静默截断 | **确认，E2** | preview/render_profiles/compiler/pipeline 多处 `int(fps)`；未实跑 23.976 |
| P1-13 | 16:9 与 9:16 来自不同时间基线 | **确认，E2** | 16:9 复用 Run F04；9:16 走 `pv.resolve_context` 读当前 docs；`ensure_final_ready` 不校验 timeline hash |
| P1-14 | `verify_r2_profiles.py` 排序崩溃 | **确认，E2** | 第 146 行按 `(profile,size)` 排序；D02 contact sheet 的 meta 无 `profile` |
| P1-15 | 删除保护/替换只扫 timeline | **确认，E2** | `scan_usages` 仅遍历 ProjectDoc(kind=timeline)；未扫 Template.content_json/Run 快照/audio.json |
| P1-16 | 许可强制只对字体，且可清空/洗白 | **确认，E2** | `import_asset` 仅 `real_kind=="font"` 检查；`update_asset` 允许清空；`rights.json` 硬编码 Noto Sans SC |
| P1-17 | QA 撤销链一步即断 | **确认，E2** | `afterVersion` 要求当前版本等于修复后版本；每次 save_doc +1；无步数上限 |
| P1-18 | `fill_license` 准凭空填许可 | **确认，E2** | 建议 params 内置 `authorized: True`；UI 两个 prompt 预填“自制/CC0” |
| P1-19 | 验收脚本硬编码演示 ID，且改/删演示数据 | **确认，E2** | e2e_takes PID 188/run 237/254；verify_r3_qa PID 227 改写 timeline；e2e_assets/audio PID 211；多处硬编码主目录 |
| P1-20 | SDLC 声明与 git 现实脱节 | **部分确认，E1** | 62 提交中 `test:` 本次统计为 1（专家写 2，差异不影响结论）；feat/docs 巨提交；无 CI/验收日志 |
| P1-21 | fresh clone 无法走通检查表 | **部分确认，E2** | 依赖仓库外风格库、rumor-39s、系统 Chrome/ffmpeg、DB 内演示项目；本次未在干净机器实测 |
| P1-22 | 白名单 env 覆盖导致 import 期崩溃 | **确认，E1** | `FILMFLOW_WORKSPACE_ROOTS=/tmp/other` → `SettingsError`；仅 JSON 数组可用；`.env.example` 未提 |
| P1-23 | 51 个端点用 `payload: dict`，零请求模型 | **确认，E1/E2** | `grep -c` = 51；`BaseModel` = 0 |

### 2.3 P2/P3 索引（详见原始报告）

P2 共 35 条，按主题归组：

- **引擎/缓存/并发**：P2-01 门继承无 workflow 过滤、P2-02 timeout/retries 死配置、P2-03 同项目并发 Run 无互斥、P2-04 帧文件非原子写、P2-05 delivery 无幂等、P2-06 缓存命中无 workflow 作用域。
- **数据/事务**：P2-07 DocRevision 无上限、P2-08 JSON 侧 load-modify-save 无锁、P2-09 两个 “unique” 索引实非 unique。
- **媒体**：P2-10 交付 QC 硬编码 24fps、P2-11 图片失败画 X 框、P2-12 音频 loudnorm/色彩/码率问题簇、P2-13 转场期文字淡出、P2-14 相机 anchor 三路径不一致且 ease 被忽略、P2-35 preview/final 字体 CSS 优先级相反。
- **QA/定位**：P2-21 报告 `failed`/`successRate` 结构性失真、P2-22 分类靠消息子串、P2-23 定位 fps 口径错位。
- **前端**：P2-15 a11y 近零、P2-16 zustand/react-query 死依赖、P2-17 资产删除与渲染竞态/无 GC、P2-18 模板丢 scene.text、P2-19 模板升级删图层、P2-20 系列半途失败留孤儿。
- **运维/质量**：P2-24 limit 未下推 SQL、P2-25 17 个 feature 仅 2 个绑定、P2-26 e2e flaky/无 CI、P2-27 恒真/退化断言、P2-28 无服务级日志、P2-29 ruff 517 errors/1 F821、P2-30 21 处 except pass/87 type ignore、P2-31 C02 字体无 sha pin、P2-32 FrameServer 无鉴权、P2-33 黄金证据引用 failed run/缩略图 SSIM、P2-34 手工 DB 备份。

P3 共 26 条，主题包括：模块级单例/配置未接线/组件扩展点、aware UTC 落库变 naive、`/api/artifacts/{id}/file` 无白名单、SVG 上传与缺 CSP/nosniff、500MB base64 内存放大、可预测 Chrome profile/CDP 9222、帧数计算散布、文本避头尾/emoji 硬失败、预览 JPEG 中转、播放器 fps/JKL、Asset 绝对路径、`list_assets` O(项目×场景)、模板变量缺失不阻断、QA wrap_text 固化文案、`analyze` 重复执行/阻塞、前端轮询/SSE/响应式/硬编码首页路径、ffmpeg GPL/仓库无 LICENSE、DB 空闲页、取消状态、长 session、routes.py 2560 行、.DS_Store。

> P2/P3 未逐条重跑；表中“确认”主要来自代码走查或专家 E1。整改时应按批次补测试，而不是一次性全改。

### 2.4 专家报告纠错与口径澄清

这是本次复核最重要的“反审查”部分。专家报告整体质量高，但以下结论需要修正或谨慎引用：

1. **“风格库 76MB 失实 8 倍，实为 9.3MB；3 个 mp4 全部 0 字节”是误判。**
   - 实测：`du -sh` = 9.3M，这是**磁盘分配**；`stat` 逻辑大小合计 **74.7MiB**，3 个 mp4 逻辑大小 **59.8MiB**（约 17–22MB/个），但均为**稀疏文件**，分配块为 0。
   - 因此文档的“76MB 库 / 61MB 示例 mp4”描述的是逻辑体积，基本准确；“9.3MB”是磁盘占用。正确结论应是：**文档未区分逻辑大小与磁盘分配，容易误导；但不是 8 倍虚报。**
   - 建议在 `vendor/README.md` 增加一行：“逻辑约 75MiB；示例 mp4 为稀疏文件，磁盘分配约 9.3MiB。”
2. **提交数差异**：专家写“62 个提交中 `test:` 仅 2 个”；本次 `git log --format=%s | grep -c '^test:'` = **1**。不影响“SDLC 与 git 现实脱节”的结论，但引用时应写“1–2 个（口径差异）”。
3. **DB/磁盘/空闲页是审计时快照**：专家报告写 14→27、2.1G/183M、freelist 1734；本次当前值为 27/21、2.6G/418M、freelist 567。原因是审计本身创建了项目/产物，后续又有运行。引用时必须带时间点，不能当作当前基线。
4. **P0-4 不是功能错误，是回归安全网缺口**：把它列为 P0 是因为它让后续改动无法被自动验证，而不是当前用户会立即看到错误。整改时应拆成 P0-4a（最小真实出片冒烟）和 P0-4b（黄金/40s 证据治理）。
5. **P0-3 的 DB 污染包含专家自己的 4 次 pytest/e2e**：228–240 的产生时间与专家报告一致；这不是全部既有问题，但机制是真实的，且每跑一次测试就复现。
6. **P1-20 的“验收造假”措辞过重**：报告自己也承认“结论层面未发现造假”。更准确的表述是“验收过程不可独立审计、数字事后改写、证据不可复现”，而不是主观造假。
7. **P1-21 fresh clone 未在干净机器实测**：属于高置信度推断（E2），不是 E1；应通过 bootstrap 脚本验证。
8. **P1-11 “100 场景 60fps”**：代码确实没有虚拟化，播放头每帧 `setPlayhead` 触发全树重渲染；但 60fps 未实测，不能写成“已确认卡顿”，应写“性能声明无实现支撑，需实测”。
9. **P2-35 字体 CSS 优先级**：本次确认 preview 先读 `fonts/embed.css`，final 先读 `fonts/noto-sans-sc/embed.css`；但只有当两个文件同时存在且内容不同才会漂移，属条件性缺陷。
10. **P3-22 freelist**：当前 567 页（约 2.2MiB），不是专家报告时的 1734 页（约 7MiB）；结论“从未 VACUUM”仍成立，但数字需更新。

### 2.5 已确认做得好的部分

- **不变量**：46 节点 / 7 阶段 / 93 边（data 81、trigger 10、order 2）/ 8 人工门 + 8 自动门 / 7 caps；本次直接读取 `edges.py` 复核成立。
- **版本纪律**：`EXECUTOR_VERSION=2.9.2`；专家报告称 21 次变更均有原因，未发现“改行为不升版”；FR-37 不改执行器故不 bump 合理。
- **路径安全**：`_safe_join` 使用 `resolve()` + `is_relative_to`；专家实测 `..`、绝对路径、符号链接三类用例均阻断；全仓无 `shell=True`/`os.system`，subprocess 使用 argv。
- **数据完整性**：DB `integrity_check=ok`；`foreign_key_check` 零违规；artifact/job/noderun→run 零孤儿；JSON 类文件普遍 tmp + `Path.replace()` 原子写。
- **内容寻址/资产**：sha256 去重、global/project scope 隔离、跨项目私有资产引用阻断。
- **乐观锁后端**：ProjectDoc CAS + 409 带 diff + DocRevision 版本链；问题主要在前端 409 处理。
- **测试质量**：137 项构成真实，unit 层几乎不 mock；`test_assets.py` 真查 cmap，`test_audio_v2.py` 真调 ffmpeg。
- **范围诚实**：FR-40/41、R4、30 步 UI 连点、浏览器 60fps、多 worker 等未做/未测项均如实标注，没有把未开始项写成已完成。

## 3. 五个 P0 的根因与修复设计

### P0-1 局域网暴露零鉴权 API

**根因**：`dev.sh` 用 `pnpm dev` 启动 Next，Next dev 默认绑定 `0.0.0.0`；`next.config.mjs` 无条件把 `/api/:path*` 反代到 `127.0.0.1:7860`；后端假设只被本机访问，没有 Host/Origin 校验。后端本身绑定 127.0.0.1 是正确且有效的（局域网直连 :7860 失败），但 Next 代理把边界打开了。

**修复建议（按层）**：

1. `dev.sh`：`pnpm exec next dev -H 127.0.0.1`（或 `pnpm dev -- -H 127.0.0.1`，以 Next 15 实际 CLI 为准）。
2. 后端加 `TrustedHostMiddleware(allowed_hosts=["127.0.0.1","localhost"])`；对状态变更方法校验 `Origin`（允许 `http://127.0.0.1:3000`/`http://localhost:3000`，拒绝其他）。
3. 可选但推荐：启动时生成 `~/.filmflow/token`，前端经 rewrite 注入 `X-FilmFlow-Token`；所有 POST/PUT/PATCH/DELETE 校验。这样即使 Host/Origin 被绕过，也有第二道门。
4. 保持 API 端口只绑 127.0.0.1；不要为了“方便手机访问”改成 0.0.0.0。

**验收**：第二台机器/手机访问 `http://<LAN-IP>:3000/api/projects` 连接失败；带错误 Host 返回 400；跨源 Origin 的写请求返回 403；本机 UI 全部功能正常；补一条安全回归测试。

**工作量**：S（1 小时内可完成主修复，token 层再加半天）。

### P0-2 preview/final 转场映射分叉

**根因**：`preview.py::_transition_type` 与 `pipeline.py::_transition_type` 是两份实现。前者只做中文子串匹配，后者先精确匹配英文枚举。`timeline_ops.TRANSITIONS` 和内置模板都产出英文枚举，所以经 UI/模板设置过转场的项目在 preview 全部退化为 `match-shape`。

**修复建议**：

1. 把 `transition_type` 抽到共享模块（如 `engine/scene/transitions.py`），preview 与 pipeline 同时 import；删除两份实现。
2. 参数化测试遍历 8 个 `TRANSITIONS`，断言 `preview == final`。
3. 在 SSIM 验收选点中加入 `next.start ± 0.25s` 的转场窗口，避免同类漂移再次漏网。
4. 检查内置场景模板中的转场值（`templates.py`）全部走同一枚举。

**验收**：`divergent 0 / 8`；转场窗口 SSIM 仍 ≥ 0.98；新 Run 的 preview 与 final 在 8 类转场下肉眼一致。

**工作量**：S。

### P0-3 测试污染生产 DB + 静默 skip

**根因**：`conftest.py` 只把 `FILMFLOW_HOME` 隔离到 `/tmp/filmflow-test-home`，但 integration 测试通过 HTTP 打真实运行的 `:7860`，该进程使用真实 `~/.filmflow/filmflow.db`；`test_docs_api` 的 `finally` 只删目录不删 DB 行，`test_wizard_flow` 两者都不删。4 处 `skipif` 硬编码风格库路径/服务存活，换机即静默 skip。

**修复建议**：

1. integration fixture 内启动独立 uvicorn：独立 `FILMFLOW_HOME`、独立端口（临时端口）、独立 DB；测试结束 kill + 清理。
2. `skipif` 条件改读 `settings.style_library_root`；核心环境（Chrome/ffmpeg/风格库）缺失时用 session 级断言报 `E_ENV_MISSING` 硬错，不静默 skip。
3. 每条 integration 测试使用 `tmp_path` 或在 `finally` 删除 DB 行 + 目录；连续跑两次 pytest，DB 项目数不变。
4. 给测试加 `pytest -m "not slow"` 分层，避免 CI 每次都扫 341 风格库。

**验收**：连续两次 `pytest tests -q` 后生产 DB 项目数不变；无风格库机器上报明确错误而非 skip；137 项数字仍可比较。

**工作量**：M（1–2 天）。

### P0-4 出片核心链零自动化回归 + 证据灭失

**根因**：真实渲染慢且产物体积大（5s 项目约 541MB），团队把 Chrome/ffmpeg/SSIM 验证放在手工脚本；pytest 只测纯函数/契约。`golden_run.py` 在 480×270 缩略图上算 SSIM（阈值实际 0.98 + pHash≤6），文档却写 1.0；40s 增量证据项目已删，`verify_r2_incremental.py` 只做 5s；run 282 实际 failed，却被正文当作 FR-36 证据。

**修复建议**：

- **P0-4a（先做）**：3s/12 帧最小真实出片冒烟：Chrome 截帧一次、ffmpeg 合成一次、SSIM 计算一次；标 `@pytest.mark.slow`；清空 `~/.filmflow/cache` 后仍绿。
- **P0-4b（随后）**：把 40s 增量做成可执行脚本（或扩展到 `verify_r2_5s_incremental.py --project 40s`）；黄金报告按 runId 归档 JSON；SSIM 提到原帧分辨率；`--update` 加审批/记录；修正 run 282 证据引用。
- 在 CI 或夜间任务跑 `golden_run.py --project 5s`，报告入库。

**验收**：删掉缓存后冒烟仍绿；40s 增量脚本可复现 9.69%；黄金报告带环境指纹；run 状态为 succeeded 才可作为证据。

**工作量**：P0-4a S–M；P0-4b L。

### P0-5 QA 修复给出虚假确认

**根因**：`_apply` 的 `extend_scene` 只改 timeline doc，不写 profile doc；E01/F02/G05 的 frames/duration 来自 profile（Run 快照或 `project.profile.json`），`render_manifest` 把场景 clamp 到 profile frames。于是扩出的 0.5s 在 final 被截掉；扩中间场景会把后续场景推移，尾部场景 range 清空，内容整场消失，而帧数/时长 QC 仍绿。`retry_run` 复用旧 `snapshot.json`，时间轴类修复对重试不生效；`verified=True` 只反映文档级 `analyze` 通过。

**修复建议**：

1. `extend_scene` 在同一事务中更新 timeline doc + profile doc（duration/frames），或提供显式的“同步 profile”步骤；如果只改 timeline，必须在响应中明确要求新 Run，不能报 `verified=true`。
2. `retry_run` 改为 fork 新 Run（或显式刷新快照）；不要复用旧 `runs/<id>/docs/*.doc.json`。
3. “立即验证”至少对受影响场景跑一次静帧/预览比对；验证失败要回滚，而不是只记 `verified=False`。
4. 为 `extend_scene` 增加端到端测试：apply → 新 Run → ffprobe 时长增加且尾部场景仍在。

**验收**：text_overflow 项目扩 0.5s 后，新 Run 的 master 时长增加，尾部场景存在；`verified=true` 必须蕴含渲染级证据。

**工作量**：M（1–2 天，依赖 P0-2 的 preview 可信）。

## 4. 整改路线图

### Wave 0（立即，1–2 天，S 级为主）

1. **P0-1**：Next 绑定 127.0.0.1 + TrustedHost/Origin 校验（可先不做 token）。
2. **P0-2**：抽公共 `_transition_type` + 8 类参数化测试 + 转场窗口 SSIM。
3. **P1-02/P1-03/P1-04**：根节点自指纹、C01 键注入 `enginePackSha`、G02/G04 输入入键；各配一条失效测试。这三项修复成本极低，收益最高。
4. **P1-05**：A05 自动批准加 `imported or style_decision` 守卫。
5. **P1-06**：SQLite `WAL` + `foreign_keys=ON` + `synchronous=NORMAL`。
6. **P1-22**：`.env.example` 补 `FILMFLOW_WORKSPACE_ROOTS`，`Settings` 接受逗号分隔或明确 JSON 数组。

### Wave 1（2–4 天，M 级）

1. **P0-3**：integration 独立服务/DB；skipif 读 settings；conftest 环境断言；连续两次 pytest DB 不变。
2. **P0-5**：extend_scene 同步 profile；retry_run fork；验证回滚；E2E。
3. **P1-08**：timeline 409 保留 draft + 展示 diff + 强制覆盖。✅ 已完成（保留草稿 + 「只看服务端 / 保留本地并重试」，冲突期间暂停自动保存）。
4. **P1-13**：9:16 变体读 Run 快照，或交付前校验 timeline hash。✅ 已完成（交付前比对当前 timeline 与 Run 快照哈希；生产库 22 个真实快照回归：18 放行 / 4 真实漂移拦截，零分歧）。
5. **P1-15/P1-16/P1-17**：✅ 全部完成。P1-15（引用面含模板/其它文档/Run 快照）、P1-16/P1-18（入库需 source+type、引用中不可清空、rights.json 由真实资产生成、QA 不再预置 authorized）、P1-17（撤销链按 afterHash 链顶逐级 LIFO 回退 + 修掉 before/after 引用别名）。
6. **P1-14/P1-19**：修 `verify_r2_profiles.py` 排序崩溃（✅ 代码已修，待实跑）；验收脚本自建自删（🟡 已开始：`scripts/_acceptance.py` + `verify_r3_qa.py` 已自包含，演示 227 不再被改写；其余脚本待迁）。

### Wave 2（1–2 周，L 级/治理）

1. **P0-4a/P0-4b**：最小真实出片冒烟、40s 增量脚本、原分辨率 SSIM、证据归档。
2. **P1-07**：✅ 已完成（`db.MIGRATIONS` 登记处 + 幂等 `apply_migrations`，取代一次性 `_migrate_job_table`；未引入 Alembic，SQLite 单文件场景下登记表足够）。
3. **P1-23**：高风险端点 Pydantic 请求模型。
4. **P1-10/P1-11/P2-15/P2-17**：ErrorBoundary、时间轴虚拟化、a11y、资产 GC。
5. **P2/P3**：按主题分批，优先缓存正确性、媒体一致性、安全纵深、日志/可观测性。

### FR-40/41 准入

- 必须先完成：P0-1、P0-2、P0-3、P0-5、P0-4a。
- 建议同时完成：P1-02/03/04、P1-05、P1-06。
- 准入验收：
  - `divergent 0/8`；
  - 连续两次 pytest 生产 DB 项目数不变；
  - LAN/Origin/Host 探测失败；
  - QA extend_scene → 新 Run ffprobe 时长增加且尾部场景存在；
  - 3s/12 帧真实出片冒烟绿；
  - 137 项旧测试 + 新增测试全绿。

## 5. FR 追踪结论

| FR | 结论 | 关键问题 |
|---|---|---|
| R1 DAG 46/93/caps/门 | 🟢 成立 | A05 自动批准削弱“人工门”语义（P1-05） |
| R1 风格索引 341 | 🟡 依赖仓库外库 | skipif 静默；本机可用 |
| FR-20 参数化渲染链 | 🟢 | — |
| FR-21 组件库 12 组件 | 🟢 | 扩展点需改 4 处（P3-03） |
| FR-22 场景级增量 | 🔴 40s 部分 | 40s 证据项目已删、无脚本 |
| FR-23 预览 | 🟡 | 转场 7/8 分叉（P0-2） |
| FR-24 档位 | 🟡 | `verify_r2_profiles.py` 崩溃；SSIM 选点避开转场 |
| FR-25 文档版本化 | 🟢 | 后端乐观锁质量好；无 30 版上限 |
| FR-26 静帧审阅 | 🟢 | 脚本可自建 |
| FR-27 音频 v1 | 🟢 | — |
| FR-28 交付 v1 | 🟢 带缺陷 | 16:9/9:16 基线不同、fps 硬编码 24、rights 硬编码 |
| FR-29 Job/恢复 | 🟢 | 半写帧毒化（P2-04） |
| FR-30 黄金回归 | 🟡 | 缩略图 SSIM、run 282 failed、15s/40s 报告缺失 |
| FR-31 新手引导 | 🟢 | 示例/模板音轨边界已标注 |
| FR-32 时间轴 | 🟢 | 无虚拟化；30 步 UI 连点未自动化 |
| FR-33 审片批注 | 🟢 | 并发批注丢更新（P2-08） |
| FR-34 相机/转场 | 🟡 | 转场 P0-2；anchor/ease 不一致 |
| FR-35 音频 v2 | 🟢 | `onsets>=0` 恒真断言 |
| FR-36 资产库 | 🟡 | 验收规模小；引用面只扫 timeline |
| FR-37 模板/系列 | 🟢 | 丢 text override、升级删图层 |
| FR-38 Take 对比 | 🟢 不可移植 | 硬编码 188/237/254，DELETE 253/254 |
| FR-39 QA 修复 | 🔴 | P0-5 虚假确认、撤销链断、统计失真 |
| FR-40/41 | ⚪ 未开始 | 如实标注 |
| R4 | ⚪ 未开始 | 如实标注 |

## 6. 当前工作区状态与审计残留

本次复核没有清理任何数据。当前状态：

- DB：**27 个项目**（审计前 14；228–240 为审计新增 13 行），1702 条 NodeRun，1680 条 Artifact；`integrity_check=ok`。
- 项目目录：**21 个**；其中 `it-docs-*`/`it-import-*` 等 8 条 DB 行的 root 目录不存在。
- 磁盘：`filmflow-projects` 2.6G；`~/.filmflow` 418M（含 backups/cache/logs/db）。
- 测试：`pytest --collect-only` = 137；未重跑完整套件。
- 运行中服务：Next :3000、API :7860、FrameServer :8787；无运行中 Job（复核时）。
- Git：工作区 clean；无 remote（复核开始时）。

**清理建议（未执行，需明确批准）**：

1. 先备份 `~/.filmflow/filmflow.db`（现有 backups 是手工副本）。
2. 确认无运行中 Job/Chrome/ffmpeg。
3. 只删除审计残留：DB `project.id >= 228` 及其关联行 + 对应 `it-*`/`r2-profiles-*` 目录；不要动演示项目 202/174/188/211/215/216/223/227。
4. 删除前后各出一份计数对照；不要 `rm -rf` 整个 `filmflow-projects`。
5. 清理后更新 HANDOFF 的 DB/目录数字。

## 7. 文档与版本需要同步的项

已在本次提交中同步：

- `HANDOFF.md`：专家审查结论、P0 阻塞、DB 27/21 口径、下一步先修 P0。
- `AGENTS.md`：当前进度改为“专家审查 Conditional Go，先修 P0 再开 FR-40/41”。
- `docs/process/r3_plan.md`：QA 报告数字改为最终 8/8；追加专家审查阻塞段。

尚未改代码/测试，留待整改批次：

- `models.py:1` “15 张表” → 实际 21 张。
- `smoke_m1.py:68` `edges>=80` → 应 `==93`。
- `verify_r3_audio_v2.py:89` `onsets>=0` → 应断言具体数量/范围。
- `test_frame_fixtures.py:55` 条件表达式退化 → 应显式断言。
- `test-strategy.md` “环境断言/不静默跳过” → 与 conftest 实现不一致，修测试或改文档。
- `README.md` 预览数字与 HANDOFF/ADR 三组值不一致 → 标注为历史快照或统一。
- `main.py`/`pyproject.toml` 版本恒 0.1.0 → 决定是否随里程碑 bump。
- `vendor/README.md` 风格库体积 → 增加“逻辑大小 vs 磁盘分配”说明，避免再次误判。

## 8. 结论

专家的核心判断成立：**当前基线可以继续开发，但不能直接宣称生产级；FR-40/41 之前必须先修 P0。** 最值得先做的不是大重构，而是五个小而关键的修复：

1. 把 Next 关回 127.0.0.1，并加 Host/Origin 校验。
2. 把转场映射抽成一份实现，补 8 类参数化测试。
3. 把 integration 测试从生产服务上摘下来。
4. 把 QA 修复接到 profile/Run 快照上，让 `verified` 有渲染级证据。
5. 补一个 3s/12 帧真实出片冒烟，恢复回归安全网。

完成这些后，再开 FR-40/41，才符合“预览即可信、完成即有证据”的项目标准。

---

### 附：本次复核使用的主要只读命令

```bash
git rev-parse HEAD && git status --porcelain && git describe --tags --always
uv run --project server pytest server/tests --collect-only -q
uv run --project server ruff check server/app scripts --select F821
sqlite3 "file:$HOME/.filmflow/filmflow.db?mode=ro" "pragma integrity_check; ..."
lsof -nP -iTCP:3000 -sTCP:LISTEN
curl -s -o /dev/null -w '%{http_code}' -H 'Origin: https://evil.example.com' http://127.0.0.1:7860/api/projects
curl -s -o /dev/null -w '%{http_code}' -H 'Host: attacker.example.com' http://127.0.0.1:7860/api/projects
PYTHONPATH=server uv run --project server python -c "from app.services.preview import _transition_type as pv; ..."
FILMFLOW_WORKSPACE_ROOTS=/tmp/other PYTHONPATH=server uv run --project server python -c "import app.config"
```

未重跑完整 pytest 的原因见 §1；这不影响“137 collected”与既有 137 passed 的基线判断，但 P0-3 修复后必须重新全量跑一次并记录环境指纹。
