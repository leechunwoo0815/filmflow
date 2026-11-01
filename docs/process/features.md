# Feature 拆分总表（Epic → Feature → Story → Gherkin → Fixture）

> 版本 v1.0 · 本表是开发排期与追溯的唯一入口。Size：S ≤1 天 / M 1–3 天 / L >3 天（按开发模型连续工作折算，非人日）。

## Epic A · 首屏与风格系统（M0）

| F-ID | Feature | 关键 Story | Size | Gherkin | 夹具 |
|---|---|---|---|---|---|
| F01 | 新建项目向导与项目导入 | 5 步向导、drafts 恢复、materialize 前置门、导入 rumor-39s | M | wizard.feature | 参考项目目录 |
| F02 | 风格库索引（A03） | 首扫生成 index、341/343/10 集断言、缺文件 unavailable、重索引漂移 | M | style-indexing.feature | 真实风格库 |
| F03 | 风格发现与筛选 | 中文子串搜索、7 chips、推荐 12（冷启动 5 族）、长尾无死条目、角标优先级 | L | style-discovery.feature | 341 真实 md |
| F04 | 风格对比与主选（A05 门） | 托盘 ≤4 同样片、残缺不可主选、tokens 摘要 + impact 预估、index_sha 漂移 | M | style-selection.feature | — |
| F05 | 预演渲染器（Previs） | 仅服务 ≤53 无封面完整条目、缓存键含 engine sha、失败占位、串行队列 | M | previs.feature | 封面×tokens 矩阵 |
| F06 | 引擎包注册与可用性门 | Contract 校验、riso fixture 通过→available、未就绪阻断 E_ENGINE_UNAVAILABLE | M | engine-registry.feature | riso fixtures |

## Epic B · 任务卡（M0 骨架 / M1 完整）

| F07 | 任务卡编辑器 | 无卡不进 B07 之后、导入 phase 一致性、错误定位到字段、阅读窗实时校验 | L | task-card-editor.feature | 正常/异常 task.json |

## Epic C · 执行引擎（M1/M2）

| F08 | 能力、锁与队列 | caps 单调递增、E_PHASE_FORBIDDEN、chrome-queue 全局 1、拓扑队列 | L | execution-caps.feature | — |
| F09 | 审批门与失效 | 驳回阻断、content_hash→stale、重批同内容不失效、reapprove、impact dry-run | L | gates.feature | 审批夹具 |
| F10 | 缓存与失效传播 | crf 只动 F04/F05/F06/G07、文案动全链、cached 命中、强制重跑 | M | cache-invalidation.feature | — |
| F11 | 断点续跑 | kill 后补缺帧（frames+proxy）、Run 恢复 running | M | resume.feature | 缺帧/断点夹具 |

## Epic D · 质量门（M1 静帧 / M2 运动·成片）

| F12 | 质量门（四组） | 静帧阈值、运动代理口径、成片 QA、字体覆盖率；pacing 覆盖留痕 | L | quality-gates.feature | 黑帧/死开头/切点/缺字夹具 |

## Epic E · 渲染编码（M2）

| F13 | 渲染编码流水线 | F01 端口服务、F02 串行 948 帧、F03 抓缺帧/黑帧、F04 编码、F05 SSIM | L | render-pipeline.feature | 缺帧/黑帧夹具 |

## Epic F · 音频交付（M3）

| F14 | 音频与交付 | whisper 词级对齐、E_MODEL_MISSING、手动打点回退、混音/LUFS、manifest 打包 | L | audio-delivery.feature | 口播样本、模型 |

## Epic G · 平台（M4）

| F15 | 版本、导入导出、审计与监控 | Take 对比、提升为当前、sources.json 换机、审计日志、SSE 事件、Run 报告 | M | platform.feature | — |

## 追溯矩阵（列摘要）

每条 .feature 场景必须可追溯到：`FR-xx（PRD）→ 节点 ID（规格 §4）→ 夹具（规格 §14）→ E2E 场景（Playwright）`。
实现时的绑定写在 step-definitions 文件头注释，本表不重复。当前矩阵覆盖率目标：M0 五个 Feature 100% 有 gherkin；M1–M4 开工前一周补齐对应文件。
