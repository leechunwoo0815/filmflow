# language: zh-CN
功能: R2.0 制作工作台关键链路

  场景: 参数化新项目出片
    假设 5 秒文案「风从纸上起。纸不动，风先动。」
    当 编译全部场景程序
    那么 每个场景程序包含用户原文
    并且 时间轴有 2 个场景

  场景: 单场景增量
    假设 40 秒 5 场时间轴
    当 只修改 S03 的一句文案
    那么 只有 S03 及其离场转场帧脏
    并且 渲染帧数不超过总帧数的 25%

  场景: 预览优先级
    假设 队列中有 batch 与 preview 两种 Job
    那么 preview Job 的优先级是 100 且排在 batch 前面

  场景: 交付必须 final
    假设 最新 manifest 是 final
    那么 允许打包 final
    当 最新 manifest 是 review
    那么 打包被 E_FINAL_REQUIRED 拒绝
