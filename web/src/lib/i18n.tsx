"use client";
/**
 * i18n 脚手架（DoD §15.8）：zh 默认全量 + en 词典。
 * 用法：const { t, lang, setLang } = useLang();  <LangToggle />
 * 切换持久化在 localStorage("ff.lang")。
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Lang = "zh" | "en";

const DICT: Record<string, { zh: string; en: string }> = {
  // 通用
  "app.title": { zh: "FilmFlow", en: "FilmFlow" },
  "app.subtitle": { zh: "· 印厂控制台", en: " · Print-shop Console" },
  "app.tagline": { zh: "代码动画全生命周期工作台 · 46 节点 / 7 阶段 / 341 条风格库", en: "Code-animation lifecycle workbench · 46 nodes / 7 stages / 341 styles" },
  "nav.newProject": { zh: "＋ 新建项目向导", en: "＋ New Project Wizard" },
  "nav.labeling": { zh: "补标队列", en: "Labeling Queue" },
  "nav.back": { zh: "← 项目", en: "← Projects" },
  "nav.editor": { zh: "任务卡编辑器", en: "Task Card Editor" },
  // 首页
  "home.import": { zh: "导入项目（含 task.json）", en: "Import Project (with task.json)" },
  "home.importBtn": { zh: "导入 rumor-39s", en: "Import rumor-39s" },
  "home.importHint": { zh: "导入后画布为 46 节点只读视图，状态来自真实文件。", en: "Imported canvas is a read-only 46-node view; states come from real files." },
  "home.projects": { zh: "项目", en: "Projects" },
  "home.noProjects": { zh: "暂无项目——先导入参考项目，或走新建向导。", en: "No projects yet — import the reference project or run the wizard." },
  "home.stat.styles": { zh: "风格库", en: "Style Library" },
  "home.stat.stylesSub": { zh: "10 来源集 · 可生产", en: "10 collections · producible" },
  "home.stat.labelQueue": { zh: "补标队列", en: "Label Queue" },
  "home.stat.labelSub": { zh: "tokens 残缺 · 不可主选", en: "incomplete tokens · not primary-selectable" },
  "home.stat.env": { zh: "环境", en: "Environment" },
  "home.stat.envReady": { zh: "就绪", en: "Ready" },
  // 向导
  "wiz.title": { zh: "新建项目", en: "New Project" },
  "wiz.disclaimer": { zh: "本应用不生成剧本/场景，只校验与编排。", en: "This app does not generate scripts/scenes; it validates and orchestrates only." },
  "wiz.step1": { zh: "文案", en: "Copy" },
  "wiz.step2": { zh: "画幅与时长", en: "Frame & Duration" },
  "wiz.step3": { zh: "选整体风格", en: "Pick Style" },
  "wiz.step4": { zh: "声音方案", en: "Voice Plan" },
  "wiz.step5": { zh: "生成工作流", en: "Generate Workflow" },
  "wiz.copyTitle": { zh: "① 文案（粘贴/上传）", en: "① Copy (paste/upload)" },
  "wiz.copyPh": { zh: "粘贴或输入口播文案……", en: "Paste or type narration copy…" },
  "wiz.chars": { zh: "字数", en: "chars" },
  "wiz.sentences": { zh: "句数", en: "sentences" },
  "wiz.estDuration": { zh: "按 5.2 字/秒 预估口播", en: "est. narration at 5.2 chars/s" },
  "wiz.next": { zh: "下一步", en: "Next" },
  "wiz.prev": { zh: "上一步", en: "Back" },
  "wiz.frameTitle": { zh: "② 画幅与时长", en: "② Frame & Duration" },
  "wiz.width": { zh: "宽", en: "Width" },
  "wiz.height": { zh: "高", en: "Height" },
  "wiz.duration": { zh: "时长(s)", en: "Duration(s)" },
  "wiz.framesCalc": { zh: "帧数 = round(时长 × fps) =", en: "frames = round(duration × fps) =" },
  "wiz.styleTitle": { zh: "③ 选整体风格（341 条全库）", en: "③ Pick Style (all 341)" },
  "wiz.stylePicked": { zh: "已选主风格", en: "Primary picked:" },
  "wiz.stylePickFirst": { zh: "先设为主风格", en: "Pick a primary style first" },
  "wiz.voiceTitle": { zh: "④ 声音方案", en: "④ Voice Plan" },
  "wiz.genTitle": { zh: "⑤ 生成工作流", en: "⑤ Generate Workflow" },
  "wiz.summaryCopy": { zh: "文案：", en: "Copy: " },
  "wiz.summaryFrame": { zh: "画幅：", en: "Frame: " },
  "wiz.summaryPrimary": { zh: "主风格：", en: "Primary: " },
  "wiz.summaryAlt": { zh: "备选", en: "alternates" },
  "wiz.summaryVoice": { zh: "声音：", en: "Voice: " },
  "wiz.summaryNodes": { zh: "将生成 46 节点画布 · A05 门已按你的选择记录批准", en: "Will generate the 46-node canvas · A05 gate recorded as approved per your pick" },
  "wiz.generate": { zh: "生成工作流 →", en: "Generate Workflow →" },
  "wiz.generating": { zh: "生成中…", en: "Generating…" },
  // 风格选择器
  "style.searchPh": { zh: "搜索 风格/ID/关键词（支持同义词：水墨↔中国风）", en: "Search style/ID/keyword (synonyms supported)" },
  "style.shuffle": { zh: "换一批", en: "Shuffle" },
  "style.random": { zh: "随机", en: "Random" },
  "style.recommend": { zh: "推荐（按文案匹配度）", en: "Recommended (by copy match)" },
  "style.loading": { zh: "加载中…", en: "Loading…" },
  "style.railFamily": { zh: "语义族 9", en: "Families 9" },
  "style.railCollection": { zh: "来源集 10", en: "Collections 10" },
  "style.matrixNote": { zh: "实测矩阵（ADR-0002）", en: "Measured matrix (ADR-0002)" },
  "style.tray": { zh: "对比托盘", en: "Compare Tray" },
  "style.traySameSample": { zh: "同一样片并排", en: "same sample side-by-side" },
  "style.clear": { zh: "清空", en: "Clear" },
  "style.primary": { zh: "主风格：", en: "Primary: " },
  "style.addToTray": { zh: "加入对比（托盘", en: "Add to tray (" },
  "style.similar": { zh: "相似风格", en: "Similar" },
  "style.setPrimary": { zh: "设为主风格", en: "Set as Primary" },
  "style.toLabeling": { zh: "加入补标队列 →", en: "Send to labeling queue →" },
  "style.detailHint": { zh: "点击卡片查看详情（调色/质感/动效/字体/版式）", en: "Click a card for details (palette/texture/motion/type/layout)" },
  "style.missing": { zh: "缺失字段", en: "Missing fields" },
  // 画布
  "cv.run": { zh: "▶ Run", en: "▶ Run" },
  "cv.step": { zh: "Step", en: "Step" },
  "cv.cancel": { zh: "取消", en: "Cancel" },
  "cv.resume": { zh: "Resume", en: "Resume" },
  "cv.retry": { zh: "Retry failed", en: "Retry failed" },
  "cv.pendingGates": { zh: "等待批准的门（", en: "Gates awaiting approval (" },
  "cv.approve": { zh: "批准", en: "Approve" },
  "cv.reject": { zh: "驳回", en: "Reject" },
  "cv.rejectPrompt": { zh: "驳回必须填写意见：", en: "Rejection requires a note:" },
  "cv.humanGate": { zh: "人工门", en: "Human gate" },
  "cv.autoGate": { zh: "自动门", en: "Auto gate" },
  "cv.artifacts": { zh: "产物", en: "Artifacts" },
  "cv.clickNode": { zh: "点击节点查看状态/日志/产物", en: "Click a node for status/logs/artifacts" },
  // 补标
  "lb.title": { zh: "补标队列", en: "Labeling Queue" },
  "lb.pending": { zh: "条待补", en: " pending" },
  "lb.hint": { zh: "每条补 6 字段 + 语义族；完成后解锁为主选候选（解析失败全集，含 A-G 17 条）。", en: "Fill 6 fields + family per style; completion unlocks primary-selection (parse-failure full set incl. 17 in A-G)." },
  "lb.submit": { zh: "提交补标并解锁", en: "Submit & Unlock" },
  "lb.queueEmpty": { zh: "队列空——全部 341 条都齐了。", en: "Queue empty — all 341 styles are labeled." },
  // 编辑器
  "ed.title": { zh: "任务卡编辑器", en: "Task Card Editor" },
  "ed.disclaimer": { zh: "四表三面板 · 本应用不生成剧本/场景，只校验与编排", en: "Four tables, three panels · no script generation; validation & orchestration only" },
  "ed.save": { zh: "保存", en: "Save" },
  "ed.validate": { zh: "校验（B07 同一验证器）", en: "Validate (same as B07)" },
  "ed.addScene": { zh: "＋ 场景", en: "＋ Scene" },
  "ed.basic": { zh: "基本信息", en: "Basics" },
  "ed.scenes": { zh: "① 场景表（", en: "① Scenes (" },
  "ed.events": { zh: "② 事件表（", en: "② Events (" },
  "ed.reportPass": { zh: "校验报告：✓ 通过", en: "Validation: ✓ passed" },
  "ed.reportFail": { zh: "校验报告：✗ 未通过", en: "Validation: ✗ failed" },
  // 监控
  "mo.title": { zh: "监控 / 审计", en: "Monitor / Audit" },
  "mo.export": { zh: "导出报告 JSON", en: "Export report JSON" },
  "mo.audit": { zh: "审计日志", en: "Audit Log" },
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, extra?: string) => string };
const LangCtx = createContext<Ctx>({ lang: "zh", setLang: () => {}, t: (k) => k });

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("zh");
  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem("ff.lang") as Lang | null : null;
    if (saved === "en" || saved === "zh") setLangState(saved);
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { window.localStorage.setItem("ff.lang", l); } catch {}
  }, []);
  const t = useCallback((key: string, extra?: string) => {
    const entry = DICT[key];
    const base = entry ? entry[lang] : key;
    return extra !== undefined ? `${base}${extra}` : base;
  }, [lang]);
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export function useLang() {
  return useContext(LangCtx);
}

export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="flex rounded border border-line overflow-hidden text-xs">
      {(["zh", "en"] as Lang[]).map((l) => (
        <button key={l} onClick={() => setLang(l)}
          className={`px-2 py-1 ${lang === l ? "bg-blue/20 text-blue" : "text-dim hover:text-txt"}`}>
          {l === "zh" ? "中" : "EN"}
        </button>
      ))}
    </div>
  );
}
