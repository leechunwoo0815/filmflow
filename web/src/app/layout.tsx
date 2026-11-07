import type { Metadata } from "next";
import "./globals.css";
import { LangProvider } from "@/lib/i18n";
import { ApiFailureBanner } from "@/components/ApiFailureBanner";
import { WorkbenchChrome } from "@/components/WorkbenchChrome";
import Script from "next/script";

export const metadata: Metadata = { title: "FilmFlow · 印厂控制台", description: "代码动画全生命周期工作台" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        {/* 主题初始化（ADR-0004：默认白天；夜间存 localStorage） */}
        <Script id="theme-init" strategy="beforeInteractive">
          {`(function(){try{if(localStorage.getItem('ff.theme')==='dark')document.documentElement.classList.add('dark');}catch(e){}})();`}
        </Script>
        <LangProvider>{children}</LangProvider>
        <ApiFailureBanner />
        {/* FR-40：命令面板 / 通知中心 / 快捷键表挂在壳层，全站一套键位（lib/commands.ts 是唯一真源） */}
        <WorkbenchChrome />
      </body>
    </html>
  );
}
