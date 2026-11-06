// a11y 静态检查（老板 2026-11-06 点头新增）：只挂 jsx-a11y，不引入 eslint-config-next，
// 目的是给 P2-15 一个可量化基线（棘轮见 scripts/lint_a11y.py），不是新增一整套 lint 宇宙。
import a11y from 'eslint-plugin-jsx-a11y';
import ts from 'typescript-eslint';

// 插件 6.10 只提供 legacy configs.recommended（无 flat/recommended），取它的规则表统一降为 warn
const asWarn = Object.fromEntries(
  Object.entries(a11y.configs.recommended.rules || {}).map(([k, v]) => [
    k, Array.isArray(v) ? ['warn', ...v.slice(1)] : 'warn',
  ]),
);

export default [
  // 源码里存在 `/* eslint-disable @next/next/... */` 这类内联指令，指向本配置未加载的插件；
// 这份配置只做 a11y 基线，忽略内联指令（否则 eslint 对未知规则名直接报 error）。
  { linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: 'off' } },
  { ignores: ['.next/**', 'out/**', 'node_modules/**', 'next-env.d.ts'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: ts.parser,
      parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } },
    },
    plugins: { 'jsx-a11y': a11y },
    rules: asWarn,
  },
];
