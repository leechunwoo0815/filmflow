# FilmFlow 交接文档（HANDOFF）

> 更新时间：2026-11-03 20:00（本地，darwin）· **R2.0/R2.5/R3.0 v1（FR-32–38）/R3.5 FR-39 已交付；专家审查 Conditional Go 的 P0 Gate 已全部关闭；P1 治理已推进 14 项，剩余见 §0.6/§6.5**
> 复核基线：本轮 P1 治理最后一个提交 `9bc0f95`（master，已推送 `git@github.com:leechunwoo0815/filmflow`）；FR-39 代码 `3bb81a0`（tag `r3.5-qa`）、FR-37 `f887424`、FR-36 `900076b`、`7a0ee2c`、R2.5 基线 `b7591bd`。本轮 9 个提交的清单见 §0.6 表尾。
> 测试 **219 passed + 1 skipped（unit 190 + integration 13 + BDD 7 + 门禁 happy-path；`foreign_keys=ON`）**，`pytest server/tests -q` 约 55s；integration 用独立临时 uvicorn/HOME/workspace，连跑两次生产 DB 不变；`EXECUTOR_VERSION=2.10.0`、preview `1.8.0`。
> 数据现状：**DB 35 个项目 / `filmflow-projects` 29 个目录 2.3GB / `~/.filmflow` 1.1GB**（审计与验证残留，删除需老板点头；口径见 §0.5/§7.4）。
> **先读本文 §0（§0.5 审查结论、§0.6 状态表、§0.7 破坏性语义与运维坑）、§5、§6.5；再读 `AGENTS.md`、`docs/process/r3_plan.md`、`docs/reviews/2026-11-03-expert-review-analysis.md`、PRD-002、ADR-0005/0007/0008/0009/0010/0011/0012。**
> 上下文压缩后继续开发时：按 §6.5 的顺序做 P1 剩余项，不要提前做 R4，不要回滚已完成部分；申报完成必须按 §0.7 的复现命令附证据。

---

## 0. 下一个 Agent 从这里开始（15 分钟）

### 0.1 工作目录与服务

```bash
cd /Users/litianyu/cc-projects/ai-v/filmflow
./dev.sh                  # API :7860 + Web :3000
curl -s http://127.0.0.1:7860/api/health
```

Web 入口：`/`（模板/项目）、`/wizard`、`/canvas?project=&run=`、`/editor`、`/timeline`、
`/review`、`/player`、`/takes`、`/audio`、`/assets`、`/templates`、`/qa`、`/delivery`、`/help`。
API 文档：`http://127.0.0.1:7860/api/docs`。

### 0.2 第一小时必做

> **2026-11-04 判官复核**：整夜自主循环结果（`044ff59..280cd7f`）的独立审查结论在
> [`docs/process/judge-review-2026-11-04.md`](docs/process/judge-review-2026-11-04.md) ——
> 判定**未完成**：1 个 P0（`DELETE /projects/{id}` 可删到工作区根与 rumor 参考项目）、NTSC 交付路径仍截断 fps、
> 422 信封打破前端契约、60fps 结论来自空载测量、报告 4 处度量与实测不符。修单与验收口径见该文 §六。

> 若要交给专家做整夜自主循环开发（goal 模式），提示词已固化在
> [`docs/process/expert-overnight-goal-prompt.md`](docs/process/expert-overnight-goal-prompt.md)：
> 含收敛判据、先证伪再建设的顺序、每轮循环协议、反作弊条款与收尾产物要求。

```bash
cd server && uv run pytest tests -q                       # 219 passed
cd .. && uv run --project server python scripts/e2e_ui.py  # UI 8 场景 ~16s
uv run --project server python scripts/e2e_onboarding.py   # FR-31 UI 冒烟
uv run --project server python scripts/smoke_m1.py         # 46 / 93
uv run --project server python scripts/verify_r2_incremental.py --project 5s
uv run --project server python scripts/verify_r2_preview.py
uv run --project server python scripts/verify_r2_profiles.py
uv run --project server python scripts/verify_r2_recovery.py   # 会杀/重启 dev.sh
uv run --project server python scripts/golden_run.py --project 5s --resolution original
uv run --project server python scripts/verify_r2_5_review.py
uv run --project server python scripts/verify_r2_5_audio.py
uv run --project server python scripts/verify_r2_5_onboarding.py
uv run --project server python scripts/verify_r2_5_delivery.py
uv run --project server python scripts/verify_r2_5_delivery_40s.py
uv run --project server python scripts/verify_rumor_regression.py   # 干净 rumor 46/46
uv run --project server python scripts/verify_r3.py                 # R3 时间轴+审片
uv run --project server python scripts/verify_r3_camera.py          # 相机/文本/转场 final
uv run --project server python scripts/e2e_r3.py                    # R3 时间轴/审片 UI
uv run --project server python scripts/verify_r3_takes.py           # Take 对比/采纳/分支
uv run --project server python scripts/e2e_takes.py                 # Take UI 同步/差异
uv run --project server python scripts/verify_r3_audio_v2.py        # 音频 v2 全链
uv run --project server python scripts/e2e_audio_v2.py              # 音频 v2 UI
uv run --project server python scripts/verify_r3_assets.py          # 资产库/图片/字体/SFX
uv run --project server python scripts/e2e_assets.py                # 资产库 UI
uv run --project server python scripts/verify_r3_templates.py       # 模板/场景/系列
uv run --project server python scripts/e2e_templates.py             # 模板 UI
uv run --project server python scripts/verify_p1_governance.py   # ★ 一条命令复核本轮全部 P1 门禁（8 步，自建自删）
uv run --project server python scripts/verify_r3_qa.py              # QA 修复建议（自建自删临时项目）
uv run --project server python scripts/e2e_qa.py                     # QA UI
```

> 注意：P0-3 已修，integration 测试现在启动独立临时 uvicorn/HOME/workspace，不再连真实 `:7860`、不再污染生产 DB。

### 0.3 当前下一步（按优先级）

1. **专家审查状态**：2026-11-03 全量审查结论 **Conditional Go**；**P0-1/P0-2/P0-3/P0-5/P0-4a/P0-4b 全部关闭**（P0-4b 的 40s 增量与 15s/40s 原帧 baseline 仍是"脚本可用但未实跑"，见 §0.6 边界）。复核分析：`docs/reviews/2026-11-03-expert-review-analysis.md`。
2. **P1 治理已完成 14 项**（02/03/04/05/06 部分/07/08/13/14/15/16/17/18/19 起步/22/23 第一批）。**剩余顺序建议**：
   ① P1-19 其余验收脚本迁到 `scripts/_acceptance.py`（`e2e_takes`、`e2e_assets`、`verify_r3_*`）→
   ② P1-12 非整数 fps（要升 `EXECUTOR_VERSION` 并重跑 golden）→
   ③ P1-09 多步写的失败注入/事务边界 →
   ④ P1-23 其余 42 个 `payload: dict` 端点 →
   ⑤ P1-10 ErrorBoundary / P1-11 时间轴虚拟化 + 100 场景实测 →
   ⑥ P1-06 收尾（级联删除/删除顺序，然后才敢开 `foreign_keys=ON`）→
   ⑦ P1-20/P1-21（CI 与 fresh-clone bootstrap）。
3. **FR-40/41 已满足准入**（P0 全绿 + P1-02/03/04/05 已做）；是否开工由老板定，不要顺手做 R4。
4. R3.0 v1 页面：`/timeline`、`/player`、`/takes`、`/audio`、`/assets`、`/templates`、`/qa` 已可用；`/timeline` 本轮加了 409 冲突保稿（P1-08）。
5. **不要开始 R4**（多规格矩阵/平台发布/批量/photo 引擎）。

### 0.4 不要做的事

- 不要重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑；46 节点/93 边不变。
- 不要新增 DAG 节点；R2.5 的审阅/音频/交付都在服务/页面层。
- 不要把新项目回退 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 不要改执行器行为却不升 `EXECUTOR_VERSION`（当前 **2.9.3**）。
- 不要用“页面能点”代替真实产物；完成申报必须附测试、产物路径/哈希、UI 截图/curl。
- 不要跑 `verify_r2_recovery.py` 时同时使用工作台（它会 kill -9 并重启 dev.sh）。
- 不要用 `TestClient(app)` 发**会写库**的请求——它连的是生产 `~/.filmflow/filmflow.db`；本轮就用这种方式误写过 rumor-39s（project 1）的 timeline 文档行，已删除复原（过程见 §0.7）。写类验证一律走 `scripts/_acceptance.py` 的临时项目或独立 `FILMFLOW_HOME`。
- 不要把 `payload: dict` 端点直接改成 Pydantic 模型就收工——`/projects/import` 与 `/drafts/{id}/materialize` 会把 dict **直接传给 `projects_create()` 函数**，签名一改就 500；改完必须跑 integration（已为此加过 `ProjectCreateIn` 显式构造）。
- 不要在资产还"被引用"时清空许可、也不要在 Run 之后直接交付：`E_ASSET_LICENSE`、`E_DELIVERY_GATE` 是本轮新加的硬门禁，绕过它等于恢复专家指出的洗白/混版本缺陷。

### 0.5 专家审查结论（2026-11-03；P0 Gate 已关闭，不再阻塞 FR-40/41）

**总体：Conditional Go。** 结论针对当时状态；**目前 P0 全部关闭**（下表保留原证据，便于你复核当时判断）。修复明细与复现见 §0.6。

| P0 | 问题 | 关键证据 | 工作量 |
|---|---|---|---|
| P0-1 | Next dev 绑全网卡 + 反代零鉴权 API | `lsof` 显示 `*:3000`；局域网 `:3000/api/projects` 返回 200；后端直连 :7860 拒绝；无 Host/Origin 中间件 | S |
| P0-2 | 8 类转场 7 类 preview/final 分叉 | `preview._transition_type` 缺英文枚举分支；遍历 `TRANSITIONS` 输出 `divergent 7/8` | S |
| P0-3 | integration 直连生产服务、污染 DB；skipif 静默 | 审计新增 project 228–240 共 13 行；`conftest.py` 只隔离 HOME；4 处 skipif 硬编码 | M |
| P0-5 | QA 修复与渲染管线脱节，`verified=true` 但成片未变 | `extend_scene` 只改 timeline，profile/Run 快照未变；`retry_run` 复用旧 snapshot | M |
| P0-4 | 出片核心链 pytest 零覆盖；证据灭失 | 无 Chrome/SSIM 测试；golden 在 480×270 缩略图；40s 增量无脚本；run 282 failed | P0-4a S–M / P0-4b L |

**当前状态（2026-11-03 20:00）**：P0-1/P0-2/P0-3/P0-5/P0-4a **全部完成并有回归证据**；P0-4b 已补齐脚本 + 5s 原帧 golden + 报告归档，**40s 增量与 15s/40s 原帧 baseline 仍未实跑**（磁盘/耗时考量，不是功能缺口）。Gate 达成，FR-40/41 可开工；本轮继续推进 P1 治理（状态表见 §0.6）。

**先修顺序（已执行完）**：P0-1（S）→ P0-2（S）+ P1-02/03/04（S×3）→ P0-3/P0-5（M）→ P0-4a → P0-4b → P1 治理批次。
**准入复核命令**（都要贴输出）：`verify_r2_profiles.py`（divergent/档位/SSIM 分窗口）、`verify_r2_incremental.py --project 5s`、连跑两次 `pytest server/tests -q` 后 `GET /api/projects` 计数不变、LAN/Origin/Host 探测（§0.7）、`verify_r3_qa.py`（QA 新语义 + 多步 LIFO 撤销）、`golden_run.py --project 5s --resolution original`。

**审计残留（未清理，需老板点头）**：DB **35 项目 / 29 目录 / 2.3GB**；project 228–245 由专家审计与 P0-4b 验证产生，246–248 与目录 `r2-profiles-249/250/251` 由本轮档位验收重跑产生（三者的 `out/frames`+`out/proxy` 已清，各留 ~16MB 证据）。清理顺序：先备份 DB、确认无运行 Job，再删记录与目录；**演示项目 202/174/188/211/215/216/223/227 不要动**。
**新门禁会影响老演示项目交付**：P1-13 的 timeline/Run 快照哈希比对，实测生产库中 run 237/253/254（project 188 r3-camera）与 run 266（project 211 r3-audio-v2）当前就处于漂移状态——直接对它们发起交付会被 `E_DELIVERY_GATE` 拦；要交付需按该 Run 重跑 F02/G07，或基于当前文档新建 Run。这是预期行为，不是回归。

**专家报告纠错**：报告称“风格库 76MB 失实 8 倍、mp4 0 字节”是口径误判；mp4 为稀疏文件，逻辑体积约 74.7MiB（mp4 59.8MiB），磁盘分配仅 9.3MiB。完整复核见 `docs/reviews/2026-11-03-expert-review-analysis.md` §2.4。

### 0.6 专家审查整改状态表（2026-11-03 20:00）

**P0（Gate，全部关闭）**

| 项 | 状态 | 落点 | 证据/复现 |
|---|---|---|---|
| P0-1 网络边界 | ✅ | `web/package.json` dev=`next dev -H 127.0.0.1 -p 3000`；[server/app/security.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/security.py) `LocalOriginMiddleware`；[server/app/main.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/main.py) `TrustedHostMiddleware` | LAN `:3000`/`:7860` 均 000；错误 Host 400；跨源写 403 `E_ORIGIN_DENIED`；本机 UI 200。单测 `server/tests/unit/test_security_middleware.py` 3 项 |
| P0-2 转场双实现 | ✅ | [server/app/engine/scene/transitions.py:12](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/engine/scene/transitions.py#L12) `transition_type`，preview/pipeline/schema/timeline_ops 共用 | `divergent 0/8`；`server/tests/unit/test_transitions.py` 17 项 |
| P0-3 测试隔离 | ✅ | `server/tests/conftest.py`（每次 pytest 独立临时 HOME + 清理）、`server/tests/integration/conftest.py`（独立 uvicorn/HOME/workspace、`isolated_api` fixture） | 连跑两次 `pytest server/tests -q` → `GET /api/projects` 恒 35；无 skipif 硬编码；缺风格库/Chrome/ffmpeg 默认失败（`--allow-missing-env` 才跳过） |
| P0-4a 真实出片冒烟 | ✅ | `server/tests/integration/test_render_smoke.py` | 隔离服务里建 1s/12fps 项目 → Chrome 截帧 → ffmpeg 编码 → ffprobe 960×540/12fps/12 帧 → 与静帧 SSIM ≥0.95 |
| P0-4b 增量/黄金/归档 | 🟡 部分 | `scripts/verify_r2_incremental.py --project 5s\|15s\|40s`、`scripts/golden_run.py --resolution thumb\|original\|both`、`docs/reports/**` | 已实跑 5s：增量 66/120=55%、前 54 帧不变、49.8s<53.8s（`docs/reports/r2-incremental/5s-run303.json`）；5s 原帧 6 帧 SSIM=1.0（`docs/reports/golden/5s-original-run306.json`）。**40s 增量已实跑 PASS（run 311：rendered 93/960=9.69%、reused 867、报告 docs/reports/r2-incremental/40s-run311.json）；15s/40s 原帧 baseline 未实跑** |
| P0-5 QA↔渲染 | ✅ | [server/app/services/qa.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/services/qa.py) | `extend_scene` 同步 timeline+profile 且失败补偿回滚；`verified=null/documentVerified=true/requiresRerun=true`；`retry_run` fork 新 Run；报告 `pendingRerun`。`verify_r3_qa.py` 实跑 |

**P1（治理，23 项）**

| 项 | 状态 | 落点 | 证据/复现 |
|---|---|---|---|
| P1-01 CSRF/Host/Origin | ✅（并入 P0-1） | 同上 | 同上；未加 token（本机工作台，老板可另行决定） |
| P1-02/03/04 缓存键 | ✅ | [server/app/engine/runengine.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/engine/runengine.py) `_library_fingerprint/_external_input_hashes/_project_input_hashes/_engine_pack_sha` | `server/tests/unit/test_cache_inputs.py` 6 项；`EXECUTOR_VERSION=2.9.3` 使旧缓存自动失效 |
| P1-05 A05 自动批准 | ✅ | `runengine._auto_approve_a05` 需 `imported` 或 `style_decision` | `test_p1_foundations.py`（`session=None` 早退即证明守卫在前） |
| P1-06 SQLite | ✅ 收尾 | [server/app/db.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/db.py) WAL + NORMAL + **`foreign_keys=ON`**；[server/app/services/project_cleanup.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/services/project_cleanup.py) 级联删除（project/run/workflow/doc 四类关联面）+ `DELETE /projects/{id}?confirm=true`（演示保护名单） | FK 开启钓出 qa.undo 删 profile 行残留 docrevision 的真 bug（已修）；`_acceptance.destroy` 与测试清理全改走级联服务；213 tests 全绿 |
| P1-07 迁移框架 | ✅ | [server/app/db.py:73](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/db.py#L73) `MIGRATIONS` + `:80` `apply_migrations` | `server/tests/unit/test_migrations.py` 3 项；生产库连跑两次 `init_db()` 无变化（登记仍 [1,2,3]） |
| P1-08 时间轴 409 保稿 | ✅ | [web/src/app/timeline/page.tsx](file:///Users/litianyu/cc-projects/ai-v/filmflow/web/src/app/timeline/page.tsx)（`conflict` 态、`data-testid="timeline-conflict"`） | 409 时保留草稿 + 「只看服务端 / 保留本地并重试（对新版本重放）」，冲突期间暂停自动保存；`pnpm --dir web exec tsc --noEmit` 干净 |
| P1-09 多步写事务 | ✅ 四路故障注入 | [server/tests/unit/test_multi_step_writes.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/tests/unit/test_multi_step_writes.py)：branch Run 失败→文档倒序回滚（base 用当前版本）；replace 中途失败→已改项目回滚；模板 materialize 失败→delete_project 清半成品；qa extend profile 失败→timeline 补偿（锁定） |
| P1-10 ErrorBoundary | ⛔ 未做 | `web/src/app/**` 无 `error.tsx` | 需加全局/页面级 boundary + 失败可见 |
| P1-11 时间轴性能 | ⛔ 未做 | `web/src/app/timeline/page.tsx` 全量 `.map()` | 「100 场景 60fps」是**未实测的声明**；先测再决定虚拟化 |
| P1-12 非整数 fps | ✅ | [server/app/engine/fpscalc.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/engine/fpscalc.py) 唯一口径（norm_fps/frames_for/frame_at/fps_rational）；preview/render_profiles/compiler/pipeline/routes/templates/manifest 全接线 | `test_fps_math.py` 12 项；`EXECUTOR_VERSION=2.10.0`；golden 5s 原帧 run 312 SSIM 1.0；档位验收重跑数字与 run 309 一致（0.998663/0.952097）；final 门放行 NTSC 23.976（<23.9 才拦）|
| P1-13 交付文档一致性 | ✅ | [server/app/services/delivery.py:272](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/services/delivery.py#L272) `_ensure_run_documents_match` | 2 项单测 + 生产库 22 个真实快照实测：18 放行 / 4 真实漂移拦截，与哈希比对零分歧、无误拦；run 198 合成漂移确认抛 `E_DELIVERY_GATE` |
| P1-14 档位验收脚本 | ✅ | `scripts/verify_r2_profiles.py` | run 309 / project 248 全绿：D02 混排不崩；**SSIM 改为分窗口**：稳定段最差 0.998663（≥0.98）、切点/入场 0.5s 窗口最差 0.952097（≥0.90）。旧「0.9987」口径已在 §2.4 修正 |
| P1-15 资产引用面 | ✅ | [server/app/services/assets.py:298](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/services/assets.py#L298) `walk_refs`、`:342` `scan_usages` | 覆盖 timeline + 其它项目文档 + `Template.content_json` + Run 快照（`include_history`）；同容器 `assetShas` 派生索引不重复计数；HTTP 实测「仅剩模板引用 → `DELETE /assets` 409 `source=template`」。4 项新单测（`test_assets.py`） |
| P1-16 许可强制 | ✅ | `assets.py:79` `license_gap`、`:95` `asset_license_ok`、`import_asset`、`update_asset` | 全资产种类入库需 `source`+`type`、`expires` 须未过期 ISO；**被引用中不许清空/削弱**；HTTP 9 项实测（§0.6.1） |
| P1-17 QA 撤销链 | ✅ | `qa.py:510` `_require_undo_head`、`:527` `undo_fix`、`:355` `_timeline_before` | 修复记录 `afterHash/afterProfileHash/profileExisted`；撤销=链顶判定，可逐级 LIFO 回退，抢跑报错点名应先撤项；修掉 `before`/`after` 引用别名（撤销曾等价于空操作）。`test_qa.py` 新增 2 项（多步 LIFO / 无 profile 文档行） |
| P1-18 许可洗白/预置授权 | ✅ | `qa.py` `_node_suggestions`、`web/src/app/qa/page.tsx` | `fill_license` 改 `kind=confirm`、params 不再含 `authorized`；UI 去掉"自制/CC0"预填并要求输入 YES 显式确认；`apply_fix` 允许 `auto|confirm` 两类 |
| P1-19 验收脚本硬编码 | 🟡 起步 | `scripts/_acceptance.py:32` `destroy`、`:60` `throwaway` | `verify_r3_qa.py` 已完全自包含（不再改写演示 227），6 步全绿且跑完 DB 计数不变。**仍硬编码**：`e2e_takes.py` PID 188/237/254、`e2e_assets.py` PID 211、`verify_r3_assets/templates/camera/takes/audio_v2/rumor_regression` 等 |
| P1-20 SDLC/git 现实 | 🟡 部分 | 本轮提交已按 `fix/feat/test/docs(p1-xx)` 细分 | 仍无 CI、无验收日志自动归档；`docs/reports/**` 只覆盖增量与黄金 |
| P1-21 fresh clone | ⛔ 未验证 | — | 依赖仓库外风格库/rumor-39s/系统 Chrome/ffmpeg/DB 演示项目；需 bootstrap 脚本 + 干净机器实测 |
| P1-22 env 覆盖崩溃 | ✅ | `server/app/config.py` `workspace_roots_raw`（`AliasChoices` + 解析函数） | 单路径/逗号/JSON 三种写法都可；`test_p1_foundations.py` 覆盖；`.env.example` 已说明 |
| P1-23 请求模型 | 🟡 第一批 | [server/app/api/schemas.py](file:///Users/litianyu/cc-projects/ai-v/filmflow/server/app/api/schemas.py) | 9 个高风险写端点已模型化（`POST /projects`、文档 `PUT/restore`、`timeline/ops`、资产 `POST/PATCH/replace`、QA `fix/undo`），非法输入统一 422；`test_request_models.py` 7 项。**还剩 42 个 `payload: dict`** |

**本轮 9 个提交（`git log --oneline 68627d1..HEAD`，全部已推 public）**
`fc721bd` P1-13+P1-08 · `70f1361` P1-15 · `4a8c7cd` P1-16/18 · `6ff2ce5` P1-17 · `7e5b151` P1-17 补充+P1-19 起步 · `30dd4ce` P1-07 · `3b0203a` P1-23 · `d47cac5` P1-14 · `9bc0f95` docs 口径。更早：`bbb7ebf` P0-1/P0-2/P1-02/03/04 · `34ab6a4` P0-3/P0-5/P0-4a · `a6a28d0` P0-4b。

### 0.6.1 破坏性语义（接手必读，别按旧直觉写代码）

**判官复核后的修复批次（2026-11-04 上午，见 `docs/process/judge-review-2026-11-04.md`）**

9. **项目删除面（B1 已硬化）**：`server/app/services/project_cleanup.py`
   - `dir_policy()`：项目根必须是白名单条目的**真子目录**（等于白名单根一律拒），且**不能是含 `.git` 的目录**；`POST /projects` 与 `/projects/import` 登记时就拒（`_require_creatable_project_root`），所以"把仓库根注册成项目再删"这条路被掐死。
   - `plan_delete()` 先出完整计划（目录可否删、是否保护名单、有无在飞作业），**全部校验通过后才动数据**；库行删除走单事务，失败回滚，不再出现"库没了目录还在"。
   - 保护名单 `is_protected()`：`rumor*`（回归基线，含 project 1 `rumor-39s`、115 `rumor-clean-20261102`）+ 全部演示项目名；删除必须回显 `confirm_name=<项目名>`，布尔参数不足以自证。
   - 在飞判定按**心跳/started_at 120s 窗口**（`_job_is_live`），不看被启动恢复反复 bump 的 `updated_at`，也不单独看 `Run.status=="running"`（崩溃残留态）；确需强删用 `force=true`，只越过"在飞作业"这一条，并写进审计 `forcedInflight`。
   - 路由：`DELETE /projects/{id}?confirm=true[&remove_dir=&confirm_name=&force=]`；`confirm=false` 只回计划。测试：`server/tests/integration/test_project_delete_api.py`（5 项路由级）+ `test_p1_foundations.py`（目录策略矩阵 / 在飞拒绝且不留半死 / force 审计 / 白名单根被拒时库行仍在）。

### 0.6.1 本轮新增的破坏性语义（历史批次，接手必读）

1. **资产入库必须带许可**：`POST /assets` 缺 `license.source`/`license.type` → 400 `E_ASSET_LICENSE`；`expires` 非 ISO 或已过期同样拒。旧脚本/UI 只给字体填许可的路径已全部改为通用（`scripts/e2e_assets.py` 因此把许可填写移到上传之前）。
2. **许可只可补强不可削弱**：资产被任何 timeline/文档/模板/Run 快照引用时，`PATCH /assets/{id}` 送空 `source`/`type` → 400「资产正被引用，不能清空/削弱许可」。未被引用时可自由改。
3. **`rights.json` 换成 `filmflow.rights/2`**：内容由 Run 快照的真实资产引用生成（`sha256/kind/scope/name/source/type/expires`），没有字体资产时才附 `fallbackFont` 一条标注渲染器兜底；任何资产许可缺口 → `E_LICENSE_MISSING` 拒交付。**不要再断言旧的 `rights.font` 字段**（仓库内无消费者，脚本只检查文件存在）。
4. **交付前文档一致性门禁**：`run_delivery` 对非导入项目比较"当前 timeline 内容哈希 vs 所选 Run 快照哈希"，不一致 → `E_DELIVERY_GATE`。现网 run 237/253/254（project 188）、run 266（project 211）已处于漂移态，交付会被拦。
5. **QA 修复/撤销语义**：`verified` 对文档级修复为 `null`（只有 `documentVerified=true` + `requiresRerun=true`）；撤销链按 `afterHash` 判定链顶，**多步必须倒序**，且撤销会删除"修复前不存在"的 profile 文档行。`fill_license` 建议 `kind=confirm` 且必须显式送 `authorized=true`。
6. **写端点 422**：请求体类型错误不再进服务层；`/projects/import`、`/drafts/{id}/materialize` 内部**直接调用** `projects_create(...)`，必须传 `ProjectCreateIn(...)` 实例而不是 dict。
7. **`apply_fix` 允许的建议 kind 为 `auto|confirm`**（`qa.py:455`），前端把 `confirm` 也渲染成按钮（[web/src/app/qa/page.tsx:116](file:///Users/litianyu/cc-projects/ai-v/filmflow/web/src/app/qa/page.tsx#L116)）。
8. **`payload.get("x", default)` 的隐式默认值不再是可靠行为**：模型化端点的默认值以 `schemas.py` 字段声明为准，改动前先核对服务层原有默认，避免模型把 None 塞进多态 payload。

### 0.6.2 明确没做/没跑（不要当成已完成）

- ~~40s 增量渲染实跑~~ ✅ 已跑（run 311，9.69%）；15s/40s 原帧 golden baseline 生成（各约 4.3GB / 数十分钟）。
- P1-09 失败注入与事务边界、P1-10 ErrorBoundary、P1-11 时间轴虚拟化与 100 场景实测、P1-12 非整数 fps、P1-21 干净机器 fresh-clone 走通、CI。
- P1-19 其余验收脚本（列表见上表）与 P1-23 其余 42 端点。
- `foreign_keys=ON`；DB 审计残留清理（需老板点头）。
- P2 共 35 条、P3 共 26 条（索引见 `docs/reviews/2026-11-03-expert-review-analysis.md` §2.3）——本轮**一条都没系统性清**。

### 0.6.3 一条命令复核本轮治理（专家推荐先跑这个）

```bash
uv run --project server python scripts/verify_p1_governance.py
```

`scripts/verify_p1_governance.py` 会对着运行中的服务连查 8 项并**自建自删临时项目/模板/资产**
（不改演示数据，跑完 `GET /api/projects` 计数不变）：

1. 安全边界：错误 Host 400、跨源写 403、本机 200（P0-1/P1-01）。
2. 转场单实现：`preview._transition_type is transitions.transition_type`，8 类中英文标签同源（P0-2）。
3. 缓存键：`EXECUTOR_VERSION=2.9.3`；A01/A03/F01/G01 外部指纹入键、G02/G04 项目输入入键、C01 引擎包入键（P1-02/03/04）。
4. 许可门禁 + 引用面：无/过期许可入库 400；被引用中清空许可 400；仅剩模板引用时删除 409 `source=template`（P1-16/P1-18/P1-15）。
5. 交付一致性 + rights：与所选 Run 快照一致才放行；`_asset_rights` 逐项输出真实资产许可（P1-13/P1-16）。
6. 漂移拦截：合成 timeline 漂移 → `E_DELIVERY_GATE`（P1-13）。
7. QA 多步撤销：抢跑被拒且点名应先撤的 fixId；倒序两级撤回到原状（P1-17）。
8. 迁移登记 + 422：`apply_migrations` 对已登记版本返回空；非法请求体 422 不进服务层（P1-07/P1-23）。

实测输出（2026-11-03 20:00）：8 项全 ✓ + `PASS: P1 治理复核全部通过`；跑前需 `./dev.sh`。

### 0.7 运维、复现与本轮踩过的坑

- **dev 服务不是 `--reload`**：改 Python 代码后必须重启才生效。可靠配方（`pgrep -f 'uv run uvicorn'` 只杀包装进程，真 python 子进程仍在监听）：
  ```bash
  pkill -f 'dev.sh'; lsof -nP -iTCP:7860 -iTCP:3000 -sTCP:LISTEN -t | xargs kill
  sleep 3; nohup ./dev.sh > /tmp/ff-dev.log 2>&1 & sleep 13
  curl -s http://127.0.0.1:7860/api/health   # {"ok":true,...}
  ```
  跑验收脚本前先确认监听进程加载的是当前代码（`/tmp/ff-dev.log` 里有 `Application startup complete`）。
- **`TestClient(app)` 写的是生产库**：本轮一次手工探针 `POST /api/projects/1/timeline/ops`（rumor-39s）真的创建了 `projectdoc` 行（v1，S01 文案被写成"新句子。"）。处理：删该行 + 其 `docrevision`，再清掉指向已删文档的孤儿修订，复查 `GET /projects/1/docs/timeline` 回到 `version=0 / imported=true / 5 scenes / S01 text=''`。教训：**非法输入的断言用 `TestClient`（会被 422 挡在 handler 之前，`test_request_models.py` 就是这么做），任何会写的探针一律用独立 `FILMFLOW_HOME` 或 `scripts/_acceptance.py`。**
- **验收脚手架**：`scripts/_acceptance.py` 的 `throwaway(client, name, copy_text)` 会在 `~/cc-projects/ai-v/filmflow-projects/.acceptance/` 下建项目、退出时按 `project_id/run_id` 清所有相关表 + 目录（**没有 `DELETE /projects/{id}` 端点**，所以清理必须走 DB）。新项目只写 `card/copy.txt`，`script/profile/timeline` 文档由服务端派生。
- **Chrome/ffmpeg 独占**：验收脚本与 pytest integration 都会起真实 Chrome；不要并行跑两个渲染类任务（`chrome_queue_limit=1` 只在单进程内串行，跨进程不互斥）。
- **大文件目录清理**：验证项目跑完后删 `out/frames`、`out/proxy`（各约 500MB/5s 项目），保留 `film/stills/artifacts/交付包`。本轮删掉 3 个 `r2-profiles-*` 的 frames/proxy，`filmflow-projects` 由 ~3.9GB 降到 **2.3GB**。
- **QA 溢出样本要"刚刚溢出"**：`verify_r3_qa.py` 现在按 0.19s/字逐字加长到刚好超过读时（+0.5s 才修得好），不要硬编码长文案，否则 `documentVerified` 变 false。
- **内容哈希要算在保存后的文档上**：`qa.py` 的 `afterHash` 取 `saved.content_json` 而非保存前的 dict（`save_doc` 可能规范化），否则撤销链会误判。
- **深拷贝别名**：`doc_payload()["content"]` 返回的是 SQLAlchemy 对象的同一 dict，任何"先记录 before、再原地改"的路径必须 `deepcopy`，否则 before==after。
- **Pydantic 布尔宽松**：`{"archived":"yes"}` 会被 v2 合法转成 `True`，测试非法输入要用真正非法的值（如 `"不是布尔"`）。
- **安全边界复核命令**：
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" -H "Host: attacker.example.com" http://127.0.0.1:7860/api/projects  # 400
  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Origin: http://evil.example" http://127.0.0.1:7860/api/drafts  # 403
  ipconfig getifaddr en0   # 局域网 IP:3000/:7860 应连不上
  ```

---

## 1. 当前状态

### 1.1 提交与标签

| 项 | 值 |
|---|---|
| R3.0 当前代码 | `900076b`（tag `r3.0-assets`；前序 `r3.0-audio` → `7a0ee2c`） |
| R2.5 FR-26 tag | `r2_5-review` → `a37570d` |
| R2.5 FR-27 tag | `r2_5-audio` → `cd7312f` |
| R2.5 FR-28 tag | `r2_5-delivery` → `9c4ac00` |
| R2.5 FR-31 tag | `r2_5-onboarding` → `b7591bd` |
| R3.0 v1 tag | `r3.0-creation` → `7ecf84a` |
| R3.0 FR-38 tag | `r3.0-takes` → `1d2fcf6` |
| R3.0 FR-35 tag | `r3.0-audio` → `7a0ee2c` |
| R3.0 FR-36 tag | `r3.0-assets` → `900076b` |
| R3.0 FR-37 tag | `r3.0-templates` → `f887424` |
| R3.5 FR-39 tag | `r3.5-qa` → `3bb81a0` |
| R2.0 起始 tag | `r2-edge-fix` → `4f9e381` |
| R2.0 Scene DSL | `r2-scene-dsl` → `53e6462` |
| R2.0 增量 | `r2-incremental` → `07b5237` |
| R2.0 预览 | `r2-preview` → `25ff0d9` |
| R2.0 档位 | `r2-profiles` → `426aa20` |
| R2.0 Job/恢复 | `r2-jobs` → `f5d5de1` |
| R2.0 黄金 | `r2-golden` → `371ea4b` |
| 测试 | **189 passed**（unit 169 / integration 13 / BDD 7）；integration 已隔离 |
| 本轮 P1 治理 | master `68627d1..9bc0f95`（9 提交，已推 `leechunwoo0815/filmflow`）；**未打新 tag** |
| 公开仓库 | `git@github.com:leechunwoo0815/filmflow`（master 已同步；公钥已配） |
| 专家原始报告 | 仅本地 `~/.filmflow/reviews/2026-11-03-expert-review.raw.md`（692 行 / 120KB，sha256 前缀 `03d5dbcb87ad8352af3d4aa6`）；含主机路径与攻击面细节，**不进公开仓库**；仓库侧只放 `docs/reviews/2026-11-03-expert-review-analysis.md`（344 行脱敏复核） |
| EXECUTOR_VERSION | **2.9.3**（P0-2 转场统一；P1-02/03/04 缓存键） |
| UI E2E | 8 场景全绿（约 16s）；FR-31/FR-33/FR-35/FR-36/FR-37/FR-39 冒烟另 11 组 |

### 1.2 R2.0（已验收，8 FR）

| FR | 状态 | 关键实现 |
|---|---|---|
| FR-20 参数化渲染链 | DONE | docs → snapshot → base/motion program → still_spec/film_spec |
| FR-21 场景组件库 v1 | DONE | 12 组件 + fixture；视觉回归在 golden |
| FR-22 场景级增量 | DONE | manifest + SceneState；40s 改 S03 只渲 93/960=9.69% |
| FR-23 PreviewService | DONE | CDP 附加 F02、still/segment/film、水印、缓存、latest-wins |
| FR-24 draft/review/final | DONE | render.profile.json、D02 双静帧、E05 720p、F02 only-final、E_FINAL_REQUIRED |
| FR-25 文档/快照 | DONE | ProjectDoc/DocRevision、409、versions/diff/restore、Run 快照只读 |
| FR-29 Job/恢复 | DONE | Job 表、租约/心跳、retry_wait、启动恢复、队列 API、孤儿清理 |
| FR-30 黄金项目 | DONE | 5s/15s/40s fixture+baseline；SSIM 1.0；干净 rumor 46/46 |

### 1.3 R2.5（能审能交）

| FR | 状态 | 证据 |
|---|---|---|
| FR-26 全场景静帧审阅 | **DONE** | D01 长场景 6 帧、D02 contact sheet、D03 逐场门禁、D04 review_diff、`/review` |
| FR-27 音频工作台 v1 | **DONE** | Take/录音、waveform 49–51ms、手动对齐、许可、sidechain、Stems、G06 TP/同步 |
| FR-28 交付 v1 | **DONE（5s）** | 9 文件、16:9+9:16、SRT、双封面、manifest/qc/rights/zip；5s 26.1s |
| FR-31 新手引导 | [DONE] | 3 模板+音频占位、只读示例/克隆、向导用户标题 3 候选预演、Studio 5 步引导、`/help`；`verify_r2_5_onboarding.py` + `e2e_onboarding.py`。 |

### 1.4 环境与验收项目

- macOS · Python 3.13 · uv · Node ≥22 · 系统 Chrome · ffmpeg 9.x。
- 真实 DB：`~/.filmflow/filmflow.db`；测试 DB：`/tmp/filmflow-test-home/filmflow.db`。
- 风格库：`cat vendor/style-library.path`（逻辑约 75MiB；mp4 稀疏文件，磁盘分配约 9.3MiB；外置，不入 git）。
- 40s 黄金/增量：`filmflow-projects/golden-40s-134`（project 119；run 154→155）。
- R2.5 审阅：同 project 119；run 163→164（D05 后 cancel）。
- R2.5 音频最终：`filmflow-projects/r2_5-audio-160`（project 151 / run 198）。
- R2.5 交付：`filmflow-projects/r2_5-delivery-153`（project 142 / run 186；
  `out/deliveries/186/`）。
- 干净 rumor：`filmflow-projects/rumor-clean-20261102`（project 115 / **run 222**；
  `out/film/master.mp4` 39.5s / 70,542,684B；2.6.6 复跑 **46/46**，90.6s）。
- FR-31 验收：project 155 / run 202（模板 15s draft），project 156 / run 203（示例克隆）。
- 40s 交付：`filmflow-projects/r2_5-delivery40-185`（project 174 / **run 223**，2.6.6 一次通过）；
  旧证据 `r2_5-delivery40-177`（project 166 / run 213，G07 parser 修复前 retry）。

> **项目 ID 口径（2026-11-03 清理后）**：§1.4/§3.4 中的 `golden-40s-134`、`r2_5-delivery-153`、
> project 155/156 等目录已删除，ID 仅作历史证据；当前可打开的项目以 **§7.4** 为准，
> 所有验收脚本可重新生成等价项目。

---

## 2. 可复核证据（R2.0）

### 2.1 5s 参数化出片

`verify_r2_incremental.py --project 5s`：run1 120 帧、`out/film/intermediate.mp4` 1920×1080/24/5.000s；
D02 用户文案；F05 Y-SSIM 通过。

### 2.2 40s 增量

```
manifest2 rendered=93 reused=867 / 960 (9.69%)
full F02 wall=108.48s；incremental F02 wall=14.15s (13.05%)
```

- 改 S03 只脏 S03 + 离场转场帧；前两场帧哈希不变。
- 40s golden：`fixtures/golden/40s`，6 帧 SSIM 1.0 / pHash 0。

### 2.3 预览（FR-23）

- F02 运行中 attached p50 **1.50s** / p95 **1.92s**；5s 片段 **13.2s**；缓存 **5ms**。
- 20 并发拖动只留最后 1 个（1×200 + 19×429）。
- 不写 `out/frames`、不产生 Artifact/Approval；PREVIEW 水印。
- 单帧默认 D01 base；`motion=true` 用 E03 motion program 做同刻对比（SSIM 0.9987）。

### 2.4 档位（FR-24）

- D02 review 1280×720 + draft 960×540；E05 review 720p/24；F02 only-final。
- F05/G07 `ensure_final_ready`：manifest 缺失/非 final/Run 不匹配 → `E_FINAL_REQUIRED`。
- 切档不重跑已完成 final；40s draft 100.3s / review 245.6s。
- **2026-11-03 重跑档位验收（P1-14，run 309 / project 248，`r2-profiles-251`）**：D02 contact sheet 混排不再崩（draft 960×540 + review 1280×720 + 无 profile 元数据的 1920×1080 归为 other）；draft 5s 13.7s / review 32.0s；E05 720p/24；F02 manifest profile=final。**draft vs final 逐点 SSIM（8 点，含切点/入场窗口）**：稳定段最差 **0.998663**（要求 ≥0.98），切点后 0.5s 入场窗口最差 **0.952097**（t=2.55，切点 2.24；要求 ≥0.90）。
  **证据修正**：旧口径「draft vs final SSIM 0.9987」只在稳定段取样，掩盖了 draft 12fps 时序量化在切点/入场动画窗口的可见差异；现按窗口分别设阈值并打印分类，验收脚本 `verify_r2_profiles.py` 已固化该口径。

### 2.5 Job/恢复（FR-29）

- F02 中 kill -9 API：**22.3s** 恢复；frames=120；单 Job attempts=1；无 Chrome 残留。
- 单 API worker 假设；预览 Job 重启标 `E_JOB_INTERRUPTED`，不自动重试。

### 2.6 黄金与干净 rumor（FR-30）

- 5s/15s/40s golden：6 帧 SSIM **1.000000** / pHash **0**。
- 干净 rumor（run 222，2.6.6）：**46/46 succeeded**、0 failed/skipped、90.6s；
  master **39.500s / 70,542,684B** H.264+AAC；G07 QC imported 路径只查音轨。
  历史 run 194 为 2.6.4 证据。
- 本机无 whisper，G02 用 manual alignment（source=manual，ADR D7）。

---

## 3. 可复核证据（R2.5）

### 3.1 FR-26 审阅

`verify_r2_5_review.py`（project 119 / run 163→164）：

```
D03 blocked before viewing: 未查看场景 S01..S05
D05 review scenes: S01=6 S02=1 S03=1 S04=6 S05=6
contact sheet 1920×1080 / scenes S01..S05
runB diff changed: ['S03']，其余 unchanged
PASS: R2.5 FR-26 静帧审阅验收通过
```

- `/review` Playwright：22 张图、contact sheet、全场景已看、100/200%、A/B、键盘、批准 D03/D05。
- 修复：B06 同文档缓存命中不写 Run 快照 task；`_task_path` 回退只读 `card/task.json`。

### 3.2 FR-27 音频

`verify_r2_5_audio.py`（project 151 / run 198）：

```
waveform 1200 peaks in 49ms
G01/G02/G05/G06/G07 = succeeded
audio metrics lufs=-16.0 true_peak=-10.5 sync_dev_s=0.0 sync_verified=True
stem voice/music/sfx = 5.0 / 5.0 / 5.0s
master 5.000s + audio
PASS: R2.5 FR-27 音频工作台验收通过
```

- `/audio` Playwright：Take/波形/对齐/许可 UI 正常。
- 关键修复：G04 解码改临时文件（stdout 64KB 死锁）；G07 批准后回 idle 执行 package；
  G05 `alimiter=limit=0.7:level=false`（否则自动拉响度到 −13.7LUFS/+0.1dBTP）。

### 3.3 FR-28 交付（5s + 40s）

**5s 回归**（project 173 / run 221，2026-11-02）：

```
G chain G05/G06/G07 = succeeded
delivery job succeeded wall 26.2s
QC {master16/9,duration,audio,lufs,truePeak,captions,covers}=true
master16 1920×1080/24 + audio；master9 1080×1920/24 + audio，均 5.000s
PASS: R2.5 FR-28 交付 v1 验收通过
```

**40s 实测**（project 174 / run 223 / `filmflow-projects/r2_5-delivery40-185`，2.6.6 全新一次通过）：

```
run wall 305.4s  E05/F02/F04/G05/G06/G07 = succeeded
G07 qc {duration:40.0,1920x1080,24fps,audio:true,lufs:-15.9,truePeak:-10.5}
delivery job succeeded wall 190.0s
qc {master16/9,duration,audio,lufs,truePeak,captions,covers}=true
master16 1920×1080/24 + audio 40.000s 7,588,145B
master9  1080×1920/24 + audio 40.000s 6,616,460B
captions 5 cues / maxLineChars 16 / maxCharsPerSec 2.31 / source=manual
covers 1920×1080 + 1080×1920；9 文件 + zip
g07Master sha256=089419501e35acbb...（delivery manifest 可反查）
PASS: R2.5 FR-28 40s 交付验收通过（run 305.4s / delivery 190.0s）
```

- **审批口径**：run 223 的 delivery manifest 记录 **7 条 run-local 审批**（A05/B08/D03/D05/E07/F06/G07）；
  G03 因内容哈希与 run 213 相同走了既有 `inherit` 策略，没有本 Run 的 Approval 行。
  DAG 实际是 **8 个人工门**（8+8 门），PRD 写的「9 条审批」与当前门数不一致；没有伪造第 9 条。
  需要严格逐 Run 审计时，应在 R3 把 inherit 范围收窄到同 workflow 并把继承审批写进 manifest。
- 包：`out/deliveries/<runId>/`：两个 master、`captions.zh.srt`、`cover_16x9.jpg`、`cover_9x16.jpg`、
  `manifest.json`、`qc.json`、`rights.json`、`FilmFlow-delivery.zip`。
- 9:16 由 Scene DSL 重排（不裁切 16:9）；封面取中间场景 reveal 完成后的帧。
- G07 master QC：`E_QC_LUFS/TRUE_PEAK/DURATION/RESOLUTION/FPS/AUDIO`；LUFS −20 由单测
  `test_master_qc.py` 证明阻断并给「重新混音到 −16」建议。
- 复现：`verify_r2_5_delivery.py`（5s）与 `verify_r2_5_delivery_40s.py`
  （全链或 `--project 174 --run 223 --root ...` 复用 G07 产物）。

### 3.4 FR-31 新手引导（DONE）

- 首页「做第一条片」3 模板（口播 15s / 观点 30s / 产品 40s）→ `POST /projects/from-template`。
- 模板 materialize 写 `card/audio.placeholder.json`（kind/duration/source）；`GET /projects/:id/audio`
  返回 `placeholder`；上传/录音后自动清除，不生成假音频。
- `fixtures/examples/catalog.json` 只读示例（voice15/product40）；`GET /examples` +
  `POST /examples/:id/clone` 复制为独立项目，路径全在工作区。
- `GET /wizard/titles?copy=` 本地切 3 个候选标题；向导第 3 步用所选风格预览图叠加用户标题，
  可切候选；`brief.title` 写入 materialize（项目名不再固定「向导草稿」）。
- Studio 首次进入显示 5 步引导（场景列表/单帧/改一句/diff/draft），可跳过、header「引导」重看、
  localStorage 记忆，不阻塞画布。
- 验收（2026-11-02）：
  - `verify_r2_5_onboarding.py`：project 155 / run 202；`audio.placeholder.json` 15s；
    15s draft 预览 960×540/12.0/15.0s，墙钟 **38.2s**；上传后占位清除；示例 project 156/run 203。
  - `e2e_onboarding.py`：首页 3 模板 + 2 只读示例；Studio 引导可跳过/重看/刷新不反弹；
    向导标题预演使用用户文案（`很多工作不是难，是重复`），3 候选可切换。
  - 修复 StylePicker 少 `min-h-0` 导致 640px 网格溢出压住标题预演的真实 UI bug。

### 3.5 R3.0 创作闭环 v1（FR-32/33/34/35/38）

- **FR-32 时间轴**：`/timeline`；V/T/C/A1/A2/A3/M 轨道；拖块排序、拖右边缘改时长 + ripple；
  分割/合并/复制；文本框自动保存；相机/转场 inspector；250ms 防抖静帧预览；撤销/重做 50；
  读时校验 409 + force；JKL/逐帧/入出点/缩放/吸附。
- **FR-33 审片**：`/player`；F04/master 视频；矩形/箭头/画笔/文字批注锚定 frame+sceneId；
  列表跳帧；resolve/回复/指派；场景与整片决议；JSON/CSV 导出导入；审片包 zip。
- **FR-34 相机/转场**：timeline scene `camera_keyframes`/`camera_anchor` + `text` override；
  E02/PreviewService 同一 camera；renderer 支持 rotate；7 预设；8 类转场 id；E04 接受 id。
- **FR-38 Take 对比**：`/takes`；`card/takes.json` 名称/评分/备注/current/hidden；
  A/B 视频同步（≤1 帧）、difference 差异叠加；场景采纳只改目标场景；promote 写 `out/CURRENT.json`；
  branch 复制 Run 快照 docs 并写 `parent_run_id`；当前 Take 删除 409。
- **FR-35 音频 v2**：`/audio`；每场景多 Take/A-B；`scenePrimary` + G01 adelay/amix 拼接；
  processed WAV（highpass/afftdn/deesser/EQ/silenceremove/loudnorm）、onset/拍点、
  −14/−16/−18 响度目标、Stems 增益；G05/G06/G07 共用 targetLufs。
- **验收（2026-11-02，EXECUTOR_VERSION 2.8.0）**：
  - `verify_r3.py`（project 201 / run 251）：S03 +2s ripple 40→42s/1008 帧；split/merge；
    读时 409 + force；相机 3 帧 motion preview 1.63s；30 文档版本恢复初始；
    10 条批注 export→clear→import；审片包 6.8MB / review.mp4 40.0s。
  - `verify_r3_camera.py`（project 208 / run 261，2.7.2）：D01 文本 override、E03 相机 3 帧、
    E04 4 类转场；同刻 preview vs final **SSIM 0.989483**。
  - `e2e_r3.py`（project 189 / run 238）：拖 S01 +2s、改字、相机预设、撤销、刷新恢复、
    批注跳帧 4.0s→4.000s、播放器新增批注。
  - `verify_r3_takes.py`（project 188，A=237/B=254）：视频 sha 不同；元数据/评分/当前/删除保护；
    branch → Run 255（parent 254）；采纳 S03 只改 S03。
  - `e2e_takes.py`：同步播放 1.324s vs 1.324s；帧步同秒；差异面板；提升 A→B；采纳 B 的 S03。
  - **修复二次 Run 数据源**：B02/B03 现在优先 Run 快照 timeline（2.7.2），否则第二次 Run 会读旧
    `card/task.json`，时间轴/相机修改不进入 final（实测 A/B 视频曾同 sha，修复后不同）。
  - `verify_r3_audio_v2.py`（project 211 / run 266）：G01 场景拼接 5.0s、G05 mix 5.0s、
    G06 **−13.8 LUFS**（target −14）、stems 5/5/5s、processed take、16 onsets。
  - `e2e_audio_v2.py`：A/B/processed/检测拍点/拼接试听/响度预设 −16↔−14。
  - 123 tests（FR-36 前）；`e2e_ui.py`/`e2e_onboarding.py`/`e2e_r3.py`/`e2e_takes.py`/`e2e_audio_v2.py` 全绿。
  - R2.5 回归（2.8.0）：5s 交付 **24.1s**（project 215/run 270）；干净 rumor **46/46**
    （run 272，256.1s）；5s 黄金 **SSIM 1.0**（project 216/run 271，视觉断言；无音频 G 链失败不影响）。

**磁盘清理说明（2026-11-03）**：R3 验收期间大量 project（如 201/208/189/155）已在磁盘清理中删除，
上面 ID 是证据记录，不是当前可打开的项目。当前保留的演示/证据项目见 §7.4；所有验收脚本可复现。

**R3.0 v1 的诚实边界**：撤销 30 步已用 30 个文档版本恢复验证，但 30 步 UI 连点未自动化；
100 场景服务端 ops <0.2s，浏览器 100 场景 60fps 未实测；FR-38 没有音频波形对齐/帧差图，
只做视频同步 + difference 叠加；FR-35 SFX 已随 FR-36 完成；FR-37 模板/系列 v1 已完成；R3.5 未开始。

### 3.6 FR-36 资产库 v1（2026-11-03）

- **后端**：`Asset` 表 + `services/assets.py`；global `~/.filmflow/assets`、
  project `<root>/.filmflow/assets`；sha 去重、图片尺寸/音频时长/字体 family+cmap/视频元数据、
  缩略图、波形、引用扫描、删除保护、替换、字体覆盖。API `/api/assets` + file/thumb/waveform/
  font-check/replace。
- **Scene DSL**：`scene.layers[]`（image，box/z/fit/opacity）、`scene.fontSha`、
  `scene.audio_layers[]`（SFX）；compiler 通过 resolver 转 URL，缺失 `E_ASSET_MISSING`。
  FrameServer 新增 `/global-assets/`；renderer 预加载图片/字体，真正 drawImage（不再画叉）。
- **Run/预览**：D01/E03/F02 读取资产 URL；Preview/9:16 用 data URL；G05 读取 Run 快照
  `audio_layers` 生成真实 `card/stems/sfx.wav` 并混入；G01/G05/G06/G07 缓存键纳入
  `card/audio.json`、`card/audio.mix.json` 与 timeline sha（修复改设置仍 cached 的坑）。
- **UI**：`/assets` 全局/项目库、拖拽/文件上传、许可/标签、引用数/使用处、替换/删除保护、
  字体缺字标红；`/timeline` 资产面板可拖/点插入图片/SFX、选字体并自动缺字检查。
- **证据**：
  - `verify_r3_assets.py`：50 图（2 内容）新增 2/去重 48；引用计数 1；删除 409
    `E_ASSET_IN_USE` + 使用处；替换 `affectedScenes=["S01"]`；缺资产预览 409
    `E_ASSET_MISSING`；字体缺 2 字；全局 sha 复用；清理恢复。
  - `e2e_assets.py`：UI 上传图片/SFX、字体缺字标红、时间轴插入、引用计数 1、删除阻断。
  - project 211 / run 275（2.9.1）：D01/E03/F02 图片进入 final；G05 `sfxCount=1`、
    `card/stems/sfx.wav` 5.0s、volumedetect max **−24.1dB**；G06/G07 succeeded。
  - 5s 黄金（project 223 / run 282）：6 帧 **SSIM 1.0**，无资产项目视觉未回归。
  - **129 tests**；前端 `tsc --noEmit` 通过；ADR-0010。
  - 演示：`/assets?project=211`、`/timeline?project=211`（S01 有图片+SFX）。
- **边界**：视频只入库不进入 NLE；无智能裁切/主体检测；自定义字体全量 FontFace，不重做子集；
  预览大资产内联 data URL；资产目录暂无自动 GC。

### 3.7 FR-37 模板/系列 v1（2026-11-03）

- **项目模板**：`Template` 表 + `services/templates.py`；另存 profile/时间轴结构/相机/转场/
  图层/SFX/字体/风格/交付/文案；实例化时重建 script/timeline、写 `card/template.lock.json`，
  源项目本地资产复制到新项目，全局资产按 sha 复用。
- **场景模板**：内置标题/论点/证据/结论/行动；任意场景可另存；插入走 `timeline_ops.add_scene`，
  支持插入到选中场景之后；源资产随模板复制。
- **变量/系列**：`{{title}}`/`{{number}}`/`{{accent}}` 递归替换；`POST /series/from-template`
  ≤5 项同步创建、失败项隔离；CSV/10 行队列/批量 zip 依赖 R4 FR-46，未做。
- **版本/升级**：`POST /templates/:id/version` v+1；项目锁版本；
  `GET /projects/:id/template-diff`；`POST /template-upgrade {confirm:true}` 只覆盖已有场景
  视觉字段与 width/height/fps，保留文本/时长/id，不自动增删场景；未 confirm 不改文档。
- **UI**：`/templates` 项目/场景模板、另存、变量系列、插入；`/timeline` 场景模板下拉+
  保存当前场景；首页/画布入口。
- **证据**：
  - `verify_r3_templates.py`：另存 `saved:3` v1（变量 number/title）→实例化 project 228
    （文案替换/2 场结构/图片+SFX 资产复制/lock v1）→场景模板插入 S03→模板升 v2→
    diff/confirm 升级（lock v2）→系列 2 项 created=2；清理模板/项目。
  - `e2e_templates.py`：模板库/另存表单/系列表单；UI 另存模板；场景模板插入并跳时间轴；
    时间轴场景模板选择/保存入口；恢复演示时间轴。
  - **133 tests**；`verify_r2_5_onboarding.py` 允许已保存模板存在（内置三模板子集断言）。
  - 演示：`/templates`、`/templates?project=227`、`/timeline?project=227`（模板实例，lock v1）。
- **边界**：系列同步 ≤5；模板升级不增删场景/不迁移文案；模板源资产复制占磁盘；模板删除不删实例。

### 3.8 FR-39 QA 修复建议 v1（2026-11-03）

- `server/app/services/qa.py`：聚合 timeline 校验、NodeRun 失败消息、E06 motion 指标、
  资产解析与音频许可；输出稳定 issue（category/位置/原因/建议/影响/fixable）。
- 安全动作：扩场景 +0.5s、字号 −10%（`scene.text_scale`）、标点附近换行、
  target LUFS、填许可、重跑 failed 节点；改文案/删场景/换风格/重对齐只给 manual 链接。
- 撤销：`card/qa_fixes.json` 保存 before/after/afterVersion/verified；timeline 修复后若又有变化，
  自动撤销会被拒绝，避免覆盖新编辑。报告统计 attempts/applied/active/verified/undone/successRate；
  误报率明确标注需下一次成功 Run 复核。
- UI `/qa`：问题卡、位置/影响、自动按钮、manual 跳转、修复记录/撤销；画布/帮助入口。
- 证据：
  - `verify_r3_qa.py`（project 227）：text_overflow → 扩场景 → 即时验证 → 撤销；
    许可修复→验证→撤销；缺资产定位；报告 attempts=8/undone=8/successRate=1.0。
  - `e2e_qa.py`：QA 页问题卡、扩场景按钮、即时验证、UI 撤销。
  - `test_qa.py` 3 项 + `text_scale` 编译断言；**137 tests（FR-39 当时）**。
  - `EXECUTOR_VERSION=2.9.2`（text_scale，FR-39 当时）；preview `preview-1.7.0`；46 节点/边不变。
- 边界：impact 秒数是粗估；视觉溢出没有独立检测；manual 动作不自动；导入项目只读；
  retry 仍受 RunEngine/门/锁约束；falsePositive 需成功 Run 复核。

---

## 4. 架构与关键文件

### 4.1 46 节点主链（未变）

```
docs → Run 快照 → A01 → B02/B06/B07 → C01/C02/C03/C04/C05
 → D01（program）→ D02（review/draft 静帧 + contact sheet）→ D03（逐场查看）→ D04（QA/diff）→ D05
 → E01/E02/E03（motion）→ E04（transitions）→ E05（review proxy）→ E06 → E07
 → F01（8787）→ F02（only final）→ F03 → F04 → F05 → F06
 → G01/G02/G03/G04/G05/G06 → G07
```

- D01/D02/E05/F02/F04/F05/G07 的 final/profile/项目本地缓存约束见 §5。
- 46/7/8+8/93 是硬约束；R2.5 新能力不新增节点。

### 4.2 预览（FR-23）

- `server/app/services/preview.py`：上下文解析、base/motion 编译、CDP/临时 Chrome、水印、500MB 缓存、
  latest-wins、segment/film job。
- F02 Chrome：`--remote-debugging-port=9222`；F02 运行中只附加同一 Chrome，空闲时临时 Chrome。
- 相机：`_camera()` 读 timeline `camera_keyframes`/`camera_anchor`；与 E02 共用 compiler。
- 页面：`/review`、`/audio` 不依赖预览页；预览 API 独立。

### 4.3 档位（FR-24）

- `server/app/services/render_profiles.py`：draft/review/final；final 尺寸/fps 由项目 profile 锁定。
- Run 快照写入 `render_profiles`；`PROFILE_NODES` 缓存键含 `renderProfilesSha`。
- API：`GET/PUT /projects/:id/render-profile`。

### 4.4 Job/恢复（FR-29）

- `server/app/services/jobs.py`：Job 表、租约 30s/心跳 5s、retry_wait、启动恢复、孤儿清理、队列 API。
- `runengine.py`：每个 Run 一个 Job；阻塞停 retry_wait；包执行门（G07）批准后回 idle。
- `main.py` lifespan：cleanup_orphans + recover + start_run。
- 优先级：preview 100 / interactive 80 / batch 40 / delivery 20。
- **单进程假设**；不要同时跑两个 API worker。

### 4.5 R2.5 服务

- 审阅：D01 多 times；D02 `stills_manifest.json`（scene→times）+ 16 宫格 contact sheet；
  D03 逐场 viewed；D04 `review_diff.json`；D05 pending 返回 stills/contactSheet/diff。
- 音频：`server/app/services/audio.py`：Take 导入（base64→ffmpeg WAV）、主 Take、
  `card/audio.json`、waveform、`card/alignment.manual.json`、`card/music_license.json`。
  G01 读取主 voice Take；G02 manual 优先；G04/G05 读取主 music Take；G05 sidechain + loop + stems。
- 交付：`server/app/services/delivery.py`：9:16 variant compiler、frames render、SRT、covers、QC、
  manifest/rights、zip、Job。
- 页面：`/review`、`/audio`、`/delivery`、`/help`；首页模板与引导。

### 4.5b R3.0 服务（创作闭环 v1）

- `server/app/services/timeline_ops.py`：resize/ripple、move、split/merge/duplicate、set_text、
  set_camera、camera_preset、set_transition；normalize/validate；`/projects/:id/timeline/ops` 乐观锁。
- `server/app/services/review_comments.py`：`review/review.json`；评论/回复/resolve/场景+整片决议；
  JSON/CSV 导出、按 id 去重导入、`review-package.zip`（review.mp4 + review.json + README）。
- 页面：`/timeline`（V/T/C/A1/A2/A3/M 轨道、拖拽/ripple、inspector、250ms 静帧预览）、
  `/player`（视频、批注覆盖、跳帧、决议、导出导入、审片包）。
- 数据源：timeline scene `text`/`camera_keyframes`/`camera_anchor`/`transition`；ADR-0008。
- **资产（FR-36）**：`server/app/services/assets.py`（表/存储/元数据/引用/替换/字体覆盖）；
  timeline scene 增加 `layers`/`fontSha`/`audio_layers`；compiler `asset_resolver`；
  FrameServer `/global-assets`；renderer `preloadProgram(s)` + 真图绘制；G05 SFX；
  页面 `/assets` + 时间轴资产面板；ADR-0010。
- **模板（FR-37）**：`server/app/services/templates.py` + `Template` 表；项目/场景模板、
  变量替换、模板锁/版本/diff/upgrade、系列 ≤5；`/templates` 页面 + 时间轴场景模板；
  ADR-0011。

### 4.6 缓存/锁（必须理解）

- `EXECUTOR_VERSION=2.10.0`；改执行器必须升。
- `DOC_NODES` 缓存含 `doc_snapshot_sha`；`PROFILE_NODES` 含 `renderProfilesSha`；
  `PROJECT_LOCAL_NODES={D01,D02,E03,E04,E05,F02,F04,G01,G05,G07}` 含 `projectRoot`。
- **外部输入**：A01 copy、A03 风格库内容指纹、F01 项目根、G01 语音文件以 `_external:*` 进键。
- **引擎包**：C01 键含 `enginePackSha`；改 `engines/riso/**` 会从 C01 失效并向下游传播。
- **项目音频**：G01/G02/G04/G05/G06/G07 含 `projectInputsSha`（audio.json、mix、alignment、
  `card/audio/*.wav`）；G01/G05 另含 timeline 快照 sha。
- `chrome-queue=1`；`ffmpeg=1`；`port-8787=1`（F01/D02/E05/F02）。
- Chrome profile：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`。

### 4.7 文件地图

| 想改什么 | 去哪 |
|---|---|
| 节点/边/锁 | `server/app/engine/edges.py` |
| 调度/门/caps/缓存 | `server/app/engine/runengine.py` |
| 子进程 | `server/app/engine/runner.py` |
| D–G 执行器 | `server/app/engine/executors/pipeline.py`、`__init__.py` |
| Scene DSL | `server/app/engine/scene/*` |
| 增量 | `server/app/engine/render_manifest.py` |
| Run 快照 | `server/app/engine/snapshot.py` |
| 文档 | `server/app/services/project_docs.py` |
| 预览 | `server/app/services/preview.py` |
| 档位 | `server/app/services/render_profiles.py` |
| Job/恢复 | `server/app/services/jobs.py`、`main.py` |
| 音频 | `server/app/services/audio.py` |
| 资产 | `server/app/services/assets.py`、`web/src/app/assets/page.tsx` |
| 模板 | `server/app/services/templates.py`、`web/src/app/templates/page.tsx` |
| QA | `server/app/services/qa.py`、`web/src/app/qa/page.tsx` |
| SFX | `server/app/engine/executors/pipeline.py`（G05 `_timeline_sfx`/`_build_sfx_stem`） |
| 交付 | `server/app/services/delivery.py` |
| UI | `web/src/app/{review,audio,assets,templates,qa,delivery,help,page.tsx}`、`canvas/page.tsx` |
| 黄金 | `fixtures/golden/`、`scripts/golden_run.py` |

---

## 5. 踩坑清单（按优先级，必须看）

1. **EXECUTOR_VERSION**：改任何执行器行为必须升版；当前 2.9.3，否则缓存返回旧行为。
2. **task 快照回退**：B06 同文档缓存命中时不会写 `runs/<id>/docs/task.json`；`_task_path` 必须回退
   只读 `card/task.json`，否则 D01 空场景、D03/D04 失败。
3. **timeline 持久化**：materialize/首次快照落 timeline doc；编辑 script 不得重建 timeline，
   否则改一句导致全场景时长漂移、全量重渲。
4. **reading window**：`last_text_at=end-read_seconds`；B07 校验 `last_text_at+read_seconds≤end`；
   G06 用 `last_text_at+read_seconds` 作为句子对齐目标。
5. **项目本地缓存**：D01/D02/E03/E04/E05/F02/F04/G01/G05/G07 写项目文件，缓存键必须含 projectRoot；
   新增文件产物节点必须加入 `PROJECT_LOCAL_NODES`，否则 program/transitions/master/帧留在旧项目。
   R3 实测踩到 E04 跨项目命中导致新项目缺 `scenes/transitions.json`。
6. **G07 门**：G07 是 human+package；gate_decide 必须把 NodeRun 置 idle（不是 succeeded），
   否则 package 永远不执行、master 缺失。G07 前 `ensure_final_ready`；imported 跳过。
7. **G05 音频**：必须 sidechaincompress + 音乐循环/淡出到片长；`alimiter=limit=0.7:level=false`
   （默认 level=true 会自动拉响度）；mix WAV 有多份（mix/voice/music/sfx），取 `meta.mix` 或
   `card/mix.wav`，不要取最后一个 WAV。
8. **G04 解码**：ffmpeg 输出必须落临时文件，不能写 stdout 管道（大音频 64KB 死锁）。
9. **F02 CDP**：9222 仅在 F02 渲染区间可用；预览附加需 3s 重试，F02 结束竞态回退临时 Chrome/429；
   attached 模式只关 page，不关浏览器。
10. **预览质量**：单帧 native→Lanczos；片段 native JPEG q0.98→Lanczos；直接 960p 会让半调网点
    相位错位（SSIM 0.80）。缓存键含 out spec/RENDERER_VER。
11. **D02/D04**：contact sheet 是 PNG 但 D04 必须跳过（`meta.contact_sheet`）；D02 review/draft
    meta.profile 必须存在；D03 新项目逐场查看、imported 保持 ≥3 区域。
12. **引用扫描面**：`scan_usages` 现在覆盖 timeline + 其它项目文档 + `Template.content_json` + Run 快照。
    只按 timeline 图层判断"资产是否在用"的代码路径都是错的（模板与历史 Run 也算引用）；同一容器里的
    `assetShas` 是派生索引，已去重，别在它上面再叠一层计数。
13. **before/after 别名**：`docs_svc.doc_payload(...)["content"]` 返回 SQLAlchemy 对象的同一 dict。
    任何"先记 before、后原地改"的写法必须 `deepcopy`（QA 撤销曾因此形同空操作），
    且内容哈希必须算在 `save_doc` 返回的 `saved.content_json` 上，不能算保存前的 dict。
14. **改端点签名的连带影响**：`/projects/import`、`/drafts/{id}/materialize` 是**直接函数调用**
    `projects_create(...)`，把端点参数换成 Pydantic 模型后必须同步传模型实例（否则 500）。
    integration 测试是抓这类回归的第一道网，别只跑 unit。
15. **重启才生效**：`./dev.sh` 不带 `--reload`；`pgrep -f 'uv run uvicorn'` 杀不到真正监听的 python 子进程，
    用 `lsof -nP -iTCP:7860 -iTCP:3000 -sTCP:LISTEN -t | xargs kill`（配方见 §0.7）。
16. **探针写库事故**：`TestClient(app)` 连生产 DB；本轮一次手工探针给 rumor-39s 写了 timeline 文档行，
    已删除并复原。**写类验证一律用临时 HOME 或 `scripts/_acceptance.py`。**
12. **job attempts**：只在启动恢复时 +1；gate 重启/retry_wait 不自增；≥max 才失败。
13. **SQLAlchemy JSON**：原地改 `graph_json` 后必须 `flag_modified`。
14. **C02 字体**：异步 runner + 本地 cache/既有 artifact 回退；禁止同步 subprocess curl 阻塞事件循环。
15. **相机预览同源**：PreviewService `_camera()` 必须读 timeline `camera_keyframes`；R3 曾因仍用默认
    缓推导致 preview vs final SSIM 0.85，修复后 0.9895。E02 与 PreviewService 都走同一 compiler。
16. **读时门禁范围**：改文本/时长/分割/合并受 `E_SCENE_READ_OVERFLOW` 阻断；相机/转场/排序
    不应被既有读时错误连带阻断（否则用户无法继续结构编辑）。
17. **scene.text**：时间轴 override 优先于 source_span/meaning；script 仍是口播/字幕/对齐事实源，
    改画面文字不要改 script。
15. **F04 跨项目**：即使已有 projectRoot，消费者仍优先用 `_upstream_file`（内容寻址）兜底。
16. **FrameServer**：8787 全局单例；D02/E05/F02 持 `port-8787`；否则根目录被别的 Run 改。
17. **ProcessRunner**：正常退出后 cancel `_watch_cancel`；否则永久挂起。
18. **字体 family**：B05/compiler 去掉 `900/500` 字重后缀，否则 Canvas 文字不渲染。
19. **golden baseline**：与 H2/1920×1080/24/字体绑定；只有有意改视觉才 `--update`；失败看 diff。
20. **交付封面**：9:16 封面取中间场景 reveal 完成后的帧，不要取转场/未揭示帧；16:9 取 D02 review。
21. **交付 QC**：LUFS −16±1、TP≤−1.5、字幕行宽≤16/速度≤9、封面精确尺寸；失败 `E_DELIVERY_QC`。
22. **React 19 UI**：Playwright 用 click+keyboard.type，`fill()` 不触发 onChange。
23. **manual alignment**：whisper 缺失必须显式 `manual`，不要伪装词级；本机无 whisper model。
24. **单进程 Job**：启动恢复会杀 `/tmp/ff-*` Chrome/项目 ffmpeg；不要多 worker。
25. **范围边界**：R2.0/R2.5/R3.0 v1 已完成，不要重做；FR-39 已完成，下一批 R3.5（FR-40/41）；
    **不要提前做 R4**（多规格矩阵/平台发布/批量 CSV/photo 引擎）。

---

## 6. 剩余工作（R2.5 已收口；6.5 为 R3 下一批）

> 6.1–6.4 是 R2.5 收口记录（均已完成/已裁决），保留用于追溯；**真正的下一步是 6.5**。

### 6.1 FR-31 新手引导（PARTIAL → DONE）

1. **模板音频占位**：`/projects/from-template` 生成 15/30/40s 占位 voice + music（或提供
   “填充占位音频”按钮），写 `card/audio.json`/license/alignment；确保 G06 能过（不要纯静音）。
2. **wizard 标题预演**：当前 `/styles/:id/preview` 使用风格自带图；Step 3 需用用户标题渲染
   3 个候选标题的缩略图（可复用 previs 渲染器/标题文本参数），避免固定「风」。
3. **示例只读副本**：示例项目 `meta.example=true`；所有写 API 阻断；提供
   `POST /projects/:id/clone` 复制为我的项目；路径仍须 project root 内。
4. **Studio 引导**：首次进入 editor/canvas 的 5 步 overlay（场景→单帧→改一句→diff→draft），
   可跳过/重看，不阻塞老用户。
5. **10 分钟走查**：新模板→改文案→音频占位→draft→审阅→交付，记录耗时与截图。

### 6.2 40s 交付实测（FR-28，已通过）

- 40s 项目（project 174 / run 223）全链到 G07（305.4s），`POST /projects/:id/delivery` 成功；
  delivery **190.0s**，9 文件 + zip，QC 全绿，两个 master 均 40.000s/带音轨。
- 9:16 960 帧、SRT 5 cues（≤16 字/行、2.31 字/秒）、封面 1920×1080/1080×1920。
- 证据与复现命令见 §3.3；`verify_r2_5_delivery_40s.py` 支持全链与 `--project/--run` 复用 G07。
- 注意：run 223 manifest 有 7 条 run-local 审批（G03 继承），DAG 实际 8 个人工门；PRD「9 条审批」
  与当前 8+8 门口径不一致，未伪造第 9 条（见 §3.3 审批口径）。

### 6.3 G07 与交付包整合决策（已定）

- 决策记录：[ADR-0007](docs/adr/ADR-0007-g07-qc-and-delivery.md)。
- **G07**：DAG 内最终打包门，输出 master，并做核心 QC（时长/分辨率/fps/音轨/LUFS/TP）；
  失败 `E_QC_*` 阻断并给修复建议；不渲染 9:16、不生成 zip。
- **DeliveryService**：显式 post-run 作业（API/页面）；非导入项目必须已有 G07 `succeeded/cached`，
  否则 `E_DELIVERY_GATE`；完整包 QC 失败则 Job 失败；manifest 记录 G07 master sha + 全部文件 sha。
- 代价：G07 QC 最初升到 2.6.6；当前总版本 **2.9.3**；普通 Run 只多一次 ffprobe/ebur128。

### 6.4 R2.5 DoD（收尾时逐项打勾）

- [x] FR-26 全场景静帧/逐场门禁/diff（DONE）
- [x] FR-27 音频 Take/波形/对齐/许可/Stems/G06（DONE）
- [x] FR-28 16:9+9:16+SRT+封面+QC+zip；R2.5 5s 26.2s / 40s 190.0s（2.8.0 5s 24.1s）
- [x] FR-31 模板音频占位/标题预演/只读示例/Studio 引导（DONE）
- [x] 102 tests（R2.5 收口时；当前 **189 tests = unit 169 + integration 13 + BDD 7**）、E2E、干净 rumor 46/46 回归（run 222，90.6s；口径为 20 succeeded + 26 cached）
- [x] 交付与 G07 关系有明确记录（ADR-0007；G07 master QC + Delivery 显式作业）
- [x] R2.5 DoD 全绿；R3.0 v1 已开始且未回退 R2

### 6.5 下一批（P0 已关闭；P1 剩余项优先，FR-40/41 由老板点头即开工）

1. **P0 Gate：全部关闭**（P0-1/2/3/5/4a 完成；P0-4b 脚本 + 5s 原帧证据完成，40s/15s 未实跑）。
2. **P1 剩余（建议顺序，逐项附证据再申报）**：
   1. **P1-19** 其余验收脚本迁到 `scripts/_acceptance.py`：`e2e_takes.py`（PID 188/run 237/254）、
      `e2e_assets.py`（PID 211）、`verify_r3_assets/templates/camera/takes/audio_v2/rumor_regression.py`；
      依赖已有 Run 的脚本需要自建 5s 项目 + 真跑一次管线（约 1–2 分钟/项目，跑完清 frames/proxy）。
   2. **P1-12** 非整数 fps：`int(fps)` 集中在 `services/preview.py`、`services/render_profiles.py`、
      `engine/scene/compiler.py`、`engine/pipeline.py`；先定帧网格口径（建议保留 `fps` 分数 + 帧号用
      `round(t*fps)` 统一函数），改执行器必须升 `EXECUTOR_VERSION` 并重跑 `golden_run.py`。
   2. ~~P1-12~~ ✅ 已完成（见 §0.6）；3. **P1-09** 多步写：`templates.py::_materialize_first`、`takes.py` branch/replace、`assets.py` replace
      做失败注入（ monkeypatch 第二次 commit 抛错）+ 半成品断言，再决定是否包事务/补偿。
   4. **P1-23** 剩余 42 个 `payload: dict` 端点（`rg -c "payload: dict" server/app/api/routes.py`）。
   5. **P1-10** `web/src/app/error.tsx` + `global-error.tsx`；**P1-11** 时间轴虚拟化前先做 100 场景实测。
   6. **P1-06 收尾**：先修级联/删除顺序，再开 `foreign_keys=ON`（现在开会让测试立刻失败）。
   7. **P1-20/P1-21**：CI（pytest + ruff）与 fresh-clone bootstrap；`docs/reports/**` 自动归档扩展到其余验收脚本。
3. 之后 **FR-40 命令面板与通知** / **FR-41 本地规则式创作辅助**；未开始不虚报。
4. FR-36/37/39 v1 已完成（§3.6–§3.8、ADR-0010/0011/0012）；其边界见 §9。
5. **不要提前做 R4**（批量 CSV/多规格矩阵/平台发布/photo 引擎）。

---

## 7. 命令、环境、复现

### 7.1 开发/测试

```bash
./dev.sh                                # 改代码后必须重启；配方见 §0.7
cd server && uv run pytest tests -q     # 189 passed；再跑一次，GET /api/projects 计数应不变
uv run pytest tests/unit/test_migrations.py -q          # P1-07 迁移登记处
uv run pytest tests/unit/test_request_models.py -q      # P1-23 422 校验
uv run pytest tests/integration -q                       # 独立临时服务/HOME/workspace
uv run --project server python scripts/verify_p1_governance.py   # 本轮 P1 门禁 8 步复核（自建自删）
cd .. && uv run --project server python scripts/verify_r3_qa.py   # 自建自删临时项目，6 步
cd .. && uv run --project server python scripts/e2e_ui.py
uv run --project server python scripts/smoke_m1.py
uv run --project server python scripts/verify_r2_incremental.py --project 5s
uv run --project server python scripts/verify_r2_preview.py
uv run --project server python scripts/verify_r2_profiles.py
uv run --project server python scripts/verify_r2_recovery.py
uv run --project server python scripts/golden_run.py --project 5s --resolution original
uv run --project server python scripts/verify_r2_5_review.py
uv run --project server python scripts/verify_r2_5_audio.py
uv run --project server python scripts/verify_r2_5_delivery.py
```

### 7.2 常用 API

```bash
curl -s http://127.0.0.1:7860/api/health
curl -s http://127.0.0.1:7860/api/templates
curl -s http://127.0.0.1:7860/api/runs/<id>/render-manifest
curl -s http://127.0.0.1:7860/api/projects/<id>/audio
curl -s 'http://127.0.0.1:7860/api/assets?scope=project&projectId=<id>'
curl -s 'http://127.0.0.1:7860/api/assets?scope=global'
curl -s 'http://127.0.0.1:7860/api/templates?kind=scene'
curl -s 'http://127.0.0.1:7860/api/projects/<id>/template-lock'
curl -s 'http://127.0.0.1:7860/api/projects/<id>/qa'
curl -s 'http://127.0.0.1:7860/api/projects/<id>/qa/report'
curl -s http://127.0.0.1:7860/api/projects/<id>/deliveries/<run>
curl -s http://127.0.0.1:7860/api/queue
```

### 7.3 数据/清理

- 真实 DB：`~/.filmflow/filmflow.db`（WAL + `synchronous=NORMAL`；**`foreign_keys` 仍关闭**，见 §0.6 P1-06）。
- **没有 `DELETE /projects/{id}` 端点**：删项目必须走 DB（参考 `scripts/_acceptance.py::destroy` —— 按
  `project_id`/`run_id` 清 `SQLModel.metadata.sorted_tables` 全部相关表，再删目录）。
- 测试 DB：P0-3 后 integration 用独立临时 uvicorn/HOME/workspace；unit 用每次 pytest 独立的 `mkdtemp` HOME
  并在结束时清理。连跑两次 `pytest server/tests -q` 后 `GET /api/projects` 计数不变（现测 35→35）。
- 手工探针纪律：**`TestClient(app)` 直接连生产库**，只有"必然被 422/400 挡在 handler 之前"的请求可以用；
  任何会写的请求要么打到独立 `FILMFLOW_HOME` 的临时服务，要么用 `scripts/_acceptance.py` 的临时项目
  （本轮一次探针误写 rumor-39s 已复原，详见 §0.7）。
- 8787 是 FrameServer；EADDRINUSE 先查健康检查/残留进程。
- Chrome 残留：`/tmp/ff-{node}-{run_id}`、`/tmp/ff-chrome-{node}-{run_id}`；启动恢复会清理。
- 预览缓存：`~/.filmflow/cache/preview/<project>`；交付：项目 `out/deliveries/<runId>`。
- DB 备份（可删）：`~/.filmflow/` 下 4 份 `filmflow-before-*.db`（40/19/27/27MB）。

### 7.4 项目/磁盘清单（2026-11-03 20:00）

- **DB 35 个项目**，其中 **8 行的 root 目录已不存在**：project 228/229/232/233/235/236/237/238
  （专家审计与被清理的 `it-*` 测试项目遗留）；清库时先按 §7.3 走 DB，别只删目录。
- **`filmflow-projects` 29 个目录 / 2.3GB**（含空的 `.acceptance/`）。目录清单：
  `FR37模板演示-1`、`r2_5-audio-160`、`r2_5-delivery-216`、`r2_5-delivery-224`、`r2_5-delivery40-185`、
  `r3-audio-v2-221`、`r3-camera-199`、`r3-demo-20261103-1`、`golden-5s-217/225/230`、
  `rumor-clean-20261102`、`trace-x`、`it-engine-236/240/242`、`it-wizard-235/239/241`、
  `一条消息被转发往往不是因为-1`、`r2-verify-5s-244/245`、`golden-5s-246/247/248`、
  `r2-profiles-243`、**本轮新增 `r2-profiles-249/250/251`**（档位验收重跑；三者的 `out/frames`+`out/proxy`
  已删，各留 ~16MB 证据）。另有仓库外参考项目 `rumor-39s`（897MB）。
- `~/.filmflow` **1.1GB**、`ai-v` **4.0GB**。
- 演示项目（不要动）：202（时间轴）、174（审片/40s）、188（Take；run 237/253/254 当前 timeline 漂移，
  交付会被 `E_DELIVERY_GATE` 拦）、211（音频 v2 + 资产 run 275；run 266 同样漂移）、215（5s 交付）、
  216（黄金 5s）、223（FR-36 黄金 run 282，状态 failed，**不作成功证据**）、227（FR-37 模板实例 + FR-39 QA，
  本轮起 `verify_r3_qa.py` 不再改写它）。
- 风格库：**逻辑约 74.7MiB（示例 mp4 约 59.8MiB），磁盘分配约 9.3MiB**（mp4 是稀疏文件）；库外置不入 git。
- **磁盘纪律**：40s 项目一轮约 4.3GB（frames 2.7G + proxy 1.4G）。新脚本默认收尾清理
  （`verify_r2_incremental.py` 的 `finally`、`golden_run.py`）；手工跑其他验收后请自行删 `out/frames`、`out/proxy`，
  保留 `film/artifacts/stills/交付包`。
---

## 8. 硬约束（不要违反）

- 仅本机 `127.0.0.1`；不上传文件；不调用在线生成模型。
- 46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash 语义不变；边数 93。
- Chrome 全局串行 1 个（`chrome-queue=1`）；ffmpeg 独占；预览不新开第二个浏览器。
- 新项目禁止 `legacy_entry`；只有 `meta.imported=true` 可走 v1 harness。
- 改执行器行为必须升 `EXECUTOR_VERSION`（2.10.0）。
- 路径白名单/禁止路径穿越；FrameServer 只服务 `/engine`、`/project` 与 `/global-assets`。
- 风格库逻辑约 75MiB（mp4 稀疏文件，磁盘分配约 9.3MiB）不入 git；`vendor/fy-code-animation` 只查方法，不 import。
- R3.0 v1 含 FR-32–38；R3.5 FR-39 已完成，下一批先修专家审查 P0 再做 FR-40/41；R4 不提前做。
- UI 自动化用系统 Chrome + 键盘输入（Next 静态导出存在水合竞态；React 19 `fill()` 不是唯一原因）。

---

## 9. 已知限制/风险（交接必须知道）

1. **FR-31 已 DONE，但示例是仓库 fixture**：`fixtures/examples/` 只读源 + 克隆项目；不是可浏览的
   预置数据库项目。模板音轨是占位文件，不会生成假音频。
2. **FR-28 40s 已实测**：delivery 190.0s；比 5s（26.2s）慢主要来自 9:16 的 960 帧重渲。
3. **G07 与交付边界**：G07 做 master + 核心 QC；交付包是显式 post-run 作业，必须等 G07 通过（ADR-0007）。
4. **档位 UI 未接**：API/服务可用；时间轴/审片已用预览，编辑器内档位切换 UI 仍留后续。
5. **单 API worker**：Job 恢复/孤儿清理假设单进程；多 worker 不支持。
6. **whisper 缺失**：本机无 whisper CLI/model；G02 manual；R2.5 音频不伪装词级。
7. **golden baseline**：绑定 H2/1080p24/字体/风格库；换库需确认后 `--update`。
8. **40s golden**：run154 G01 因无音频失败，但 A–F/F02 成功；不要用 run 状态判断视觉回归。
9. **交付 9:16**：当前 Scene DSL 重排（非智能裁切/主体检测）；复杂版式可能 `approximate`。
10. **非 riso 新项目**：ink/code-video 仍 Contract 1.0，C01 阻断；R2.0/R2.5 范围外。
11. **测试污染真实 DB**：已修（P0-3）。integration 起独立临时 uvicorn/HOME/workspace，unit 每次 pytest
    用独立 `mkdtemp` HOME 并清理；连跑两次 `pytest server/tests -q` 后项目计数不变（现测 35→35）。
    残留的 `it-*` 历史行是修复前产生的（其中 8 行 root 已不存在，见 §7.4），删除需老板点头。
12. **F02 固定 9222**：端口被占会启动失败；排查 `lsof -i :9222`。
13. **UI i18n**：新页面中文优先；不要破坏既有 zh/en 切换。
14. **R3.5 未含**：FR-40/41 与 R4；不要把未开始项写成已完成。FR-36/37/39 v1 已做。
15. **时间轴撤销**：UI 历史 50 步；30 步只验证了文档版本恢复；长链 UI 连点未自动化。
16. **时间轴性能**：100 场景 ops 服务端 <0.2s；浏览器 60fps 未实测。
17. **审片批注**：项目级 review.json（不按 Run 分桶）；Take 对比已做，但无音频波形对齐与帧差图。
18. **R3 版本**：EXECUTOR_VERSION 2.10.0；D01/E03/E04 已加入 project-local 缓存；
    新项目二次 Run 的 B02/B03 必须读 Run 快照 timeline，不能读旧 card/task.json。
19. **A03 扫描**：风格库扫描已改 `asyncio.to_thread`，但版本升级/首次索引仍可能耗时数分钟；
    不要把同步扫描塞回事件循环。
20. **音频 v2 边界**：拍点是数值/检测列表，没有波形拖拽；SFX 已随 FR-36 做（场景级）；
    G07/Delivery 的 LUFS 范围读 `card/audio.mix.json` 的 targetLufs（−14/16/18 ±1），别再写死 −16。
21. **资产 v1 边界**：视频只入库/预览，不进入 NLE 图层；没有智能裁切/主体检测；自定义字体
    走 FontFace 全量加载，不按项目重做子集；大图/字体在预览 payload 内联 data URL。
22. **资产替换范围**：替换只重写**项目文档里的 timeline**；模板与 Run 快照**不改写**，
    但会在 `usages` 里报出来，替换响应新增 `untouched: {template: n, run: m, doc: k}` 明示未改面。
    删除被引用资产默认 409（含模板/历史 Run 引用）；`force=true` 才会留下断链（渲染报 `E_ASSET_MISSING`）。
23. **资产 GC**：删除项目不会自动清理 `.filmflow/assets` 与全局未引用资产；需手动归档/删除。
24. **旧项目 SFX 总线**：老项目 `card/audio.mix.json` 可能保留 `stems.sfx=-120`（旧默认），
    新加 SFX 会被静音；在 `/audio` 把 SFX 调到 0 即可。新项目默认 0。
25. **许可门禁（本轮新增，行为破坏性）**：任何资产种类入库都要 `license.source`+`license.type`，
    `expires` 必须未过期 ISO；被引用中的资产不许清空/削弱许可；交付前 `rights.json`（schema
    `filmflow.rights/2`）逐项列真实资产许可，有缺口 `E_LICENSE_MISSING` 直接拒交付。
    QA 的 `fill_license` 是 `kind=confirm`，不再预置 `authorized=true`（UI 需输 YES）。
26. **交付一致性门禁（本轮新增）**：非导入项目交付前要求"当前 timeline 内容哈希 == 所选 Run 快照哈希"，
    否则 `E_DELIVERY_GATE`。演示 188（run 237/253/254）与 211（run 266）当前就处于漂移态，
    直接交付会被拦——这是预期，需重跑 F02/G07 或基于当前文档新建 Run。
27. **QA 撤销是 LIFO**：`undo_fix` 只在"文档内容仍等于该次修复结果"时放行，所以多步修复必须
    倒序撤销；抢跑会被拒并点名应先撤的 fixId。撤销还会删除"修复前不存在"的 profile 文档行。
28. **档位 SSIM 口径**：`verify_r2_profiles.py` 现在分窗口断言（稳定段 ≥0.98 / 切点与入场 0.5s 窗口 ≥0.90）。
    draft 只有 12fps，时序量化在窗口内必然可见（实测最低 0.952097）；想回到"全局 ≥0.98"要先解决
    draft 的时间采样口径，别偷偷改回只取稳定段的旧口径（那是 §2.4 记录的证据修正点）。
29. **P1-23 只做第一批**：`routes.py` 仍有 42 个 `payload: dict` 端点（`rg -c "payload: dict"`）。
    模型化时保持默认值与服务层原取键方式一致，多态端点用 `extra="allow"` + `model_dump()` 透传。
30. **`foreign_keys=ON` 故意没开**：现有删除路径不完整，开启会立刻把测试打在 FK 约束上；
    必须先做级联/删除顺序批次（P1-06 收尾），再开。
31. **未跑的证据**：~~40s 增量~~ ✅（2026-11-04 run 311 实跑 PASS，9.69%，报告已归档）；
    15s/40s 原帧 golden（`golden_run.py --project 15s|40s --resolution original`）仍待实跑，
    各约 4.3GB / 数十分钟。申报"40s 复现"之前 40s 已可引用 run 311。

---

## 10. 接手检查表（第一小时）

- [ ] `./dev.sh`（或按 §0.7 配方重启）；`/api/health`、`:3000` 正常。
- [ ] `cd server && uv run pytest tests -q` → **219 passed（unit 190 + integration 13 + BDD 7）**
- [ ] 连跑两次上面这条，`GET /api/projects` 计数不变（当前 35）——这是 P0-3 的核心验收。
- [ ] `e2e_ui.py` 8 场景；`smoke_m1.py` 46/93。
- [ ] Phase 4/5/6/7/8 verifier 全绿（见 §0.2）。
- [ ] R2.5 review/audio/delivery verifier 全绿。
- [ ] `verify_r3.py`、`verify_r3_camera.py`、`e2e_r3.py`、`verify_r3_assets.py`、`e2e_assets.py` 全绿。
- [ ] `verify_r3_templates.py`、`e2e_templates.py` 全绿。
- [ ] `verify_r3_qa.py`（已自包含：自建自删临时项目，6 步，含多步 LIFO 撤销与资产许可分类）、`e2e_qa.py` 全绿。
- [ ] `verify_p1_governance.py` → 8 步全 ✓（本轮 P1 门禁一条命令复核，见 §0.6.3）。
- [ ] 打开 `/timeline?project=202&run=252`、`/player?project=174&run=223`、`/takes?project=188`、
      `/audio?project=211`、`/assets?project=211`、`/templates?project=227`、`/qa?project=227`。
- [ ] 读 §0.6（状态表）、§0.6.1（破坏性语义）、§0.7（运维坑）、§5、§6.5、§9；
      下一步按 §6.5 的 P1 剩余顺序，或经老板点头开 FR-40/41；不重做 R2/R3 已完成 FR。
- [ ] 申报完成必须附：测试输出、产物路径+sha/时长、UI 截图/curl。

---

## 附录 · 参考文档

| 文档 | 说明 |
|---|---|
| `AGENTS.md` | Agent 入口与硬约束 |
| `docs/process/r2_5-plan.md` | R2.5 计划/FR 状态 |
| `docs/process/r2-acceptance.md` | R2.0 验收报告 |
| `docs/prd/PRD-002-production-workbench.md` | v2 30 FR / 两级执行 / 交付矩阵 |
| `docs/adr/ADR-0005-v2-ratification.md` | D1–D7 冻结裁决 |
| `docs/adr/ADR-0006-preview-service.md` | 预览服务设计 |
| `docs/adr/ADR-0010-asset-library.md` | FR-36 资产库/图片/字体/SFX 决策 |
| `docs/adr/ADR-0011-template-series.md` | FR-37 项目/场景模板/系列决策 |
| `docs/adr/ADR-0012-qa-repair.md` | FR-39 QA 分类/安全修复/撤销决策 |
| `docs/process/r2-plan.md` | R2.0 阶段计划 |
| `fixtures/golden/` | 5s/15s/40s 黄金 fixture/baseline |
| `../filmflow-web-agent-prompt.md` | 规格宪法（仓库外） |

*任何“完成”申报必须附测试输出、真实产物路径（sha/时长）、UI 截图、API curl。没有证据就写“未验证”。*
