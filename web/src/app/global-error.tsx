"use client";

// P1-10：全局错误边界（layout 本身崩溃时仍可交互）。
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: 40 }}>
        <h2>FilmFlow 遇到致命错误</h2>
        <pre style={{ color: "#9a3412", whiteSpace: "pre-wrap" }}>
          {error.message || "未知错误"}
        </pre>
        <button onClick={reset}>重试</button>
      </body>
    </html>
  );
}
