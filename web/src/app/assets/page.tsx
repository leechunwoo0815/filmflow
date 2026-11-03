"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Asset = any;

const SOURCE_LABEL: Record<string, string> = {
  doc: "其它文档", template: "模板", run: "历史 Run 快照",
};

function fmtBytes(n: number) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function fileB64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

function AssetCard({ asset, all, onChanged, projectId }: {
  asset: Asset; all: Asset[]; onChanged: () => void; projectId: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [replaceId, setReplaceId] = useState("");
  const [checkText, setCheckText] = useState("");
  const [check, setCheck] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const alternatives = all.filter((a) => a.id !== asset.id && a.kind === asset.kind);

  const rename = async () => {
    const name = prompt("资产名称", asset.name);
    if (name === null) return;
    try {
      await api(`/assets/${asset.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
      onChanged();
    } catch (e: any) { setMsg(e.message); }
  };
  const remove = async () => {
    if (!confirm(`删除「${asset.name}」？被引用时会阻断。`)) return;
    try {
      await api(`/assets/${asset.id}`, { method: "DELETE" });
      onChanged();
    } catch (e: any) {
      const sites = e.details?.usages || [];
      setMsg(`${e.message}${sites.length ? "：" + sites.map((u: any) => `${u.projectName}/${u.sceneId}/${u.layerId || u.field}`).join("、") : ""}`);
      setExpanded(true);
    }
  };
  const replace = async () => {
    if (!replaceId) return;
    if (!confirm(`把「${asset.name}」替换为资产 #${replaceId}？只改引用处，保留图层位置。`)) return;
    try {
      const r = await api(`/assets/${asset.id}/replace`, {
        method: "POST", body: JSON.stringify({ assetId: Number(replaceId) }),
      });
      setMsg(`已替换；影响场景：${r.affectedScenes.join("、") || "无"}`);
      onChanged();
    } catch (e: any) { setMsg(e.message); }
  };
  const runCheck = async () => {
    try {
      setCheck(await api(`/assets/${asset.id}/font-check`, {
        method: "POST", body: JSON.stringify({ text: checkText }),
      }));
    } catch (e: any) { setMsg(e.message); }
  };

  const meta = asset.meta || {};
  return (
    <div className="card p-2 text-sm" data-testid={`asset-${asset.id}`}>
      <div className="flex gap-2">
        <div className="w-28 h-20 shrink-0 bg-panel2 rounded overflow-hidden flex items-center justify-center">
          {asset.kind === "image" && (asset.thumbUrl || asset.fileUrl)
            ? <img src={asset.thumbUrl || asset.fileUrl} alt={asset.name} className="w-full h-full object-cover" />
            : asset.kind === "audio"
              ? <audio src={asset.fileUrl} controls className="w-full" />
              : asset.kind === "video"
                ? <video src={asset.fileUrl} className="w-full h-full object-cover" muted />
                : <span className="text-2xl text-dim">{asset.kind === "font" ? "字" : "?"}</span>}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <b className="truncate">{asset.name}</b>
            <span className="chip">{asset.kind}</span>
            <span className="chip">{asset.scope === "global" ? "全局" : "项目"}</span>
            {asset.refCount > 0 && <span className="chip border-gold/50 text-gold" data-testid="asset-ref-count">引用 {asset.refCount}</span>}
          </div>
          <div className="text-[11px] text-dim mt-0.5">
            {asset.sha256.slice(0, 12)} · {fmtBytes(asset.bytes)}
            {meta.width ? ` · ${meta.width}×${meta.height}` : ""}
            {meta.duration ? ` · ${meta.duration}s` : ""}
            {meta.family ? ` · ${meta.family}${meta.weight ? ` ${meta.weight}` : ""}` : ""}
            {meta.glyphCount ? ` · ${meta.glyphCount} 字形` : ""}
          </div>
          <div className="text-[11px] text-dim mt-0.5 truncate">
            许可：{asset.license?.source || "未填"} / {asset.license?.type || "未填"}
            {asset.license?.expires ? ` / 到期 ${asset.license.expires}` : ""}
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <button className="btn" onClick={rename}>改名</button>
          <button className="btn" onClick={remove}>删除</button>
          <button className="btn" onClick={() => setExpanded((v) => !v)}>{expanded ? "收起" : "使用处"}</button>
        </div>
      </div>
      {msg && <div className="text-xs text-gold mt-1">{msg}</div>}
      {expanded && (
        <div className="mt-2 border-t border-line pt-2 text-xs space-y-1">
          {asset.usages?.length ? asset.usages.map((u: any, i: number) => (
            <div key={i} className="text-dim">
              {u.projectName} · {u.sceneId} · {u.layerId || u.field} · {u.layerType}
              {u.source !== "timeline" && <span className="ml-1">（{SOURCE_LABEL[u.source] || u.source}）</span>}
              {projectId === u.projectId && <a className="text-blue ml-1" href={`/timeline?project=${u.projectId}`}>打开</a>}
            </div>
          )) : <div className="text-dim">未被任何文档/模板/Run 快照引用</div>}
          <div className="flex gap-1 mt-1">
            <select value={replaceId} onChange={(e) => setReplaceId(e.target.value)}>
              <option value="">选择同类型替换资产</option>
              {alternatives.map((a) => <option key={a.id} value={a.id}>#{a.id} {a.name}（{a.scope === "global" ? "全局" : "项目"}）</option>)}
            </select>
            <button className="btn" disabled={!replaceId} onClick={replace}>替换引用</button>
          </div>
          {asset.kind === "font" && (
            <div className="mt-2">
              <textarea className="w-full h-16" placeholder="粘贴要检查的文字…" value={checkText}
                onChange={(e) => setCheckText(e.target.value)} />
              <button className="btn mt-1" onClick={runCheck}>检查缺字</button>
              {check && (
                <div className={`mt-1 ${check.ok ? "text-green" : "text-red"}`}>
                  {check.ok ? `覆盖 ${check.total}/${check.total} 字` :
                    `缺 ${check.missingCount} 字：` + check.missing.map((c: string) => `「${c}」`).join("")}
                </div>
              )}
            </div>
          )}
          <div className="text-dim">
            文件：<a className="text-blue" href={asset.fileUrl} target="_blank" rel="noreferrer">打开原文件</a>
          </div>
        </div>
      )}
    </div>
  );
}

function AssetsInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project") || 0);
  const [scope, setScope] = useState<"project" | "global">(projectId ? "project" : "global");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [projectAssets, setProjectAssets] = useState<Asset[]>([]);
  const [globalAssets, setGlobalAssets] = useState<Asset[]>([]);
  const [license, setLicense] = useState({ source: "", type: "", expires: "" });
  const [tags, setTags] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const qs = `&kind=${encodeURIComponent(kind)}&q=${encodeURIComponent(q)}`;
    const [proj, glob] = await Promise.all([
      projectId ? api<any>(`/assets?scope=project&projectId=${projectId}${qs}`) : Promise.resolve({ items: [] }),
      api<any>(`/assets?scope=global${qs}`),
    ]);
    setProjectAssets(proj.items || []);
    setGlobalAssets(glob.items || []);
  }, [projectId, kind, q]);

  useEffect(() => { load().catch((e) => setMsg(String(e.message || e))); }, [load]);

  const current = scope === "project" ? projectAssets : globalAssets;
  const all = useMemo(() => {
    const seen = new Set<number>();
    return [...projectAssets, ...globalAssets].filter((a) => !seen.has(a.id) && seen.add(a.id));
  }, [projectAssets, globalAssets]);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    if (scope === "project" && !projectId) { setMsg("项目库需要先选项目（URL 加 ?project=）"); return; }
    setBusy(true); setMsg("");
    let ok = 0, dup = 0;
    try {
      for (const f of list) {
        try {
          const data = await fileB64(f);
          const r = await api<any>("/assets", {
            method: "POST",
            body: JSON.stringify({
              scope, projectId: scope === "project" ? projectId : undefined,
              filename: f.name, name: f.name.replace(/\.[^.]+$/, ""), data,
              tags: tags.split(/[,，]/).map((x) => x.trim()).filter(Boolean),
              license,
            }),
          });
          if (r.deduped) dup++; else ok++;
        } catch (e: any) { setMsg(`${f.name}: ${e.message}`); }
      }
      setMsg(`导入完成：新增 ${ok}，去重 ${dup}${list.length > 1 ? `，共 ${list.length}` : ""}`);
      await load();
    } finally { setBusy(false); }
  };

  const switchScope = (s: "project" | "global") => {
    if (s === "project" && !projectId) { setMsg("项目库需要 ?project= 参数"); return; }
    setScope(s);
  };

  return (
    <main className="h-screen flex flex-col bg-bg text-txt">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-line">
        <a className="btn" href={projectId ? `/canvas?project=${projectId}` : "/"}>← 返回</a>
        <b>资产库</b>
        <span className="text-dim text-xs">{projectId ? `项目 ${projectId}` : "全局模式"}</span>
        <button className={`btn ${scope === "project" ? "border-gold" : ""}`} onClick={() => switchScope("project")}>项目库</button>
        <button className={`btn ${scope === "global" ? "border-gold" : ""}`} onClick={() => switchScope("global")}>全局库</button>
        <div className="ml-auto flex gap-2">
          {projectId && <a className="btn" href={`/timeline?project=${projectId}`}>时间轴</a>}
          <a className="btn" href="/help">帮助</a>
        </div>
      </header>
      {msg && <div className="px-3 py-1 text-xs text-gold border-b border-line">{msg}</div>}
      <div className="flex-1 flex min-h-0">
        <aside className="w-[340px] border-r border-line p-3 overflow-y-auto">
          <h2 className="font-semibold mb-2">导入资产</h2>
          <div
            className="border border-dashed border-line rounded p-4 text-center text-xs text-dim"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}
          >
            拖拽文件到这里，或
            <label className="text-blue cursor-pointer ml-1">
              选择文件
              <input type="file" multiple className="hidden" data-testid="asset-file-input"
                onChange={(e) => e.target.files && upload(e.target.files)} />
            </label>
            <div className="mt-2">图片 PNG/JPG/WebP/SVG · 音频 WAV/MP3/M4A · 字体 TTF/OTF/WOFF2 · 视频 MP4/MOV</div>
          </div>
          <div className="mt-3 space-y-2 text-xs">
            <label className="block">标签（逗号分隔）
              <input className="w-full mt-1" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="封面, 证据" />
            </label>
            <label className="block">许可来源
              <input className="w-full mt-1" value={license.source} onChange={(e) => setLicense({ ...license, source: e.target.value })} placeholder="自制 / CC0 / 购买" />
            </label>
            <label className="block">许可类型
              <input className="w-full mt-1" value={license.type} onChange={(e) => setLicense({ ...license, type: e.target.value })} placeholder="CC0 / OFL / 商业授权" />
            </label>
            <label className="block">到期
              <input className="w-full mt-1" value={license.expires} onChange={(e) => setLicense({ ...license, expires: e.target.value })} placeholder="2099-12-31" />
            </label>
            {busy && <div className="text-gold">上传中…</div>}
          </div>
          <h2 className="font-semibold mt-6 mb-2">筛选</h2>
          <div className="flex gap-1 flex-wrap text-xs">
            {[["", "全部"], ["image", "图片"], ["audio", "音频"], ["font", "字体"], ["video", "视频"]].map(([v, label]) => (
              <button key={v} className={`chip ${kind === v ? "border-gold text-gold" : ""}`} onClick={() => setKind(v)}>{label}</button>
            ))}
          </div>
          <input className="w-full mt-2" placeholder="搜索名称/标签…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="text-[11px] text-dim mt-3">
            当前 {scope === "project" ? "项目库" : "全局库"} {current.length} 项；全局 {globalAssets.length} 项。
            项目引用全局资产按 sha 复用，不复制文件。
          </div>
        </aside>
        <section className="flex-1 overflow-y-auto p-3">
          <div className="flex items-center gap-2 mb-2">
            <h2 className="font-semibold">{scope === "project" ? "项目资产" : "全局资产"}</h2>
            <span className="text-dim text-xs">{current.length} 项</span>
            {scope === "project" && <span className="text-dim text-xs">（替换时可选全局资产）</span>}
          </div>
          {current.length === 0
            ? <div className="text-dim text-sm p-6">还没有资产；从左侧拖入文件。</div>
            : <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
              {current.map((a) => <AssetCard key={a.id} asset={a} all={all} onChanged={load} projectId={projectId} />)}
            </div>}
        </section>
      </div>
    </main>
  );
}

export default function AssetsPage() {
  return <Suspense><AssetsInner /></Suspense>;
}
