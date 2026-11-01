"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import StylePicker from "@/components/StylePicker";

const STEPS = ["文案", "画幅与时长", "选整体风格", "声音方案", "生成工作流"];

export default function Wizard() {
  const [draftId, setDraftId] = useState<number | null>(null);
  const [step, setStep] = useState(1);
  const [copy, setCopy] = useState("");
  const [profile, setProfile] = useState({ width: 1920, height: 1080, fps: 24, duration: 39.5 });
  const [pick, setPick] = useState<any>(null);
  const [voice, setVoice] = useState("自录口播");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const createdRef = useRef(false);

  const frames = Math.round(profile.duration * profile.fps);
  const sentences = copy.split(/(?<=[。！？；!?;])/).filter((s) => s.trim()).length;
  const estSeconds = Math.round(copy.replace(/\s/g, "").length / 5.2);

  useEffect(() => {
    if (createdRef.current) return;
    createdRef.current = true;
    api("/drafts", { method: "POST", body: JSON.stringify({ name: "向导草稿", step: 1 }) })
      .then((d) => setDraftId(d.id)).catch((e) => setMsg(String(e)));
  }, []);

  const save = async (patch: object) => {
    if (!draftId) return;
    await api(`/drafts/${draftId}`, { method: "PATCH", body: JSON.stringify(patch) });
  };

  const next = async () => {
    await save({ step: step + 1, payload: { copy, profile, pick, voice } });
    setStep((s) => Math.min(5, s + 1));
  };

  const materialize = async () => {
    if (!pick) { setMsg("第 3 步尚未选定主风格"); return; }
    if (!copy.trim()) { setMsg("第 1 步文案为空"); return; }
    setBusy(true);
    try {
      await save({ step: 5, payload: { copy, profile, pick, voice } });
      const r = await api(`/drafts/${draftId}/materialize`, { method: "POST", body: "{}" });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  return (
    <main className="max-w-7xl mx-auto p-6">
      <h1 className="text-xl font-bold mb-1">新建项目</h1>
      <p className="text-dim text-sm mb-4">本应用不生成剧本/场景，只校验与编排。</p>
      <ol className="flex gap-2 mb-5 text-sm">
        {STEPS.map((s, i) => (
          <li key={s} className={`px-3 py-1.5 rounded border ${step === i + 1 ? "border-blue text-blue bg-blue/10" : "border-line text-dim"}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>

      {msg && <div className="card border-red/40 p-2 mb-3 text-red text-sm">{msg}</div>}

      {step === 1 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">① 文案（粘贴/上传）</h2>
          <textarea className="w-full h-56 font-mono text-sm" data-testid="copy-input"
            placeholder="粘贴或输入口播文案……" value={copy} onChange={(e) => setCopy(e.target.value)} />
          <div className="flex gap-4 text-dim text-sm mt-2">
            <span>字数 {copy.replace(/\s/g, "").length}</span>
            <span>句数 {sentences}</span>
            <span>按 5.2 字/秒 预估口播 {estSeconds}s</span>
          </div>
          <div className="mt-3 text-right"><button className="btn-primary" disabled={!copy.trim()} onClick={next}>下一步</button></div>
        </section>
      )}

      {step === 2 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">② 画幅与时长</h2>
          <div className="grid grid-cols-4 gap-3">
            <LabeledInput label="宽" value={profile.width} onChange={(v) => setProfile({ ...profile, width: +v })} />
            <LabeledInput label="高" value={profile.height} onChange={(v) => setProfile({ ...profile, height: +v })} />
            <LabeledInput label="fps" value={profile.fps} onChange={(v) => setProfile({ ...profile, fps: +v })} />
            <LabeledInput label="时长(s)" value={profile.duration} onChange={(v) => setProfile({ ...profile, duration: +v })} />
          </div>
          <p className="text-dim text-sm mt-2">帧数 = round(时长 × fps) = <span className="text-txt font-mono">{frames}</span></p>
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(1)}>上一步</button>
            <button className="btn-primary" onClick={next}>下一步</button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section>
          <h2 className="font-semibold mb-2">③ 选整体风格（341 条全库）</h2>
          <StylePicker script={copy} onPrimary={(p) => { setPick(p); save({ payload: { copy, profile, pick: p, voice } }); }} />
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(2)}>上一步</button>
            <button className="btn-primary" disabled={!pick} onClick={next} data-testid="step3-next">
              {pick ? `已选主风格 ${pick.primary}` : "先设为主风格"} → 下一步
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">④ 声音方案</h2>
          {["自录口播", "待录", "仅音乐"].map((v) => (
            <label key={v} className="flex items-center gap-2 py-1 text-sm">
              <input type="radio" name="voice" checked={voice === v} onChange={() => setVoice(v)} /> {v}
            </label>
          ))}
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(3)}>上一步</button>
            <button className="btn-primary" onClick={next}>下一步</button>
          </div>
        </section>
      )}

      {step === 5 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">⑤ 生成工作流</h2>
          <ul className="text-sm space-y-1 text-dim">
            <li>文案：{copy.length} 字 / {sentences} 句</li>
            <li>画幅：{profile.width}×{profile.height} · {profile.fps}fps · {profile.duration}s = {frames} 帧</li>
            <li>主风格：<span className="text-gold">{pick?.primary}</span>{pick?.alternates?.length ? ` · 备选 ${pick.alternates.join("/")}` : ""}</li>
            <li>声音：{voice}</li>
            <li>将生成 46 节点画布 · A05 门已按你的选择记录批准</li>
          </ul>
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(4)}>上一步</button>
            <button className="btn-amber" data-testid="materialize" disabled={busy || !pick} onClick={materialize}>
              {busy ? "生成中…" : "生成工作流 →"}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}

function LabeledInput({ label, value, onChange }: { label: string; value: number; onChange: (v: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="text-dim text-xs">{label}</span>
      <input className="w-full mt-1" type="number" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
