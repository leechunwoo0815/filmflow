"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

const CATS: Record<string, string> = { must: "必改", suggest: "建议", question: "疑问" };
const TOOLS = [["select", "选择"], ["rect", "矩形"], ["arrow", "箭头"], ["pen", "画笔"], ["text", "文字"]] as const;

function tc(t: number, fps: number) {
  const f = Math.max(0, Math.round(t * fps));
  return `${String(Math.floor(f / fps / 60)).padStart(2, "0")}:${String(Math.floor(f / fps) % 60).padStart(2, "0")}:${String(f % fps).padStart(2, "0")}`;
}
function clamp(x: number, a: number, b: number) { return Math.max(a, Math.min(b, x)); }

function PlayerInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const [review, setReview] = useState<any>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [videoId, setVideoId] = useState<number | null>(Number(params.get("video")) || null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(false);
  const [safe, setSafe] = useState(false);
  const [bright, setBright] = useState(1);
  const [tool, setTool] = useState<string>("select");
  const [shape, setShape] = useState<any>(null);
  const [drawing, setDrawing] = useState(false);
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("must");
  const [selected, setSelected] = useState<string>("");
  const [msg, setMsg] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    const [r, tl] = await Promise.all([
      api<any>(`/projects/${projectId}/review`),
      api<any>(`/projects/${projectId}/docs/timeline`),
    ]);
    setReview(r); setTimeline(tl.content);
    if (!videoId && r.videos?.length) setVideoId(r.videos[0].id);
  }, [projectId, videoId]);
  useEffect(() => { if (projectId) load().catch((e) => setMsg(String(e))); }, [projectId, load]);

  const video = (review?.videos || []).find((v: any) => v.id === videoId) || review?.videos?.[0] || null;
  const fps = Number(timeline?.fps || 24);
  const duration = Number(video ? (video.duration || timeline?.duration || 0) : 0) || Number(timeline?.duration || 0);
  const comments = review?.comments || [];
  const scenes = timeline?.scenes || [];
  const scene = useMemo(() => scenes.find((s: any) => time >= Number(s.start) && time < Number(s.end)) || scenes[scenes.length - 1], [scenes, time]);
  const frame = Math.round(time * fps);
  const selectedComment = comments.find((c: any) => c.id === selected);
  const openCount = comments.filter((c: any) => c.status === "open").length;

  useEffect(() => {
    const v = videoRef.current; if (!v) return;
    if (playing) v.play().catch(() => setPlaying(false)); else v.pause();
  }, [playing, video?.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const v = videoRef.current; if (!v) return;
      if (e.code === "Space") { e.preventDefault(); setPlaying((p) => !p); }
      else if (e.key === "j") { v.currentTime = clamp(v.currentTime - 1 / fps, 0, duration); setTime(v.currentTime); }
      else if (e.key === "k") { setPlaying(false); }
      else if (e.key === "l") { setPlaying(true); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); v.currentTime = clamp(v.currentTime - (e.shiftKey ? 1 : 1 / fps), 0, duration); setTime(v.currentTime); }
      else if (e.key === "ArrowRight") { e.preventDefault(); v.currentTime = clamp(v.currentTime + (e.shiftKey ? 1 : 1 / fps), 0, duration); setTime(v.currentTime); }
      else if (e.key === "f") { v.requestFullscreen?.(); }
      else if (e.key === "s") setSafe((s) => !s);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fps, duration]);

  const seek = (t: number) => {
    const v = videoRef.current; if (!v) return;
    v.currentTime = clamp(t, 0, duration); setTime(v.currentTime);
  };

  const pos = (e: React.PointerEvent) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return { x: 0, y: 0 };
    return { x: clamp((e.clientX - r.left) / r.width, 0, 1), y: clamp((e.clientY - r.top) / r.height, 0, 1) };
  };
  const down = (e: React.PointerEvent) => {
    if (tool === "select") return;
    if (tool === "text") {
      const text = window.prompt("文字批注");
      if (text) { setBody(text); setShape({ kind: "text", ...pos(e) }); }
      return;
    }
    setDrawing(true);
    const p = pos(e);
    if (tool === "rect") setShape({ kind: "rect", x: p.x, y: p.y, w: 0, h: 0 });
    else if (tool === "arrow") setShape({ kind: "arrow", x1: p.x, y1: p.y, x2: p.x, y2: p.y });
    else setShape({ kind: "pen", points: [[p.x, p.y]] });
  };
  const move = (e: React.PointerEvent) => {
    if (!drawing || !shape) return;
    const p = pos(e);
    setShape((s: any) => {
      if (!s) return s;
      if (s.kind === "rect") return { ...s, w: p.x - s.x, h: p.y - s.y };
      if (s.kind === "arrow") return { ...s, x2: p.x, y2: p.y };
      if (s.kind === "pen") return { ...s, points: [...s.points, [p.x, p.y]] };
      return s;
    });
  };
  const up = () => setDrawing(false);

  const saveComment = async () => {
    const v = videoRef.current; if (!v) return;
    if (!body.trim() && !shape) { setMsg("写一句话或画一个框"); return; }
    try {
      const c = await api<any>(`/projects/${projectId}/review/comments`, {
        method: "POST",
        body: JSON.stringify({
          frame: Math.round(v.currentTime * fps), time: v.currentTime,
          sceneId: scene?.id || "", kind: shape?.kind || "text",
          category, body, geometry: shape || {}, author: "local",
        }),
      });
      setBody(""); setShape(null); setTool("select"); setSelected(c.id);
      await load(); setMsg(`已添加批注 ${c.id}`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };

  const toggleResolve = async (c: any) => {
    await api(`/projects/${projectId}/review/comments/${c.id}`, {
      method: "PATCH", body: JSON.stringify({ status: c.status === "open" ? "resolved" : "open" }),
    });
    await load();
  };
  const reply = async (c: any) => {
    const text = window.prompt("回复");
    if (!text) return;
    await api(`/projects/${projectId}/review/comments/${c.id}`, {
      method: "PATCH", body: JSON.stringify({ reply: text, author: "local" }),
    });
    await load();
  };
  const assignSelf = async (c: any) => {
    await api(`/projects/${projectId}/review/comments/${c.id}`, {
      method: "PATCH", body: JSON.stringify({ assignee: "local" }),
    });
    await load();
  };
  const decide = async (decision: string, sid = "") => {
    await api(`/projects/${projectId}/review/decisions`, {
      method: "POST", body: JSON.stringify({ decision, sceneId: sid, author: "local" }),
    });
    await load(); setMsg(sid ? `${sid}：${decision}` : `整片：${decision}`);
  };
  const makePackage = async () => {
    try {
      const r = await api<any>(`/projects/${projectId}/review/package`, {
        method: "POST", body: JSON.stringify({ videoId: video?.id }),
      });
      setMsg(`审片包 ${(r.bytes / 1048576).toFixed(1)}MB · ${r.sha256.slice(0, 12)}`);
      window.open(r.download, "_blank");
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const importFile = async (file: File) => {
    try {
      const data = JSON.parse(await file.text());
      const r = await api<any>(`/projects/${projectId}/review/import`, {
        method: "POST", body: JSON.stringify(data),
      });
      await load(); setMsg(`导入：新增 ${r.added}，跳过 ${r.skipped}`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };

  const drawShape = (s: any, color: string, key: string) => {
    if (!s) return null;
    if (s.kind === "rect") {
      const x = Math.min(s.x, s.x + s.w), y = Math.min(s.y, s.y + s.h);
      return <rect key={key} x={x} y={y} width={Math.abs(s.w)} height={Math.abs(s.h)} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />;
    }
    if (s.kind === "arrow") return <line key={key} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={color} strokeWidth="2" markerEnd="url(#arrow)" vectorEffect="non-scaling-stroke" />;
    if (s.kind === "pen") return <polyline key={key} points={(s.points || []).map((p: any) => `${p[0]},${p[1]}`).join(" ")} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />;
    if (s.kind === "text") return <text key={key} x={s.x} y={s.y} fill={color} fontSize="0.025" style={{ paintOrder: "stroke", stroke: "#000", strokeWidth: 0.004 }}>文字批注</text>;
    return null;
  };

  if (!projectId) return <main className="p-8">缺 project 参数</main>;
  if (!review) return <main className="p-8 text-dim">加载审片…</main>;

  return (
    <main className="min-h-screen bg-bg text-txt p-4">
      <header className="flex items-center gap-2 mb-3">
        <a className="btn" href={`/timeline?project=${projectId}&run=${params.get("run") || ""}`}>← 时间轴</a>
        <b>审片 · 项目 {projectId}</b>
        <span className="text-dim text-xs">未解决 {openCount} / {comments.length}</span>
        {review.videos?.length ? (
          <select className="ml-3" value={videoId || ""} onChange={(e) => { setVideoId(Number(e.target.value)); setPlaying(false); }}>
            {review.videos.map((v: any) => <option key={v.id} value={v.id}>{v.label} · run {v.runId}</option>)}
          </select>
        ) : <span className="text-red text-xs">没有 MP4，先跑 F04/E05</span>}
        <div className="ml-auto flex gap-2 items-center">
          <a className="btn" href={`/api/projects/${projectId}/review/export?format=json`}>导出 JSON</a>
          <a className="btn" href={`/api/projects/${projectId}/review/export?format=csv`}>CSV</a>
          <button className="btn" onClick={() => fileRef.current?.click()}>导入 JSON</button>
          <input ref={fileRef} type="file" accept="application/json" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); }} />
          <button className="btn-amber" onClick={makePackage} data-testid="review-package">审片包</button>
        </div>
      </header>
      {msg && <div className="text-sm text-gold mb-2">{msg}</div>}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4">
        <section>
          <div className="relative bg-black rounded overflow-hidden" style={{ filter: `brightness(${bright})` }}>
            {video ? (
              <video ref={videoRef} src={video.url} className="w-full aspect-video bg-black" data-testid="review-video"
                onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                onLoadedMetadata={(e) => { if (loop) e.currentTarget.loop = true; }}
                onEnded={() => setPlaying(false)} />
            ) : <div className="aspect-video flex items-center justify-center text-dim">无视频</div>}
            <svg ref={svgRef} viewBox="0 0 1 1" preserveAspectRatio="none"
              className={`absolute inset-0 w-full h-full ${tool === "select" ? "pointer-events-none" : "cursor-crosshair pointer-events-auto"}`}
              onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} data-testid="review-overlay">
              <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="cyan" /></marker></defs>
              {safe && <rect x="0.05" y="0.08" width="0.9" height="0.84" fill="none" stroke="#39C5CF" strokeWidth="2" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />}
              {selectedComment?.geometry && drawShape(selectedComment.geometry, "#39C5CF", "sel")}
              {shape && drawShape(shape, "#E3B341", "draft")}
            </svg>
          </div>
          <div className="flex items-center gap-2 mt-2 text-sm">
            <button className="btn" onClick={() => setPlaying((p) => !p)}>{playing ? "暂停" : "播放"}</button>
            <span className="font-mono">{tc(time, fps)} <span className="text-dim">/ {tc(duration, fps)} · 帧 {frame}</span></span>
            <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={loop} onChange={(e) => { setLoop(e.target.checked); if (videoRef.current) videoRef.current.loop = e.target.checked; }} />循环</label>
            <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={safe} onChange={(e) => setSafe(e.target.checked)} />安全区</label>
            <label className="text-xs flex items-center gap-1">亮度 <input type="range" min="0.5" max="1.6" step="0.05" value={bright} onChange={(e) => setBright(+e.target.value)} /></label>
            <button className="btn ml-auto" onClick={() => videoRef.current?.requestFullscreen?.()}>全屏</button>
          </div>
          <div className="relative h-6 bg-panel2 rounded mt-2" data-testid="review-strip">
            {comments.map((c: any) => (
              <button key={c.id} title={`${c.id} 帧 ${c.frame}`} onClick={() => { seek(c.time); setSelected(c.id); }}
                className={`absolute top-1 w-2 h-4 rounded-sm ${c.status === "resolved" ? "bg-green/60" : "bg-red"}`}
                style={{ left: `${(Number(c.time) / Math.max(0.1, duration)) * 100}%` }} />
            ))}
            <div className="absolute top-0 bottom-0 w-px bg-txt" style={{ left: `${(time / Math.max(0.1, duration)) * 100}%` }} />
          </div>
          <div className="flex gap-1 mt-2 flex-wrap">
            {TOOLS.map(([v, label]) => <button key={v} className={`chip ${tool === v ? "chip-on" : ""}`} onClick={() => setTool(v)}>{label}</button>)}
            {shape && <button className="btn" onClick={() => setShape(null)}>清除图形</button>}
          </div>
          <div className="card p-2 mt-2">
            <div className="flex gap-2">
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {Object.entries(CATS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <input className="flex-1" placeholder="这一帧要改什么？" value={body} onChange={(e) => setBody(e.target.value)}
                data-testid="review-body" />
              <button className="btn-primary" onClick={saveComment} data-testid="review-save">锚定 {frame} 帧</button>
            </div>
            <p className="text-dim text-xs mt-1">场景 {scene?.id || "—"} · 当前工具 {tool} · 画框/箭头/画笔后填写文字再保存</p>
          </div>
        </section>
        <aside className="space-y-3">
          <section className="card p-2">
            <h2 className="font-semibold text-sm mb-1">批注 {comments.length}</h2>
            <div className="space-y-1 max-h-[45vh] overflow-y-auto">
              {[...comments].sort((a: any, b: any) => a.frame - b.frame).map((c: any) => (
                <div key={c.id} data-testid={`comment-${c.id}`}
                  className={`border rounded p-2 text-xs cursor-pointer ${selected === c.id ? "border-gold" : "border-line"} ${c.status === "resolved" ? "opacity-60" : ""}`}
                  onClick={() => { seek(c.time); setSelected(c.id); }}>
                  <div className="flex items-center gap-1">
                    <span className={`badge ${c.category === "must" ? "border-red text-red" : c.category === "question" ? "border-gold text-gold" : "border-line text-dim"}`}>{CATS[c.category] || c.category}</span>
                    <span className="font-mono">帧 {c.frame}</span><span className="text-dim">{tc(c.time, fps)}</span>
                    <span className="text-dim">{c.sceneId}</span>
                    <span className="ml-auto">{c.status === "resolved" ? "已解决" : "未解决"}</span>
                  </div>
                  <p className="mt-1">{c.body || "（图形批注）"}</p>
                  {c.assignee && <p className="text-dim">指派：{c.assignee}</p>}
                  {c.replies?.length > 0 && <p className="text-dim mt-1">回复 {c.replies.length} 条</p>}
                  <div className="flex gap-1 mt-1">
                    <button className="btn" onClick={(e) => { e.stopPropagation(); toggleResolve(c); }}>{c.status === "open" ? "解决" : "重开"}</button>
                    <button className="btn" onClick={(e) => { e.stopPropagation(); reply(c); }}>回复</button>
                    <button className="btn" onClick={(e) => { e.stopPropagation(); assignSelf(c); }}>指派我</button>
                  </div>
                </div>
              ))}
              {comments.length === 0 && <p className="text-dim text-xs">还没有批注。选工具，在画面上框选/写文字。</p>}
            </div>
          </section>
          <section className="card p-2 text-sm">
            <h2 className="font-semibold text-sm mb-1">审片决议</h2>
            <p className="text-dim text-xs mb-1">当前场景 {scene?.id || "—"} · 整片 {review.decisions?.overall?.decision || "未决"}</p>
            <div className="flex gap-1 flex-wrap">
              <button className="btn" onClick={() => decide("pass", scene?.id)}>本场通过</button>
              <button className="btn" onClick={() => decide("needs_changes", scene?.id)}>本场需改</button>
              <button className="btn-primary" onClick={() => decide("approved")}>整片通过</button>
              <button className="btn" onClick={() => decide("rejected")}>整片驳回</button>
            </div>
          </section>
          <section className="card p-2 text-xs text-dim">
            <p>空格播放 · J/K/L · ←→ 逐帧 · Shift+←→ 逐秒 · F 全屏 · S 安全区</p>
            <p className="mt-1">批注锚定 frame + sceneId + layerId；导出 JSON/CSV；审片包 = review.mp4 + review.json + README。</p>
          </section>
        </aside>
      </div>
    </main>
  );
}

export default function PlayerPage() {
  return <Suspense><PlayerInner /></Suspense>;
}
