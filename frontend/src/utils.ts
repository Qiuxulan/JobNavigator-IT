export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-US");
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export interface ConfidenceInfo {
  label: string;
  className: string;
}

export function confidenceInfo(confidence: number | null | undefined): ConfidenceInfo {
  const c = confidence ?? 0;
  if (c >= 0.5) return { label: "高置信", className: "conf-high" };
  if (c >= 0.3) return { label: "中置信", className: "conf-mid" };
  return { label: "低置信", className: "conf-low" };
}

const MODEL_LABELS: Record<string, string> = {
  holt: "Holt 线性趋势",
  theta: "Theta 分解",
  ets: "ETS 指数平滑",
  patchtst: "PatchTST 深度模型",
  naive: "朴素基线",
  insufficient_data: "数据不足（未建模）",
};

export function modelLabel(name: string | null | undefined): string {
  if (!name) return "—";
  return MODEL_LABELS[name] || name;
}

const SENIORITY_LABELS: Record<string, string> = {
  internship: "实习",
  junior: "初级",
  mid: "中级",
  senior: "高级",
  lead: "负责人",
};

export function seniorityLabel(key: string): string {
  return SENIORITY_LABELS[key] || key;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  general: "行业动态",
  hiring: "招聘动态",
  product_release: "产品发布",
  model_release: "模型发布",
  platform_release: "平台发布",
  market_research: "市场研究",
  regulation: "政策监管",
  funding: "投融资",
  security_incident: "安全事件",
  ai_coding_agent: "AI 编程工具",
};

export function eventTypeLabel(type: string | null | undefined): string {
  if (!type) return "行业动态";
  return EVENT_TYPE_LABELS[type] || type;
}
