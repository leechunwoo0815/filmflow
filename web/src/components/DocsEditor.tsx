"use client";
import type { KeyboardEvent } from "react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type DocPayload = {
  kind: string; version: number; hash: string; content: any;
  initialized: boolean; updated_at: string | null; imported: boolean;
};

export default function DocsEditor({ projectId }: { projectId: number }) {
  const [script, setScript] = useState<DocPayload | null>(null);
  const [timeline, setTimeline] = useState<DocPayload | null>(null);
  const [text, setText] = useState("");
  const [baseVersion, setBaseVersion] = useState(0);
  const [status, setStatus] = useState("加载中…");
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState<any>(null);
  const [undoStack, setUndoStack] = useState<string[]>([]);
  const [redoStack, setRedoStack] = useState<string[]>([]);
  const [versions, setVersions] = useState<any[]>([]);
  const [diff, setDiff] = useState<any[] | null>(null);
  const [impact, setImpact] = useState<any>(null);
  const dirtyRef = useRef(false);

  const loadTimeline = useCallback(async () => {
    const t = await api<DocPayload>(`/projects/${projectId}/docs/timeline`);
    setTimeline(t);
  }, [projectId]);

  const loadVersions = useCallback(async () => {
    const r = await api(`/projects/${projectId}/docs/script/versions`);
    setVersions(r.items || []);
  }, [projectId]);

  const loadScript = useCallback(async () => {
    const d = await api<DocPayload>(`/projects/${projectId}/docs/script`);
    setScript(d);
    setText(d.content?.text || "");
    setBaseVersion(d.version);
    dirtyRef.current = false;
    setStatus(d.version ? `文档 v${d.version} · 现有 Run 使用启动快照` : "草稿（尚未保存）");
    await loadTimeline();
    await loadVersions();
  }, [projectId, loadTimeline, loadVersions]);

  useEffect(() => {
    loadScript().catch((e: any) => setStatus(`加载失败：${e.message || e}`));
  }, [loadScript]);

  const save = useCallback(async (value: string) => {
    if (!script) return;
    setSaving(true);
    try {
      const d = await api<DocPayload>(`/projects/${projectId}/docs/script`, {
        method: "PUT",
        body: JSON.stringify({
          content: { schema: "filmflow.script/1", title: script.content?.title || "", text: value },
          base_version: baseVersion,
          author: "editor",
        }),
      });
      setScript(d);
      setText(d.content?.text || "");
      setBaseVersion(d.version);
      dirtyRef.current = false;
      setConflict(null);
      setImpact((d as any).impact || null);
      setStatus(`已保存 v${d.version} · 现有 Run 不变，下次 Run 生效`);
      await loadTimeline();
      await loadVersions();
    } catch (e: any) {
      if (e.status === 409) {
        setConflict(e.details || {});
        setStatus("409 冲突：另一个窗口已保存新版本");
      } else {
        setStatus(`保存失败：${e.message || e}`);
      }
    } finally {
      setSaving(false);
    }
  }, [script, projectId, baseVersion, loadTimeline, loadVersions]);

  useEffect(() => {
    if (!dirtyRef.current) return;
    const timer = setTimeout(() => { void save(text); }, 2000);
    return () => clearTimeout(timer);
  }, [text, save]);

  const change = (value: string) => {
    setUndoStack((s) => [...s.slice(-49), text]);
    setRedoStack([]);
    setText(value);
    dirtyRef.current = true;
    setStatus("编辑中… 2 秒后自动保存");
  };

  const undo = () => {
    if (!undoStack.length) return;
    const prev = undoStack[undoStack.length - 1];
    setUndoStack((s) => s.slice(0, -1));
    setRedoStack((s) => [...s, text]);
    setText(prev);
    dirtyRef.current = true;
  };

  const redo = () => {
    if (!redoStack.length) return;
    const next = redoStack[redoStack.length - 1];
    setRedoStack((s) => s.slice(0, -1));
    setUndoStack((s) => [...s, text]);
    setText(next);
    dirtyRef.current = true;
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    const k = e.key.toLowerCase();
    if (k === "z") {
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
    }
    if (k === "y") { e.preventDefault(); redo(); }
  };

  const showDiff = async (version: number) => {
    try {
      const r = await api(`/projects/${projectId}/docs/script/diff?from_version=${version}&to_version=${baseVersion}`);
      setDiff(r.diff || []);
    } catch (e: any) {
      setStatus(`diff 失败：${e.message || e}`);
    }
  };

  const restore = async (version: number) => {
    try {
      const r = await api<DocPayload>(`/projects/${projectId}/docs/script/restore`, {
        method: "POST",
        body: JSON.stringify({ version, author: "editor" }),
      });
      setScript(r);
      setText(r.content?.text || "");
      setBaseVersion(r.version);
      dirtyRef.current = false;
      setStatus(`已回滚并生成 v${r.version}`);
      await loadTimeline();
      await loadVersions();
    } catch (e: any) {
      setStatus(`回滚失败：${e.message || e}`);
    }
  };

  const rebuild = async () => {
    setSaving(true);
    try {
      await save(text);
      if (dirtyRef.current) {
        setStatus("文案尚未保存成功，未重建场景");
        return;
      }
      const t = await api<DocPayload>(`/projects/${projectId}/docs/timeline/rebuild`, {
        method: "POST",
        body: JSON.stringify({ base_version: timeline?.version ?? 0, author: "editor" }),
      });
      setTimeline(t);
      setStatus(`场景已按文案重建 v${t.version}`);
    } catch (e: any) {
      setStatus(`重建失败：${e.message || e}`);
    } finally {
      setSaving(false);
    }
  };

  const sentences = script?.content?.sentences || [];
  const scenes = timeline?.content?.scenes || [];
  const sceneText = (s: any) => {
    const bySpan = (s.source_span || []).map((i: number) => sentences[i]?.text || "").join("");
    return bySpan || s.meaning || "（无文字）";
  };

  if (!script) return <main className="p-8 text-dim">加载文档…</main>;

  return (
    <main className="max-w-7xl mx-auto p-6">
      <header className="flex items-center gap-2 mb-4">
        <Link className="btn" href={`/canvas?project=${projectId}`}>← Canvas</Link>
        <h1 className="text-xl font-bold">文档编辑</h1>
        <span className="text-dim text-sm">FR-25 · 自动保存 / 撤销 / 版本 / 冲突检测</span>
        <div className="ml-auto flex gap-2">
          <button className="btn" onClick={undo} disabled={!undoStack.length}>撤销</button>
          <button className="btn" onClick={redo} disabled={!redoStack.length}>重做</button>
          <button className="btn" onClick={rebuild} disabled={saving}>按文案重建场景</button>
          <button className="btn-primary" onClick={() => void save(text)} disabled={saving}>
            {saving ? "保存中…" : `保存 v${baseVersion + 1}`}
          </button>
        </div>
      </header>

      <div className="card p-2 mb-3 text-sm text-dim">
        {status}
        {impact && (
          <span className="ml-3 text-gold">
            影响预估：{impact.nodes?.length || 0} 节点 / {impact.gates?.length || 0} 门（下次 Run）
          </span>
        )}
      </div>

      {conflict && (
        <div className="card border-red/40 p-3 mb-3 text-sm">
          <b className="text-red">版本冲突</b>：服务端当前 v{conflict.current_version}。
          <span className="text-dim"> 你的内容未丢失；请先重新加载，再合并。</span>
          <button className="btn ml-2" onClick={() => void loadScript()}>重新加载最新版本</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <section className="card p-3">
          <h2 className="font-semibold mb-2">文案（script.doc）</h2>
          <textarea
            className="w-full h-80 font-mono text-sm"
            value={text}
            onChange={(e) => change(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入文案；句号/问号/分号后自动断句，场景由 source_span 指向句子。"
          />
          <p className="text-dim text-xs mt-2">
            句数 {sentences.length} · 字符 {text.replace(/\s/g, "").length} · 自动保存 2s · Cmd/Ctrl+Z 撤销
          </p>
        </section>

        <section className="card p-3">
          <h2 className="font-semibold mb-2">场景（timeline.doc）</h2>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-xs">
              <thead className="text-dim"><tr>
                <th className="text-left p-1">ID</th><th className="text-left p-1">start</th>
                <th className="text-left p-1">end</th><th className="text-left p-1">source_span</th>
                <th className="text-left p-1">画面文字</th>
              </tr></thead>
              <tbody>
                {scenes.map((s: any) => (
                  <tr key={s.id} className="border-t border-line">
                    <td className="p-1 font-mono">{s.id}</td>
                    <td className="p-1">{s.start}</td>
                    <td className="p-1">{s.end}</td>
                    <td className="p-1 font-mono">{JSON.stringify(s.source_span || [])}</td>
                    <td className="p-1">{sceneText(s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-dim text-xs mt-2">时间轴手动编辑在 R3；当前场景结构由文案自动生成。</p>
        </section>
      </div>

      <section className="card p-3 mt-4">
        <h2 className="font-semibold mb-2">版本历史（script.doc）</h2>
        <div className="flex flex-wrap gap-2 mb-2">
          {versions.map((v) => (
            <span key={v.version} className="inline-flex gap-1">
              <button className="btn text-xs" onClick={() => void showDiff(v.version)}>
                v{v.version} · {v.author}
              </button>
              <button className="btn text-xs" onClick={() => void restore(v.version)}>回滚</button>
            </span>
          ))}
          {!versions.length && <span className="text-dim text-sm">尚无保存版本</span>}
        </div>
        {diff && (
          <div className="text-xs">
            <div className="text-dim mb-1">当前版本与所选版本的差异（前 20 条）：</div>
            {diff.length === 0 && <div className="text-green">无差异</div>}
            <ul className="space-y-1">
              {diff.slice(0, 20).map((d: any, i: number) => (
                <li key={i} className="font-mono">
                  <span className="text-gold">{d.path}</span>：
                  <span className="text-red">{JSON.stringify(d.from)}</span> →
                  <span className="text-green">{JSON.stringify(d.to)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}
