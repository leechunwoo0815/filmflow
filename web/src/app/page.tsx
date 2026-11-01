"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function Home() {
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
          <h1 className="text-2xl font-bold">FilmFlow <span className="text-dim text-base font-normal">· 印厂控制台</span></h1>
          <p className="text-dim text-sm mt-1">代码动画全生命周期工作台 · 46 节点 / 7 阶段 / 341 条风格库</p>
        </div>
        <div className="flex gap-2">
          <a className="btn" href="/labeling">补标队列{lib ? ` (${lib.matrix?.label_queue ?? 0})` : ""}</a>
          <a className="btn-primary" href="/wizard">＋ 新建项目向导</a>
        </div>
      </header>

      {msg && <div className="card border-red/40 p-3 mb-4 text-red text-sm">{msg}</div>}

      <div className="grid grid-cols-3 gap-3 mb-8">
        <Stat title="风格库" value={lib ? `${lib.total_styles} 条` : "…"} sub={lib ? `10 来源集 · 可生产 ${lib.matrix?.producible}` : ""} />
        <Stat title="补标队列" value={lib ? `${lib.matrix?.label_queue}` : "…"} sub="tokens 残缺 · 不可主选" />
        <Stat title="环境" value={env?.ok ? "就绪" : "缺失"} sub={env?.ok ? `Chrome · ffmpeg ✓` : "点击查看 /api/environment"} />
      </div>

      <section className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">导入项目（含 task.json）</h2>
        <div className="flex gap-2">
          <input className="flex-1 font-mono text-xs" value={importRoot} onChange={(e) => setImportRoot(e.target.value)} />
          <button className="btn-primary" onClick={doImport}>导入 rumor-39s</button>
        </div>
        <p className="text-dim text-xs mt-2">导入后画布为 46 节点只读视图，状态来自真实文件。</p>
      </section>

      <section>
        <h2 className="font-semibold mb-3">项目</h2>
        {projects.length === 0 && <p className="text-dim text-sm">暂无项目——先导入参考项目，或走新建向导。</p>}
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
