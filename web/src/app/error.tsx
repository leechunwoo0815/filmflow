"use client";

// P1-10：路由级错误边界——任何页面抛错不再白屏静默，给重试出口。
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 本机工作台不上报；控制台留下完整栈便于复制反馈
    console.error("[FilmFlow] 页面渲染失败:", error);
  }, [error]);

  return (
    <div
      style={{
        minHeight: "60vh", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: 12, padding: 24,
      }}
      data-testid="page-error"
    >
      <h2 style={{ margin: 0 }}>页面出错了</h2>
      <p style={{ margin: 0, color: "#9a3412", fontSize: 14, maxWidth: 640, wordBreak: "break-all" }}>
        {error.message || "未知错误"}
        {error.digest ? `（digest: ${error.digest}）` : ""}
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={reset} className="btn" data-testid="page-error-retry">重试</button>
        <button onClick={() => { window.location.href = "/"; }} className="btn">回首页</button>
      </div>
    </div>
  );
}
