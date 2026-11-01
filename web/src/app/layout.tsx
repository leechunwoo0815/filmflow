import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "FilmFlow · 印厂控制台", description: "代码动画全生命周期工作台" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
