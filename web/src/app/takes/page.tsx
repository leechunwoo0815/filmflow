"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

function tc(t: number, fps: number) {
  const f = Math.max(0, Math.round(t * fps));
  return `${String(Math.floor(f / fps / 60)).padStart(2, "0")}:${String(Math.floor(f / fps) % 60).padStart(2, "0")}:${String(f % fps).padStart(2, "0")}`;
}
function clamp(x: number, a: number, b: number) { return Math.max(a, Math.min(b, x)); }

function TakesInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const [takes, setTakes] = useState<any[]>([]);
  const [currentRun, setCurrentRun] = useState<number | null>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [aId, setAId] = useState<number | null>(null);
  const [bId, setBId] = useState<number | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [diff, setDiff] = useState(false);
  const [msg, setMsg] = useState("");
  const [meta, setMeta] = useState({ name: "", score: "", note: "" });
  const [sceneId, setSceneId] = useState("");
  const aRef = useRef<HTMLVideoElement | null>(null);
  const bRef = useRef<HTMLVideoElement | null>(null);
  const syncRef = useRef(false);

  const load = async () => {
    const [t, tl] = await Promise.all([
      api<any>(`/projects/${projectId}/takes`),
      api<any>(`/projects/${projectId}/docs/timeline`),
    ]);
    setTakes(t.items); setCurrentRun(t.currentRunId); setTimeline(tl.content);
    setAId((cur: number | null) => cur ?? t.items[0]?.runId ?? null);
    setBId((cur: number | null) => cur ?? t.items[1]?.runId ?? t.items[0]?.runId ?? null);
    setSceneId((cur: string) => cur || tl.content?.scenes?.[0]?.id || "");
  };
  useEffect(() => { if (projectId) load().catch((e) => setMsg(String(e))); }, [projectId]);

  const a = takes.find((x) => x.runId === aId) || takes[0] || null;
  const b = takes.find((x) => x.runId === bId) || takes[1] || takes[0] || null;
  const fps = Number(timeline?.fps || 24);
  const duration = Number(timeline?.duration || 0);
  const av = a?.videos?.[0] || null;
  const bv = b?.videos?.[0] || null;

  useEffect(() => {
    if (!a) return;
    setMeta({ name: a.name || "", score: a.score == null ? "" : String(a.score), note: a.note || "" });
  }, [aId, takes]);

  const playBoth = async () => {
    const avEl = aRef.current, bvEl = bRef.current;
    if (!avEl) return;
    try {
      if (playing) { avEl.pause(); bvEl?.pause(); setPlaying(false); }
      else { await avEl.play(); if (bvEl) { bvEl.currentTime = avEl.currentTime; await bvEl.play().catch(() => {}); } setPlaying(true); }
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const seek = (t: number) => {
    const aEl = aRef.current, bEl = bRef.current;
    if (aEl) aEl.currentTime = clamp(t, 0, aEl.duration || duration);
    if (bEl) bEl.currentTime = clamp(t, 0, bEl.duration || duration);
    setTime(t);
  };
  const syncFromA = () => {
    const aEl = aRef.current, bEl = bRef.current;
    if (!aEl) return;
    setTime(aEl.currentTime);
    if (!bEl || syncRef.current) return;
    if (Math.abs(bEl.currentTime - aEl.currentTime) > 1 / fps) {
      syncRef.current = true;
      bEl.currentTime = aEl.currentTime;
      setTimeout(() => { syncRef.current = false; }, 30);
    }
  };

  const saveMeta = async () => {
    if (!a) return;
    try {
      const r = await api<any>(`/projects/${projectId}/takes/${a.runId}`, {
        method: "PATCH",
        body: JSON.stringify({ name: meta.name, score: meta.score === "" ? null : Number(meta.score), note: meta.note }),
      });
      setMsg(`已保存 ${r.name} · ${r.score ?? "未评分"}`);
      await load();
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const promote = async (take: any) => {
    try {
      await api(`/projects/${projectId}/takes/${take.runId}/promote`, { method: "POST", body: "{}" });
      setMsg(`当前 Take → ${take.name} (#${take.runId})`); await load();
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const branch = async (take: any) => {
    try {
      const r = await api<any>(`/projects/${projectId}/takes/${take.runId}/branch`, { method: "POST", body: "{}" });
      setMsg(`已从 #${take.runId} 分支 → Run ${r.runId}（parent ${r.parentRunId}）`); await load();
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const remove = async (take: any) => {
    if (!confirm(`软删除 Take #${take.runId}？`)) return;
    try {
      await api(`/projects/${projectId}/takes/${take.runId}`, { method: "DELETE" });
      setMsg(`已软删除 #${take.runId}`); await load();
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const adopt = async () => {
    if (!b || !sceneId) return;
    try {
      const r = await api<any>(`/projects/${projectId}/takes/${b.runId}/adopt-scene`, {
        method: "POST", body: JSON.stringify({ sceneId }),
      });
      setTimeline(r.content);
      setMsg(`已采纳 #${b.runId} 的 ${sceneId}；timeline v${r.version}`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };

  if (!projectId) return <main className="p-8">缺 project 参数</main>;
  return (
    <main className="min-h-screen bg-bg text-txt p-4">
      <header className="flex items-center gap-2 mb-3">
        <a className="btn" href={`/canvas?project=${projectId}`}>← 画布</a>
        <b>Take 对比</b>
        <span className="text-dim text-xs">当前 #{currentRun ?? "—"} · {takes.length} 个 Take</span>
        <label className="ml-3 text-xs flex items-center gap-1"><input type="checkbox" checked={diff} onChange={(e) => setDiff(e.target.checked)} data-testid="take-diff" />差异叠加</label>
        <div className="ml-auto flex gap-1">
          <button className="btn" onClick={() => seek(time - 1 / fps)}>←帧</button>
          <button className="btn" onClick={playBoth}>{playing ? "暂停" : "同步播放"}</button>
          <button className="btn" onClick={() => seek(time + 1 / fps)}>帧→</button>
          <span className="font-mono text-xs self-center">{tc(time, fps)}</span>
        </div>
      </header>
      {msg && <div className="text-sm text-gold mb-2">{msg}</div>}
      <div className="grid grid-cols-[280px_1fr_300px] gap-3">
        <aside className="card p-2 max-h-[80vh] overflow-y-auto">
          <h2 className="font-semibold text-sm mb-2">Takes</h2>
          {takes.map((t) => (
            <div key={t.runId} data-testid={`take-${t.runId}`}
              className={`border rounded p-2 mb-2 text-xs ${aId === t.runId ? "border-gold" : "border-line"}`}>
              <div className="flex items-center gap-1">
                <b>#{t.runId}</b><span className="truncate">{t.name}</span>
                {t.current && <span className="badge border-green text-green ml-auto">当前</span>}
              </div>
              <div className="text-dim">{t.status} · {t.score == null ? "未评分" : `★${t.score}`} {t.parentRunId ? `· parent ${t.parentRunId}` : ""}</div>
              <div className="flex gap-1 mt-1">
                <button className="btn px-1" onClick={() => setAId(t.runId)}>A</button>
                <button className="btn px-1" onClick={() => setBId(t.runId)}>B</button>
                <button className="btn px-1" onClick={() => promote(t)} disabled={t.current}>提升</button>
                <button className="btn px-1" onClick={() => branch(t)}>分支</button>
                <button className="btn px-1" onClick={() => remove(t)} disabled={t.current}>删除</button>
              </div>
            </div>
          ))}
        </aside>
        <section>
          {diff ? (
            <div className="relative aspect-video bg-black rounded overflow-hidden" data-testid="take-diff-panel">
              {av ? <video ref={aRef} src={av.url} muted className="absolute inset-0 w-full h-full object-contain" onTimeUpdate={syncFromA} onEnded={() => setPlaying(false)} /> : <div className="p-4 text-dim">A 无视频</div>}
              {bv ? <video ref={bRef} src={bv.url} muted className="absolute inset-0 w-full h-full object-contain pointer-events-none" style={{ mixBlendMode: "difference" }} /> : null}
              <span className="absolute left-2 top-2 badge bg-black/60 text-white">A #{a?.runId} vs B #{b?.runId}</span>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs mb-1">A #{a?.runId} · {a?.name}</div>
                <div className="aspect-video bg-black rounded overflow-hidden">
                  {av ? <video ref={aRef} src={av.url} muted className="w-full h-full object-contain" onTimeUpdate={syncFromA} onEnded={() => setPlaying(false)} data-testid="take-video-a" /> : <div className="p-3 text-dim">无视频</div>}
                </div>
              </div>
              <div>
                <div className="text-xs mb-1">B #{b?.runId} · {b?.name}</div>
                <div className="aspect-video bg-black rounded overflow-hidden">
                  {bv ? <video ref={bRef} src={bv.url} muted className="w-full h-full object-contain" data-testid="take-video-b" /> : <div className="p-3 text-dim">无视频</div>}
                </div>
              </div>
            </div>
          )}
          <div className="mt-2 text-xs text-dim">同步：A 为主时钟；拖动/逐帧会 seek 两路；差异模式用 difference 叠加（不相同即亮）。</div>
          <div className="card p-2 mt-3">
            <h2 className="font-semibold text-sm mb-1">场景采纳</h2>
            <div className="flex gap-2 items-center text-sm">
              <span>把 B #{b?.runId} 的</span>
              <select value={sceneId} onChange={(e) => setSceneId(e.target.value)}>
                {(timeline?.scenes || []).map((s: any) => <option key={s.id} value={s.id}>{s.id} · {(s.text || "").slice(0, 18) || "（source_span）"}</option>)}
              </select>
              <span>采纳到当前项目</span>
              <button className="btn-primary" onClick={adopt} data-testid="take-adopt">采纳</button>
            </div>
            <p className="text-dim text-xs mt-1">只替换该场的文本/相机内容，保留目标时间轴；下一次 Run 只该场 hash 变化。</p>
          </div>
        </section>
        <aside className="card p-3 text-sm">
          <h2 className="font-semibold text-sm mb-2">A 元数据</h2>
          <label className="block text-xs text-dim">名称<input data-testid="take-name" className="w-full mt-1" value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} /></label>
          <label className="block text-xs text-dim mt-2">评分 0-5<input data-testid="take-score" className="w-full mt-1" type="number" min="0" max="5" value={meta.score} onChange={(e) => setMeta({ ...meta, score: e.target.value })} /></label>
          <label className="block text-xs text-dim mt-2">备注<textarea data-testid="take-note" className="w-full mt-1 h-20" value={meta.note} onChange={(e) => setMeta({ ...meta, note: e.target.value })} /></label>
          <button className="btn-primary mt-2 w-full" onClick={saveMeta} data-testid="take-save-meta">保存元数据</button>
          <h2 className="font-semibold text-sm mt-4 mb-1">血缘</h2>
          <p className="text-xs text-dim">A: #{a?.runId} {a?.parentRunId ? `← parent ${a.parentRunId}` : "（根）"}</p>
          <p className="text-xs text-dim">B: #{b?.runId} {b?.parentRunId ? `← parent ${b.parentRunId}` : "（根）"}</p>
          <p className="text-xs text-dim mt-3">软删除只隐藏列表；当前 Take 不能删除。分支会复制该 Run 的 script/timeline/profile 快照并新建 Run。</p>
        </aside>
      </div>
    </main>
  );
}

export default function TakesPage() {
  return <Suspense><TakesInner /></Suspense>;
}
