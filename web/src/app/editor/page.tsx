"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useLang, LangToggle } from "@/lib/i18n";
import { ThemeToggle } from "@/lib/theme";

function EditorInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const projectId = Number(params.get("project"));
  const [task, setTask] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    api(`/projects/${projectId}/task`).then((r) => {
      if (r.exists) setTask(r.task);
      else setTask({ schema_version: 1, task_id: `p${projectId}`, phase: "card", actions: ["read", "write_plan", "logic_check"],
                     fps: 24, width: 1920, height: 1080, scenes: [], events: [], film: {}, evidence: [] });
    }).catch((e) => setMsg(String(e)));
  }, [projectId]);

  const save = async () => {
    try {
      await api(`/projects/${projectId}/task`, { method: "PUT", body: JSON.stringify({ task }) });
      setMsg("✓ 已保存 card/task.json");
    } catch (e: any) { setMsg(e.message); }
  };

  const validate = async () => {
    try { setReport(await api(`/projects/${projectId}/validate`, { method: "POST", body: "{}" })); }
    catch (e: any) { setMsg(e.message); }
  };

  if (!task) return <main className="p-8 text-dim">加载中…</main>;

  const updScene = (i: number, k: string, v: any) => {
    const scenes = [...task.scenes]; scenes[i] = { ...scenes[i], [k]: v }; setTask({ ...task, scenes });
  };
  const updEvent = (i: number, k: string, v: any) => {
    const events = [...task.events]; events[i] = { ...events[i], [k]: v }; setTask({ ...task, events });
  };
  const addScene = () => {
    const n = task.scenes.length;
    const start = n === 0 ? 0 : task.scenes[n - 1].end;
    setTask({ ...task, scenes: [...task.scenes, { id: `S${String(n + 1).padStart(2, "0")}`, start, end: start + 5,
      time_basis: "planned", meaning: "", operation: "", last_text_at: start, read_seconds: 2 }] });
  };

  return (
    <main className="max-w-6xl mx-auto p-6">
      <header className="flex items-center gap-2 mb-4">
        <a className="btn" href={`/canvas?project=${projectId}`}>← Canvas</a><LangToggle /><ThemeToggle />
        <h1 className="text-xl font-bold">{t("ed.title")}</h1>
        <span className="text-dim text-sm">{t("ed.disclaimer")}</span>
        <div className="ml-auto flex gap-2">
          <button className="btn" onClick={addScene}>{t("ed.addScene")}</button>
          <button className="btn" onClick={save}>{t("ed.save")}</button>
          <button className="btn-primary" onClick={validate}>{t("ed.validate")}</button>
        </div>
      </header>
      {msg && <div className="card border-green/40 p-2 mb-3 text-green text-sm">{msg}</div>}

      <section className="card p-3 mb-4">
        <h2 className="font-semibold mb-2">{t("ed.basic")}</h2>
        <div className="grid grid-cols-4 gap-3 text-sm">
          <label className="block"><span className="text-dim text-xs">task_id</span>
            <input className="w-full mt-1" value={task.task_id || ""} onChange={(e) => setTask({ ...task, task_id: e.target.value })} /></label>
          <label className="block"><span className="text-dim text-xs">phase</span>
            <select className="w-full mt-1" value={task.phase} onChange={(e) => setTask({ ...task, phase: e.target.value })}>
              {["card", "still", "audition", "final"].map((p) => <option key={p}>{p}</option>)}
            </select></label>
          <label className="block"><span className="text-dim text-xs">fps</span>
            <input className="w-full mt-1" type="number" value={task.fps || 24} onChange={(e) => setTask({ ...task, fps: +e.target.value })} /></label>
          <label className="block"><span className="text-dim text-xs">actions（逗号分隔）</span>
            <input className="w-full mt-1" value={(task.actions || []).join(",")} onChange={(e) => setTask({ ...task, actions: e.target.value.split(",").map((s: string) => s.trim()) })} /></label>
        </div>
      </section>

      <section className="card p-3 mb-4">
        <h2 className="font-semibold mb-2">{t("ed.scenes")}{task.scenes.length}）</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-dim"><tr>
              {["ID", "start", "end", "meaning", "operation", "last_text_at", "read_seconds", "camera", "transition"].map((h) => <th key={h} className="text-left p-1">{h}</th>)}
            </tr></thead>
            <tbody>
              {task.scenes.map((s: any, i: number) => (
                <tr key={i} className="border-t border-line">
                  <td className="p-1 font-mono">{s.id}</td>
                  {(["start", "end", "last_text_at", "read_seconds"] as const).map((k) => (
                    <td key={k} className="p-1"><input className="w-16" type="number" step="0.1" value={s[k] ?? 0} onChange={(e) => updScene(i, k, +e.target.value)} /></td>
                  ))}
                  <td className="p-1"><input className="w-44" value={s.meaning || ""} onChange={(e) => updScene(i, "meaning", e.target.value)} /></td>
                  <td className="p-1"><input className="w-64" value={s.operation || ""} onChange={(e) => updScene(i, "operation", e.target.value)} /></td>
                  <td className="p-1"><input className="w-32" value={s.camera || ""} onChange={(e) => updScene(i, "camera", e.target.value)} /></td>
                  <td className="p-1"><input className="w-32" value={s.transition || ""} onChange={(e) => updScene(i, "transition", e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card p-3 mb-4">
        <h2 className="font-semibold mb-2">{t("ed.events")}{task.events.length}）</h2>
        <div className="overflow-x-auto max-h-48 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="text-dim"><tr>{["id", "scene_id", "at", "role", "allow_snap", "tolerance"].map((h) => <th key={h} className="text-left p-1">{h}</th>)}</tr></thead>
            <tbody>
              {task.events.map((e: any, i: number) => (
                <tr key={i} className="border-t border-line">
                  <td className="p-1 font-mono">{e.id}</td>
                  <td className="p-1"><input className="w-16" value={e.scene_id || ""} onChange={(ev) => updEvent(i, "scene_id", ev.target.value)} /></td>
                  <td className="p-1"><input className="w-16" type="number" step="0.1" value={e.at ?? 0} onChange={(ev) => updEvent(i, "at", +ev.target.value)} /></td>
                  <td className="p-1"><input className="w-40" value={e.role || ""} onChange={(ev) => updEvent(i, "role", ev.target.value)} /></td>
                  <td className="p-1"><input type="checkbox" checked={!!e.allow_snap} onChange={(ev) => updEvent(i, "allow_snap", ev.target.checked)} /></td>
                  <td className="p-1"><input className="w-16" type="number" step="0.05" value={e.tolerance ?? 0.1} onChange={(ev) => updEvent(i, "tolerance", +ev.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {report && (
        <section className={`card p-3 ${report.passed ? "border-green/40" : "border-red/40"}`}>
          <h2 className="font-semibold mb-1">{report.passed ? t("ed.reportPass") : t("ed.reportFail")}</h2>
          {report.errors?.length > 0 && (
            <ul className="text-red text-sm list-disc ml-4">{report.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul>
          )}
        </section>
      )}
    </main>
  );
}

export default function EditorPage() {
  return <Suspense><EditorInner /></Suspense>;
}
