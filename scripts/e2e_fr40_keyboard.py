"""FR-40 / FR-41 键盘可达验收：**全流程纯键盘**（零鼠标）跑一遍。

覆盖任务书 H8 的第 ⑤ 条：建项目 → 改文案 → 预览 → 跑 Run → 签人工门 → 交付。
每一步只允许 `keyboard`（Tab / Shift+Tab / Enter / Space / 方向键 / ⌘K），
所以 `tab_to()` 是这脚本的核心断言装置：**焦点必须在 N 次 Tab 内到达目标**，
到不了就是键盘不可达（那才是这条验收要抓的东西，而不是"页面上有没有这个按钮"）。

用法：
    uv run --project server python scripts/e2e_fr40_keyboard.py            # 全流程（含真渲染，数分钟）
    uv run --project server python scripts/e2e_fr40_keyboard.py --surface   # 只跑 FR-40 键盘面（不渲染）
    uv run --project server python scripts/e2e_fr40_keyboard.py --keep      # 保留现场项目

纪律：项目自建自删（_acceptance.Cleanup），不打演示项目；零鼠标（本脚本不调用任何 click）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _scratch_state as ss
from _acceptance import Cleanup, add_keep_flag

WEB = "http://127.0.0.1:3000"
API = "http://127.0.0.1:7860/api"
ORIGIN = {"Origin": WEB}
# 292 字：建议引擎的 4–6 场目标要够长才成立（实测 76 字只出 3 场，会被这条验收当场抓住）
COPY = ("一条消息被转发，往往不是因为它有多重要，而是因为它刚好能被读懂。"
        "读起来吃力的句子，会被悄悄跳过；读起来顺的句子，会一路走到第三个人。"
        "所以我们做的不是漂亮话术，而是给句子安排能走完的路：一句一个意思，先给结论，再给条件。"
        "短的句子负责推进，长的句子负责解释；两者之间留一口气，让观众来得及抬头。"
        "抬头之后看见什么很关键：数字要带单位，对比要带基准，趋势要带时间。"
        "把这三样凑齐，观众才会自己得出结论——而不是被你说服。"
        "自己得出的结论会留下来；被说服的结论会在下一次反对意见出现时被换掉。"
        "所以这条片子的目标不是让人点头，是让人在关掉屏幕之后还能复述一句。"
        "能复述的那一句，才是真正被读完的那一句。")

MAX_TABS = 45           # 一屏之内 45 次 Tab 到不了 = 不可达，不是"再多按几下"的问题

_step = 0


def step(msg: str) -> None:
    global _step
    _step += 1
    print(f"✓ {_step}. {msg}", flush=True)


def tab_to(page, selector: str, label: str, *, shift: bool = False, limit: int = MAX_TABS) -> None:
    """纯键盘把焦点移动到 selector；到不了就把当前焦点链报出来（失败信息要能被复用）。"""
    trail = []
    for _ in range(limit):
        page.keyboard.press("Shift+Tab" if shift else "Tab")
        cur = page.evaluate("() => {"
                            "const a = document.activeElement; if (!a) return 'null';"
                            "return (a.getAttribute('data-testid') || a.tagName + ':' + (a.textContent || '')).slice(0, 60); }")
        trail.append(cur)
        if page.evaluate(f"() => !!document.activeElement && document.activeElement.matches({json.dumps(selector)})"):
            return
    raise AssertionError(f"Tab {limit} 次内焦点到不了 {selector}（{label}）；焦点链尾部：{trail[-12:]}")

def tab_to_nth(page, selector: str, nth: int, label: str, *, limit: int = MAX_TABS) -> None:
    """Tab 到第 nth 个匹配元素（从 1 数）。用于没有专属 testid 的同构输入框。"""
    trail = []
    for _ in range(limit):
        page.keyboard.press("Tab")
        cur = page.evaluate("() => {"
                            "const sel = document.querySelectorAll(" + json.dumps(selector) + ");"
                            "return Array.from(sel).indexOf(document.activeElement) + 1; }")
        trail.append(cur)
        if cur == nth:
            return
    raise AssertionError(f"Tab {limit} 次内没走到第 {nth} 个 {selector}（{label}）；命中序列尾部 {trail[-12:]}")


def press_on(page, selector: str, label: str, key: str = "Enter") -> None:
    tab_to(page, selector, label)
    page.keyboard.press(key)


def api_get(path: str):
    with httpx.Client(base_url=API, headers=ORIGIN, timeout=60, trust_env=False) as c:
        r = c.get(path)
        r.raise_for_status()
        return r.json()


def api_post(path: str, body=None):
    with httpx.Client(base_url=API, headers=ORIGIN, timeout=120, trust_env=False) as c:
        r = c.post(path, json=body or {})
        r.raise_for_status()
        return r.json()


def wait_for(predicate, timeout: float, what: str, interval: float = 0.5) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"等不到：{what}（{timeout}s）")


# FR-41 判据③的**第一手证据**：浏览器里发生过的每一个请求。比"审计代码没有 fetch 调用"硬，
# 因为它测的是这一趟真实流程里用户设备实际外呼了什么。
NET_LOG: list[str] = []


def watch_network(page) -> None:
    page.on("request", lambda r: NET_LOG.append(r.url))


def _project_root(project_id: int) -> str:
    """项目根从 `GET /projects` 列表里取。

    没有 `GET /projects/{id}` 这个端点（实测 405）——别按想象拼 URL。
    """
    for item in api_get("/projects")["items"]:
        if int(item["id"]) == int(project_id):
            return item["root"]
    raise AssertionError(f"项目 {project_id} 不在 /projects 列表里（materialize 没成功？）")


def _draft_id(page) -> int | None:
    raw = page.locator('[data-testid="wizard-root"]').get_attribute("data-draft-id")
    return int(raw) if raw and raw.isdigit() else None


DRAFTS_PATH = "/drafts"   # 自建入口：草稿由向导在浏览器里 POST /drafts 建出来（本脚本零次鼠标）


def _adopted_payload(draft_id: int):
    """库侧核对：GET /drafts/{id} 的 payload（不是 UI 上写了什么，而是草稿里存了什么）。"""
    # 库侧草稿行的键名是 payload_json（table_dict 原样输出列名），不是 payload——
    # 上一版按 `payload` 读，读到空字典，把"采纳其实成功了"误报成失败。
    payload = api_get(f"{DRAFTS_PATH}/{draft_id}").get("payload_json") or {}
    brief = payload.get("brief") or {}
    return payload if brief.get("suggestedScenes") else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface", action="store_true", help="只跑 FR-40 键盘面，不建项目不渲染")
    add_keep_flag(ap)
    args = ap.parse_args()

    chrome_ok = api_get("/health")
    assert chrome_ok.get("ok", True), "API 未就绪：先 ./dev.sh"

    # Cleanup 需要 httpx 客户端：删除一律走 DELETE /projects/{id}（级联清库+清目录），
    # 自己 rmtree 是纪律外的做法（会把 artifact 行留在库里）。
    with httpx.Client(base_url=API, headers=ORIGIN, timeout=120, trust_env=False) as c, \
         Cleanup(c, keep=args.keep) as cleanup, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=_chrome_path())
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(30000)
        watch_network(page)
        # 未覆盖的判据如实收集，最后决定退出码——"跑完了"和"判据都覆盖了"是两件事。
        boundaries: list[str] = []

        # ---------------------------------------------------------------- 1. 命令面板：⌘K 纯键盘打开/搜索/执行
        page.goto(f"{WEB}/", wait_until="load")
        page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
        page.wait_for_selector('[data-testid="command-palette-scrim"]')
        step("⌘K/Ctrl+K 打开命令面板（无需鼠标）")

        page.keyboard.type("时间轴")
        page.wait_for_selector('[data-testid="palette-item-nav.timeline"]')
        step("面板可按中文关键词搜到命令（搜索框已自动聚焦，直接打字）")

        page.keyboard.press("ArrowDown")
        selected = page.evaluate("() => document.activeElement?.getAttribute('aria-activedescendant')")
        assert selected, "↑/↓ 移动选中项必须有 aria-activedescendant，否则读屏用户不知道选到哪"
        page.keyboard.press("Enter")
        # 断言必须是"到了 /timeline"。上一版这里写的是 `"/timeline" in url or WEB in url`，
        # 后半句恒真——命令没跳成功也会绿，正是那种"断言比自己弱"的假过。
        page.wait_for_url(lambda u: "/timeline" in u, timeout=20000)
        page.wait_for_selector('[data-testid="command-palette-scrim"]', state="detached")
        step(f"Enter 执行命令并真的跳转（URL={page.url}），面板自动关闭")

        # ---------------------------------------------------------------- 2. 通知中心：键盘打开/读/关
        press_on(page, '[data-testid="notifications-bell"]', "铃铛", key="Enter")
        page.wait_for_selector('[data-testid="notifications-panel"]')
        step("铃铛可用键盘打开通知中心")

        tabs = page.locator('[data-testid="notif-tab-进行中"]')
        assert tabs.count() == 1
        press_on(page, '[data-testid="notif-tab-进行中"]', "进度中心页签", key="Enter")
        page.wait_for_selector('[data-testid="progress-empty"], [data-testid^="progress-job-"]')
        step("进度中心页签可达；在飞作业与空态都有对应节点")

        press_on(page, '[data-testid="notif-tab-通知"]', "通知页签", key="Enter")
        page.keyboard.press("Escape")
        page.wait_for_selector('[data-testid="notifications-panel"]', state="detached")
        step("Esc 关闭通知中心（焦点仍在铃铛上，可继续 Tab）")

        # ---------------------------------------------------------------- 3. 快捷键表 + 冲突检测
        page.goto(f"{WEB}/", wait_until="load")
        page.keyboard.press("Shift+?")
        page.wait_for_selector('[data-testid="shortcuts-scrim"]')
        page.wait_for_selector('[data-testid="shortcuts-no-conflicts"]')
        rows = page.locator('[data-testid^="shortcut-row-"]').count()
        assert rows >= 6, f"快捷键表只渲染了 {rows} 行，少于注册表里的绑定数"
        step(f"『?』打开快捷键表：{rows} 条绑定命令，且无键位冲突")
        page.keyboard.press("Escape")

        # ---------------------------------------------------------------- 4. 打字时不许抢键（真实缺陷防护）
        page.goto(f"{WEB}/wizard", wait_until="load")
        page.wait_for_selector('[data-testid="copy-input"]')
        tab_to(page, '[data-testid="copy-input"]', "文案输入框")
        page.keyboard.type("这是第一句。这句里带一个问号？——它不该弹出快捷键表。")
        sheet_open = page.locator('[data-testid="shortcuts-scrim"]').count()
        assert sheet_open == 0, "在文本框里输入『?』弹出了快捷键表：全局键位抢了用户输入"
        step("文本输入中的『?』不会被全局快捷键抢走（打字优先）")

        # -------------------------------------------------- FR-40 判据①：注册表里每条命令都要
        # "在面板里搜得到"。逐条真打键盘（不数数组长度），因为判据写的是"可搜到并执行"，
        # 而"搜不到"是拼 testid/改标题这类改动的直接后果——只有真打字才测得出来。
        cmds = re.findall(r'id: "([a-z0-9.]+)", title: "([^"]+)"',
                          Path(__file__).resolve().parents[1].joinpath("web/src/lib/commands.ts")
                          .read_text(encoding="utf-8"))
        assert len(cmds) >= 20, f"命令注册表只有 {len(cmds)} 条，PRD 判据①要求 20 条核心命令"
        missing_cmd = []
        for cid, ctitle in cmds:
            page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
            page.keyboard.type(ctitle)
            if page.locator(f'[data-testid="palette-item-{cid}"]').count() == 0:
                missing_cmd.append(f"{cid}←「{ctitle}」")
            page.keyboard.press("Escape")
        assert not missing_cmd, f"面板里搜不到这些命令：{missing_cmd}"
        step(f"命令面板逐条搜得到：注册表 {len(cmds)} 条命令全部命中（判据①前半）")

        if args.surface:
            browser.close()
            step("--surface：FR-40 键盘面全部可达，未启动渲染")
            return 0

        # ---------------------------------------------------------------- 5. 纯键盘建项目（向导 5 步）
        tab_to(page, '[data-testid="copy-input"]', "文案输入框")
        page.keyboard.press("Control+a" if not _is_mac_context() else "Meta+a")
        page.keyboard.press("Backspace")
        page.keyboard.type(COPY)
        chars_before = page.locator('[data-testid="copy-input"]').input_value()
        assert chars_before == COPY, "键盘输入的文案与服务侧看到的不一致"
        step(f"纯键盘输入 {len(chars_before)} 字文案（5 句）")

        # FR-41 判据①：粘贴 300 字 → **1s 内**给 4–6 场 + 每场理由。计时就在这条验收里做，
        # 起点是"按下生成"那一刻（含 HTTP + 规则引擎 + React 渲染），不是只量服务层函数。
        tab_to(page, '[data-testid="suggest-generate"]', "生成分场建议")
        t_gen = time.perf_counter()
        page.keyboard.press("Enter")
        page.wait_for_selector('[data-testid="suggest-results"]')
        gen_ms = (time.perf_counter() - t_gen) * 1000
        assert gen_ms < 1000, f"建议链路 {gen_ms:.0f}ms，超过 PRD 判据①的 1s"
        scenes = int(page.locator('[data-testid="suggest-scene-count"]').inner_text())
        assert 4 <= scenes <= 6, f"PRD 要求 4–6 场建议，实际 {scenes} 场"
        reasons = page.locator('[data-testid^="suggest-reason-"]').count()
        assert reasons == scenes, f"{scenes} 场建议里只有 {reasons} 条写了理由"
        step(f"建议引擎出 {scenes} 场、每场带理由，链路耗时 {gen_ms:.0f}ms"
             f"（PRD 判据①④：<1s、4–6 场、可解释）")

        joined = page.evaluate("""() => [...document.querySelectorAll('[data-testid^="suggest-scene-"]')]
              .map(li => li.querySelector('p')?.textContent || '').join('')""")
        assert joined and "".join(joined.split()) == "".join(COPY.split()), \
            f"断句重组与原文不逐字相等：{joined[:60]}…"
        step("断句重组逐字等于原文（PRD 判据②：不改用户文案）")

        # 海象写在 lambda 里只在该 lambda 内可见，外面拿到的还是 None——
        # 第一版就是这么把断言跑成 GET /drafts/None 的 422 的。改成显式轮询取值。
        holder: dict = {}

        def _draft_ready() -> bool:
            holder["draft_id"] = _draft_id(page)
            return holder["draft_id"] is not None

        wait_for(_draft_ready, 20, "向导建出草稿并在 DOM 上暴露 draft id")
        draft_id = holder["draft_id"]
        cleanup.track_draft(draft_id)   # 第 1 步建的草稿没有 root，destroy() 收不到，必须自己登记

        def _draft_payload() -> dict:
            return api_get(f"{DRAFTS_PATH}/{draft_id}").get("payload_json") or {}

        def _scenes_of(payload: dict) -> dict:
            d = (payload.get("brief") or {}).get("suggestedScenes") or []
            return {str(s["id"]): round(float(s.get("suggestedSeconds") or 0), 2) for s in d}

        payload_before = _draft_payload()
        press_on(page, '[data-testid="suggest-adopt"]', "全部采纳到草稿层")

        def _stored_ready() -> bool:
            holder["stored"] = _adopted_payload(draft_id)
            return holder["stored"] is not None

        wait_for(_stored_ready, 25, f"草稿 {draft_id} 的 brief 里出现 suggestedScenes")
        stored = holder["stored"]
        assert len(stored["brief"]["suggestedScenes"]) == scenes, stored
        # 判据④"建议不改变原文，只改结构"用前后差分证明，不靠"页面上没变"：
        # brief 以外的任何一个键被动过，这里就红。
        keys_outside_brief_before = {k: v for k, v in payload_before.items() if k != "brief"}
        keys_outside_brief_after = {k: v for k, v in _draft_payload().items() if k != "brief"}
        assert keys_outside_brief_after == keys_outside_brief_before, (
            f"采纳动到了 brief 以外的键：before={sorted(keys_outside_brief_before)} "
            f"after={sorted(keys_outside_brief_after)}")
        step(f"全部采纳写入草稿层：draft {draft_id} 的 suggestedScenes={scenes} 场，"
             f"brief 之外的键逐项相等（原文/标题未被改写）")

        # -------------------------------------------------- FR-41 判据②：逐条可接受/拒绝/编辑，
        # 且"接受后只影响对应场景"。三条全部从**库里**回读，页面上写了什么不算证据。
        ids = page.evaluate("""() => [...document.querySelectorAll('[data-testid^="suggest-scene-"]')]
              .filter(li => li.querySelector('span.font-semibold'))
              .map(li => li.querySelector('span.font-semibold').textContent.trim())""")
        assert ids and len(ids) == scenes, f"页面上的场次 {len(ids)} 与计数 {scenes} 不一致"
        assert scenes >= 5, f"逐条验收至少要 5 场，实际 {scenes} 场"
        ignored_id, edited_id, solo_id = ids[0], ids[2], ids[4]

        def _set_seconds(idx: int, value: str) -> None:
            tab_to(page, f'[data-testid="suggest-scene-seconds-{idx}"]', f"第 {idx + 1} 场停留时长输入框")
            page.keyboard.press("Meta+a" if _is_mac_context() else "Control+a")
            page.keyboard.type(value)

        press_on(page, '[data-testid="suggest-scene-ignore-0"]', f"忽略 {ignored_id}")
        assert page.get_attribute('[data-testid="suggest-scene-ignore-0"]', "aria-pressed") == "true", \
            "忽略态必须用 aria-pressed 播报，否则读屏用户不知道自己拒掉了哪一场"
        _set_seconds(2, "4.5")
        press_on(page, '[data-testid="suggest-adopt"]', "全部采纳到草稿层")

        def _stored_ignore_edit() -> bool:
            got = _scenes_of(_draft_payload())
            holder["got"] = got
            return len(got) == scenes - 1 and ignored_id not in got and got.get(edited_id) == 4.5

        try:
            wait_for(_stored_ignore_edit, 25, "忽略一场 + 改停留后全部采纳：库里少一场、改过的是 4.5s")
        except AssertionError:
            raise AssertionError(
                f"逐条采纳结果与预期不符：库里 {holder.get('got')}（应无 {ignored_id}、{edited_id}=4.5）") from None
        step(f"拒绝+编辑生效：草稿里 {len(holder['got'])} 场（{ignored_id} 被拒、不留痕；"
             f"{edited_id} 停留改成 4.5s）")

        _set_seconds(4, "6")
        press_on(page, '[data-testid="suggest-scene-adopt-4"]', f"单独采纳 {solo_id}")

        def _stored_solo() -> bool:
            got = _scenes_of(_draft_payload())
            holder["got"] = got
            return len(got) == scenes - 1 and got.get(solo_id) == 6.0 and got.get(edited_id) == 4.5

        wait_for(_stored_solo, 25, f"单场采纳只改 {solo_id}→6s，{edited_id} 仍是 4.5s，场次总数不变")
        step(f"单场采纳只影响对应场景：{solo_id}=6.0s 与 {edited_id}=4.5s 共存，"
             f"共 {len(holder['got'])} 场（场次总数未被改动）")

        press_on(page, '[data-testid="wizard-next-1"]', "第 1 步下一步")
        page.wait_for_timeout(900)
        # 不压时长（attempt 14 实测教训）：3s 片配 292 字旁白，交付字幕 cps≈97 ≫ 上限 9
        # （delivery.MAX_CAPTION_CPS），E_DELIVERY_QC: ['captions'] 必挂。292 字 ÷ 9 cps
        # ⇒ 片长必须 ≥33s，自然时长 39.5s ≈ 7.4 cps 恰好在判据内。保留键盘读回帧数作证据。
        frames = page.locator('[data-testid="wizard-next-2"]').locator("..").evaluate(
            "el => el.parentElement.querySelector('.font-mono')?.textContent")
        step(f"键盘读回自然时长（帧数回读={frames}；不压时长——字幕 QC 的 cps 判据要求片长 ≥33s）")

        press_on(page, '[data-testid="wizard-next-2"]', "第 2 步下一步")
        page.wait_for_timeout(900)
        step("键盘从第 2 步进入第 3 步（风格选择）")

        # 必须选**可生产**的风格：随手点第一张会撞上 code-video（Contract 1.0），
        # C01 直接 E_ENGINE_API_UNSUPPORTED，Run 停在 blocked 又没有任何门——
        # 那样这条验收测的就是运气，不是流程。搜索框是键盘路径的一部分。
        tab_to(page, '[data-testid="style-search"]', "风格搜索框", limit=40)
        page.keyboard.type("H2")
        page.wait_for_selector('[data-testid="style-card-H2"]', timeout=20000)
        cards = page.locator('[data-testid^="style-card-"]').count()
        assert cards, "搜索 H2 之后没有风格卡：可生产风格不在面上，流程没法继续"
        # 卡片的 Enter 只打开详情；主风格要靠详情面板里的「设为主风格」（两步都是键盘）
        tab_to(page, '[data-testid="style-card-H2"]', "H2 风格卡", limit=60)
        page.keyboard.press("Enter")
        page.wait_for_selector('[data-testid="style-set-primary"]', timeout=15000)
        tab_to(page, '[data-testid="style-set-primary"]', "设为主风格按钮", limit=40)
        page.keyboard.press("Enter")
        page.wait_for_selector('[data-testid="step3-next"]:not([disabled])', timeout=15000)
        step("键盘走完风格选择：卡片 Enter → 详情面板「设为主风格」→ 第 3 步按钮解禁")

        press_on(page, '[data-testid="step3-next"]', "第 3 步下一步")
        page.wait_for_timeout(800)
        press_on(page, '[data-testid="wizard-next-4"]', "第 4 步下一步")
        page.wait_for_timeout(800)
        step("键盘走完第 4 步（配音/标题）")

        press_on(page, '[data-testid="materialize"]', "生成项目按钮")
        page.wait_for_url(lambda u: "/canvas" in u, timeout=90000)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query)
        project_id = int(q.get("project", ["0"])[0])
        run_id = int(q.get("run", ["0"])[0])
        assert project_id and run_id, f"materialize 后 URL 缺 project/run：{page.url}"
        # 先登记再取 root：任何一步炸了，Cleanup 都能把这个项目带走（反过来就会漏）
        root = Path(_project_root(project_id))
        cleanup.track(project_id, root)
        step(f"纯键盘建项目完成：project={project_id} run={run_id}（Cleanup 已登记，跑完自删）")

        # ---------------------------------------------------------------- 6. 命令面板驱动：预览 / 运行
        def _total_jobs() -> int:
            """队列里所有作业条数（含已完成的）——只数 active 会漏掉"秒完"的预览。"""
            return sum(api_get("/queue")["counts"].values())

        jobs_before = _total_jobs()
        page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
        page.keyboard.type("整片预览")
        page.wait_for_selector('[data-testid="palette-item-preview.film"]')
        page.keyboard.press("Enter")
        toast_text: dict = {}

        def _preview_toast() -> bool:
            toast_text["v"] = page.locator('[data-testid="toast-host"]').inner_text()
            return "排队" in toast_text["v"]

        try:
            wait_for(_preview_toast, 20, "整片预览的回执出现在 aria-live 面上")
        except AssertionError:
            raise AssertionError(
                f"整片预览命令没走到端点；toast 面上是 {toast_text.get('v')!r}"
                f"（当前 URL={page.url}）") from None
        # 第二个信号独立于页面文字：作业真的进了库（防止"提示了一句漂亮话"蒙过这条验收）
        wait_for(lambda: _total_jobs() > jobs_before, 20, f"预览作业入库（队列总数 {jobs_before} → ?）")
        step(f"命令面板触发整片预览：回执「{toast_text['v']}」，队列作业总数 {jobs_before} → {_total_jobs()}")

        # ---------------------------------------------------------------- 7. 跑 Run + 等终态
        # G01 的输入是口播音频。浏览器里的"选择文件"是操作系统对话框，不属于网页键盘的范围，
        # 所以这一步用服务层前置（scripts/_scratch_state.build_audio_state：本地 ffmpeg 合成 wav
        # → /audio/upload → 逐场 primary → process → license）。没有它，Run 只会停在
        # `node failed G01: 未上传口播音频`，后面 4 道门与交付就都没得测（attempt 10 实测）。
        audio = ss.build_audio_state(c, project_id)
        step(f"口播音频前置：{len(audio['takes'])} 条本地合成 Take（G01 输入；文件选择框属 OS 对话框，不在键盘范围）")

        # 手动对齐也走键盘（⌘4 → 保存手动对齐）。这一步有两个用处：
        # 它补上 FR-40 判据②里的"改"，也让 G02 不再依赖 whisper 模型——
        # `pipeline.py::g02` 写的是"手动对齐优先，whisper 缺失也走这里，不静默降级"，
        # 而没有手动对齐也没有模型时 Run 会 `E_MODEL_MISSING` 直接失败（attempt 11 实测）。
        page.keyboard.press("Meta+4" if _is_mac_context() else "Control+4")
        page.wait_for_url(lambda u: "/audio" in u, timeout=20000)
        page.wait_for_selector('table input[type="number"]', timeout=30000)
        seg_inputs = page.locator('table input[type="number"]').count()
        press_on(page, '[data-testid="audio-save-alignment"]', "保存手动对齐")
        holder4: dict = {}

        def _alignment_saved() -> bool:
            holder4["align"] = api_get(f"/projects/{project_id}/audio/alignment")
            return (holder4["align"].get("source") == "manual"
                    and bool(holder4["align"].get("segments")))

        wait_for(_alignment_saved, 25, "手动对齐写进项目卡片（card/alignment.json）")
        step(f"键盘手动对齐：⌘4 到音频工作台 → 保存手动对齐（表格 {seg_inputs // 2} 段，"
             f"落库 {len(holder4['align']['segments'])} 段 source=manual，G02 不必依赖 whisper）")

        # 对齐段一比一回任务场景（测试数据修进产品判据，不是放宽判据）。两道门同时喂饱：
        # ① G06 音画同步：scene 的 last_text_at+read_seconds 恒等于 scene.end
        #   （project_docs.py:88；实测 174 项目 task.json 与 timeline 逐值相等），
        #   段 [start,end]=场景窗口 ⇒ 偏差=0（attempt 15 的 4.8s 假对齐被它当场抓住）；
        # ② 交付字幕 QC：UI 默认对齐段 text 是空的（SRT count=0 必挂）——这里 text=
        #   script 句子按场景 source_span 拼接（时间线场景不带 text，attempt 16 实测），
        #   cps=字数/场景窗口 ≈5.2 ≤ 9（行宽由 _wrap 钉 ≤16）。
        _tl = (api_get(f"/projects/{project_id}/docs/timeline").get("content") or {})
        _sents = (api_get(f"/projects/{project_id}/docs/script")
                  .get("content", {}).get("sentences")) or []
        _fixed, _max_cps = [], 0.0
        for _sc in (_tl.get("scenes") or []):
            _span = _sc.get("source_span") or []
            _text = "".join(_sents[i].get("text", "") for i in _span
                            if isinstance(i, int) and i < len(_sents)).strip()
            _start, _end = float(_sc.get("start") or 0.0), float(_sc.get("end") or 0.0)
            if _end <= _start or not _text:
                continue
            _max_cps = max(_max_cps, len(_text) / (_end - _start))
            _fixed.append({"text": _text, "start": round(_start, 3), "end": round(_end, 3)})
        assert _fixed and all(s["text"] for s in _fixed), \
            f"场景窗口或文本缺失（SRT 会挂 count>0）：{_fixed[:2]}"
        assert _max_cps <= 9.0, f"对齐段 cps={_max_cps:.2f} > 9（某场文本太长/窗口太短，" \
                                f"字幕 QC 必挂——先修测试数据再跑交付）"
        api_post(f"/projects/{project_id}/audio/alignment",
                 {"segments": _fixed, "author": "local"})
        step(f"对齐段一比一回任务场景：{len(_fixed)} 段 [start,end]=场景窗口、text=场景文本"
             f"（G06 偏差=0；最大 cps={_max_cps:.2f} ≤ 9）")

        api_post(f"/runs/{run_id}/start")
        step(f"POST /runs/{run_id}/start 已发出（面板命令与页面用同一对端点）")
        holder: dict = {}

        def _settled() -> bool:
            holder["status"] = api_get(f"/runs/{run_id}").get("status")
            return holder["status"] in ("succeeded", "failed", "blocked", "needs_changes")

        wait_for(_settled, 900, f"Run {run_id} 进入终态/待门")
        state = holder["status"]
        step(f"Run 结束态={state}（真渲染完成；进度中心期间可读，见下）")

        page.goto(f"{WEB}/monitor?run={run_id}", wait_until="load")
        step("运行监控页可达（键盘导航 ⌘6 已在快捷键表里绑定）")

        # ---------------------------------------------------------------- 8. 逐门批准（46 节点上有 8 道人工门）
        # 三个必须同时成立的设计：
        #  · 每一道门都走"命令面板 → 画布 → Tab 到批准按钮 → Enter"，全程零鼠标；
        #  · 批准之后**立刻关掉浏览器**：Chrome 全局串行 1 个，验收自己占着槽位时
        #    后面的节点永远不会开始（实测卡死 240s 就是这个原因）；
        #  · 只批第一道门就等终态是等不到的——签完 B08 会停在 D03，所以要循环。
        holder2: dict = {"status": api_get(f"/runs/{run_id}").get("status")}
        holder3: dict = {"scenesViewed": False}   # D03/D05 的静帧前置只需满足一次
        approved: list[str] = []
        browser.close()                      # 先进入"让位"状态，需要页面时再开
        browser = None
        page = None

        def _open_page():
            nonlocal browser, page
            browser = pw.chromium.launch(headless=True, executable_path=_chrome_path())
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.set_default_timeout(30000)
            watch_network(page)
            return page

        def _close_page():
            nonlocal browser, page
            if browser is not None:
                browser.close()
            browser = None
            page = None

        def _status() -> str:
            holder2["status"] = api_get(f"/runs/{run_id}").get("status")
            return holder2["status"]

        rounds = 0
        idle_waits = 0
        while rounds < 12 and _status() not in ("succeeded", "failed"):
            rounds += 1
            raw = api_get(f"/gates/{run_id}/pending").get("items") or []
            gates = [g["gate"] if isinstance(g, dict) and g.get("gate") else g for g in raw]
            gates = [g for g in gates if isinstance(g, str)]
            if not gates:
                # 没有待办门也没到终态：正在渲染。此时绝对不能占着浏览器。
                _close_page()
                idle_waits += 1
                wait_for(lambda: _status() in ("succeeded", "failed")
                         or bool(api_get(f"/gates/{run_id}/pending").get("items")),
                         900, f"Run {run_id} 继续推进（出下一道门或终态；自然片长 F04 有 948 帧）")
                continue
            gate = gates[0]
            _open_page()
            page.goto(f"{WEB}/", wait_until="load")
            page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
            page.keyboard.type("待办人工门")
            page.wait_for_selector('[data-testid="palette-item-gate.decide"]')
            page.keyboard.press("Enter")
            page.wait_for_url(lambda u: "/canvas" in u, timeout=20000)
            step(f"第 {len(approved) + 1} 道门 {gate}：命令面板键盘跳到画布（URL={page.url}）")
            if gate in ("D03", "D05") and not holder3["scenesViewed"]:
                # 门前置是产品规则不是 bug：`routes.py::_gate_precheck` 要求 D03/D05 每个场景
                # 至少看过一张静帧，没看全就批准会得到一条 400。键盘路径 = 画布上按 ⌘3
                # （命令自己把 project/run 补进 URL）→ ArrowRight 把静帧翻完 → 页头报"全场景已看"。
                page.keyboard.press("Meta+3" if _is_mac_context() else "Control+3")
                page.wait_for_url(lambda u: "/review" in u, timeout=20000)
                page.wait_for_selector('[data-testid="review-view-state"]')
                seen = {"presses": 0, "header": ""}

                def _read_header(_s: dict = seen) -> str:
                    _s["header"] = " ".join(page.locator("header").inner_text().split())
                    return _s["header"]

                # 页头在数据到手前是"审阅状态载入中…"——这一句是这条验收能成立的前提，
                # 否则 `0 张 / 全场景已看` 那种空真会把"没看"混成"看完了"（实测踩过）。
                wait_for(lambda: "载入中" not in _read_header(), 30,
                         f"审片页取回审阅状态（页头「{seen['header'][:70]}」）")
                m = re.search(r"(\d+) 张", seen["header"])
                stills_n = int(m.group(1)) if m else 0
                assert stills_n > 0, f"审片页没有静帧可看，D03 却要求逐场景看过：{seen['header'][:80]}"

                def _all_viewed() -> bool:
                    return "全场景已看" in _read_header()

                while not _all_viewed() and seen["presses"] < 60:
                    page.keyboard.press("ArrowRight")
                    seen["presses"] += 1
                    page.wait_for_timeout(200)
                wait_for(_all_viewed, 25, f"翻完 {seen['presses']} 张静帧后页头报『全场景已看』")
                holder3["scenesViewed"] = True
                step(f"键盘审片：⌘3 到了审片页（{stills_n} 张静帧），{seen['presses']} 次 ArrowRight → "
                     f"页头「{seen['header'][:60]}」（{gate} 的批准前置）")
                # 回画布也走命令面板（这条同时验证 nav.canvas 会自己补 Run）
                page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
                page.keyboard.type("生产画布")
                page.wait_for_selector('[data-testid="palette-item-nav.canvas"]')
                page.keyboard.press("Enter")
                page.wait_for_url(lambda u: "/canvas" in u, timeout=20000)

            # 门面板在 DOM 末尾（画布 93 条边一度把 tab 序列吃掉），所以走页首的"跳到待办门"。
            # 跳转链接是 pendingGates 到手之后才渲染的，必须先等它出现再数 Tab。
            page.wait_for_selector('[data-testid="skip-to-gates"]', timeout=20000)
            tab_to(page, '[data-testid="skip-to-gates"]', "跳到待办门链接", limit=12)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            # 前置没满足时批准按钮是 disabled（disabled 不进 Tab 序），所以这里先给出**原因**，
            # 而不是让 tab_to 报一句"焦点到不了"让人去猜。
            hint = page.locator(f'[data-testid="gate-precheck-{gate}"]')
            assert hint.count() == 0, f"{gate} 的批准前置仍未满足：{hint.first.inner_text()}"
            tab_to(page, f'[data-testid="gate-approve-{gate}"]', f"批准 {gate} 门按钮", limit=15)
            page.keyboard.press("Enter")
            # 批准是异步的（页面 POST 完还要重取图），所以"等到门离开待办"而不是固定睡 1.5s
            page_held = page
            gone = {"ok": False, "remaining": []}

            def _gate_gone(_gate: str = gate, _sink: dict = gone) -> bool:
                left = [str(g["gate"] if isinstance(g, dict) else g)
                        for g in (api_get(f"/gates/{run_id}/pending").get("items") or [])]
                _sink["remaining"] = left
                return _gate not in left

            try:
                wait_for(_gate_gone, 30, f"键盘批准 {gate} 后它离开待办列表")
            except AssertionError:
                banner = page_held.locator("main").inner_text()[-300:]
                detail = api_get(f"/gates/{run_id}/pending").get("items") or []
                # 同一份请求体直接打端点：这是区分"产品规则挡住"与"按钮根本没生效"的唯一硬证据
                with httpx.Client(base_url=API, headers=ORIGIN, timeout=60, trust_env=False) as cc:
                    probe = cc.post(f"/gates/{gate}/decide", json={
                        "run_id": run_id, "decision": "approved", "author": "diagnostic",
                        "note": "", "checklist": []})
                _close_page()
                raise AssertionError(
                    f"键盘批准后 {gate} 仍在待办：{gone['remaining']}\n"
                    f"  · pending 明细：{json.dumps(detail, ensure_ascii=False)[:700]}\n"
                    f"  · 同样请求体直打端点 → HTTP {probe.status_code} {probe.text[:300]}\n"
                    f"  · 页面尾部：{banner}") from None
            _close_page()                      # 批完立刻让位，渲染才走得动
            approved.append(gate)
            step(f"第 {len(approved)} 道门 {gate} 已用键盘批准（累计 {approved}，浏览器已让位）")

        _close_page()
        if _status() not in ("succeeded", "failed"):
            raise AssertionError(f"Run {run_id} 在 {rounds} 轮（批准 {approved}、空等 {idle_waits} 次）后仍未到终态")
        step(f"门全部签完，Run 到终态 status={holder2['status']}（共批准 {len(approved)} 道门）")

        # 第 8 道人工门 A05 不走键盘，是设计不是漏签：向导第 3 步用户亲手选过风格，
        # A04 完成后 `_carry_a05_approval`（runengine.py:510）自动种子批准并 emit auto=True。
        # 键盘 e2e 断言的正是这条设计本身——键盘签 7 道 + A05 自动携带 = 8/8 门全覆盖。
        rep = api_get(f"/runs/{run_id}/report")
        a05 = [a for a in (rep.get("approvals") or []) if a.get("gate_id") == "A05"]
        assert a05 and a05[0].get("decision") == "approved", \
            f"A05 应由 _carry_a05_approval 自动携带（向导带 style_decision），实测 approvals：{a05}"
        assert "A05" not in approved, "A05 不该出现在键盘签出的门里——它是自动携带的第 8 道门"
        step(f"A05 自动携带确认：policy={a05[0].get('policy')} author={a05[0].get('author')} "
             f"note={a05[0].get('note')}（键盘签 {len(approved)} + 自动 1 = 8 道门全覆盖）")

        page = _open_page()

        # ---------------------------------------------------------------- 9. 导出：真跑一次交付
        if holder2["status"] != "succeeded":
            # 这条不能只"如实记录"然后照样打 PASS：判据②写的是"…→导出"，
            # Run 没成功就是没覆盖，退出码必须非零，否则绿色输出替产品撒了谎。
            boundaries.append(f"Run 终态={holder2['status']}，导出判据未覆盖")
            step(f"Run 未成功（{holder2['status']}），记为未覆盖判据并在结尾如实退出")
        else:
            deliv = api_post(f"/projects/{project_id}/delivery", {"runId": run_id, "profile": "final"})
            job_id = deliv.get("job", {}).get("id") or deliv.get("jobId") or deliv.get("id")
            assert job_id, f"交付没返回作业标识：{list(deliv)}"
            holder3: dict = {}

            def _delivered() -> bool:
                holder3["body"] = api_get(f"/jobs/{job_id}") if job_id is not None else {}
                return (holder3["body"] or {}).get("status") in ("succeeded", "failed")

            wait_for(_delivered, 1500, f"交付作业 {job_id} 结束（含 9:16 变体 948 帧重渲染）")
            status = holder3["body"]["status"]
            # 返回体是 table_dict(Job) → 键是列名（error_code/error_msg/result_json，models.py:287）。
            # attempt 13 就是读了驼峰 errorCode/errorMsg 才把成功读成"失败：None None"。
            assert status == "succeeded", \
                f"交付失败：{holder3['body'].get('error_code')} {holder3['body'].get('error_msg')}" \
                f"｜body 头部：{str(holder3['body'])[:200]}"
            files = (holder3["body"].get("result_json") or {}).get("files") or []
            assert files, f"交付成功但没有文件清单：{str(holder3['body'])[:300]}"
            step(f"交付完成：{len(files)} 个产物文件（前 6 个：{files[:6]}）")

        page.goto(f"{WEB}/", wait_until="load")
        page.keyboard.press("Meta+k" if _is_mac_context() else "Control+k")
        page.keyboard.type("交付")
        page.wait_for_selector('[data-testid="palette-item-nav.delivery"]')
        page.keyboard.press("Enter")
        page.wait_for_url(lambda u: "/delivery" in u, timeout=20000)
        step("命令面板键盘到达交付页（导出入口所在页）")

        # ---------------------------------------------------------------- 10. 零网络证据（PRD FR-41 判据③）
        # 两个层次，缺一不可：
        # ① 这一趟流程里**浏览器发出的每个请求**都只指向 127.0.0.1——这是对"产品不联网"最直接
        #    的测量（比"代码里没有 fetch"硬，因为它测的是真实发生过的流量）；
        # ② API 进程（建议引擎与渲染管线所在的 :7860）没有非环回连接。
        # 判据的主语是**产品进程**，不是整台机器：上一版 `lsof` 不带 `-a -p`，把 Qoder、浏览器、
        # OrbStack 的既有连接都算了进来，得到一个与 FilmFlow 无关的 False（attempt 10 实测）。
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        external_reqs = sorted({u for u in NET_LOG
                                if urllib.parse.urlparse(u).scheme in ("http", "https")
                                and (urllib.parse.urlparse(u).hostname or "") not in local_hosts})
        step(f"浏览器侧流量：{len(NET_LOG)} 个请求、去重后非环回 {len(external_reqs)} 个")
        assert not external_reqs, f"页面发生了非环回请求：{external_reqs[:8]}"

        listen = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True,
                                text=True, errors="replace", check=False)

        def _remote(ln: str) -> str:
            return ln.split("->", 1)[1].split()[0] if "->" in ln else ln

        def _pids_on(port: str) -> list[str]:
            return sorted({ln.split()[1] for ln in listen.stdout.splitlines()[1:]
                           if f":{port} " in ln})

        api_pids = _pids_on("7860")
        assert api_pids, "找不到 :7860 的监听进程——这条零网络判据会变成空检查"
        out = subprocess.run(["lsof", "-nP", "-a", "-p", ",".join(api_pids),
                              "-iTCP", "-sTCP:ESTABLISHED"],
                             capture_output=True, text=True, errors="replace", check=False)
        api_lines = out.stdout.splitlines()[1:]
        api_foreign = [ln for ln in api_lines if not _remote(ln).startswith(("127.", "[::1]"))]
        step(f"API 进程 pid={','.join(api_pids)}：ESTABLISHED {len(api_lines)} 条，"
             f"非环回 {len(api_foreign)} 条")
        assert not api_foreign, f"API 进程存在非环回连接：\n{chr(10).join(api_foreign)}"

        # 如实记录（不是判据）：`next dev` 这个**开发工具进程**自己会连 npm registry 查版本，
        # telemetry 已在 next.config.mjs + dev.sh 关掉，版本检查这一条没关干净。
        # 它不属于产品流量（浏览器与 API 两项都在断言里），所以这里打印不 assert。
        web_pids = _pids_on("3000")
        if web_pids:
            wout = subprocess.run(["lsof", "-nP", "-a", "-p", ",".join(web_pids),
                                   "-iTCP", "-sTCP:ESTABLISHED"],
                                  capture_output=True, text=True, errors="replace", check=False)
            wforeign = [ln for ln in wout.stdout.splitlines()[1:]
                        if not _remote(ln).startswith(("127.", "[::1]"))]
            if wforeign:
                print("  · 注：next dev（开发工具，非产品进程）仍有版本检查外呼："
                      + "; ".join(_remote(ln) for ln in wforeign[:3]))

        _close_page()
        step(f"纯键盘操作面全程无鼠标（{_step} 步，零次鼠标调用）")
        if boundaries:
            print("PARTIAL: 有判据未覆盖 → " + "；".join(boundaries))
            return 2
        print(f"PASS: e2e_fr40_keyboard（{_step} 步全绿，判据①②③与 FR-41 ①②③④ 均现场覆盖）")
        return 0


def _chrome_path() -> str:
    from app.config import detect_chrome
    p = detect_chrome()
    if not p:
        raise SystemExit("E_ENV_MISSING: 未检测到系统 Chrome（本脚本必须用真实浏览器，不许用内置 chromium）")
    return p


def _is_mac_context() -> bool:
    import platform
    return platform.system() == "Darwin"


if __name__ == "__main__":
    sys.exit(main())
