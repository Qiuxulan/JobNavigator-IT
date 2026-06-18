import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { getGraph } from "../api";
import type { GraphLink, GraphNode } from "../api";
import { catColor } from "../components/Badge";

type GraphMode = "role_skill" | "event" | "full";

interface ChartNode {
  id: string;
  name: string;
  value: string;
  kind: GraphNode["kind"];
  categoryName: string;
  symbolSize: number;
  category: number;
  itemStyle: Record<string, unknown>;
  label?: Record<string, unknown>;
  raw: GraphNode;
}

interface ChartLink {
  source: string;
  target: string;
  relation: string;
  lineStyle: Record<string, unknown>;
}

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  role: "岗位",
  skill: "技能",
  event: "行业事件",
};

function nodeColor(node: GraphNode): string {
  if (node.kind === "role") return catColor(node.category || "Other");
  if (node.kind === "skill") return node.hot ? "#FFB13D" : "#cdd2da";
  return node.impact_direction === "negative" ? "#FB5566" : "#6E8AFF";
}

function nodeSize(node: GraphNode): number {
  if (node.kind === "role") return 28;
  if (node.kind === "skill") return node.hot ? 18 : 14;
  return 17;
}

function relationLabel(relation: string): string {
  if (relation === "REQUIRES") return "岗位要求技能";
  if (relation === "CORE_SKILL") return "核心技能";
  if (relation === "PREREQ") return "技能前置依赖";
  if (relation === "AFFECTS") return "事件影响岗位";
  return relation;
}

export default function Graph() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");
  const [mode, setMode] = useState<GraphMode>("role_skill");

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

  const roleCategories = useMemo(
    () => Array.from(new Set(nodes.filter((node) => node.kind === "role").map((node) => node.category || "Other"))).sort((a, b) => a.localeCompare(b, "zh-CN")),
    [nodes],
  );

  const filtered = useMemo(() => {
    const selectedRoles = new Set(
      nodes
        .filter((node) => node.kind === "role" && (category === "all" || node.category === category))
        .map((node) => node.id),
    );
    const visibleIds = new Set<string>();
    const visibleLinks: GraphLink[] = [];

    if (mode === "role_skill") {
      if (category === "all") {
        for (const node of nodes) {
          if (node.kind === "role" || node.kind === "skill") visibleIds.add(node.id);
        }
        for (const link of links) {
          if (["REQUIRES", "CORE_SKILL", "PREREQ"].includes(link.relation)) visibleLinks.push(link);
        }
      } else {
        for (const roleId of selectedRoles) visibleIds.add(roleId);
        for (const link of links) {
          if (!["REQUIRES", "CORE_SKILL"].includes(link.relation)) continue;
          if (!selectedRoles.has(link.source)) continue;
          visibleIds.add(link.source);
          visibleIds.add(link.target);
          visibleLinks.push(link);
        }
        for (const link of links) {
          if (link.relation === "PREREQ" && visibleIds.has(link.source) && visibleIds.has(link.target)) {
            visibleLinks.push(link);
          }
        }
      }
    }

    if (mode === "event") {
      for (const roleId of selectedRoles) visibleIds.add(roleId);
      for (const link of links) {
        if (link.relation !== "AFFECTS") continue;
        const target = nodeById.get(link.target);
        const source = nodeById.get(link.source);
        const roleId = target?.kind === "role" ? target.id : source?.kind === "role" ? source.id : "";
        if (!selectedRoles.has(roleId)) continue;
        visibleIds.add(link.source);
        visibleIds.add(link.target);
        visibleLinks.push(link);
      }
    }

    if (mode === "full") {
      if (category === "all") {
        for (const node of nodes) visibleIds.add(node.id);
        visibleLinks.push(...links);
      } else {
        for (const roleId of selectedRoles) visibleIds.add(roleId);
        for (const link of links) {
          if (["REQUIRES", "CORE_SKILL"].includes(link.relation) && selectedRoles.has(link.source)) {
            visibleIds.add(link.source);
            visibleIds.add(link.target);
            visibleLinks.push(link);
          }
          if (link.relation === "AFFECTS" && selectedRoles.has(link.target)) {
            visibleIds.add(link.source);
            visibleIds.add(link.target);
            visibleLinks.push(link);
          }
        }
        for (const link of links) {
          if (link.relation === "PREREQ" && visibleIds.has(link.source) && visibleIds.has(link.target)) visibleLinks.push(link);
        }
      }
    }

    const visibleNodes = nodes.filter((node) => visibleIds.has(node.id));
    return { visibleNodes, visibleLinks };
  }, [category, links, nodeById, nodes, mode]);

  const visibleSummary = useMemo(
    () => ({
      roles: filtered.visibleNodes.filter((node) => node.kind === "role").length,
      skills: filtered.visibleNodes.filter((node) => node.kind === "skill").length,
      events: filtered.visibleNodes.filter((node) => node.kind === "event").length,
      links: filtered.visibleLinks.length,
    }),
    [filtered],
  );

  const totalSummary = useMemo(
    () => ({
      roles: nodes.filter((node) => node.kind === "role").length,
      skills: nodes.filter((node) => node.kind === "skill").length,
      events: nodes.filter((node) => node.kind === "event").length,
      links: links.length,
    }),
    [nodes, links],
  );

  const graphOption = useMemo(() => {
    const categoryNames = Array.from(
      new Set(filtered.visibleNodes.map((node) => `${KIND_LABEL[node.kind]}:${node.category || node.kind}`)),
    );
    const catIndex = new Map(categoryNames.map((name, index) => [name, index]));

    const chartNodes: ChartNode[] = filtered.visibleNodes.map((node) => {
      const categoryName = `${KIND_LABEL[node.kind]}:${node.category || node.kind}`;
      return {
        id: node.id,
        name: node.id,
        value: node.label_zh || node.label,
        kind: node.kind,
        categoryName,
        symbolSize: nodeSize(node),
        category: catIndex.get(categoryName) ?? 0,
        itemStyle: { color: nodeColor(node), borderColor: "#fff", borderWidth: 1.2 },
        label: {
          show: node.kind === "role",
          position: "right",
          color: "#1b1d22",
          fontSize: 11,
          formatter: () => node.label_zh || node.label,
        },
        raw: node,
      };
    });

    const chartLinks: ChartLink[] = filtered.visibleLinks.map((link) => ({
      source: link.source,
      target: link.target,
      relation: link.relation,
      lineStyle: {
        type: link.relation === "PREREQ" ? "dashed" : "solid",
        opacity: link.relation === "CORE_SKILL" ? 0.55 : link.relation === "AFFECTS" ? 0.36 : 0.24,
        width: link.relation === "CORE_SKILL" ? 1.7 : 1,
        color: link.relation === "AFFECTS" ? "#6E8AFF" : "rgba(28,30,35,0.18)",
      },
    }));

    return {
      tooltip: {
        backgroundColor: "rgba(255,255,255,0.98)",
        borderColor: "rgba(28,30,35,0.10)",
        borderWidth: 1,
        textStyle: { color: "#1c1e23", fontSize: 12 },
        formatter: (p: { dataType?: string; data?: ChartNode | ChartLink }) => {
          if (p.dataType === "edge") return relationLabel((p.data as ChartLink).relation);
          const raw = (p.data as ChartNode).raw;
          const eventExtra = raw.kind === "event"
            ? `<br/>${raw.event_date || ""} ${raw.source_name || ""}<br/><span style="color:#767b85">${raw.summary_zh || ""}</span>`
            : "";
          const title = raw.kind === "role" ? `${raw.label_zh || raw.label}<br/><span style="color:#767b85">${raw.label}</span>` : raw.label;
          return `<b>${title}</b><br/><span style="color:#767b85">${KIND_LABEL[raw.kind]} · ${raw.category || ""}</span>${eventExtra}`;
        },
      },
      series: [{
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        categories: categoryNames.map((name) => ({ name })),
        data: chartNodes,
        links: chartLinks,
        force: { repulsion: mode === "full" ? 78 : 125, edgeLength: [36, 120], gravity: 0.07, friction: 0.24 },
        labelLayout: { hideOverlap: true },
        emphasis: { focus: "adjacency", lineStyle: { width: 2, opacity: 0.9 } },
        scaleLimit: { min: 0.2, max: 4 },
      }],
    };
  }, [filtered, mode]);

  if (loading) return <div className="loading-center"><div className="spinner" />加载知识图谱...</div>;

  return (
    <div className="page" style={{ maxWidth: 1320 }}>
      <div className="page-head">
        <div className="page-eyebrow">Knowledge Graph / Evidence Graph</div>
        <div className="page-title">岗位、技能、事件证据<span className="lite"> 关系图谱</span></div>
        <div className="page-sub">
          数据总量：{totalSummary.roles} 个细粒度岗位、{totalSummary.skills} 个技能节点、{totalSummary.events} 个行业事件节点、{totalSummary.links} 条关系。下方统计为当前视图筛选后的节点与关系数量。
        </div>
      </div>

      <div className="seg" style={{ marginBottom: 12, flexWrap: "wrap", display: "flex" }}>
        {(["role_skill", "event", "full"] as GraphMode[]).map((item) => (
          <button key={item} className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
            {item === "role_skill" ? "岗位-技能" : item === "event" ? "事件入图" : "融合图谱"}
          </button>
        ))}
      </div>

      <div className="seg" style={{ marginBottom: 18, flexWrap: "wrap", display: "flex" }}>
        <button className={category === "all" ? "active" : ""} onClick={() => setCategory("all")}>全部大类</button>
        {roleCategories.map((cat) => <button key={cat} className={category === cat ? "active" : ""} onClick={() => setCategory(cat)}>{cat}</button>)}
      </div>

      <div className="graph-shell">
        <ReactECharts option={graphOption} style={{ width: "100%", height: "100%" }} />
        <div className="graph-stat">
          <div><div className="gs-v">{visibleSummary.roles}</div><div className="gs-l">岗位</div></div>
          <div><div className="gs-v">{visibleSummary.skills}</div><div className="gs-l">技能</div></div>
          <div><div className="gs-v">{visibleSummary.events}</div><div className="gs-l">事件</div></div>
          <div><div className="gs-v">{visibleSummary.links}</div><div className="gs-l">关系</div></div>
        </div>
        <div className="graph-legend">
          <div className="lg-title">图例</div>
          <div className="lg-cats">
            <span className="lg-cat"><span className="dot-cat" style={{ background: "#cdd2da" }} />技能</span>
            <span className="lg-cat"><span className="dot-cat" style={{ background: "#FFB13D" }} />热门技能</span>
            <span className="lg-cat"><span className="dot-cat" style={{ background: "#6E8AFF" }} />正向/中性事件</span>
            <span className="lg-cat"><span className="dot-cat" style={{ background: "#FB5566" }} />负向事件</span>
          </div>
        </div>
      </div>
    </div>
  );
}
