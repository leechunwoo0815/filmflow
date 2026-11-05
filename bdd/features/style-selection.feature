# @unbound（P2-25/ADR-0014：同上（ADR-0014））
# language: zh-CN
功能: F04 风格对比与主选（A05 门）
  对比防误选；残缺与无引擎不可主选；确认产生 style_decision 并预估失效。

  背景:
    假如 A04 已产出推荐与预演

  场景: 对比托盘最多 4 条且同一样片
    当 我把 4 条风格加入对比托盘
    那么 4 条并排展示且使用同一条预演样片
    当 我尝试加入第 5 条
    那么 系统拒绝并提示先移除一条

  场景: 用自己的标题重渲对比
    当 我在对比托盘点击「用我的标题重渲」
    那么 4 条风格用我第 1 步文案的标题重新渲染样片
    而且 一次对比内四条使用同一文案

  场景: 残缺风格不可主选
    假如 一条风格 tokens_status 为 incomplete
    当 我点击「设为主风格」
    那么 系统显示缺失字段清单
    而且 提供「加入补标队列」按钮
    而且 主选操作被拒绝

  场景: 设为主风格的确认信息
    当 我对一条可生产风格点击「设为主风格」
    那么 右侧显示将锁定的 tokens 摘要（纸色/版色/网角/周期/动效）
    而且 显示「将使 N nodes / M gates 失效」的预估
    而且 该预估来自 impact dry-run 接口

  场景: 确认生成 style_decision
    当 我确认主风格
    那么 生成 style_decision.json
    而且 包含 primary、alternates（≤2 且与 primary 同标准）、reason、author、decided_at、index_sha、constraint_report
    而且 约束检查默认只警告，hard=true 才阻断

  场景: index_sha 漂移的处理
    假如 已有 style_decision 的 index_sha 与当前 A03 不一致
    当 我打开 A05
    那么 A05 显示为 stale
    当 主风格的 md sha256 未变化
    那么 允许「复核刷新」仅更新 index_sha 并保留原批准
    当 主风格的 md 已变化或条目消失
    那么 必须重跑 A04/A05 重新选择
