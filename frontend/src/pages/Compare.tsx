import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getRoleCatalog, getTrend } from "../api";
import type { RoleCatalogItem, TrendSignal } from "../api";
import { Ic } from "../components/Icons";
import { Card } from "../components/Card";
import { TrendBadge, catColor } from "../components/Badge";

const COLORS = ["#1c1e23", "#8a9bb0", "#8fb094", "#c9b684", "#c69a93", "#a897bb", "#82afa9", "#c4917f"];

function roleTitle(role: RoleCatalogItem | undefined, fallback: string): string {
  return role?.role_name_zh || fallback;
}

export default function Compare() {
  const navigate = useNavigate();
  const [roles, setRoles] = useState<RoleCatalogItem[]>([]);
  const [selected, setSelected] = useState<string[]>(["AI Engineer", "DevOps Engineer"]);
  const [results, setResults] = useState<TrendSignal[]>([]);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    getRoleCatalog()
      .then((data) => { if (alive) setRoles(data); })
      .finally(() => { if (alive) setLoadingRoles(false); });
    return () => { alive = false; };
  }, []);

  const roleMap = useMemo(() => new Map(roles.map((role) => [role.role_name, role])), [roles]);

  const grouped = useMemo(() => {
    const map = new Map<string, RoleCatalogItem[]>();
    for (const role of roles) map.set(role.coarse_role, [...(map.get(role.coarse_role) || []), role]);
    return Array.from(map.entries());
  }, [roles]);

  useEffect(() => {
    let alive = true;
    async function load() {
      if (selected.length === 0) {
        setResults([]);
        return;
      }
      setLoading(true);
      const rows = await Promise.all(selected.map(async (role) => {
        try {
          return await getTrend(role, 36);
        } catch {
          return { canonical_role: role, trend_direction: "flat", predicted_demand_index: 0, confidence: 0, main_factors: [], evidence: [] };
        }
      }));
      if (alive) {
        setResults(rows);
        setLoading(false);
      }
    }
    void load();
    return () => { alive = false; };
  }, [selected]);

  const toggle = (name: string) => {
    setSelected((prev) => prev.includes(name) ? prev.filter((x) => x !== name) : prev.length < 8 ? [...prev, name] : prev);
  };

  const barOption = useMemo(() => {
    const sorted = [...results].sort((a, b) => b.predicted_demand_index - a.predicted_demand_index);
    return {
      tooltip: { trigger: "axis" as const },
      grid: { left: 4, right: 40, top: 18, bottom: 4, containLabel: true },
      xAxis: { type: "value" as const },
      yAxis: { type: "category" as const, data: sorted.map((r) => roleTitle(roleMap.get(r.canonical_role), r.canonical_role)), inverse: true },
      series: [{
        type: "bar",
        data: sorted.map((r) => ({
          value: r.predicted_demand_index,
          itemStyle: { color: COLORS[selected.indexOf(r.canonical_role) % COLORS.length], borderRadius: [0, 4, 4, 0] },
        })),
        barWidth: 18,
        label: { show: true, position: "right" as const, formatter: (p: { value: number }) => Number(p.value).toFixed(4), color: "#767b85", fontSize: 11 },
      }],
    };
  }, [results, roleMap, selected]);

  if (loadingRoles) return <div className="loading-center"><div className="spinner" />加载岗位列表...</div>;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-eyebrow">Compare / Role Comparison</div>
        <div className="page-title">岗位<span className="lite">发展对比</span></div>
        <div className="page-sub">最多选择 8 个岗位，横向比较预测需求指数、趋势方向和置信度。已选择 {selected.length} / 8。</div>
      </div>

      <Card title="选择岗位" desc="按岗位大类分组，点击标签添加或移除" action={selected.length > 0 ? <button className="btn ghost sm" onClick={() => setSelected([])}>清空</button> : undefined}>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {grouped.map(([category, items]) => (
            <div className="chip-group" key={category} style={{ margin: 0 }}>
              <div className="chip-cat-label"><span className="dot-cat" style={{ background: catColor(category) }} />{category}</div>
              <div className="chips">
                {items.map((role) => (
                  <span key={role.role_name} className={"chip" + (selected.includes(role.role_name) ? " sel" : "")} onClick={() => toggle(role.role_name)}>
                    {role.role_name_zh || role.role_name}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {loading && <div className="loading-center" style={{ padding: 40 }}><div className="spinner" />加载对比数据...</div>}
      {!loading && results.length === 0 && <Card style={{ marginTop: 20 }}><div className="cmp-empty"><Ic.compare /><div>请选择至少一个岗位开始对比。</div></div></Card>}
      {!loading && results.length > 0 && (
        <>
          <Card style={{ marginTop: 20 }} title="需求指数对比">
            <ReactECharts option={barOption} style={{ height: Math.max(220, results.length * 56) }} />
          </Card>
          <Card style={{ marginTop: 20 }} title="对比数据" desc="按预测需求指数排序">
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th style={{ width: 16 }} /><th>岗位</th><th>趋势</th><th className="num">置信度</th><th className="num">需求指数</th><th /></tr></thead>
                <tbody>
                  {[...results].sort((a, b) => b.predicted_demand_index - a.predicted_demand_index).map((r) => {
                    const colorIndex = Math.max(0, selected.indexOf(r.canonical_role));
                    const meta = roleMap.get(r.canonical_role);
                    return (
                      <tr key={r.canonical_role} onClick={() => navigate(`/role/${encodeURIComponent(r.canonical_role)}`)}>
                        <td><span style={{ display: "inline-block", width: 14, height: 3, borderRadius: 2, background: COLORS[colorIndex % COLORS.length] }} /></td>
                        <td><span className="role-link">{roleTitle(meta, r.canonical_role)}<small className="role-en">{r.canonical_role}</small></span></td>
                        <td><TrendBadge trend={r.trend_direction || "flat"} /></td>
                        <td className="num mono">{(r.confidence * 100).toFixed(0)}%</td>
                        <td className="num">{r.predicted_demand_index.toFixed(4)}</td>
                        <td className="num" style={{ width: 30 }}><Ic.back style={{ width: 14, height: 14, transform: "rotate(180deg)", opacity: 0.35 }} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
