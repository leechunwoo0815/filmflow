"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Artifact = {
  id: number; node_id: string; type: string; sha256: string;
  meta_json?: Record<string, any>;
};
type Still = { scene: string; t: number; url: string; sha256: string; artifact: number };
type Gate = {
  gate: string; title: string; stale?: boolean; checklist?: string[]; review?: any;
  precheck?: string | null;          // 后端 _gate_precheck 算好的批准前置（页面不另写判据）
};

function ReviewInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const runId = Number(params.get("run"));
  const [pending, setPending] = useState<Gate[]>([]);
  const [arts, setArts] = useState<Artifact[]>([]);
  const [prevArts, setPrevArts] = useState<Artifact[]>([]);
  const [viewed, setViewed] = useState<string[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [idx, setIdx] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [compare, setCompare] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  // "已看全"必须是**查过之后**的结论。缺了这一位，页面在 pending/产物还没回来时
  // missing 是空数组 → 页头直接绿灯"全场景已看"、批准按钮可点，点下去后端回 400
  // （e2e 第一次纯键盘跑 D03 时实测到的就是这个假象）。
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    const p = await api<{ items: Gate[] }>(`/gates/${runId}/pending`);
    setPending(p.items);
    const d05 = p.items.find((g) => g.gate === "D05");
    const diff = d05?.review?.diff;
    if (diff?.previousRunId) {
      const prev = await api<{ items: Artifact[] }>(`/runs/${diff.previousRunId}/artifacts`);
      setPrevArts(prev.items);
    }
    const a = await api<{ items: Artifact[] }>(`/runs/${runId}/artifacts`);
    setArts(a.items);
    if (projectId) {
      const v = await api<{ scenes: string[]; missing: string[] }>(
        `/projects/${projectId}/stills/viewed`);
      setViewed(v.scenes || []);
      setMissing(v.missing || []);
    }
    setLoaded(true);
  }, [runId, projectId]);

  useEffect(() => { load().catch((e) => setMsg(String(e))); }, [load]);

  const reviewGate = pending.find((g) => g.gate === "D05");
  const review = reviewGate?.review;
  const stills: Still[] = useMemo(() => {
    if (review?.stills?.length) return [...review.stills].sort((a, b) =>
      a.scene === b.scene ? a.t - b.t : a.scene.localeCompare(b.scene));
    return arts.filter((a) => a.node_id === "D02" && a.type === "PNG" &&
      a.meta_json?.profile === "review").map((a) => ({
        scene: String(a.meta_json?.scene || ""), t: Number(a.meta_json?.t || 0),
        url: `/api/artifacts/${a.id}/file`, sha256: a.sha256, artifact: a.id,
      })).sort((a, b) => a.scene === b.scene ? a.t - b.t : a.scene.localeCompare(b.scene));
  }, [arts, review]);
  const contact = useMemo(() => {
    if (review?.contactSheet) return review.contactSheet;
    const a = arts.find((x) => x.node_id === "D02" && x.meta_json?.contact_sheet);
    return a ? { artifact: a.id, url: `/api/artifacts/${a.id}/file`, scenes: a.meta_json?.scenes } : null;
  }, [arts, review]);
  const prevByScene = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of prevArts) {
      if (a.node_id === "D02" && a.type === "PNG" && a.meta_json?.profile === "review") {
        m[String(a.meta_json?.scene)] = `/api/artifacts/${a.id}/file`;
      }
    }
    return m;
  }, [prevArts]);

  const current = stills[idx];
  useEffect(() => {
    if (!current || !projectId) return;
    api(`/projects/${projectId}/stills/viewed`, {
      method: "POST", body: JSON.stringify({ scene: current.scene, time: current.t }),
    }).then(async (r: any) => {
      setViewed(r.scenes || []); setMissing(r.missing || []);
      // 看完一场之后把"门"也重取一次：页头的已看/未看来自 /stills/viewed，
      // 批准按钮的状态来自 pending 里的 precheck。两处不同步时屏幕上会同时出现
      // "全场景已看"和"批准前置未满足：未查看场景 S01…"（实测到的自相矛盾）。
      const p = await api<{ items: Gate[] }>(`/gates/${runId}/pending`);
      setPending(p.items);
    })
      .catch(() => { /* 失败由 api() 的全局横幅播报 */ });
  }, [current, projectId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setIdx((i) => Math.min(stills.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "1") setZoom(100);
      if (e.key === "2") setZoom(200);
      if (e.key.toLowerCase() === "c") setCompare((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stills.length]);

  const decide = async (gate: string) => {
    setBusy(true); setMsg("");
    try {
      await api(`/gates/${gate}/decide`, {
        method: "POST",
        body: JSON.stringify({ run_id: runId, decision: "approved", author: "review-ui" }),
      });
      await load();
      setMsg(`${gate} 已批准`);
    } catch (e: any) { setMsg(String(e?.message || e)); }
    finally { setBusy(false); }
  };

  if (!runId) return <main className="p-8">缺少 run 参数：/review?project=1&run=1</main>;
  return (
    <main className="min-h-screen bg-bg text-txt p-6">
      <header className="flex items-center gap-3 mb-4">
        <Link className="btn" href={`/canvas?project=${projectId}&run=${runId}`}>← 画布</Link>
        <h1 className="text-xl font-semibold">静帧审阅 · Run {runId}</h1>
        <span className="text-dim text-sm">{stills.length} 张 / {new Set(stills.map(s => s.scene)).size} 场景</span>
        <span data-testid="review-view-state" className={
          !loaded ? "text-dim" : missing.length ? "text-red" : "text-green"}>
          {!loaded ? "审阅状态载入中…"
            : missing.length ? `未看：${missing.join(", ")}` : "全场景已看"}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {(() => {
            const d03 = pending.find((g) => g.gate === "D03");
            if (!d03) return null;
            return (
              <>
                {!!d03.precheck && (
                  <span className="text-xs text-red" data-testid="review-precheck">
                    批准前置未满足：{d03.precheck}
                  </span>
                )}
                <button className="btn" disabled={busy || !!d03.precheck}
                  onClick={() => decide("D03")}>批准 D03</button>
              </>
            );
          })()}
          {reviewGate && (
            <button className="btn" disabled={busy || !!reviewGate.precheck}
              onClick={() => decide("D05")}>
              批准 D05
            </button>
          )}
        </span>
      </header>
      {msg && <div className="mb-3 text-sm text-red">{msg}</div>}
      {contact && (
        <section className="mb-5">
          <h2 className="font-semibold mb-2">Contact sheet（全部场景）</h2>
          <img src={contact.url} alt="contact sheet" className="w-full max-w-5xl border border-line" />
        </section>
      )}
      <section className="grid grid-cols-2 xl:grid-cols-4 gap-3 mb-6">
        {stills.map((s, i) => (
          <button key={`${s.scene}-${s.t}-${s.artifact}`} onClick={() => setIdx(i)}
                  className={`text-left border ${i === idx ? "border-gold" : "border-line"} bg-panel p-2`}>
            <img src={s.url} alt={`${s.scene}@${s.t}`} className="w-full aspect-video object-cover" />
            <div className="flex justify-between text-xs mt-1">
              <span>{s.scene} @{s.t.toFixed(1)}s</span>
              <span className={viewed.includes(s.scene) ? "text-green" : "text-red"}>
                {viewed.includes(s.scene) ? "已看" : "未看"}
              </span>
            </div>
          </button>
        ))}
      </section>
      {current && (
        <section>
          <div className="flex items-center gap-2 mb-2 text-sm">
            <b>{current.scene} @{current.t.toFixed(1)}s</b>
            <span className="text-dim">←/→ 切换 · 1/2 缩放 · C A/B</span>
            <button className="btn" onClick={() => setZoom(100)}>100%</button>
            <button className="btn" onClick={() => setZoom(200)}>200%</button>
            <button className="btn" onClick={() => setCompare((v) => !v)}>A/B</button>
          </div>
          <div className="overflow-auto border border-line bg-black">
            <div className={compare ? "grid grid-cols-2 gap-1" : ""}>
              <img src={current.url} alt={current.scene} style={{ width: `${zoom}%`, maxWidth: "none" }} />
              {compare && prevByScene[current.scene] && (
                <img src={prevByScene[current.scene]} alt="previous" style={{ width: `${zoom}%`, maxWidth: "none" }} />
              )}
            </div>
          </div>
          {review?.diff && (
            <div className="mt-3 text-sm text-dim">
              与上一版（Run {review.diff.previousRunId ?? "—"}）差异：
              {(review.diff.scenes || []).filter((d: any) => d.status !== "unchanged")
                .map((d: any) => `${d.scene}:${d.status}`).join(" · ") || "无变化"}
            </div>
          )}
        </section>
      )}
    </main>
  );
}

export default function ReviewPage() {
  return <Suspense fallback={<main className="p-8">加载审阅…</main>}><ReviewInner /></Suspense>;
}
