"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type FileItem = { name: string; url: string; bytes: number };

function DeliveryInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const initialRun = Number(params.get("run")) || 0;
  const [runId, setRunId] = useState(initialRun);
  const [job, setJob] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const loadDetail = useCallback(async (rid = runId) => {
    if (!rid || !projectId) return;
    try {
      setDetail(await api<any>(`/projects/${projectId}/deliveries/${rid}`));
    } catch { setDetail(null); }
  }, [projectId, runId]);
  useEffect(() => { loadDetail(initialRun).catch(() => {}); }, [initialRun, loadDetail]);

  const create = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await api<any>(`/projects/${projectId}/delivery`, {
        method: "POST", body: JSON.stringify({ runId: runId || undefined, profile: "final" }),
      });
      setJob(r);
      const id = r.jobId;
      const t0 = Date.now();
      while (Date.now() - t0 < 15 * 60 * 1000) {
        const j = await api<any>(`/jobs/${id}`);
        setJob(j);
        if (j.status === "succeeded") {
          setRunId(j.run_id); await loadDetail(j.run_id); break;
        }
        if (["failed", "canceled"].includes(j.status)) {
          setMsg(j.error_msg || j.error_code || j.status); break;
        }
        await new Promise((res) => setTimeout(res, 2000));
      }
    } catch (e: any) { setMsg(String(e?.message || e)); }
    finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen bg-bg text-txt p-6">
      <header className="flex items-center gap-3 mb-4">
        <a className="btn" href={`/canvas?project=${projectId}&run=${runId || ""}`}>← 画布</a>
        <h1 className="text-xl font-semibold">交付 v1 · 项目 {projectId}</h1>
        <button className="btn-amber" disabled={busy} onClick={create}>
          {busy ? "生成中…" : "生成交付包"}
        </button>
        {job && <span className={job.status === "failed" ? "text-red" : "text-green"}>
          Job {job.id}: {job.status} {job.progress ? `${Math.round(job.progress * 100)}%` : ""}
        </span>}
      </header>
      {msg && <div className="text-red text-sm mb-3">{msg}</div>}
      {detail ? (
        <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <div className="border border-line bg-panel p-3">
            <h2 className="font-semibold mb-2">交付文件（9）</h2>
            <div className="space-y-1 text-sm">
              {(detail.files || []).map((f: FileItem) => (
                <div key={f.name} className="flex justify-between border-b border-line py-1">
                  <a className="text-blue underline" href={f.url} target="_blank">{f.name}</a>
                  <span className="text-dim">{f.bytes < 1024 * 1024 ? `${(f.bytes / 1024).toFixed(1)} KB` : `${(f.bytes / 1024 / 1024).toFixed(2)} MB`}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="border border-line bg-panel p-3">
            <h2 className="font-semibold mb-2">QC</h2>
            <div className={detail.qc?.ok ? "text-green" : "text-red"}>
              {detail.qc?.ok ? "QC 全绿" : "QC 未通过"}
            </div>
            <pre className="text-xs whitespace-pre-wrap mt-2 text-dim">
              {JSON.stringify(detail.qc?.checks || {}, null, 1)}
            </pre>
            <h3 className="font-semibold mt-3">Manifest</h3>
            <pre className="text-xs whitespace-pre-wrap mt-1 text-dim">
              {JSON.stringify(detail.manifest?.env || {}, null, 1)}
            </pre>
          </div>
        </section>
      ) : (
        <div className="text-dim">还没有交付包。点击「生成交付包」（需该 Run 已到 final）。</div>
      )}
    </main>
  );
}

export default function DeliveryPage() {
  return <Suspense fallback={<main className="p-8">加载交付…</main>}><DeliveryInner /></Suspense>;
}
