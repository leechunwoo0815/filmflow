# 测试策略与 TDD 规则

> 版本 v1.0 · 配合 sdlc.md §4 使用。BDD 工具链：**pytest + pytest-bdd（中文 gherkin）**；E2E：**Playwright**。

## 1. 测试金字塔

```
        ┌─────────────┐
        │ E2E  ~10%   │ Playwright × pytest-bdd：走真实 UI + 真实 Chrome/ffmpeg
        ├─────────────┤
        │ 集成 ~20%   │ RunEngine + SQLite + 真实子进程（小夹具项目）
        ├─────────────┤
        │ 单元 ~70%   │ 执行器契约 / 解析器 / 状态机 / 失效图 / caps / 缓存键
        └─────────────┘
```

## 2. 分层职责

| 层 | 测什么 | 不测什么 |
|---|---|---|
| 单元（pytest） | 执行器的命令构造、输出/@@PROGRESS 解析、退出码处理；token 解析器；caps/minCap 判定；缓存键计算；失效图（data/order/trigger）；门 content_hash；双口径阈值表 | 不测真实渲染时长 |
| 集成（pytest + 夹具项目） | A03 扫描真实库、C03 fontTools、D02 用真实 Chrome 渲 1 帧、E06 对 474 代理帧真算、F03 缺帧检测、ffmpeg 编码 3 秒小片 | 不跑全片 948 帧（E2E 里程碑验收才跑） |
| BDD（pytest-bdd） | 每个 .feature 场景 = 一条可执行验收；步骤绑定优先调集成层 API 而非 UI | 不测视觉样式 |
| E2E（Playwright） | 向导流程、选择器交互、画布状态色、门审批弹窗、断点续跑演示、监控页曲线 | 不穷举 341 张卡渲染（用抽检 + 单元断言总数） |

## 3. TDD 循环与提交

```
red   ：写失败单测（test(F08): caps 未批准时 D02 必须 E_PHASE_FORBIDDEN）
green ：最小实现（feat(F08): …）
refactor：全绿后整理（refactor(F08): 提取 capability 检查器）
```

- 红绿各自 commit（sdlc §6）；重构不改 .feature。
- 每个执行器先写**契约测试**：输入 fixture → 断言 stdout 结构、产物文件、sha256、指标 JSON schema。

## 4. 覆盖率目标（变更行覆盖）

| 域 | 目标 |
|---|---|
| server 核心域（runengine / scheduler / invalidation / gates / caps / cachekey） | ≥ 90% |
| 46 个执行器 | 契约测试 100% 存在；解析分支 ≥ 85% |
| token 解析器 + 推荐评分 | 100%（纯函数） |
| web 纯逻辑（store / impact 预估 / 筛选器） | ≥ 70% |
| UI 组件 | 不追覆盖率，以 E2E 场景为准 |

## 5. 夹具映射（规格 §14 全量承接）

| 夹具 | 生成方式 | 被引用的 gherkin |
|---|---|---|
| 1 正常（参考项目 task.json + 3 静帧 + 39.5s mp4） | 导入真实项目 | wizard / render-pipeline |
| 2 缺帧（删 0400.png） | 脚本删除 | render-pipeline / resume |
| 3 黑帧（0500.png 替换纯黑） | 脚本替换 | render-pipeline / quality-gates |
| 4 静态开头（前 14 代理帧相同） | 代理帧复制 | quality-gates@motion |
| 5 切点（9.0s 硬切无 transition，代理帧差 13.51） | 构造 | quality-gates@motion |
| 6 字体缺字（woff2 去一字） | fontTools 重建 | quality-gates@fonts |
| 7 审批（驳回/批准） | API 调用 | gates |
| 8 断点（渲染中 kill） | 测试钩子 | resume |
| 9 风格库（真实 index + 343 条记录、矩阵 169/24/53/95） | A03 首扫 | style-indexing / style-discovery |
| 10 风格切换（L28→O88） | API 调用 | cache-invalidation / style-selection |
| 11 引擎未就绪（卡通族） | 注册表状态 | engine-registry / wizard / style-selection |

## 6. 环境真值断言（测试前置检查）

测试套件启动时断言环境：Chrome 156 二进制存在、ffmpeg 9 可用、Python 3.13、风格库路径可读且 `_统计.json` total=341。任一失败 → 测试报 `E_ENV_MISSING` 风格的明确错误，不静默跳过。

## 7. 性能回归线（防退化，非验收）

- 首屏 12 张有封面推荐 ≤1s、需预演 ≤8s → Playwright 计时断言（允许 CI 机器 ±50% 松弛）。
- 100 节点画布 60fps → 滚动帧率采样冒烟（M4）。
- 341 张虚拟滚动无卡死 → 滚到底断言全部条目出现过。
