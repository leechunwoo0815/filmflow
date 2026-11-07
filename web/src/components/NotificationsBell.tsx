"use client";
// FR-40：通知中心（铃铛 + 面板）与进度中心（在飞作业 / ETA / 取消）。
//
// 三件事必须有真后端，不许做成装饰：
// 1. 未读数来自 `GET /notifications` 的 `unread`（服务端算的，不是前端数一遍）；
// 2. "修复入口"走通知自带的 `link`（后端已保证 `?project=&run=` 口径，见 services/notifications）；
// 3. 进度中心读 `GET /queue` 的 active 作业，取消走 `POST /jobs/{id}/cancel`——
//    与监控页同一对端点，面板不是第二条实现。
//
// 轮询节奏：打开时 5s（用户在盯着看），收起时 20s（只要角标别骗人）。
// 面板用 aria-live="polite" 播报新未读，键盘可达：Enter 打开 / Esc 关闭 / Tab 可用。
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, describeApiError } from "@/lib/api";
import { onAppEvent } from "@/lib/commands";

interface NotifyItem {
  id: string; kind: string; ref: string; title: string; detail?: string;
  link?: string | null; action?: { kind?: string; runId?: number; gate?: string };
  createdAt: string; readAt?: string | null;
}

interface ActiveJob {
  id: number; kind: string; status: string; priority: number; runId?: number | null;
  attempts: number; maxAttempts: number; progress: number; eta?: number | null;
  cancelRequested: boolean; errorCode?: string; errorMsg?: string;
}

const KIND_LABEL: Record<string, string> = {
  run_succeeded: "完成", run_failed: "失败", gate_pending: "待门",
};

export function NotificationsBell({ onToast }: { onToast: (t: string) => void }) {
  const router = useRouter();
  const [items, setItems] = useState<NotifyItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [jobs, setJobs] = useState<ActiveJob[]>([]);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"通知" | "进行中">("通知");
  const bellRef = useRef<HTMLButtonElement>(null);
  const prevUnread = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const n = await api<{ items: NotifyItem[]; unread: number }>("/notifications", { silent: true });
      setItems(n.items.slice().reverse());
      setUnread(n.unread);
      const q = await api<{ active: ActiveJob[] }>("/queue", { silent: true });
      setJobs(q.active);
    } catch (e) {
      // 通知中心自己读不到不该弹窗刷屏：角标停在旧值 + console 留痕
      console.warn("通知/队列读取失败", describeApiError(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const tick = window.setInterval(() => void refresh(), open ? 5000 : 20000);
    return () => window.clearInterval(tick);
  }, [refresh, open]);

  useEffect(() => onAppEvent("notifications:refresh", () => void refresh()), [refresh]);
  useEffect(() => onAppEvent("notifications:open", () => { setOpen(true); bellRef.current?.focus(); }), []);
  useEffect(() => {
    if (!open) return;
    // Esc 关面板挂在 window 上：面板本体是 role="dialog" 里的列表/表格，
    // 把键盘处理器绑到非交互元素上是 jsx-a11y 明确反对的写法（也确实不管用——焦点在子按钮上时事件被吃掉）
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    // 未读数上升时播报一次（PRD：异步失败必须可见；光靠角标数字对视障用户等于没有）
    if (prevUnread.current !== null && unread > prevUnread.current) onToast(`有 ${unread - prevUnread.current} 条新通知`);
    prevUnread.current = unread;
  }, [unread, onToast]);

  const markRead = async (it: NotifyItem) => {
    await api(`/notifications/${it.id}/read`, { method: "POST", body: "{}", silent: true });
    void refresh();
  };

  const openItem = async (it: NotifyItem) => {
    await markRead(it);
    if (it.link) router.push(it.link);
    else onToast(`通知「${it.title}」没有可跳转的目标`);
  };

  const cancelJob = async (j: ActiveJob) => {
    try {
      await api(`/jobs/${j.id}/cancel`, { method: "POST", body: "{}" });
      onToast(`作业 ${j.id} 已请求取消`);
      void refresh();
    } catch (e) { onToast(`取消失败：${describeApiError(e)}`); }
  };

  return (
    <>
      <button ref={bellRef} data-testid="notifications-bell"
        aria-label={unread ? `通知中心，${unread} 条未读` : "通知中心，无未读"}
        aria-expanded={open} aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
        className="btn relative px-2">
        🔔
        {unread > 0 && <span data-testid="notifications-unread"
          className="absolute -right-1 -top-1 rounded-full bg-[var(--gold)] px-1 text-[10px] text-black"
          aria-hidden>{unread > 99 ? "99+" : unread}</span>}
      </button>

      {open && (
        <div role="dialog" aria-modal="false" aria-label="通知中心" data-testid="notifications-panel"
          className="card fixed bottom-14 right-3 z-40 w-[26rem] max-w-[92vw] overflow-hidden">
          <div role="tablist" aria-label="通知中心分页" className="flex border-b">
            {(["通知", "进行中"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} data-testid={`notif-tab-${t}`}
                className={`flex-1 px-3 py-2 text-sm ${tab === t ? "bg-[var(--panel)] font-semibold" : "opacity-70"}`}
                onClick={() => setTab(t)}>
                {t}{t === "通知" && unread ? ` (${unread})` : ""}{t === "进行中" && jobs.length ? ` (${jobs.length})` : ""}
              </button>
            ))}
          </div>

          <button className="btn w-full border-b px-3 py-2 text-sm" data-testid="notifications-read-all"
            onClick={async () => {
              const r = await api<{ marked: number }>("/notifications/read-all", { method: "POST" });
              onToast(`已标记 ${r.marked} 条为已读`);
              void refresh();
            }}>全部标记已读</button>

          <div className="max-h-80 overflow-auto" role={tab === "通知" ? "list" : "table"}
            aria-label={tab === "通知" ? "通知列表" : "在飞作业列表"}>
            {tab === "通知" && (items.length === 0
              ? <p className="px-3 py-4 text-sm opacity-60" data-testid="notifications-empty">还没有通知</p>
              : items.map((it) => (
                <div key={it.id} data-testid={`notification-${it.kind}`} data-read={!!it.readAt}
                  className={`flex items-start gap-2 border-b px-3 py-2 ${it.readAt ? "opacity-60" : ""}`}>
                  <span className="chip shrink-0 mt-0.5">{KIND_LABEL[it.kind] ?? it.kind}</span>
                  <button className="min-w-0 flex-1 text-left" onClick={() => void openItem(it)}
                    data-testid={`notification-open-${it.id}`}>
                    <span className="block truncate">{it.title}</span>
                    {!!it.detail && <span className="block text-xs opacity-70">{it.detail}</span>}
                  </button>
                  {it.kind === "run_failed" && <button className="btn px-2 text-xs"
                    data-testid={`notification-fix-${it.id}`}
                    onClick={() => void openItem(it)}>修复</button>}
                  {!it.readAt && <button className="btn px-2 text-xs" aria-label="标记已读"
                    data-testid={`notification-read-${it.id}`} onClick={() => void markRead(it)}>已读</button>}
                </div>
              )))}

            {tab === "进行中" && (jobs.length === 0
              ? <p className="px-3 py-4 text-sm opacity-60" data-testid="progress-empty">没有在飞作业</p>
              : jobs.map((j) => (
                <div key={j.id} data-testid={`progress-job-${j.id}`} className="border-b px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono">#{j.id} {j.kind} · {j.status}</span>
                    <span className="opacity-70">{Math.round((j.progress || 0) * 100)}%
                      {j.eta ? ` · 约 ${Math.round(j.eta)}s` : ""}</span>
                  </div>
                  <div role="progressbar" aria-valuemin={0} aria-valuemax={100}
                    aria-valuenow={Math.round((j.progress || 0) * 100)}
                    aria-label={`作业 ${j.id} 进度`}
                    className="mt-1 h-1.5 w-full rounded bg-[var(--panel)]">
                    <div className="h-1.5 rounded bg-[var(--gold)]" style={{ width: `${Math.min(100, Math.round((j.progress || 0) * 100))}%` }} />
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="truncate text-xs opacity-70">
                      {j.errorCode ? `${j.errorCode} ${j.errorMsg ?? ""}` : `尝试 ${j.attempts}/${j.maxAttempts} · 优先级 ${j.priority}`}
                    </span>
                    <button className="btn px-2 text-xs" data-testid={`progress-cancel-${j.id}`}
                      disabled={j.cancelRequested} aria-label={`取消作业 ${j.id}`}
                      onClick={() => void cancelJob(j)}>
                      {j.cancelRequested ? "取消中…" : "取消"}
                    </button>
                  </div>
                </div>
              )))}
          </div>
          <p className="px-3 py-2 text-xs opacity-60">Esc 关闭 · 通知不推送、不邮件（离线可用）</p>
        </div>
      )}
    </>
  );
}

/** 全局轻提示（命令面板与通知共用一个出口；aria-live 让它对读屏也"可见"）。 */
export function ToastHost({ toasts }: { toasts: { id: number; text: string }[] }) {
  return (
    <div aria-live="polite" role="status" data-testid="toast-host"
      className="pointer-events-none fixed bottom-4 left-1/2 z-50 -translate-x-1/2 space-y-1">
      {toasts.map((t) => (
        <div key={t.id} data-testid={`toast-${t.id}`}
          className="card px-3 py-2 text-sm shadow-lg">{t.text}</div>
      ))}
    </div>
  );
}
