"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Take = { id: string; name: string; kind: string; file: string; duration: number; primary: boolean; sceneId?: string };
type Segment = { text: string; start: number; end: number };
type AudioData = {
  takes: Take[]; primary: Take | null; alignment: { segments: Segment[]; source?: string };
  license: any; licenseOk: boolean; licenseReason: string;
};

function readBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function AudioInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const [data, setData] = useState<AudioData | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [peaks, setPeaks] = useState<number[][]>([]);
  const [msg, setMsg] = useState("");
  const [recording, setRecording] = useState(false);
  const [lic, setLic] = useState({ source: "", license: "", authorized: true, expires: "", note: "" });
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const canvas = useRef<HTMLCanvasElement | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    const d = await api<AudioData>(`/projects/${projectId}/audio`);
    setData(d);
    setLic({ source: d.license?.source || "", license: d.license?.license || "",
             authorized: d.license?.authorized !== false, expires: d.license?.expires || "",
             note: d.license?.note || "" });
    const takeId = d.primary?.id || d.takes[0]?.id || "";
    setSelected(takeId);
    if (d.alignment?.segments?.length) setSegments(d.alignment.segments);
    else {
      const tl = await api<any>(`/projects/${projectId}/docs/timeline`);
      setSegments((tl.content?.scenes || []).map((s: any) => ({
        text: s.meaning || "", start: Number(s.start || 0), end: Number(s.end || 0),
      })));
    }
  }, [projectId]);
  useEffect(() => { load().catch((e) => setMsg(String(e))); }, [load]);

  useEffect(() => {
    if (!selected || !projectId) return;
    api<any>(`/projects/${projectId}/audio/waveform?takeId=${selected}&w=1200`)
      .then((d) => setPeaks(d.peaks || [])).catch(() => setPeaks([]));
  }, [selected, projectId]);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.fillStyle = "#0f172a"; ctx.fillRect(0, 0, c.width, c.height);
    if (!peaks.length) return;
    const mid = c.height / 2;
    ctx.strokeStyle = "#39C5CF"; ctx.beginPath();
    peaks.forEach((p, i) => {
      const x = (i / Math.max(1, peaks.length - 1)) * c.width;
      ctx.moveTo(x, mid - (p[1] || 0) * mid);
      ctx.lineTo(x, mid - (p[0] || 0) * mid);
    });
    ctx.stroke();
  }, [peaks]);

  const upload = async (file: File) => {
    setMsg("");
    const b64 = await readBase64(file);
    const r = await api<any>(`/projects/${projectId}/audio/upload`, {
      method: "POST",
      body: JSON.stringify({ filename: file.name, data: b64, kind: "voice", name: file.name }),
    });
    setMsg(`已导入 ${r.take.name}（${r.take.duration}s）`);
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
        await api<any>(`/projects/${projectId}/audio/upload`, {
          method: "POST",
          body: JSON.stringify({ filename: "record.webm", data: b64, kind: "voice", name: "录音" }),
        });
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

  const saveAlignment = async () => {
    const r = await api<any>(`/projects/${projectId}/audio/alignment`, {
      method: "POST", body: JSON.stringify({ segments, author: "audio-ui" }),
    });
    setMsg(`对齐已保存（${r.segments.length} 段，manual）`);
  };

  const saveLicense = async () => {
    try {
      await api(`/projects/${projectId}/audio/license`, { method: "POST", body: JSON.stringify(lic) });
      setMsg("音乐许可已保存");
      await load();
    } catch (e: any) { setMsg(String(e?.message || e)); }
  };

  const total = useMemo(() => segments.reduce((a, s) => Math.max(a, s.end), 0), [segments]);
  if (!projectId) return <main className="p-8">缺少 project 参数</main>;
  return (
    <main className="min-h-screen bg-bg text-txt p-6">
      <header className="flex items-center gap-3 mb-4">
        <a className="btn" href={`/editor?project=${projectId}`}>← 编辑器</a>
        <h1 className="text-xl font-semibold">音频工作台 · 项目 {projectId}</h1>
        <span className={data?.licenseOk ? "text-green" : "text-red"}>
          音乐许可：{data?.licenseOk ? "OK" : data?.licenseReason || "未填写"}
        </span>
      </header>
      {msg && <div className="text-sm text-gold mb-3">{msg}</div>}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="border border-line bg-panel p-3">
          <h2 className="font-semibold mb-2">口播 Take</h2>
          <div className="flex gap-2 mb-3">
            <label className="btn cursor-pointer">
              导入音频
              <input type="file" accept="audio/*" className="hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
            </label>
            <button className="btn" onClick={toggleRecord}>{recording ? "停止录音" : "浏览器录音"}</button>
          </div>
          <div className="space-y-2 max-h-72 overflow-auto">
            {(data?.takes || []).map((t) => (
              <div key={t.id} className={`border p-2 text-sm ${selected === t.id ? "border-gold" : "border-line"}`}>
                <button className="text-left w-full" onClick={() => setSelected(t.id)}>
                  <div className="font-medium">{t.name} {t.primary && <span className="text-green">主 Take</span>}</div>
                  <div className="text-dim">{t.duration}s · {t.kind} {t.sceneId || ""}</div>
                </button>
                <button className="btn mt-1" onClick={() => setPrimary(t.id)}>设为主 Take</button>
              </div>
            ))}
            {!data?.takes?.length && <div className="text-dim text-sm">还没有音频，导入或录音。</div>}
          </div>
        </div>
        <div className="xl:col-span-2 border border-line bg-panel p-3">
          <h2 className="font-semibold mb-2">波形与手动对齐</h2>
          <canvas ref={canvas} width={1200} height={180} className="w-full bg-black border border-line" />
          <div className="text-xs text-dim mt-1">总时长 {total.toFixed(2)}s · 来源 manual</div>
          <table className="w-full text-sm mt-3">
            <thead><tr className="text-dim"><th className="text-left">文本</th><th>开始</th><th>结束</th></tr></thead>
            <tbody>
              {segments.map((s, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1">{s.text || `片段 ${i + 1}`}</td>
                  <td><input className="w-24 bg-bg border border-line px-1" type="number" step="0.01"
                             value={s.start} onChange={(e) => { const v = Number(e.target.value);
                               setSegments((all) => all.map((x, j) => j === i ? { ...x, start: v } : x)); }} /></td>
                  <td><input className="w-24 bg-bg border border-line px-1" type="number" step="0.01"
                             value={s.end} onChange={(e) => { const v = Number(e.target.value);
                               setSegments((all) => all.map((x, j) => j === i ? { ...x, end: v } : x)); }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn mt-3" onClick={saveAlignment}>保存手动对齐</button>
        </div>
      </section>
      <section className="border border-line bg-panel p-3 mt-5">
        <h2 className="font-semibold mb-2">音乐许可（无许可 final 会被阻断）</h2>
        <div className="grid grid-cols-2 xl:grid-cols-5 gap-2 text-sm">
          <input className="bg-bg border border-line px-2" placeholder="来源"
                 value={lic.source} onChange={(e) => setLic({ ...lic, source: e.target.value })} />
          <input className="bg-bg border border-line px-2" placeholder="许可类型"
                 value={lic.license} onChange={(e) => setLic({ ...lic, license: e.target.value })} />
          <input className="bg-bg border border-line px-2" type="date"
                 value={lic.expires} onChange={(e) => setLic({ ...lic, expires: e.target.value })} />
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
