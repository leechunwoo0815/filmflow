# language: zh-CN
功能: F14 音频与交付
  上传 → whisper 词级对齐 → 音乐 → 混音 → 响度 QA → 打包。

  背景:
    假如 F06 画面锁定已批准

  场景: 口播上传校验
    当 我上传一段 wav
    那么 系统校验采样率转 48kHz 单声道
    而且 校验时长、峰值与噪声
    而且 超过 200MB 拒绝

  场景: whisper 词级对齐
    假如 ggml-medium 模型可用
    当 G02 执行
    那么 输出每句起止时间的 alignment.json
    而且 每句落在场景窗 ±0.3s 内
    而且 偏差超窗的句子被标记

  场景: 模型缺失不静默降级
    假如 本地与缓存均无 whisper 模型
    当 G02 执行
    那么 报 E_MODEL_MISSING
    而且 不静默回退

  场景: 手动打点回退
    当 whisper 对齐置信度低于阈值
    那么 提供手动逐句打点界面
    而且 手动结果直接写 alignment.json 并标记 manual

  场景: 音乐与混音
    当 G03 选定本地音乐并记录来源许可
    而且 G04 生成拍点图
    当 G05 混音（ducking −12dB、去低频）
    那么 输出 mix.wav 且无削波

  场景: 交付打包
    当 G07 执行
    那么 产出 master.mp4 + manifest.json + zip
    而且 manifest 包含全部产物哈希与审批记录
    而且 校验和全部可复验
    而且 G07 作为 reapprove 门需要本 Run 重新签字
