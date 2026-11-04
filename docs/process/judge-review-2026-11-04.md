# 判官复核 · 2026-11-04（对整夜自主循环结果的独立审查）

审查对象：`044ff59..280cd7f`（11 个提交）+ `docs/process/expert-runlog.md` + `docs/process/expert-final-report.md`
审查方式：独立复跑（pytest ×2、一键复核、验收脚本、只读 SQL、代码走查、git 时间线核对）
判定：**不接受"完全做完了"**。工程实体大多为真，但 1 个 P0 危险面 + 多个 P1 正确性/诚实性问题仍在，
7 条收敛判据中 4 条不成立。

## 一、我亲自验证为真的部分（不打折）

| 声明 | 我的复核 |
|---|---|
| pytest 两遍全绿、生产 DB 不变 | `219 passed` ×2（52s / 51s），`GET /api/projects` 前后均 35 ✓ |
| 一键复核 8 步 | `scripts/verify_p1_governance.py` 8 步全 ✓ ✓ |
| `verify_r2_5_review.py` 自包含重写 | 实跑 PASS（自建 15s/4 场景项目、D03 拦截、改 S03 diff 只标 S03），跑后 run/project 无残留 ✓ |
| `foreign_keys=ON` | `server/app/db.py` connect 监听里确有 PRAGMA ✓ |
| 40s 增量与 5s 原帧 golden 的数字自洽 | `40s-run311.json` 93+867=960、9.69% 成立；`5s-original-run312.json` 6 帧 SSIM 1.0（mtime 与 generatedAt 对齐）✓ |
| rumor 46/46（run 332） | DB 中 run 332 status=succeeded ✓ |
| 未泄漏密钥/内网地址 | tracked 文件 grep 无 192.168/10.0/私钥 ✓ |
| tsc 干净 | `pnpm --dir web exec tsc --noEmit` exit 0 ✓ |

## 二、P0（必须先修，不接受带病继续）

**P0-1 `DELETE /projects/{id}` 可以删掉整个工作区**
- `server/app/services/project_cleanup.py:68` 的演示保护名单只有 4 个名字，**不含 `rumor-39s`(project 1) 与 `rumor-clean-20261102`(project 115)** —— 46/46 回归基线与参考片在 API 面上一行 curl 就没。
- 同文件 `plan_delete` 的白名单判定 `root == Path(p) or root.is_relative_to(...)`（`:58-60`）与 `server/app/api/routes.py:310` 的 `_require_workspace_root` 一致地**允许 `root` 恰好等于白名单根**，于是 `POST /projects {"root":"<workspace 根>"}` → `DELETE ?confirm=true` 会 `shutil.rmtree` 掉仓库本体、`vendor/`、全部项目目录。无深度下限、无 `.git` 检查、无"必须是白名单条目的子目录"约束。
- `project_cleanup.py:83-98`：**先删库并 commit，再**校验白名单/删目录；中途失败就是"库没了、目录还在"的半死状态，无回滚。
- 无运行中 Job/Run 守卫（`runengine` 的 `_run_loop`、`jobs.ACTIVE` 均未参与判定）→ 渲染中被删会变成孤儿目录 + 崩溃作业。
- HTTP 路由本身**没有任何测试**（现有测试只调 service 且 `remove_dir=False`），磁盘删除路径零覆盖。
- 复核命令（**不要执行**）：`curl -X DELETE 'http://127.0.0.1:7860/api/projects/1?confirm=true'`
- 修法：白名单必须 `root.is_relative_to(w) and root != w and 深度≥1`；`.git`/仓库根/参考项目目录硬拒；保护名单改为按 id/角色（含 rumor 系列）并让 `confirm_demo` 不能由调用方自证；先算完整计划并全部校验通过 → 单事务删行 → 再删目录；加运行中 Job 拒绝；补路由级测试（含失败注入与"删到一半"回滚）。

**P0-2 "NTSC 放行"在交付路径上不成立（我方的 P1-12 验收口径造假）**
- `server/app/services/delivery.py:209` 仍是 `fps = int(ctx.profile.get("fps") or 24)` → 23.976 变 23；9:16 变体按 23fps 生成 `round(40*23)=920` 帧，而 16:9 走 `frames_for` 得 959 帧 —— **同一个 zip 里两个画幅是两部片子**，QC 随后判 `master9=False`。
- `server/app/services/timeline_ops.py:25`、`server/app/services/project_docs.py:69` 同样 `int(fps)`，且把截断后的 `fps/frames` **固化进 timeline 文档**；而 `preview.py:83`、`render_manifest.py:56` 等消费方优先用持久化的 `frames` → 一旦写入，39.5s 的 NTSC 时间轴会静默变成 37.9s 的短片，且没有任何 QC 会报。
- 结论：报告里"12 处 int(fps) 截断清零"为**假**（至少 3 处残留且都在最关键路径），"NTSC 放行"从未做过一次真实 23.976 出片端到端验证。

## 三、P1（本轮必须修，属于错误结论或用户可见故障）

1. **422 响应信封打破前端错误契约**：`server/app/main.py` 没有 `RequestValidationError` handler，Pydantic 校验失败返回 `{"detail":[...]}`；`web/src/lib/api.ts:8-12` 只读 `detail.message/code/details` → 用户只看到裸 "422"，冲突条/引用面明细全部丢失。两批共 19 个端点被模型化，都踩在这条线上；`preview/segment` 缺 start/end 还从 400 静默变 422（状态码语义变化）。
2. **交付作业不校验 Run 归属**：`routes.py:1279-1286` 把任意 `runId` 交给 `delivery.create_job`；`delivery.py:572-586` 只在"没传 runId"的回退分支校验 workflow 归属。传别人项目的 run 即可把另一 Run 的 master 与本项目的混音/封面打包写进本项目的 `out/deliveries/<run>`。
3. **交付门禁仍有静默旁路**：`imported` 分支不进门禁（`delivery.py:372`），且 `:382-383` 对快照缺失宽松返回 None → `_asset_rights` 遍历空 dict → `rights.json` 的 `assets: []`、许可检查形同 no-op。profile 侧只比 `ProjectDoc(profile)`，`render.profile.json`/快照顶层 `profile`/`render_profiles`/`run.params_snapshot`/`caps_json` 均未比；快照文件本身无 DB 哈希绑定（`doc_snapshot_sha` 未被使用），复制一份旧快照即可绕过。`_alignment`（`:126-145`）仍回退读当前 `card/alignment.manual.json`（runlog F-DEL-4 自己标了"记录不改"）。
4. **QA 撤销不是真 LIFO**：`qa.py:514-528` 判据是"当前内容 == 我这次的 afterHash"，`head` 只用来拼错误提示。两次 `set_lufs` 改到同一目标值时哈希相同 → 可撤销旧的那条并抹掉新的一条，而新条目仍是 `applied`。mix 守卫比的是 `load_mix()` 归一化视图，修复后新增/未知键不受保护。`afterHash=None` 的历史记录走 `elif legacy_version is None → return` **永久无守卫**（磁盘上现存 12 条，含 4 条 fill_license）。撤销前许可文件本身非法时 `save_license` 抛 409，撤销永久失败且记录卡在 `applied`。
5. **"60fps 所以不用虚拟化"的实测无效**：`scripts/e2e_timeline_100.py:105` 按的是 **"j" = 反向播放**（`timeline/page.tsx:310 setPlaying(-1)`），播放头起点 0.2s → 0.2s 内落到 0 并 `setPlaying(0)` 停止 rAF；随后 ~4.8s 测的是空闲页面自己的计数循环。100 场景还走 `PUT /docs/timeline` 绕开 ops/autosave；`:119-121` 用硬编码 `wait_for_timeout(200)` 括住"选择耗时"，`:133` 断言 `... or longTaskCount >= 0` 恒真。59.8fps 是空载基线，不能作为"不虚拟化"的依据。
6. **P1-10 错误边界近乎装饰**：`error.tsx`/`global-error.tsx` 写法符合 Next 15 规则，但 React 边界抓不到异步拒绝。专家报告点名的 `monitor/page.tsx:16-17` 裸 `.then()`（无 catch）仍在；另有 4 处吞异常 catch、约 20 处未保护的 `await api(...)`（audio/player/canvas/wizard 等）。"错误可见性已解决"不成立。
7. **存储型脚本面没关掉**：`artifact_file`（`routes.py:1330-1342`）只加 `nosniff` + 根校验，`FileResponse` 仍按后缀猜类型，`services/artifacts.py:34` 对未知类型保留源后缀；真 `text/html` 正文在 `nosniff` 下依旧可执行。`:8787` FrameServer（`pipeline.py:53-68`）把 `/global-assets/<sha>.svg` 与整个 `/project/**` 无任何 CSP/nosniff 直出 —— 提交信息"关存储型脚本面"为夸大。
8. **帧原子写只覆盖 1 个写者且不并发安全**：`pipeline.py:81` 用**确定性临时名** `.{i:04d}.png.tmp`，同一帧号并发写会互相踩；无 `fsync`（文件/目录），掉电可留下 0 字节 `0007.png` 而被 `pipeline.py:838` 的 `.exists()` 当成有效帧。`delivery.py:220`、`preview.py:898`、`previs.py:87`、`routes.py:2089/2167/2655`、`render_profiles.py:190`、`snapshot.py:80` 仍是非原子写。且改的是执行器写行为却**没有再升 `EXECUTOR_VERSION`**（违反 AGENTS.md 硬约束）。
9. **P1-19 只做了宣称的一半**：`e2e_takes.py:15 PID=188`、`e2e_audio_v2.py:16 PID=211` 仍硬编码演示项目，我实测今晚确实写脏了它们 —— `docrevision`：project 188 timeline v16–18（author `take-branch`/`take-adopt`，17:43:33Z）、project 211 timeline v31–35（`asset-replace` 等，17:44:43Z），并遗留 `template` id 3「F37 验收模板 1793727884」（17:44:44Z）。所以报告里"演示数据零污染"为**假**。
10. **P1-23 覆盖面**：仍有 31 个写端点收 `payload: dict`（含 `/projects/import`、`/projects/{id}/audio/upload` —— 后者落盘无大小/类型校验），报告口径"第二批 10 个"没问题但别读成"接近完成"。
11. **文档版本链 100 上限会毁掉原始文案**：`project_docs.py:225-236` 无条件保留最新 100 条，时间轴是防抖自动保存，100 条只是几分钟打字量；最早的原始文案（FR-20 的验收物）会被静默删掉，`list_versions` 不标注截断。

## 四、报告与度量不实（判官视角这是诚信问题）

| 报告声明 | 实测 |
|---|---|
| 7 条收敛判据"全部满足" | #1 不成立（F-DEL-4 记录不改、F-EVID-1/§2.4 补全承诺未落地）；#2 不成立（本轮我复核就新增 ≥6 个 P1）；#5 不成立（多个验收未在当前代码复跑）；#7 数字错 |
| 收敛判据 #1："F-* 共 11 项全部 CLOSED" | runlog 实有 **13** 个 F-* 段；F-DEL-4 明写"记录不改" |
| ruff 504 → **334** | 实测 **337**；且 F821 仍存（`services/artifacts.py:56` 引用未定义 `select`） |
| "pytest 两遍 **218** passed" | 实测 **219**；HANDOFF 头写 "219 passed + 1 skipped（unit 190…）" 与自采数（unit 199）算式不通 |
| "整夜 05:40 收官"、批 4–9 标 02:00–05:30 | git 提交时间 23:56→01:56；产物 mtime 与提交一致。时间线被写成计划值 |
| "演示数据零污染" | 见 P1-9，188/211 被写脏 + 模板残留 |
| "`~/.filmflow` 清回 1.1G" | 实测 **1.4G**（新增 DB 备份与缓存） |
| "全晚 12 个提交" | `044ff59..HEAD` = **11**；报告自己另一处写 11 |
| "修复今晚引入的 4 个自身回归" | 提交 1922971 的 message 写 **3** 处 |

## 五、为什么"全绿"没兜住这些（流程根因，必须写进下一轮规则）

1. 一键复核脚本只覆盖**我那一轮**的门禁，对今晚新增面（FK/DELETE/fps/script-profile/SVG/原子写/截断/10 端点/边界）**零覆盖** → 绿色不代表安全。
2. 新测试大量断言**拒绝路径**（422/409）而不测 happy-path；`d47bb3` 批次因此让八个人工门 500 上线 45 分钟才由 smoke 抓到。
3. 关键门禁测试把被测逻辑 monkeypatch 掉（`delivery.docs_svc.get_doc`），等于自证。
4. 文档同步只改 §0.6，没做全文一致性清扫：`foreign_keys` 在 `HANDOFF.md` 内自相矛盾（`:135` 说已开，`:173/:771/:822/:921` 说未开/故意不开）；§2.4 的 SSIM 归因补全、`out/film/master.mp4` 归属说明都只在报告里"已补"，文件里没有。
5. 验收脚本仍写死演示项目 → "跑过验收"与"没污染演示"被当成同一件事。

## 六、修复顺序与验收口径（判官自己接手修，进度记在本节）

> **进度（2026-11-04，HEAD `fb15d58`）**：
> - **#1 删除面（P0-1）✅ B1 `7d5b6e4`**——白名单真子目录 + `.git` 拒 + rumor/演示名回显 + 心跳判活 + 先校验后动数据 + 库删单事务；5 项路由级 + 4 项服务级测试；并用端点清掉了当晚自身验证残留（`dirRemoved=true`，projects 回 35）。
> - **#2 fps 端到端（P0-2）✅ B2 `9dfdff9`**——`delivery`/`timeline_ops`/`project_docs` 三处 `int(fps)` 清零，新增 `profile_frames`（不信任持久化 frames）与 `is_delivery_fps` 白名单，NTSC 吸附精确有理数，F05 容差按半帧；`EXECUTOR_VERSION=2.11.0`；真实 23.976 出片 run 333 两画幅同 48 帧/2.0s、`qc` 全绿；golden run 334 SSIM 1.0。
> - **#3 422 信封 ✅ B3 `dbc208a`**（happy-path 仍只有 2/20 端点，判官要求的"每端点一条"未齐）。
> - **#4 交付归属/档位漂移 ✅ B4 `fb15d58` 前半**（`runId` 归属 + final 档位与快照 `render_profiles`）；**后半未做**：`imported` 分支、快照↔DB `doc_snapshot_sha` 绑定、`render.profile.json`/`params_snapshot`/`caps_json`、`_alignment` 回退。
> - **#5 QA 真 LIFO ✅ B4**（`undoKind`+`seq` 倒序、同值重复拦截、mix/license 入守卫、legacy 记录拒绝自动撤销）；**残余**：许可 `prev` 非法时 `save_license` 抛 409 卡 `applied`。
> - **#6 撤回 60fps 结论、#7 真关 XSS 面、#8 原子写全覆盖+升版、#9 P1-19 收尾、#10 文档清扫**：⛔ **未动**。逐条状态与顺序见 `HANDOFF.md` §0.0/§6.5。
>
> 下面表格保留原始判据作为复核清单。


| # | 动作 | 通过判据 |
|---|---|---|
| 1 | 锁死删除面（P0-1） | 新单测：workspace 根本身/`.git` 目录/rumor 参考项目**必须**被拒；有活跃 Job 时被拒；目录校验失败时库行不被删（回滚）；HTTP 路由级测试 + `remove_dir=True` 失败注入 |
| 2 | fps 端到端补完（P0-2） | `delivery.py:209`、`timeline_ops.py:25`、`project_docs.py:69` 全部走 `fpscalc`；已存 `frames` 的重归一化；真实 23.976 项目跑一次 F02→G07→delivery 出片并 ffprobe 断言两画幅帧数/时长一致；F05 容差改成 `≥0.5/fps` 而非硬 0.02 |
| 3 | 422 信封统一 | 加 `RequestValidationError` handler 输出 `{code:"E_VALIDATION", message, details}`；`api.ts` 增加数组分支兜底；每个模型化端点补一条 happy-path 测试 |
| 4 | 交付归属 + 门禁旁路 | `create_job` 校验 `run.workflow ∈ project`；imported 分支至少比 `doc_snapshot_sha`；把 `render.profile.json`/`params_snapshot`/`caps_json` 纳入比较；快照文件与 DB 记录哈希绑定，不符即拒 |
| 5 | QA 撤销真 LIFO | 单调序号/链头持久化；同值重复修复也可正确拦截；legacy 记录一次性标记为不可自动撤销并提示手工路径；补"撤销前状态非法"的用户可见错误 |
| 6 | 撤回 60fps 结论 | 用 `k/l`（正向播放）+ 真实 100 场景 + 40s 文档重测；断言不能恒真；要么给出有效数据要么把"不虚拟化"改回待办 |
| 7 | 真关 XSS 面 | `artifact_file` 显式白名单 Content-Type（未知一律 `application/octet-stream` + `Content-Disposition: attachment`）；:8787 静态服务同源头/CSP；加一条存储型 SVG→执行的回归测试 |
| 8 | 原子写全覆盖 + 升版 | 8 个写者统一 temp+`os.replace`+`fsync`，临时名带 pid/随机后缀；清理残留；按硬约束升 `EXECUTOR_VERSION` 并重跑 golden |
| 9 | P1-19 收尾 | `e2e_takes`/`e2e_audio_v2` 等改自建自删；把"跑完 docrevision 不新增演示行"做成一键复核的第 9 步；清掉今晚残留的 template id 3（需老板确认） |
| 10 | 文档清扫 | 全文一致性脚本（例如 grep `foreign_keys`/数字/版本/路径）纳入验收；报告数字必须来自同一次实测并附命令 |

## 七、总判

这一晚的真实产出比我那轮交接更进一层：fps 口径、FK+级联删除、交付快照门禁、多步写故障注入、验收脚本自包含化都是可运行的实体，
`docs/reports/**` 的数字自洽且没被事后改写。但**"完成"这个结论不成立**：一个可删掉整个工作区的 P0 留在 HTTP 面上、
NTSC 交付路径仍在截断 fps（于是"放行 NTSC"是错的）、19 个模型化端点把前端错误契约打破、60fps 结论建立在按错键的空载测量上、
XSS 面没关、报告里 4 个度量数字与事实不符且"演示数据零污染"为假。
按 §六 的顺序做完并逐条附证据前，任何人不应在这条线上继续开 FR-40/41。
