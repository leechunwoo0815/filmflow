# language: zh-CN
功能: F12 质量门（静帧 / 运动 / 成片 / 字体）
  阈值按口径与风格分开；覆盖必须写进 run 报告。

  @still
  场景: 静帧阈值
    当 D04 对 3 张静帧执行 QA
    那么 断言尺寸 1920×1080（来自 profile）
    而且 断言 lum_mean ≥ 40
    而且 断言正文最小字号 ≥ 44px 档位
    而且 断言安全区 5%宽 8%高
    而且 任一硬失败都会让 D04 门失败

  @motion
  场景: 代理口径的静态段与死开头
    假如 E06 输入 474 帧 12fps 代理
    当 前 14 代理帧完全相同
    那么 报告死开头警告（前 6 帧内有变化为通过线）

  @motion
  场景: 代理口径切点必须绑定转场
    当 代理帧差在 9.0s 处达到 13.51 且无 transition 记录
    那么 产生切点警告
    而且 绑定 transition 后警告消除

  @motion
  场景: pacing 覆盖留痕
    当 visual_tokens.motion.pacing 为 slow
    那么 静态段容忍为成片 24 帧 / 代理 12 帧
    而且 切点阈值为 4/6
    而且 覆盖值写进 run 报告

  @final
  场景: 成片 QA
    当 F05 对 intermediate.mp4 执行
    那么 断言帧数 = round(duration × fps)
    而且 断言抽帧 Y 平面 SSIM ≥ 0.98
    而且 ffprobe 规格与 profile 一致

  @final
  场景: 音频响度门
    当 G06 对 mix.wav 执行
    那么 断言 integrated loudness 在 −16 LUFS ± 1
    而且 断言 true peak ≤ −1.5 dBTP
    而且 断言口播-画面偏差 ≤ 0.15s

  @fonts
  场景: 字体覆盖率缺字
    假如 本片字集包含某个字符
    当 从 woff2 中去掉该字后执行 C03
    那么 C03 失败
    而且 报告列出缺失的具体字符
