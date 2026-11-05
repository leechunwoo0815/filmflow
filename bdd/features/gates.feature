# @unbound（P2-25/ADR-0014：待真绑（优先级 1，ADR-0014））
# language: zh-CN
功能: F09 审批门与失效
  门绑定输入 content_hash；驳回阻断；重批相同内容不产生新失效。

  背景:
    假如 Run 已执行到 B07 自动门通过

  场景: 驳回阻断下游
    当 我在 B08 驳回并填写意见
    那么 B08 的拓扑下游全部 blocked
    而且 Run 状态变为 needs_changes
    而且 审批记录保存 decision/rejected 与意见

  场景: 批准解除阻塞
    当 我逐项勾选清单并批准 B08
    那么 写入 approvals/B08.json
    而且 下游解除阻塞
    而且 caps 增加 render_still

  场景: 输入变化使门变 stale
    假如 D05 已批准
    当 D02 的静帧产物因上游重算而变化
    那么 D05 从 approved 变为 stale
    而且 其拓扑下游立即 blocked
    而且 历史审批记录保留可查

  场景: 重批完全相同内容不产生新失效
    假如 门输入 content_hash 未变化
    当 我重新批准该门
    那么 不产生任何新失效
    而且 decided_at 保留首次批准时间

  场景: reapprove 门在新 Run 必须重签
    假如 G07 的 approvalPolicy 为 reapprove
    当 我为同样内容开新 Run
    那么 G07 仍需人工重新签字

  场景: 失效预估 dry-run
    当 我请求改 F04 的 crf 前调用 impact 接口
    那么 返回 N nodes = 4（F04 F05 F06 G07）
    而且 返回 M gates 与受影响门清单
    而且 确认弹窗先于任何执行显示该预估
