"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

const CAT_LABEL: Record<string, string> = {
  text_overflow: "文案读时", font_missing: "字体缺字", black_frame: "黑帧",
  missing_frame: "缺帧", motion_spike: "运动突变", static_too_long: "静态过长",
  lufs_out: "响度", tp_out: "真峰", sync_out: "同步偏差",
  license_missing: "许可缺失", engine_unavailable: "引擎不可用",
  missing_asset: "资产缺失", qa_generic: "QA 失败",
};

function withIds(href: string, pid: number, rid: string) {
  return (href || "").replace("{projectId}", String(pid)).replace("{runId}", rid || "");
}

function QaInner() {
  const params = useSearchParams();
  const projectId = Number(params.get("project") || 0);
  const runId = params.get("run") || "";
  const [qa, setQa] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    const q = runId ? `?runId=${runId}` : "";
    const [a, b] = await Promise.all([
      api<any>(`/projects/${projectId}/qa${q}`),
      api<any>(`/projects/${projectId}/qa/report`),
    ]);
    setQa(a); setReport(b);
  }, [projectId, runId]);
  useEffect(() => { load().catch((e) => setMsg(String(e.message || e))); }, [load]);

  const doFix = async (issue: any, s: any) => {
    let payload = { ...(s.params || {}) };
    if (s.action === "fill_license") {
      const source = prompt("许可来源（必填，如 自制 / 购买订单号 / 素材库账号）");
      if (source === null) return;
      const license = prompt("许可类型（必填，如 CC0 / OFL-1.1 / 商业授权）");
      if (license === null) return;
      const expires = prompt("到期日（可留空，ISO 日期，如 2099-12-31）") || "";
      if (prompt("确认你已核实上述许可允许本片商用发布？输入 YES 确认") !== "YES") {
        setMsg("未确认授权，已取消填写许可");
        return;
      }
      payload = { source, license, expires, authorized: true };
    }
    setBusy(true); setMsg("");
    try {
      const r = await api<any>(`/projects/${projectId}/qa/fix`, {
        method: "POST", body: JSON.stringify({
          issueId: issue.id, action: s.action, payload,
          runId: runId ? Number(runId) : undefined,
        }),
      });
      setQa(r.qa);
      setReport(await api<any>(`/projects/${projectId}/qa/report`));
      setMsg(r.fix?.verified === true ? "已修复并即时验证" :
        r.fix?.verified === false ? "已执行，但问题仍存在" : "已执行；需要下一次 Run 验证");
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  };

  const undo = async (id: string) => {
    setBusy(true); setMsg("");
    try {
      const r = await api<any>(`/projects/${projectId}/qa/undo`, {
        method: "POST", body: JSON.stringify({ fixId: id }),
      });
      setQa(r.qa);
      setReport(await api<any>(`/projects/${projectId}/qa/report`));
      setMsg("已撤销修复");
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  };

  const issues = qa?.issues || [];
  const summary = qa?.summary || {};
  const fixes = useMemo(() => (report?.items || []).slice().reverse(), [report]);

  if (!projectId) return <main className="p-8">缺 project 参数</main>;
  return (
    <main className="min-h-screen max-w-5xl mx-auto p-6 bg-bg text-txt">
      <header className="flex items-center gap-2 mb-4">
        <a className="btn" href={`/canvas?project=${projectId}${runId ? `&run=${runId}` : ""}`}>← 画布</a>
        <h1 className="text-xl font-bold">QA 修复建议</h1>
        <span className="text-dim text-xs">项目 {projectId}{qa?.runId ? ` · Run ${qa.runId}` : ""}</span>
        <div className="ml-auto flex gap-2">
          <a className="btn" href={`/timeline?project=${projectId}`}>时间轴</a>
          <a className="btn" href={`/audio?project=${projectId}`}>音频</a>
          <button className="btn" onClick={() => load()}>刷新</button>
        </div>
      </header>
      {msg && <div className="card border-gold/40 p-2 text-sm text-gold mb-3">{msg}</div>}
      <div className="grid grid-cols-4 gap-2 mb-4 text-sm">
        <div className="card p-3">问题 <b>{summary.total ?? 0}</b></div>
        <div className="card p-3 text-red">错误 <b>{summary.error ?? 0}</b></div>
        <div className="card p-3 text-gold">警告 <b>{summary.warning ?? 0}</b></div>
        <div className="card p-3 text-green">可自动修复 <b>{summary.fixable ?? 0}</b></div>
      </div>
      <div className="space-y-3">
        {issues.map((issue: any) => (
          <div key={issue.id} className="card p-3" data-testid={`qa-issue-${issue.category}`}>
            <div className="flex items-start gap-2">
              <span className={`chip ${issue.severity === "error" ? "border-red/60 text-red" : "border-gold/50 text-gold"}`}>
                {issue.severity === "error" ? "错误" : "警告"}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold">{issue.title} <span className="text-dim text-xs">{CAT_LABEL[issue.category] || issue.category}</span></div>
                <div className="text-sm text-dim mt-0.5">{issue.reason}</div>
                <div className="text-[11px] text-dim mt-1">
                  位置：{issue.location.sceneId || issue.location.nodeId || "项目"}
                  {issue.location.frame !== null && issue.location.frame !== undefined ? ` · 帧 ${issue.location.frame}` : ""}
                  {issue.location.layerId ? ` · 图层 ${issue.location.layerId}` : ""}
                  {" · "}预计 {issue.impact?.seconds ?? "?"}s · 节点 {(issue.impact?.nodes || []).join("/") || "—"}
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(issue.suggestions || []).map((s: any) => (
                    (s.kind === "auto" || s.kind === "confirm") ? (
                      <button key={s.action} className={s.kind === "confirm" ? "btn" : "btn-primary"} disabled={busy}
                        data-testid={`qa-fix-${issue.category}-${s.action}`}
                        onClick={() => doFix(issue, s)}>{s.label}</button>
                    ) : (
                      <a key={s.action} className="btn" href={withIds(s.href, projectId, runId)}>{s.label}</a>
                    )
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
        {!issues.length && <div className="card p-6 text-green">当前没有 QA 问题。</div>}
      </div>
      <section className="mt-6">
        <h2 className="font-semibold mb-2">修复记录</h2>
        <div className="text-xs text-dim mb-2">
          尝试 {report?.attempts ?? 0} · 已应用 {report?.applied ?? 0}（当前有效 {report?.active ?? 0}）·
          即时验证 {report?.verified ?? 0} · 未验证 {report?.unverified ?? 0} ·
          撤销 {report?.undone ?? 0} · 成功率 {report?.successRate == null ? "—" : `${Math.round(report.successRate * 100)}%`}
          <span className="ml-2">误报率：需下一次成功 Run 后复核</span>
        </div>
        <div className="space-y-1">
          {fixes.map((f: any) => (
            <div key={f.id} className="card p-2 text-xs flex items-center gap-2">
              <span className={f.undone ? "text-dim line-through" : f.verified === false ? "text-gold" : "text-green"}>
                {f.action} · {f.category} · {f.verified === true ? "已验证" : f.verified === false ? "仍存在" : "待验证"}
              </span>
              <span className="text-dim">{f.at?.slice(0, 19)}</span>
              {!f.undone && f.before && <button className="btn ml-auto" onClick={() => undo(f.id)}>撤销</button>}
              {f.undone && <span className="ml-auto text-dim">已撤销</span>}
            </div>
          ))}
          {!fixes.length && <div className="text-dim text-sm">还没有修复记录。</div>}
        </div>
      </section>
    </main>
  );
}

export default function QaPage() {
  return <Suspense><QaInner /></Suspense>;
}
