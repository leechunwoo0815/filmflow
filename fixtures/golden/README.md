# 黄金回归锚（`fixtures/golden/<项目>/baseline_original/`）

这 6 张 1920×1080 PNG 是**回归基线本身**，不是产物、不是缓存，也不是可以顺手清掉的中间文件。
`scripts/golden_run.py --project <5s|15s|40s> --resolution original` 拿新渲染的帧与它们逐帧算 SSIM。

## 为什么"整批替换"是有意的

一次 `--update` 会**同时换掉 6 张**。这不是 churn 失控，而是设计：锚点是**一次 Run 的 6 个采样帧**，
只换其中几张会得到一个从来没被任何一次真实渲染产出过的拼图——那种锚点自洽但无意义，
用它测出来的 1.0 是假的。所以：

- 整批替换 = 一次真实 Run 的完整快照；
- 替换必须带理由：`golden_run.py --update --reason "…"`，理由写进 `spec.json` 的 `updateHistory`；
- 没有 `--reason` 时 `--update` 直接拒绝执行（P0-4b 的程序）。

## 台账在哪

| 东西 | 位置 |
|---|---|
| 锚点（当前生效的 6 张） | `fixtures/golden/<项目>/baseline_original/*.png` |
| 锚点的更新史（谁、何时、为什么换） | `fixtures/golden/<项目>/spec.json` → `updateHistory` |
| 每次验证的报告 | `docs/reports/golden/<项目>-<档>-run<id>.json`（含**环境指纹**：EXECUTOR/Chrome/ffmpeg/字体 sha） |
| 报告的归档台账 | `docs/reports/golden/index.json`（`items` = 现存，`pruned` = 被裁掉的**及其 sha256**） |
| 保留策略 | `scripts/cleanup_golden_reports.py`（默认 keep=20；被裁的报告**移动**到仓库根 `.trash/golden-reports/`，不 unlink） |
| 机检 | `scripts/verify_p1_governance.py` 第 **19** 项：报告数在保留内、`pruned` 每条有哈希、三个锚点目录各 ≥6 张 |

## 三条别做的事

1. **别只删几张 PNG**——`check_golden_churn` 会红，而且红得对。
2. **别为了 CI 变绿把锚点挪出 git**——干净机器要靠它们复现原帧回归（`bootstrap_fresh_clone.sh` 的第 5 步就在数它们）。
3. **别用 `--update` 掩盖回归**——先看报告里的 `environment` 是否与锚点一致；
   环境真变了是 H10 的"漂移诊断 + 重锚"流程，不是随手 `--update`。
