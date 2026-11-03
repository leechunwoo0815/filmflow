# ADR-0011 项目模板 / 场景模板 / 小系列

- 日期：2026-11-03
- 状态：已采纳（R3.0 FR-37 v1）
- 关联：FR-37、FR-25、FR-28、FR-36、FR-46（R4 批量）

## 背景

R2.5 只有 3 个内置“新手模板”：复制文案 + profile，再确定性生成时间轴，不能保存用户项目结构、
不能复用场景、不能按变量批量建项目。FR-37 要求项目模板（profile/timeline骨架/场景模板/
风格/交付预设）、场景模板、系列变量替换与模板版本锁定；CSV 批量/队列依赖 R4 FR-46。

## 决策

1. **`Template` 表**：`kind=project|scene`、`name`、`description`、`content_json`、`version`、
   时间戳。内置项目模板仍在代码（`FIRST_TEMPLATES`），内置场景模板在
   `services/templates.py`；`/templates` 默认只返回项目模板，`?kind=scene` 返回场景模板，
   `?kind=all` 两者合并，保持 R2.5 脚本兼容。
2. **项目模板内容**：
   - `profile`（画幅/fps/时长/frames）、`style_id`/`style_family`、`delivery` 文档、
     `copy`（可含 `{{title}}`/`{{number}}`/`{{accent}}`）；
   - `timeline.scenes[]` 只存结构：duration、meaning/operation、camera/keyframes/anchor、
     transition、layers、audio_layers、fontSha；不存绝对 start/end/source_span，文本交给新 script；
   - `sourceProjectId` + `assetShas`：实例化时把源项目本地资产复制到新项目；全局资产按 sha 复用；
   - `variables`：递归扫描 `{{var}}` 得到。
3. **实例化**：复用 Draft→materialize→Project/Run 路径，随后覆盖 profile/timeline/delivery 文档，
   按模板 duration/场景数重新分配新 script 的句子区间；写 `card/template.lock.json`
   `{templateId,version,variables,appliedAt}`。原项目模板不会被修改。
4. **场景模板**：内置标题/论点/证据/结论/行动；支持把任意场景另存为模板（默认清空文本、
   保留相机/转场/图层/SFX/字体）；插入走 `timeline_ops.add_scene`，可选插入到指定场景之后；
   场景模板的源资产同样在应用时复制。
5. **变量替换**：纯函数递归替换字符串值；缺失变量保留占位并在响应 `missingVariables` 返回，
   不静默改写文案；数值变量按字符串插入。
6. **系列 v1**：`POST /series/from-template` 接收 ≤5 个 items，同步逐个 materialize；
   单项失败隔离，返回 `created/failed/items`。**CSV、10 行队列、批量 zip、失败重试属于
   R4 FR-46，本轮不做**。
7. **版本/升级**：模板可保存新版本（`POST /templates/{id}/version`，version+1）；
   项目锁记录版本；`GET /projects/:id/template-diff` 返回 profile/场景数差异；
   `POST /template-upgrade {confirm:true}` 只覆盖已有场景的相机/转场/图层/字体/SFX 和
   width/height/fps，保留当前文本/时长/id，不自动增删场景；未 confirm 不改文档。
8. **不修改 46 节点 DAG**：模板是文档/项目层能力，不新增节点/边，不改变执行器语义。

## 后果

- 正面：第二条片不再从零开始；场景结构/相机/转场/资产可复用；模板变量和小系列可用；
  模板升级有锁/diff/confirm。
- 代价：项目模板保存 JSON 快照而非引用；源项目资产复制会增加磁盘；升级只覆盖视觉结构，
  不处理场景增删/文案迁移；系列同步创建，不是队列。
- 边界：模板删除 API 只删模板行，不删除已实例化项目；项目删除不自动清模板；视频资产仍只入库。

## 验证

- `scripts/verify_r3_templates.py`：另存项目模板→变量实例化（文案替换/结构/资产复制/锁）→
  场景模板插入→模板 v2 diff/confirm 升级→系列 2 项；清理模板/项目。
- `scripts/e2e_templates.py`：模板库/另存表单/场景模板插入/时间轴入口。
- unit `test_templates.py`：变量、项目模板 roundtrip、场景模板 add/overlay、模板锁。
- 133 tests；5s 黄金 SSIM 1.0 与 FR-36 证据保持。
