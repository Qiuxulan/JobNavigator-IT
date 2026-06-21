/* eslint-disable react-refresh/only-export-components */
import { Ic } from "./Icons";

const TREND_MAP: Record<string, [string, React.FC<React.SVGProps<SVGSVGElement>>, string]> = {
  up: ["up", Ic.up, "上升"],
  down: ["down", Ic.down, "下降"],
  flat: ["flat", Ic.flat, "平稳"],
};

const CAT_COLORS: Record<string, string> = {
  "Emerging AI": "#5B8DEF",
  "AI & Data": "#9B72F0",
  "Backend Development": "#1FC8A9",
  "Frontend & Mobile": "#FFB13D",
  "Cloud & DevOps": "#33CFD5",
  Cybersecurity: "#FF7A90",
  "Data Engineering": "#8A72F0",
  "Product & Design": "#FF9466",
  "QA & Testing": "#6E8AFF",
  "Systems & Embedded": "#86CB3C",
  Management: "#FF6FA5",
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
      {category}
    </span>
  );
}
