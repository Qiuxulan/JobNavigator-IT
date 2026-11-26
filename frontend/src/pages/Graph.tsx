import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getGraph } from "../api";
import type { GraphLink, GraphNode } from "../api";
import { catColor } from "../components/Badge";
import { Ic } from "../components/Icons";
import PageHead from "../components/PageHead";

type GraphMode = "ego" | "overview" | "dag" | "event";

interface ChartNode {
  id: string;
  name: string;
  value: string;
  kind: GraphNode["kind"];
  categoryName: string;
  symbolSize: number | [number, number];
  symbol?: string;
  category: number;
  x?: number;
  y?: number;
  itemStyle: Record<string, unknown>;
  label?: Record<string, unknown>;
  /** 装饰元素（轨道圆环 / 层色带 / 区域标注）：不可交互、不进统计 */
  decor?: boolean;
  silent?: boolean;
  raw?: GraphNode;
}

interface ChartLink {
  source: string;
  target: string;
  relation: string;
  lineStyle: Record<string, unknown>;
}

interface ViewData {
  chartNodes: ChartNode[];
  chartLinks: ChartLink[];
  catNames: string[];
  counts: { roles: number; skills: number; events: number; links: number };
}

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  role: "岗位",
  skill: "技能",
  event: "行业事件",
};

/** 调色板：用户指定的 11 色柔和渐变系（蓝→青→绿→黄→橙→红） */
const SKILL_CAT_META: Record<string, { zh: string; color: string }> = {
  ai_emerging: { zh: "新兴 AI", color: "#f47254" },
  ai_ml: { zh: "AI / 机器学习", color: "#c85e62" },
  bigdata: { zh: "大数据", color: "#7b95c6" },
  cloud: { zh: "云计算", color: "#49c2d9" },
  data_analysis: { zh: "数据分析", color: "#fded95" },
  database: { zh: "数据库", color: "#67a583" },
  devops: { zh: "DevOps", color: "#a1d8e8" },
  frontend: { zh: "前端", color: "#ffc1a6" },
  backend: { zh: "后端", color: "#f59c7c" },
  language: { zh: "编程语言", color: "#a2c986" },
  methods: { zh: "工程方法", color: "#d0e2c0" },
  mobile: { zh: "移动端", color: "#ffc1a6" },
  security: { zh: "安全", color: "#c85e62" },
  testing: { zh: "测试", color: "#fded95" },
};

const FALLBACK_COLORS = ["#7b95c6", "#49c2d9", "#a1d8e8", "#67a583", "#a2c986", "#d0e2c0", "#fded95", "#ffc1a6", "#f59c7c", "#f47254", "#c85e62"];

function labelCardStyle(dark: boolean): Record<string, unknown> {
  return dark
    ? { backgroundColor: "rgba(15,23,42,0.72)", borderColor: "rgba(148,163,184,0.28)", borderWidth: 1, borderRadius: 5, padding: [3, 7] }
    : { backgroundColor: "rgba(255,255,255,0.88)", borderColor: "rgba(28,30,35,0.09)", borderWidth: 1, borderRadius: 5, padding: [3, 7] };
}

function skillCatZh(cat?: string): string {
  return (cat && SKILL_CAT_META[cat]?.zh) || cat || "其他";
}

function skillColor(node: GraphNode): string {
  return (node.category && SKILL_CAT_META[node.category]?.color) || "#94A3B8";
}

/** 热门技能不再使用死色块，而是在类别色上加光晕 */
function skillItemStyle(node: GraphNode): Record<string, unknown> {
  const color = skillColor(node);
  if (!node.hot) return { color, borderColor: "rgba(255,255,255,0.9)", borderWidth: 1.2 };
  return {
    color,
    borderColor: "rgba(255,255,255,0.95)",
    borderWidth: 1.5,
    shadowColor: color,
    shadowBlur: 14,
  };
}

function roleColor(cat: string | undefined, allCats: string[]): string {
  const c = catColor(cat || "Other");
  if (c !== "#9aa0a9") return c;
  const idx = allCats.indexOf(cat || "Other");
  return FALLBACK_COLORS[(idx < 0 ? 0 : idx) % FALLBACK_COLORS.length];
}

function eventColor(node: GraphNode): string {
  if (node.impact_direction === "negative") return "#c85e62";
  if (node.impact_direction === "mixed") return "#f59c7c";
  return "#7b95c6";
}

function relationLabel(relation: string): string {
  if (relation === "REQUIRES") return "岗位要求技能";
  if (relation === "CORE_SKILL") return "核心技能";
  if (relation === "PREREQ") return "技能前置依赖";
  if (relation === "AFFECTS") return "事件影响岗位";
  return relation;
}

function nodeTooltip(raw: GraphNode): string {
  const eventExtra = raw.kind === "event"
    ? `<br/>${raw.event_date || ""} ${raw.source_name || ""}<br/><span style="color:#767b85">${raw.summary_zh || ""}</span>`
    : "";
  const title = raw.kind === "role" ? `${raw.label_zh || raw.label}<br/><span style="color:#767b85">${raw.label}</span>` : raw.label;
  return `<b>${title}</b><br/><span style="color:#767b85">${KIND_LABEL[raw.kind]} · ${raw.kind === "skill" ? skillCatZh(raw.category) : raw.category || ""}</span>${eventExtra}`;
}

function tooltipStyle(dark: boolean) {
  return dark
    ? {
        backgroundColor: "rgba(15,23,42,0.94)",
        borderColor: "rgba(148,163,184,0.2)",
        borderWidth: 1,
        padding: [10, 14] as [number, number],
        textStyle: { color: "#e2e8f0", fontSize: 12.5 },
        extraCssText: "box-shadow: 0 10px 32px -10px rgba(0,0,0,0.6); border-radius: 10px;",
      }
    : {
        backgroundColor: "rgba(255,255,255,0.97)",
        borderColor: "rgba(28,30,35,0.08)",
        borderWidth: 1,
        padding: [10, 14] as [number, number],
        textStyle: { color: "#1c1e23", fontSize: 12.5 },
        extraCssText: "box-shadow: 0 10px 32px -10px rgba(28,30,35,0.28); border-radius: 10px;",
      };
}

/** 轨道圆环 / 层色带等装饰节点：自身不可交互、不进 tooltip */
function decorNode(id: string, x: number, y: number, symbolSize: number | [number, number], itemStyle: Record<string, unknown>, label?: Record<string, unknown>, symbol = "circle"): ChartNode {
  return {
    id,
    name: "",
    value: "",
    kind: "skill",
    categoryName: "",
    symbolSize,
    symbol,
    category: 0,
    x, y,
    itemStyle,
    label: { show: false, ...label },
    decor: true,
    silent: true,
  };
}

function faintRing(id: string, r: number, opacity: number, ink: string, dashed = false): ChartNode {
  return decorNode(id, 0, 0, r * 2, {
    color: "rgba(0,0,0,0)",
    borderColor: `${ink}${opacity})`,
    borderWidth: 1,
    ...(dashed ? { borderType: "dashed" as const } : {}),
  });
}

// ---------------------------------------------------------------------------
// 搜索选择器（岗位 / 技能通用，支持中文、英文模糊过滤）
// ---------------------------------------------------------------------------

interface PickerItem {
  id: string;
  zh: string;
  en: string;
}

function GraphPicker({ items, placeholder, onPick }: { items: PickerItem[]; placeholder: string; onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    if (!kw) return items;
    return items.filter((it) => it.zh.toLowerCase().includes(kw) || it.en.toLowerCase().includes(kw));
  }, [q, items]);

  const pick = (id: string) => {
    onPick(id);
    setQ("");
    setOpen(false);
  };

  return (
    <div className="graph-picker">
      <div className="search">
        <Ic.search />
        <input
          value={q}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && filtered.length) pick(filtered[0].id);
            if (e.key === "Escape") setOpen(false);
          }}
        />
      </div>
      {open && (
        <div className="graph-dd">
          {filtered.length === 0 && <div className="graph-dd-empty">没有匹配的节点</div>}
          {filtered.slice(0, 12).map((it, i) => (
            <div key={it.id} className={"graph-dd-item" + (i === 0 && q.trim() ? " hl" : "")} onMouseDown={() => pick(it.id)}>
              <span className="dd-zh">{it.zh}</span>
              <span className="dd-en">{it.en}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 数据构建辅助
// ---------------------------------------------------------------------------

/** 以 target 为终点，沿 PREREQ 反向收集全部先修技能（含自身）。 */
function ancestorClosure(target: string, prereqLinks: GraphLink[]): Set<string> {
  const set = new Set([target]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const l of prereqLinks) {
      if (set.has(l.target) && !set.has(l.source)) {
        set.add(l.source);
        changed = true;
      }
    }
  }
  return set;
}

/** 在闭包子图上做拓扑分层（源在左、目标在右），容忍环。 */
function layerOf(ids: Set<string>, edges: GraphLink[]): Map<string, number> {
  const layer = new Map<string, number>();
  ids.forEach((id) => layer.set(id, 0));
  for (let i = 0; i < ids.size; i++) {
    let changed = false;
    for (const e of edges) {
      const want = (layer.get(e.source) ?? 0) + 1;
      if (want > (layer.get(e.target) ?? 0)) {
        layer.set(e.target, want);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return layer;
}

const MODES: Array<{ key: GraphMode; label: string }> = [
  { key: "ego", label: "岗位图谱" },
  { key: "overview", label: "全量总览" },
  { key: "dag", label: "学习路径" },
  { key: "event", label: "事件影响" },
];

export default function Graph() {
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<GraphMode>("ego");
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [dagTarget, setDagTarget] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dark, setDark] = useState(false);
  const pulse = 0;
  const chartInst = useRef<{ dispatchAction: (p: Record<string, unknown>) => void } | null>(null);

  /** 深浅两套画布主题：节点颜色不变，只换背景 / 连线 / 标签 / 装饰色 */
  const theme = useMemo(() => ({
    ink: dark ? "rgba(226,232,240," : "rgba(28,30,35,",
    labelInk: dark ? "#e2e8f0" : "#1b1d22",
    labelCard: labelCardStyle(dark),
    tooltip: tooltipStyle(dark),
    edgeCore: dark ? "#a1d8e8" : "#7b95c6",
    edgeReq: dark ? "#55638a" : "#B6BFCE",
    edgePre: dark ? "#64748b" : "#CBD5E1",
    bandA: dark ? "rgba(99,102,241,0.12)" : "rgba(91,141,239,0.05)",
    bandB: dark ? "rgba(148,163,184,0.05)" : "rgba(28,30,35,0.022)",
    decorText: dark ? "#64748b" : "#a3a8b1",
    legendText: dark ? "#94a3b8" : "#5c626c",
    legendInactive: dark ? "#334155" : "#d8dce3",
  }), [dark]);

  useEffect(() => {
    let alive = true;
    getGraph()
      .then((data) => {
        if (alive) {
          setNodes(data.nodes);
          setLinks(data.links);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  const roleNodes = useMemo(
    () => nodes.filter((n) => n.kind === "role").sort((a, b) => (a.label_zh || a.label).localeCompare(b.label_zh || b.label, "zh-CN")),
    [nodes],
  );
  const roleCats = useMemo(() => Array.from(new Set(roleNodes.map((n) => n.category || "Other"))).sort(), [roleNodes]);
  const skillNodes = useMemo(
    () => nodes.filter((n) => n.kind === "skill").sort((a, b) => a.label.localeCompare(b.label)),
    [nodes],
  );
  const prereqLinks = useMemo(() => links.filter((l) => l.relation === "PREREQ"), [links]);

  const roleItems = useMemo<PickerItem[]>(
    () => roleNodes.map((n) => ({ id: n.id, zh: n.label_zh || n.label, en: n.label })),
    [roleNodes],
  );
  const skillItems = useMemo<PickerItem[]>(
    () => skillNodes.map((n) => ({ id: n.id, zh: n.label_zh || n.label, en: n.label })),
    [skillNodes],
  );

  // 默认学习目标：RAG（先修闭包最丰富），用户选择后以其为准
  const effectiveDagTarget = dagTarget
    ?? (nodeById.has("skill:rag") ? "skill:rag" : nodeById.has("skill:machine-learning") ? "skill:machine-learning" : skillNodes[0]?.id ?? null);

  // 热门岗位：核心技能多、热门技能多的岗位优先
  const hotRoles = useMemo(() => {
    const score = new Map<string, number>();
    for (const l of links) {
      if (l.relation !== "CORE_SKILL") continue;
      const add = nodeById.get(l.target)?.hot ? 3 : 1;
      score.set(l.source, (score.get(l.source) || 0) + add);
    }
    return [...roleNodes]
      .sort((a, b) => ((score.get(b.id) || 0) - (score.get(a.id) || 0)) || ((b.size ?? 0) - (a.size ?? 0)))
      .slice(0, 8);
  }, [links, nodeById, roleNodes]);

  useEffect(() => {
    if (!selectedRole && hotRoles.length) setSelectedRole(hotRoles[0].id);
    // 仅在首次拿到数据时设置默认岗位
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hotRoles.length]);

  // -------------------------------------------------------------------------
  // 视图一：岗位自我中心网络（径向布局 + 轨道圆环参考线）
  // -------------------------------------------------------------------------
  const ego = useMemo(() => {
    if (!selectedRole) return null;
    const coreIds: string[] = [];
    const reqIds: string[] = [];
    const egoLinks: GraphLink[] = [];
    const direct = new Set<string>();
    for (const l of links) {
      if (l.source !== selectedRole) continue;
      if (l.relation === "CORE_SKILL") { coreIds.push(l.target); direct.add(l.target); egoLinks.push(l); }
      else if (l.relation === "REQUIRES") { reqIds.push(l.target); direct.add(l.target); egoLinks.push(l); }
    }
    coreIds.sort((a, b) => (nodeById.get(a)?.label || "").localeCompare(nodeById.get(b)?.label || ""));
    reqIds.sort((a, b) => (nodeById.get(a)?.label || "").localeCompare(nodeById.get(b)?.label || ""));

    const extIds: string[] = [];
    const extAnchor = new Map<string, string>();
    for (const l of prereqLinks) {
      if (extIds.length >= 14) break;
      const sIn = direct.has(l.source);
      const tIn = direct.has(l.target);
      if (sIn && tIn) { egoLinks.push(l); continue; }
      if (tIn && !direct.has(l.source) && !extAnchor.has(l.source)) { extIds.push(l.source); extAnchor.set(l.source, l.target); egoLinks.push(l); }
      else if (sIn && !direct.has(l.target) && !extAnchor.has(l.target)) { extIds.push(l.target); extAnchor.set(l.target, l.source); egoLinks.push(l); }
    }

    // 径向布局：岗位居中，核心技能内圈、要求技能中圈、外部前置外圈
    const pos = new Map<string, { x: number; y: number }>();
    const TAU = Math.PI * 2;
    coreIds.forEach((id, i) => {
      const a = -Math.PI / 2 + (TAU * i) / Math.max(coreIds.length, 1);
      pos.set(id, { x: Math.cos(a) * 150, y: Math.sin(a) * 150 });
    });
    reqIds.forEach((id, i) => {
      const a = -Math.PI / 2 + (TAU * (i + 0.5)) / Math.max(reqIds.length, 1);
      pos.set(id, { x: Math.cos(a) * 290, y: Math.sin(a) * 290 });
    });
    extIds.forEach((id, i) => {
      const anchor = pos.get(extAnchor.get(id) || "");
      const base = anchor ? Math.atan2(anchor.y, anchor.x) : -Math.PI / 2;
      const a = base + ((i % 2 === 0 ? 1 : -1) * 0.22 * Math.ceil(i / 2));
      pos.set(id, { x: Math.cos(a) * 420, y: Math.sin(a) * 420 });
    });

    const catNames = ["岗位", "核心技能", "要求技能", "前置技能"];
    const chartNodes: ChartNode[] = [
      faintRing("decor:ring-core", 150, 0.09, theme.ink),
      faintRing("decor:ring-req", 290, 0.07, theme.ink),
      faintRing("decor:ring-ext", 420, 0.05, theme.ink, true),
    ];
    const push = (raw: GraphNode, cat: number, size: number, showLabel: boolean, x?: number, y?: number) => {
      chartNodes.push({
        id: raw.id,
        name: raw.label_zh || raw.label,
        value: raw.label_zh || raw.label,
        kind: raw.kind,
        categoryName: catNames[cat],
        symbolSize: size,
        category: cat,
        x, y,
        itemStyle: raw.kind === "role"
          ? { color: roleColor(raw.category, roleCats), borderColor: "rgba(255,255,255,0.95)", borderWidth: 2, shadowColor: "rgba(28,30,35,0.3)", shadowBlur: 16 }
          : skillItemStyle(raw),
        label: {
          show: showLabel,
          position: raw.kind === "role" ? "bottom" : "right",
          distance: 6,
          color: theme.labelInk,
          fontSize: raw.kind === "role" ? 14 : 11.5,
          fontWeight: raw.kind === "role" ? 700 : 500,
          ...theme.labelCard,
        },
        raw,
      });
    };
    const roleRaw = nodeById.get(selectedRole);
    if (roleRaw) push(roleRaw, 0, 62, true, 0, 0);
    coreIds.forEach((id) => {
      const raw = nodeById.get(id);
      if (raw) push(raw, 1, raw.hot ? 30 : 24, true, pos.get(id)?.x, pos.get(id)?.y);
    });
    reqIds.forEach((id) => {
      const raw = nodeById.get(id);
      if (raw) push(raw, 2, raw.hot ? 20 : 15, false, pos.get(id)?.x, pos.get(id)?.y);
    });
    extIds.forEach((id) => {
      const raw = nodeById.get(id);
      if (raw) push(raw, 3, 14, false, pos.get(id)?.x, pos.get(id)?.y);
    });

    // 连线保持中性：颜色只留给节点。核心技能用主色加粗，要求技能浅灰细线，前置依赖虚线
    const chartLinks: ChartLink[] = egoLinks.map((l) => {
      if (l.relation === "PREREQ") {
        return {
          source: l.source,
          target: l.target,
          relation: l.relation,
          lineStyle: { type: "dashed", opacity: 0.5, width: 1, color: theme.edgePre, curveness: 0.08 },
        };
      }
      const isCore = l.relation === "CORE_SKILL";
      return {
        source: l.source,
        target: l.target,
        relation: l.relation,
        lineStyle: {
          type: "solid",
          opacity: isCore ? 0.55 : 0.4,
          width: isCore ? 2.2 : 1.1,
          color: isCore ? theme.edgeCore : theme.edgeReq,
          curveness: 0,
        },
      };
    });

    return { chartNodes, chartLinks, catNames, counts: { roles: 1, skills: coreIds.length + reqIds.length + extIds.length, events: 0, links: chartLinks.length } };
  }, [selectedRole, links, prereqLinks, nodeById, roleCats, theme]);

  // -------------------------------------------------------------------------
  // 视图二：全量总览（环形分组布局 + 类别区域标注，图例可点击隐藏）
  // -------------------------------------------------------------------------
  const overview = useMemo(() => {
    if (!nodes.length) return null;
    const TAU = Math.PI * 2;
    const roles = [...roleNodes].sort((a, b) => (a.category || "").localeCompare(b.category || "") || (a.label_zh || a.label).localeCompare(b.label_zh || b.label, "zh-CN"));
    const skillCats = Array.from(new Set(skillNodes.map((n) => n.category || "other"))).sort((a, b) => skillCatZh(a).localeCompare(skillCatZh(b), "zh-CN"));

    const pos = new Map<string, { x: number; y: number }>();
    roles.forEach((r, i) => {
      const a = -Math.PI / 2 + (TAU * i) / roles.length;
      pos.set(r.id, { x: Math.cos(a) * 190, y: Math.sin(a) * 190 });
    });
    let angle = -Math.PI / 2;
    const catArcs: Array<{ name: string; mid: number }> = [];
    for (const cat of skillCats) {
      const members = skillNodes.filter((n) => (n.category || "other") === cat);
      const arc = TAU * ((members.length + 4) / (skillNodes.length + skillCats.length * 4));
      members.forEach((s, i) => {
        const a = angle + (arc * (i + 0.5)) / members.length;
        pos.set(s.id, { x: Math.cos(a) * 430, y: Math.sin(a) * 430 });
      });
      catArcs.push({ name: skillCatZh(cat), mid: angle + arc / 2 });
      angle += arc;
    }

    const catNames = ["岗位", ...skillCats.map(skillCatZh)];
    const catIndex = new Map(catNames.map((c, i) => [c, i]));
    const chartNodes: ChartNode[] = [
      faintRing("decor:ring-role", 202, 0.055, theme.ink),
      faintRing("decor:ring-skill", 442, 0.045, theme.ink, true),
    ];
    catArcs.forEach((arc, i) => {
      chartNodes.push(decorNode(
        `decor:cat-${i}`,
        Math.cos(arc.mid) * 474, Math.sin(arc.mid) * 474,
        1,
        { color: "rgba(0,0,0,0)" },
        { show: true, position: "inside", formatter: arc.name, fontSize: 10, color: theme.decorText, fontWeight: 500 },
      ));
    });
    for (const n of nodes) {
      if (n.kind === "event") continue;
      const isRole = n.kind === "role";
      const size = isRole
        ? 13 + Math.min(15, Math.sqrt(n.size ?? 100) / 3.2)
        : n.hot ? 10 : 6;
      chartNodes.push({
        id: n.id,
        name: n.label_zh || n.label,
        value: n.label_zh || n.label,
        kind: n.kind,
        categoryName: isRole ? "岗位" : skillCatZh(n.category),
        symbolSize: size,
        category: catIndex.get(isRole ? "岗位" : skillCatZh(n.category)) ?? 0,
        x: pos.get(n.id)?.x,
        y: pos.get(n.id)?.y,
        itemStyle: isRole
          ? { color: roleColor(n.category, roleCats), borderColor: "rgba(255,255,255,0.7)", borderWidth: 0.6 }
          : skillItemStyle(n),
        label: { show: false, color: theme.labelInk, fontSize: 11, ...theme.labelCard },
        raw: n,
      });
    }

    const visibleIds = new Set(chartNodes.filter((c) => !c.decor).map((n) => n.id));
    const chartLinks: ChartLink[] = links
      .filter((l) => (l.relation === "CORE_SKILL" || l.relation === "PREREQ") && visibleIds.has(l.source) && visibleIds.has(l.target))
      .map((l) => ({
        source: l.source,
        target: l.target,
        relation: l.relation,
        lineStyle: {
          type: l.relation === "PREREQ" ? "dashed" : "solid",
          opacity: l.relation === "PREREQ" ? 0.1 : 0.09,
          width: 0.7,
          color: theme.edgeReq,
        },
      }));

    return {
      chartNodes, chartLinks, catNames,
      counts: {
        roles: roles.length,
        skills: skillNodes.length,
        events: 0,
        links: chartLinks.length,
      },
    };
  }, [nodes, links, roleNodes, skillNodes, roleCats, theme]);

  // -------------------------------------------------------------------------
  // 视图三：技能前置 DAG（学习路径，按层加背景色带）
  // -------------------------------------------------------------------------
  const dag = useMemo(() => {
    if (!effectiveDagTarget || !nodeById.has(effectiveDagTarget)) return null;
    const closure = ancestorClosure(effectiveDagTarget, prereqLinks);
    const edges = prereqLinks.filter((l) => closure.has(l.source) && closure.has(l.target));
    const layer = layerOf(closure, edges);
    const maxLayer = Math.max(...layer.values(), 0);
    const byLayer: string[][] = Array.from({ length: maxLayer + 1 }, () => []);
    closure.forEach((id) => byLayer[layer.get(id) ?? 0].push(id));
    byLayer.forEach((arr) => arr.sort((a, b) => (nodeById.get(a)?.label || "").localeCompare(nodeById.get(b)?.label || "")));

    const pos = new Map<string, { x: number; y: number }>();
    byLayer.forEach((arr, li) => {
      arr.forEach((id, i) => {
        pos.set(id, { x: li * 190 - (maxLayer * 190) / 2, y: (i - (arr.length - 1) / 2) * 80 });
      });
    });

    const maxPerLayer = Math.max(...byLayer.map((arr) => arr.length), 1);
    const bandH = maxPerLayer * 80 + 70;
    const chartNodes: ChartNode[] = [];
    byLayer.forEach((_arr, li) => {
      const cx = li * 190 - (maxLayer * 190) / 2;
      chartNodes.push(decorNode(
        `decor:band-${li}`, cx, 0,
        [172, bandH],
        { color: li % 2 === 0 ? theme.bandA : theme.bandB, borderWidth: 0 },
        undefined, "rect",
      ));
      chartNodes.push(decorNode(
        `decor:layer-${li}`, cx, -bandH / 2 - 4, 1,
        { color: "rgba(0,0,0,0)" },
        { show: true, position: "bottom", distance: 10, formatter: `第 ${li + 1} 层`, fontSize: 10, color: theme.decorText, fontFamily: "ui-monospace, Menlo, monospace" },
      ));
    });

    for (const id of closure) {
      const raw = nodeById.get(id)!;
      const isTarget = id === effectiveDagTarget;
      chartNodes.push({
        id: raw.id,
        name: raw.label_zh || raw.label,
        value: raw.label_zh || raw.label,
        kind: raw.kind,
        categoryName: "技能",
        symbolSize: isTarget ? 28 : raw.hot ? 19 : 14,
        category: 0,
        x: pos.get(id)?.x,
        y: pos.get(id)?.y,
        itemStyle: isTarget
          ? { ...skillItemStyle(raw), borderColor: "#1b1d22", borderWidth: 2, shadowColor: skillColor(raw), shadowBlur: 18 }
          : skillItemStyle(raw),
        label: {
          show: true,
          position: "bottom",
          distance: 5,
          color: theme.labelInk,
          fontSize: 11,
          fontWeight: isTarget ? 700 : 500,
          ...theme.labelCard,
        },
        raw,
      });
    }

    const chartLinks: ChartLink[] = edges.map((l) => ({
      source: l.source,
      target: l.target,
      relation: l.relation,
      lineStyle: { type: "solid", opacity: 0.5, width: 1.3, color: theme.edgePre, curveness: 0.06 },
    }));

    return { chartNodes, chartLinks, catNames: ["技能"], maxLayer, counts: { roles: 0, skills: closure.size, events: 0, links: chartLinks.length } };
  }, [effectiveDagTarget, prereqLinks, nodeById, theme]);

  // -------------------------------------------------------------------------
  // 视图四：事件影响（按选中岗位过滤）
  // -------------------------------------------------------------------------
  const eventView = useMemo(() => {
    if (!selectedRole) return null;
    const evLinks = links.filter((l) => l.relation === "AFFECTS" && l.target === selectedRole);
    const roleRaw = nodeById.get(selectedRole);
    if (!roleRaw) return null;
    const evIds = Array.from(new Set(evLinks.map((l) => l.source)));
    const TAU = Math.PI * 2;
    const pos = new Map<string, { x: number; y: number }>();
    evIds.forEach((id, i) => {
      const a = -Math.PI / 2 + (TAU * i) / Math.max(evIds.length, 1);
      pos.set(id, { x: Math.cos(a) * 320, y: Math.sin(a) * 320 });
    });

    const catNames = ["岗位", "行业事件"];
    const chartNodes: ChartNode[] = [{
      id: roleRaw.id,
      name: roleRaw.label_zh || roleRaw.label,
      value: roleRaw.label_zh || roleRaw.label,
      kind: "role",
      categoryName: "岗位",
      symbolSize: 44,
      category: 0,
      x: 0, y: 0,
      itemStyle: { color: roleColor(roleRaw.category, roleCats), borderColor: "rgba(255,255,255,0.95)", borderWidth: 2, shadowColor: "rgba(28,30,35,0.28)", shadowBlur: 16 },
      label: { show: true, position: "bottom", distance: 6, color: theme.labelInk, fontSize: 13, fontWeight: 600, ...theme.labelCard },
      raw: roleRaw,
    }];
    for (const id of evIds) {
      const raw = nodeById.get(id);
      if (!raw) continue;
      const color = eventColor(raw);
      chartNodes.push({
        id: raw.id,
        name: raw.label,
        value: raw.label,
        kind: "event",
        categoryName: "行业事件",
        symbolSize: 12 + Math.min(13, ((raw.importance ?? 0.5) as number) * 13),
        category: 1,
        x: pos.get(id)?.x,
        y: pos.get(id)?.y,
        itemStyle: { color, borderColor: "rgba(255,255,255,0.9)", borderWidth: 1, shadowColor: color, shadowBlur: 8 },
        label: { show: false, color: theme.labelInk, fontSize: 10.5, ...theme.labelCard },
        raw,
      });
    }
    const chartLinks: ChartLink[] = evLinks.map((l) => {
      const src = nodeById.get(l.source);
      const color = src ? eventColor(src) : "#3B82F6";
      return {
        source: l.source,
        target: l.target,
        relation: l.relation,
        lineStyle: { type: "solid", opacity: 0.45, width: 1.1, color, curveness: 0.04 },
      };
    });
    return { chartNodes, chartLinks, catNames, counts: { roles: 1, skills: 0, events: evIds.length, links: chartLinks.length } };
  }, [selectedRole, links, nodeById, roleCats, theme]);

  // -------------------------------------------------------------------------
  // 视图挂载
  // -------------------------------------------------------------------------

  const view: ViewData | null = mode === "overview" ? overview : mode === "ego" ? ego : mode === "dag" ? dag : eventView;

  const switchMode = (m: GraphMode) => {
    setMode(m);
    setSelectedId(null);
  };

  const onChartClick = (p: { dataType?: string; data?: ChartNode }) => {
    if (p.dataType !== "node" || !p.data) { setSelectedId(null); return; }
    if (p.data.decor || !p.data.raw) return;
    setSelectedId(p.data.id);
    const raw = p.data.raw;
    if (raw.kind === "role") navigate(`/role/${encodeURIComponent(raw.label)}`);
    if (raw.kind === "skill") {
      setDagTarget(raw.id);
      switchMode("dag");
    }
  };

  /** 图例 hover 联动：高亮同类节点，移出恢复 */
  const hlNodes = (pred?: (n: ChartNode) => boolean) => {
    const inst = chartInst.current;
    if (!inst || !view) return;
    inst.dispatchAction({ type: "downplay", seriesIndex: 0 });
    if (!pred) return;
    view.chartNodes.forEach((n, i) => {
      if (!n.decor && pred(n)) inst.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: i });
    });
  };

  const option = useMemo(() => {
    if (!view) return null;

    // 选中节点呼吸：放大 + 光晕脉动
    const sizedNodes = selectedId
      ? view.chartNodes.map((n) => {
          if (n.decor || n.id !== selectedId) return n;
          const grow = 1 + pulse * 0.1;
          const base = Array.isArray(n.symbolSize) ? n.symbolSize[0] : n.symbolSize;
          const color = (n.itemStyle.color as string) || "#7b95c6";
          return {
            ...n,
            symbolSize: Array.isArray(n.symbolSize) ? [base * grow, n.symbolSize[1] * grow] : base * grow,
            itemStyle: { ...n.itemStyle, borderColor: theme.labelInk, borderWidth: 1.6, shadowColor: color, shadowBlur: 16 + pulse * 12 },
          };
        })
      : view.chartNodes;

    if (mode === "overview") {
      return {
        tooltip: {
          ...theme.tooltip,
          formatter: (p: { dataType?: string; data?: ChartNode | ChartLink }) =>
            p.dataType === "edge" ? relationLabel((p.data as ChartLink).relation) : nodeTooltip((p.data as ChartNode).raw!),
        },
        legend: {
          left: 16, top: 14, orient: "vertical",
          itemWidth: 9, itemHeight: 9, icon: "circle",
          inactiveColor: theme.legendInactive,
          textStyle: { fontSize: 11, color: theme.legendText },
          data: view.catNames,
        },
        series: [{
          type: "graph",
          layout: "none",
          roam: true,
          draggable: true,
          categories: view.catNames.map((name) => ({ name })),
          data: sizedNodes,
          links: view.chartLinks,
          labelLayout: { hideOverlap: true },
          emphasis: { focus: "adjacency", scale: 1.25, label: { show: true }, lineStyle: { opacity: 0.5 } },
          scaleLimit: { min: 0.35, max: 6 },
          animation: false,
        }],
      };
    }

    const isDag = mode === "dag";
    return {
      tooltip: {
        ...theme.tooltip,
        formatter: (p: { dataType?: string; data?: ChartNode | ChartLink }) => {
          if (p.dataType === "edge") {
            const l = p.data as ChartLink;
            return isDag
              ? `<b>${nodeById.get(l.source)?.label ?? l.source}</b> 是 <b>${nodeById.get(l.target)?.label ?? l.target}</b> 的前置技能`
              : relationLabel(l.relation);
          }
          return nodeTooltip((p.data as ChartNode).raw!);
        },
      },
      series: [{
        type: "graph",
        layout: "none",
        roam: true,
        draggable: true,
        categories: view.catNames.map((name) => ({ name })),
        data: sizedNodes,
        links: view.chartLinks,
        edgeSymbol: isDag || mode === "ego" ? ["none", "arrow"] : ["none", "none"],
        edgeSymbolSize: isDag ? 7 : 5,
        labelLayout: { hideOverlap: true },
        emphasis: { focus: "adjacency", scale: 1.25, label: { show: true }, lineStyle: { opacity: 0.9 } },
        scaleLimit: { min: 0.3, max: 5 },
        animationDuration: 550,
        animationEasing: "cubicOut",
        animationDurationUpdate: 260,
        animationEasingUpdate: "cubicOut",
      }],
    };
  }, [mode, view, nodeById, selectedId, pulse, theme]);

  const counts = view?.counts;
  const needRole = (mode === "ego" || mode === "event") && !selectedRole;

  if (loading) {
    return (
      <div className="page graph-skel" style={{ maxWidth: 1320 }}>
        <div className="graph-skel-head">
          <div className="skel" style={{ height: 13, width: 240 }} />
          <div className="skel" style={{ height: 36, width: 440 }} />
          <div className="skel" style={{ height: 15, width: 600 }} />
        </div>
        <div className="skel" style={{ height: 40, width: 360 }} />
        <div className="skel" style={{ height: "calc(100vh - 300px)", minHeight: 520, borderRadius: "var(--r-lg)" }} />
      </div>
    );
  }

  const selectedRoleRaw = selectedRole ? nodeById.get(selectedRole) : null;
  const dagTargetRaw = effectiveDagTarget ? nodeById.get(effectiveDagTarget) : null;

  return (
    <div className="page" style={{ maxWidth: 1320 }}>
      <PageHead
        eyebrow="Career Graph / Role · Skill · Event"
        title={<>岗位 · 技能 · 行业事件<span className="lite"> 职业图谱</span></>}
        sub={`${roleNodes.length} 个细粒度岗位、${skillNodes.length} 个技能、${nodes.filter((n) => n.kind === "event").length} 个行业事件、${links.length} 条关系。从搜索一个岗位开始，看它的技能构成与前置依赖；或切换到总览 / 学习路径视角。`}
      />

      <div className="seg" style={{ marginBottom: 14, flexWrap: "wrap", display: "flex" }}>
        {MODES.map((m) => (
          <button key={m.key} className={mode === m.key ? "active" : ""} onClick={() => switchMode(m.key)}>{m.label}</button>
        ))}
      </div>

      {mode !== "overview" && (
        <div className="graph-toolbar">
          {mode === "ego" && (
            <>
              <GraphPicker
                items={roleItems}
                placeholder="搜索岗位（中文 / 英文名）…"
                onPick={setSelectedRole}
              />
              {selectedRoleRaw && (
                <button className="chip sel" onClick={() => setSelectedRole(null)}>
                  {selectedRoleRaw.label_zh || selectedRoleRaw.label}
                  <span style={{ opacity: 0.7 }}>×</span>
                </button>
              )}
            </>
          )}
          {mode === "event" && (
            <>
              <GraphPicker
                items={roleItems}
                placeholder="选择岗位，查看影响它的行业事件…"
                onPick={setSelectedRole}
              />
              {selectedRoleRaw && (
                <button className="chip sel" onClick={() => setSelectedRole(null)}>
                  {selectedRoleRaw.label_zh || selectedRoleRaw.label}
                  <span style={{ opacity: 0.7 }}>×</span>
                </button>
              )}
            </>
          )}
          {mode === "dag" && (
            <>
              <GraphPicker
                items={skillItems}
                placeholder="选择目标技能，查看先修依赖链…"
                onPick={setDagTarget}
              />
              {dagTargetRaw && (
                <button className="chip sel" onClick={() => setDagTarget(null)}>
                  目标：{dagTargetRaw.label_zh || dagTargetRaw.label}
                  <span style={{ opacity: 0.7 }}>×</span>
                </button>
              )}
            </>
          )}
        </div>
      )}

      <div className={"graph-shell" + (dark ? " dark" : "")}>
        <button className="graph-theme" onClick={() => setDark((d) => !d)}>
          {dark ? "☀ 浅色" : "☾ 深色"}
        </button>
        {needRole ? (
          <div className="graph-empty">
            <Ic.graph />
            <div className="ge-title">先选择一个岗位</div>
            <div className="ge-sub">
              {mode === "ego"
                ? "在上方搜索岗位，或从下面的热门岗位中选择一个，查看它的核心技能、要求技能与前置依赖。"
                : "在上方搜索岗位，查看影响它的行业事件。"}
            </div>
            <div className="chips">
              {hotRoles.map((r) => (
                <button key={r.id} className="chip" onClick={() => setSelectedRole(r.id)}>
                  {r.label_zh || r.label}
                </button>
              ))}
            </div>
          </div>
        ) : mode === "dag" && !effectiveDagTarget ? (
          <div className="graph-empty">
            <Ic.route />
            <div className="ge-title">选择一个目标技能</div>
            <div className="ge-sub">学习路径视图会展示该技能的全部前置技能，并按从左到右的顺序分层排列。</div>
            <div className="chips">
              {["skill:rag", "skill:llm", "skill:kubernetes", "skill:terraform"].filter((id) => nodeById.has(id)).map((id) => (
                <button key={id} className="chip" onClick={() => setDagTarget(id)}>
                  {nodeById.get(id)?.label}
                </button>
              ))}
            </div>
          </div>
        ) : option ? (
          <ReactECharts
            option={option}
            style={{ width: "100%", height: "100%" }}
            onChartReady={(inst) => { chartInst.current = inst; }}
            onEvents={{ click: onChartClick }}
          />
        ) : null}

        {counts && (
          <div className="graph-stat">
            <div><div className="gs-v">{counts.roles}</div><div className="gs-l">岗位</div></div>
            <div><div className="gs-v">{counts.skills}</div><div className="gs-l">技能</div></div>
            <div><div className="gs-v">{counts.events}</div><div className="gs-l">事件</div></div>
            <div><div className="gs-v">{counts.links}</div><div className="gs-l">关系</div></div>
          </div>
        )}

        <div className="graph-legend">
          <div className="lg-title">图例</div>
          {mode === "ego" && view && (
            <>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.categoryName === "核心技能")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#7b95c6", boxShadow: "0 0 6px 1px rgba(123,149,198,0.5)" }} />核心技能
              </span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.categoryName === "要求技能")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#94A3B8" }} />要求技能
              </span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.categoryName === "前置技能")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#cbd5e1", border: "1.5px dashed #94A3B8" }} />外部前置
              </span>
              <span className="lg-cat"><span className="lg-line" style={{ borderTop: "2px solid rgba(123,149,198,0.7)" }} />核心 / 要求</span>
              <span className="lg-cat"><span className="lg-line" style={{ borderTop: "1.5px dashed #94A3B8" }} />前置依赖</span>
              <span className="lg-cat" style={{ color: "#9aa0a9" }}>点击技能 → 学习路径</span>
            </>
          )}
          {mode === "overview" && (
            <>
              <span className="lg-cat"><span className="dot-cat" style={{ background: "#7b95c6" }} />内圈：岗位（按大类）</span>
              <span className="lg-cat"><span className="dot-cat" style={{ background: "#f59c7c" }} />外圈：技能（按类别）</span>
              <span className="lg-cat" style={{ color: "#9aa0a9" }}>左上角色块可点击隐藏 ·  hover 节点看名称</span>
            </>
          )}
          {mode === "dag" && view && (
            <>
              <span className="lg-cat"><span className="lg-line" style={{ borderTop: "1.5px solid rgba(28,30,35,0.4)" }} />前置依赖（箭头指向后续技能）</span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => Boolean(n.raw?.hot))} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#f59c7c", boxShadow: "0 0 6px 1px rgba(245,156,124,0.55)" }} />热门技能
              </span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.id === effectiveDagTarget)} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#1b1d22" }} />目标技能
              </span>
              <span className="lg-cat" style={{ color: "#9aa0a9" }}>从左到右 = 建议学习顺序</span>
            </>
          )}
          {mode === "event" && view && (
            <>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.raw?.impact_direction !== "negative" && n.raw?.impact_direction !== "mixed" && n.kind === "event")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#7b95c6" }} />正向 / 中性事件
              </span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.raw?.impact_direction === "mixed")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#f59c7c" }} />混合影响
              </span>
              <span className="lg-cat lg-hover" onMouseEnter={() => hlNodes((n) => n.raw?.impact_direction === "negative")} onMouseLeave={() => hlNodes()}>
                <span className="dot-cat" style={{ background: "#c85e62" }} />负向事件
              </span>
              <span className="lg-cat" style={{ color: "#9aa0a9" }}>点大小 = 事件重要度</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
