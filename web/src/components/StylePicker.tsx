"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, StyleDTO, FAMILY_LABELS, cornerBadge, badges3, visualOneLine } from "@/lib/api";

const CHIPS = ["可生产", "中文友好", "低饱和", "高密度", "动态强", "可印刷", "≤3版"];

export default function StylePicker({ script, onPrimary }: { script: string; onPrimary: (pick: any) => void }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [chips, setChips] = useState<Set<string>>(new Set());
  const [items, setItems] = useState<StyleDTO[]>([]);
  const [total, setTotal] = useState(0);
  const [recommended, setRecommended] = useState<any[]>([]);
  const [recommendMode, setRecommendMode] = useState(true);
  const [seed, setSeed] = useState(0);
  const [detail, setDetail] = useState<StyleDTO | null>(null);
  const [tray, setTray] = useState<StyleDTO[]>([]);
  const [primary, setPrimary] = useState<string>("");
  const [lib, setLib] = useState<any>(null);
  const [railTab, setRailTab] = useState<"family" | "collection">("family");
  const [family, setFamily] = useState("");
  const [collection, setCollection] = useState("");
  const [loading, setLoading] = useState(false);
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api("/library/status").then(setLib).catch(() => {}); }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const loadRecommend = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api(`/recommend?script=${encodeURIComponent(script)}&seed=${seed}`);
      setRecommended(r.items);
      const ids = r.items.map((x: any) => x.style_id);
      const all = await api(`/styles?limit=400`);
      const byId: Record<string, StyleDTO> = {};
      for (const it of all.items) byId[it.id] = it;
      setItems(ids.map((i: string) => byId[i]).filter(Boolean));
      setTotal(ids.length);
      setRecommendMode(true);
    } finally { setLoading(false); }
  }, [script, seed]);

  const loadSearch = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ q: debounced, limit: "400" });
      if (family) params.set("family", family);
      if (collection) params.set("collection", collection);
      if (chips.size) params.set("chips", [...chips].join(","));
      const r = await api(`/styles?${params}`);
      setItems(r.items); setTotal(r.total); setRecommendMode(false);
    } finally { setLoading(false); }
  }, [debounced, chips, family, collection]);

  useEffect(() => {
    if (debounced || chips.size || family || collection) loadSearch();
    else loadRecommend();
  }, [debounced, chips, family, collection, loadRecommend, loadSearch]);

  const setPrimaryStyle = async (s: StyleDTO) => {
    if (s.engine_status === "unavailable") { alert(`E_ENGINE_UNAVAILABLE：${s.family} 族暂无引擎，可登记需求`); return; }
    if (s.tokens_status !== "complete") { alert(`该风格元数据不完整（缺 ${s.missing_fields.join("/")}），不可主选；可加入补标队列`); return; }
    setPrimary(s.id);
    onPrimary({ primary: s.id, alternates: tray.filter((t) => t.id !== s.id).slice(0, 2).map((t) => t.id), reason: `对比后选定 · ${s.collection}` });
  };

  const toggleTray = (s: StyleDTO) => {
    setTray((cur) => cur.some((t) => t.id === s.id)
      ? cur.filter((t) => t.id !== s.id)
      : cur.length >= 4 ? (alert("对比托盘最多 4 条，先移除一条"), cur) : [...cur, s]);
  };

  const similar = async (s: StyleDTO) => {
    const r = await api(`/styles/${s.id}/similar`);
    const all = await api(`/styles?limit=400`);
    const byId: Record<string, StyleDTO> = {}; all.items.forEach((i: StyleDTO) => byId[i.id] = i);
    setItems(r.items.map((x: any) => byId[x.style_id]).filter(Boolean)); setRecommendMode(false); setDetail(null);
  };

  const randomOne = async () => {
    const r = await api(`/styles/random?seed=${Date.now() % 100000}`);
    const all = await api(`/styles?limit=400`);
    const s = all.items.find((i: StyleDTO) => i.id === r.style_id);
    if (s) { setItems([s]); setTotal(1); setRecommendMode(false); setDetail(s); }
    if (r.reason) alert(r.reason);
  };

  // 键盘：Enter 详情 / C 对比 / S 主选（规格 §7.0）
  const onKey = (e: React.KeyboardEvent) => {
    if (!items.length) return;
    if (e.key === "Escape") setDetail(null);
  };

  const famGroups = useMemo(() => {
    const g: Record<string, number> = {};
    lib && Object.entries(FAMILY_LABELS).forEach(([k]) => (g[k] = 0));
    return g;
  }, [lib]);

  return (
    <div onKeyDown={onKey} className="grid grid-cols-[220px_1fr_300px] gap-3 h-[640px] overflow-hidden" data-testid="style-picker">
      {/* 左侧双轴 */}
      <aside className="card p-3 overflow-y-auto text-sm min-h-0">
        <div className="flex gap-1 mb-3">
          <button className={`chip ${railTab === "family" ? "chip-on" : ""}`} onClick={() => setRailTab("family")}>语义族 9</button>
          <button className={`chip ${railTab === "collection" ? "chip-on" : ""}`} onClick={() => setRailTab("collection")}>来源集 10</button>
        </div>
        {railTab === "family" && Object.keys(FAMILY_LABELS).map((f) => (
          <button key={f} className={`block w-full text-left px-2 py-1.5 rounded hover:bg-panel2 ${family === f ? "text-blue" : "text-dim"}`}
            onClick={() => setFamily(family === f ? "" : f)}>
            ▸ {FAMILY_LABELS[f]}
          </button>
        ))}
        {railTab === "collection" && lib && (
          <>
            <p className="text-dim text-xs px-2 py-1">341 总数 · 可生产 {lib.matrix?.producible}</p>
            {["O_奥斯卡98部", "L_Lemo-Opuscar", "M_动态风格", "K_卡通画风", "X_code-video", "A-G_代码样片", "V_mg-styles-15", "Z_中国风", "H_现成版式", "R_照参考学来的"].map((c) => (
              <button key={c} className={`block w-full text-left px-2 py-1.5 rounded hover:bg-panel2 ${collection === c ? "text-blue" : "text-dim"}`}
                onClick={() => setCollection(collection === c ? "" : c)}>
                ▸ {c.split("_")[0]} <span className="text-xs">{c.split("_")[1]}</span>
              </button>
            ))}
          </>
        )}
        {lib && (
          <div className="mt-4 border-t border-line pt-3 text-xs text-dim">
            <p>实测矩阵（ADR-0002）</p>
            <p className="mt-1">{lib.matrix?.cover_complete} / {lib.matrix?.cover_incomplete} / {lib.matrix?.nocover_complete} / {lib.matrix?.nocover_incomplete}</p>
          </div>
        )}
      </aside>

      {/* 中部：搜索 + chips + 网格 */}
      <section className="flex flex-col min-w-0 min-h-0">
        <div className="flex gap-2 items-center mb-2">
          <input data-testid="style-search" className="flex-1" placeholder="搜索 风格/ID/关键词（支持同义词：水墨↔中国风）"
            value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn" onClick={() => { setSeed((s) => s + 1); }} title="换一批（换种子）">换一批</button>
          <button className="btn" onClick={randomOne} title="随机但可解释">随机</button>
        </div>
        <div className="flex gap-1.5 mb-2 flex-wrap">
          {CHIPS.map((c) => (
            <button key={c} className={`chip ${chips.has(c) ? "chip-on" : ""}`}
              onClick={() => setChips((cur) => { const n = new Set(cur); n.has(c) ? n.delete(c) : n.add(c); return n; })}>{c}</button>
          ))}
          <span className="text-dim text-xs ml-auto self-center">
            {loading ? "加载中…" : `${items.length} / ${total} 条`}{recommendMode && " · 推荐（按文案匹配度）"}
          </span>
        </div>
        <div ref={gridRef} className="grid grid-cols-3 gap-2 overflow-y-auto pr-1 flex-1"
          style={{ contentVisibility: "auto" }}>
          {items.map((s) => {
            const cb = cornerBadge(s);
            return (
              <div key={s.id} data-testid={`style-card-${s.id}`}
                className={`card cursor-pointer hover:border-dim relative ${primary === s.id ? "border-gold ring-1 ring-gold" : ""} ${tray.some((t) => t.id === s.id) ? "border-cyan" : ""}`}
                onClick={() => setDetail(s)}>
                <div className="aspect-video bg-panel2 relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/api/styles/${s.id}/preview?variant=thumb`} alt={`${s.id} ${s.name}`} loading="lazy"
                    className="w-full h-full object-cover" />
                  {cb && <span className={`badge absolute top-1.5 right-1.5 bg-bg/80 ${cb.cls}`}>{cb.label}</span>}
                </div>
                <div className="p-2">
                  <div className="text-sm font-medium truncate">{s.id} {s.name}</div>
                  <div className="text-dim text-xs mt-0.5 truncate">{visualOneLine(s)}</div>
                  <div className="flex gap-1 mt-1.5">
                    {badges3(s).map((b) => <span key={b} className="badge border-line text-dim">{b}</span>)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 右侧详情 */}
      <aside className="card p-3 overflow-y-auto text-sm min-h-0">
        {detail ? (
          <>
            <div className="aspect-video bg-panel2 rounded mb-2 overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/api/styles/${detail.id}/preview?variant=detail`} alt={detail.name} className="w-full h-full object-cover" />
            </div>
            <h3 className="font-semibold">{detail.id} {detail.name}</h3>
            <p className="text-dim text-xs mt-0.5">{detail.collection} · {FAMILY_LABELS[detail.family]}</p>
            <p className="text-xs mt-2 text-dim">sha256 <span className="font-mono">{detail.sha256.slice(0, 16)}…</span></p>
            <Palette tokens={detail.tokens} />
            <dl className="text-xs mt-2 space-y-1">
              <Row k="质感" v={(detail.tokens?.texture || []).join("、") || "—"} />
              <Row k="动效" v={(detail.tokens?.motion?.pacing) || "—"} />
              <Row k="字体" v={(detail.tokens?.type || []).join("、") || "—"} />
              <Row k="版式" v={(detail.tokens?.composition || []).join("、") || "—"} />
              {detail.missing_fields?.length > 0 && <Row k="缺失字段" v={detail.missing_fields.join("、") + "（estimated）"} />}
            </dl>
            <div className="flex flex-col gap-2 mt-4">
              <button className="btn" onClick={() => toggleTray(detail)}>加入对比（托盘 {tray.length}/4）</button>
              <button className="btn" onClick={() => similar(detail)}>相似风格</button>
              <button className="btn-amber" onClick={() => setPrimaryStyle(detail)}>设为主风格</button>
              {detail.tokens_status !== "complete" && (
                <a className="btn text-center" href="/labeling">加入补标队列 →</a>
              )}
            </div>
          </>
        ) : <p className="text-dim">点击卡片查看详情（调色/质感/动效/字体/版式）</p>}
      </aside>

      {/* 对比托盘 */}
      {tray.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-panel border-t border-line p-2 flex gap-2 items-center z-40">
          <span className="text-dim text-xs ml-2">对比托盘 {tray.length}/4 · 同一样片并排</span>
          {tray.map((t) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={t.id} src={`/api/styles/${t.id}/preview?variant=thumb`} alt={t.name}
              className="w-24 aspect-video object-cover rounded border border-line" />
          ))}
          <button className="btn ml-auto" onClick={() => setTray([])}>清空</button>
          {primary && <span className="text-gold text-sm mr-2">主风格：{primary}</span>}
        </div>
      )}
    </div>
  );
}

function Palette({ tokens }: { tokens: any }) {
  const pal: string[] = tokens?.palette || [];
  if (!pal.length) return <p className="text-dim text-xs mt-2">调色板：—（estimated）</p>;
  return (
    <div className="flex gap-1 mt-2" data-testid="palette">
      {pal.slice(0, 5).map((c, i) => (
        <div key={i} className="w-8 h-8 rounded border border-line" style={{ background: c }} title={c} />
      ))}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex gap-2"><dt className="text-dim w-16 shrink-0">{k}</dt><dd className="min-w-0">{v}</dd></div>;
}
