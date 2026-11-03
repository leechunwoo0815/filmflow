# 专家整夜自主循环 Runlog（2026-11-03 深夜启动）

> 执行者：ZCode（goal 模式，按 docs/process/expert-overnight-goal-prompt.md 协议）。
> 基线 DB 备份：`~/.filmflow/filmflow-before-expert-20261103-234205.db`（28.1MB）。
> 收敛判据与硬约束见该 prompt；本文件逐批追加：时间 / 动作 / 证据 / 结论 / 下一步。

## B0 · 基线（23:42–23:50）

- 读 AGENTS.md / HANDOFF §0–§10 / expert-review-analysis / ADR-0005~0012 ✅。
- 服务重启（pkill dev.sh + 端口 kill + nohup dev.sh），`/api/health` ok。
- `cd server && uv run pytest tests -q` → **189 passed, 50.45s** ✅
- `GET /api/projects` → **35**（跑 pytest 前后一致）✅
- `verify_p1_governance.py` → **8 步全 ✓**，跑完项目数仍 35 ✅
- `pnpm --dir web exec tsc --noEmit` → 退出码 0 ✅
- `uv run --project server ruff check server` → **504 errors**（187 --fix 可修 / 86 unsafe）= 基线一致 ✅

## 证伪阶段发现清单（F-*）

### F-DOC-1 · 档位验收 run 号口径 · CLOSED（HEAD 已正确）
- 复核：DB `project 248 (r2-profiles-251) / run 309`；`git show HEAD:AGENTS.md` 已是 run 309、
  `run 311` 出现 0 次（会话开场读到的是压缩前陈旧上下文，非仓库错误）。两处复核均通过：run 号 309 ✓、
  分窗口阈值 稳定段 0.98 / 切点 0.90 与脚本一致 ✓。

### F-EVID-1 · 老交付证据抽验 · CLOSED（证据完好，1 处口径澄清）
- 抽样 1：run 222（rumor-clean）G07 MP4 → `artifacts/f2/f21a7717….mp4` 70,542,684B **在盘**，
  文件名即内容 sha 自洽 ✓；run 272 G07 4f942b8e 70,327,613B 亦在盘 ✓（两者并存，
  `out/film/master.mp4` 是最后一次 Run（272）的拷贝——HANDOFF §2.6 数字与 run 222 对应，无造假）。
- 抽样 2：`docs/reports/golden/5s-original-run306.json`（schema filmflow.golden-report/2，SSIM 1.0）✓
- 抽样 3：`docs/reports/r2-incremental/5s-run303.json` ✓
- 待办（P2 级）：HANDOFF 补一句"`out/film/master.mp4` 属最后 Run"。

### F-MIG-1 · 迁移登记处 · SAFE
- `_add_columns_on` 先 `PRAGMA table_info` 查重 → 幂等；fn 抛错时 `eng.begin()` 回滚且不登记，
  下次启动重试；create_all 先行 → 新库列已存在，迁移 3 变 no-op；登记失败在 fn 成功后 → 重跑仍幂等。
- `test_migrations.py` 3 项 + 生产库 [1,2,3] 幂等复跑（verify_p1_governance 第 8 步）✓

### F-REQ-1 · 请求模型行为兼容 · SAFE（1 条口径备忘）
- PUT docs：旧 `int(payload.get("base_version", 0))` → 新 `payload.base_version` 默认 0，行为一致；
  非法类型从 500 变 422（改善）。前端逐路由键名一致（timeline/ops 发 camel、docs PUT 发 snake）。
- 备忘：routes.py 三处 base 键名三种写法（:765 camel / :2203 camel via extra / :2432 snake）——
  P1-23 建模剩余 42 个时**保留各路由原键名**，不要统一重命名。

### F-SSIM-1 · 档位分窗口阈值归因 · CONFIRMED-PARTIAL（阈值保持，归因补全）
- 独立探针 `scripts/probe_profile_ssim_offset.py`（run 309 final intermediate.mp4，8 点，
  final vs final±1/24s）：稳定段 worst **0.987533** / 切点窗口 worst **0.987099**。
- draft-vs-final 切点实测 0.952097 vs 相邻帧 0.987099 → ~0.035 差值**不能**全归因于 12fps 时间量化，
  另含 draft 原生 960×540 vs final 1080p 降采样的空间差（半调网点相位敏感）。
- 判断：0.90 阈值作为工程门可接受（余量 0.05），但 §2.4"属档位固有近似而非双实现漂移"的归因
  不完整；不改阈值（THRESHOLD-KEEP），补文档归因说明。

### F-DEL-1 · 快照缺失时交付门禁静默失效 · CONFIRMED（代码级，待修）
- `snapshot.py:31-34 ensure_run_snapshot`：`snapshot.json` 缺失或 schema 不符时**用当前文档重建快照**。
- `delivery.py:272-282 _ensure_run_documents_match`：随后"当前 timeline vs 重建快照"恒等 → 门禁 no-op。
- 影响：`runs/<id>/docs/` 被清理/损坏的非导入项目，交付门禁形同虚设。

### F-DEL-2 · 交付门禁只比 timeline，script 漂移不拦 · CONFIRMED（代码级，待修）
- 9:16 变体 `_render_variant_frames` 用 `pv.resolve_context`（当前文档）重渲；16:9 master 用 Run 旧帧。
- 改 script（不改 timeline）→ 16:9 旧文案 + 9:16 新文案 → 恰是 P1-13 要防的双画幅分叉。
- `_ensure_run_documents_match` 只取 `docs.timeline`（delivery.py:275）。

### F-DEL-3 · 封面标题读当前 script · CONFIRMED（随 F-DEL-2 一起修）
- `delivery.py:150-152 _title()` 读当前 script doc，非 Run 快照 → 封面标题可与成片文案漂移。

### F-DEL-4 · `_alignment` 回退读当前 `card/alignment.manual.json` · CONFIRMED（低危，记录不改）
- delivery.py:138：G02 产物缺失时回退**当前** root 下的 manual alignment；正常 Run 都有 G02 JSON，触发面小。

### F-LIC-1 · 许可门禁 · SAFE（抽查通过）
- `license_gap`：source/type 均 `.strip()` 后判空（纯空格被拒）；`expires` 用 `date.fromisoformat(exp[:10])`，
  非 ISO 报错、过期报错；PATCH `update_asset` 整体替换 license 且引用中禁削弱（:458-465）。
- "取消引用→清空→挂回"洗白链：Run 不查许可，但交付 `_asset_rights`→`asset_license_ok` 二次拦截 → 深度防御成立。

### F-ASSET-1 · timeline 文档跳过 walk_refs 兜底 · 口径差异（SAFE，记录不改）
- `scan_usages` 对 timeline 走 `_timeline_usages`（结构化三路径：layers[].assetSha / scene.fontSha /
  audio_layers[].assetSha）后 `continue`；根级散字段（如 assetShas 派生索引、假想的根级 fontSha）不计入。
- 渲染/compiler 也只读这三条路径 → 根级散字段对渲染是惰性数据，不构成真实引用面。与 §5.12"assetShas 是
  派生索引"口径一致。

### F-QA-1 · mix/license 撤销缺"当前==after"守卫 · CONFIRMED（代码级，待修）
- `qa.py:556-563`：kind=mix/license 的 undo 直接 `save_mix/save_license(before.content)`，不走
  `_require_undo_head`。手工改过 targetLufs/stems 后撤销 set_lufs 会静默覆盖手工编辑。
- timeline 分支（:534-555）有完整 LIFO 守卫 → 防御不一致。

### F-QA-2 · 分类型 LIFO 语义 · SAFE
- 混合撤销（timeline+mix+license 交错）：三类文件互不干扰，同类型内 `afterHash` 判链顶；抢跑报错并点名。
- 深拷贝：`_timeline_before` deepcopy（:361-364）；`load_mix/load_license` 每次全新 JSON 解析 → 无别名。
- P1-09 关联：extend_scene 的 profile 保存失败回滚路径（:416-421）回滚失败仅 `pass` —— 并入 P1-09 故障注入批次。

## 待证伪（下一步）
- 请求模型：baseVersion/base_version 别名、timeline/ops extra 透传、默认值一致性。
- 迁移登记处：MIGRATIONS vs 既有 DB、抛错半应用、create_all 顺序。
- 档位 SSIM 分窗口独立复测；老交付证据抽 3 份。

## 建设批 1 · 40s 增量实跑 + P1-12 非整数 fps（2026-11-04 00:30–01:10）

### 40s 增量实跑（交接"明确没做"最大项）· ✅ PASS
- 命令：`uv run --project server python scripts/verify_r2_incremental.py --project 40s --scene-index 2`
- 结果：run1 352.7s / run2 282.3s；**rendered=93/960 (9.69%)、reused=867**；first changed scene=S03、
  unchanged_prefix_frames=396；**报告归档 `docs/reports/r2-incremental/40s-run311.json`**。
- 与 HANDOFF §2.2 历史声称（93/960=9.69%）一致 —— 旧证据项目已删的数字现已在全新 Run 311 复现。
- 磁盘：脚本自动清 frames/proxy，`r2-verify-40s-252` 仅 94MB。

### P1-12 非整数 fps · ✅ 完成（RED→GREEN→升版→重跑）
- 新增 `server/app/engine/fpscalc.py`：`norm_fps`（数字/"23.976"/"24000/1001"）、
  `frames_for(duration,fps)=round(d*f)`、`frame_at/time_at`、`fps_rational`（NTSC 率出精确有理数）、`FPS_TOL`。
- 全仓 `int(fps)`/`round(d*int(fps))` 截断点接线：render_profiles(_tier/resolve/ensure_final_ready/
  新增 normalize_project_profile)、compiler、render_manifest(build_plan/plan_dirty/build_manifest)、
  pipeline(e01/e05/f03/F02/intermediate 编码)、executors.__init__(task 卡)、routes(3 处)、preview、
  templates、delivery(_render_variant_frames/_encode_frames→fps_rational/QC)。
- **THRESHOLD-CHANGE（1 处，已记录）**：final 门 `ffps < 24` → `ffps < 23.9`。理由：23.976/29.97 是
  广播标准交付帧率，原一刀切使 P1-12 对交付无用；23.9 仍拦住 draft 级 12fps。影响面：仅 final 门槛。
- **行为变化**：ensure_final_ready/plan_dirty 的 fps 比较从 int() 改容差（0.01）——修复
  "manifest 23.976 vs profile 24000/1001 误报 409/全量重渲"。
- 测试：`server/tests/unit/test_fps_math.py` 12 项（先 RED 后 GREEN；网格往返/单调/确定性/NTSC 归一）。
- 升版：`EXECUTOR_VERSION 2.9.3 → 2.10.0`（旧缓存自动失效）。
- 重跑：golden 5s 原帧 **run 312 SSIM 1.000000 / pHash 0**（6 帧，报告
  `docs/reports/golden/5s-original-run312.json`）；`verify_r2_profiles.py` PASS 且 8 点 SSIM 与
  run 309 完全一致（0.998663 / 0.952097）—— 整数 24fps 项目视觉零回归。
- 全量：`pytest tests/unit tests/bdd` 188 passed；integration 13 项待整批跑。
- 文档：HANDOFF/AGENTS 版本号与测试计数（201）已同步；P0-4b 40s 证据口径已更新。
- 磁盘：r2-profiles-254 / golden-5s-253 的 frames+proxy 已清（2.4G 持平）。

## 建设批 3 · F-QA-1 + F-DEL-1/2/3 修复（2026-11-04 01:10–01:50）

### 交付门禁（F-DEL-1/2/3）· ✅ 修复 + 9 项单测
- `delivery.py`：新增 `_load_run_snapshot_file`——只信磁盘 `runs/<id>/docs/snapshot.json`
  （缺失/JSON 损坏/schema 不符 → E_DELIVERY_GATE），**不再用 ensure_run_snapshot 重建**（关死
  F-DEL-1 的 no-op 通道）。
- `_ensure_run_documents_match`：script + timeline 都必须在快照中且与当前一致（当前侧行缺省时用
  与服务层同源的 default_doc 派生——copy.txt 被改仍会拦住真漂移）；profile 双方存在时也比对
  （9:16 变体按当前 profile 重渲）。探针实测：新项目无 script 文档行时快照与派生同源放行。
- `_title` 优先取快照 script（F-DEL-3），封面标题不再随当前文档漂移。
- 单测：test_p1_foundations.py 重写为真实快照文件契约，9 项（缺文件/坏 JSON/错 schema/缺 timeline/
  timeline 漂移/**script 漂移**/profile 漂移/全匹配放行/标题用快照）。
- `verify_p1_governance.py` 第 5/6 步改为真实落盘快照契约（先 ensure 落盘、改盘上快照合成漂移），
  去掉 monkeypatch；8 步全 ✓ 重跑通过。
- 教训记录：我写的两个哈希探针中途异常未走 destroy，向 DB 泄漏 project 252/253——已用
  `_acceptance.destroy` 清除，连同今晚验收产生的 249/250/251（报告已归档 docs/reports，
  DB/目录不再保留），**`GET /api/projects` 回到基线 35**。

### QA 撤销守卫（F-QA-1）· ✅ 修复 + 2 项单测
- `qa.py`：set_lufs/fill_license 的 after_state 增加 `hash=content_hash(after)`；
  `undo_fix` 的 mix/license 分支补 `_require_undo_head`（"混音配置"/"音乐许可"）——
  修复后又手工改过 targetLufs/许可时拒绝撤销并提示；旧记录无 afterHash 时走 legacy 放行（兼容）。
- 单测：手工改响度后撤销被拒 → 回到链顶后撤销放行并复原；许可同构（含"撤销回到不存在"）。
- `pytest tests/unit tests/bdd` → **196 passed**（此前 188 + 门禁 7 新增 -2 重写 + QA 2）。
