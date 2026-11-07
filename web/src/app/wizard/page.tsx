"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";
import { ThemeToggle } from "@/lib/theme";
import { SuggestionPanel } from "@/components/SuggestionPanel";
import StylePicker from "@/components/StylePicker";

const STEPS = ["wiz.step1", "wiz.step2", "wiz.step3", "wiz.step4", "wiz.step5"];

export default function Wizard() {
  const [draftId, setDraftId] = useState<number | null>(null);
  const [step, setStep] = useState(1);
  const [copy, setCopy] = useState("");
  const [profile, setProfile] = useState({ width: 1920, height: 1080, fps: 24, duration: 39.5 });
  const [pick, setPick] = useState<any>(null);
  const [voice, setVoice] = useState("自录口播");
  const [titles, setTitles] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const { t } = useLang();
  const router = useRouter();
  const createdRef = useRef(false);
  const titleCopyRef = useRef("");

  const frames = Math.round(profile.duration * profile.fps);
  const sentences = copy.split(/(?<=[。！？；!?;])/).filter((s) => s.trim()).length;
  const estSeconds = Math.round(copy.replace(/\s/g, "").length / 5.2);

  useEffect(() => {
    if (createdRef.current) return;
    createdRef.current = true;
    api("/drafts", { method: "POST", body: JSON.stringify({ name: "向导草稿", step: 1 }) })
      .then((d) => setDraftId(d.id)).catch((e) => setMsg(String(e)));
  }, []);

  useEffect(() => {
    if (step !== 3 || !copy.trim()) return;
    api<{ items: string[] }>(`/wizard/titles?copy=${encodeURIComponent(copy)}`)
      .then((r) => {
        setTitles(r.items);
        if (titleCopyRef.current !== copy) {
          titleCopyRef.current = copy;
          setTitle(r.items[0] || "");
        } else {
          setTitle((cur) => cur || r.items[0] || "");
        }
      }).catch((e) => setMsg(String(e)));
  }, [step, copy]);

  const pickTitle = (value: string) => {
    setTitle(value);
    save({ payload: { copy, profile, pick, voice, title: value, brief: { title: value } } });
  };

  const save = async (patch: object) => {
    if (!draftId) return;
    await api(`/drafts/${draftId}`, { method: "PATCH", body: JSON.stringify(patch) });
  };

  const next = async () => {
    await save({ step: step + 1, payload: { copy, profile, pick, voice, title, brief: { title } } });
    setStep((s) => Math.min(5, s + 1));
  };

  const materialize = async () => {
    if (!pick) { setMsg("第 3 步尚未选定主风格"); return; }
    if (!copy.trim()) { setMsg("第 1 步文案为空"); return; }
    setBusy(true);
    try {
      await save({ step: 5, payload: { copy, profile, pick, voice, title, brief: { title } } });
      const r = await api(`/drafts/${draftId}/materialize`, { method: "POST", body: "{}" });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  return (
    <main className="max-w-7xl mx-auto p-6">
      <div data-testid="wizard-root" data-draft-id={draftId ?? ""}
        className="flex items-center justify-between"><h1 className="text-xl font-bold mb-1">{t("wiz.title")}</h1><div className="flex items-center gap-2"><LangToggle /><ThemeToggle /></div></div>
      <p className="text-dim text-sm mb-4">{t("wiz.disclaimer")}</p>
      <ol className="flex gap-2 mb-5 text-sm">
        {STEPS.map((key, i) => (
          <li key={key} className={`px-3 py-1.5 rounded border ${step === i + 1 ? "border-blue text-blue bg-blue/10" : "border-line text-dim"}`}>
            {i + 1}. {t(key)}
          </li>
        ))}
      </ol>

      {msg && <div className="card border-red/40 p-2 mb-3 text-red text-sm">{msg}</div>}

      {step === 1 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">{t("wiz.copyTitle")}</h2>
          <textarea className="w-full h-56 font-mono text-sm" data-testid="copy-input"
            placeholder={t("wiz.copyPh")} value={copy} onChange={(e) => setCopy(e.target.value)} />
          <div className="flex gap-4 text-dim text-sm mt-2">
            <span>{t("wiz.chars")} {copy.replace(/\s/g, "").length}</span>
            <span>{t("wiz.sentences")} {sentences}</span>
            <span>{t("wiz.estDuration")} {estSeconds}s</span>
          </div>
          <SuggestionPanel copy={copy} draftId={draftId} brief={{ title }} />
          <div className="mt-3 text-right"><button className="btn-primary" disabled={!copy.trim()} onClick={next} data-testid="wizard-next-1">{t("wiz.next")}</button></div>
        </section>
      )}

      {step === 2 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">{t("wiz.frameTitle")}</h2>
          <div className="grid grid-cols-4 gap-3">
            <LabeledInput label={t("wiz.width")} value={profile.width} onChange={(v) => setProfile({ ...profile, width: +v })} />
            <LabeledInput label={t("wiz.height")} value={profile.height} onChange={(v) => setProfile({ ...profile, height: +v })} />
            <LabeledInput label="fps" value={profile.fps} onChange={(v) => setProfile({ ...profile, fps: +v })} />
            <LabeledInput label={t("wiz.duration")} value={profile.duration} onChange={(v) => setProfile({ ...profile, duration: +v })} />
          </div>
          <p className="text-dim text-sm mt-2">{t("wiz.framesCalc")} <span className="text-txt font-mono">{frames}</span></p>
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(1)}>{t("wiz.prev")}</button>
            <button className="btn-primary" onClick={next} data-testid="wizard-next-2">{t("wiz.next")}</button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section>
          <h2 className="font-semibold mb-2">{t("wiz.styleTitle")}</h2>
          <StylePicker script={copy} onPrimary={(p) => { setPick(p); save({ payload: { copy, profile, pick: p, voice, title, brief: { title } } }); }} />
          {pick && (
            <div className="card p-3 mt-3" data-testid="title-preview">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-sm">标题预演 · 使用你的文案</h3>
                <span className="text-dim text-xs">3 个候选，点击切换</span>
              </div>
              <div className="relative aspect-video max-h-72 overflow-hidden rounded bg-panel2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/styles/${pick.primary}/preview?variant=detail`} alt="风格预演"
                  className="w-full h-full object-cover" />
                <div className="absolute inset-0 flex items-center justify-center bg-black/35">
                  <div className="text-white text-2xl md:text-3xl font-bold text-center px-6 drop-shadow-lg"
                    data-testid="wizard-title">{title}</div>
                </div>
              </div>
              <div className="flex gap-2 mt-2 flex-wrap">
                {titles.map((value, i) => (
                  <button key={value} className={`chip ${title === value ? "chip-on" : ""}`}
                    data-testid={`title-choice-${i}`} onClick={() => pickTitle(value)}>{value}</button>
                ))}
              </div>
            </div>
          )}
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(2)}>上一步</button>
            <button className="btn-primary" disabled={!pick} onClick={next} data-testid="step3-next">
              {pick ? `${t("wiz.stylePicked")} ${pick.primary}` : t("wiz.stylePickFirst")} → {t("wiz.next")}
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">{t("wiz.voiceTitle")}</h2>
          {["自录口播", "待录", "仅音乐"].map((v) => (
            <label key={v} className="flex items-center gap-2 py-1 text-sm">
              <input type="radio" name="voice" checked={voice === v} onChange={() => setVoice(v)} /> {v}
            </label>
          ))}
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(3)}>{t("wiz.prev")}</button>
            <button className="btn-primary" onClick={next} data-testid="wizard-next-4">{t("wiz.next")}</button>
          </div>
        </section>
      )}

      {step === 5 && (
        <section className="card p-4">
          <h2 className="font-semibold mb-2">{t("wiz.genTitle")}</h2>
          <ul className="text-sm space-y-1 text-dim">
            <li>{t("wiz.summaryCopy")}{copy.length} / {sentences}</li>
            <li>标题：<span className="text-txt">{title}</span></li>
            <li>{t("wiz.summaryFrame")}{profile.width}×{profile.height} · {profile.fps}fps · {profile.duration}s = {frames}</li>
            <li>{t("wiz.summaryPrimary")}<span className="text-gold">{pick?.primary}</span>{pick?.alternates?.length ? ` · ${t("wiz.summaryAlt")} ${pick.alternates.join("/")}` : ""}</li>
            <li>{t("wiz.summaryVoice")}{voice}</li>
            <li>{t("wiz.summaryNodes")}</li>
          </ul>
          <div className="mt-3 flex justify-between">
            <button className="btn" onClick={() => setStep(4)}>{t("wiz.prev")}</button>
            <button className="btn-amber" data-testid="materialize" disabled={busy || !pick} onClick={materialize}>
              {busy ? t("wiz.generating") : t("wiz.generate")}
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
