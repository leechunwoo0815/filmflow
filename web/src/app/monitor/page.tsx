"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { ThemeToggle } from "@/lib/theme";

function MonitorInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const runId = Number(params.get("run"));
  const [report, setReport] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);

  useEffect(() => {
    if (runId) api(`/runs/${runId}/report`).then(setReport);
    api("/audit").then((r) => setAudit(r.items));
  }, [runId]);

  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex items-center gap-2 mb-4"><h1 className="text-xl font-bold">{t("mo.title")}</h1><ThemeToggle /></div>
      {report && (
        <section className="card p-3 mb-4">
          <h2 className="font-semibold mb-2">Run {runId} · {report.run.status}</h2>
          <div className="grid grid-cols-4 gap-2 text-sm">
            {report.nodes.map((n: any) => (
              <div key={n.node_id} className="border border-line rounded p-1.5">
                <span className="font-mono">{n.node_id}</span>
                <span className={`ml-1 ${n.status === "succeeded" ? "text-green" : n.status === "failed" ? "text-red" : "text-dim"}`}>{n.status}</span>
              </div>
            ))}
          </div>
          <a className="btn mt-3 inline-block" href={`/api/runs/${runId}/report`} target="_blank">{t("mo.export")}</a>
        </section>
      )}
      <section className="card p-3">
        <h2 className="font-semibold mb-2">{t("mo.audit")}</h2>
        <table className="w-full text-xs">
          <thead className="text-dim"><tr>{["时间", "动作", "对象"].map((h) => <th key={h} className="text-left p-1">{h}</th>)}</tr></thead>
          <tbody>{audit.map((a) => (
            <tr key={a.id} className="border-t border-line">
              <td className="p-1 text-dim">{(a.at || "").slice(0, 19)}</td><td className="p-1">{a.action}</td><td className="p-1 font-mono">{a.target}</td>
            </tr>
          ))}</tbody>
        </table>
      </section>
    </main>
  );
}

export default function MonitorPage() {
  return <Suspense><MonitorInner /></Suspense>;
}
