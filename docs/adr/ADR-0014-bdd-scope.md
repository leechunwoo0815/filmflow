# ADR-0014 · BDD 规格 17:2 的处置——保留活规格、登记死规格、不造假绑定（P2-25 裁决）

日期：2026-11-06 · 状态：已裁决 · 关联：专家账本 P2-25、整夜任务书 B6

## 背景

`bdd/features/` 有 17 个 `.feature`（仓库根，不入 pytest 收集路径），只有 2 个有真正的
pytest-bdd 绑定（`server/tests/bdd/test_style_indexing_bdd.py`、`test_r2_workbench_bdd.py`，
共 7 条测试）。专家 P2-25：规格与执行脱节——文件存在却从不运行，给读者"已覆盖"的错觉。

## 裁决

**不造假绑定，两步走：**

1. **本批（2026-11-06 夜）**：给 15 个未绑定 feature 的头部加 `@unbound` 标记注释，
   并写明每个的"为什么还没绑"（覆盖面已被哪些 pytest 用例替代 / 依赖的 UI 还不存在 /
   依赖多机环境）。**不改运行面**：pytest 收集数不变（384）。
2. **后续批**：按价值逐个真绑（每绑一个 = 删一个 @unbound）；优先级 =
   `gates.feature`（人工门语义）> `cache-invalidation.feature`（B9 缓存语义）>
   `resume.feature`（断点续跑）。全部真步骤实现，不写空壳。

## 逐个理由（15 个 @unbound）

| feature | 为什么暂不绑 |
|---|---|
| platform | 4 场景分别被 Take 对比验收（verify_r3_takes）、审计守卫、SSE 通道、版本链单测覆盖——先重复后绑会双维护 |
| wizard | 5 步向导已有 e2e_ui.py 全流程真跑（8 场景），BDD 绑定是第二份实现 |
| render-pipeline | 46 节点链路被 golden + 渲染级 E2E（test_qa_extend_scene_render）+ verify_r2_5 全覆盖 |
| gates | **待真绑（优先级 1）**——人工门语义目前只有零散单测 |
| cache-invalidation | **待真绑（优先级 2）**——语义已被 test_cache_hit_material + test_cache_inputs 钉住，但场景化的失效传播值得场景化表达 |
| resume | **待真绑（优先级 3）**——resume_run 有单测，缺断点续跑的端到端场景 |
| audio-delivery | 被 verify_r3_audio_v2 + verify_r2_5_delivery_40s 全覆盖 |
| quality-gates | G 门阈值被 _validate_master_qc 单测 + G06 LUFS 验收覆盖 |
| execution-caps | caps 语义被 test_cache_inputs/快照 caps 单测覆盖 |
| engine-registry | 引擎登记被 C01/Contract v2 校验测试覆盖 |
| style-discovery / style-selection / style-indexing-manual | 搜索/选择被 BDD 绑定的 style-indexing 兄弟文件 + verify_r3_templates 覆盖；manual 变体依赖人工确认步骤，本来就不可自动化 |
| previs | 预演被 preview 单测 + e2e_assets/previs 冒烟覆盖 |
| task-card-editor | 任务卡编辑被 B06 写路径单测覆盖 |

## 结论

- 不删任何 feature（规格文本是 PRD 的可读投影，留着当验收对照）。
- 不写没有断言的空壳步骤（那比没有更糟——假绿）。
- 专家 P2-25 的"沉默"以本 ADR + @unbound 标记终结：状态可见、路径明确。
