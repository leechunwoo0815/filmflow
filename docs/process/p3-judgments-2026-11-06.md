# Wave D · P3 26 条逐条判定（2026-11-06 夜，整夜任务书 §6）

对专家分析 §2.3 的 P3 清单逐条判定：**修（附提交）/ 不修（附理由）/ 需老板决策**。
判定口径：本机单用户 127.0.0.1 产品、不虚构"会有人用"的威胁模型。

| # | P3 条目 | 判定 | 理由/落点 |
|---|---|---|---|
| 1 | 仓库无 LICENSE | **需老板决策** | 选哪种许可影响商用/开源边界，不是工程问题。§8 决策点 2；未决前不加文件 |
| 2 | routes.py 2764 行 | **不修（本批）+ 方案入账** | 拆 router 是纯机械重构但触及 51 个 happy-path 守卫的映射面，深夜批量改路由风险>收益。方案：按 §2 域拆（styles/projects/runs/docs/assets/delivery/system 七个 router 文件 + 一个聚合），守卫反射面不动；留待白天的专批 |
| 3 | 500MB base64 内存放大 | **不修（本批）+ 已有护栏** | 入口上限 200MB（与服务层同源，治理第 15 项实测）；本机回环传输 200MB 峰值内存可承受。真流式要动 API 形状（multipart），留待 R4 |
| 4 | CDP 9222 可预测端口 + 可预测 profile | **修（部分）** | preview 预热 Chrome 的 profile 目录加随机后缀（本批 commit）；CDP 端口本机 127.0.0.1-only，仅本机其它用户可探——单用户机器上威胁模型不成立，记录不动 |
| 5 | list_assets O(项目×场景) | **不修** | 扫描只在资产删除/替换时触发，规模 = 用户主动行为；引入引用倒排索引是结构变更，收益不匹配 |
| 6 | 模板变量缺失不阻断 | **不修** | 现行为：缺失变量进 `missingVariables` 明细返回给 UI 供人工补——比硬阻断更符合"向导"语义 |
| 7 | qa.analyze 重复执行/阻塞 | **不修** | analyze 是用户点"分析"触发的同步操作，P2-21/22/23 已把结果落账；去重缓存是优化非正确性问题 |
| 8 | 前端轮询 → SSE | **不修（本批）** | `/runs/{id}/events` SSE 通道已存在；前端切 SSE 是独立的 UI 批次（与 FR-40 进度中心同批做更合适） |
| 9 | aware UTC 落库变 naive | **不修 + 记录** | 现网读路径统一 `replace(tzinfo=UTC)` 兜底（jobs/expire_parked 等已实现）；全局改列类型要迁移，风险大收益零 |
| 10 | DB freelist 从未 VACUUM | **需老板决策** | 破坏性维护（锁库重写）；现库 33MB，无膨胀症状。要做得先备份+停机窗口——§8 决策点 4 |
| 11 | .DS_Store | **修（已做）** | `git ls-files` 实测命中 0；`.gitignore` 补 `.DS_Store` 兜底（本批 commit） |
| 12 | 帧数计算散布 | **不修（已闭合）** | B2 批已统一到 `engine/fpscalc`（frames_for/norm_fps），本轮 grep 确认无残留直算 |
| 13 | 文本避头尾/emoji 硬失败 | **不修** | 现行为：怪字符导致 wrap 超限时报 E_SCENE_READ_OVERFLOW（可诊断、可改文案）——比静默降级诚实 |
| 14 | 预览 JPEG 中转 | **不修** | JPEG 中转是预览缓存 1.2GB 可控的代价；换 WebP 是纯优化 |
| 15 | 播放器 fps/JKL | **不修** | 播放器增强属产品功能（PRD 未列），不入工程债 |
| 16 | Asset 绝对路径 | **不修** | Asset.path 绝对路径在本机单用户 + 白名单根模型下无迁移需求；换机会走"重新登记根目录"流程（platform.feature 已描述） |
| 17 | 模板变量缺失不阻断 | （同 6，专家清单重复项） | — |
| 18 | SVG 上传与缺 CSP/nosniff | **修（已做）** | C5 实测确认 SVG 优雅降级路径；`security.frameserver_headers` 已带 CSP/nosniff（文件响应守卫覆盖）；导入面 C5 测试钉住 |
| 19 | `/api/artifacts/{id}/file` 无白名单 | **不修 + 记录** | artifact path 由服务端 content-address 生成、不经用户输入拼接；file_response 白名单 content-type 守卫已覆盖响应面 |
| 20 | 组件扩展点/模块级单例 | **不修** | 单例（FrameServer/_fs_instance 等）都是进程内有状态资源，本机单 API 进程语义下正确 |
| 21 | 取消状态传播 | **不修（已闭合）** | cancel_run → CANCESLS event → kill_current（P2-02）链路已在 2.15.0 落地并有测试 |
| 22 | 长 session | **不修** | Session 均为请求级/with 块级，未发现长持连接（grep 佐证）；FastAPI 每请求一 session |
| 23 | ffmpeg GPL | **需老板决策** | ffmpeg 是系统依赖不是分发产物（brew 安装），不触发 GPL 传染；若未来静态分发需定许可——与 #1 同批决策 |
| 24 | DB 空闲页 | （同 10 VACUUM） | — |
| 25 | QA wrap_text 固化文案 | **不修** | wrap 建议是启发式展示，改字由用户确认后落 doc（P2-18 语义），无固化问题 |
| 26 | 前端响应式/硬编码首页路径 | **不修** | 桌面 1600px 主场景 + i18n 脚手架已就位；响应式是产品批次 |

**汇总**：修 3（#4 部分、#11、#18 确认）/ 需老板决策 3（#1 LICENSE、#10/#24 VACUUM、#23 ffmpeg）/ 不修+理由 20。
