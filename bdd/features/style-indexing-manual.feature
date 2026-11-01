# language: zh-CN
功能: F02b 风格库索引 · 手动/脚本验收场景
  这两个场景需要改动真实风格库文件，由验收脚本执行，不进自动化套件。

  场景: 缺文件的条目标记 unavailable 但不隐藏
    假如 某条索引记录对应的 md 文件被移走
    当 A03 重新执行
    那么 该条目 available 为 false
    而且 选择器中仍然可见并带「缺文件」标记

  场景: 库变更导致索引漂移
    当 风格库中任何 md 文件内容变化后 A03 重新执行
    那么 index_sha 发生变化
    而且 引用旧 index_sha 的 style_decision 被标记为 stale
