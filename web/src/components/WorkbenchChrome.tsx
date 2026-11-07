"use client";
// FR-40：工作台外壳——把命令面板、通知中心、快捷键表与全局键位挂在一处。
//
// 挂在这里而不是每个页面各写一份的原因很实际：键位如果散在各页，就会出现
// "在时间轴 ⌘2 能用、在交付页没绑"这种只有用户能发现的缺陷。
// 全局键位的**唯一真源**是 lib/commands.ts，这个组件只负责"按注册表分发"。
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CommandPalette, ShortcutsSheet } from "@/components/CommandPalette";
import { NotificationsBell, ToastHost } from "@/components/NotificationsBell";
import { COMMANDS, type AppCommand, dispatchAppEvent, matchKey, onAppEvent } from "@/lib/commands";

export function WorkbenchChrome() {
  const router = useRouter();
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);
  const [chromeOpen, setChromeOpen] = useState(false);
  const seq = useRef(0);
  const isMac = useRef(false);

  const notify = useCallback((text: string) => {
    const id = ++seq.current;
    setToasts((t) => [...t, { id, text }]);
    // 提示 4s 后自己消失：常驻的轻提示会变成第二个错误横幅，把真正的失败挤下去
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  useEffect(() => onAppEvent("ui:toast", (m) => notify(String(m ?? ""))), [notify]);

  useEffect(() => {
    isMac.current = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA"
        || target.isContentEditable);
      for (const cmd of COMMANDS as AppCommand[]) {
        if (!cmd.key || !matchKey(e, cmd, isMac.current)) continue;
        // 正在打字时不抢键：⌘ 组合照常执行（浏览器里它们本就不属于文本输入），
        // 但无修饰符的 `?` 必须让位——否则"文案里打个问号"会弹出快捷键表。
        if (cmd.key.mod === "none" && typing) return;
        e.preventDefault();
        void Promise.resolve(cmd.run({ router, notify })).catch(() => { /* api() 已广播失败 */ });
        return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, notify]);

  return (
    <>
      <div className="fixed bottom-4 right-3 z-30 flex items-center gap-2" data-testid="workbench-chrome">
        {/* 老板实测：整排常驻盖住页面右下角的按钮。默认收起成一枚小圆钮，展开才是三件套。 */}
        {chromeOpen && (<>
          <button className="btn px-2" data-testid="palette-trigger"
            aria-label="打开命令面板（⌘K 或 Ctrl+K）"
            onClick={() => dispatchAppEvent("palette:open")}>⌘K 命令</button>
          <NotificationsBell onToast={notify} />
          <button className="btn px-2" data-testid="shortcuts-trigger" aria-label="查看快捷键表"
            onClick={() => dispatchAppEvent("shortcuts:open")}>?</button>
        </>)}
        <button className="btn px-2 rounded-full w-9 h-9 leading-none" data-testid="chrome-toggle"
          aria-label={chromeOpen ? "收起命令/通知/快捷键" : "展开命令/通知/快捷键"}
          title="命令 · 通知 · 快捷键"
          onClick={() => setChromeOpen((v) => !v)}>{chromeOpen ? "✕" : "☰"}</button>
      </div>
      <CommandPalette onToast={notify} />
      <ShortcutsSheet />
      <ToastHost toasts={toasts} />
    </>
  );
}
