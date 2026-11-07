"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Tpl = any;

function TemplateCard({ tpl, onUse, onSeries }: { tpl: Tpl; onUse: () => void; onSeries?: () => void }) {
  return (
    <div className="card p-4 flex flex-col" data-testid={`template-${tpl.id}`}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-medium">{tpl.title}{tpl.saved && <span className="badge border-gold/50 text-gold ml-1">已保存</span>}</div>
        <span className="text-gold text-sm">{Number(tpl.seconds || 0).toFixed(1)}s</span>
      </div>
      <p className="text-dim text-sm mt-2 flex-1">{tpl.description || "—"}</p>
      {tpl.copy && <p className="text-xs text-dim mt-2 line-clamp-3">{tpl.copy}</p>}
      <div className="text-[11px] text-dim mt-2">
        {tpl.kind === "project" ? `${tpl.sceneCount ?? "—"} 场` : "场景模板"}
        {tpl.version ? ` · v${tpl.version}` : ""}
        {tpl.variables?.length ? ` · 变量 ${tpl.variables.join("、")}` : ""}
      </div>
      <div className="flex gap-2 mt-3">
        <button className="btn-primary" onClick={onUse}>用此模板</button>
        {onSeries && tpl.saved && tpl.kind === "project" && <button className="btn" onClick={onSeries}>系列</button>}
      </div>
    </div>
  );
}

function TemplatesInner() {
  const params = useSearchParams();
  const router = useRouter();
  const initialProject = Number(params.get("project") || 0);
  const [tab, setTab] = useState<"project" | "scene">("project");
  const [projects, setProjects] = useState<any[]>([]);
  const [projectTemplates, setProjectTemplates] = useState<Tpl[]>([]);
  const [sceneTemplates, setSceneTemplates] = useState<Tpl[]>([]);
  const [msg, setMsg] = useState("");
  const [saveProject, setSaveProject] = useState(initialProject || 0);
  const [saveName, setSaveName] = useState("");
  const [saveDesc, setSaveDesc] = useState("");
  const [saveCopy, setSaveCopy] = useState("");
  const [seriesTpl, setSeriesTpl] = useState("");
  const [seriesItems, setSeriesItems] = useState('[{"variables":{"title":"第一条","number":1}},{"variables":{"title":"第二条","number":2}}]');
  const [seriesResult, setSeriesResult] = useState<any>(null);
  const [insertProject, setInsertProject] = useState(initialProject || 0);
  const [insertTpl, setInsertTpl] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [p, pt, st] = await Promise.all([
      api<any>("/projects"),
      api<any>("/templates"),
      api<any>("/templates?kind=scene"),
    ]);
    setProjects(p.items || []);
    setProjectTemplates(pt.items || []);
    setSceneTemplates(st.items || []);
    const latest = p.items?.length ? p.items[p.items.length - 1].id : 0;
    setSaveProject((cur) => cur || latest);
    setInsertProject((cur) => cur || latest);
    setSeriesTpl((cur) => cur || (pt.items || []).find((x: Tpl) => x.saved)?.id || "");
  }, []);
  useEffect(() => { load().catch((e) => setMsg(String(e.message || e))); }, [load]);

  const savedProjects = useMemo(() => projectTemplates.filter((x) => x.saved), [projectTemplates]);
  const seriesPreview = useMemo(() => {
    try {
      const arr = JSON.parse(seriesItems);
      return Array.isArray(arr) ? arr.slice(0, 3) : [];
    } catch { return []; }
  }, [seriesItems]);

  const useTemplate = async (tpl: Tpl) => {
    try {
      let variables: any = {};
      const vars = tpl.variables || [];
      if (vars.length) {
        const raw = window.prompt(`模板变量（JSON）：${vars.join("、")}`, JSON.stringify(
          Object.fromEntries(vars.map((v: string) => [v, ""])), null, 1));
        if (raw === null) return;
        variables = JSON.parse(raw);
      }
      const r = await api<any>("/projects/from-template", {
        method: "POST", body: JSON.stringify({
          templateId: tpl.id, name: `新片 · ${tpl.title}`, variables,
        }),
      });
      router.push(`/canvas?project=${r.project.id}&run=${r.run_id}`);
    } catch (e: any) { setMsg(String(e.message || e)); }
  };

  const saveAsTemplate = async () => {
    if (!saveProject || !saveName.trim()) { setMsg("选择项目并填写模板名称"); return; }
    setBusy(true); setMsg("");
    try {
      const body: any = { name: saveName.trim(), description: saveDesc };
      if (saveCopy.trim()) body.copy = saveCopy;
      const r = await api<any>(`/projects/${saveProject}/save-template`, {
        method: "POST", body: JSON.stringify(body),
      });
      setMsg(`已保存模板：${r.template.title} v${r.template.version}`);
      setSaveName(""); setSaveDesc(""); setSaveCopy("");
      await load();
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  };

  const loadCopy = async () => {
    if (!saveProject) return;
    try {
      const r = await api<any>(`/projects/${saveProject}/docs/script`);
      setSaveCopy(r.content?.text || "");
    } catch (e: any) { setMsg(String(e.message || e)); }
  };

  const createSeries = async () => {
    if (!seriesTpl) { setMsg("选择一个已保存的项目模板"); return; }
    let items;
    try { items = JSON.parse(seriesItems); } catch { setMsg("系列 items 必须是 JSON 数组"); return; }
    if (!Array.isArray(items) || !items.length) { setMsg("至少 1 项"); return; }
    if (items.length > 5) { setMsg("v1 最多 5 项；批量 CSV/队列属 R4 FR-46"); return; }
    setBusy(true); setMsg("");
    try {
      const r = await api<any>("/series/from-template", {
        method: "POST", body: JSON.stringify({ templateId: seriesTpl, name: "系列", items }),
      });
      setSeriesResult(r);
      setMsg(`系列创建完成：成功 ${r.created}，失败 ${r.failed}`);
      await load();
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  };

  const insertScene = async () => {
    if (!insertProject || !insertTpl) { setMsg("选择项目和场景模板"); return; }
    setBusy(true); setMsg("");
    try {
      const tl = await api<any>(`/projects/${insertProject}/docs/timeline`);
      const r = await api<any>(`/projects/${insertProject}/timeline/scene-template`, {
        method: "POST", body: JSON.stringify({
          templateId: insertTpl, baseVersion: tl.version,
        }),
      });
      setMsg(`已插入 ${r.sceneId}；打开时间轴继续编辑`);
      router.push(`/timeline?project=${insertProject}`);
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen max-w-6xl mx-auto p-6 bg-bg text-txt">
      <header className="flex items-center gap-2 mb-5">
        <Link className="btn" href="/">← 首页</Link>
        <h1 className="text-xl font-bold">模板库</h1>
        <span className="text-dim text-xs">项目模板 / 场景模板 / 小系列</span>
        <div className="ml-auto flex gap-2">
          <Link className="btn" href="/help">帮助</Link>
          <Link className="btn" href="/wizard">新建项目</Link>
        </div>
      </header>
      {msg && <div className="card border-gold/40 p-2 text-sm text-gold mb-3">{msg}</div>}
      <div className="flex gap-2 mb-4">
        <button className={`btn ${tab === "project" ? "border-gold" : ""}`} onClick={() => setTab("project")}>项目模板</button>
        <button className={`btn ${tab === "scene" ? "border-gold" : ""}`} onClick={() => setTab("scene")}>场景模板</button>
      </div>

      {tab === "project" ? (
        <>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
            {projectTemplates.map((tpl) => (
              <TemplateCard key={tpl.id} tpl={tpl} onUse={() => useTemplate(tpl)}
                onSeries={() => { setSeriesTpl(tpl.id); setMsg(`已选择「${tpl.title}」做系列`); }} />
            ))}
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card p-4">
              <h2 className="font-semibold mb-2">把项目另存为模板</h2>
              <div className="space-y-2 text-sm">
                <select className="w-full" data-testid="save-project" value={saveProject} onChange={(e) => setSaveProject(Number(e.target.value))}>
                  {projects.map((p) => <option key={p.id} value={p.id}>#{p.id} {p.name}</option>)}
                </select>
                <input className="w-full" data-testid="save-name" placeholder="模板名称" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
                <input className="w-full" placeholder="描述（可选）" value={saveDesc} onChange={(e) => setSaveDesc(e.target.value)} />
                <div className="flex gap-1">
                  <textarea className="w-full h-20 font-mono text-xs" placeholder="文案（留空=使用项目当前文案；可写 {{title}}、{{number}}、{{accent}}）"
                    value={saveCopy} onChange={(e) => setSaveCopy(e.target.value)} />
                  <button className="btn self-start" onClick={loadCopy}>载入文案</button>
                </div>
                <button className="btn-primary" disabled={busy} onClick={saveAsTemplate}>保存模板</button>
                <p className="text-[11px] text-dim">保存 profile、时间轴结构/相机/转场/图层/SFX/字体、风格、交付文档；实例化时复制源项目本地资产，全局资产复用 sha。</p>
              </div>
            </div>

            <div className="card p-4">
              <h2 className="font-semibold mb-2">系列（v1 最多 5 项）</h2>
              <div className="space-y-2 text-sm">
                <select className="w-full" value={seriesTpl} onChange={(e) => setSeriesTpl(e.target.value)}>
                  <option value="">选择已保存的项目模板</option>
                  {savedProjects.map((t) => <option key={t.id} value={t.id}>{t.title} v{t.version}</option>)}
                </select>
                <textarea className="w-full h-28 font-mono text-xs" value={seriesItems}
                  onChange={(e) => setSeriesItems(e.target.value)} />
                <div className="text-[11px] text-dim">
                  预览前 3 项：
                  {seriesPreview.map((x: any, i: number) => (
                    <div key={i}>{i + 1}. {x.name || "自动命名"} · {JSON.stringify(x.variables || x.vars || {})}</div>
                  ))}
                </div>
                <button className="btn-primary" disabled={busy} onClick={createSeries}>创建系列</button>
                {seriesResult && (
                  <div className="text-xs space-y-1" data-testid="series-result">
                    {seriesResult.items.map((x: any) => (
                      <div key={x.index} className={x.ok ? "text-green" : "text-red"}>
                        {x.name}: {x.ok ? <Link className="text-blue" href={`/canvas?project=${x.project.id}&run=${x.run_id}`}>项目 #{x.project.id}</Link> : x.error}
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-dim">CSV/10 行队列/批量 zip 依赖 R4 FR-46，本批未做；失败项隔离。</p>
              </div>
            </div>
          </section>
        </>
      ) : (
        <>
          <div className="card p-3 mb-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-dim">插入到项目：</span>
            <select data-testid="scene-insert-project" value={insertProject} onChange={(e) => setInsertProject(Number(e.target.value))}>
              {projects.map((p) => <option key={p.id} value={p.id}>#{p.id} {p.name}</option>)}
            </select>
            <select data-testid="scene-insert-template" value={insertTpl} onChange={(e) => setInsertTpl(e.target.value)}>
              <option value="">选择场景模板</option>
              {sceneTemplates.map((t) => <option key={t.id} value={t.id}>{t.title}（{Number(t.seconds || 0).toFixed(1)}s）</option>)}
            </select>
            <button className="btn-primary" disabled={busy} onClick={insertScene} data-testid="scene-template-insert">插入到末尾</button>
            <span className="text-[11px] text-dim">也可以在时间轴 inspector 里插入到选中场景之后。</span>
          </div>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {sceneTemplates.map((tpl) => (
              <TemplateCard key={tpl.id} tpl={tpl} onUse={() => { setInsertTpl(tpl.id); setMsg(`已选择「${tpl.title}」`); }} />
            ))}
          </section>
        </>
      )}
    </main>
  );
}

export default function TemplatesPage() {
  return <Suspense><TemplatesInner /></Suspense>;
}
