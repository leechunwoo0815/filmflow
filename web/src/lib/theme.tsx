"use client";
/** 主题切换（ADR-0004）：默认白天；html.dark = 夜间。持久化 localStorage("ff.theme")。
 *
 *  FR-40 起 `toggleTheme()` 是导出函数：命令面板（⌘K → 切换明暗主题）与按钮必须走**同一条**
 *  代码路径。两处各写一份 classList/localStorage 的话，早晚只有一边生效（这是最典型的
 *  "UI 有两条真源"腐化）。
 */
import { useEffect, useState } from "react";

export function toggleTheme(): boolean {
  const nextLight = document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", !nextLight);
  try { window.localStorage.setItem("ff.theme", nextLight ? "light" : "dark"); } catch { /* 隐私模式写不了，不拦 UI */ }
  return nextLight;
}

export function ThemeToggle() {
  const [light, setLight] = useState(true);
  useEffect(() => {
    setLight(!document.documentElement.classList.contains("dark"));
    // 命令面板改的是同一段 class，这里跟着同步（MutationObserver 是最省事的单源读法）
    const obs = new MutationObserver(() => setLight(!document.documentElement.classList.contains("dark")));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return (
    <button onClick={() => toggleTheme()} className="btn px-2" data-testid="theme-toggle"
      aria-label={light ? "切换夜间主题" : "切换白天主题"} title={light ? "切换夜间" : "切换白天"}>
      {light ? "🌙" : "☀️"}
    </button>
  );
}
