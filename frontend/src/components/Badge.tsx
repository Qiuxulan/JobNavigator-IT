import { coarseZh } from "../market";
/* eslint-disable react-refresh/only-export-components */
import { Ic } from "./Icons";

const TREND_MAP: Record<string, [string, React.FC<React.SVGProps<SVGSVGElement>>, string]> = {
  up: ["up", Ic.up, "上升"],
  down: ["down", Ic.down, "下降"],
  flat: ["flat", Ic.flat, "平稳"],
};

const CAT_COLORS: Record<string, string> = {
  "Emerging AI": "#f47254",
  "AI & Data": "#f59c7c",
  "Backend Development": "#67a583",
  "Frontend & Mobile": "#ffc1a6",
  "Cloud & DevOps": "#49c2d9",
  Cybersecurity: "#c85e62",
  "Data Engineering": "#7b95c6",
  "Product & Design": "#fded95",
  "QA & Testing": "#a2c986",
  "Systems & Embedded": "#a1d8e8",
  Management: "#d0e2c0",
};

export function TrendBadge({ trend, withLabel = true }: { trend: string; withLabel?: boolean }) {
  const [cls, I, label] = TREND_MAP[trend] || TREND_MAP.flat;
  return <span className={"badge " + cls}><I />{withLabel ? label : ""}</span>;
}

export function catColor(category: string): string {
  return CAT_COLORS[category] || "#9aa0a9";
}

export function CatBadge({ category }: { category: string }) {
  return (
    <span className="badge cat">
      <span className="dot-cat" style={{ background: catColor(category) }} />
      {coarseZh(category)}
    </span>
  );
}

const MATCH_CONF_MAP: Record<string, [string, string]> = {
  high: ["conf-high", "置信度 高"],
  medium: ["conf-mid", "置信度 中"],
  low: ["conf-low", "置信度 低"],
};

const MATCH_CONF_TIP = "置信度=技能覆盖+语义匹配+命中技能数综合分档";

/** 岗位推荐置信度徽标（/v1/jobs/recommend 的 confidence 字段）；为 null/缺失时不渲染。 */
export function MatchConfidenceBadge({ confidence }: { confidence?: string | null }) {
  if (!confidence) return null;
  const [cls, label] = MATCH_CONF_MAP[confidence] || [];
  if (!cls) return null;
  return (
    <span className={"badge " + cls} title={MATCH_CONF_TIP}>
      {label}
    </span>
  );
}

// 公司雷达状态胶囊（/v1/companies 的 status_tag 字段）
const COMPANY_STATUS_MAP: Record<string, [string, string]> = {
  expanding: ["up", "扩张中"],
  cooling: ["neutral", "降温"],
  stable: ["flat", "平稳"],
  shrinking: ["down", "有裁员备案"],
};

const COMPANY_STATUS_TIP: Record<string, string> = {
  expanding: "近 30 天在招岗位净增、处于扩张通道",
  cooling: "近 30 天在招岗位净减、招聘放缓",
  stable: "近 30 天在招岗位基本持平",
  shrinking: "近 12 个月有 WARN 裁员备案记录",
};

/** 公司招聘状态胶囊；未知/缺失 tag 时不渲染。 */
export function CompanyStatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const [cls, label] = COMPANY_STATUS_MAP[status] || [];
  if (!cls) return null;
  return (
    <span className={"badge " + cls} title={COMPANY_STATUS_TIP[status]}>
      {label}
    </span>
  );
}
