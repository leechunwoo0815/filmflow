# @unbound（P2-25/ADR-0014：平台层场景已被 Take 验收/审计守卫/SSE/版本链单测覆盖（见 ADR-0014））
# language: zh-CN
功能: F15 版本、导入导出、审计与监控
  平台层能力：Take 管理、可移植、审计、事件流、运行报告。

  场景: Workflow 版本快照
    当 我修改画布并保存两次
    那么 生成 v2 与 v3 快照
    而且 可回滚到任一版本

  场景: Take 对比与提升为当前
    假如 同一 workflow 跑了两个 Run
    当 我对比两个 Take
    那么 显示指标差异与产物差异
    当 我把 Run-2 提升为当前
    那么 项目当前产物指针指向 Run-2 的产物

  场景: 换机导入
    当 我把 workflow.json + sources.json 导入另一台机器
    那么 系统提示重新登记风格库根目录
    而且 vendored 的 tools/ 直接可用
    而且 whisper 模型缺失时报 E_MODEL_MISSING 而不是崩溃

  场景: 审计日志
    当 我修改参数、运行节点、批准门、删除产物
    那么 每个操作记入 audit_log（actor/action/target/before/after/at）
    而且 日志不可篡改

  场景: SSE 事件流
    当 Run 执行时我订阅 /api/runs/:id/events
    那么 依次收到 node.started / node.progress / node.succeeded
    而且 门变 stale 时收到 gate.stale
    而且 SSE 是唯一实时通道

  场景: Run 报告导出
    当 我导出某次 Run 的报告
    那么 JSON/HTML 包含全部指标、审批记录与产物哈希
    而且 血缘可从任意产物回溯到节点、参数与输入
