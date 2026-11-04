export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail: any = {};
    try {
      detail = (await res.json())?.detail || {};
      // 兜底：数组形态（FastAPI 原生 422）没有 message，用第一条错误拼出来
      if (Array.isArray(detail)) {
        const first = detail[0] || {};
        detail = { code: "E_VALIDATION",
          message: `${(first.loc || []).slice(1).join(".") || "请求体"}: ${first.msg || res.status}`,
          details: { errors: detail } };
      }
    } catch {}
    const err: any = new Error(detail.message || `${res.status}`);
    err.status = res.status;
    err.code = detail.code;
    err.details = detail.details;
    throw err;
  }
  return res.json();
}

export type StyleDTO = {
  id: string; name: string; collection: string; family: string;
  sub_families: string[]; tokens_status: string; preview_status: string;
  engine_status: string; has_cover: boolean; available: boolean; labeled: boolean;
  missing_fields: string[]; tokens: any; sha256: string; path: string;
};

export const FAMILY_LABELS: Record<string, string> = {
  print: "印刷/丝网", collage: "拼贴/档案", handdrawn: "手绘/笔触", cartoon: "卡通/角色",
  pixel: "像素/游戏", threedee: "3D/渲染", photo: "摄影/电影", ink: "东方/水墨",
  infographic: "信息图/实验", uncategorized: "未分类",
};

export function cornerBadge(s: StyleDTO): { label: string; cls: string } | null {
  if (s.engine_status === "unavailable") return { label: "引擎未就绪", cls: "border-dim/40 text-dim" };
  if (s.tokens_status !== "complete") return { label: "待补标", cls: "border-gold/50 text-gold" };
  if (s.preview_status === "no_preview" || s.preview_status === "failed")
    return { label: "无预演", cls: "border-dim/40 text-dim" };
  return { label: "可生产", cls: "border-green/50 text-green" };
}

export function badges3(s: StyleDTO): string[] {
  const out: string[] = [];
  const t = s.tokens || {};
  const typeStr = (t.type || []).join(" ");
  if ((t.type || []).length || /黑体|900|Noto|bold/i.test(typeStr) || /[\u4e00-\u9fff]/.test(s.name)) out.push("中文友好");
  if ((t.motion || {}).pacing === "fast" || (t.motion || {}).pacing === "medium") out.push("动态强");
  if (s.family === "print" || s.family === "collage") out.push("版式友好");
  return out.slice(0, 3);
}

export function visualOneLine(s: StyleDTO): string {
  const t = s.tokens || {};
  const parts: string[] = [];
  if (t.texture?.length) parts.push(t.texture.slice(0, 2).join("·"));
  if (t.composition?.length) parts.push(t.composition[0]);
  if (t.motion?.pacing) {
    const pacingLabel: Record<string, string> = { slow: "慢速", medium: "中速", fast: "快节奏" };
    parts.push(pacingLabel[t.motion.pacing as string] || String(t.motion.pacing));
  }
  return parts.join(" · ").slice(0, 18) || "—";
}
