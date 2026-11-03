"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

const TRANSITIONS = [
  ["cut", "硬切"], ["dissolve", "溶解"], ["wipe", "擦除"], ["push", "推"],
  ["paper-slide", "滑纸"], ["ink-bleed", "墨晕"], ["glitch", "故障"], ["match-shape", "匹配"],
] as const;
const PRESETS = [
  ["lock", "锁定"], ["push-in", "缓推"], ["pull-out", "缓拉"], ["pan-right", "右移"],
  ["follow", "跟随"], ["handheld", "手持"], ["impact", "撞击"],
] as const;
const ROW_H = { V: 78, T: 44, C: 40, A1: 30, A2: 30, A3: 30, M: 32 };

function fmtTC(t: number, fps: number) {
  const f = Math.max(0, Math.round(t * fps));
  const ff = f % fps;
  const s = Math.floor(f / fps);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}:${String(ff).padStart(2, "0")}`;
}
function clamp(x: number, a: number, b: number) { return Math.max(a, Math.min(b, x)); }
function sceneText(scene: any, script: any) {
  if (scene?.text) return scene.text;
  const ss = script?.sentences || [];
  const out = (scene?.source_span || []).map((i: number) => ss[i]?.text || "").join("");
  return out || scene?.meaning || "";
}
function requiredRead(text: string) { return (text || "").replace(/\s/g, "").length / 5.2; }

function TimelineInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const runId = params.get("run") || "";
  const [doc, setDoc] = useState<any>(null);
  const [script, setScript] = useState<any>({ sentences: [] });
  const [audio, setAudio] = useState<any>(null);
  const [assetLists, setAssetLists] = useState<{ project: any[]; global: any[] }>({ project: [], global: [] });
  const [fontCheck, setFontCheck] = useState<any>(null);
  const [sceneTemplates, setSceneTemplates] = useState<any[]>([]);
  const [sceneTplId, setSceneTplId] = useState("");
  const [version, setVersion] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [history, setHistory] = useState<any[]>([]);
  const [future, setFuture] = useState<any[]>([]);
  const [pps, setPps] = useState(90);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState<0 | 1 | -1>(0);
  const [snap, setSnap] = useState(true);
  const [loop, setLoop] = useState(false);
  const [inOut, setInOut] = useState<{ in: number | null; out: number | null }>({ in: null, out: null });
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<any>(null);
  const [textDraft, setTextDraft] = useState("");
  const [cameraDraft, setCameraDraft] = useState<any[]>([]);
  const [cameraAnchor, setCameraAnchor] = useState<[number, number]>([960, 540]);
  const [transitionDraft, setTransitionDraft] = useState("cut");
  const [transitionDur, setTransitionDur] = useState(0.5);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewMs, setPreviewMs] = useState(0);
  const [previewErr, setPreviewErr] = useState("");
  const [resize, setResize] = useState<{ id: string; end: number } | null>(null);
  const [dragId, setDragId] = useState("");
  const opRef = useRef<any>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);

  const scenes: any[] = doc?.scenes || [];
  const fps = Number(doc?.fps || 24);
  const duration = Number(doc?.duration || 0);
  const selected = scenes.find((s) => s.id === selectedId) || null;

  const load = useCallback(async () => {
    const [tl, sc] = await Promise.all([
      api<any>(`/projects/${projectId}/docs/timeline`),
      api<any>(`/projects/${projectId}/docs/script`),
    ]);
    setDoc(tl.content); setVersion(tl.version); setValidation(tl.validation || null);
    setScript(sc.content || { sentences: [] });
    api<any>(`/projects/${projectId}/audio`).then(setAudio).catch(() => setAudio(null));
    const first = (tl.content?.scenes || [])[0];
    if (first) {
      setSelectedId((cur: string) => cur || first.id);
      setPlayhead((cur) => cur || first.start + Math.min(1, (first.end - first.start) / 2));
    }
  }, [projectId]);
  useEffect(() => { if (projectId) load().catch((e) => setMsg(String(e))); }, [projectId, load]);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([
      api<any>(`/assets?scope=project&projectId=${projectId}`),
      api<any>("/assets?scope=global"),
    ]).then(([p, g]) => setAssetLists({ project: p.items || [], global: g.items || [] }))
      .catch((e) => setMsg(String(e.message || e)));
    api<any>("/templates?kind=scene").then((d) => setSceneTemplates(d.items || []))
      .catch((e) => setMsg(String(e.message || e)));
  }, [projectId]);

  const allAssets = useMemo(() => {
    const seen = new Set<number>();
    return [...assetLists.project, ...assetLists.global].filter((a: any) => !seen.has(a.id) && seen.add(a.id));
  }, [assetLists]);
  const imageAssets = allAssets.filter((a: any) => a.kind === "image");
  const soundAssets = allAssets.filter((a: any) => a.kind === "audio");
  const fontAssets = allAssets.filter((a: any) => a.kind === "font");

  useEffect(() => {
    const s = scenes.find((x) => x.id === selectedId);
    if (!s) return;
    setTextDraft(sceneText(s, script));
    setCameraDraft((s.camera_keyframes || []).map((k: any) => ({ ...k })));
    setCameraAnchor(s.camera_anchor || [960, 540]);
    setTransitionDraft(s.transition || "cut");
    setTransitionDur(Number(s.transition_duration || 0.5));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, version, script]);

  const applyResponse = (r: any) => {
    setDoc(r.content); setVersion(r.version);
    setValidation(r.validation || null);
  };

  const runOp = useCallback(async (op: string, extra: any = {}, opts: any = {}) => {
    if (!doc) return;
    setSaving(true); setMsg("");
    try {
      const r = await api<any>(`/projects/${projectId}/timeline/ops`, {
        method: "POST",
        body: JSON.stringify({ op, baseVersion: version, ...extra, ...(opts.force ? { force: true } : {}) }),
      });
      setHistory((h) => [...h.slice(-49), { content: doc, version }]);
      setFuture([]);
      applyResponse(r);
      if (opts.message) setMsg(opts.message);
    } catch (e: any) {
      const m = String(e.message || e);
      if (m.includes("E_SCENE_READ_OVERFLOW") && !opts.force &&
          window.confirm(`${m}\n\n读时不足。仍要应用吗？（可稍后再拉长）`)) {
        setSaving(false);
        return runOp(op, extra, { ...opts, force: true });
      }
      if (m.includes("DOC_CONFLICT") || m.includes("文档版本")) {
        await load();
        setMsg("文档已被其他窗口修改，已刷新");
      } else setMsg(m);
    } finally { setSaving(false); }
  }, [doc, version, projectId, load]);
  opRef.current = runOp;

  useEffect(() => {
    if (!selected || textDraft === sceneText(selected, script)) return;
    const timer = setTimeout(() => {
      opRef.current?.("set_text", { sceneId: selected.id, text: textDraft }, { quiet: true });
    }, 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textDraft, selectedId]);

  useEffect(() => {
    const sha = selected?.fontSha;
    if (!sha) { setFontCheck(null); return; }
    const asset = fontAssets.find((a: any) => a.sha256 === sha);
    if (!asset) { setFontCheck({ assetId: 0, ok: false, missingCount: 0, missing: [],
      name: "字体资产缺失", missingText: "字体资产缺失，请重新选择" }); return; }
    const timer = setTimeout(async () => {
      try {
        const r = await api<any>(`/assets/${asset.id}/font-check`, {
          method: "POST", body: JSON.stringify({ text: textDraft || sceneText(selected, script) }),
        });
        setFontCheck({ assetId: asset.id, name: asset.name, ...r });
      } catch { /* 编辑输入期间不打断 */ }
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, textDraft, selected?.fontSha, fontAssets.length]);

  const undo = async () => {
    if (!history.length) return;
    const prev = history[history.length - 1];
    setSaving(true);
    try {
      const r = await api<any>(`/projects/${projectId}/docs/timeline`, {
        method: "PUT", body: JSON.stringify({ content: prev.content, base_version: version, author: "timeline-undo" }),
      });
      setHistory((h) => h.slice(0, -1));
      setFuture((f) => [{ content: doc, version }, ...f].slice(0, 50));
      applyResponse(r); setMsg("已撤销");
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setSaving(false); }
  };
  const redo = async () => {
    if (!future.length) return;
    const next = future[0];
    setSaving(true);
    try {
      const r = await api<any>(`/projects/${projectId}/docs/timeline`, {
        method: "PUT", body: JSON.stringify({ content: next.content, base_version: version, author: "timeline-redo" }),
      });
      setFuture((f) => f.slice(1));
      setHistory((h) => [...h.slice(-49), { content: doc, version }]);
      applyResponse(r); setMsg("已重做");
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setSaving(false); }
  };

  useEffect(() => {
    if (!doc || !selectedId || playing) return;
    const s = scenes.find((x) => x.id === selectedId);
    if (!s) return;
    const t = clamp(playhead, s.start, Math.max(s.start, s.end - 1 / fps));
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setPreviewErr("");
      try {
        const res = await fetch(`/api/projects/${projectId}/preview/still`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sceneId: selectedId, time: t, profile: "draft", watermark: true }),
          signal: ctrl.signal,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.detail?.message || String(res.status));
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return url; });
        setPreviewMs(Number(res.headers.get("X-Preview-Ms") || 0));
      } catch (e: any) { if (e.name !== "AbortError") setPreviewErr(String(e.message || e)); }
    }, 250);
    return () => { clearTimeout(timer); ctrl.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc?.duration, version, selectedId, playhead, playing, fps]);

  useEffect(() => {
    if (!playing || !doc) return;
    let raf = 0; let last = performance.now();
    const step = (now: number) => {
      const dt = (now - last) / 1000; last = now;
      setPlayhead((p) => {
        let next = p + dt * playing;
        const a = loop ? (inOut.in ?? 0) : 0;
        const b = loop ? (inOut.out ?? duration) : duration;
        if (next >= b) { if (loop) next = a; else { setPlaying(0); next = b; } }
        if (next < a) { if (loop) next = b; else { setPlaying(0); next = 0; } }
        return clamp(next, 0, duration);
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, loop, inOut, duration, doc]);

  const snapTime = useCallback((t: number, alt = false) => {
    let out = Math.round(t * fps) / fps;
    if (!snap || alt) return out;
    const cands = [playhead, ...(doc?.events || []).map((e: any) => Number(e.at))];
    const close = cands.filter((c) => Number.isFinite(c) && Math.abs(c - out) * pps <= 7)
      .sort((a, b) => Math.abs(a - out) - Math.abs(b - out))[0];
    return close === undefined ? out : close;
  }, [snap, fps, playhead, doc?.events, pps]);

  const startResize = (e: React.PointerEvent, scene: any) => {
    e.stopPropagation(); e.preventDefault();
    const x0 = e.clientX; const end0 = Number(scene.end);
    const move = (ev: PointerEvent) => {
      const raw = end0 + (ev.clientX - x0) / pps;
      setResize({ id: scene.id, end: clamp(snapTime(raw, ev.altKey), scene.start + 0.5, duration + 10) });
    };
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      const raw = end0 + (ev.clientX - x0) / pps;
      const end = snapTime(raw, ev.altKey);
      setResize(null);
      if (Math.abs(end - end0) > 1 / fps) opRef.current?.("resize", { sceneId: scene.id, end });
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const selectScene = (id: string) => {
    const s = scenes.find((x) => x.id === id); if (!s) return;
    setSelectedId(id);
    if (playhead < s.start || playhead >= s.end) setPlayhead(s.start + Math.min(1, (s.end - s.start) / 2));
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.code === "Space") { e.preventDefault(); setPlaying((p) => p ? 0 : 1); }
      else if (e.key === "j") setPlaying(-1);
      else if (e.key === "k") setPlaying(0);
      else if (e.key === "l") setPlaying(1);
      else if (e.key === "ArrowLeft") { e.preventDefault(); setPlayhead((p) => clamp(p - (e.shiftKey ? 1 : 1 / fps), 0, duration)); }
      else if (e.key === "ArrowRight") { e.preventDefault(); setPlayhead((p) => clamp(p + (e.shiftKey ? 1 : 1 / fps), 0, duration)); }
      else if (e.key === "i" || e.key === "I") setInOut((v) => ({ ...v, in: playhead }));
      else if (e.key === "o" || e.key === "O") setInOut((v) => ({ ...v, out: playhead }));
      else if (e.key === "+" || e.key === "=") setPps((p) => clamp(p * 1.25, 20, 400));
      else if (e.key === "-") setPps((p) => clamp(p / 1.25, 20, 400));
      else if (e.key === "Escape") setSelectedId("");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fps, duration, playhead]);

  const fit = () => {
    const w = bodyRef.current?.clientWidth || 900;
    setPps(clamp((w - 40) / Math.max(1, duration), 20, 260));
  };

  const applyCamera = () => opRef.current?.("set_camera", {
    sceneId: selectedId, keyframes: cameraDraft, anchor: cameraAnchor,
  });
  const addAsset = (asset: any, sceneId = selectedId) => {
    if (!asset || !sceneId) return;
    if (asset.kind === "image") {
      opRef.current?.("add_image", { sceneId, assetSha: asset.sha256,
        box: [480, 270, 960, 540], z: 20, fit: "cover", opacity: 1, name: asset.name });
    } else if (asset.kind === "audio") {
      opRef.current?.("add_sfx", { sceneId, assetSha: asset.sha256, at: 0,
        gainDb: 0, fadeIn: 0.05, fadeOut: 0.1, name: asset.name });
    } else if (asset.kind === "font") {
      opRef.current?.("set_font", { sceneId, assetSha: asset.sha256 });
    }
  };
  const insertSceneTemplate = async (templateId: string) => {
    if (!templateId) return;
    try {
      const tl = await api<any>(`/projects/${projectId}/docs/timeline`);
      const r = await api<any>(`/projects/${projectId}/timeline/scene-template`, {
        method: "POST", body: JSON.stringify({
          templateId, afterSceneId: selectedId || undefined, baseVersion: tl.version,
        }),
      });
      applyResponse(r);
      setMsg(`已插入场景 ${r.sceneId || ""}`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const saveSceneTemplate = async () => {
    if (!selected) return;
    const name = prompt("场景模板名称", `${selected.id} 场景`);
    if (name === null) return;
    try {
      const r = await api<any>(`/projects/${projectId}/scenes/${selected.id}/save-template`, {
        method: "POST", body: JSON.stringify({ name, keepText: false }),
      });
      setMsg(`已保存场景模板：${r.template.title}`);
      setSceneTemplates((await api<any>("/templates?kind=scene")).items || []);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const checkFont = async (asset: any) => {
    if (!asset) return;
    try {
      const text = sceneText(selected, script) || textDraft;
      const r = await api<any>(`/assets/${asset.id}/font-check`, {
        method: "POST", body: JSON.stringify({ text }),
      });
      setFontCheck({ assetId: asset.id, name: asset.name, ...r });
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const addKeyframe = () => {
    if (!selected) return;
    const t = clamp(playhead - selected.start, 0, selected.end - selected.start);
    setCameraDraft((k) => [...k, { t: Math.round(t * 1000) / 1000, zoom: 1, x: 0, y: 0, rotate: 0 }]
      .sort((a, b) => a.t - b.t));
  };
  const updKf = (i: number, key: string, v: any) => setCameraDraft((k) => k.map((x, j) => j === i ? { ...x, [key]: v } : x));

  const ticks = useMemo(() => {
    const step = pps >= 180 ? 0.5 : pps >= 90 ? 1 : pps >= 45 ? 2 : 5;
    const out: number[] = [];
    for (let t = 0; t <= duration + 0.001; t += step) out.push(Math.round(t * 1000) / 1000);
    return out;
  }, [pps, duration]);

  if (!projectId) return <main className="p-8">缺 project 参数</main>;
  if (!doc) return <main className="p-8 text-dim">加载时间轴…</main>;
  const bodyW = Math.max(700, duration * pps + 60);
  const selectedText = selected ? sceneText(selected, script) : "";
  const required = requiredRead(textDraft || selectedText);
  const dur = selected ? selected.end - selected.start : 0;
  const readBad = required > dur + 0.05;
  const voice = (audio?.takes || []).filter((t: any) => t.kind === "voice");
  const music = (audio?.takes || []).filter((t: any) => t.kind === "music");

  return (
    <main className="h-screen flex flex-col bg-bg text-txt">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-line">
        <a className="btn" href={`/canvas?project=${projectId}${runId ? `&run=${runId}` : ""}`}>← 画布</a>
        <b>时间轴</b><span className="text-dim text-xs">项目 {projectId} · v{version}</span>
        <span className={`text-xs ${saving ? "text-gold" : "text-dim"}`}>{saving ? "保存中…" : "已保存"}</span>
        <button className="btn" onClick={undo} disabled={!history.length} data-testid="timeline-undo">撤销</button>
        <button className="btn" onClick={redo} disabled={!future.length}>重做</button>
        <button className="btn" onClick={fit}>Fit</button>
        <button className="btn" onClick={() => setPps((p) => clamp(p / 1.25, 20, 400))}>−</button>
        <button className="btn" onClick={() => setPps((p) => clamp(p * 1.25, 20, 400))}>＋</button>
        <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} />吸附</label>
        <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} />循环</label>
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono text-sm">{fmtTC(playhead, fps)} <span className="text-dim">/ {fmtTC(duration, fps)}</span></span>
          <button className="btn" onClick={() => setPlaying((p) => p ? 0 : 1)}>{playing ? "暂停" : "播放"}</button>
          <a className="btn" href={`/player?project=${projectId}${runId ? `&run=${runId}` : ""}`}>审片</a>
          <a className="btn" href={`/takes?project=${projectId}`}>Take 对比</a>
          <a className="btn" href={`/assets?project=${projectId}`}>资产库</a>
          <a className="btn" href="/help">帮助</a>
        </div>
      </header>
      {msg && <div className="px-3 py-1 text-xs text-gold border-b border-line">{msg}</div>}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          <div className="flex flex-1 min-h-0">
            <div className="w-24 shrink-0 border-r border-line text-xs">
              <div className="h-7 border-b border-line" />
              <div style={{ height: ROW_H.V }} className="border-b border-line p-1 font-semibold">V 场景</div>
              <div style={{ height: ROW_H.T }} className="border-b border-line p-1">T 文字</div>
              <div style={{ height: ROW_H.C }} className="border-b border-line p-1">C 相机</div>
              <div style={{ height: ROW_H.A1 }} className="border-b border-line p-1">A1 口播</div>
              <div style={{ height: ROW_H.A2 }} className="border-b border-line p-1">A2 音乐</div>
              <div style={{ height: ROW_H.A3 }} className="border-b border-line p-1">A3 SFX</div>
              <div style={{ height: ROW_H.M }} className="border-b border-line p-1">M 事件</div>
            </div>
            <div ref={bodyRef} className="flex-1 overflow-x-auto overflow-y-auto"
              onWheel={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); setPps((p) => clamp(p * (e.deltaY > 0 ? 0.9 : 1.1), 20, 400)); } }}>
              <div className="relative" style={{ width: bodyW }} data-testid="timeline-body">
                <div className="h-7 border-b border-line relative text-[10px] text-dim select-none">
                  {ticks.map((t) => (
                    <div key={t} className="absolute top-0 h-full border-l border-line/60" style={{ left: t * pps }}>
                      <span className="ml-1">{t}s</span>
                    </div>
                  ))}
                  {inOut.in !== null && <div className="absolute top-0 h-full bg-green/15 border-l border-green" style={{ left: inOut.in * pps, width: inOut.out ? (inOut.out - inOut.in) * pps : 0 }} />}
                </div>
                <div className="relative border-b border-line bg-panel/40" style={{ height: ROW_H.V }}
                  onClick={(e) => { const rect = (e.currentTarget as HTMLElement).getBoundingClientRect(); setPlayhead(clamp((e.clientX - rect.left) / pps, 0, duration)); }}>
                  {scenes.map((s: any, i: number) => {
                    const end = resize && resize.id === s.id ? resize.end : s.end;
                    const width = Math.max(8, (end - s.start) * pps);
                    const txt = sceneText(s, script);
                    const bad = requiredRead(txt) > (end - s.start) + 0.05;
                    return (
                      <div key={s.id} draggable data-testid={`scene-block-${s.id}`}
                        onDragStart={(e) => { setDragId(s.id); e.dataTransfer.setData("text/plain", s.id); }}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          const raw = e.dataTransfer.getData("application/x-ff-asset");
                          if (raw) {
                            try { addAsset(JSON.parse(raw), s.id); } catch {}
                            setDragId("");
                            return;
                          }
                          const id = e.dataTransfer.getData("text/plain") || dragId;
                          if (id && id !== s.id) opRef.current?.("move", { sceneId: id, toIndex: i });
                          setDragId("");
                        }}
                        onClick={(e) => { e.stopPropagation(); selectScene(s.id); }}
                        onDoubleClick={() => setTimeout(() => textRef.current?.focus(), 0)}
                        className={`absolute top-1.5 h-[62px] rounded border text-[11px] px-1.5 py-1 cursor-grab overflow-hidden ${selectedId === s.id ? "border-gold bg-gold/15" : "border-line bg-panel2 hover:border-dim"} ${bad ? "ring-1 ring-red" : ""}`}
                        style={{ left: s.start * pps, width }}>
                        <div className="flex justify-between"><b>{s.id}</b><span className="text-dim">{durations(s)}s</span></div>
                        <div className="truncate mt-0.5">{txt || "（空）"}</div>
                        <div className="text-[10px] text-dim mt-0.5">读 {Number(s.read_seconds || 0).toFixed(2)}s</div>
                        <div className="absolute right-0 top-0 h-full w-2 cursor-ew-resize bg-gold/0 hover:bg-gold/40"
                          onPointerDown={(e) => startResize(e, s)} data-testid={`scene-resize-${s.id}`} />
                      </div>
                    );
                  })}
                </div>
                <div className="relative border-b border-line" style={{ height: ROW_H.T }}>
                  {scenes.map((s: any) => (
                    <div key={s.id} className="absolute top-1 h-8 rounded bg-cyan/10 border border-cyan/30 text-[10px] px-1 truncate cursor-pointer"
                      style={{ left: s.start * pps, width: Math.max(8, (s.end - s.start) * pps) }}
                      onClick={() => selectScene(s.id)} onDoubleClick={() => setTimeout(() => textRef.current?.focus(), 0)}
                      title={sceneText(s, script)}>
                      {sceneText(s, script)}
                    </div>
                  ))}
                </div>
                <div className="relative border-b border-line" style={{ height: ROW_H.C }}>
                  {scenes.map((s: any) => {
                    const kfs = s.camera_keyframes || [];
                    return (
                      <div key={s.id}>
                        <div className="absolute top-5 h-px bg-purple/30" style={{ left: s.start * pps, width: Math.max(1, (s.end - s.start) * pps) }} />
                        {kfs.map((k: any, j: number) => (
                          <button key={j} title={`${k.t}s zoom ${k.zoom}`}
                            className="absolute top-2 w-2.5 h-2.5 rounded-full bg-purple border border-bg"
                            style={{ left: (s.start + Number(k.t || 0)) * pps - 5 }}
                            onClick={() => { selectScene(s.id); setPlayhead(s.start + Number(k.t || 0)); }} />
                        ))}
                      </div>
                    );
                  })}
                </div>
                {(["A1", "A2", "A3"] as const).map((track) => {
                  const items = track === "A1" ? voice : track === "A2" ? music : [];
                  return (
                    <div key={track} className="relative border-b border-line" style={{ height: ROW_H[track] }}>
                      {items.length === 0
                        ? <span className="absolute left-2 top-1 text-[10px] text-dim">未上传</span>
                        : items.map((t: any, j: number) => (
                          <div key={t.id} className="absolute top-0.5 h-6 rounded bg-green/15 border border-green/30 text-[10px] px-1 truncate"
                            style={{ left: 0, width: Math.max(20, Number(t.duration || 0) * pps), top: 1 + j * 26 }}
                            title={`${t.name} ${t.duration}s`}>
                            {t.name} · {t.duration}s{t.primary ? " · 主" : ""}
                          </div>
                        ))}
                    </div>
                  );
                })}
                <div className="relative border-b border-line" style={{ height: ROW_H.M }}>
                  {(doc.events || []).map((ev: any) => (
                    <div key={ev.id} title={`${ev.id} ${ev.role} @${ev.at}`}
                      className="absolute top-1 w-1.5 h-1.5 rotate-45 bg-amber"
                      style={{ left: Number(ev.at || 0) * pps }} />
                  ))}
                </div>
                <div className="absolute top-0 bottom-0 w-px bg-red z-20 pointer-events-none" style={{ left: playhead * pps }}>
                  <div className="w-2 h-2 bg-red -ml-[3px]" />
                </div>
                {loop && inOut.in !== null && inOut.out !== null && (
                  <div className="absolute top-0 bottom-0 bg-green/10 border-l border-r border-green/50 pointer-events-none"
                    style={{ left: inOut.in * pps, width: Math.max(1, (inOut.out - inOut.in) * pps) }} />
                )}
              </div>
            </div>
          </div>
          <div className="border-t border-line p-2 text-[11px] text-dim">
            空格播放 · J/K/L 倒/停/正 · ←→ 逐帧 · Shift+←→ 逐秒 · I/O 入出点 · +/- 缩放 · Ctrl+滚轮缩放 · 拖块排序 · 拖右边缘改时长
          </div>
        </div>
        <aside className="w-[360px] shrink-0 border-l border-line overflow-y-auto p-3 text-sm">
          {selected ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">{selected.id} <span className="text-dim text-xs">{selected.start.toFixed(2)}–{selected.end.toFixed(2)}s</span></h2>
                <span className={`text-xs ${readBad ? "text-red" : "text-green"}`}>读 {required.toFixed(2)}s / {dur.toFixed(2)}s</span>
              </div>
              <textarea ref={textRef} data-testid="timeline-text" className="w-full h-28 mt-2 font-mono text-sm"
                value={textDraft} onChange={(e) => setTextDraft(e.target.value)} />
              <div className="h-1.5 bg-panel2 rounded mt-1 overflow-hidden">
                <div className={`h-full ${readBad ? "bg-red" : "bg-green"}`} style={{ width: `${clamp((required / Math.max(0.1, dur)) * 100, 0, 100)}%` }} />
              </div>
              <div className="flex gap-1 mt-2 flex-wrap">
                <button className="btn" onClick={() => {
                  if (!selected) return;
                  opRef.current?.("split", { sceneId: selected.id, at: clamp(playhead, selected.start + 0.5, selected.end - 0.5) });
                }}>在播放头分割</button>
                <button className="btn" onClick={() => opRef.current?.("merge", { sceneId: selected.id, nextId: scenes[scenes.indexOf(selected) + 1]?.id })}>合并下一场</button>
                <button className="btn" onClick={() => opRef.current?.("duplicate", { sceneId: selected.id })}>复制</button>
              </div>
              <h3 className="font-semibold mt-4 mb-1 flex items-center gap-2">资产
                <a className="text-blue text-xs font-normal" href={`/assets?project=${projectId}`}>管理/导入</a>
              </h3>
              <div className="text-xs space-y-2">
                <div>
                  <div className="text-dim mb-1">图片（拖到场景块或点击插入）</div>
                  <div className="flex gap-1 flex-wrap">
                    {imageAssets.slice(0, 10).map((a: any) => (
                      <button key={a.id} draggable className="chip" data-testid={`asset-insert-${a.id}`}
                        onDragStart={(e) => e.dataTransfer.setData("application/x-ff-asset",
                          JSON.stringify({ sha: a.sha256, kind: a.kind, name: a.name }))}
                        onClick={() => addAsset(a)} title={`${a.name} ${a.sha256.slice(0, 8)}`}>
                        {a.thumbUrl ? <img src={a.thumbUrl} alt="" className="inline w-5 h-4 object-cover mr-1" /> : null}
                        {a.name}
                      </button>
                    ))}
                    {!imageAssets.length && <span className="text-dim">资产库还没有图片</span>}
                  </div>
                  {(selected.layers || []).map((l: any) => (
                    <div key={l.id} className="flex items-center gap-1 mt-1 border border-line rounded px-1 py-0.5">
                      <span className="truncate flex-1">{l.name || l.id}</span>
                      <select value={l.fit || "cover"} className="text-[10px]"
                        onChange={(e) => opRef.current?.("update_image", { sceneId: selected.id,
                          layerId: l.id, patch: { fit: e.target.value } })}>
                        <option value="cover">cover</option>
                        <option value="contain">contain</option>
                      </select>
                      <input type="range" min="0" max="1" step="0.05" value={l.opacity ?? 1}
                        className="w-14" title="不透明度"
                        onChange={(e) => opRef.current?.("update_image", { sceneId: selected.id,
                          layerId: l.id, patch: { opacity: +e.target.value } })} />
                      <button className="btn px-1" onClick={() => opRef.current?.("remove_layer",
                        { sceneId: selected.id, layerId: l.id })}>×</button>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-dim mb-1">场景字体</div>
                  <div className="flex gap-1">
                    <select value={selected.fontSha || ""} className="flex-1"
                      onChange={(e) => opRef.current?.("set_font", { sceneId: selected.id, assetSha: e.target.value })}>
                      <option value="">默认（Noto Sans SC）</option>
                      {fontAssets.map((a: any) => <option key={a.id} value={a.sha256}>{a.name}</option>)}
                    </select>
                    <button className="btn" disabled={!selected.fontSha}
                      onClick={() => {
                        const a = fontAssets.find((x: any) => x.sha256 === selected.fontSha);
                        checkFont(a);
                      }}>查缺字</button>
                  </div>
                  {fontCheck && selected.fontSha &&
                    <div className={`mt-1 ${fontCheck.ok ? "text-green" : "text-red"}`}>
                      {fontCheck.missingText ? fontCheck.missingText :
                        fontCheck.ok ? `${fontCheck.name} 覆盖全部 ${fontCheck.total} 字` :
                        `${fontCheck.name} 缺 ${fontCheck.missingCount} 字：` +
                        (fontCheck.missing || []).map((c: string) => `「${c}」`).join("")}
                    </div>}
                </div>
                <div>
                  <div className="text-dim mb-1">SFX（拖到场景块或点击插入）</div>
                  <div className="flex gap-1 flex-wrap">
                    {soundAssets.slice(0, 10).map((a: any) => (
                      <button key={a.id} draggable className="chip"
                        onDragStart={(e) => e.dataTransfer.setData("application/x-ff-asset",
                          JSON.stringify({ sha: a.sha256, kind: a.kind, name: a.name }))}
                        onClick={() => addAsset(a)} title={a.name}>
                        {a.name}
                      </button>
                    ))}
                    {!soundAssets.length && <span className="text-dim">资产库还没有音频</span>}
                  </div>
                  {(selected.audio_layers || []).map((l: any) => (
                    <div key={l.id} className="flex items-center gap-1 mt-1 border border-line rounded px-1 py-0.5">
                      <span className="truncate flex-1">{l.name || l.id} @{Number(l.at || 0).toFixed(2)}s</span>
                      <button className="btn px-1" onClick={() => opRef.current?.("remove_sfx",
                        { sceneId: selected.id, layerId: l.id })}>×</button>
                    </div>
                  ))}
                </div>
              </div>
              <h3 className="font-semibold mt-4 mb-1">场景模板</h3>
              <div className="text-xs space-y-1">
                <div className="flex gap-1">
                  <select className="flex-1" value={sceneTplId} data-testid="scene-template-select"
                    onChange={(e) => setSceneTplId(e.target.value)}>
                    <option value="">选择场景模板</option>
                    {sceneTemplates.map((t: any) => (
                      <option key={t.id} value={t.id}>{t.title}（{Number(t.seconds || 0).toFixed(1)}s）</option>
                    ))}
                  </select>
                  <button className="btn" disabled={!sceneTplId} data-testid="scene-template-insert"
                    onClick={() => insertSceneTemplate(sceneTplId)}>插入到后面</button>
                </div>
                <button className="btn" onClick={saveSceneTemplate} data-testid="scene-template-save">保存当前场景为模板</button>
              </div>
              <h3 className="font-semibold mt-4 mb-1">转场</h3>
              <div className="flex gap-1">
                <select value={transitionDraft} onChange={(e) => setTransitionDraft(e.target.value)} data-testid="timeline-transition">
                  {TRANSITIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                </select>
                <input className="w-16" type="number" step="0.1" value={transitionDur} onChange={(e) => setTransitionDur(+e.target.value)} />
                <button className="btn" onClick={() => opRef.current?.("set_transition", { sceneId: selected.id, transition: transitionDraft, duration: transitionDur })}>应用</button>
              </div>
              <h3 className="font-semibold mt-4 mb-1">相机</h3>
              <div className="flex gap-1 flex-wrap">
                {PRESETS.map(([v, label]) => (
                  <button key={v} className="chip" data-testid={`camera-preset-${v}`}
                    onClick={() => opRef.current?.("camera_preset", { sceneId: selected.id, preset: v })}>{label}</button>
                ))}
              </div>
              <svg viewBox="0 0 260 54" className="w-full h-14 mt-2 bg-panel2 rounded" data-testid="camera-curve">
                {cameraDraft.length > 1 && (
                  <polyline fill="none" stroke="#E3B341" strokeWidth="1.5"
                    points={cameraDraft.map((k) => `${(Number(k.t || 0) / Math.max(0.001, dur)) * 250 + 5},${40 - (Number(k.zoom || 1) - 0.9) * 200}`).join(" ")} />
                )}
                {cameraDraft.map((k, i) => <circle key={i} cx={(Number(k.t || 0) / Math.max(0.001, dur)) * 250 + 5}
                  cy={40 - (Number(k.zoom || 1) - 0.9) * 200} r="2.5" fill="#E3B341" />)}
              </svg>
              <div className="space-y-1 mt-1">
                {cameraDraft.map((k, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-1 text-[10px]">
                    {["t", "zoom", "x", "rotate"].map((key) => (
                      <input key={key} type="number" step={key === "t" ? 0.1 : 0.01} value={k[key] ?? 0}
                        onChange={(e) => updKf(i, key, +e.target.value)} title={key} />
                    ))}
                    <button className="btn px-1" onClick={() => setCameraDraft((x) => x.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>
              <div className="flex gap-1 mt-2">
                <button className="btn" onClick={addKeyframe} data-testid="camera-add">+ 关键帧</button>
                <button className="btn-primary" onClick={applyCamera}>应用相机</button>
              </div>
              <h3 className="font-semibold mt-4 mb-1">静帧预览 <span className="text-dim text-xs">{previewMs ? `${previewMs}ms` : ""}</span></h3>
              <div className="aspect-video bg-panel2 rounded overflow-hidden relative">
                {previewUrl ? <img src={previewUrl} alt="preview" className="w-full h-full object-cover" data-testid="timeline-preview" />
                  : <div className="p-3 text-dim text-xs">{previewErr || "等待预览…"}</div>}
                <span className="absolute left-1 top-1 text-[10px] bg-black/50 text-white px-1 rounded">PREVIEW</span>
              </div>
              {(validation?.errors?.length > 0 || validation?.warnings?.length > 0) && (
                <div className="mt-3 text-xs">
                  {validation.errors.map((e: any, i: number) => <p key={`e${i}`} className="text-red">✕ {e.message}</p>)}
                  {validation.warnings.map((w: any, i: number) => <p key={`w${i}`} className="text-gold">! {w.message}</p>)}
                </div>
              )}
            </>
          ) : <p className="text-dim">选择一个场景开始编辑</p>}
        </aside>
      </div>
    </main>
  );
}

function durations(s: any) { return (Number(s.end) - Number(s.start)).toFixed(1); }

export default function TimelinePage() {
  return <Suspense><TimelineInner /></Suspense>;
}
