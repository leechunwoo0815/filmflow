# FilmFlow

本地代码动画全生命周期 Web 工作台。**46 节点 / 7 阶段 / 341 条风格库 / 3 个渲染引擎（riso · code-video · ink）/ 中英双语。**

## 当前状态：全链已贯通 ✅

```
文案 → 索引 341 → 预演/推荐 → 风格门 → tokens → 任务卡+校验门 → 引擎编译
 → 字体子集(0缺字) → 静帧渲染(真实 Chrome) → 查看门 → QA门 → 批准门
 → 时间轴/代理帧474 → 运动QA → 分镜门 → 帧服务 → 逐帧渲染948 → 完整性
 → ffmpeg编码 → Y-SSIM QA → 画面锁定 → 口播/对齐/音乐/混音(loudnorm)
 → 响度QA(−16LUFS±1) → 交付门 → master.mp4 (39.500s, AAC 音轨)
```

实测（rumor-39s 导入全链，Run #1）：46/46 节点 succeeded · 49 产物 · 9 条审批记录（含驳回→重批历史）· master.mp4 = 69.9MB · 三引擎可生产 61 条。

## 快速开始

```bash
./dev.sh        # 开发态：API :7860 + Web :3000
./build.sh      # 发布态：Next 静态导出 + FastAPI 单进程 :7860
```

- 首页 http://localhost:3000 → 导入 `~/cc-projects/ai-v/rumor-39s` 或走 5 步向导
- API 文档 http://127.0.0.1:7860/api/docs

## 测试

```bash
cd server
uv run pytest tests/unit tests/bdd tests/integration/test_style_index.py -q   # 25+
uv run --project server python scripts/smoke_m1.py    # M0/M1 API 全链冒烟（需服务在跑）
uv run --project server python scripts/e2e_ui.py      # Playwright UI E2E（8 场景，需 ./dev.sh 在跑）
uv run --project server python scripts/drive_run.py <run> <project>   # 全链驱动（自动批门）
```

## 文档地图

| 文档 | 说明 |
|---|---|
| **[HANDOFF.md](HANDOFF.md)** | **接手入口（交接文档：状态/坑/缺口/路线图）** |
|---|---|
| `../filmflow-web-agent-prompt.md` | 技术规格（§4.8 边表 / §19 裁决表为宪法） |
| `../filmflow-prd.md` | PRD（FR-1~14 / US-01~10 / 风险） |
| `docs/tech-plan.md` | §18 九项技术方案 |
| `docs/process/` | SDLC / Feature 拆分 / 测试策略 |
| `bdd/features/` | 16 个中文 Gherkin 特性文件（自动化 3 场景 + 手动验收拆分） |
| `docs/adr/` | ADR-0001 技术栈 · ADR-0002 实测矩阵 · ADR-0003 embed 上限 |

## 已知边界（诚实清单）

- ~~Playwright UI E2E~~ → 已交付（`scripts/e2e_ui.py`：8 场景 15s 全绿——首页→向导 5 步→风格选择器搜索/设主风格→生成→46 节点画布→EN 切换→导入）。
- **补标队列 123 条**：标注 UI 已交付（/labeling），标注本身需人工完成（约 4 小时）。
- **whisper 对齐**：模型未下载时走手动打点回退（规格允许）；下载 ggml-medium 后自动启用词级对齐。
- ~~ink 引擎~~ → 已交付（`engines/ink/` 含基准 fixture，producible 61）。
- ~~英文 i18n~~ → 已交付（`web/src/lib/i18n.tsx`：zh/en 双词典 + 语言切换，全页面接入）。

## 实现期裁决（已录规格 §19）

F03 重复帧按 §6.2 降为警告 · G07 门后真实打包 · embed 上限 profile 化 · 门控调度活同步。
