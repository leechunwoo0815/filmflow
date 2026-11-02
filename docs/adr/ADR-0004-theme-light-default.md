# ADR-0004 · 主题：默认白天，夜间可切

- 状态：已接受（老板 2026-11-02 指示："换白天的主题吧，黑色主题看不清楚"）
- 背景：ADR-0001 定的是深色工作台；实际使用中白底纸感更易读，且与印刷工房气质一致。
- 决定：主题实现改为 CSS 变量（`web/src/app/globals.css` 的 `:root`=白天 / `html.dark`=夜间），**默认白天**；页面头部提供 🌙/☀️ 切换（localStorage `ff.theme` 持久化）；浅色下强调色加深以保对比度（blue #2563EB / amber #B45309 / green #15803D …）。
- 后果：所有 Tailwind 语义色（bg/panel/panel2/line/txt/dim/amber/blue/green/red/purple/cyan/gold）自动跟随主题；引擎预演图（riso 纸感 / code-video 终端 / ink 宣纸）是"作品内容"，不随 UI 主题变化。
