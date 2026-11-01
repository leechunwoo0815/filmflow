# language: zh-CN
功能: F06 引擎包注册与可用性门
  引擎按语义族分包；App 不生成引擎代码；fixture 校验通过才 available。

  背景:
    假如 引擎注册表已启用

  场景: Engine Contract 校验
    当 我登记一个缺少 fixtures 的引擎包
    那么 注册被拒绝
    而且 错误信息指明缺失字段

  场景: riso 引擎通过 fixture 校验
    当 我登记 riso 引擎包（families: 印刷/丝网、拼贴/档案）
    而且 其 fixture 渲染与基准图校验通过
    那么 引擎状态为 available
    而且 属于这两个语义族的风格角标变为「可生产」（若 tokens 完整）

  场景: 引擎未就绪的族不可主选
    假如 手绘/卡通/3D/摄影族没有已注册引擎
    当 我选择其中任何一条风格
    那么 角标显示「引擎未就绪」
    而且 主选被拒绝并报 E_ENGINE_UNAVAILABLE
    而且 可浏览、可对比、可登记需求

  场景: 引擎升级使预演与编译失效
    当 riso 引擎包内容变化（sha256 变化）
    那么 所有 riso 风格的预演缓存失效
    而且 依赖该引擎的 C01 编译结果标记为 invalidated

  场景: E03 只产出时间轴绑定
    当 E03 执行
    那么 产物是 timeline_binding.json
    而且 不存在被生成的 film.html
    而且 film.html 由引擎包的 entry 提供
