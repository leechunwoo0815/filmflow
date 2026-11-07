// FR-40：命令注册表——命令面板、快捷键表、冲突检测**都从这一份派生**。
//
// 为什么要有单一真源：快捷键最典型的腐化是"面板里一套、按下处理里另一套、帮助页再写一套"，
// 三处手写迟早不同步，而且用户按下去发现和看到的不是同一件事。这里把
// 「有什么命令 / 它绑哪个键 / 它做什么」钉成一个数组，面板与 `?` 视图都读它。
import { useRouter } from "next/navigation";

import { api } from "./api";

export type CommandGroup = "导航" | "生产" | "审阅" | "系统";

export interface CommandCtx {
  router: ReturnType<typeof useRouter>;
  /** 需要组件内部状态的动作（打开面板、标记已读）通过事件总线派发，见 dispatchAppEvent */
  notify: (message: string) => void;
}

export interface AppCommand {
  id: string;
  title: string;
  keywords: string;              // 搜索命中用（小写、空格分隔的同义词）
  group: CommandGroup;
  shortcut?: string;             // 展示用，如 "⌘K" / "Ctrl+K" 由 isMac 决定，这里只写规范名
  /** 全局快捷键（小写，含修饰符前缀），见 matchKey } */
  key?: { mod: "cmd" | "ctrl" | "none"; shift?: boolean; key: string };
  run: (ctx: CommandCtx) => void | Promise<void>;
}

// ---------------------------------------------------------------- 事件总线（小颗粒，够用就好）

type Handler = (detail?: unknown) => void;
const listeners = new Map<string, Set<Handler>>();

export function onAppEvent(name: string, fn: Handler): () => void {
  const set = listeners.get(name) ?? new Set<Handler>();
  set.add(fn);
  listeners.set(name, set);
  return () => set.delete(fn);
}

export function dispatchAppEvent(name: string, detail?: unknown): void {
  for (const fn of listeners.get(name) ?? []) fn(detail);
}

// ---------------------------------------------------------------- 导航命令

function go(path: string) {
  return (ctx: CommandCtx) => ctx.router.push(path === "home" ? "/" : `/${path}`);
}

/** 项目内的页面：把当前 `project` 带过去，而不是丢一个没有参数的空页。 */
function goWithProject(path: string) {
  return (ctx: CommandCtx) => {
    const id = currentProjectId();
    if (!id) { ctx.notify("当前页面没有项目上下文：先到首页（⌘1）点开一个项目"); return; }
    ctx.router.push(`/${path}?project=${id}`);
  };
}

/** 必须绑定一次 Run 才有内容的页面（画布、审片）：沿用 URL 上的 run，没有就取该项目最新 Run。 */
function goWithRun(path: string) {
  return async (ctx: CommandCtx) => {
    const id = currentProjectId();
    if (!id) { ctx.notify("当前页面没有项目上下文：先到首页（⌘1）点开一个项目"); return; }
    const q = new URLSearchParams(window.location.search);
    const fromUrl = q.get("run");
    const run = fromUrl && /^\d+$/.test(fromUrl)
      ? Number(fromUrl)
      : (await api<{ items: { id: number }[] }>(`/projects/${id}/runs`)).items.at(-1)?.id;
    if (!run) { ctx.notify(`项目 ${id} 还没有 Run：用「运行当前项目」先跑一次`); return; }
    ctx.router.push(`/${path}?project=${id}&run=${run}`);
  };
}

// ---------------------------------------------------------------- 注册表

export const COMMANDS: AppCommand[] = [
  // —— 系统
  {
    id: "palette.open", title: "打开命令面板", keywords: "palette command 命令 面板",
    group: "系统", shortcut: "⌘K / Ctrl+K", key: { mod: "cmd", key: "k" },
    run: () => dispatchAppEvent("palette:open"),
  },
  {
    id: "shortcuts.show", title: "查看快捷键表", keywords: "shortcut help 快捷键 帮助 冲突",
    // 键名用 "?" 而不是 "/"：按出问号本来就要 Shift，浏览器给出的 e.key 是 "?"，
    // 若声明成 shift+"/" 就永远匹配不上（真跑 e2e 时第一次就按不出来）。
    group: "系统", shortcut: "?", key: { mod: "none", shift: true, key: "?" },
    run: () => dispatchAppEvent("shortcuts:open"),
  },
  {
    id: "notifications.open", title: "打开通知中心", keywords: "notification bell 通知 铃铛 消息",
    group: "系统", shortcut: "⌘⇧N / Ctrl+Shift+N", key: { mod: "cmd", shift: true, key: "n" },
    run: () => dispatchAppEvent("notifications:open"),
  },
  {
    id: "notifications.readAll", title: "全部标记已读", keywords: "read all 已读 清空 未读",
    group: "系统",
    run: async (ctx) => {
      const r = await api<{ marked: number }>("/notifications/read-all", { method: "POST" });
      dispatchAppEvent("notifications:refresh");
      ctx.notify(`已标记 ${r.marked} 条为已读`);
    },
  },
  {
    id: "theme.toggle", title: "切换明暗主题", keywords: "theme dark light 主题 深色 浅色",
    group: "系统",
    run: () => dispatchAppEvent("theme:toggle"),
  },
  // —— 导航（前 8 个高频页给快捷键）
  { id: "nav.home", title: "前往：首页", keywords: "home 首页 dashboard", group: "导航", shortcut: "⌘1", key: { mod: "cmd", key: "1" }, run: go("home") },
  { id: "nav.timeline", title: "前往：时间轴", keywords: "timeline 时间轴 场景", group: "导航", shortcut: "⌘2", key: { mod: "cmd", key: "2" }, run: go("timeline") },
  { id: "nav.review", title: "前往：审片", keywords: "review 审片 播放 静帧", group: "导航", shortcut: "⌘3", key: { mod: "cmd", key: "3" }, run: goWithRun("review") },
  { id: "nav.audio", title: "前往：音频", keywords: "audio 音频 口播", group: "导航", shortcut: "⌘4", key: { mod: "cmd", key: "4" }, run: goWithProject("audio") },
  { id: "nav.assets", title: "前往：资产库", keywords: "assets 资产 图片 字体", group: "导航", shortcut: "⌘5", key: { mod: "cmd", key: "5" }, run: go("assets") },
  { id: "nav.qa", title: "前往：质量检查", keywords: "qa 质量 修复", group: "导航", run: go("qa") },
  { id: "nav.delivery", title: "前往：交付", keywords: "delivery 交付 打包", group: "导航", run: go("delivery") },
  { id: "nav.takes", title: "前往：Take 对比", keywords: "takes 对比 ab", group: "导航", run: go("takes") },
  { id: "nav.templates", title: "前往：模板库", keywords: "templates 模板 系列", group: "导航", run: go("templates") },
  { id: "nav.canvas", title: "前往：生产画布", keywords: "canvas 画布 节点 46", group: "导航", run: goWithRun("canvas") },
  { id: "nav.monitor", title: "前往：运行监控", keywords: "monitor 监控 队列", group: "导航", run: go("monitor") },
  { id: "nav.editor", title: "前往：文档编辑", keywords: "editor 文档 项目卡", group: "导航", run: go("editor") },
  { id: "nav.wizard", title: "前往：新建向导", keywords: "wizard 新建 向导", group: "导航", run: go("wizard") },
  { id: "nav.labeling", title: "前往：人工补标", keywords: "labeling 补标 调色板", group: "导航", run: go("labeling") },
  { id: "nav.help", title: "前往：帮助", keywords: "help 帮助 说明", group: "导航", run: go("help") },
  // —— 生产
  {
    // 真链路：项目的 workflow（从已有 Run 反查）→ POST /runs → POST /runs/{id}/start。
    // 刻意不新开一个"便利端点"：画布/时间轴用的就是这两个端点，面板必须走同一条路，
    // 否则面板能跑而页面上跑不通（或反过来）就没人会发现。
    id: "run.project", title: "运行当前项目", keywords: "run 运行 渲染 生产 start",
    group: "生产",
    run: async (ctx) => {
      const id = currentProjectId();
      if (!id) { ctx.notify("当前页面没有项目上下文：先进入某个项目（⌘2 时间轴）"); return; }
      const { items } = await api<{ items: { workflow_id: number }[] }>(`/projects/${id}/runs`);
      const wf = items.at(-1)?.workflow_id;
      if (!wf) { ctx.notify("这个项目还没有 workflow/Run：请先走一次新建向导"); return; }
      const run = await api<{ id: number }>("/runs", { method: "POST", body: JSON.stringify({ workflowId: wf }) });
      await api(`/runs/${run.id}/start`, { method: "POST", body: "{}" });
      ctx.notify(`Run ${run.id} 已开始`);
      ctx.router.push(`/canvas?project=${id}&run=${run.id}`);
    },
  },
  {
    id: "preview.film", title: "整片预览（当前项目）", keywords: "preview film 预览 整片 快速",
    group: "生产",
    run: async (ctx) => {
      const id = currentProjectId();
      if (!id) { ctx.notify("没有项目上下文"); return; }
      await api(`/projects/${id}/preview/film`, { method: "POST", body: JSON.stringify({}) });
      ctx.notify("整片预览已排队（draft 档，不占 final 队列）");
      dispatchAppEvent("notifications:refresh");
    },
  },
  {
    id: "queue.open", title: "打开运行监控（队列 / 在飞作业）", keywords: "queue monitor 队列 进度 作业 取消",
    group: "生产", shortcut: "⌘6", key: { mod: "cmd", key: "6" },
    run: (ctx) => ctx.router.push("/monitor"),
  },
  // —— 审阅
  {
    // 待办门来自通知中心（后端 gate_pending 已经把它们发出来了），不新造查询端点。
    id: "gate.decide", title: "处理最近的待办人工门", keywords: "gate 门 审批 待办 人工 签门",
    group: "审阅",
    run: async (ctx) => {
      const r = await api<{ items: { kind: string; link?: string }[] }>("/notifications");
      const g = r.items.find((x) => x.kind === "gate_pending" && x.link);
      if (!g?.link) { ctx.notify("没有等待人工处理的门"); return; }
      ctx.router.push(g.link);
    },
  },
  {
    id: "qa.open", title: "打开质量检查（当前项目）", keywords: "qa 质量 检查 修复",
    group: "审阅",
    run: (ctx) => {
      const id = currentProjectId();
      ctx.router.push(id ? `/qa?project=${id}` : "/qa");
    },
  },
];

// ---------------------------------------------------------------- 工具

/** 当前项目 id：全站页面统一用 `?project=`（首页/向导/模板跳出去时也是这个名字），
 *  URL 上没有就是"没有项目上下文"，不去猜最近打开的项目——那会让面板和页面各用一套口径。 */
export function currentProjectId(): number | null {
  if (typeof window === "undefined") return null;
  const q = new URLSearchParams(window.location.search).get("project");
  return q && /^\d+$/.test(q) ? Number(q) : null;
}

export function isMacPlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
}

export function formatShortcut(cmd: AppCommand, isMac: boolean): string {
  if (!cmd.key) return cmd.shortcut ?? "";
  const mod = cmd.key.mod === "none" ? "" : isMac ? "⌘" : "Ctrl+";
  const shift = cmd.key.shift ? (isMac ? "⇧" : "Shift+") : "";
  const key = cmd.key.key.length === 1 ? cmd.key.key.toUpperCase() : cmd.key.key;
  return `${mod}${shift}${key}`;
}

/** 快捷键冲突：同一个 (mod,shift,key) 被两条命令声明就是真冲突（不是"我觉得重复"）。 */
export function shortcutConflicts(): { label: string; ids: string[] }[] {
  const by = new Map<string, string[]>();
  for (const c of COMMANDS) {
    if (!c.key) continue;
    const k = `${c.key.mod}+${c.key.shift ? "shift" : ""}+${c.key.key}`;
    by.set(k, [...(by.get(k) ?? []), c.id]);
  }
  return [...by.entries()].filter(([, ids]) => ids.length > 1)
    .map(([label, ids]) => ({ label, ids }));
}

export function matchKey(e: KeyboardEvent, cmd: AppCommand, isMac: boolean): boolean {
  if (!cmd.key) return false;
  const meta = e.metaKey, ctrl = e.ctrlKey;
  const want = cmd.key.mod === "cmd" ? (isMac ? meta : ctrl)
    : cmd.key.mod === "ctrl" ? ctrl : !(meta || ctrl);
  if (!want) return false;
  if (!!cmd.key.shift !== e.shiftKey) return false;
  return e.key.toLowerCase() === cmd.key.key.toLowerCase();
}

export function searchCommands(query: string): AppCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return COMMANDS;
  return COMMANDS.filter((c) => `${c.title} ${c.keywords} ${c.group}`.toLowerCase().includes(q));
}
