# FilmFlow PRD v2.0 — 专业视频生产机器（补充需求）

| 项 | 内容 |
|---|---|
| 文档版本 | v2.0（2026-11-02） |
| 状态 | **待老板裁决 D1–D6**；裁决后即冻结为本期开发基线 |
| 文档性质 | **增量 PRD**。v1（`../filmflow-prd.md`，FR-1~14 / US-01~10）继续有效；本文只定义 v2 新增与变更，不重写已交付部分 |
| 上游文件 | 规格 `../../filmflow-web-agent-prompt.md`（§19 裁决与 ADR 仍是宪法）· 交接文档 `../../HANDOFF.md`（§9 硬缺口） |
| 适用范围 | R2「能出片」→ R3「好创作」→ R4「能批量」 |
| 不变约束 | 仅本机 `127.0.0.1`；不上传文件；**不调用任何在线生成模型**；Chrome 全局串行；确定性时间轴；46 节点 / 7 阶段 / 8+8 门 |

---

## 0. 阅读指引

- **老板/产品**：读 §1、§2.1、§5、§12、§13.1。§13.1 是需要您拍板的 6 个决策。
- **开发 Agent**：读 §2.2、§4、§6、§7、§8、§9、§10、§11。§8 是可直接开工的子系统规格。
- **验收/测试**：读 §5、§7 每条的「验收」、§12.4、§14.5。
- **术语**：场景（scene）= 一段有独立画面语义与时间范围的内容；镜头（shot）= 场景内的一个连续取景；模板（template）= 可复用的场景/项目骨架；变体（variant）= 同一时间轴的不同画幅/平台交付。

---

## 1. 执行摘要

### 1.1 一句话

FilmFlow v1 是一台**可靠的印厂机器**：它能把一部已知影片的 46 道工序跑对、跑稳、跑可追溯。  
FilmFlow v2 要把它变成一台**专业的视频生产机器**：让创作者每天都能用**自己的文案**，在**分钟级**做出**可审、可改、可交付**的片子。

### 1.2 现在是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 46 节点真实执行引擎（run #1：46/46 succeeded） | 新项目出片工具（新项目仍渲染参考片内容） |
| 可靠的审批/失效/缓存/续跑底座 | 创作工具（没有时间轴、没有逐帧审片、没有音频工作台） |
| 341 条风格的真实索引与预演 | 可规模生产的内容系统（61/341 可生产，photo 157 条无引擎） |
| 单部 39.5s 片的完整证据链 | 日产/批量/多平台交付的生产线 |

### 1.3 五个结构性缺口（不是功能清单，是架构判断）

1. **内容与渲染没有分离**：`D02` 用 `entry.still`、`E05/F02` 用 `entry.film`，这两个入口是 rumor-39s 的原版 harness，画面内容写死；参数化的 `entry/still_spec.html` 存在但**没有任何执行器调用**，`film_spec.html` 根本不存在。→ 新项目选任何风格，预演是对的，D02/F02 仍会渲染参考片的字与镜头。
2. **创作单位与执行单位错位**：最小可执行单位是「整部片」的节点。改一句文案 → B/C/D/E/F 全链重跑，实测 25–40 分钟；没有「当前场景/当前句」的热预览。
3. **文档不是一等公民**：`card/task.json` 被编辑器直接写、被 B02/B03/B06/D01/E01 直接读，却**不在缓存键里**；同一份文件还有 B06 这个第二写入者。结果是「改了任务卡，Run 可能仍用旧缓存」，以及无法回答「这一版和上一版差在哪」。
4. **反馈链路太长且不可视**：没有项目级预览 API；D02 一次只为前 3 个场景出静帧（`pipeline.py:185`）；没有时间轴、没有逐帧批注、没有 A/B 对比；审片只能点「通过/驳回」。
5. **交付是附属品**：G07 只封装一个 1920×1080 的 master.mp4；没有 9:16/1:1、没有字幕、没有封面、没有平台检查、没有交付包；G05 的「闪避」是固定 −12dB，G06 的「音画同步偏差」是伪计算（`pipeline.py:649/692`）。

### 1.4 v2 的核心命题

> **场景是创作的单位，文档是修改的单位，预览是反馈的单位，成片只是批处理的结果。**

由此推导出四条设计主线：

1. **两级执行**：46 节点影片级 DAG 不变；节点内部新增「场景微流水线」（编译 → 静帧 → 帧段 → QA → 片段编码），缓存与续跑下沉到场景/帧。
2. **文档中心**：`script.doc` / `timeline.doc` / `scene.program` 成为唯一事实源，带版本、可 diff、可回滚；`task.json` 降级为校验器兼容导出。
3. **预览优先**：单帧 p50 ≤2s、5 秒片段 ≤20s；预览走独立高优先级通道，不排在大批渲染后面。
4. **交付矩阵**：一条时间轴 → 多画幅/多平台/多语言变体；每个变体独立 QC、独立封面、独立字幕、独立打包。

### 1.5 预期收益（R2.5 结束时：能出片 + 能审能交）

| 任务 | 现在 | R2 目标 |
|---|---|---|
| 新建 5 秒片 | 出的是参考片内容 | 出用户自己的文案 |
| 40 秒片初剪（有画面有声音） | 25–40 分钟且门门手动 | ≤8 分钟 draft，自动过自动门 |
| 改一句文案后看到画面 | 全链 25–40 分钟 | 单帧 ≤2s；脏场景 draft ≤3 分钟 |
| 审片意见 | 只有「驳回」+ 一段文字 | 时间码批注、逐帧、可导出 |
| 交付 | 1 个 mp4 | 1080p + 9:16 + SRT + 封面 + zip + QC 报告 |
| 崩溃恢复 | 手工清 Chrome、手动续跑 | 重启 ≤60s 自动恢复 |

---

## 2. 现状诊断（证据优先）

### 2.1 证据链

| # | 症状 | 代码证据 | 根因 | 后果 |
|---|---|---|---|---|
| 1 | 新项目渲染参考片内容 | `pipeline.py:201`（D02 用 `entry.still`）、`:316`（E05 用 `entry.film`）、`:420`（F02 用 `entry.film`）；`engines/riso/contract.json` 的 `still/film` 指向 rumor 原版 | 引擎入口未版本化，参数化入口未接线 | 新项目不可用；这是 P0 中的 P0 |
| 2 | 参数化静帧从未被调用 | `entry/still_spec.html` 仅被 contract 引用；`grep still_spec server/` 只有 D01 写 spec，无执行器消费 | D01 产物没有进入渲染 URL | 参数化能力等于零 |
| 3 | 静帧只覆盖前 3 场 | `pipeline.py:185` `scenes[:3]` | D01 默认值写死 | D05 批准的是 3/5 个场景，不是整片 |
| 4 | 改任务卡可能不生效 | `__init__.py:217/241/282` 直接读 `card/task.json`；`routes.py:813` 直接写；`runengine.py` 的上游哈希只含上游产物，不含 task.json | 文件是侧信道，未进内容哈希 | 缓存命中旧内容；「改了没变」不可解释 |
| 5 | 任务卡有两个写入者 | 编辑器 PUT 写 task.json；B06 也写 task.json | 没有文档所有权 | 互相覆盖，无版本、无冲突检测 |
| 6 | 相机是假的 | `e02` 固定线性 `zoom [[start,1.0],[end,1.03]]` | 没有相机关键帧模型 | `camera` 文本不生效，运镜千篇一律 |
| 7 | 转场是假的 | `e04` 默认 `shape_match` | 没有转场库/参数 | 接缝靠默认值，无法创作 |
| 8 | 闪避是固定值 | `pipeline.py:649` `duck = 10**(-12/20)` | 没有 sidechain/自动化曲线 | 音乐该让的地方不让，不该让的地方一直小 |
| 9 | 音画同步 QA 是伪计算 | `pipeline.py:692` `min(abs(s["start"] - 0))` | 没有把 alignment 与事件/场景对齐比较 | 恒为 0，永远通过 |
| 10 | 交付只有单规格 | `pipeline.py:697` G07 只 mux master.mp4 | 没有 delivery 模型 | 不能发抖音/小红书/YouTube Shorts |
| 11 | 没有可恢复队列 | `models.py:171` `Job` 只有模型，全仓无写入；`runengine.py:384` 进程内 `gather` | 队列是内存态 | 重启/崩溃后队列丢失，Chrome 残留 |
| 12 | 没有项目级预览 | `routes.py` 只有 `/styles/{id}/preview`（风格预演），无项目场景预览 | 预览不是一等能力 | 每次看效果都要跑节点 |
| 13 | 编辑器无版本/撤销/自动保存 | `web/src/app/editor/page.tsx` 直接 PUT；无 base_version | 文档模型缺失 | 误改不可恢复；刷新丢编辑 |
| 14 | 监控只有表格 | `web/src/app/monitor/page.tsx`（54 行） | 没有时序/指标可视化 | 无法定位慢在哪、为什么慢 |
| 15 | 可生产覆盖低 | 61/341；photo 族 157 条无引擎 | 引擎扩容未排期 | 大部分风格只能看不能用 |
| 16 | **E04 转场是死端** | `edges.py` 中 E04 只有入边、**出边为空**；`transitions.json` 从未被 E05/F02 读取 | 边表缺 E04→E05/F02 | 「接缝匹配」只是产出一个无人消费的 JSON；F02 不知道转场 |
| 17 | **排版规格未进 tokens.lock** | `__init__.py:442` C05 只锁 A06/B04；B05 `type_spec` 不在 C05 上游 | 字号/行高/字重变化不失效 C05→D01/E03 | 改了排版，静帧/分镜可能仍用旧锁 |

### 2.2 七个架构判断

**判断 1：一级 DAG 的粒度没错，错在只有一级。**  
46 节点表达「一部片的工序」是对的，必须保留；但它不适合表达「一个场景的迭代」。v2 增加**场景微流水线**（scene pipeline），作为 D02/E05/F02 的内部编排，不新增 DAG 节点。这样既不动已稳定的调度/门/缓存内核，又拿到场景级并发、缓存与续跑。

**判断 2：文件不是文档。**  
`task.json` 现在同时是「编辑器草稿」「B06 产物」「validator 输入」「运行时输入」。v2 把它拆成：`script.doc`（文案结构）、`timeline.doc`（场景/轨道/关键帧）、`scene.program`（可渲染程序）；`task.json` 只作为**导出快照**给 vendored validator 与旧项目兼容。所有文档带 `version / base_version / hash`，写入走乐观并发。

**判断 3：Engine Contract 只到「入口 URL」，不够。**  
v1 的 contract 能回答「用哪个 html」，不能回答「支持哪些元素/转场/文字动画/限制」。v2 的 contract 要暴露 **scene schema + capabilities + limits + fixtures**；引擎从「一个页面」升级为「一个可校验的渲染器」。

**判断 4：缓存粒度必须等于创作粒度。**  
节点级缓存适合「整片复现」，不适合「改一句看一句」。v2 的缓存键下沉到 `scene_hash = sha256(program + tokens.lock + engine_sha + font_sha + profile + renderer_version)`；F02 用 `render_manifest` 只重渲脏场景及其转场重叠帧。节点级缓存保留，作为第二层。

**判断 5：预览不能是节点。**  
预览要求「快、可取消、可抢占、不进审批」，而节点要求「可审计、可缓存、可阻断」。两者生命周期不同。v2 增加独立 Preview Service：高优先级、独立缓存、独立并发预算、绝不写入 final 产物。

**判断 6：交付不是最后一步，是另一条流水线。**  
一条时间轴要产出多个变体；变体不是「裁一下」，而是**重新布局**（安全区、字号、构图、转场）。v2 把 Delivery 建模为「variant matrix + 每变体 QC + 打包」，G07 变成编排者，不是唯一执行者。

**判断 7：生产力 = 可恢复 + 可观测 + 可度量。**  
专业机器不是按钮多，而是：崩了能续、慢了知道慢在哪、错了知道改哪里、交付前知道会不会被平台拒。v2 的队列、场景状态、运行报告、修复建议都服务这件事。

### 2.3 不做什么（防止把底座推倒）

- 不重写 RunEngine 的 caps / 门 / 三类边 / content_hash / 断点续跑。
- 不改变 46 节点 / 7 阶段 / 8+8 门的计数与语义（D2 裁决）。
- 不引入云端、账号、多租户、在线生成模型。
- 不做通用 NLE（任意视频剪辑/特效合成）；时间轴只编辑本 DSL 的场景与图层。
- 不把引擎逻辑搬进 App；引擎仍是 vendored 包，App 只编排与校验。

---

## 3. 用户与场景

### 3.1 三类用户

| 角色 | 目标 | 痛点 | v2 必须给什么 |
|---|---|---|---|
| **导演/创作者**（主） | 把文案变成有风格的片；快速试错 | 改一句要等半小时；运镜/转场不可控；不知道字体/版式会不会崩 | 秒级预览、时间轴、镜头语言、修复建议 |
| **制片/运营**（次） | 一条内容多平台发；批量做系列 | 每次只能出 16:9；没有字幕/封面；不能批量 | 交付矩阵、字幕、封面、模板、批量 |
| **审片人/客户**（外） | 在片子上直接提意见 | 只能看 mp4，意见靠微信语音 | 时间码批注、审片包、逐帧对比 |

> 约束：审片人仍是**本机或离线审片包**，不做云端协作、不做账号体系。

### 3.2 一个真实工作日的对比

**现在**：09:30 写文案 → 10:00 走向导 → 10:30 发现 D02 出的是参考片 → 11:00 手工改 harness → 13:00 渲染 → 14:00 发现一句文案要改 → 14:01 全链重跑 → 15:30 出片 → 16:00 客户说「竖屏版呢」→ 没有。

**v2**：09:30 写文案 → 09:35 选风格（用**自己的标题**预演）→ 09:40 时间轴初剪 → 09:50 单帧预览逐场调 → 10:10 draft 初剪（带临时配音/音乐）→ 10:30 审片批注 8 条 → 10:50 改 3 场，脏场景重渲 → 11:10 final → 11:20 交付 16:9 + 9:16 + 字幕 + 封面 → 11:30 发。

### 3.3 Jobs-to-be-done

| JTBD | 成功标准 |
|---|---|
| 把一段文案变成「能看」的初剪 | 30 秒片 ≤20 分钟（含一次审片） |
| 改一句，立刻看 | 单帧 ≤2s；脏场景 draft ≤3 分钟 |
| 让运镜/转场服务叙事 | 相机关键帧 + 转场库可编辑、可预览 |
| 在片子上直接提意见 | 时间码 + 帧号 + 图层，批注可导出/回灌 |
| 一次做多平台 | 一条时间轴出 3 个变体，全部过平台检查 |
| 做系列/批量 | 模板 + 文案数组 → N 条排队 → 批量导出 |
| 崩了不丢工作 | 重启 ≤60s 恢复；文档版本可回滚 |

### 3.4 易用性硬要求（UX）

| # | 规则 | 验收 |
|---|---|---|
| UX-1 | 每个页面只有一个主行动，其余次要 | 首页/Studio/Delivery 各 1 个 primary 按钮 |
| UX-2 | 任何 >3s 的操作后台化 + 进度 + 可取消 | 预览/渲染/导出不冻结 UI |
| UX-3 | 破坏性操作可撤销或二次确认 | 删除场景/资产/项目/版本 |
| UX-4 | 错误 = 原因 + 定位 + 修复动作 | 100% 失败有 `fix_hint` |
| UX-5 | 默认值可用；高级参数渐进展开 | 新用户不改参数也能出片 |
| UX-6 | 键盘全路径 + 命令面板 | 核心流程可无鼠标完成 |
| UX-7 | 反馈延迟：点击 <100ms、保存 <1s、>1s 显示进度 | 前端埋点 |
| UX-8 | 预览始终可用；预览不阻塞编辑 | 预览按钮不因批渲染置灰 |
| UX-9 | 空状态/首次引导/模板，不给空白画布 | 首日 10 分钟出片 |
| UX-10 | 诚实标注：`preview`/`manual`/`approximate`/`no_preview` | 不伪装能力 |

---

## 4. 产品原则 v2（12 条，防回退）

1. **场景是创作单位**：任何编辑、预览、缓存、审批、批注，都能落到 `sceneId`。不能落到场景的功能，不做。
2. **预览优先**：每个编辑动作必须有 ≤2s 的静帧反馈或 ≤20s 的片段反馈；预览失败必须给可行动的修复建议。
3. **文档即输入**：运行时只读 Run 快照；禁止执行器直接读可编辑文档；派生产物（`scenes/`/`renders/`/`deliveries/`）可写项目根，但必须由快照生成；`task.json` 不再作为新项目的运行时事实源。
4. **内容与渲染分离**：引擎包不得包含项目文案/场景；项目文档不得包含引擎实现。DSL 是唯一契约。
5. **确定性**：同一 `document_hash + engine_sha + font_sha + profile + toolchain` → 同一帧哈希；禁止 `Date.now()` / 无种子随机进入画面。
6. **非破坏性**：编辑可撤销、版本可回滚、Take 不删除；任何「重跑」不覆盖已批准产物，除非显式提升。
7. **局部失效**：只重算脏场景与受影响转场；禁止「改一个字重渲整片」。
8. **失败可行动**：每个错误必须有 `code / cause / fix / retry`；UI 给「一键修复」或「跳转到字段」。
9. **本地优先**：不上传、不联网渲染、不调用在线模型；唯一网络例外是字体/whisper 模型首次获取（可离线指定路径）。
10. **可交付才算完成**：DoD 包含「过 QC、有字幕/封面、有 manifest/rights、可复现」。
11. **底座不动**：46 节点、caps、门、三类边、content_hash 语义不变；扩展走子流水线/参数/新产物。
12. **诚实**：没有实现的能力不伪装；`no_preview`、`approximate`、`manual` 必须显式标注。

---

## 5. 目标与成功指标

### 5.1 北极星指标

> **30 秒新片，从文案到「可审初剪」（有画面、有声音、可批注）≤20 分钟；单场景修改到看到新画面 ≤3 分钟（R2）/ ≤60 秒（R3）。**

### 5.2 指标表（基线来自 run #1 与当前代码）

| 指标 | 当前基线 | R2 目标 | R3 目标 | 测量方式 |
|---|---|---|---|---|
| 新项目能否出自己的片 | ❌（渲染参考片） | ✅ | ✅ | 黄金项目 5s / 15s / 40s |
| 30s 片 TTFW（到可审初剪） | 不存在 | ≤20 min | ≤12 min | 从 materialize 到 draft+audio 可播 |
| 40s 片 draft 渲染 | 不存在（只能跑 final） | ≤8 min | ≤6 min | PreviewService `/preview/film` |
| 40s 片 final 渲染 | 25–40 min | ≤30 min | ≤22 min | F02 profile=final |
| 单帧预览延迟 | 分钟级（跑节点） | p50 ≤2s / p95 ≤6s | p50 ≤1s / p95 ≤3s | Preview Service 埋点 |
| 5s 片段预览 | 不存在 | ≤20s | ≤10s | preview/segment |
| 改一句 → 看到新 draft | 25–40 min | ≤3 min | ≤60s | 脏场景重渲 + draft |
| 迭代缓存命中率 | 0–20% | ≥60% | ≥80% | scene_hash 命中 / 总场景 |
| 崩溃恢复 | 手工 | ≤60s | ≤30s | kill -9 后重启 |
| 交付变体数 | 1 | 3 | 5+ | delivery manifest |
| QA 误报率 | 高（重复帧曾 28.8%） | <10% | <5% | 人工抽检 50 条 |
| 可生产风格 | 61/341 | 61/341（先把链路跑对） | 61/341（R4.0 起 218/341，photo 引擎） | style-index 统计 |
| 门驳回后的返工闭环 | 天级 | ≤2h | ≤30min | 批注→修改→重审 |

### 5.3 质量指标

- **确定性**：同一文档跑两次，全部帧 sha 一致率 100%（Chrome/字体/引擎锁定）。
- **恢复性**：任意节点 `kill -9` 后重启，Run 在 60s 内回到可继续状态；无孤儿 Chrome。
- **可解释**：100% 的失败节点有 `error_code` 与 `fix_hint`；100% 的缓存命中可在 UI 看到键组成。
- **交付**：3 个变体全部通过平台检查（时长/分辨率/fps/码率/LUFS/TP/字幕/封面）。
- **回归**：rumor-39s 仍 46/46 succeeded；黄金帧 SSIM ≥0.98。

---

## 6. 领域模型 v2

### 6.1 两级执行模型

```
┌──────────────────────────────────────────────────────────────────┐
│ Film Run（46 节点，不变）                                          │
│  A 立项 → B 任务卡 → C 资产 → D 静帧 → E 分镜 → F 渲染 → G 交付      │
│                                                                  │
│  D02 / E05 / F02 内部：                                           │
│  D01 编译 base program → D02 静帧（entry.still_spec）              │
│  E03 合并相机 → E04 转场 → E05/F02 逐帧（entry.film_spec 合成）    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Scene Pipeline（每场景，虚拟节点，SceneState 表跟踪）          │  │
│  │  compile(base) → still → compile(motion) → frames(range)    │  │
│  │  → scene QA → segment encode → merge                         │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

- **场景微流水线不是 DAG 节点**：不增加 46 的计数，不参与 caps/门；由执行器内部调度。
- **SceneState** 记录每个场景的 hash/状态/帧范围/耗时/QA；F02 的进度与续跑以它为准。
- **失败隔离**：一个场景失败不影响其他场景渲染；F02 在 `fail_fast=false` 时先渲完可渲的，再汇总失败场景。

### 6.2 新增/变更的数据对象

| 对象 | 生产者 | 消费者 | 说明 |
|---|---|---|---|
| `script.doc.json` | A01 / 编辑器 | B01/B02/E01 | 文案结构：段落、句子、停顿、重音、读音、source_span；带 version |
| `timeline.doc.json` | B02/B03/E01 / 编辑器 | B06/D01/E01/E03 | 轨道/场景块/事件/markers；v2 唯一时间轴事实源 |
| `scene.program.json`（每场景） | D01（base）/ E03（camera） | D02/E05/F02 | Scene DSL v1，可直接渲染；base 与 motion 两版共享同一编译器，带 `scene_hash` |
| `transitions.json` | E04 | E05/F02 | 相邻场景的转场类型/时长/方向/参数；**v2 补出边后才真正被消费** |
| `render.profile.json` | 设置/预设 | D02/E05/F02/F03/F05 | draft / review / final 的画幅、fps、质量、QA 阈值 |
| `render.manifest.json` | F02 | F03/F04/G07 | 场景→帧范围→hash→状态；增量渲染与复用的唯一依据 |
| `delivery.spec.json` | G07/交付页 | G07/Delivery | 变体矩阵：画幅、平台、字幕、封面、码率、响度 |
| `review.json` | 审片页 | 编辑器/G07 | 批注、决议、时间码、图层、状态 |
| `asset`（表） | 资产库 | 时间轴/引擎 | 图片/音频/字体/视频；sha、标签、许可、使用处 |
| `project.lock.json` | F02/G07 | 复现 | 引擎/字体/Chrome/ffmpeg/Python/Node 版本与 sha |
| `task.json` | B06（导出） | vendor validator / 旧项目 | **只读快照**，不再被编辑器直接写 |

### 6.3 Scene DSL v1（示例）

```json
{
  "schema": "filmflow.scene/1",
  "id": "S03",
  "duration": 8.0,
  "canvas": { "w": 1920, "h": 1080, "fps": 24, "background": "paper" },
  "camera": {
    "anchor": [960, 540],
    "keyframes": [
      { "t": 0.0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0, "ease": "linear" },
      { "t": 6.0, "zoom": 1.08, "x": -40, "y": 0, "rotate": 0, "ease": "easeInOut" }
    ]
  },
  "layers": [
    {
      "id": "L_title", "type": "text", "z": 10,
      "content": "停下来",
      "style": { "font": "Noto Sans SC", "weight": 900, "size": 148,
                 "lineHeight": 1.1, "letterSpacing": 2, "color": "#F4EEE2",
                 "align": "center", "maxWidth": 1200 },
      "box": [360, 420, 1200, 260],
      "reveal": { "type": "mask-reveal", "at": 1.2, "duration": 0.8, "ease": "easeOut" },
      "in": { "at": 0.0, "type": "cut" },
      "out": { "at": 7.4, "type": "fade", "duration": 0.4 }
    },
    {
      "id": "L_cards", "type": "component", "z": 5,
      "component": "scene-kit/evidence-card",
      "props": { "count": 5, "stagger": 0.55, "paper": "#F4EEE2", "ink": "#3D5588" }
    }
  ],
  "transitions": {
    "in": { "type": "cut" },
    "out": { "type": "shape-match", "to": "S04", "duration": 0.5 }
  },
  "audioCues": [
    { "at": 1.2, "role": "knockout_reveal", "allowSnap": false }
  ],
  "meta": { "operation": "纸白镂空‘停下来’；五张证据卡逐张落版", "author": "local" }
}
```

**图层类型（v1）**：`text` · `shape` · `image` · `group` · `component`。  
**组件库（v1，12 个）**：`paper-card` · `headline` · `body-block` · `stamp` · `arrow-grow` · `hand-pointer` · `roller` · `halftone-field` · `registration-cross` · `evidence-card` · `chart-bar` · `count-up`。  
**转场（v1，8 个）**：`cut` · `match-shape` · `paper-slide` · `wipe` · `dissolve` · `ink-bleed` · `glitch` · `push`。  
**缓动**：`linear` · `easeIn` · `easeOut` · `easeInOut` · `cubic-bezier(...)` · `steps(n)`。  
**硬限制**：无任意 JS、无网络请求、无 `Date.now()`；随机必须带 `seed`；单场景 ≤200 图层、≤2000 字；所有图片/字体按 sha 引用。

### 6.4 Timeline Doc v2（示例）

```json
{
  "schema": "filmflow.timeline/2",
  "fps": 24, "duration": 39.5, "frames": 948,
  "tracks": [
    { "id": "V1", "type": "video", "clips": [
      { "sceneId": "S01", "start": 0.0, "end": 9.0, "program": "scenes/S01.program.json" },
      { "sceneId": "S02", "start": 9.0, "end": 16.0, "program": "scenes/S02.program.json" }
    ]},
    { "id": "A1", "type": "audio.voice", "clips": [
      { "asset": "asset:voice-take-2", "start": 0.0, "gainDb": 0, "fadeIn": 0.1 }
    ]},
    { "id": "A2", "type": "audio.music", "clips": [
      { "asset": "asset:music-bed-1", "start": 0.0, "gainDb": -12,
        "ducking": { "source": "A1", "depthDb": -8, "attack": 0.08, "release": 0.35 } }
    ]},
    { "id": "M1", "type": "markers", "events": [
      { "id": "E12", "sceneId": "S03", "at": 17.8, "role": "knockout_reveal" }
    ]}
  ],
  "layout": { "safeArea": { "w": 0.05, "h": 0.08 }, "grid": { "cols": 12 } }
}
```

### 6.5 Render Manifest（增量渲染）

```json
{
  "schema": "filmflow.render/1",
  "profile": "draft", "fps": 12, "frames": 474,
  "scenes": [
    { "id": "S01", "hash": "a1b2…", "range": [0, 108], "status": "done", "ms": 18300 },
    { "id": "S02", "hash": "c3d4…", "range": [108, 192], "status": "dirty", "ms": 0 }
  ],
  "transitionOverlap": 6,
  "reusedFrames": 312,
  "renderedFrames": 162
}
```

> 示例仅列 2 场；实际 manifest 覆盖时间轴全部场景，`frames` 为 profile 下的总帧数。

### 6.6 兼容与迁移

- **已导入项目**（`meta.imported=true`，如 rumor-39s）：保留 v1 harness，读 `legacy_entry.still/film`；`task.json` 仍是运行时输入；黄金回归必须仍 46/46。
- **新项目**：强制 `engine_api=2` + `still_spec/film_spec`；`timeline.doc` 是事实源；`task.json` 由 B06 导出为只读快照。
- **task.json → timeline.doc**：一次性迁移器（场景/事件/相机文本 → 轨道 + 默认 program）；迁移后 `task.json` 只读。
- **旧 Run**：不迁移；只读可查；新 Run 用新模型。

---

## 7. 功能需求

### 7.1 需求总表

| ID | 需求 | 优先级 | 发布 | 一句话 |
|---|---|---|---|---|
| FR-20 | 参数化渲染链 | P0 | R2.0 | 让新项目渲染用户内容 |
| FR-21 | 场景组件库 v1 | P0 | R2.0 | 12 个可组合镜头组件 |
| FR-22 | 场景级增量渲染 | P0 | R2.0 | 只重渲脏场景与转场 |
| FR-23 | 快速预览服务 | P0 | R2.0 | 单帧 ≤2s、片段 ≤20s |
| FR-24 | 渲染档位 draft/review/final | P0 | R2.0 | 同一时间轴三种质量 |
| FR-25 | 文档版本化与安全编辑 | P0 | R2.0 | 自动保存/撤销/版本/diff |
| FR-26 | 全场景静帧与关键帧审阅 | P0 | R2.5 | D01 覆盖全部场景 |
| FR-27 | 音频工作台 v1 | P0 | R2.5 | 录音/波形/对齐/闪避 |
| FR-28 | 交付 v1 | P0 | R2.5 | 1080p+字幕+封面+zip+QC |
| FR-29 | 渲染队列与崩溃恢复 | P0 | R2.0 | 可恢复、可抢占、可观测 |
| FR-30 | 黄金项目与视觉回归 | P0 | R2.0 | 5s/15s/40s 自动验收 |
| FR-31 | 新手引导与示例项目 | P1 | R2.5 | 10 分钟做出第一条片 |
| FR-32 | 时间轴编辑器 | P1 | R3.0 | 轨道/拖拽/吸附/波纹 |
| FR-33 | 审片播放器与批注 | P1 | R3.0 | 时间码批注/导出/回灌 |
| FR-34 | 镜头语言编辑器 | P1 | R3.0 | 相机关键帧/转场库 |
| FR-35 | 音频工作台 v2 | P1 | R3.0 | 多 Take/降噪/拍点/Stems |
| FR-36 | 资产库 | P1 | R3.0 | 图片/音频/字体/视频 |
| FR-37 | 模板与系列 | P1 | R3.0 | 模板/批量/系列 |
| FR-38 | Take 对比与回滚 | P1 | R3.0 | 并排/同步/提升 |
| FR-39 | QA 修复建议 | P1 | R3.5 | 错误→可执行修复 |
| FR-40 | 命令面板/快捷键/通知 | P1 | R3.5 | 键盘优先 |
| FR-41 | 本地规则式创作辅助 | P1 | R3.5 | 断句/场景建议/读时 |
| FR-42 | 多规格交付矩阵 | P2 | R4.0 | 9:16/1:1/4:5 |
| FR-43 | 平台规格与发布检查 | P2 | R4.0 | 各平台 QC 清单 |
| FR-44 | 字幕与本地化 | P2 | R4.0 | SRT/VTT/ASS/双语 |
| FR-45 | Engine SDK v2 + photo 引擎 | P2 | R4.0 | 引擎可注册/可回归 |
| FR-46 | 批量生产 | P2 | R4.0 | 文案数组→N 条排队 |
| FR-47 | 存储/项目管理 | P2 | R4.0 | 配额/GC/备份/交接 |
| FR-48 | 可观测性 | P2 | R4.0 | 甘特/吞吐/失败分类 |
| FR-49 | 审片包/协作边界 | P2 | R4.0 | 离线审片包导入导出 |

---

### 7.2 R2「能出片」（P0）

#### FR-20 参数化渲染链（P0 / R2.0）

**问题**：D02/E05/F02 仍调用参考片的 `entry.still`/`entry.film`；`still_spec.html` 无人调用；没有 `film_spec.html`。

**目标**：新项目从 B08 之后，D02 出用户场景的静帧，F02 出用户场景的逐帧画面；画面文字、版式、相机、转场全部来自 `scene.program`，引擎包只提供渲染原语。

**行为**：
1. **D01 编译 base program**：以 `timeline.doc + tokens.lock + layout_tokens + scene.template` 为输入，为**全部场景**产出 `scenes/<sceneId>.base.program.json`（无相机/转场运动，保留默认取景）；编译器是纯函数，带 `compiler_version`。
2. **D01 的 `still_spec.json` v2** 引用 base program 与 `times[]`（默认每场 1 个 `last_text_at`，长场景加 1 个中点），全场景覆盖。
3. **D02** URL 形如 `entry.still_spec?spec=<still_spec.json URL>&scene=<sid>&t=<t>&embed=<css>`；`still_spec.json` v2 = `{tokens, profile, scenes:[{id, program: URL, times:[]}]}`。`still_spec.html` 更新为读 `program`，**禁止**把 `scene.meaning/operation` 当默认文字；缺 program → `E_PROGRAM_INVALID`，不回退旧入口。**仅 imported 项目**（无 program）→ `legacy_entry.still`。
4. **E03 编译 motion program**：读取同一 timeline/tokens 与 E02 相机曲线，用**同一编译器**内部重编 base 后合并 `camera`（不依赖 D01 产物，避免新增边；测试断言与 D01 base 静态部分逐字节一致），产出 `scenes/<sceneId>.program.json`，并写入 `timeline_binding.json` 的 `programs[]`。
5. **E04 转场**：产出 `transitions.json`（每对相邻场景的类型/时长/方向/参数）；**补 E04→E05、E04→F02 两条 data 边**（修复当前 E04 无出边）；E04 变更使前后两场 dirty。
6. 新增 `engines/riso/entry/film_spec.html`：URL 形如 `entry.film_spec?binding=<timeline_binding.json URL>&transitions=<transitions.json URL>&mode=render|proxy&profile=<p>&start=&end=&total=&embed=<css>`；读 `binding.programs[]` + `transitions[]`，逐帧渲染并在转场区间合成；`mode=render` 支持 `start/end/total` 续渲；`mode=proxy` 支持 `fps/scale`。
7. **E05/F02** 判定：`engine_api>=2` 且 motion program 存在 → `entry.film_spec`（带 transitions）；imported → `legacy_entry.film`。
8. 引擎 contract 增加 `api_version: "2.0"`、`entry.still_spec`、`entry.film_spec`、`legacy_entry.{still,film}`、`scene_schema: "filmflow.scene/1"`。

**数据/API**：
- `GET /api/projects/:id/scenes/{sid}/program`、`PUT`（编辑器保存）
- `POST /api/projects/:id/scenes/{sid}/compile`（重编译单场景）
- `GET /api/runs/:id/render-manifest`

**验收**：
- [ ] 5 秒新项目（文案「风从纸上起」）D02 静帧中的文字是这句，不是 rumor 的任何句子。
- [ ] F02 产出的 120 帧中，逐帧文字/版式来自 program；抽 6 帧人工确认 + 黄金图 SSIM ≥0.98。
- [ ] imported rumor-39s 仍走旧 harness，46/46 succeeded，master 仍 39.5s。
- [ ] `grep -r "legacy_entry"` 是 v2 路径中唯一引用旧 `still/film` 的地方；新项目路径不出现 `entry.still`/`entry.film` 的旧 URL。
- [ ] base program 与 motion program 的静态部分逐字节一致（同 compiler version）；相机/转场差异只出现在 motion 段。

**依赖**：FR-21、FR-22、FR-24；引擎侧 film_spec 实现。

**风险**：DSL 表达力不足 → v1 只覆盖 12 组件/8 转场，剩余用 `text/shape/image` 组合；超纲需求进 v1.1，不阻塞。

---

#### FR-21 场景组件库 v1（P0 / R2.0）

**目标**：把 rumor harness 里的「手、箭头、滚轮、纸卡、印章、网点」等实体，迁移为**参数化组件**，供 program 引用；新项目不写引擎代码也能有镜头语言。

**行为**：
1. 新增 `engines/<id>/assets/scene-kit.js`，导出 12 个组件；每个组件有 `schema`（props 类型/范围/默认值）、`render(ctx, props, t)`、`bbox`、`capabilities`。
2. 组件只依赖 riso-core 的画布/网点/套印原语；不读项目文案。
3. program 的 `type:"component"` 通过 `component:"scene-kit/xxx"` + `props` 引用；未知组件 → `E_COMPONENT_UNKNOWN`，不静默降级。
4. 组件库有 fixture：每个组件 1 张基准图 + 1 个最小 program；C01 校验组件 schema，导出前跑 fixture。
5. UI 组件面板按「纸/字/图形/动作/数据」分组，拖入场景即插入默认 props，右侧 inspector 可调。

**验收**：
- [ ] 12 个组件全部有 schema、默认 props、fixture；C01 能在 3s 内校验完。
- [ ] 用组件库搭一个 5 秒 3 场景样片，不写任何引擎 JS。
- [ ] 组件参数越界（如 `count=0`）→ 编译期报错并定位到 props 字段。
- [ ] 组件渲染 3 次（同输入）帧 sha 一致。

**依赖**：FR-20。

---

#### FR-22 场景级增量渲染（P0 / R2.0）

**目标**：改一个场景，只重渲这个场景 + 相邻转场重叠帧；其余帧复用。把「改一句等半小时」降到「分钟级」。

**行为**：
1. `scene_hash = sha256(canonical_json(program) + tokens_lock_sha + engine_sha + font_sha + profile + renderer_version)`。
2. F02 开始前生成 `render.manifest.json`：场景 → 帧范围（`round(start*fps)` 到 `round(end*fps)`），转场重叠 `ceil(transition.duration*fps)` 同时算入前后两场。
3. 与上一次 manifest 比对：hash 不同 → `dirty`；时长/顺序变化 → 该场景及其后所有场景 `dirty`；转场变化 → 前后两场 `dirty`。
4. 渲染顺序：`dirty` 场景按时间轴顺序；`clean` 场景的帧直接复用（同目录硬链接或保留原文件）。
5. F02 进度按场景汇报：`scene S03 42/192`；单场景失败不阻塞其他场景（`fail_fast=false`）。
6. F03 用 manifest 校验：missing/black 按场景聚合；重复帧仍按 §6.2 警告。
7. 强制全量：`POST /runs/:id/start` 带 `force_full=true` 或 UI「完全重渲」。

**数据/API**：
- `render.manifest.json`（见 §6.5）
- `SceneState` 表：`run_id, scene_id, hash, status, frame_start, frame_end, ms, qa_json`
- `GET /api/runs/:id/render-manifest`、`POST /api/runs/:id/render` `{profile, scenes?, force_full}`

**验收**：
- [ ] 40s 片改 S03 一句文案 → 只重渲 S03 + S02/S04 重叠帧；`renderedFrames ≤ 25%` 总帧数；F02 墙钟 ≤ 全量的 20%。
- [ ] 改 S03 时长（8s→10s）→ S03 及其后全部 dirty；前两场复用。
- [ ] 改 S02→S03 转场 → S02/S03 dirty；S01 不变。
- [ ] 杀进程后 Resume → 只补 dirty 场景缺失帧；已 done 场景不重渲。
- [ ] manifest 与 `out/frames/` 帧数一致；F03 能定位到场景。

**依赖**：FR-20、FR-24；F02/F03 改造。

---

#### FR-23 快速预览服务（P0 / R2.0）

**目标**：编辑时「随手看一眼」：单帧 ≤2s、5 秒片段 ≤20s；不排在大批渲染后面；不进审批、不写 final 产物。

**行为**：
1. 独立 `PreviewService`（**共用同一个 Chrome 实例与 `chrome-queue=1`**，不新开第二个浏览器；独立优先级队列），优先级：`preview > interactive(still) > batch(film) > delivery`。
2. `POST /api/projects/:id/preview/still` `{sceneId, time, profile:"draft"}`：同步等待 ≤6s，返回 PNG（或 202 + job）。
3. `POST /api/projects/:id/preview/segment` `{sceneId, start, end, profile:"draft"}`：异步 job，返回 mp4（H.264, 540p/12fps, 无音或临时音）≤20s。
4. `POST /api/projects/:id/preview/film` `{profile:"draft"|"review"}`：整片预览 job，**复用 preview cache 的 clean 场景帧、只渲脏场景**，draft ≤8min；产物写 `out/preview/`，**不进** F02 产物链、不影响 F06。
5. 同一 `scene_hash + time + profile` 命中缓存 → ≤300ms；缓存目录 `~/.filmflow/cache/preview/<project>/<scene_hash>/<time>.png`，LRU 500MB。
6. 防抖 250ms；新请求取消同场景旧请求；取消只在帧边界生效，不中断正在写的帧。
7. 预览永不写入 `out/frames/`；`still_spec/film_spec` 的 `mode=preview` 只写 `out/preview/` 与缓存，**不走** `/frame` 端点；不产生 Artifact 审批记录。
8. 门之前可用，但画面右上角水印 `PREVIEW`；门之后可关水印；水印不进入 final。
9. Chrome 忙时：预览最多等「当前帧」完成；若等待 >3s，返回 `E_PREVIEW_BUSY` + 预计时间，UI 显示「批量渲染中，稍后自动刷新」。

**验收**：
- [ ] 40s 片 F02 运行中，单帧预览 p50 ≤2s、p95 ≤6s；不导致 F02 失败。
- [ ] 连续拖时间轴 20 次，只保留最后一次结果；无内存泄漏、无 Chrome 页面堆积。
- [ ] 同参数二次预览 ≤300ms（缓存）。
- [ ] 预览图与同参数、同 profile 渲染帧 SSIM ≥0.995（同源 shader）；与 final 归一化后 ≥0.98。
- [ ] 预览不产生 Approval/Artifact 记录（审计可查但不算交付）。

**依赖**：FR-20、FR-24、FR-29。

---

#### FR-24 渲染档位 draft/review/final（P0 / R2.0）

**目标**：同一时间轴，三种质量：draft 用来改，review 用来审，final 用来交。  
**产出者**：draft（整片）→ PreviewService `/preview/film`；review（整片）→ PreviewService 或 E05 代理；final（整片）→ F02。

| profile | 分辨率 | fps | 编码 | 音频 | QA | 目标耗时（40s） |
|---|---|---|---|---|---|---|
| `draft` | 960×540 | 12 | x264 crf 28, ultrafast | 临时混音（可无） | 只查 missing/黑帧 | ≤8 min |
| `review` | 1280×720 | 24 | x264 crf 22, fast | 临时音（口播/占位，可无） | 运动（有临时音时同步/响度） | ≤18 min |
| `final` | 1920×1080 | 24 | x264 crf 17, medium | 完整混音 | 全量（SSIM/LUFS/TP） | ≤30 min |

**行为**：
1. `render.profile.json` 定义档位；项目可覆盖分辨率/fps/码率，但 `final` 不得低于 1080p/24（可调）。
2. D02 产出 `draft` + `review` 静帧（D05 用 review，全场景）；**F02 只跑 `final`**（DAG 中的权威画面）；**E05 跑 `review` 代理**；`draft/review` 的整片预览走 PreviewService `/preview/film`，**不写入 F02 产物链**，因此不会让 F06 失效。G07 校验 F02 final。
3. QA 节点按 profile 读阈值：draft 只做冒烟；review 做运动+同步；final 做全量。
4. 同一 `scene_hash` 不同 profile 的缓存**不共享**（profile 进 hash）。
5. UI 顶部档位切换；切换后显示「预计 X 分钟 / 复用 Y 帧」。
6. G07 前校验最新 F02 manifest 的 `profile=final` 且与当前 Run 匹配；缺失 → `E_FINAL_REQUIRED`，不允许用 review/draft 交付。

**验收**：
- [ ] 40s 片 draft ≤8 min（PreviewService），review ≤18 min（E05/PreviewService），final ≤30 min（F02）；记录在报告。
- [ ] draft 与 final 的场景内容一致（抽 6 帧 SSIM ≥0.98；分辨率归一后）。
- [ ] 切档不重跑已完成的 final；只补缺失档。
- [ ] QA 阈值随档位生效（draft 不因 LUFS 失败）。

**依赖**：FR-22、FR-29。

---

#### FR-25 文档版本化与安全编辑（P0 / R2.0）

**目标**：编辑不再直接改运行时文件；自动保存、撤销、版本、diff、回滚、冲突检测。

**行为**：
1. 文档类型：`script` / `brief` / `timeline` / `profile` / `delivery` / `audio`；每种有 `version`（自增）、`hash`、`base_version`。
2. `PUT /api/projects/:id/docs/:kind` 带 `base_version`；不匹配 → `409 E_DOC_CONFLICT`，返回当前版本与 diff。
3. 每次保存生成 `DocRevision`；保留最近 100 版；可 `GET /docs/:kind/versions`、`POST /docs/:kind/restore`。
4. 编辑器自动保存 2s 防抖；本地 undo/redo 50 步；服务端每 10s 或显式保存落版。
5. 保存后显示「影响预估」：`N scenes / M nodes / K gates`；用户确认后才「应用到 Run」。
6. B06 只导出 `task.json` 快照（带 `doc_version`/`doc_hash`），不再写回文档；validator 读快照。
7. 执行器只读 Run 启动时的快照（`runs/<id>/docs/` + `snapshot.json`：文档、tokens.lock、字体 sha、资产清单、profile）；运行中编辑不改变本次 Run；快照哈希进缓存键。

**验收**：
- [ ] 两个标签页同时改同一文档：后保存者收到 409，不丢前者内容。
- [ ] 改一句 → 自动保存 → 刷新 → 内容还在；撤销 20 步回到原文。
- [ ] 保存后显示影响范围；确认前 Run 不变。
- [ ] 版本列表可 diff（字段级）、可回滚；回滚生成新版本，不删历史。
- [ ] 新项目 task.json 的 `doc_version` 与文档一致；手改项目根 task.json 不会影响运行（只读快照）；imported 项目例外。

**依赖**：FR-20、FR-22；DB 迁移。

---

#### FR-26 全场景静帧与关键帧审阅（P0 / R2.5）

**目标**：D05 批准的是**整片**，不是前 3 场；审阅有 contact sheet、逐场对比、逐帧查看。

**行为**：
1. D01 已覆盖全部场景（FR-20）；本 FR 增加 contact sheet、逐场查看、审批 diff、逐帧对比。
2. D02 产出 `stills_manifest.json`：`sceneId → [{t, artifact, sha}]`；生成 16 宫格 contact sheet。
3. D03 的「已查看」按场景记录：每个场景至少看 1 张；`viewed.json` 记录 `sceneId/time/region`。
4. D05 审批清单显示：场景数、每场静帧缩略图、未查看标记、与上一版 diff（新增/变化/删除）。
5. UI 支持：网格/单张 100%/200%、A/B 叠加、前后版切换、键盘 ←/→ 切场景。
6. 静帧 QA（D04）按场景出指标：lum、文字溢出、安全区、缺字；任一场景失败 → 定位到 sceneId。

**验收**：
- [ ] 5 场景项目 D02 产出 ≥5 张静帧（长场景 ≥6 张），contact sheet 含全部场景。
- [ ] D03 未看全 5 场时 D05 不可批准，提示缺失场景。
- [ ] 修改 S03 后，D05 diff 只标 S03 变化；其他场景显示「未变」。
- [ ] 文字溢出/缺字能在 1s 内定位到场景与图层。

**依赖**：FR-20、FR-21。

---

#### FR-27 音频工作台 v1（P0 / R2.5）

**目标**：不靠 `scripts/drive_run.py` 的 `say` 和正弦波；用户能录/导口播、看到波形、手动对齐、自动闪避。

**行为**：
1. 口播：浏览器录音（MediaRecorder）或导入 WAV/MP3/M4A；每个场景可存多个 Take；选一个主 Take。
2. 波形：服务端预计算 peaks（`GET /audio/waveform?asset=...&w=2000`），前端 canvas 绘制；播放头与时间轴同步。
3. 对齐：有 whisper → 词级；无 whisper → 手动拖句子块，吸附场景/事件；显示 `manual` 来源徽标；偏差 >0.15s 高亮。
4. 闪避：sidechaincompress（`threshold=0.03, ratio=4, attack=80, release=350`），深度可调（默认 −8dB）；波形上显示闪避曲线。
5. 响度：默认 −16 LUFS / TP −1.5；可选 −14（播客/YouTube）/ −16（通用）；G06 按目标校验。
6. 音乐：本地文件 + 许可字段（来源/授权/到期）；无许可不得进 final。
7. 导出 Stems：voice/music/sfx 三轨 WAV，供平台或后期。

**验收**：
- [ ] 录 5 句口播，波形 1s 内出图；拖对齐后每个句子偏差 ≤0.15s。
- [ ] 闪避在语音段降低 ≥6dB，非语音段恢复 ≤0.3s；混音时长 = 片长，音乐不足循环/淡出，不截断。
- [ ] 无 whisper 时明确显示 `manual`，不伪装词级。
- [ ] 无许可音乐 → G03/G07 阻断，错误 `E_LICENSE_MISSING`。
- [ ] Stems 三轨时长与 master 一致（±1 帧）。

**依赖**：FR-25、G02/G05/G06 改造；whisper 下载器（D7）。

---

#### FR-28 交付 v1（P0 / R2.5）

**目标**：一次交付 = 1080p master + 字幕 + 封面 + manifest + QC 报告 + zip；不是只有一个 mp4。

**行为**：
1. 默认变体：`16:9 1920×1080` + `9:16 1080×1920`（安全区重排，不做智能裁切）；1:1/4:5 在 FR-42 扩展。
2. 字幕：由 alignment 生成 SRT（中文），可选 VTT；行宽 ≤16 全角字、阅读速度 ≤9 字/秒；时间码与音频对齐。
3. 封面：从 D02 静帧选一张；叠加标题（可选）；导出 1920×1080 JPG/PNG；9:16 同步生成。
4. 包结构：
```
deliveries/<runId>/
  master_16x9.mp4
  master_9x16.mp4
  captions.zh.srt
  cover_16x9.jpg
  cover_9x16.jpg
  manifest.json        # 产物哈希、审批、环境锁、权利
  qc.json              # 平台检查结果
  rights.json          # 字体/音乐/风格来源许可
  FilmFlow-delivery.zip
```
5. QC：时长、分辨率、fps、码率、LUFS、TP、黑帧、字幕条数、封面尺寸、文件大小；任一失败 → G07 阻断并列修复建议。
6. manifest 增加 `project.lock.json`（引擎/字体/Chrome/ffmpeg 版本）与 `rights`。
7. 交付页可预览、可下载、可重新打包；zip 生成后计算 sha。
8. 变体渲染：按 variant layout 重新编译 program（不改文案），走 scene pipeline 只渲 dirty 场景；共用音频与字幕时间码；9:16 不裁切 16:9 画面。

**验收**：
- [ ] 40s 片一键产出上述 9 个文件；zip 可解压、master 可播。
- [ ] 字幕 100% 句子覆盖；每行 ≤16 字；时间码与音频偏差 ≤0.15s。
- [ ] 封面 1920×1080 / 1080×1920；无拉伸。
- [ ] QC 全绿；故意把 LUFS 调到 −20 → G07 阻断并给「重新混音到 −16」建议。
- [ ] manifest 含全部产物 sha、9 条审批、环境锁；换机可复现。

**依赖**：FR-27、G07 改造、字幕/封面生成器。

---

#### FR-29 渲染队列与崩溃恢复（P0 / R2.0）

**目标**：队列可持久化、可抢占、可恢复；崩溃后不丢任务、不残留 Chrome。

**行为**：
1. 扩展 `Job`：`kind, priority, status, payload_json, result_json, attempts, max_attempts, lease_until, heartbeat_at, parent_id, cancel_requested, progress, eta, error_code, error_msg`。
2. 状态机：`queued → leased → running → succeeded | failed | canceled | retry_wait`；租约 30s，心跳 5s；过期 → 重新入队（attempts+1）。
3. 优先级：`preview=100, interactive=80, batch=40, delivery=20`；同优先级 FIFO；批渲染每 10 帧检查一次抢占点。
4. 启动恢复：扫描 `running/leased` 且租约过期 → `queued`；清理 `/tmp/ff-chrome-*`、孤儿 8787、孤儿 ffmpeg（按 run_id 匹配）。
5. 队列页：排队/运行/失败/历史；显示 ETA、当前帧、所属 Run、取消/重试/提升优先级。
6. Run 级取消：取消所有子 job；等待当前帧写完；10s 未停 → SIGTERM→KILL。
7. 幂等：同一 `(run_id, node_id, scene_hash, profile)` 只允许一个活跃 job。
8. RunEngine 的 `ACTIVE/CANCELS` 不再是唯一事实源：Run/Job 状态落库；启动时扫描 `running` Run 并恢复调度；取消请求落库，重启后仍生效。

**验收**：
- [ ] F02 运行中 `kill -9` API 进程 → 重启 → 60s 内 Run 回到 running，缺失帧继续；无重复帧。
- [ ] 预览请求在批渲染中 3s 内得到结果或明确 ETA；批渲染不被取消。
- [ ] 队列页能看到 4 类优先级；取消后 10s 内进程退出。
- [ ] 连续 3 次崩溃/恢复，最终帧数正确、无孤儿 Chrome。

**依赖**：DB 迁移、RunEngine 调度改造；不改变门语义。

---

#### FR-30 黄金项目与视觉回归（P0 / R2.0）

**目标**：任何渲染链改动都能被自动抓住；新项目出片不是靠人眼。

**行为**：
1. 新增 `fixtures/golden/5s/`、`15s/`、`40s/`：文案、风格、profile、期望静帧/关键帧、期望 manifest。
2. `scripts/golden_run.py`：建项目 → 跑到 F06 → 抽 6 帧与基准比 SSIM/pHash → 校验文字内容（program 字符串 + 可选 OCR）→ 输出报告。
3. CI（本地 `make verify`）：单元 + 集成 + 黄金项目（5s 必跑，15s/40s nightly）。
4. 视觉回归阈值：SSIM ≥0.98；pHash 汉明距离 ≤6；允许字体抗锯齿差异，不允许内容差异。
5. 每次改引擎/执行器/字体/Chrome，必须跑黄金项目；失败给出 diff 图与场景定位。
6. 新增 BDD 场景：`参数化新项目出片`、`单场景增量渲染`、`预览优先级`、`交付包完整性`。

**验收**：
- [ ] 5s 黄金项目在 clean 环境 10 分钟内跑完，6 帧全过。
- [ ] 故意改错一个字 → 黄金项目失败并定位到 S01/L_title。
- [ ] 故意改 shader 网点角度 → 视觉回归失败并输出 diff 图。
- [ ] imported rumor-39s 黄金回归仍 46/46、master 39.5s。

**依赖**：FR-20~24。

---

#### FR-31 新手引导与示例项目（P1 / R2.5）

**目标**：第一次打开 10 分钟做出第一条片；不面对空白画布和 46 个节点。

**行为**：
1. 首页「做第一条片」：3 个模板（口播 15s / 观点 30s / 产品 40s），每个预置文案、风格、场景结构、音频占位。
2. 向导第 3 步的预演使用**用户标题**（不是固定「风」）；可切换 3 个候选标题。
3. 首次进入 Studio 的 5 步引导：场景列表 → 单帧预览 → 改一句 → 看 diff → 出 draft。
4. 空状态：每个页面有「下一步做什么」与示例；错误页有「怎么修」。
5. 示例项目只读副本，用户可「复制为我的项目」。
6. 帮助面板：快捷键、DSL 组件速查、常见 QA 错误。

**验收**：
- [ ] 新用户按引导 10 分钟内产出 15s draft（含音频占位）。
- [ ] 模板复制后所有路径在项目根内，无外部依赖。
- [ ] 引导可跳过、可重看；不阻塞老用户。

**依赖**：FR-23、FR-24、FR-28。

---

### 7.3 R3「好创作」（P1）

#### FR-32 时间轴编辑器（P1 / R3.0）

**目标**：把「表格里的场景」变成「可拖、可看、可听」的时间轴；场景块是画布上的第一等对象。

**行为**：
1. 轨道：`V`（场景块）、`T`（文字）、`G`（图形/组件）、`C`（相机）、`A1`（口播）、`A2`（音乐）、`A3`（SFX）、`M`（事件/markers）。
2. 场景块：拖拽移动、拖边改时长、右键分割/合并/复制/禁用；相邻场景默认 ripple（改时长推后面）。
3. 吸附：帧、场景边界、事件、拍点、播放头；可开关；`Alt` 临时关闭。
4. 播放：空格播放/暂停、`J/K/L` 倒放/停/正放、`←/→` 逐帧、`Shift+←/→` 逐秒、`I/O` 入出点、循环区间。
5. 缩放：`+/-`、`Fit`、滚轮；时间刻度帧号/秒双显；100 场景 60fps。
6. 画布内联编辑：双击文字图层直接改字；拖拽移动；右侧 inspector 调字号/颜色/对齐/入场动画。
7. 每次编辑 → 250ms 防抖预览；场景 hash 变化 → 标脏；保存 → 版本。
8. 撤销/重做 50 步；自动保存 2s；冲突走 FR-25。
9. 读时校验：场景字数/语速 → 红/黄提示；拖短到读不完时阻止或要求确认。
10. 键盘优先：所有操作有快捷键；命令面板可搜。

**验收**：
- [ ] 拖 S03 结束点 8s→10s，S04/S05 自动后移；总时长/帧数更新；读时校验通过。
- [ ] 分割 S02 为两场；program 复制并可独立编辑；转场自动补 cut。
- [ ] 改一句文字，250ms 后画布出现新静帧；≤3s 完成（draft 单帧）。
- [ ] 撤销 30 步回到初始；刷新后恢复最后自动保存。
- [ ] 100 场景/500 图层时间轴拖动 60fps。

**依赖**：FR-20、FR-23、FR-25。

---

#### FR-33 审片播放器与批注（P1 / R3.0）

**目标**：审片人能在片子上直接说「这一帧，这个字，太大」，而不是发语音。

**行为**：
1. 播放器：master/review 切换、逐帧、时间码、帧号、JKL、循环区间、全屏、亮度/安全区叠加。
2. 批注工具：矩形、箭头、自由画笔、文字；锚定 `frame + sceneId + layerId`；颜色分类（必改/建议/疑问）。
3. 评论列表：按时间/场景/状态排序；点击跳帧；可回复；可 resolve/reopen；可 assign 给自己。
4. 审片决议：按场景「通过/需修改」；整片「通过/驳回」；与 D05/E07/F06/G07 门联动（门清单显示批注数）。
5. 导出：`review.json` + CSV；导入合并（按 id 去重）。
6. 离线审片包：`review-package.zip` = review 版 mp4 + review.json + README（如何导入）；客户在另一台机器看，回传 JSON 导入。
7. 对比：两个 Take 并排/同步逐帧；差异帧高亮；可把 B 的某场景「采纳」到 A。
8. 不做云端、不做账号；审片包是唯一外发形态。

**验收**：
- [ ] 在 10 个不同帧上建 10 条批注（含框选），列表点击均准确跳帧。
- [ ] 导出→清空→导入，10 条批注/状态/锚点完全恢复。
- [ ] 审片包在无 FilmFlow 的机器可播放；回传 JSON 可导入。
- [ ] 两 Take 同步播放，帧偏差 ≤1 帧；采纳单场景后只标脏该场景。

**依赖**：FR-32、FR-38。

---

#### FR-34 镜头语言编辑器（P1 / R3.0）

**目标**：相机与转场从「默认值」变成「可创作的语言」。

**行为**：
1. 相机：每场景独立 `camera.keyframes`；可编辑 zoom/pan/rotate/anchor；曲线视图；预设：锁定、缓推、缓拉、横移、跟随、手持轻抖、撞击。
2. 相机参数支持「相对画面」与「相对图层」两种锚点；安全区可视化。
3. 转场：8 种库；可选时长/方向/形状；A/B 两端各 1s 预览；转场影响前后两场 dirty。
4. 文字动画：打字机、逐行、遮罩、逐字错峰、强调脉冲；每个文字图层独立。
5. 组件 inspector：所有 props 有 schema 驱动表单、范围、默认值、说明；不合法即时红框。
6. 所有参数变更 → program 更新 → 场景 hash 变 → 预览/增量渲染。

**验收**：
- [ ] 给 S01 设 3 个相机关键帧（推近→横移→拉远），预览与 final 一致。
- [ ] 换 5 种转场，前后场景自动标脏；预览 A/B 无跳变。
- [ ] 组件 props 越界即时提示；修正后 1s 内预览更新。
- [ ] 相机曲线可保存为预设，跨项目复用。

**依赖**：FR-21、FR-32。

---

#### FR-35 音频工作台 v2（P1 / R3.0）

**目标**：把音频从「过 G 门」变成「可打磨」：多 Take、降噪、拍点、SFX、Stems。

**行为**：
1. 多 Take：每场景可录/导多个；A/B 试听；选择主 Take；支持「拼接」（前句 Take1 + 后句 Take2）。
2. 清理：`afftdn` 降噪、`highpass 80`、`deesser`、3 段 EQ、静音裁剪、响度归一；每个处理可开关、可预览。
3. 对齐：词级/句级；手动拖块；偏差着色；一键「按场景起点对齐」；导出/导入 alignment。
4. 拍点：显示 onset 强度；可增删/拖动；吸附事件；`allow_snap` 事件自动吸附。
5. SFX：资产库拖入；按事件/时间码放置；音量/淡入淡出；同事件多候选试听。
6. Stems：voice/music/sfx 三轨 WAV；每轨可调；导出与 master 等长。
7. 响度预设：−14（YouTube/播客）、−16（通用）、−18（广播）；G06 按所选目标。
8. 无许可音乐/SFX 不可进 final；许可到期提醒。

**验收**：
- [ ] 同一句录 3 个 Take，A/B 切换无爆音；拼接后时间轴自动更新。
- [ ] 降噪后底噪 ≤−50dBFS，语音可懂度不下降（人工抽检）。
- [ ] 拍点图 20 个 onset，拖动吸附到事件 ≤1 帧。
- [ ] Stems 三轨求和与 mix 的 LUFS 差 ≤0.5。
- [ ] 许可缺失/过期 → G07 阻断。

**依赖**：FR-27、FR-36。

---

#### FR-36 资产库（P1 / R3.0）

**目标**：图片/音频/字体/视频有地方放、能复用、可追溯、可替换。

**行为**：
1. 两个作用域：全局库（跨项目）+ 项目库；项目引用全局资产用 sha，不复制。
2. 导入：拖拽/文件选择；图片 PNG/JPG/WebP/SVG；音频 WAV/MP3/M4A；字体 TTF/OTF/WOFF2；视频 MP4/MOV（作为素材，不作 NLE 剪辑）。
3. 去重：sha 相同只存一份；显示引用计数与使用处（场景/图层）。
4. 元数据：名称、标签、尺寸/时长、许可（来源/类型/到期）、作者、备注；缩略图/波形。
5. 拖入画布 → 创建 `image`/`audio` 图层；缺失资产 → 渲染前阻断，给「重新链接」。
6. 替换资产：保持图层位置/动画，换 sha；相关场景标脏。
7. 字体：显示字重/字符覆盖；项目缺字在 C03 前预警；许可证必填。
8. 清理：未引用资产可归档；全局资产删除需确认引用数。

**验收**：
- [ ] 导入 50 张图，重复 sha 只入库 1 次；引用计数正确。
- [ ] 删除被引用资产 → 阻断并列出使用处。
- [ ] 替换图片后，只有使用该图的场景 dirty。
- [ ] 字体缺字在编辑器即时标红，不用等 C03。

**依赖**：FR-25、FR-32。

---

#### FR-37 模板与系列（P1 / R3.0）

**目标**：第二条片不从零开始；十条片能批量做。

**行为**：
1. 项目模板：`profile + tokens + timeline 骨架 + 场景模板 + 样式 + 交付预设`；从任意项目「另存为模板」。
2. 场景模板：常用场景结构（标题/论点/证据/结论/CTA），带组件与动画预设；拖入时间轴即实例化。
3. 系列：一个系列 = 模板 + 文案数组 + 变量（标题/数字/颜色）；每项生成一个项目/Run。
4. 批量：CSV/JSON 导入；预览前 3 项；排队；失败项隔离；批量导出 zip。
5. 变量替换：`{{title}}`、`{{number}}`、`{{accent}}`；替换后重新编译 program。
6. 模板版本化；项目锁定模板版本，升级需显式迁移。

**验收**：
- [ ] 从模板 30 秒建 5 个项目，场景/风格/交付预设一致。
- [ ] CSV 10 行 → 10 个 Run 排队；3 个失败不影响 7 个成功；批量 zip 含 10 个交付包。
- [ ] 模板升级不自动改老项目；迁移有 diff 与确认。

**依赖**：FR-25、FR-28、FR-46。

---

#### FR-38 Take 对比与回滚（P1 / R3.0）

**目标**：一版不如一版时，能找回来；两版之间能看出差在哪。

**行为**：
1. Take = Run；可命名、评分、备注、标记「当前」；列表按时间/评分。
2. 并排对比：同步播放/逐帧；帧差高亮；音频波形对齐；场景级「哪版更好」。
3. 场景级采纳：把 B 的 S03 program 复制到 A；只标脏 S03。
4. 提升为当前：写 `out/CURRENT`；交付/G07 默认读当前 Take。
5. 分支：从任意 Take 复制文档创建新 Run；保留血缘 `parent_run_id`。
6. 删除：软删除；被引用/当前不可删。

**验收**：
- [ ] 两 Take 同步播放偏差 ≤1 帧；帧差图正确。
- [ ] 采纳 S03 后 A 的 manifest 只 S03 dirty。
- [ ] 提升/分支/回滚均可在 UI 完成；血缘可查。
- [ ] 删除当前 Take 被阻止。

**依赖**：FR-33、FR-25。

---

#### FR-39 QA 修复建议（P1 / R3.5）

**目标**：QA 失败不再只给红字；给「改哪里、怎么改、改完影响什么」。

**行为**：
1. 失败分类：`text_overflow`、`font_missing`、`black_frame`、`missing_frame`、`motion_spike`、`static_too_long`、`lufs_out`、`tp_out`、`sync_out`、`license_missing`、`engine_unavailable`。
2. 每条给：原因、定位（scene/layer/frame）、建议动作（1–3 个）、预计影响（nodes/gates/时间）。
3. 一键修复（安全动作）：扩场景 0.5s、字号 −10%、换行、补静帧、重渲单场景、重新混音到目标 LUFS、补许可字段。
4. 非安全动作（改文案/删场景）只给建议 + 跳转，不自动改。
5. 修复前可预览；修复后只跑受影响节点/场景；记录 audit。
6. 修复成功率与误报率进报告。

**验收**：
- [ ] 5 类常见失败各有 ≥1 个可执行建议。
- [ ] 「扩场景 0.5s」一键后读时校验通过、只重渲该场景。
- [ ] 「字号 −10%」后文字不再溢出，其他场景不动。
- [ ] 所有修复可撤销。

**依赖**：FR-30、FR-32、FR-35。

---

#### FR-40 命令面板/快捷键/通知（P1 / R3.5）

**目标**：熟练用户不碰鼠标；长任务有进度中心。

**行为**：
1. `Cmd/Ctrl+K` 命令面板：跳转、运行、预览、批准、导出、切换档位、搜索场景/资产。
2. 全局快捷键表；可自定义；冲突检测；`?` 查看。
3. 通知中心：渲染完成/失败/门待批/许可到期/磁盘不足；点击跳转。
4. 进度中心：所有 job 的进度/ETA/取消；后台运行不阻塞编辑。
5. 离线可用；无推送、无邮件。

**验收**：
- [ ] 20 个核心命令可在面板搜到并执行。
- [ ] 全流程可纯键盘完成（建项目→改→预览→跑→批门→导出）。
- [ ] 通知不重复、可标记已读；失败通知带修复入口。

**依赖**：FR-29、FR-32。

---

#### FR-41 本地规则式创作辅助（P1 / R3.5）

**目标**：降低「从文案到分镜」的门槛，但**不生成内容、不调用在线模型**；所有建议可解释、可拒绝。

**行为**：
1. 断句：按标点/语义停顿/长度；给「建议断句」与读时估算；用户可改。
2. 场景建议：按 4–6 场景模板、句群、情绪转折；给理由（句数/读时/转折词）。
3. 组件建议：关键词 → 组件（如「证据/卡片」→ evidence-card，「增长/数字」→ count-up/chart-bar）；给匹配词。
4. 镜头建议：按场景类型给 2–3 个相机预设（锁定/缓推/横移）；不自动应用。
5. 读时校验：字数/语速/停留；给出「建议时长」与「最短可读」。
6. 全部规则在本地；可导出规则表；不联网；不写文案。
7. 建议以「草稿层」呈现，用户接受才写入文档；拒绝不留痕。

**验收**：
- [ ] 粘贴 300 字 → 1s 内给 4–6 场景建议 + 每场理由。
- [ ] 每条建议可接受/拒绝/编辑；接受后只影响对应场景。
- [ ] 断网可用；进程无外部请求（可抓包验证）。
- [ ] 建议不改变原文；只改结构。

**依赖**：FR-25、FR-32。

---

### 7.4 R4「能批量/工作室」（P2）

#### FR-42 多规格交付矩阵（P2 / R4.0）

**目标**：一条时间轴出 16:9 / 9:16 / 1:1 / 4:5，不是拉伸，是重新布局。

**行为**：
1. 变体：`16:9 1920×1080`、`9:16 1080×1920`、`1:1 1080×1080`、`4:5 1080×1350`；可自定义。
2. 布局 profile：安全区、网格列数、字号比例、标题最大行数、组件缩放；每变体独立。
3. 重排优先：文字重新断行、组件重排、相机 anchor 调整；无法重排的图片按 focus point 裁切，**禁止拉伸**。
4. 每变体独立渲染/QA/封面/字幕；共享 program 与音频。
5. 变体间一致性检查：关键文字不丢、不溢出、不遮挡；差异报告。
6. 只重渲受影响变体；16:9 不变时 9:16 单独重渲。

**验收**：
- [ ] 40s 片出 4 个变体；每个文字完整、无溢出、无拉伸。
- [ ] 9:16 的字号/行宽符合移动端可读性（≥36px，行宽 ≤14 全角字）。
- [ ] 改一句文案 → 4 个变体都标脏，但只重渲脏场景。
- [ ] 变体 QC 全绿；封面/字幕各自匹配画幅。

**依赖**：FR-28、FR-34。

---

#### FR-43 平台规格与发布检查（P2 / R4.0）

**目标**：交付前就知道会不会被平台拒。

**行为**：
1. 平台预设：YouTube、Bilibili、抖音、视频号、小红书、Instagram Reels；每个含分辨率/fps/码率/时长/LUFS/TP/封面/字幕要求。
2. 检查项：容器/编码/像素格式、时长、码率、音频声道/采样率、LUFS/TP、黑帧、字幕、封面尺寸、文件大小。
3. 结果三态：pass/warn/block；block 不给导出；warn 需确认。
4. 平台规则版本化；更新记录；可自定义预设。
5. 报告写入 `qc.json` 与交付 manifest；可导出 PDF/HTML（本地）。

**验收**：
- [ ] 6 个平台预设均可选；检查项与官方规格一致（记录来源/日期）。
- [ ] 故意 9:16 用 16:9 封面 → block 并给正确尺寸。
- [ ] LUFS −20 → block；−17 → warn；−16 → pass。
- [ ] qc.json 含每项实测值/阈值/结论。

**依赖**：FR-42、FR-28。

---

#### FR-44 字幕与本地化（P2 / R4.0）

**目标**：字幕不是附属品；多语言版本可交付。

**行为**：
1. 从 alignment 生成 SRT/VTT/ASS；支持手动改行/断句/时间码。
2. 规则：每行 ≤16 全角字（横屏）/≤12（竖屏）；阅读速度 ≤9 字/秒；最短 1s；最长 7s。
3. 双语：中文+英文双行；可导入翻译 JSON/CSV（人工，不调用在线翻译）；时间码复用。
4. 烧录可选：`burn-in=true` 生成硬字幕变体；软字幕单独文件。
5. 多语言音轨：不同语言口播 Take → 独立 mix/变体；字幕跟随。
6. 字幕 QA：覆盖、重叠、超速、超长、缺字。

**验收**：
- [ ] 40s 片生成中英 SRT；每行/速度合规；与音频偏差 ≤0.15s。
- [ ] 导入英文翻译后生成双语字幕；时间码不变。
- [ ] 竖屏字幕行宽 ≤12；不超安全区。
- [ ] 烧录版与软字幕版都可交付。

**依赖**：FR-27、FR-42。

---

#### FR-45 Engine SDK v2 + photo 引擎（P2 / R4.0）

**目标**：引擎可注册、可校验、可回归；photo 族 157 条从「只能看」变「可生产」。

**行为**：
1. Contract v2：`api_version 2.0`、`entry{preview,still_spec,film_spec,proxy}`、`legacy_entry{still,film}`、`scene_schema`、`capabilities{elements,transitions,effects}`、`limits`、`fixtures[{program,png,ssim}]`、`validate`。
2. CLI：`filmflow-engine validate <pack>`、`render <program>`、`bench <program>`；输出 JSON。
3. 注册：放入 `engines/<id>/` → 扫描 → 校验 → `available`；失败给具体缺项。
4. 视觉回归：每个 fixture 渲染→SSIM/pHash→阈值；CI 阻断。
5. capability negotiation：program 用了引擎不支持的元素 → 编译期 `E_CAPABILITY_MISSING`；可声明 `approximate` 降级。
6. photo 引擎：图片/渐变/文字/电影调色/颗粒/暗角/漏光；支持 157 条 photo tokens；中文排版复用 type-spec。
7. 目标：producible 61 → 218/341。

**验收**：
- [ ] 新引擎只加目录 + contract + fixture，不改 App 代码即可 `available`。
- [ ] 缺 capabilities/fixture 的引擎被拒绝并列出缺项。
- [ ] photo 引擎跑 10 条 photo 风格，C01/fixture 全过；producible ≥218。
- [ ] 引擎升级自动使相关 preview/scene 缓存失效。

**依赖**：FR-20、FR-21、FR-30。

---

#### FR-46 批量生产（P2 / R4.0）

**目标**：十条片不是重复十次，而是一次编排。

**行为**：
1. 批量定义：模板 + 文案数组（CSV/JSON）+ 变量 + 每项覆盖（风格/时长/交付）。
2. 预览：前 3 项生成 draft 缩略图；确认后全量排队。
3. 队列：按优先级/公平调度；单条失败隔离；可重试/跳过/暂停。
4. 批量监控：进度矩阵（10×46）、预计完成时间、失败原因聚合。
5. 批量交付：每条一个交付包；汇总 zip + 总 manifest。
6. 资源预算：并发受 Chrome/ffmpeg 锁限制；显示排队 ETA；夜间模式。

**验收**：
- [ ] 10 条 15s 片批量跑完；失败 1 条不影响 9 条；总耗时 ≤单条×10×1.2。
- [ ] 批量矩阵可看到每条/每阶段状态；失败可单独重试。
- [ ] 汇总 zip 含 10 个交付包 + 总报告。
- [ ] 中途重启，队列恢复。

**依赖**：FR-29、FR-37、FR-42。

---

#### FR-47 存储/项目管理（P2 / R4.0）

**目标**：项目多了不爆盘；能归档、备份、交接。

**行为**：
1. 项目列表：最近/归档/模板；大小、最后运行、当前 Take、交付状态。
2. 存储：按项目/缓存/预览/交付分类统计；配额告警；一键清理预览/旧帧（保留当前 Take）。
3. 归档：项目打包（文档+产物+manifest+lock）→ zip；可恢复。
4. 备份：定时/手动到本地目录；校验 sha；恢复演练。
5. 删除：软删除 30 天；硬删除需输入项目名；被引用资产保护。
6. 交接包：项目 + 文档版本 + 环境锁 + 复现步骤；换机导入即跑。

**验收**：
- [ ] 存储页显示 4 类占用；清理预览缓存不影响 final。
- [ ] 归档→删除→导入→恢复，产物/审批/版本完整。
- [ ] 交接包在另一台 Mac 导入后可跑 5s 黄金项目。
- [ ] 硬删除有二次确认与 audit。

**依赖**：FR-28、FR-38。

---

#### FR-48 可观测性（P2 / R4.0）

**目标**：知道时间花在哪、为什么失败、缓存有没有效。

**行为**：
1. 甘特图：节点/场景/帧段时间轴；锁等待；门等待。
2. 吞吐：帧/分钟、场景/分钟、Chrome 利用率、ffmpeg 利用率；按 profile。
3. 缓存：命中率、复用帧数、失效原因 Top 10。
4. 失败分类：按 error_code/节点/场景聚合；趋势。
5. 成本：每片耗时、每场景耗时、返工次数；导出 CSV。
6. 告警：磁盘 <10GB、LUFS 连续失败、渲染超时、Chrome 残留。
7. Run 报告 v2：包含以上 + 审批 + 环境锁 + 权利。

**验收**：
- [ ] 甘特图能看出 F02 的 948 帧按场景分布与锁等待。
- [ ] 缓存页显示「本次复用 312/474 帧，命中原因」。
- [ ] 失败 Top 10 可下钻到节点/场景/日志。
- [ ] 报告可导出 HTML/JSON，含所有指标。

**依赖**：FR-22、FR-29。

---

#### FR-49 审片包/协作边界（P2 / R4.0）

**目标**：不建云，也能和外部审片人协作。

**行为**：
1. 审片包：`review-package.zip` = review mp4 + review.json + README + 校验 sha。
2. 外部审片：任意播放器看片；用 FilmFlow 只读模式导入包→批注→导出。
3. 回传：导入 review.json，按 `comment.id` 去重合并；冲突（同一帧不同意见）保留双方。
4. 只读模式：无项目根写权限；只能批注/导出；不可运行/改文档。
5. 版本：审片包绑定 Take + 时间码；Take 变更后旧批注标「过期」。
6. 不做账号、不做云端、不做实时协作。

**验收**：
- [ ] 审片包在另一台机器导入，10 条批注回传合并无丢失。
- [ ] 同一帧两条冲突意见都保留，UI 可对比。
- [ ] 只读模式无法触发运行/保存。
- [ ] Take 变更后旧批注显示「基于旧版」并可跳转对比。

**依赖**：FR-33、FR-38。

---

## 8. 关键子系统规格

### 8.1 Scene DSL 与编译器

**设计目标**：声明式、确定性、引擎无关、可 diff、可校验。  
**编译链**：

```
timeline.doc + scene.template + tokens.lock + layout.profile
        │
        ▼  compile(base)  [D01，纯函数]
scenes/<sid>.base.program.json ──► D02 still_spec（静帧）
        │
        ▼  merge(camera)  [E03，同一编译器]
scenes/<sid>.program.json ──► E04 transitions.json
        │
        ▼  validate / capability check  [E05/F02 合成转场]
renderer
```

**校验规则**（编译期，全部给字段路径）：
1. schema 版本、id 唯一、duration >0、fps/画幅来自 profile。
2. 图层 id 唯一；z 排序稳定；box 在画布内（允许出血但标记）。
3. 文字：字体存在、字重存在、字号 ≥ profile 最小值、`maxWidth` 内可断行、字数 ≤2000。
4. 关键帧：时间单调、值在范围、ease 合法。
5. 组件：存在、props 符合 schema、capability 支持。
6. 资源：图片/字体/音频 sha 存在；许可字段存在。
7. 禁止项：`script`、`eval`、`fetch`、`Date.now`、无种子 `random`。
8. 引擎能力：program 使用的 element/transition 必须在 `capabilities` 内；否则 `E_CAPABILITY_MISSING`（可 `approximate` 降级并记录）。

**Canonical JSON**：键排序、数字固定 6 位小数、去除空白；用于 `scene_hash`。  
**编译确定性**：同一输入 + 同一 compiler version → 同一 program 字节。  
**版本**：`filmflow.scene/1`；不兼容变更升 `/2` + 迁移器。

### 8.2 场景级增量渲染算法

```
prev = read_manifest(run) or empty
layout_changed = timeline.order/duration changed
for scene in timeline.scenes:
    h = sha256(canonical(program) | tokens_lock | engine_sha | font_sha | profile | renderer_ver
               | transitions_sha(affected_scene))
    dirty = (prev.hash(scene) != h) or layout_changed
    if scene.transition_out changed: mark scene and next dirty
    range = [round(start*fps), round(end*fps))
    if dirty: plan.append(scene, range)
for frame in [0, frames):
    if frame not in any dirty range: reuse existing file
render plan (scene order, fail_fast=false)
write manifest (status/ms/reused/rendered)
```

**帧所有权**：`floor(t*fps)` 落在 `[start,end)` 的场景；转场帧归**进入场景**，但依赖**离开场景** program，因此两者都标脏。  
**时长/顺序变化**：从变化场景到片尾全部重渲（帧号位移，不能复用旧索引）。  
**复用方式**：同路径保留，不复制；需要移动时用 `os.link`（同卷）或复制。  
**失败隔离**：场景失败 → 该场景帧缺失 → F03 汇总；其他场景继续。  
**幂等**：同一 `(scene_hash, profile)` 渲染结果必须一致；重复渲染覆盖同帧。  
**存储**：`out/frames/%04d.png` 保持扁平（ffmpeg 兼容）；manifest 是唯一映射。  
**清理**：切 profile 不删另一 profile；GC 按「非当前 Take + 非 final」策略。

### 8.3 预览服务

| 接口 | 请求 | 返回 | 预算 |
|---|---|---|---|
| `POST /api/projects/:id/preview/still` | `{sceneId, time, profile}` | PNG（同步）或 `202 {jobId}` | p50 ≤2s / p95 ≤6s |
| `POST /api/projects/:id/preview/segment` | `{sceneId, start, end, profile}` | `202 {jobId}` → mp4 | ≤20s（5s 片段） |
| `POST /api/projects/:id/preview/film` | `{profile:"draft"\|"review"}` | `202 {jobId}` → mp4 | draft ≤8min |
| `GET /api/preview/jobs/:id` | — | `{status, url, eta, error}` | — |
| `DELETE /api/preview/jobs/:id` | — | 取消 | ≤1 帧 |
| `GET /api/projects/:id/preview/cache` | — | 命中/大小 | — |

**预览 URL**：单帧 `entry.still_spec?mode=preview&spec=...&scene=S03&t=17.2`；片段 `entry.film_spec?mode=preview&binding=...&transitions=...&start=16&end=21`。  
**优先级**：preview(100) > interactive(80) > batch(40) > delivery(20)。  
**串行约束**：预览与 D02/E05/F02 共用 `chrome-queue=1`；**不新开第二个浏览器**；预览只是在队列中优先，不是并行。  
**抢占**：只在帧边界；批渲染每 10 帧检查一次；预览等待上限 3s，超时返回 `E_PREVIEW_BUSY` + ETA。  
**缓存键**：`sha256(scene_hash | time | profile | renderer_ver)`；LRU 500MB/项目。  
**一致性**：单帧预览用 D01 base program，片段预览用 E03 motion program；与同 profile 的 PreviewService/E05 渲染帧同 shader；与 final 归一化后抽检 SSIM ≥0.98。  
**安全**：预览不写 `out/frames`、不产生 Approval；门之前加水印；不暴露项目路径（URL 走 `/project/` 白名单）。

### 8.4 时间轴编辑器

**数据流**：本地 doc → 250ms 防抖 → 预览（不落盘）→ 2s 自动保存 → 版本。  
**交互**：
- 拖动场景块：`Shift` 不 ripple；`Alt` 关闭吸附；拖边改时长；双击进场景。
- 分割：播放头处 `S`；合并：选中相邻 `M`；复制：`Cmd+D`。
- 文字：双击画布文字 → 内联编辑；`Esc` 退出；`Enter` 换行。
- 关键帧：右键属性 → 添加关键帧；曲线视图拖点；`Delete` 删除。
- 播放：`Space`、`J/K/L`、`←/→`、`I/O`、`Home/End`。
- 缩放：`+/-`、`F` fit、`Shift+滚轮` 横向。
**约束**：
- 场景最短 0.5s；相邻不重叠；总时长 = 最后场景 end。
- 读时不足 → 黄色警告；严重不足 → 阻止保存（可强制）。
- 转场时长 ≤ 相邻场景最短时长的一半。
**性能**：100 场景/500 图层 60fps；虚拟化渲染；缩略图懒加载。  
**可访问性**：全部操作有键盘路径；焦点可见；对比度 ≥4.5:1。

### 8.5 渲染档位与 QA 矩阵

| 检查 | draft | review | final |
|---|---|---|---|
| 帧数/时长/分辨率 | ✅ | ✅ | ✅ |
| 缺帧/黑帧 | ✅ | ✅ | ✅ |
| 重复帧 | 忽略 | 警告 | 警告 |
| 运动切点/静态段 | 忽略 | ✅ | ✅ |
| 音画同步 | 忽略 | 有临时音则 ✅（真计算） | ✅ |
| LUFS/TP | 忽略 | 有临时音则 ✅ | ✅ |
| SSIM vs 帧 | 忽略 | 抽 3 帧 | 抽 9 帧 ≥0.98 |
| 字幕/封面 | 忽略 | 忽略 | ✅ |
| 许可 | 忽略 | 警告 | 阻断 |

**时间预算**（40s 片：final 948 帧 / draft 474 帧，M 系列 Mac，SwiftShader）：draft ≤8min；review ≤18min；final ≤30min。超时即失败并给 profile 建议。

### 8.6 交付与 QC

**变体矩阵**：

| id | 画幅 | 分辨率 | 布局 | 字幕行宽 | 封面 |
|---|---|---|---|---|---|
| `16x9` | 16:9 | 1920×1080 | 基准 | 16 全角 | 1920×1080 |
| `9x16` | 9:16 | 1080×1920 | 单列/字号 0.85 | 12 全角 | 1080×1920 |
| `1x1` | 1:1 | 1080×1080 | 单列/居中 | 14 全角 | 1080×1080 |
| `4x5` | 4:5 | 1080×1350 | 单列/居中 | 14 全角 | 1080×1350 |

**重排规则**：文字重新断行 → 组件按列重排 → 相机 anchor 重算 → 图片按 focus point 裁切（禁止拉伸）。无法重排 → 标记 `approximate` 并人工确认。  
**字幕规则**：每行 ≤16/12 全角；≤9 字/秒；1–7s；不超安全区；中英双行时英文在下。  
**封面**：从 D02 静帧选；标题可选；安全区；导出 JPG（质量 92）。  
**QC**：见 FR-43；结果写 `qc.json`；block 不导出。  
**包结构**：见 FR-28；zip 内路径扁平、含 `README.txt`（如何播放/校验 sha）。

### 8.7 持久化队列

**状态机**：

```
queued ──lease──► running ──ok──► succeeded
  ▲                 │
  │                 ├─fail─► retry_wait ──(backoff)──► queued
  │                 ├─cancel─► canceled
  │                 └─lease expired──► queued (attempts+1)
  └──────────────────────────────────┘
```

**字段**：`priority, kind, status, payload_json, result_json, attempts, max_attempts, lease_until, heartbeat_at, parent_id, cancel_requested, progress, eta, error_code, error_msg`。  
**恢复**：启动时 `status in (leased,running) and lease_until < now` → `queued`；`attempts >= max` → `failed`。  
**容量**：`chrome-queue=1`、`ffmpeg=1`、CPU 分析 2；预览预留 1 个「帧间隙」。  
**公平**：同优先级 FIFO；批渲染每 10 帧让位预览；交付可降级到空闲。  
**孤儿清理**：`/tmp/ff-chrome-*`、8787 无主服务、`ffmpeg` 命令行含已结束 run_id。  
**隔离**：Chrome profile 路径含 `run_id/job_id`，避免并发 Run 共用 `/tmp/ff-chrome-D02` 互相踩踏。  

### 8.8 Engine Contract v2

```json
{
  "engine_id": "riso",
  "api_version": "2.0",
  "version": "2.0.0",
  "families": ["print", "collage"],
  "scene_schema": "filmflow.scene/1",
  "entry": {
    "preview": "entry/previs.html",
    "still_spec": "entry/still_spec.html",
    "film_spec": "entry/film_spec.html",
    "proxy": "entry/film_spec.html?mode=proxy"
  },
  "legacy_entry": {
    "still": "entry/still.html",
    "film": "entry/film.html"
  },
  "capabilities": {
    "elements": ["text", "shape", "image", "group", "component", "particle"],
    "components": ["paper-card", "headline", "body-block", "stamp", "arrow-grow",
                   "hand-pointer", "roller", "halftone-field", "registration-cross",
                   "evidence-card", "chart-bar", "count-up"],
    "transitions": ["cut", "match-shape", "paper-slide", "wipe", "dissolve",
                    "ink-bleed", "glitch", "push"],
    "text_animations": ["typewriter", "stagger", "mask-reveal", "line-reveal", "pulse"],
    "effects": ["halftone", "overprint", "registration", "paper-grain", "misregister"]
  },
  "limits": { "max_layers": 200, "max_text_chars": 2000, "max_fps": 30 },
  "fixtures": [
    { "program": "fixture/program-basic.json", "png": "fixture/basic.png", "ssim": 0.98 }
  ],
  "validate": "filmflow-engine validate"
}
```

**CLI**：`validate`（schema/capability/fixture）、`render`（program → PNG 序列）、`bench`（每帧耗时）。  
**兼容**：`api_version 1.x` 走 LegacyAdapter（入口 URL 模式），**仅 imported 项目**；新项目必须 2.x。**新项目禁止回退 `legacy_entry`**：缺 `still_spec/film_spec` → `E_ENGINE_API_UNSUPPORTED`，宁可阻断也不渲染参考片内容。  
**注册**：目录扫描 → contract 解析 → CLI validate → `available`；失败给缺项清单。  
**缓存失效**：contract `sha256` 进 `scene_hash`；引擎版本变更自动失效。

### 8.9 音频图

**数据**：`audio.doc.json` = tracks（voice/music/sfx）+ clips（asset, start, gain, fades, ducking）+ alignment（segments/words）+ loudnessTarget。  
**闪避**：`sidechaincompress`：`threshold=0.03, ratio=4, attack=80ms, release=350ms, makeup=1`；深度 `depthDb` 可调；曲线可视。  
**混音时长**：以 `profile.duration` 为准；音乐不足 → 循环/淡出，超过 → 淡出；**禁止** `amix duration=first` 把音乐截断到口播长度。  
**响度**：`loudnorm=I=<target>:TP=-1.5:LRA=11`；target ∈ {−14,−16,−18}；G06 按 target 校验。  
**Stems**：voice/music/sfx 分别 `-filter_complex` 输出；求和与 mix 的 LUFS 差 ≤0.5。  
**对齐**：whisper 词级 → 句级聚合；无模型 → 手动块；来源 `whisper|manual` 必须标注；每个 segment 带 `scene_id/source_span`。  
**同步度量**：每个 scene 取 `source_span` 对应 alignment segment 的 `end`，与该 scene 的 `last_text_at` 比较；`sync_dev = max(|end - last_text_at|)`；final 阈值 ≤0.15s；无 alignment → `E_ALIGNMENT_MISSING`（不静默通过）。
**许可**：music/sfx 资产必须有 `license.type/expires`；缺失/过期 → G03/G07 阻断。

### 8.10 审片批注

**模型**：`comment{id, runId, takeId, sceneId, frame, timecode, layerId?, body, author, kind(required|suggest|question), status(open|resolved), annotation{type,points,color}, createdAt, resolvedAt}`。  
**锚点**：`frame` 是权威；`timecode` 是显示；`sceneId/layerId` 用于定位；Take 变更 → 标 `stale`。  
**导出**：`review.json{v, take, comments[], summary}` + CSV。  
**导入**：按 `id` 去重；同帧冲突保留双方；合并报告。  
**审片包**：mp4 + review.json + README + sha256；只读模式。  
**与门联动**：D05/E07/F06/G07 清单显示 open comments 数；有 required open → 门不可批准（可配置）。

### 8.11 文档模型

**表**：`projectdoc(id, project_id, kind, version, base_version, content_json, hash, author, created_at)`；`docrevision(id, doc_id, version, content_json, diff_json, author, created_at)`。  
**并发**：PUT 必带 `base_version`；不匹配 → 409 + 当前内容 + 字段级 diff。  
**保存**：自动保存 2s；显式保存立即；每版写 revision；保留 100 版。  
**运行快照**：Run 启动时把 `script/timeline/profile` 复制到 `runs/<id>/docs/`；执行器只读快照。  
**缓存键**：`node_cache_key += doc_snapshot_sha`；所有读取文档的节点（B02/B03/B06/D01/E01）必须包含，否则改文档不失效（当前 B02 只依赖 B01 的缺陷）。  
**审计**：每次保存写 `audit_log`（before/after hash）。  
**迁移**：`task.json` → `timeline.doc` 一次性；旧项目只读兼容；新项目强制 doc。  
**回滚**：restore 生成新版本，不删历史；diff 可导出。  
**DB 迁移**：新增 `schema_migrations` 表；迁移脚本幂等；失败回滚；备份 `filmflow.db.bak`。

---

## 9. 对 46 节点 DAG 的影响（计数不变）

> 原则：**不新增节点**。能力通过「节点内部子流程 + 新产物 + 新参数」实现；若未来必须新增，走规格修订流程（同步 §4.8/§17/§19 + 测试 + 版本号）。

| 节点 | 变更 | 新产物/参数 | 验收 |
|---|---|---|---|
| A01 | 输出 `script.doc`（句子/停顿/重音） | `script.doc.json` | 断句可编辑；读时估算 |
| A02 | brief 进文档 | `brief.doc.json` | 版本化 |
| A04 | 预演用**用户标题**；候选 12 支持「我的文案」 | `previs` 参数 `title` | 预演图含用户标题 |
| A06 | tokens 不变；增加 `font_coverage` | `visual_tokens.json` | 缺字预警 |
| A07 | 口播方案支持 takes | `voice_plan.json` | 多 Take |
| A08 | 音乐候选带许可字段 | `music_plan.json` | 无许可阻断 |
| B01 | 从 script.doc 计算；支持目标时长反推 | `budget.json` | 误差 ≤5% |
| B02 | 输出 `timeline.doc`（场景块） | `timeline.doc.json` | 与旧 task 兼容 |
| B03 | 事件进 timeline 轨道 | `events` in timeline | 吸附/拍点 |
| B04 | 布局 profile 按变体 | `layout_tokens.json` | 4 变体 |
| B05 | 排版按变体/场景；**补 B05→C05 边** | `type_spec.json` | 进 tokens.lock；竖屏字号 |
| B06 | 只导出 task.json 到 Run 快照；imported 才写项目根 | `runs/<id>/docs/task.json` | 不写文档；快照含 doc_version |
| B07 | 校验快照（带 doc_version） | `validate_report.json` | 不一致阻断 |
| B08 | 门清单显示场景/读时/缺字 | — | 批注联动 |
| C01 | 校验 contract v2/capabilities | `engine_build.json` | 缺项阻断 |
| C02 | 字体来源/许可/版本锁定 | `font_fetch_report.json` | 可离线 |
| C03 | 全文本子集（`script.doc` + `timeline.doc` 全部文字 + UI 固定文案）；缺字 0 | `font_subset_report.json` | 缺字阻断；不读 task.json |
| C04 | embed 上限 profile；按变体 | `embed.css` | ≤512KB |
| C05 | tokens.lock 含 **visual/layout/type_spec/font_sha/engine_sha** | `tokens.lock.json` | 进 scene_hash；D01/E03 输入一致 |
| D01 | **全场景**；base program 编译；多 time | `still_spec.json` v2 | 场景覆盖 100%；timeout 30s |
| D02 | `entry.still_spec`；按 scene 出图 | `stills_manifest.json` | 用户文案 |
| D03 | 按场景记录 viewed | `viewed.json` | 全场景 |
| D04 | 场景级 QA（溢出/缺字/亮度） | `still_metrics.json` | 定位 scene/layer |
| D05 | 门清单含 diff/未看 | — | 不可漏场 |
| E01 | timeline.doc → timeline.json | `timeline.json` v2 | 帧号/秒 |
| E02 | 真实相机关键帧（解析/编辑） | `camera.json` | 预览一致 |
| E03 | **base + 相机 → motion program** + binding v2 | `scenes/*.program.json` | hash 稳定；静态部分与 base 一致；timeout 60s |
| E04 | 转场库 + 参数；**补 E04→E05/F02 两条 data 边** | `transitions.json` | 前后场 dirty；E05/F02 真正消费 |
| E05 | `entry.film_spec`：proxy 12fps（E06）+ review mp4（E07） | `proxy/`+`review.mp4`+contact sheet | 可审（临时音/无音）；timeout 1200s |
| E06 | profile 阈值；场景聚合 | `motion_metrics.json` | 定位场景 |
| E07 | 门清单含运动/批注 | — | 批注联动 |
| F01 | 服务静态资源 + program JSON | `frame_server.json` | 白名单 |
| F02 | manifest + **final profile** + 增量 + 优先级（draft/review 走 PreviewService/E05） | `render_manifest.json` | 只渲脏场景；G07 可校验 final；timeout 2700s |
| F03 | 场景级 missing/black/dup | `frame_report.json` | 定位场景 |
| F04 | profile 编码（draft/review/final） | `intermediate.mp4` | 档位正确 |
| F05 | profile QA（SSIM/帧数/时长） | `video_metrics.json` | 档位阈值 |
| F06 | 门清单含 diff/批注 | — | — |
| G01 | 多 Take  ingest | `voice_take_*.wav` | 选择主 Take |
| G02 | 对齐文档；真偏差计算 | `alignment.json` | 偏差 ≤0.15s |
| G03 | 音乐许可校验 | `music_choice.json` | 无许可阻断 |
| G04 | 拍点图 + 可编辑 | `beat_map.json` | 吸附 |
| G05 | sidechain 闪避 + 目标响度 | `mix.wav`+`ducking.json` | 深度可调；timeout 600s |
| G06 | 真同步（alignment vs events）；目标 LUFS | `audio_metrics.json` | 不再恒 0 |
| G07 | 变体/字幕/封面/zip/QC/rights；校验 final profile | `deliveries/*`+`manifest.json` | 9 文件；`E_FINAL_REQUIRED`；timeout 3600s；变体渲染持 `chrome-queue` |

**边表修正**：E04 当前出边为空；v2 增加 `E04→E05`、`E04→F02`、`B05→C05` 三条 `data` 边。节点数仍 46，边数 90→93；必须同步规格 §4.8/§17、`edges.py`、`test_dag_core`，并在 PR 描述中单列。

**版本纪律**：以上任何执行器行为变更 → `EXECUTOR_VERSION` 升级（建议 2.0.0）；否则缓存会返回旧行为（HANDOFF §7-11 的隐蔽坑）。

---

## 10. 数据模型、API 与存储变更

### 10.1 新增表

| 表 | 关键字段 | 用途 |
|---|---|---|
| `projectdoc` | project_id, kind, version, base_version, content_json, hash, author | 文档事实源 |
| `docrevision` | doc_id, version, content_json, diff_json, author | 版本历史 |
| `asset` | scope, project_id, kind, path, sha256, bytes, meta_json, tags_json, license | 资产库 |
| `comment` | run_id, take_id, scene_id, frame, timecode, layer_id, body, kind, status, annotation_json | 审片批注 |
| `delivery` | run_id, preset_id, status, artifacts_json, qc_json | 交付变体 |
| `scenestate` | run_id, scene_id, hash, status, frame_start, frame_end, ms, qa_json | 场景级状态 |
| `template` | kind, name, content_json, version | 项目/场景/交付模板 |
| `schema_migrations` | version, applied_at | 迁移 |

### 10.2 变更表

- `job`：+`priority, attempts, max_attempts, lease_until, heartbeat_at, parent_id, cancel_requested, progress, eta, error_code, error_msg`。
- `run`：+`name, notes, rating, is_current`（Take 语义）。
- `approval`：+`comments_open, comments_required`（门与批注联动）。
- `artifact`：+`scene_id, profile`（便于按场景/档位检索）。

### 10.3 新增 API（摘要）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET/PUT | `/api/projects/:id/docs/:kind` | 读写文档（带 base_version） |
| GET | `/api/projects/:id/docs/:kind/versions` | 版本列表 |
| POST | `/api/projects/:id/docs/:kind/restore` | 回滚 |
| GET | `/api/projects/:id/docs/:kind/diff` | 字段级 diff |
| POST | `/api/projects/:id/preview/still` | 单帧预览 |
| POST | `/api/projects/:id/preview/segment` | 片段预览 |
| GET/DELETE | `/api/preview/jobs/:id` | 查询/取消 |
| GET | `/api/runs/:id/render-manifest` | 渲染清单 |
| POST | `/api/runs/:id/render` | 按 profile/场景渲染 |
| GET | `/api/projects/:id/scenes` | 场景列表 |
| GET/PUT | `/api/projects/:id/scenes/:sid/program` | 场景程序 |
| POST | `/api/projects/:id/scenes/:sid/compile` | 单场景编译 |
| GET/POST/DELETE | `/api/assets` | 资产库 |
| GET/POST/PATCH | `/api/runs/:id/comments` | 批注 |
| POST | `/api/comments/:id/resolve` | 解决 |
| GET/POST | `/api/runs/:id/review-package` | 审片包 |
| GET/POST | `/api/runs/:id/deliveries` | 交付 |
| GET | `/api/deliveries/:id/qc` | QC 报告 |
| GET | `/api/jobs` / `/api/queue` | 队列 |
| POST | `/api/jobs/:id/cancel` / `retry` | 队列操作 |
| GET/POST | `/api/templates` | 模板 |
| POST | `/api/projects/:id/apply-template` | 应用模板 |
| GET | `/api/analytics/overview` | 可观测性 |
| GET | `/api/projects/:id/audio/waveform` | 波形 peaks |
| GET | `/api/projects/:id/audio/beats` | 拍点 |

### 10.4 SSE 事件新增

`preview.ready` · `preview.failed` · `scene.rendered` · `scene.failed` · `job.queued|started|progress|finished` · `doc.saved|conflict` · `comment.created|resolved` · `delivery.ready|failed`。

### 10.5 存储布局（新增部分）

```
<项目根>/
  card/
    script.doc.json
    timeline.doc.json
    task.json                 # 只读快照
    audio.doc.json
    tokens.lock.json
  scenes/
    S01.base.program.json     # D01
    S01.program.json          # E03（含相机）
    S02.program.json
    transitions.json          # E04
  renders/
    manifest.json
    draft/ review/ final/     # 可选：按 profile 分目录
  deliveries/<runId>/
    master_16x9.mp4 · master_9x16.mp4
    captions.zh.srt · cover_16x9.jpg · cover_9x16.jpg
    manifest.json · qc.json · rights.json · FilmFlow-delivery.zip
  runs/<runId>/docs/          # 运行快照（只读）
  reviews/<runId>/review.json
~/.filmflow/
  cache/preview/<project>/<scene_hash>/<time>.png
  cache/waveform/<asset_sha>/<w>.json
  （job 表复用 filmflow.db，不建独立队列库）
```

---

## 11. 非功能需求 v2

| 类别 | 要求 |
|---|---|
| 性能 | 首屏 ≤1.5s；时间轴 100 场景/500 图层 60fps；单帧预览 p50 ≤2s；5s 片段 ≤20s；draft 40s ≤8min；final ≤30min；搜索 ≤300ms |
| 确定性 | 文档 canonical hash；帧 sha 可复现；`project.lock.json` 锁引擎/字体/Chrome/ffmpeg/Python/Node；禁 `Date.now()`/无种子随机 |
| 可靠性 | job 租约/心跳/重试；崩溃恢复 ≤60s；无孤儿 Chrome/ffmpeg/8787；幂等渲染；交付包 sha 校验 |
| 可恢复 | 文档版本 100 版；Take 软删；DB 迁移备份；项目归档/恢复 |
| 安全 | 仅 `127.0.0.1`；路径白名单拒绝 `..`；上传限制（音频 ≤200MB/文本 ≤5MB/图片 ≤50MB）；DSL 禁 JS/网络；不执行用户脚本 |
| 隐私 | 不上传；预览/渲染全本地；审片包由用户手动外发；日志不含文案全文（可配置） |
| 存储 | 资产 sha 去重；预览 LRU 500MB；旧帧/归档 GC；磁盘 <10GB 告警；项目配额可配 |
| 可访问性 | 键盘全路径；焦点可见；对比度 ≥4.5:1；alt 文本；中英双语；时间码/帧号双显 |
| 可观测 | 节点/场景/帧段耗时；缓存命中；失败分类；Chrome/ffmpeg 利用率；Run 报告 v2 |
| 测试 | 单元/集成/BDD/E2E/视觉回归/性能/混沌/迁移 8 类；黄金项目 5s/15s/40s；覆盖率门槛（核心 ≥80%） |
| 兼容 | macOS 13+；Chrome 固定版本（lock 记录）；Python 3.13；Node ≥22；SQLite；旧项目只读兼容 |

**性能预算说明**：所有指标在本机 M 系列 + SwiftShader 下测量；若硬件不同，报告记录 CPU/内存/Chrome 版本，目标按比例调整但不得放宽 2 倍。

---

## 12. 发布计划与验收

### 12.1 发布节奏

| 版本 | 周期 | 范围 | 退出标准 |
|---|---|---|---|
| **R2.0 能出片** | 6 周 | FR-20/21/22/23/24/25/29/30 | 5s 黄金项目出用户文案；40s draft ≤8min；改一句 draft ≤3min；崩溃恢复 ≤60s |
| **R2.5 能审能交** | 4 周 | FR-26/27/28/31 | 全场景静帧；录/导口播+对齐；1080p+9:16+SRT+封面+zip+QC；新手 10 分钟出片 |
| **R3.0 好创作** | 6 周 | FR-32/33/34/35/36/37/38 | 时间轴/镜头/审片/音频/资产/模板/Take 全可用；单场景改→draft ≤60s |
| **R3.5 打磨** | 3 周 | FR-39/40/41 | 5 类 QA 一键修；纯键盘；规则式辅助 |
| **R4.0 能批量** | 8 周 | FR-42~49 | 4 变体；6 平台 QC；双语字幕；photo 218；10 条批量；交接包 |

### 12.2 R2.0 交付物（可演示）

1. `engines/riso/entry/film_spec.html` + `scene-kit.js`（12 组件）。
2. `scene.program` 编译器 + 校验器 + `filmflow-engine` CLI。
3. D02/E05/F02 的 v2 分支；`render.manifest` + `SceneState`；边表修复（`E04→E05/F02`、`B05→C05`）。
4. Preview Service + `/preview/still|segment`。
5. 文档模型 + 编辑器自动保存/撤销/版本。
6. 持久化 Job + 队列页 + 崩溃恢复。
7. 黄金项目 5s/15s/40s + `golden_run.py` + 视觉回归。
8. 新增 BDD 4 场景 + 单测/集成；`EXECUTOR_VERSION=2.0.0`。

### 12.3 R2.0 演示脚本（10 分钟）

1. 新建项目，输入「风从纸上起。纸不动，风先动。」，选 riso，生成。
2. 跑 A–D，看 D02 两张静帧：文字是这两句，不是 rumor。
3. 在 Studio 改第二句为「纸不动，字先动。」→ 250ms 单帧预览更新。
4. 跑 draft：3 场景/6 秒，≤2 分钟；播放带临时音。
5. 改 S02 时长 2s→3s → 只重渲 S02/S03；展示 manifest 复用帧数。
6. 杀 API 进程 → 重启 → 队列恢复；再跑完。
7. 展示黄金项目报告：SSIM/pHash/文字断言全绿。

### 12.4 DoD v2（完成标准）

- [ ] **能出片**：5s 新项目从文案到 final，画面文字 100% 是用户文案；无 rumor 内容残留。
- [ ] **能改**：改一句 → 单帧 ≤2s；脏场景 draft ≤3min；只重渲受影响场景。
- [ ] **能审**：全场景静帧；时间码批注 10 条；导出/导入往返无损。
- [ ] **能交**：1080p + 9:16 + SRT + 封面 + manifest + QC + zip；QC 全绿。
- [ ] **能恢复**：kill -9 后 60s 内续跑；无孤儿进程。
- [ ] **能回归**：rumor-39s 仍 46/46；黄金帧 SSIM ≥0.98。
- [ ] **能解释**：所有失败有 error_code + fix_hint；所有缓存命中可看键组成。
- [ ] **不退化**：原有 26 测试 + 8 UI E2E 全绿；新增测试覆盖 P0 路径。

### 12.5 验收场景（Gherkin 摘要）

```gherkin
# language: zh-CN
功能: 参数化新项目出片
  场景: 5 秒新项目渲染用户文案
    假如 我新建项目并输入文案 "风从纸上起。纸不动，风先动。"
    并且 我选择 riso 风格并批准 B08
    当 我运行到 F06
    那么 D02 静帧的文字应为 "风从纸上起"
    并且 成片抽帧中不应出现 "谣言" 字样
    并且 master.mp4 时长应为 5.0 秒 ±1 帧

  场景: 单场景增量渲染
    假如 40 秒项目已完成一次 final
    当我 只修改 S03 的一句文案
    那么 只有 S03 与相邻转场帧被重渲
    并且 复用帧数占总帧数 ≥75%
    并且 F02 墙钟 ≤ 全量渲染的 20%

  场景: 预览优先级
    假如 F02 正在批量渲染
    当我 请求 S03 的单帧预览
    那么 预览在 6 秒内返回
    并且 批量渲染不失败
    并且 预览图与 final 同帧 SSIM ≥0.995

  场景: 交付包完整性
    假如 当前 Run 已通过 F06 与 G06
    当我 执行交付
    那么 生成 16:9/9:16 两个 master、中文字幕、两版封面、manifest、qc、rights 与 zip
    并且 所有 QC 项为 pass
    并且 manifest 含全部产物 sha 与 9 条审批
```

---

## 13. 风险与决策

### 13.1 需要老板拍板的 6 个决策

| # | 决策 | 选项 | 建议 | 影响 |
|---|---|---|---|---|
| **D1** | 先做哪条线 | A. R2 能出片优先；B. R3 时间轴优先；C. 并行 | **A** | B 会让「新项目仍出不了片」再拖 6 周；A 是生死线 |
| **D2** | 是否保持 46 节点 | A. 不变，场景子流水线；B. 扩到 52+ 节点 | **A** | B 要改规格/门/测试/文档，风险高、收益低 |
| **D3** | Scene DSL 开放性 | A. 封闭组件库（无任意 JS）；B. 允许项目自定义 JS | **A** | B 破坏确定性/安全/可复现；引擎包可扩展 |
| **D4** | 门之前能否预览 | A. 允许 draft+水印，不进 final；B. 仅门后 | **A** | B 会让创作循环又回到「先批后看」；A 需明确水印/审计 |
| **D5** | 首批交付规格 | A. 16:9 + 9:16 + SRT + 封面；B. 只 16:9；C. 全平台 | **A** | B 不满足短视频；C 摊薄 R2 |
| **D6** | 是否允许本地规则式创作辅助 | A. 允许（无生成模型）；B. 不允许 | **A** | B 保留「从文案到分镜」门槛；A 必须坚持规则化/可解释/不联网 |

> 另需运营决策（不阻塞开发）：**D7 whisper 模型**——下载 `ggml-medium`（带 sha）还是继续手动回退？建议 medium + 下载器 + 手动回退。

### 13.2 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | Scene DSL 表达力不足，复杂镜头做不出来 | 高 | 高 | v1 只 12 组件/8 转场；`text/shape/image` 兜底；v1.1 按真实项目补组件；DSL 版本化 |
| R2 | film_spec 性能不达标（SwiftShader） | 中 | 高 | draft 540p/12fps；场景并行受 Chrome 1 限制；预览抢占；bench 门槛 |
| R3 | 增量渲染的帧所有权/转场边界出错 | 中 | 高 | manifest 单一事实源；黄金项目覆盖「改时长/改转场/换序」；F03 场景校验 |
| R4 | 文档迁移破坏 rumor-39s 回归 | 中 | 高 | 旧项目只读兼容；黄金回归门禁；迁移器 dry-run + diff |
| R5 | 预览抢占导致批渲染饥饿 | 中 | 中 | 每 10 帧检查；预览预算 ≤20% 时间片；等待上限 3s |
| R6 | 交付多规格重排质量差 | 高 | 中 | 先安全区重排 + 人工确认；`approximate` 标注；不做智能裁切承诺 |
| R7 | 音频许可/字体许可缺失 | 中 | 中 | 资产许可必填；G03/G07 阻断；rights.json |
| R8 | 范围过大（30 FR） | 高 | 高 | 严格按 R2/R2.5/R3/R4 门禁；R2 只做 8 个 FR；未过验收不进入下一阶段 |
| R9 | 用户不愿学时间轴/DSL | 中 | 中 | 模板 + 规则式辅助 + 默认值；所有 DSL 藏在 UI 后；高级用户可看 JSON |
| R10 | 存储增长（多 profile/变体/帧） | 中 | 中 | sha 去重；GC；配额；只保留当前 Take 的 final + 预览 LRU |

### 13.3 开放问题（不阻塞 R2）

1. photo 引擎的美术方向：剧照/胶片/渐变/颗粒，是否需要图片素材库？
2. 9:16 重排是否要「智能构图」（人脸/主体检测）——本机可用 OpenCV，但增加复杂度。
3. 多语言配音是否要本地 TTS（如 macOS `say`）作为占位——仅 draft，不进 final。
4. 批量是否需要「夜间自动跑」——可用本地 cron/队列，不引入云。
5. 是否支持 Windows/Linux——当前 macOS；跨平台主要是 Chrome/ffmpeg 路径与字体渲染差异。

---

## 14. 附录

### 14.1 关键界面线框

**Studio（创作主界面）**

```
┌──────────────────────────────────────────────────────────────────────┐
│ FilmFlow 项目名   [draft|review|final]  [预览当前句]  [运行]  [交付]  │
├──────────────┬───────────────────────────────────────┬───────────────┤
│ 场景/文案     │                                       │ Inspector     │
│ S01 0.0-9.0  │           画布 / 播放器                │ 图层          │
│  S02 9.0-16  │        （单帧预览 / 片段播放）          │ 文字/版式     │
│  S03 16-24   │                                       │ 相机/动画     │
│  + 新场景     │                                       │ 组件 props    │
├──────────────┴───────────────────────────────────────┴───────────────┤
│ 时间轴：V1 [S01][S02][S03][S04][S05]                                  │
│        A1 ~~~~ 口播 ~~~~   A2 ~~~ 音乐 ~~~   M1 事件标记              │
│ 播放头 00:17:12 / 00:39:12   帧 412/948   [J][K][L]  [Fit]           │
└──────────────────────────────────────────────────────────────────────┘
```

**Review（审片）**

```
┌──────────────────────────────────────────────────────────────┐
│ Take 3 · 00:17:12 · 帧 412     [逐帧] [循环] [对比 Take 2]   │
│                                                              │
│                 画面（可框选/箭头/画笔）                       │
│                                                              │
├──────────────────────────────┬───────────────────────────────┤
│ 批注列表（按时间）             │ 当前批注                       │
│ 00:17 这个字太大  [必改]      │ 场景 S03 / 图层 L_title        │
│ 00:21 转场太快    [建议]      │ 回复 / 解决 / 指派             │
└──────────────────────────────┴───────────────────────────────┘
```

**Delivery（交付）**

```
┌──────────────────────────────────────────────────────────────┐
│ 交付 · Run #12 · final 已通过                                 │
│ 变体：☑ 16:9  ☑ 9:16  ☐ 1:1  ☐ 4:5                         │
│ 字幕：☑ 中文 SRT  ☐ 英文  ☐ 烧录                              │
│ 封面：S03 帧 412  [换一张]                                    │
│ QC：✅ 时长 ✅ 码率 ✅ LUFS ✅ 字幕 ✅ 封面                   │
│ [生成交付包]  [下载 zip]                                      │
└──────────────────────────────────────────────────────────────┘
```

### 14.2 新增错误码

`E_DOC_CONFLICT` · `E_DOC_SCHEMA` · `E_PROGRAM_INVALID` · `E_CAPABILITY_MISSING` · `E_COMPONENT_UNKNOWN` · `E_FONT_GLYPH_MISSING` · `E_TEXT_OVERFLOW` · `E_PREVIEW_BUSY` · `E_PREVIEW_CANCELED` · `E_RENDER_DIRTY_PLAN` · `E_SCENE_FAILED` · `E_FINAL_REQUIRED` · `E_JOB_LEASE_LOST` · `E_JOB_CANCELED` · `E_ALIGNMENT_MISSING` · `E_LICENSE_MISSING` · `E_LICENSE_EXPIRED` · `E_DELIVERY_QC_FAILED` · `E_PLATFORM_SPEC` · `E_CAPTION_INVALID` · `E_ASSET_MISSING` · `E_ASSET_IN_USE` · `E_REVIEW_CONFLICT` · `E_ENGINE_API_UNSUPPORTED` · `E_EXPORT_FAILED`.

### 14.3 术语表（v2 新增）

| 术语 | 定义 |
|---|---|
| Scene DSL | 场景程序：声明式描述画布、图层、相机、转场、音频提示 |
| Program | `scene.program.json`，DSL 的实例，可直接渲染 |
| Scene Pipeline | 场景微流水线：compile → still → frames → QA → segment |
| Render Manifest | 场景→帧范围→hash→状态的清单，增量渲染的唯一依据 |
| Dirty Scene | hash 变化的场景，需要重渲 |
| Profile | draft/review/final 三种渲染档位 |
| Variant | 同一时间轴的不同画幅/平台交付 |
| Take | 一次 Run 的产物版本；可命名/评分/提升 |
| Review Package | 离线审片包（视频 + review.json + README） |
| Doc Revision | 文档版本；每次保存一条 |
| Capability | 引擎声明的元素/转场/效果支持 |
| Approximate | 引擎无法精确实现时的降级标注（不得静默） |

### 14.4 追溯矩阵（缺口 → FR → 发布）

| 缺口 | FR | 发布 | 验收 |
|---|---|---|---|
| 新项目渲染参考片 | FR-20/21/30 | R2.0 | 5s 黄金项目文字断言 |
| 静帧只覆盖 3 场 | FR-26 | R2.5 | 全场景 contact sheet |
| task.json 侧信道 | FR-25 | R2.0 | 改文档→失效正确 |
| 排版规格未进锁 | FR-20/25 | R2.0 | B05→C05；改字号失效 |
| 改一句等半小时 | FR-22/23/24 | R2.0 | 单帧 ≤2s；脏场景 ≤3min |
| 相机假 | FR-34 | R3.0 | 关键帧预览一致 |
| E04 转场死端 | FR-20/34 | R2.0/R3.0 | E04 出边；F02 合成转场 |
| 审片只能驳回 | FR-33 | R3.0 | 10 条时间码批注 |
| 音频靠 driver | FR-27/35 | R2.5/R3.0 | 录音/对齐/闪避/Stems |
| 交付单规格 | FR-28/42/43/44 | R2.5/R4.0 | 4 变体+字幕+封面+QC |
| 崩溃不可恢复 | FR-29 | R2.0 | kill -9 后 60s |
| 无资产/模板/批量 | FR-36/37/46 | R3.0/R4.0 | 10 条批量 |
| 61/341 可生产 | FR-45 | R4.0 | ≥218 |
| 监控只有表格 | FR-48 | R4.0 | 甘特/吞吐/缓存 |

### 14.5 基线测量方法

- **TTFW**：从 `POST /projects` 或 `materialize` 到 draft 可播（含 gate 批准），前端埋点 `project.created` → `delivery.draft.ready`。
- **单帧预览**：Preview Service 记录 `queued_at/render_start/first_byte`；p50/p95 按 100 次采样。
- **脏场景重渲**：F02 报告 `renderedFrames/reusedFrames/duration_ms`；黄金项目固定脚本。
- **崩溃恢复**：`kill -9` API 进程，记录重启到 Run 回到 running 的时间；检查帧数/孤儿进程。
- **缓存命中**：`scene_hash` 与 manifest 对比；报告命中/总场景。
- **QA 误报**：人工抽检 50 条失败；统计「实际无问题」比例。
- **交付合规**：`qc.json` 每项实测值/阈值；平台规则版本记录。

---

## 15. 附：本 PRD 与 v1/规格的关系（防冲突）

1. **v1 FR-1~14 继续有效**；本 PRD 的 FR-20~49 是增量。冲突处（如「不做通用时间线」）按 §2.3 解释：本 PRD 的时间轴只编辑 Scene DSL，不是通用 NLE。
2. **46 节点 / 7 阶段 / 8+8 门 / caps / 三类边 / content_hash** 语义不变；**唯一例外**是修复两处边表缺陷：E04 死端（`E04→E05`、`E04→F02`）与 B05 未进锁（`B05→C05`），共新增 3 条 `data` 边（90→93），必须同步规格 §4.8/§17 与 `test_dag_core`。
3. **§19 裁决**（F03 重复帧=警告、G07 双身份、门控活同步、style-index 为 A03 产物）继续有效；本 PRD 不推翻。
4. **ADR**：ADR-0001（Python 全栈）、ADR-0002（实测矩阵）、ADR-0003（embed 上限）、ADR-0004（白天主题）继续有效；本 PRD 新增决策需另立 ADR（建议 ADR-0005 Scene DSL、ADR-0006 两级执行、ADR-0007 渲染档位）。
5. **安全边界**：仅 `127.0.0.1`、不上传、无在线生成模型、路径白名单、禁任意 shell/JS；本 PRD 所有新能力必须遵守。
6. **变更流程**：任何新增 DAG 节点、修改门语义、改变 46 计数 → 先改规格 §4.8/§17/§19 + 测试 + ADR，再实现；本 PRD 默认不新增节点。

---

*本文档为 v2.0 补充需求。老板裁决 D1–D6 后，按 §12 发布计划进入 R2.0；每期结束以 §12.4 DoD 与 §12.5 Gherkin 验收，未过不进入下一期。*

