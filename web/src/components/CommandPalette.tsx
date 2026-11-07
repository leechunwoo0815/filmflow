"use client";
// FR-40：命令面板（⌘K / Ctrl+K）与快捷键表（`?`）。
//
// 键盘可达是硬要求，不是加分项：面板打开后焦点必须落在输入框（能直接打字）、
// ↑/↓ 选中、Enter 执行、Esc 关闭、Tab 不逃出对话框；关闭后焦点回到打开它的那个元素。
// 这些都写在下面几个 useEffect 里，每条都有它挡的实际失误（例如不 trap Tab 时
// 用户会 tab 到面板背后的页面上，按回车触发了完全无关的按钮）。
import { useRouter } from "next/navigation";
import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  COMMANDS, type AppCommand, formatShortcut, isMacPlatform, matchKey,
  onAppEvent, searchCommands, shortcutConflicts,
} from "@/lib/commands";

type Toast = { id: number; text: string };

export function CommandPalette({ onToast }: { onToast: (t: string) => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const openerRef = useRef<Element | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const isMac = useMemo(() => isMacPlatform(), []);
  const results = useMemo(() => searchCommands(query), [query]);

  const run = useCallback(async (cmd: AppCommand) => {
    setOpen(false);
    (openerRef.current as HTMLElement | null)?.focus?.();
    try {
      await cmd.run({ router, notify: onToast });
    } catch (e) {
      // api() 已经把失败广播给 ApiFailureBanner 了；这里只兜住"面板自己关掉后没人知道失败了"
      onToast(`命令失败：${(e as Error).message}`);
    }
  }, [router, onToast]);

  useEffect(() => onAppEvent("palette:open", () => {
    openerRef.current = document.activeElement;
    setQuery(""); setIndex(0); setOpen(true);
  }), []);

  const onPanelKey = useCallback((e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); (openerRef.current as HTMLElement | null)?.focus?.(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); const c = results[index]; if (c) void run(c); }
    else if (e.key === "Tab") {
      // 焦点圈在对话框内：只在输入框与列表之间来回，不去背后的页面
      e.preventDefault();
      const target = document.activeElement === inputRef.current ? listRef.current : inputRef.current;
      (target as HTMLElement | null)?.focus?.();
    }
  }, [results, index, run]);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  useEffect(() => {
    // 选中项随 ↓/↑ 滚动，否则第 20 条命令永远看不见（键盘可达性的实际含义）
    if (!open) return;
    listRef.current?.querySelector(`[data-cmd-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index, open]);

  if (!open) return null;
  return (
    <>
      <button type="button" aria-label="关闭命令面板" data-testid="command-palette-scrim"
        onClick={() => setOpen(false)}
        className="fixed inset-0 z-40 cursor-default bg-black/40" />
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-24">
      <div role="dialog" aria-modal="true" aria-label="命令面板"
        className="card w-[38rem] max-w-[92vw] overflow-hidden">
        <input ref={inputRef} value={query} data-testid="palette-input"
          onChange={(e) => { setQuery(e.target.value); setIndex(0); }}
          placeholder="搜索命令（页面、运行、通知、主题…）"
          role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list"
          aria-label="搜索命令" aria-activedescendant={results[index] ? `cmd-${results[index].id}` : undefined}
          onKeyDown={onPanelKey}
          className="w-full border-b bg-transparent px-4 py-3 outline-none" />
        <div ref={listRef} id="palette-list" role="listbox" aria-label="命令列表" tabIndex={0}
          onKeyDown={onPanelKey} className="max-h-80 overflow-auto outline-none">
          {!results.length && <p className="px-4 py-3 text-sm opacity-60">没有匹配的命令</p>}
          {results.map((c, i) => (
            <button key={c.id} id={`cmd-${c.id}`} role="option" aria-selected={i === index}
              data-cmd-index={i} data-testid={`palette-item-${c.id}`}
              onMouseEnter={() => setIndex(i)} onClick={() => void run(c)}
              className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left ${i === index ? "bg-[var(--panel)]" : ""}`}>
              <span className="min-w-0">
                <span className="block truncate">{c.title}</span>
                <span className="block text-xs opacity-50">{c.group}</span>
              </span>
              {c.key && <kbd className="chip shrink-0">{formatShortcut(c, isMac)}</kbd>}
            </button>
          ))}
        </div>
        <p className="px-4 py-2 text-xs opacity-60">
          ↑↓ 选择 · Enter 执行 · Esc 关闭 · 共 {COMMANDS.length} 条命令（面板与快捷键同源 <code>lib/commands.ts</code>）
        </p>
      </div>
      </div>
    </>
  );
}

/** 快捷键表：直接读注册表，绝不另写一份键位清单（写第二份就等着它和实际行为不一致）。 */
export function ShortcutsSheet() {
  const [open, setOpen] = useState(false);
  const isMac = useMemo(() => isMacPlatform(), []);
  const conflicts = useMemo(() => shortcutConflicts(), []);
  useEffect(() => onAppEvent("shortcuts:open", () => setOpen(true)), []);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;
  const bound = COMMANDS.filter((c) => c.key);
  return (
    <>
      <button type="button" aria-label="关闭快捷键表" data-testid="shortcuts-scrim"
        onClick={() => setOpen(false)} className="fixed inset-0 z-40 cursor-default bg-black/40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div role="dialog" aria-modal="true" aria-label="快捷键表"
        className="card w-[34rem] max-w-[92vw]">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <h2 className="font-semibold">快捷键</h2>
          <button className="btn px-2" onClick={() => setOpen(false)} aria-label="关闭快捷键表"
            data-testid="shortcuts-close">关闭（Esc）</button>
        </div>
        {conflicts.length > 0
          ? <p role="alert" className="border-b bg-[var(--panel)] px-4 py-2 text-sm">
              检出 {conflicts.length} 处快捷键冲突：
              {conflicts.map((c) => <span key={c.label} className="ml-1 font-mono">{c.label} ← {c.ids.join(" / ")}</span>)}
            </p>
          : <p className="border-b px-4 py-2 text-sm opacity-60" data-testid="shortcuts-no-conflicts">
              无快捷键冲突（{bound.length} 条已绑定命令两两不重键）</p>}
        <table className="w-full text-sm">
          <caption className="sr-only">命令与快捷键对照表</caption>
          <thead><tr className="text-left opacity-60"><th className="px-4 py-1">命令</th><th>键位</th><th>分组</th></tr></thead>
          <tbody>
            {bound.map((c) => (
              <tr key={c.id} data-testid={`shortcut-row-${c.id}`}>
                <td className="px-4 py-1">{c.title}</td>
                <td><kbd className="chip">{formatShortcut(c, isMac)}</kbd></td>
                <td className="opacity-60">{c.group}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="px-4 py-2 text-xs opacity-60">
          {isMac ? "⌘ 即 Command 键" : "Ctrl 键"} · 本页与命令面板读同一份 <code>lib/commands.ts</code>
        </p>
      </div>
      </div>
    </>
  );
}
