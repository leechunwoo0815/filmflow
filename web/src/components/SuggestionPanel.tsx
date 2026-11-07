"use client";
// FR-41：创作辅助的建议草稿层（纯本地规则，零网络）。
//
// "草稿层"三个字是有约束的，不是措辞：**不改用户的原文**，只给出可采纳的结构。
// 所以这里没有"替换文案"这种一键毁灭的按钮，只有：
//   · 看建议（断句 / 4–6 场 / 每场理由 / 组件 / 镜头 / 读时校验）
//   · 逐场采纳 → 只替换草稿里**那一场**，其余原样（PRD FR-41 验收②"接受后只影响对应场景"）
//   · 逐场忽略 → 只改本地候选，不写库、不留痕（验收②的"拒绝不留痕"）
//   · 逐场改停留时长 → 采纳时带的是改过的值（"可编辑"落在时长上；断句级的改写属于时间轴编辑器）
//   · 全部采纳 → 一次性写入未被忽略的场次
// 断网证据：面板不发任何外部请求，`/authoring/suggest` 是本机 API；
// 验收脚本 e2e_fr40_keyboard.py 里用 lsof 快照证明该进程没有对外连接。
import { useState } from "react";

import { api, describeApiError } from "@/lib/api";
import { dispatchAppEvent } from "@/lib/commands";

export interface SuggestionScene {
  id: string; sentences: string[]; suggestedSeconds: number; reason: string;
  kind?: string;
  components?: { keyword: string; component: string; reason: string }[];
  cameraPresets?: Record<string, unknown>[];
  readCheck?: { chars: number; suggestedSeconds: number; givenSeconds: number;
                minReadable: number; verdict: string };
}

export interface Suggestion {
  schema: string; sentences: { text: string; readSeconds: number; chars: number }[];
  scenes: SuggestionScene[]; readCps: number;
}

export function SuggestionPanel({ copy, draftId, brief }:
  { copy: string; draftId: number | null; brief: Record<string, unknown> }) {
  const [data, setData] = useState<Suggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ignored, setIgnored] = useState<Record<string, boolean>>({});
  const [secondsEdit, setSecondsEdit] = useState<Record<string, number>>({});
  // 本面板最后一次写进草稿的场次。没有它，第二次"采纳这一场"会拿挂载时的旧 brief 去合并，
  // 把第一次采纳的那场抹掉——"只影响对应场景"就变成"只影响最后一次"。
  const [pushed, setPushed] = useState<SuggestionScene[] | null>(null);

  const secondsOf = (s: SuggestionScene) => secondsEdit[s.id] ?? s.suggestedSeconds;

  const generate = async () => {
    setBusy(true); setErr("");
    try {
      setData(await api<Suggestion>("/authoring/suggest",
        { method: "POST", body: JSON.stringify({ text: copy }) }));
      setIgnored({}); setSecondsEdit({}); setPushed(null);
    } catch (e) { setErr(describeApiError(e)); } finally { setBusy(false); }
  };

  /** PATCH /drafts 的 payload 是**顶层合并**（routes.py:520），所以 brief 必须自己带上旧键——
   *  只发 {brief:{suggestedScenes}} 会把用户已填的标题整个抹掉。 */
  const writeDraft = async (scenes: SuggestionScene[]) => {
    if (!data || !draftId) return;
    await api(`/drafts/${draftId}`, {
      method: "PATCH",
      body: JSON.stringify({
        payload: { brief: { ...brief, suggestedScenes: scenes, readCps: data.readCps } },
      }),
    });
    setPushed(scenes);
  };

  const adopt = async () => {
    if (!data || !draftId) return;
    setBusy(true); setErr("");
    try {
      const kept = data.scenes.filter((s) => !ignored[s.id])
        .map((s) => ({ ...s, suggestedSeconds: secondsOf(s) }));
      await writeDraft(kept);
      // 回执走 ui:toast：宿主（向导）不该各自实现一套"成功了吗"的呈现方式
      dispatchAppEvent("ui:toast", `已把 ${kept.length} 场建议写入草稿层`
        + `（忽略 ${data.scenes.length - kept.length} 场；原文与标题未改动）`);
    } catch (e) { setErr(describeApiError(e)); } finally { setBusy(false); }
  };

  /** 单场采纳：草稿里同 id 的那场被替换，其余原样——这就是 PRD 的"接受后只影响对应场景"。 */
  const adoptOne = async (s: SuggestionScene) => {
    if (!data || !draftId) return;
    setBusy(true); setErr("");
    try {
      const before = pushed ?? (brief.suggestedScenes as SuggestionScene[] | undefined) ?? [];
      const entry = { ...s, suggestedSeconds: secondsOf(s) };
      const next = before.some((x) => x.id === s.id)
        ? before.map((x) => (x.id === s.id ? entry : x))
        : [...before, entry];
      await writeDraft(next);
      dispatchAppEvent("ui:toast", `已采纳 ${s.id}：草稿里 ${before.length} → ${next.length} 场，其余未动`);
    } catch (e) { setErr(describeApiError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="mt-3 border-t pt-3" data-testid="suggestion-panel">
      <div className="flex items-center gap-2">
        <button className="btn" onClick={() => void generate()} disabled={busy || !copy.trim()}
          data-testid="suggest-generate">生成分场建议</button>
        <span className="text-xs opacity-60">本机规则引擎 · 无外部请求 · 读速 {data?.readCps ?? "—"} 字/秒</span>
      </div>
      {!!err && <p role="alert" className="mt-2 text-sm text-red" data-testid="suggest-error">{err}</p>}

      {data && (
        <div className="mt-3" data-testid="suggest-results">
          <p className="text-sm">
            断句 <b data-testid="suggest-sentence-count">{data.sentences.length}</b> 句 ·
            建议 <b data-testid="suggest-scene-count">{data.scenes.length}</b> 场
            （{" "}
            <button className="underline" data-testid="suggest-adopt" disabled={busy || !draftId}
              onClick={() => void adopt()}>全部采纳到草稿层</button> ，原文不变；下面每场可单独采纳或忽略）
          </p>
          <ol className="mt-2 space-y-2">
            {data.scenes.map((s, i) => (
              <li key={s.id} className="card p-2 text-sm" data-testid={`suggest-scene-${i}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{s.id}</span>
                  <span className="opacity-70">{s.suggestedSeconds.toFixed(1)}s
                    · 读时判定 {s.readCheck?.verdict ?? "—"}</span>
                </div>
                <p className="mt-1 opacity-80">{s.sentences.join("")}</p>
                <p className="mt-1 text-xs opacity-60" data-testid={`suggest-reason-${i}`}>理由：{s.reason}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-1" htmlFor={`suggest-seconds-${i}`}>
                    停留
                    <input id={`suggest-seconds-${i}`} type="number" min={0.5} step={0.5}
                      data-testid={`suggest-scene-seconds-${i}`} value={secondsOf(s)}
                      onChange={(e) => setSecondsEdit((m) => ({ ...m, [s.id]: Number(e.target.value) }))}
                      className="w-20 border border-line bg-panel px-1" />
                    秒
                  </label>
                  <button className="btn" data-testid={`suggest-scene-adopt-${i}`} disabled={busy}
                    onClick={() => void adoptOne(s)}>采纳这一场</button>
                  <button className="btn" aria-pressed={!!ignored[s.id]}
                    data-testid={`suggest-scene-ignore-${i}`} disabled={busy}
                    onClick={() => setIgnored((m) => ({ ...m, [s.id]: !m[s.id] }))}>
                    {ignored[s.id] ? "已忽略（不写入草稿）" : "忽略这一场"}
                  </button>
                </div>
                {!!s.components?.length && (
                  <ul className="mt-1 text-xs opacity-70" aria-label={`${s.id} 建议组件`}>
                    {s.components.map((c, j) => (
                      <li key={`${c.keyword}-${j}`}>「{c.keyword}」→ {c.component}（{c.reason}）</li>
                    ))}
                  </ul>
                )}
                {!!s.cameraPresets?.length && (
                  <p className="mt-1 text-xs opacity-70">
                    镜头建议：{s.cameraPresets.map((p) => JSON.stringify(p)).join(" · ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {!data && !busy && !err && (
        <p className="mt-2 text-xs opacity-60">
          建议只做草稿层参考：分场、组件、镜头、读时校验都可逐条采纳或忽略。
        </p>
      )}
    </div>
  );
}
