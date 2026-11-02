# R2.0 验收报告（2026-11-02）

> 范围：FR-20/21/22/23/24/25/29/30。结论：**DoD 通过**。未开始 R2.5。

## 1. 代码与标签

| Phase | 标签 | 提交 |
|---|---|---|
| 0.1–1 基线/边表 | `r2-edge-fix` | `4f9e381` |
| 3 Scene DSL | `r2-scene-dsl` | `53e6462` |
| 4 增量 | `r2-incremental` | `07b5237` |
| 5 预览 | `r2-preview` | `25ff0d9` |
| 6 档位 | `r2-profiles` | `426aa20` |
| 7 Job/恢复 | `r2-jobs` | `f5d5de1` |
| 8 黄金/回归 | `r2-golden` | `371ea4b` |

测试：`83 passed`（unit 64 / integration 12 / BDD 7）；`EXECUTOR_VERSION=2.4.2`。
执行器：`46 节点 / 7 阶段 / 93 边` 不变。

## 2. DoD

| 验收项 | 结果 | 证据 |
|---|---|---|
| 5s 新项目全链出用户文案 | PASS | `fixtures/golden/5s`；run 152；D02/F02 用户文案 |
| 5s 改 S02 只渲 S02+邻接 | PASS | 66/120；`verify_r2_5s_incremental.py` |
| 40s 改 S03 只渲脏场景 | PASS | 93/960=9.69%；F02 墙钟 13.05%（run 154→155） |
| 预览 F02 中 p50/p95 | PASS | attached 1.50s / 1.92s；`verify_r2_preview.py` |
| 5s 片段预览 ≤20s | PASS | 13.2s；960×540/12fps/5.000s |
| 预览缓存 ≤300ms | PASS | 5ms；同参数二次命中 |
| 预览不污染 final | PASS | `frame_delta=0`，Artifact/Approval 不增加 |
| 档位 D02/E05/F02/G07 | PASS | D02 review/draft 双静帧；E05 720p/24；F02 only-final；`E_FINAL_REQUIRED` |
| 40s draft/review/final | PASS | draft 100.3s / review 245.6s / final F02 108.5s（全链 4:25） |
| Job kill -9 ≤60s | PASS | F02 22.3s；frames=120；单 Job attempts=1 |
| 黄金 5s/15s/40s | PASS | 6 帧 SSIM 1.000000 / pHash 0；baseline 入库 |
| 干净 rumor imported legacy | PASS | 46/46 succeeded；master 39.500s、H.264+AAC、70,204,586 bytes |
| BDD | PASS | 参数化出片/单场景增量/预览优先级/交付 final |

## 3. 复现命令

```bash
./dev.sh
cd server && uv run pytest tests -q                              # 83 passed
cd .. && uv run --project server python scripts/e2e_ui.py        # UI 8 场景
uv run --project server python scripts/smoke_m1.py               # 46 / 93
uv run --project server python scripts/verify_r2_5s_incremental.py
uv run --project server python scripts/verify_r2_preview.py
uv run --project server python scripts/verify_r2_profiles.py
uv run --project server python scripts/verify_r2_recovery.py     # 会重启 dev.sh
uv run --project server python scripts/golden_run.py --project 5s
uv run --project server python scripts/golden_run.py --project 15s
uv run --project server python scripts/golden_run.py --project 40s
```

更新基线只在有意改视觉时：`golden_run.py --project <name> --update`。

## 4. 关键产物

- 5s 黄金：`fixtures/golden/5s/baseline/`（6 帧 480×270 + pHash）
- 15s 黄金：`fixtures/golden/15s/baseline/`
- 40s 黄金：`fixtures/golden/40s/baseline/`
- 40s 全量/增量：`filmflow-projects/golden-40s-134`（run 154→155）
- 干净 rumor：`filmflow-projects/rumor-clean-20261102`（run 150）
- 预览证据：`filmflow-projects/r2-preview-117/out/preview/`（另有 Phase 5 验收项目）

## 5. 已知缺口（不阻塞 R2.0）

1. 预览/档位 UI 未接线；时间轴/审片 UI 属 R3。
2. G05 `amix duration=first` 与 G06 完整同步阈值为 R2.5；G06 已标 `sync_verified/approximate`。
3. 干净 rumor 使用 manual 对齐（本机无 whisper CLI/model，ADR D7 允许）。
4. 黄金 baseline 与 H2/1920×1080/24fps、当前字体/style 库绑定；换库需确认后 `--update`。
5. Job 恢复为单 API worker 假设；多 worker 抢占不支持。
6. 非 riso 引擎仍 Contract 1.0，新项目被 C01 阻断（R2.0 范围外）。
