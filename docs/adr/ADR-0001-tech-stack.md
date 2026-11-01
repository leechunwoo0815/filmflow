# ADR-0001 · 技术栈定案

- 状态：已接受（老板拍板，2026-11-01）
- 关联：规格 §12 / §19，PRD §0

## 决策

1. **后端：Python 3.13 + FastAPI + SQLModel + SQLite（FTS5 trigram）**——老板在 Node/Python/Next 三方案中选择 Python 全栈。
2. **前后端契约：OpenAPI 3.1**，openapi-typescript 自动生成 TS 客户端（放弃 tRPC）。
3. **前端：Next.js 15 + React 19 + Tailwind + shadcn/ui（深色工作台主题）+ @xyflow/react + Zustand + TanStack Query + Recharts。**
4. **进程形态**：开发 `./dev` 双进程（uvicorn :7860 + next :3000）；发布 `./build` 单进程（Next 静态导出由 FastAPI 托管），满足规格"可双击启动"。
5. **whisper：whisper.cpp CLI + ggml-medium（~1.5GB，首跑下载带 sha256）**；备选 faster-whisper 仅在 brew 方案失败时启用并事先告知。
6. **包管理**：uv（Python 侧）+ pnpm（前端侧）；仓库 `filmflow/{server, web, docs, bdd}`。

## 备选与理由

- Node 全栈：类型端到端更顺，但老板选择 Python——fontTools/jieba/Pillow 原生、与既有技能脚本（validate_task.py、film_server.py）同语言，子进程边界更少。
- Next.js 单进程全栈：启动最简，但 RunEngine（子进程/锁/SSE 长驻）与 Next 运行时耦合，架构分层受损。

## 后果

- +：解析/字体/图像分析全在 Python 侧原生完成；与参考项目脚本零翻译成本。
- −：类型安全靠 OpenAPI 生成层保障（schema 先行的纪律必须执行）；前端到后端的每次契约变更必须先改 OpenAPI 再生成。
