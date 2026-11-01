"use client";
import { useEffect, useState } from "react";
import { api, FAMILY_LABELS, StyleDTO } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";

export default function Labeling() {
  const { t } = useLang();
  const [items, setItems] = useState<StyleDTO[]>([]);
  const [current, setCurrent] = useState<StyleDTO | null>(null);
  const [form, setForm] = useState<any>({});
  const [msg, setMsg] = useState("");

  const load = async () => {
    const r = await api("/labels/queue");
    setItems(r.items);
    if (!current && r.items.length) pick(r.items[0]);
  };
  useEffect(() => { load().catch((e) => setMsg(String(e))); }, []);

  const pick = (s: StyleDTO) => {
    setCurrent(s);
    setForm({
      palette: (s.tokens?.palette || []).join(","),
      texture: (s.tokens?.texture || []).join(","),
      motion_pacing: s.tokens?.motion?.pacing || "medium",
      type: (s.tokens?.type || []).join(","),
      composition: (s.tokens?.composition || []).join(","),
      screen_angle: s.tokens?.screen?.angle ?? "",
      screen_period: s.tokens?.screen?.period ?? "",
      family: s.family,
    });
  };

  const submit = async () => {
    if (!current) return;
    try {
      await api(`/labels/${current.id}`, {
        method: "POST",
        body: JSON.stringify({
          palette: form.palette.split(/[,，]/).map((x: string) => x.trim()).filter(Boolean),
          texture: form.texture.split(/[,，]/).map((x: string) => x.trim()).filter(Boolean),
          motion: { pacing: form.motion_pacing },
          type: form.type.split(/[,，]/).map((x: string) => x.trim()).filter(Boolean),
          composition: form.composition.split(/[,，]/).map((x: string) => x.trim()).filter(Boolean),
          screen: { angle: form.screen_angle ? +form.screen_angle : undefined, period: form.screen_period ? +form.screen_period : undefined },
          family: form.family, labeled: true,
        }),
      });
      const next = items.filter((i) => i.id !== current.id);
      setItems(next);
      pick(next[0] || null);
      setMsg(`✓ ${current.id} 补标完成`);
    } catch (e: any) { setMsg(e.message); }
  };

  return (
    <main className="max-w-5xl mx-auto p-6">
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold mb-1">{t("lb.title")} <span className="text-dim text-sm">{items.length} {t("lb.pending")}</span></h1><LangToggle /></div>
      <p className="text-dim text-sm mb-4">{t("lb.hint")}</p>
      {msg && <div className="card border-green/40 p-2 mb-3 text-green text-sm">{msg}</div>}
      <div className="grid grid-cols-[220px_1fr] gap-3">
        <aside className="card p-2 h-[560px] overflow-y-auto text-sm">
          {items.map((s) => (
            <button key={s.id} className={`block w-full text-left px-2 py-1.5 rounded hover:bg-panel2 ${current?.id === s.id ? "text-blue" : ""}`}>
              {s.id} {s.name} <span className="text-dim text-xs">缺 {(s.missing_fields || []).length}</span>
            </button>
          ))}
        </aside>
        <section className="card p-4">
          {current ? (
            <>
              <div className="aspect-video w-64 bg-panel2 rounded mb-3 overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/styles/${current.id}/preview?variant=thumb`} alt={current.name} className="w-full h-full object-cover" />
              </div>
              <h2 className="font-semibold">{current.id} {current.name}</h2>
              <p className="text-dim text-xs mb-3">{current.collection} · 缺失：{(current.missing_fields || []).join("、")}</p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <F label="调色 hex（逗号分隔）" v={form.palette} onChange={(v) => setForm({ ...form, palette: v })} ph="#F4EEE2, #3D5588, #FF665E" />
                <F label="质感（逗号分隔）" v={form.texture} onChange={(v) => setForm({ ...form, texture: v })} ph="纸纹, 网点" />
                <label className="block"><span className="text-dim text-xs">动效节奏</span>
                  <select className="w-full mt-1" value={form.motion_pacing} onChange={(e) => setForm({ ...form, motion_pacing: e.target.value })}>
                    <option value="slow">slow</option><option value="medium">medium</option><option value="fast">fast</option>
                  </select>
                </label>
                <F label="字体（逗号分隔）" v={form.type} onChange={(v) => setForm({ ...form, type: v })} ph="黑体 900" />
                <F label="版式（逗号分隔）" v={form.composition} onChange={(v) => setForm({ ...form, composition: v })} ph="满版, 套准十字" />
                <label className="block"><span className="text-dim text-xs">语义族</span>
                  <select className="w-full mt-1" value={form.family} onChange={(e) => setForm({ ...form, family: e.target.value })}>
                    {Object.entries(FAMILY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <F label="网角（可选）" v={form.screen_angle} onChange={(v) => setForm({ ...form, screen_angle: v })} ph="15" />
                <F label="网周期（可选）" v={form.screen_period} onChange={(v) => setForm({ ...form, screen_period: v })} ph="7" />
              </div>
              <button className="btn-amber mt-4" onClick={submit}>{t("lb.submit")}</button>
            </>
          ) : <p className="text-dim">{t("lb.queueEmpty")}</p>}
        </section>
      </div>
    </main>
  );
}

function F({ label, v, onChange, ph }: { label: string; v: string; onChange: (v: string) => void; ph: string }) {
  return (
    <label className="block"><span className="text-dim text-xs">{label}</span>
      <input className="w-full mt-1" value={v} placeholder={ph} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
