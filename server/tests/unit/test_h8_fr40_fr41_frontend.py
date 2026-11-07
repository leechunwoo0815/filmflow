"""H8：FR-40/FR-41 前端接线的静态防线（不需要浏览器，CI 也能跑）。

真跑在 `scripts/e2e_fr40_keyboard.py`（纯键盘全流程）。这个文件钉的是**结构**：
1. 命令注册表是唯一真源——≥20 条命令、id 不重、键位不冲突（冲突是运行时才算得出的）；
2. 面板真的挂在壳层里（`layout.tsx`），不是"组件写了但没人 mount"那种半件；
3. a11y 关键属性挂在**会被聚焦的元素**上（`aria-activedescendant` 在 combobox 输入框上，
   不在列表 div 上）——这条正是 e2e 第一次真跑抓出来的缺陷的反向固化；
4. 键盘验收脚本**一次鼠标调用都不许有**（`.click(` / `page.mouse` 出现即红）；
5. FR-41 的建议入口在向导第 1 步（草稿层），且"采纳"只写 `brief`，不覆盖用户原文。

为什么这些能在静态层测：它们都是"有没有接线"的事实，而不是行为；行为归 e2e。
把接线钉在单测里，是为了让下一次有人删掉 mount 或把 testid 改名时，在 CI 就红，
而不是等 e2e 跑出半程再报一个看不懂的 TimeoutError。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # unit → tests → server → 仓库根
WEB = ROOT / "web" / "src"
SCRIPTS = ROOT / "scripts"


def _read(p: Path) -> str:
    assert p.is_file(), f"缺文件：{p}"
    return p.read_text(encoding="utf-8")


def test_command_registry_is_the_single_source() -> None:
    src = _read(WEB / "lib" / "commands.ts")
    ids = re.findall(r'\bid: "([a-z0-9.]+)"', src)   # 有的命令是单行写法，不能按缩进匹配
    assert len(ids) >= 20, f"命令注册表只有 {len(ids)} 条，PRD 要求 20 条命令的面板"
    assert len(ids) == len(set(ids)), f"命令 id 重复：{[i for i in ids if ids.count(i) > 1]}"
    # 键位冲突必须在静态层就被发现：两条命令抢同一个组合键，用户按下去只会得到一个"随机"结果
    keys = re.findall(r'key: \{ mod: "(\w+)", (?:shift: true, )?key: "(.+?)" \}', src)
    assert len(keys) >= 8, f"注册表里只认出 {len(keys)} 条键位绑定，正则可能已经跟不上写法"
    assert len(keys) == len(set(keys)), f"快捷键绑定冲突：{sorted(keys)}"
    assert 'export function shortcutConflicts' in src, "冲突检测必须由注册表派生，不能靠人肉看"


def test_palette_is_mounted_in_the_shell() -> None:
    layout = _read(WEB / "app" / "layout.tsx")
    assert "WorkbenchChrome" in layout, "命令面板/通知中心没挂进根布局——面板代码存在但用户看不见"
    chrome = _read(WEB / "components" / "WorkbenchChrome.tsx")
    assert "CommandPalette" in chrome and "NotificationsBell" in chrome and "ShortcutsSheet" in chrome
    # 全局键位必须读注册表；自己另写一份 switch 就是第二真源
    assert re.search(r"for \(const cmd of COMMANDS", chrome), "全局键位没按注册表分发"
    assert 'cmd.key.mod === "none" && typing' in chrome, "打字时的裸键（? ）必须让位给输入框"


def test_keyboard_a11y_attributes_are_on_focusable_elements() -> None:
    pal = _read(WEB / "components" / "CommandPalette.tsx")
    input_block = pal[pal.index("<input"):pal.index("/>", pal.index("<input"))]
    assert 'role="combobox"' in input_block, "面板输入框必须是 combobox，否则读屏报不出可自动补全"
    assert "aria-activedescendant" in input_block, "选中项 id 要挂在**被聚焦的输入框**上（挂列表上是无效的）"
    assert 'aria-controls="palette-list"' in input_block
    assert 'id="palette-list"' in pal and 'role="listbox"' in pal
    # Esc/↑/↓ 挂在可聚焦元素（input / listbox tabIndex）上，而不是挂在非交互容器上
    assert pal.count("onKeyDown={onPanelKey}") >= 2, "键位处理器要同时覆盖输入框与列表两处焦点位置"
    sheet = pal[pal.index("export function ShortcutsSheet"):]
    assert 'aria-label="快捷键表"' in sheet and "shortcutConflicts()" in sheet


def test_notifications_panel_wires_unread_and_repair_entry() -> None:
    bell = _read(WEB / "components" / "NotificationsBell.tsx")
    assert 'data-testid="notifications-unread"' in bell, "未读角标要有可定位的锚（e2e 与读屏都用它）"
    assert "unread ? ` (${unread})` : \"\"" in bell or "aria-label" in bell, "铃铛必须用 aria-label 播报未读数"
    assert "/notifications" in bell and "/notifications/read-all" in bell
    assert '/jobs/' in bell and "/queue" in bell, "进度中心必须读真队列端点，不许假数据"
    assert 'aria-live="polite"' in bell, "提示必须过 aria-live（PRD：异步失败可见）"
    assert 'role="progressbar"' in bell and "aria-valuenow" in bell
    notif_svc = _read(ROOT / "server" / "app" / "services" / "notifications.py")
    # 只查**代码**里的链接拼接，不查解释这段历史的注释文案
    assert not re.search(r'link=f?"[^"]*projectId=', notif_svc), \
        "通知链接又退回旧的无效口径（页面读 ?project=&run=，见 _canvas_link 的注释）"
    assert "/canvas?project=" in notif_svc, "修复入口必须带 project 参数"


def test_keyboard_e2e_covers_the_real_blockers_and_exits_honestly() -> None:
    """这条钉的是 e2e 的**测的是不是真流程**：三个必然撞上的前置 + 不许假绿。

    真跑一轮轮撞出来的（attempt 10/11/12）：
      · 向导自建项目没有口播音频 → G01 直接失败，Run 到不了后半段；
      · 没有手动对齐且本机无 whisper 模型 → G02 E_MODEL_MISSING；
      · Run 没成功时旧脚本照样打 PASS——绿色输出替产品撒了谎。
    这三条写进守卫，下次改脚本就不会又把它测成"运气"。
    """
    e2e = _read(SCRIPTS / "e2e_fr40_keyboard.py")
    assert "build_audio_state" in e2e, "G01 需要口播音频：脚本必须自建音频前置"
    assert "audio-save-alignment" in e2e, "G02 的手动对齐路径必须由键盘覆盖（否则撞 E_MODEL_MISSING）"
    assert 'data-testid="audio-save-alignment"' in _read(WEB / "app" / "audio" / "page.tsx"), \
        "音频页的保存按钮锚点被改名了，e2e 那条键盘路径就断了"
    assert "boundaries" in e2e and "return 2" in e2e, \
        "有判据未覆盖时必须 PARTIAL + 非零退出，不许照样打 PASS"
    assert "全场景已看" in e2e and "载入中" in e2e, "D03 前置必须等审阅状态真的取回，不吃空真"
    assert 'lsof' in e2e and "-a" in e2e and "NET_LOG" in e2e, \
        "零网络判据要按 pid 查进程并看浏览器请求；机器级 lsof 测的是别的程序"


def test_keyboard_e2e_uses_no_mouse() -> None:
    e2e = _read(SCRIPTS / "e2e_fr40_keyboard.py")
    assert ".click(" not in e2e, "键盘验收脚本里出现了鼠标点击，那它测的就不是键盘"
    assert "page.mouse" not in e2e, "同上：不许用 mouse API"
    assert "def tab_to(" in e2e and "def tab_to_nth(" in e2e, "Tab 到达必须是显式断言（到不了要报焦点链）"
    assert "Cleanup(" in e2e, "自建项目必须登记回收（任务书：验收脚本不许留残留）"
    assert "4 <= scenes <= 6" in e2e, "PRD 判据①（4–6 场）必须在验收里断言"
    assert "重组逐字等于原文" in e2e, "PRD 判据②必须在验收里断言"


def test_command_context_reads_the_param_names_pages_actually_use() -> None:
    """面板解析"当前项目 / 当前 Run"必须用页面真正读的那个参数名。

    e2e 第一次真跑抓到 `整片预览` 什么都没排队：注册表读 `?projectId=`，而全站页面读的都是
    `?project=`——命令以为自己拿到了项目，其实拿到 null，然后礼貌地提示了一句"没有项目上下文"。
    这种分叉只有真跑才会暴露，所以把它反向钉成静态断言。
    """
    src = _read(WEB / "lib" / "commands.ts")
    fn = src[src.index("export function currentProjectId"):]
    fn = fn[:fn.index("\n}")]
    assert '.get("project")' in fn, "currentProjectId 读的参数名和页面不一致"
    assert "projectId" not in fn, "全站没有页面读 ?projectId=，不要凭空猜第二套口径"

    names: set[str] = set()
    for page in (WEB / "app").glob("*/page.tsx"):
        names.update(re.findall(r'params\.get\("(proj\w*|run)"\)', _read(page)))
    assert names <= {"project", "run"}, f"页面出现了新参数名 {sorted(names)}，注册表要跟着对齐"


def test_run_dependent_pages_are_reached_with_context_resolved() -> None:
    """`/review` 没有 run 只有一句"缺少 run 参数"，`/canvas` 没有 run 是一片空白。

    ⌘3 这种"看起来能到"的导航如果落在空页上，用户学到的是"这个功能是坏的"。
    所以这两条命令必须走 goWithRun（URL 上有 run 就沿用，没有就取该项目最新 Run）。
    """
    src = _read(WEB / "lib" / "commands.ts")
    review = _read(WEB / "app" / "review" / "page.tsx")
    canvas = _read(WEB / "app" / "canvas" / "page.tsx")
    assert "if (!runId)" in review, "review 页对 run 的前置要求变了，这条守卫要跟着改"
    # canvas 2026-11-07 升级：无 run 参数时自动接上项目最新 Run（不再空白早退、
    # 不再假装 Run 0——老板首次 UI 实测点出 E_NOT_FOUND /runs/0/start）。
    assert 'api(`/projects/${projectId}/runs`)' in canvas and "setActiveRunId" in canvas, \
        "canvas 必须自动解析项目最新 Run（守卫跟新契约走，比旧的空白早退更强）"
    for nav_id in ("nav.review", "nav.canvas"):
        body = src[src.index(f'id: "{nav_id}"'):]
        assert 'goWithRun("' in body[:260], f"{nav_id} 仍然把用户送进一个没有 Run 的空页"
    assert "goWithProject(\"audio\")" in src, "/audio 没有 project 也是空页，同理要带上下文"


def test_gate_precheck_reason_is_surfaced_instead_of_a_400_surprise() -> None:
    """D03/D05 的"先把每个场景看一遍"必须在**界面上**看得见，而不是点下去才吃一条 400。

    这条是 e2e 第二次真跑抓出来的：审片页在数据到手前 missing 是空数组，于是页头绿灯
    "全场景已看"、批准按钮可点，用户（和自动化）都被这个空真相骗。判据只有一份
    （`_gate_precheck`），所以由 pending 接口随门带出，页面只显示不判断。
    """
    routes = _read(ROOT / "server" / "app" / "api" / "routes_runs.py")  # P3 #2 拆分后门审批在 runs 域
    assert 'item["precheck"] = _gate_precheck(session, run_id, gid)' in routes, \
        "批准前置没有随待办门一起给出，UI 就只能自己猜（判据分叉）"
    canvas = _read(WEB / "app" / "canvas" / "page.tsx")
    assert "gate-precheck-${g.gate}" in canvas, "画布门面板不显示前置缺口"
    assert "disabled={!!g.precheck}" in canvas, "前置未满足时批准按钮必须不可用（它也因此不进 Tab 序）"
    review = _read(WEB / "app" / "review" / "page.tsx")
    assert "载入中" in review and "setLoaded(true)" in review, \
        "审片页不许在状态还没取回时说『全场景已看』"
    assert "disabled={busy || !!d03.precheck}" in review, "审片页的 D03 按钮要跟着同一条判据"


def test_fr41_suggestion_panel_is_draft_layer() -> None:
    panel = _read(WEB / "components" / "SuggestionPanel.tsx")
    assert "/authoring/suggest" in panel, "面板必须打后端建议引擎（不许前端复刻一套规则）"
    assert "suggestedScenes" in panel and "readCps" in panel
    assert "brief: { ...brief," in panel, ("PATCH /drafts 的 payload 是顶层合并，"
                                          "不带旧 brief 会把用户标题抹掉")
    assert "setCopy" not in panel, "建议是草稿层：不许改用户的原文"
    # PRD FR-41 验收②"每条建议可接受/拒绝/编辑；接受后只影响对应场景"——只有"全部采纳"不算逐条
    assert "suggest-scene-adopt-${i}" in panel and "suggest-scene-ignore-${i}" in panel, \
        "逐场采纳/忽略的键盘锚不在了"
    assert "suggest-scene-seconds-${i}" in panel, "逐场停留时长可编辑（编辑落在时长上）"
    assert "x.id === s.id ? entry : x" in panel, "单场采纳必须只替换那一场，其余原样保留"
    assert "pushed ??" in panel, ("单场采纳要基于本面板最后一次写入的结果合并，"
                                  "否则第二次采纳会拿挂载时的旧 brief 把第一次的成果抹掉")
    wizard = _read(WEB / "app" / "wizard" / "page.tsx")
    assert "SuggestionPanel" in wizard, "建议面板必须挂在向导第 1 步（文案入口）"
    routes = _read(ROOT / "server" / "app" / "api" / "routes_system.py")  # P3 #2 拆分后 FR-41 在 system 域
    assert '@router.post("/authoring/suggest")' in routes, "向导阶段没有项目 id，需要无项目入口"
    assert "SuggestIn" in routes, "新端点同样必须收 Pydantic 模型（51 端点口径不许破例）"
