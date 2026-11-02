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
  const esRef = useRef<EventSource | null>(null);

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
      background: "rgb(var(--panel))", border: `1px solid ${n.status === "running" ? "rgb(var(--amber))" : n.status === "failed" ? "rgb(var(--red))" : "rgb(var(--line))"}`,
      borderRadius: 8, padding: 6, width: 190, color: "rgb(var(--txt))",
      borderStyle: n.status === "blocked" ? "dashed" : "solid",
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
      <header className="flex items-center gap-2 p-3 border-b border-line">
        <a className="btn" href="/">{t("nav.back")}</a>
        <span className="font-semibold">Run {runId}</span><LangToggle /><ThemeToggle />
        {graph && <span className={`text-sm ${STATUS_CLS[graph.run.status]}`}>{graph.run.status}</span>}
        {graph && <span className="text-dim text-xs">caps: {graph.caps.join("/")}</span>}
        <div className="ml-auto flex gap-2">
          <a className="btn" href={`/editor?project=${projectId}`}>{t("nav.editor")}</a>
          <a className="btn" href={`/review?project=${projectId}&run=${runId}`}>静帧审阅</a>
          <a className="btn" href={`/audio?project=${projectId}`}>音频</a>
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
            onNodeClick={(_, n) => setSelected(graph.nodes.find((x: any) => x.id === n.id))}>
            <Background color="rgb(var(--line))" gap={18} />
            <Controls />
          </ReactFlow>
        </div>
        <aside className="w-80 border-l border-line p-3 overflow-y-auto text-sm">
          {/* 待批准门 */}
          <h3 className="font-semibold mb-2">{t("cv.pendingGates")}{pendingGates.length}）</h3>
          {pendingGates.map((g) => (
            <div key={g.gate} className="card p-2 mb-2 border-purple/40" data-testid={`gate-${g.gate}`}>
              <div className="font-medium">🔒 {g.gate} {g.title}{g.stale && <span className="text-gold"> · stale</span>}</div>
              <ul className="text-dim text-xs mt-1 list-disc ml-4">
                {g.checklist.slice(0, 5).map((c: string, i: number) => <li key={i}>{c}</li>)}
              </ul>
              <div className="flex gap-2 mt-2">
                <button className="btn-primary" onClick={async () => { await api(`/gates/${g.gate}/decide`, { method: "POST", body: JSON.stringify({ run_id: runId, decision: "approved", author: "local", note: "", checklist: [] }) }); load(); }}>{t("cv.approve")}</button>
                <button className="btn" onClick={async () => {
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
    </main>
  );
}

export default function CanvasPage() {
  return <Suspense><CanvasInner /></Suspense>;
}
