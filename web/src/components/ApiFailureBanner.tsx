"use client";
import { useEffect, useState } from "react";
import { onApiFailure, type ApiFailure } from "@/lib/api";

/**
 * 全局失败条。
 *
 * `error.tsx` 只能抓渲染期抛错，抓不到 `await api(...)` 的拒绝；而工作台里绝大多数故障
 * （门禁拦截、许可缺口、文档冲突、作业失败）都是异步的。所以在 API 客户端这一层订阅，
 * 任何一个非 2xx 都必须在界面上可见，而不是静默变成"点了没反应"。
 */
export function ApiFailureBanner() {
  const [failures, setFailures] = useState<ApiFailure[]>([]);

  useEffect(() => onApiFailure((f) => {
    setFailures((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.path === f.path && last.message === f.message && last.status === f.status) {
        return prev;  // 自动保存这类同错重放不该把界面刷成队列
      }
      return [...prev.slice(-4), f];
    });
  }), []);

  if (!failures.length) return null;
  return (
    <div role="alert" data-testid="api-failure-banner"
         className="fixed bottom-4 right-4 z-50 max-w-sm space-y-2">
      {failures.map((f, i) => (
        <div key={`${f.path}-${f.status}-${i}`} data-testid="api-failure-item"
             className="card border border-red p-3 text-xs shadow-lg">
          <div className="font-semibold text-red">
            {f.code || `HTTP ${f.status}`}
          </div>
          <div className="mt-1 break-words">{f.message}</div>
          <div className="mt-1 text-dim font-mono">{f.path}</div>
          <button type="button" className="btn mt-2"
                  onClick={() => setFailures((prev) => prev.filter((_, j) => j !== i))}>
            知道了
          </button>
        </div>
      ))}
    </div>
  );
}
