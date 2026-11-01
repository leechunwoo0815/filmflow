# language: zh-CN
功能: F02 风格库索引（A03）
  style-index.json 是 A03 的产物而不是输入：首次扫描风格提示词目录生成索引，
  并与 _统计.json 交叉核对。

  背景:
    假如 风格库根目录登记为 /Users/litianyu/Documents/fy-style-library/代码动画_341种风格提示词

  场景: 首次扫描生成索引
    当 A03 执行
    那么 生成 adapters/style-index.json
    而且 记录数 entries 等于 343
    而且 其中 kind=prompt 有 341 条
    而且 其中 kind=example 有 2 条且不入选择器
    而且 每条记录包含 id、name、kind、path、sha256、bytes、lines、has_cover

  场景: 十个来源集计数断言
    当 A03 执行完成
    那么 来源集计数为 O98 L59 M40 K38 X31 AG26 V15 Z15 H12 R7
    而且 与 _统计.json 的 bySeries 完全一致
    而且 有封面 jpg 的条目为 193 条

  场景: 库版本哈希可复现
    当 A03 连续执行两次且库未变化
    那么 两次生成的 index 内容哈希完全一致
