"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Take = {
  id: string; name: string; kind: string; file: string; duration: number; primary: boolean;
  sceneId?: string; processedFile?: string; processing?: Record<string, boolean>;
  processedDuration?: number;
};
type Segment = { text: string; start: number; end: number };
type Mix = { preset: string; targetLufs: number; stems: { voice: number; music: number; sfx: number } };
type AudioData = {
  takes: Take[]; primary: Take | null; scenePrimary: Record<string, string>;
  alignment: { segments: Segment[]; source?: string };
  license: any; licenseOk: boolean; licenseReason: string;
  mix: Mix; markers: { markers: { id: string; time: number; label?: string }[]; onsets: { time: number; strength?: number }[] };
  placeholder: { kind: string; duration: number; source: string; note?: string } | null;
};

function readBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
const PROC_KEYS = [
  ["highpass", "高通 80Hz"], ["denoise", "降噪 afftdn"], ["deesser", "齿音 deesser"],
  ["eq", "3 段 EQ"], ["trim", "静音裁剪"], ["normalize", "响度归一"],
] as const;

function AudioInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const [data, setData] = useState<AudioData | null>(null);
  const [scenes, setScenes] = useState<any[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selected, setSelected] = useState("");
  const [peaks, setPeaks] = useState<number[][]>([]);
  const [msg, setMsg] = useState("");
  const [recording, setRecording] = useState(false);
  const [uploadScene, setUploadScene] = useState("");
  const [sceneSel, setSceneSel] = useState("");
  const [ab, setAb] = useState<{ a: string; b: string }>({ a: "", b: "" });
  const [proc, setProc] = useState<Record<string, boolean>>({});
  const [mix, setMix] = useState<Mix>({ preset: "-16", targetLufs: -16, stems: { voice: 0, music: -8, sfx: -120 } });
  const [markers, setMarkers] = useState<any[]>([]);
  const [onsets, setOnsets] = useState<any[]>([]);
  const [markerTime, setMarkerTime] = useState(0);
  const [concatUrl, setConcatUrl] = useState("");
  // P1-18：授权默认**不勾选**——默认打勾等于让用户在没确认的情况下声明"已授权"
  const [lic, setLic] = useState({ source: "", license: "", authorized: false, expires: "", note: "" });
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const canvas = useRef<HTMLCanvasElement | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    const [d, tl] = await Promise.all([
      api<AudioData>(`/projects/${projectId}/audio`),
      api<any>(`/projects/${projectId}/docs/timeline`),
    ]);
    setData(d);
    const sc = tl.content?.scenes || [];
    setScenes(sc);
    setUploadScene((v) => v || sc[0]?.id || "");
    setSceneSel((v) => v || sc[0]?.id || "");
    setMix(d.mix || { preset: "-16", targetLufs: -16, stems: { voice: 0, music: -8, sfx: -120 } });
    setMarkers(d.markers?.markers || []);
    setOnsets(d.markers?.onsets || []);
    setLic({ source: d.license?.source || "", license: d.license?.license || "",
             authorized: d.license?.authorized === true, expires: d.license?.expires || "",
             note: d.license?.note || "" });
    const takeId = d.primary?.id || d.takes[0]?.id || "";
    setSelected((v) => v || takeId);
    setAb((v) => ({ a: v.a || takeId, b: v.b || d.takes.find((t) => t.id !== takeId)?.id || takeId }));
    if (d.alignment?.segments?.length) setSegments(d.alignment.segments);
    else setSegments(sc.map((s: any) => ({ text: s.text || s.meaning || "", start: Number(s.start || 0), end: Number(s.end || 0) })));
  }, [projectId]);
  useEffect(() => { load().catch((e) => setMsg(String(e))); }, [load]);

  useEffect(() => {
    if (!selected || !projectId) return;
    api<any>(`/projects/${projectId}/audio/waveform?takeId=${selected}&w=1200`)
      .then((d) => setPeaks(d.peaks || [])).catch(() => setPeaks([]));
    const take = data?.takes.find((t) => t.id === selected);
    setProc(take?.processing || {});
  }, [selected, projectId, data]);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.fillStyle = "#0f172a"; ctx.fillRect(0, 0, c.width, c.height);
    const dur = Math.max(0.001, Number(data?.takes.find((t) => t.id === selected)?.duration || 1));
    if (peaks.length) {
      const mid = c.height / 2;
      ctx.strokeStyle = "#39C5CF"; ctx.beginPath();
      peaks.forEach((p, i) => {
        const x = (i / Math.max(1, peaks.length - 1)) * c.width;
        ctx.moveTo(x, mid - (p[1] || 0) * mid);
        ctx.lineTo(x, mid - (p[0] || 0) * mid);
      });
      ctx.stroke();
      ctx.fillStyle = "rgba(227,179,65,.8)";
      onsets.forEach((o) => ctx.fillRect((Number(o.time) / dur) * c.width, 0, 1, c.height));
      ctx.fillStyle = "#F47067";
      markers.forEach((m) => ctx.fillRect((Number(m.time) / dur) * c.width, 0, 2, c.height));
    }
  }, [peaks, onsets, markers, selected, data]);

  const upload = async (file: File) => {
    setMsg("");
    const b64 = await readBase64(file);
    const r = await api<any>(`/projects/${projectId}/audio/upload`, {
      method: "POST",
      body: JSON.stringify({ filename: file.name, data: b64, kind: "voice", name: file.name, sceneId: uploadScene }),
    });
    if (uploadScene) {
      await api(`/projects/${projectId}/audio/scene-primary`, {
        method: "POST", body: JSON.stringify({ sceneId: uploadScene, takeId: r.take.id }),
      });
    }
    setMsg(`已导入 ${r.take.name}（${r.take.duration}s）${uploadScene ? ` → ${uploadScene}` : ""}`);
    await load();
  };

  const toggleRecord = async () => {
    if (recording) { recorder.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(chunks.current, { type: mr.mimeType || "audio/webm" });
        const b64 = await readBase64(blob);
        const r = await api<any>(`/projects/${projectId}/audio/upload`, {
          method: "POST",
          body: JSON.stringify({ filename: "record.webm", data: b64, kind: "voice", name: "录音", sceneId: uploadScene }),
        });
        if (uploadScene) {
          await api(`/projects/${projectId}/audio/scene-primary`, {
            method: "POST", body: JSON.stringify({ sceneId: uploadScene, takeId: r.take.id }),
          });
        }
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false); setMsg("录音已保存");
        await load();
      };
      recorder.current = mr; mr.start(); setRecording(true);
    } catch (e: any) { setMsg(String(e?.message || e)); }
  };

  const setPrimary = async (id: string) => {
    await api(`/projects/${projectId}/audio/primary`, { method: "POST", body: JSON.stringify({ takeId: id }) });
    await load();
  };
  const setSceneTake = async (takeId: string | null) => {
    if (!sceneSel) { setMsg("先在时间轴有场景"); return; }
    await api(`/projects/${projectId}/audio/scene-primary`, {
      method: "POST", body: JSON.stringify({ sceneId: sceneSel, takeId: takeId || "" }),
    });
    setMsg(takeId ? `${sceneSel} → Take ${takeId}` : `${sceneSel} 已清除场景 Take`);
    await load();
  };
  const processTake = async (clear = false) => {
    if (!selected) return;
    const r = await api<any>(`/projects/${projectId}/audio/takes/${selected}/process`, {
      method: "POST", body: JSON.stringify(clear ? {} : proc),
    });
    setMsg(clear ? "已撤销处理" : `已处理：${Object.entries(proc).filter(([, v]) => v).map(([k]) => k).join("/") || "无效果"}`);
    setProc(r.take.processing || {});
    await load();
  };
  const concat = async () => {
    try {
      const r = await api<any>(`/projects/${projectId}/audio/concat`, { method: "POST", body: "{}" });
      setConcatUrl(`${r.url}?t=${Date.now()}`);
      setMsg(`拼接预览 ${r.duration}s · ${r.picks} 段`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const detect = async () => {
    if (!selected) return;
    const r = await api<any>(`/projects/${projectId}/audio/onset?takeId=${selected}`);
    setOnsets(r.onsets || []);
    await api(`/projects/${projectId}/audio/markers`, {
      method: "POST", body: JSON.stringify({ markers, onsets: r.onsets || [] }),
    });
    setMsg(`检测到 ${r.onsets?.length || 0} 个 onset`);
  };
  const saveMarkers = async (next = markers, nextOnsets = onsets) => {
    const r = await api<any>(`/projects/${projectId}/audio/markers`, {
      method: "POST", body: JSON.stringify({ markers: next, onsets: nextOnsets }),
    });
    setMarkers(r.markers || []); setOnsets(r.onsets || []);
  };
  const addMarker = async () => {
    await saveMarkers([...markers, { time: Number(markerTime || 0), label: "拍点" }], onsets);
  };
  const saveMix = async () => {
    try {
      const r = await api<Mix>(`/projects/${projectId}/audio/mix`, { method: "POST", body: JSON.stringify(mix) });
      setMix(r); setMsg(`响度目标 ${r.targetLufs} LUFS · stems ${r.stems.voice}/${r.stems.music}/${r.stems.sfx}dB`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };
  const saveAlignment = async () => {
    const r = await api<any>(`/projects/${projectId}/audio/alignment`, {
      method: "POST", body: JSON.stringify({ segments, author: "audio-ui" }),
    });
    setMsg(`对齐已保存（${r.segments.length} 段，manual）`);
  };
  const saveLicense = async () => {
    try {
      await api(`/projects/${projectId}/audio/license`, { method: "POST", body: JSON.stringify(lic) });
      setMsg("音乐许可已保存"); await load();
    } catch (e: any) { setMsg(String(e?.message || e)); }
  };

  const total = useMemo(() => segments.reduce((a, s) => Math.max(a, s.end), 0), [segments]);
  const takeById = (id: string) => data?.takes.find((t) => t.id === id);
  const takeUrl = (t?: Take) => t ? `/api/projects/${projectId}/audio/takes/${t.id}/file?processed=${t.processedFile ? 1 : 0}` : "";
  if (!projectId) return <main className="p-8">缺少 project 参数</main>;
  return (
    <main className="min-h-screen bg-bg text-txt p-6">
      <header className="flex items-center gap-3 mb-4 flex-wrap">
        <Link className="btn" href={`/editor?project=${projectId}`}>← 编辑器</Link>
        <Link className="btn" href={`/timeline?project=${projectId}`}>时间轴</Link>
        <h1 className="text-xl font-semibold">音频工作台 v2 · 项目 {projectId}</h1>
        <span className={data?.licenseOk ? "text-green" : "text-red"}>
          音乐许可：{data?.licenseOk ? "OK" : data?.licenseReason || "未填写"}
        </span>
      </header>
      {msg && <div className="text-sm text-gold mb-3">{msg}</div>}
      {data?.placeholder && !data.takes.some((t) => t.kind === data.placeholder?.kind) && (
        <div className="border border-gold/40 bg-gold/10 text-sm px-3 py-2 mb-3" data-testid="audio-placeholder">
          音频占位：模板预留 {data.placeholder.duration}s {data.placeholder.kind} 轨（来源 {data.placeholder.source}）。
          录制或导入后占位自动移除；占位不会生成假音频。
        </div>
      )}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="border border-line bg-panel p-3">
          <h2 className="font-semibold mb-2">口播 Take</h2>
          <div className="flex gap-2 mb-2 flex-wrap text-sm">
            <select value={uploadScene} onChange={(e) => setUploadScene(e.target.value)} data-testid="upload-scene">
              <option value="">不指定场景</option>
              {scenes.map((s: any) => <option key={s.id} value={s.id}>{s.id}</option>)}
            </select>
            <label className="btn cursor-pointer">
              导入音频
              <input type="file" accept="audio/*" className="hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
            </label>
            <button className="btn" onClick={toggleRecord}>{recording ? "停止录音" : "浏览器录音"}</button>
          </div>
          <div className="space-y-2 max-h-80 overflow-auto">
            {(data?.takes || []).map((t) => (
              <div key={t.id} data-testid={`take-${t.id}`}
                className={`border p-2 text-sm ${selected === t.id ? "border-gold" : "border-line"}`}>
                <button className="text-left w-full" onClick={() => setSelected(t.id)}>
                  <div className="font-medium">{t.name} {t.primary && <span className="text-green">主</span>} {t.processedFile && <span className="text-cyan">已处理</span>}</div>
                  <div className="text-dim">{t.duration}s · {t.kind} {t.sceneId || ""} {t.processedFile ? `· P ${t.processedDuration}s` : ""}</div>
                </button>
                <div className="flex gap-1 mt-1 flex-wrap">
                  <button className="btn" onClick={() => { setAb((v) => ({ ...v, a: t.id })); setSelected(t.id); }}>A</button>
                  <button className="btn" onClick={() => { setAb((v) => ({ ...v, b: t.id })); setSelected(t.id); }}>B</button>
                  <button className="btn" onClick={() => setPrimary(t.id)}>设为主</button>
                  <button className="btn" onClick={() => setSceneTake(t.id)}>设为场景</button>
                  <a className="btn" href={takeUrl(t)} target="_blank">试听</a>
                </div>
              </div>
            ))}
            {!data?.takes?.length && <div className="text-dim text-sm">还没有音频，导入或录音。</div>}
          </div>
        </div>
        <div className="xl:col-span-2 border border-line bg-panel p-3">
          <h2 className="font-semibold mb-2">波形、拍点与手动对齐</h2>
          <canvas ref={canvas} width={1200} height={180} className="w-full bg-black border border-line" />
          <div className="text-xs text-dim mt-1">总时长 {total.toFixed(2)}s · 黄色 onset · 红色 marker</div>
          <div className="flex gap-2 items-center text-xs mt-2 flex-wrap">
            <button className="btn" onClick={detect} data-testid="audio-onsets">检测拍点</button>
            <input className="w-20" type="number" step="0.01" value={markerTime} onChange={(e) => setMarkerTime(+e.target.value)} />
            <button className="btn" onClick={addMarker}>加 marker</button>
            <button className="btn" onClick={() => saveMarkers(markers.filter((m) => m.label !== "拍点"))}>清 marker</button>
            <span className="text-dim">onsets {onsets.length} · markers {markers.length}</span>
          </div>
          <table className="w-full text-sm mt-3">
            <thead><tr className="text-dim"><th className="text-left">文本</th><th>开始</th><th>结束</th></tr></thead>
            <tbody>
              {segments.map((s, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1">{s.text || `片段 ${i + 1}`}</td>
                  <td><input className="w-24 bg-bg border border-line px-1" type="number" step="0.01" value={s.start}
                    onChange={(e) => setSegments((all) => all.map((x, j) => j === i ? { ...x, start: Number(e.target.value) } : x))} /></td>
                  <td><input className="w-24 bg-bg border border-line px-1" type="number" step="0.01" value={s.end}
                    onChange={(e) => setSegments((all) => all.map((x, j) => j === i ? { ...x, end: Number(e.target.value) } : x))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn mt-3" onClick={saveAlignment}
            data-testid="audio-save-alignment">保存手动对齐</button>
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-5 mt-5">
        <div className="border border-line bg-panel p-3 text-sm">
          <h2 className="font-semibold mb-2">A/B 试听</h2>
          <div className="flex gap-2 items-center"><b>A</b><span className="text-dim">{takeById(ab.a)?.name || "—"}</span></div>
          <audio key={`a-${ab.a}`} controls src={takeUrl(takeById(ab.a))} className="w-full mt-1" />
          <div className="flex gap-2 items-center mt-3"><b>B</b><span className="text-dim">{takeById(ab.b)?.name || "—"}</span></div>
          <audio key={`b-${ab.b}`} controls src={takeUrl(takeById(ab.b))} className="w-full mt-1" />
        </div>
        <div className="border border-line bg-panel p-3 text-sm">
          <h2 className="font-semibold mb-2">处理（作用于主 Take / 场景拼接）</h2>
          <div className="grid grid-cols-2 gap-1">
            {PROC_KEYS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-1">
                <input type="checkbox" checked={!!proc[k]} onChange={(e) => setProc({ ...proc, [k]: e.target.checked })} />{label}
              </label>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <button className="btn-primary" onClick={() => processTake(false)} data-testid="audio-process">应用处理</button>
            <button className="btn" onClick={() => processTake(true)}>撤销处理</button>
          </div>
          <p className="text-dim text-xs mt-1">处理结果写入 processed WAV；G01 优先使用。</p>
        </div>
        <div className="border border-line bg-panel p-3 text-sm">
          <h2 className="font-semibold mb-2">场景 Take / 拼接</h2>
          <select value={sceneSel} onChange={(e) => setSceneSel(e.target.value)} className="w-full">
            {scenes.map((s: any) => <option key={s.id} value={s.id}>{s.id} · {s.start}s–{s.end}s</option>)}
          </select>
          <p className="text-xs text-dim mt-1">当前：{data?.scenePrimary?.[sceneSel] || (data?.primary ? `全局 ${data.primary.name}` : "未分配")}</p>
          <div className="flex gap-1 mt-2 flex-wrap">
            <button className="btn" onClick={() => setSceneTake(selected)}>把选中 Take 设为场景</button>
            <button className="btn" onClick={() => setSceneTake(null)}>清除场景</button>
            <button className="btn-primary" onClick={concat} data-testid="audio-concat">拼接试听</button>
          </div>
          {concatUrl && <audio key={concatUrl} controls src={concatUrl} className="w-full mt-2" />}
        </div>
      </section>

      <section className="border border-line bg-panel p-3 mt-5 text-sm">
        <h2 className="font-semibold mb-2">响度目标与 Stems</h2>
        <div className="flex gap-3 flex-wrap items-center">
          <label>目标 <select value={mix.preset} onChange={(e) => {
            const p = e.target.value;
            setMix({ ...mix, preset: p, targetLufs: Number(p) });
          }} data-testid="audio-loudness">
            <option value="-14">-14（YouTube/播客）</option>
            <option value="-16">-16（通用）</option>
            <option value="-18">-18（广播）</option>
          </select></label>
          <span className="text-dim">当前 {mix.targetLufs} LUFS</span>
          {(["voice", "music", "sfx"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1">{k}
              <input className="w-20" type="number" step="0.5" value={mix.stems[k]}
                onChange={(e) => setMix({ ...mix, stems: { ...mix.stems, [k]: Number(e.target.value) } })} /> dB
            </label>
          ))}
          <button className="btn-primary" onClick={saveMix} data-testid="audio-mix-save">保存响度/Stems</button>
        </div>
        <p className="text-dim text-xs mt-1">G05 按此目标 loudnorm；Stems 输出三轨等长 WAV。SFX 需资产库（FR-36）后才能拖入。</p>
      </section>

      <section className="border border-line bg-panel p-3 mt-5">
        <h2 className="font-semibold mb-2">音乐许可（无许可 final 会被阻断）</h2>
        <div className="grid grid-cols-2 xl:grid-cols-5 gap-2 text-sm">
          <input className="bg-bg border border-line px-2" placeholder="来源" value={lic.source}
            onChange={(e) => setLic({ ...lic, source: e.target.value })} />
          <input className="bg-bg border border-line px-2" placeholder="许可类型" value={lic.license}
            onChange={(e) => setLic({ ...lic, license: e.target.value })} />
          <input className="bg-bg border border-line px-2" type="date" value={lic.expires}
            onChange={(e) => setLic({ ...lic, expires: e.target.value })} />
          <label className="flex items-center gap-1"><input type="checkbox" checked={lic.authorized}
            onChange={(e) => setLic({ ...lic, authorized: e.target.checked })} />已授权</label>
          <button className="btn" onClick={saveLicense}>保存许可</button>
        </div>
      </section>
    </main>
  );
}

export default function AudioPage() {
  return <Suspense fallback={<main className="p-8">加载音频…</main>}><AudioInner /></Suspense>;
}
