"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";
import { ThemeToggle } from "@/lib/theme";

const STAGE_COLORS: Record<string, string> = {
  A: "#4C8DFF", B: "#39C5CF", C: "#3FB950", D: "#E3B341", E: "#F5A623", F: "#F47067", G: "#A371F7",
};
const STATUS_CLS: Record<string, string> = {
  idle: "text-dim", queued: "text-blue", running: "text-amber", succeeded: "text-green",
  cached: "text-cyan", failed: "text-red", blocked: "text-purple", stale: "text-gold",
  disabled: "text-dim", skipped: "text-dim",
};

function CanvasInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const runId = Number(params.get("run"));
  const [graph, setGraph] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [pendingGates, setPendingGates] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [guideOpen, setGuideOpen] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const guideParam = params.get("guide");
  useEffect(() => {
    if (!projectId) return;
    const seen = window.localStorage.getItem("ff_studio_guide_seen") === "1";
    setGuideOpen(guideParam === "1" || !seen);
  }, [projectId, guideParam]);

  const dismissGuide = () => {
    setGuideOpen(false);
    window.localStorage.setItem("ff_studio_guide_seen", "1");
  };

  const load = useCallback(async () => {
    if (!runId) return;
    setGraph(await api(`/runs/${runId}/graph`));
    setPendingGates((await api(`/gates/${runId}/pending`)).items);
  }, [runId]);

  useEffect(() => { load().catch((e) => setMsg(String(e))); }, [load]);

  // SSE 实时通道（规格 §9.1 唯一实时通道）
  useEffect(() => {
    if (!runId) return;
    const es = new EventSource(`/api/runs/${runId}/events`);
    esRef.current = es;
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (["node.started", "node.progress", "node.succeeded", "node.failed", "gate.stale", "run.finished", "gate.decided"].includes(d.event)) {
          load();
        }
      } catch {}
    };
    // SSE 断线不会走 api() 的失败通道，必须自己说一声，否则画布只是"停止刷新"
    es.onerror = () => setMsg("实时通道断开：节点状态可能不是最新，刷新页面可重连");
    return () => { es.close(); };
  }, [runId, load]);

  const act = async (path: string) => {
    try { await api(path, { method: "POST", body: "{}" }); await load(); } catch (e: any) { setMsg(e.message); }
  };

  const rfNodes = useMemo(() => (graph?.nodes || []).map((n: any) => ({
    id: n.id,
    position: { x: n.position.x, y: n.position.y },
    data: {
      label: (
        <div className="text-[11px] leading-tight" onClick={() => setSelected(n)}>
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: STAGE_COLORS[n.stage] }} />
            <span className="font-semibold">{n.id}</span>
            <span className="text-dim">{n.title}</span>
          </div>
          <div className={STATUS_CLS[n.status] || "text-dim"}>
            {n.status}{n.status === "running" ? ` ${(n.progress * 100).toFixed(0)}%` : ""}
            {n.message ? ` · ${n.message.slice(0, 40)}` : ""}
          </div>
          {n.gate === "human" && <span className="text-purple">🔒 {t("cv.humanGate")}</span>}
          {n.gate === "auto" && <span className="text-cyan">⚙ {t("cv.autoGate")}</span>}
        </div>
      ),
    },
    style: {
      // 全用非简写属性：React 的 style 逐键 diff 遇到 border（简写）与 borderStyle
      // 混用会在重渲染时报冲突警告（2026-11-07 老板首次 UI 实测的 Console Error）。
      background: "rgb(var(--panel))",
      borderWidth: 1,
      borderStyle: n.status === "blocked" ? "dashed" : "solid",
      borderColor: n.status === "running" ? "rgb(var(--amber))" : n.status === "failed" ? "rgb(var(--red))" : "rgb(var(--line))",
      borderRadius: 8, padding: 6, width: 190, color: "rgb(var(--txt))",
    },
  })), [graph]);

  const rfEdges = useMemo(() => (graph?.edges || []).map(([f, t, ty]: [string, string, string], i: number) => ({
    id: `e${i}`, source: f, target: t,
    animated: ty === "data",
    style: { stroke: ty === "trigger" ? "rgb(var(--purple))" : ty === "order" ? "rgb(var(--dim))" : "rgb(var(--line))", strokeDasharray: ty === "order" ? "4 3" : undefined },
    markerEnd: { type: MarkerType.ArrowClosed, color: ty === "trigger" ? "rgb(var(--purple))" : "rgb(var(--dim))" },
  })), [graph]);

  if (!projectId) return <main className="p-8">缺 project 参数</main>;

  return (
    <main className="h-screen flex flex-col">
      {!!pendingGates.length && (
        <a href="#gate-panel" data-testid="skip-to-gates"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 btn">
          跳到待办门（{pendingGates.length}）
        </a>
      )}
      <header className="flex flex-wrap items-center gap-2 p-3 border-b border-line">
        <a className="btn" href="/">{t("nav.back")}</a>
        <span className="font-semibold shrink-0">Run {runId}</span><span className="shrink-0"><LangToggle /></span><span className="shrink-0"><ThemeToggle /></span>
        {graph && <span className={`text-sm ${STATUS_CLS[graph.run.status]}`}>{graph.run.status}</span>}
        {graph && <span className="text-dim text-xs">caps: {graph.caps.join("/")}</span>}
        <div className="ml-auto flex gap-2">
          <a className="btn" href={`/editor?project=${projectId}`}>{t("nav.editor")}</a>
          <a className="btn" href={`/timeline?project=${projectId}&run=${runId}`}>时间轴</a>
          <a className="btn" href={`/assets?project=${projectId}`}>资产库</a>
          <a className="btn" href={`/templates?project=${projectId}`}>模板库</a>
          <a className="btn" href={`/qa?project=${projectId}&run=${runId}`}>QA 建议</a>
          <a className="btn" href={`/review?project=${projectId}&run=${runId}`}>静帧审阅</a>
          <a className="btn" href={`/player?project=${projectId}&run=${runId}`}>审片</a>
          <a className="btn" href={`/takes?project=${projectId}`}>Take 对比</a>
          <a className="btn" href={`/audio?project=${projectId}`}>音频</a>
          <a className="btn" href={`/delivery?project=${projectId}&run=${runId}`}>交付</a>
          <button className="btn" data-testid="studio-guide-btn" onClick={() => setGuideOpen((v) => !v)}>引导</button>
          <button className="btn" data-testid="step-btn" onClick={() => act(`/runs/${runId}/step`)}>{t("cv.step")}</button>
          <button className="btn-amber" data-testid="run-btn" onClick={() => act(`/runs/${runId}/start`)}>{t("cv.run")}</button>
          <button className="btn" onClick={() => act(`/runs/${runId}/cancel`)}>{t("cv.cancel")}</button>
          <button className="btn" onClick={() => act(`/runs/${runId}/resume`)}>{t("cv.resume")}</button>
          <button className="btn" onClick={() => act(`/runs/${runId}/retry`)}>{t("cv.retry")}</button>
        </div>
      </header>
      {msg && <div className="bg-panel border-b border-red/40 text-red text-sm px-3 py-1.5">{msg}</div>}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1" data-testid="node-canvas">
          <ReactFlow nodes={rfNodes} edges={rfEdges} fitView proOptions={{ hideAttribution: true }}
            edgesFocusable={false}
            onNodeClick={(_, n) => setSelected(graph.nodes.find((x: any) => x.id === n.id))}>
            <Background color="rgb(var(--line))" gap={18} />
            <Controls />
          </ReactFlow>
        </div>
        <aside id="gate-panel" tabIndex={-1} className="w-80 border-l border-line p-3 overflow-y-auto text-sm">
          {/* 待批准门 */}
          <h3 className="font-semibold mb-2">{t("cv.pendingGates")}{pendingGates.length}）</h3>
          {pendingGates.map((g) => (
            <div key={g.gate} className="card p-2 mb-2 border-purple/40" data-testid={`gate-${g.gate}`}>
              <div className="font-medium">🔒 {g.gate} {g.title}{g.stale && <span className="text-gold"> · stale</span>}</div>
              <ul className="text-dim text-xs mt-1 list-disc ml-4">
                {g.checklist.slice(0, 5).map((c: string, i: number) => <li key={i}>{c}</li>)}
              </ul>
              {g.comments && (
                <div className="text-xs text-gold mt-1">批注：未解决 {g.comments.open} / 共 {g.comments.total}</div>
              )}
              {/* 前置条件由后端算好随门带出（_gate_precheck 同一条判据）：
                  按钮 disabled + 一句"还差什么"，比让用户点下去收一条 400 诚实。 */}
              {g.precheck && (
                <p className="text-xs text-red mt-1" data-testid={`gate-precheck-${g.gate}`}>
                  批准前置未满足：{g.precheck}
                </p>
              )}
              <div className="flex gap-2 mt-2">
                <button className="btn-primary" data-testid={`gate-approve-${g.gate}`}
                  disabled={!!g.precheck}
                  aria-label={`批准 ${g.gate} 门`}
                  onClick={async () => { await api(`/gates/${g.gate}/decide`, { method: "POST", body: JSON.stringify({ run_id: runId, decision: "approved", author: "local", note: "", checklist: [] }) }); load(); }}>{t("cv.approve")}</button>
                <button className="btn" data-testid={`gate-reject-${g.gate}`}
                  aria-label={`驳回 ${g.gate} 门`} onClick={async () => {
                  // 注意：这里用 window.prompt 收驳回理由，headless 浏览器会自动 dismiss，
                  // 所以自动化验收走"批准"这条路径；改成页面内输入框是 a11y/自动化的待办项。
                  const note = prompt(t("cv.rejectPrompt"));
                  if (note === null) return;
                  await api(`/gates/${g.gate}/decide`, { method: "POST", body: JSON.stringify({ run_id: runId, decision: "rejected", author: "local", note }) });
                  load();
                }}>{t("cv.reject")}</button>
              </div>
            </div>
          ))}
          {/* 节点检查器 */}
          {selected ? (
            <>
              <h3 className="font-semibold mt-4 mb-1">{selected.id} {selected.title}</h3>
              <p className="text-xs text-dim">{selected.executor} · 锁 {selected.locks.join("/") || "—"}</p>
              <p className={`text-sm mt-1 ${STATUS_CLS[selected.status]}`}>{selected.status} {(selected.progress * 100).toFixed(0)}%</p>
              {selected.message && <p className="text-xs text-red mt-1 break-all">{selected.message}</p>}
              {selected.artifacts?.length > 0 && (
                <div className="mt-2">
                  <p className="text-dim text-xs mb-1">{t("cv.artifacts")}</p>
                  {selected.artifacts.map((a: any) => (
                    <div key={a.id} className="text-xs font-mono flex justify-between gap-1 border-b border-line py-1">
                      <span>{a.type}</span><a className="text-blue" href={`/api/artifacts/${a.id}/file`} target="_blank">{a.sha}</a>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : <p className="text-dim mt-6">{t("cv.clickNode")}</p>}
        </aside>
      </div>
      {guideOpen && (
        <div className="fixed bottom-4 right-4 z-50 w-80 card border-gold/40 p-3 text-sm shadow-xl"
          data-testid="studio-guide">
          <div className="flex items-center justify-between mb-2">
            <b>第一次进 Studio？5 步出片</b>
            <button className="btn" onClick={dismissGuide} data-testid="studio-guide-close">知道了</button>
          </div>
          <ol className="space-y-1.5">
            <li><a className="text-blue" href={`/editor?project=${projectId}`}>1. 场景列表</a><span className="text-dim"> · 看每句文案对应哪一场</span></li>
            <li><a className="text-blue" href={`/review?project=${projectId}&run=${runId}`}>2. 单帧预览</a><span className="text-dim"> · 逐场看静帧</span></li>
            <li><a className="text-blue" href={`/editor?project=${projectId}`}>3. 改一句</a><span className="text-dim"> · 自动保存并标脏</span></li>
            <li><a className="text-blue" href={`/review?project=${projectId}&run=${runId}`}>4. 看 diff</a><span className="text-dim"> · 只对比变化的场景</span></li>
            <li><a className="text-blue" href={`/delivery?project=${projectId}&run=${runId}`}>5. 出 draft</a><span className="text-dim"> · 预览或交付</span></li>
          </ol>
          <p className="text-dim text-xs mt-2">可跳过；随时用顶部「引导」重看。</p>
        </div>
      )}
    </main>
  );
}

export default function CanvasPage() {
  return <Suspense><CanvasInner /></Suspense>;
}
