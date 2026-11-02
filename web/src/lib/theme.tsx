"use client";
/** 主题切换（ADR-0004）：默认白天；html.dark = 夜间。持久化 localStorage("ff.theme")。 */
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [light, setLight] = useState(true);
  useEffect(() => {
    setLight(!document.documentElement.classList.contains("dark"));
  }, []);
  const toggle = () => {
    const nextLight = !light;
    setLight(nextLight);
    document.documentElement.classList.toggle("dark", !nextLight);
    try { window.localStorage.setItem("ff.theme", nextLight ? "light" : "dark"); } catch {}
  };
  return (
    <button onClick={toggle} className="btn px-2" title={light ? "切换夜间" : "切换白天"}>
      {light ? "🌙" : "☀️"}
    </button>
  );
}
