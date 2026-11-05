# @unbound（P2-25/ADR-0014：caps 语义单测覆盖）
# language: zh-CN
功能: F08 能力（caps）、锁与队列
  caps 随门批准单调递增；节点执行前按 auth/minCap 校验；Chrome 全局串行。

  背景:
    假如 一个新 Run 已 materialize 且 A05 已批准

  场景: 初始 caps 只允许规划节点
    当 我尝试直接运行 D02
    那么 返回 E_PHASE_FORBIDDEN
    而且 UI 显示「等待 B08 批准」

  场景: B08 批准解锁渲染静帧能力
    假如 B07 通过且 B08 已批准
    那么 caps 包含 render_still
    而且 D02 可以执行
    而且 C01/D01 不再因门阻塞

  场景: E07 批准解锁视频与音频能力
    假如 E07 已批准
    那么 caps 包含 render_video、analyze_audio、generate_local_music
    而且 F02、G01、G02 解锁
    而且 F02 仍等待 E07 的 trigger 边

  场景: D05 未批准阻断 E 阶段
    假如 B08 已批准但 D05 未批准
    当 我尝试运行 E01
    那么 E01 blocked
    而且 其拓扑下游全部 blocked

  场景: Chrome 全局串行
    假如 D02 正在渲染静帧
    当 E05 请求 chrome-queue
    那么 E05 进入锁等待
    而且 甘特图记录锁等待时长

  场景: 队列按拓扑序且同节点不并发
    当 我 Queue Run 整图
    那么 执行顺序遵守 §4.8 边表的拓扑序
    而且 任一节点同时最多一个执行实例
