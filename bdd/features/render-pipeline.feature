# language: zh-CN
功能: F13 渲染编码流水线
  F01 端口服务 → F02 串行逐帧 → F03 完整性 → F04 编码 → F05 成片 QA。

  背景:
    假如 E07 已批准且 chrome-queue 空闲

  场景: 帧服务健康检查
    当 F01 启动
    那么 监听 127.0.0.1:8787
    而且 健康检查通过
    而且 端口被占用时可复用已有服务

  场景: 串行渲染全部帧
    当 F02 执行
    那么 按帧号 0 到 round(duration×fps)−1 串行渲染
    而且 每帧 POST 落盘并记录哈希
    而且 输出 @@PROGRESS 进度可被解析

  场景: 完整性门抓缺帧
    假如 frames/0400.png 被删除
    当 F03 执行
    那么 报告缺失帧清单包含 0400
    而且 F03 门失败

  场景: 完整性门抓黑帧与重复
    当 frames/0500.png 被替换为纯黑
    那么 F03 报告黑帧并失败
    当 重复帧比例超过 0.1%
    那么 F03 报告重复帧

  场景: 编码与规格断言
    当 F04 执行
    那么 使用 libx264 crf17 preset medium yuv420p faststart（profile 可覆盖）
    而且 F05 用 ffprobe 断言分辨率/帧率/时长与 profile 一致

  场景: 渲染期间不出现第二个 Chrome
    当 F02 渲染中
    那么 系统进程列表中 FilmFlow 启动的 Chrome 实例数为 1
