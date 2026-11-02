import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ADR-0004：全部走 CSS 变量（:root=白天，html.dark=夜间）
        bg: "rgb(var(--bg) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        panel2: "rgb(var(--panel2) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        txt: "rgb(var(--txt) / <alpha-value>)",
        dim: "rgb(var(--dim) / <alpha-value>)",
        amber: "rgb(var(--amber) / <alpha-value>)",
        blue: "rgb(var(--blue) / <alpha-value>)",
        green: "rgb(var(--green) / <alpha-value>)",
        red: "rgb(var(--red) / <alpha-value>)",
        purple: "rgb(var(--purple) / <alpha-value>)",
        cyan: "rgb(var(--cyan) / <alpha-value>)",
        gold: "rgb(var(--gold) / <alpha-value>)",
      },
    },
  },
  plugins: [],
};
export default config;
