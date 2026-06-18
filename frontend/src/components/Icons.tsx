/* eslint-disable react-refresh/only-export-components */
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

const base: P = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" };

export const Ic = {
  dash: (p: P) => <svg {...base} {...p}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>,
  compare: (p: P) => <svg {...base} {...p}><path d="M3 6h7M3 12h12M3 18h5"/><circle cx="18" cy="6" r="2"/><circle cx="20" cy="12" r="2"/><circle cx="12" cy="18" r="2"/></svg>,
  graph: (p: P) => <svg {...base} {...p}><circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="7" r="2.4"/><circle cx="12" cy="17" r="2.4"/><circle cx="5" cy="17" r="1.8"/><path d="M8 7l8 0.6M7.5 8L11 15M16.5 9L13 15M7 16h3"/></svg>,
  chat: (p: P) => <svg {...base} {...p}><path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 13h5"/></svg>,
  search: (p: P) => <svg {...base} strokeWidth={1.9} {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>,
  up: (p: P) => <svg {...base} strokeWidth={2.1} {...p}><path d="M3 17 9 11l4 4 8-8"/><path d="M15 4h6v6"/></svg>,
  down: (p: P) => <svg {...base} strokeWidth={2.1} {...p}><path d="M3 7 9 13l4-4 8 8"/><path d="M15 20h6v-6"/></svg>,
  flat: (p: P) => <svg {...base} strokeWidth={2.1} {...p}><path d="M3 12h18"/><path d="M16 7l5 5-5 5"/></svg>,
  flame: (p: P) => <svg {...base} {...p}><path d="M12 3c0 3-4 4.5-4 8a4 4 0 0 0 8 0c0-1.5-1-2.5-1-4 2 1 3 3 3 5a6 6 0 0 1-12 0c0-4 4-6 6-9z"/></svg>,
  layers: (p: P) => <svg {...base} {...p}><path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/></svg>,
  back: (p: P) => <svg {...base} strokeWidth={1.9} {...p}><path d="M15 18l-6-6 6-6"/></svg>,
  ext: (p: P) => <svg {...base} {...p}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>,
  send: (p: P) => <svg {...base} strokeWidth={1.9} {...p}><path d="M4 12 20 4l-6 16-3.5-6.5L4 12z"/></svg>,
  spark: (p: P) => <svg {...base} strokeWidth={1.7} {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/></svg>,
  user: (p: P) => <svg {...base} {...p}><circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.3 3-5.5 7-5.5s7 2.2 7 5.5"/></svg>,
  route: (p: P) => <svg {...base} {...p}><circle cx="6" cy="19" r="2.4"/><circle cx="18" cy="5" r="2.4"/><path d="M8 19h6a4 4 0 0 0 4-4V8M16 5h-6a4 4 0 0 0-4 4v8"/></svg>,
  target: (p: P) => <svg {...base} {...p}><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.6" fill="currentColor"/></svg>,
  gap: (p: P) => <svg {...base} {...p}><path d="M9 4v16M15 4v16"/><path d="M4 9h3M4 15h3M17 9h3M17 15h3"/></svg>,
  brain: (p: P) => <svg {...base} strokeWidth={1.7} {...p}><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1 5.5A3 3 0 0 0 7 18a2.5 2.5 0 0 0 5 .5V5.5A2.5 2.5 0 0 0 9 4z"/><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 1 5.5A3 3 0 0 1 17 18a2.5 2.5 0 0 1-5 .5"/></svg>,
};

export function Logo({ accent, style, className }: { accent?: string; style?: React.CSSProperties; className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" style={style} className={className} aria-hidden="true">
      <path d="M16 3.4 L26 28 16 22 Z" fill={accent || "currentColor"} />
      <path d="M16 3.4 L6 28 16 22 Z" fill="currentColor" opacity="0.9" />
    </svg>
  );
}
