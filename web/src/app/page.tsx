"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";

export default function Home() {
  const { t } = useLang();
  const [projects, setProjects] = useState<any[]>([]);
  const [lib, setLib] = useState<any>(null);
  const [env, setEnv] = useState<any>(null);
  const [importRoot, setImportRoot] = useState("/Users/litianyu/cc-projects/ai-v/rumor-39s");
  const [msg, setMsg] = useState("");
  const router = useRouter();

  const load = async () => {
    setProjects((await api("/projects")).items);
    setLib(await api("/library/status"));
    setEnv(await api("/environment"));
  };
  useEffect(() => { load().catch((e) => setMsg(String(e))); }, []);

  const doImport = async () => {
    try {
      const r = await api("/projects/import", { method: "POST", body: JSON.stringify({ root: importRoot }) });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(e.message); }
  };

  return (
    <main className="max-w-6xl mx-auto p-8">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">{t("app.title")}<span className="text-dim text-base font-normal">{t("app.subtitle")}</span></h1>
          <p className="text-dim text-sm mt-1">{t("app.tagline")}</p>
        </div>
        <div className="flex gap-2 items-center">
          <a className="btn" href="/labeling">{t("nav.labeling")}{lib ? ` (${lib.matrix?.label_queue ?? 0})` : ""}</a>
          <a className="btn-primary" href="/wizard">{t("nav.newProject")}</a>
          <LangToggle />
        </div>
      </header>

      {msg && <div className="card border-red/40 p-3 mb-4 text-red text-sm">{msg}</div>}

      <div className="grid grid-cols-3 gap-3 mb-8">
        <Stat title={t("home.stat.styles")} value={lib ? `${lib.total_styles}` : "…"} sub={lib ? `${t("home.stat.stylesSub")} ${lib.matrix?.producible}` : ""} />
        <Stat title={t("home.stat.labelQueue")} value={lib ? `${lib.matrix?.label_queue}` : "…"} sub={t("home.stat.labelSub")} />
        <Stat title={t("home.stat.env")} value={env?.ok ? t("home.stat.envReady") : "—"} sub={env?.ok ? "Chrome · ffmpeg ✓" : "/api/environment"} />
      </div>

      <section className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">{t("home.import")}</h2>
        <div className="flex gap-2">
          <input className="flex-1 font-mono text-xs" value={importRoot} onChange={(e) => setImportRoot(e.target.value)} />
          <button className="btn-primary" onClick={doImport}>{t("home.importBtn")}</button>
        </div>
        <p className="text-dim text-xs mt-2">{t("home.importHint")}</p>
      </section>

      <section>
        <h2 className="font-semibold mb-3">{t("home.projects")}</h2>
        {projects.length === 0 && <p className="text-dim text-sm">{t("home.noProjects")}</p>}
        <div className="grid grid-cols-2 gap-3">
          {projects.map((p) => (
            <a key={p.id} href={`/canvas?project=${p.id}`} className="card p-3 hover:border-blue/50">
              <div className="font-medium">{p.name}</div>
              <div className="text-dim text-xs font-mono mt-1 truncate">{p.root}</div>
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}

function Stat({ title, value, sub }: { title: string; value: string; sub: string }) {
  return (
    <div className="card p-4">
      <div className="text-dim text-xs">{title}</div>
      <div className="text-xl font-bold mt-1">{value}</div>
      <div className="text-dim text-xs mt-1">{sub}</div>
    </div>
  );
}
