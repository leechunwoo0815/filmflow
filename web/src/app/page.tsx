"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";
import { ThemeToggle } from "@/lib/theme";

export default function Home() {
  const { t } = useLang();
  const [projects, setProjects] = useState<any[]>([]);
  const [lib, setLib] = useState<any>(null);
  const [env, setEnv] = useState<any>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [examples, setExamples] = useState<any[]>([]);
  const [onboard, setOnboard] = useState(true);
  const [importRoot, setImportRoot] = useState("/Users/litianyu/cc-projects/ai-v/rumor-39s");
  const [msg, setMsg] = useState("");
  const router = useRouter();

  const load = async () => {
    setProjects((await api("/projects")).items);
    setLib(await api("/library/status"));
    setEnv(await api("/environment"));
    setTemplates((await api<{ items: any[] }>("/templates")).items);
    setExamples((await api<{ items: any[] }>("/examples")).items);
  };
  useEffect(() => { load().catch((e) => setMsg(String(e))); }, []);

  const useTemplate = async (templateId: string) => {
    try {
      const r = await api<any>("/projects/from-template", {
        method: "POST", body: JSON.stringify({ templateId }),
      });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(e.message); }
  };

  const cloneExample = async (exampleId: string) => {
    try {
      const r = await api<any>(`/examples/${exampleId}/clone`, { method: "POST", body: "{}" });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(e.message); }
  };

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
          <a className="btn" href="/templates">模板库</a>
          <a className="btn" href="/help">帮助</a>
          <a className="btn" href="/labeling">{t("nav.labeling")}{lib ? ` (${lib.matrix?.label_queue ?? 0})` : ""}</a>
          <a className="btn-primary" href="/wizard">{t("nav.newProject")}</a>
          <LangToggle /><ThemeToggle />
        </div>
      </header>

      {msg && <div className="card border-red/40 p-3 mb-4 text-red text-sm">{msg}</div>}

      <div className="grid grid-cols-3 gap-3 mb-8">
        <Stat title={t("home.stat.styles")} value={lib ? `${lib.total_styles}` : "…"} sub={lib ? `${t("home.stat.stylesSub")} ${lib.matrix?.producible}` : ""} />
        <Stat title={t("home.stat.labelQueue")} value={lib ? `${lib.matrix?.label_queue}` : "…"} sub={t("home.stat.labelSub")} />
        <Stat title={t("home.stat.env")} value={env?.ok ? t("home.stat.envReady") : "—"} sub={env?.ok ? "Chrome · ffmpeg ✓" : "/api/environment"} />
      </div>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">做第一条片</h2>
          <span className="text-dim text-xs">选一个模板，系统会预置文案/场景/风格；音频可稍后补</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {templates.map((tpl) => (
            <div key={tpl.id} className="card p-4 flex flex-col" data-testid={`template-${tpl.id}`}>
              <div className="flex items-baseline justify-between">
                <div className="font-medium">{tpl.title}</div>
                <span className="text-gold text-sm">{tpl.seconds}s</span>
              </div>
              <p className="text-dim text-sm mt-2 flex-1">{tpl.description}</p>
              <p className="text-xs text-dim mt-2 line-clamp-2">{tpl.copy}</p>
              <button className="btn-primary mt-3" data-testid={`use-template-${tpl.id}`} onClick={() => useTemplate(tpl.id)}>用此模板</button>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">示例项目（只读）</h2>
          <span className="text-dim text-xs">仓库内只读源；复制后得到你自己的项目根，可随意改</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {examples.map((ex) => (
            <div key={ex.id} className="card p-4 flex flex-col" data-testid={`example-${ex.id}`}>
              <div className="flex items-baseline justify-between">
                <div className="font-medium">{ex.title} <span className="badge border-line text-dim ml-1">只读</span></div>
                <span className="text-gold text-sm">{ex.seconds}s</span>
              </div>
              <p className="text-dim text-sm mt-2 flex-1">{ex.description}</p>
              <p className="text-xs text-dim mt-2 line-clamp-2">{ex.copyPreview}…</p>
              <button className="btn-primary mt-3 self-start" onClick={() => cloneExample(ex.id)}>复制为我的项目</button>
            </div>
          ))}
        </div>
      </section>

      {onboard && projects.length === 0 && (
        <section className="card p-4 mb-6 border-gold/40">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">第一次用？按 5 步走（10 分钟出片）</h2>
            <button className="btn" onClick={() => setOnboard(false)}>跳过</button>
          </div>
          <ol className="grid grid-cols-5 gap-2 mt-3 text-sm">
            <li className="border border-line p-2"><b>1</b> 场景列表<br /><span className="text-dim">画布 / 编辑器</span></li>
            <li className="border border-line p-2"><b>2</b> 单帧预览<br /><span className="text-dim">静帧审阅</span></li>
            <li className="border border-line p-2"><b>3</b> 改一句<br /><span className="text-dim">编辑器自动保存</span></li>
            <li className="border border-line p-2"><b>4</b> 看 diff<br /><span className="text-dim">审阅页对比</span></li>
            <li className="border border-line p-2"><b>5</b> 出 draft<br /><span className="text-dim">预览 / 交付</span></li>
          </ol>
        </section>
      )}

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
