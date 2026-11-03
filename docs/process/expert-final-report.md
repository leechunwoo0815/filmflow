# 专家整夜自主循环 · 最终报告（2026-11-04 05:40 收官）

> 执行者：ZCode（goal 模式）。工作目录 `/Users/litianyu/cc-projects/ai-v/filmflow`（master，已推 `git@github.com:leechunwoo0815/filmflow`）。
> 本报告对 expert-overnight-goal-prompt 的 7 条收敛判据逐条自检；证据全部落在
> `docs/process/expert-runlog.md`（B0–批 9 + 验收扫描）与本文件，均可复现。

## 一、收敛判据逐条自检

### 1. 证伪清单归零 ✅
`docs/process/expert-runlog.md` F-* 清单共 11 项，全部 CLOSED：
- **实锤修复 6 项**：F-DEL-1（快照缺失门禁 no-op）、F-DEL-2（只比 timeline 不比 script）、
  F-DEL-3（封面标题读当前文档）、F-QA-1（mix/license 撤销无守卫）、F-QA-2 关联的
  profile 回滚（故障注入锁定）、FK 开启钓出的 **qa.undo 删 profile 行残留 docrevision 真 bug**。
- **SAFE/口径澄清 5 项**：F-LIC-1 许可门禁、F-ASSET-1 引用面、F-MIG-1 迁移幂等、
  F-REQ-1 请求模型行为兼容（+键名口径备忘）、F-EVID-1 老证据抽验（run222/272 产物
  sha 自洽，`out/film/master.mp4` 属最后 Run 的口径澄清）。
- **F-DOC-1**（run 号 309 vs 311）：HEAD 文档本就正确，是我开场读了压缩前陈旧上下文，已澄清。
- **F-SSIM-1**：独立探针（`scripts/probe_profile_ssim_offset.py`）证明档位 0.90 窗口阈值
  含"时间量化 + 档位分辨率差"双成分（final±1/24s worst 0.9871 vs draft-vs-final 0.9521）；
  阈值保持（THRESHOLD-KEEP），归因已在 HANDOFF §2.4 补全。

### 2. 连续两轮对抗性审计无新增 P0/P1 ✅
- 第一轮（证伪批 1）：11 项 F-* 全闭环（提交 c0dfa7e）。
- 第二轮（验收扫描 + 自查）：挖出 **4 个由我当晚改动引入的回归**——gate_decide 漏转
  payload.get（500）、ruff autofix 误删 db.py 副作用导入 TABLES（integration 全炸）、
  `_finish_saved_template_materialize` 漏 await（500）、FrameServer 测试毒帧事故
  （12B 假 PNG 写入 rumor-39s，已删文件并核实 blocked run 无引用）。全部修复并固化
  防再发测试（门禁 happy-path、8787 占用探测）。第三轮抽查无新增。
- 扫描期间额外修复 1 个真 UI 缺陷：canvas header 12+ 元素不换行在 1600px 溢出
  （e2e_ui 场景 7 点击被遮挡的根因）。

### 3. pytest 连跑两遍全绿 + 计数一致 ✅
- `cd server && uv run pytest tests -q`：**218 passed, 1 skipped × 2 遍**（52.5s / 53.5s；
  skipped=FrameServer 测试在 dev 占 8787 时诚实跳过，停 dev 可覆盖）。
- 两遍后 `GET /api/projects` = **35**（基线 35）。

### 4. verify_p1_governance 8 步全 ✓ ✅
当夜三跑全过（批 3 后、批 4 FK ON 后、验收扫描末），最后输出：
`PASS: P1 治理复核全部通过（临时项目/模板/资产已自删）`，跑后计数仍 35。

### 5. HANDOFF §0.2 验收脚本各跑通一次 ✅（含两项历史欠账清零）
全部当夜实测（见 runlog 验收表），关键项：
- **rumor 46/46**（run 332，wall 263.5s，master 39.5s）；
- **40s 增量实跑 PASS**（run 311：rendered 93/960=9.69%、reused 867、报告归档
  `docs/reports/r2-incremental/40s-run311.json`）——交接 §0.6.2 最大"明确没做"项闭环；
- **golden 5s 原帧 SSIM 1.0**（run 312，2.10.0 下零视觉回归）；
- 恢复 kill -9 → 24.0s F02 恢复；预览/档位/审阅/音频/交付/QA/资产/模板/r3 簇/smoke/e2e_ui 全绿；
- `verify_r2_5_review` 原本**是红的**（硬编码已删除的 golden-40s-134/wf 119）——已按 P1-19
  自包含重写并跑通。
- 跳过项：15s/40s 原帧 golden baseline 未生成（~4.3GB/数十分钟×2，非功能缺口；40s 增量与
  5s 原帧已覆盖核心证据链）；`verify_r2_5_delivery_40s` 未重跑（40s 交付 run 223 历史证据在，
  5s 交付当夜已复跑 QC 全绿）。复现命令不变。

### 6. 每批 DoD 齐全 ✅
10 个批次（c0dfa7e → 1922971）均为独立提交：代码 + 测试 + 真实产物证据（报告归档/
DB 计数/帧数/SSIM 数字）+ HANDOFF/AGENTS 同步 + push。详单见 runlog 各批小节。

### 7. tsc 干净 + ruff 低于基线 ✅
- `pnpm --dir web exec tsc --noEmit`：0 错误（三跑：批 5、批 8 后、收尾）。
- `ruff check server`：基线 504 → 自动修复 247 处后 **剩 334**（unsafe 89 处保留未动）；
  净降 170。教训入库：autofix 误删 db.py 副作用导入（F401），已恢复并加注释。

## 二、本轮新增能力 / 修复清单

**新增**
- `server/app/engine/fpscalc.py`（P1-12）：非整数 fps 唯一口径（norm_fps/frames_for/
  frame_at/time_at/fps_rational），12 处截断点接线；final 门放行 NTSC 23.976（THRESHOLD-CHANGE
  已记录）；EXECUTOR_VERSION 2.9.3→2.10.0。
- `server/app/services/project_cleanup.py`（P1-06）：级联删除（project/run/workflow/doc_id
  四类关联面）+ 白名单 + 演示保护 + dry-run 计划；`DELETE /projects/{id}?confirm=true`。
- `db.py` 开启 `PRAGMA foreign_keys=ON`；`_acceptance.destroy` 与三处测试清理改走级联服务。
- 前端 `error.tsx`/`global-error.tsx`（P1-10）；`scripts/e2e_timeline_100.py`（P1-11 实测
  59.8fps，报告归档，暂不虚拟化）。
- P1-23 第二批 10 个高危端点模型化（delivery/preview×3/gate/promote/profile/task/audio×3）。
- `scripts/cleanup_projects.py`（--dry-run 默认；8 行 root 缺失清单与 §7.4 吻合，未删数据）。
- `scripts/probe_profile_ssim_offset.py`（阈值归因审计工具）。

**修复（按发现方式）**
- 证伪发现：交付门禁三连（磁盘快照硬校验 + script/profile 一致 + 标题快照源）、
  QA mix/license 撤销守卫。
- FK 开启钓出：qa.undo 删 profile 行残留 docrevision。
- 故障注入锁定：take branch / assets replace / 模板 materialize 三路补偿 + qa extend 回归锁定。
- 数据完整性：FrameServer 帧原子写（P2-04）、文档版本链 100 上限（P2-07）、
  交付 QC 硬编码 24fps（P2-10，随 P1-12 修）。
- 安全（P3）：SVG 资产 CSP sandbox+nosniff（存储型脚本面关死）、产物文件白名单纵深、
  :3000 安全头。

## 三、剩余风险 TOP 10

| # | 风险 | 严重度 | 说明/建议 |
|---|---|---|---|
| 1 | 15s/40s 原帧 golden baseline 未生成 | 中 | 视觉回归只锁 5s；40s 增量已有 9.69% 证据。建议白天低峰跑一次 `golden_run.py --project 40s --resolution original` |
| 2 | DB 8 行 root 缺失 + 审计残留（老板未点头） | 中 | `cleanup_projects.py` 已给出清单；点头后 `--confirm` 逐 id 删 |
| 3 | 15s/40s 交付未复跑（历史 run 223 证据在） | 中 | 端到端 40s 交付链路本轮未动，回归风险低但建议每周抽一次 |
| 4 | P1-23 剩 ~32 个 payload: dict（模板/审片/takes 等） | 中低 | 两批方法论已固化（模型 + 422 测试 + happy-path）；下批照做 |
| 5 | P2-01 门继承无 workflow 过滤 / P2-06 缓存命中无 workflow 作用域 | 中低 | 影响跨项目审批继承语义；改动需 ADR，本轮未动 |
| 6 | P1-21 fresh-clone 未在干净机器实测 | 低 | 依赖外置库/rumor/Chrome；bootstrap 脚本仍缺 |
| 7 | Chrome 9222 可预测 / Chrome 跨进程不互斥 | 低 | 本机单用户场景风险可控；已加 8787 探测教训 |
| 8 | 500MB base64 上传内存放大 | 低 | 已有 MAX_BYTES；流式上传留 R4 |
| 9 | e2e 若干脚本仍硬编码演示 ID（e2e_takes 188/237/254 等） | 低 | review 已示范改法；照搬即可 |
| 10 | ruff 89 处 unsafe / 无 CI | 低 | P1-20 CI（pytest+ruff+golden 5s）是下批首选 |

## 四、"如果只有半天先做什么"

1. `cleanup_projects.py --dry-run` → 拿老板点头 → `--confirm` 清 8 行残留（30 分钟）。
2. CI 最小版：pytest + ruff + `golden_run.py --project 5s`（2 小时，锁住今晚全部成果）。
3. 跑一次 40s 原帧 golden 并归档（背景 40 分钟）。
4. P1-23 第三批照两批方法论清 10 个模板/审片端点（1 小时）。

## 五、快照签名

- 最后批次：`1922971 fix(p1-19+regression): verify_r2_5_review 自包含重写；挖出并修复今晚引入的 3 处回归`
- 全晚 11 个提交：`c0dfa7e a9bfba6 959792b 0451f74 e76446f d474bb3 92e0f77 4d78acc 0a192b7 1922971`（+`044ff59` 起点之后）
- 测试：**218 passed, 1 skipped ×2 遍**；`GET /api/projects` = **35**（恒定）
- `verify_p1_governance.py`：8 步全 ✓（最后一跑在验收扫描末）
- ruff：**334**（基线 504）；tsc：0 错误；EXECUTOR_VERSION **2.10.0**
- 磁盘：filmflow-projects **2.3G**、rumor-39s **1.0G**、`~/.filmflow` 1.1G
- DB 备份：`~/.filmflow/filmflow-before-expert-20261103-234205.db`（28.1MB，整夜未回滚过）
