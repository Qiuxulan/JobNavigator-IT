import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getRoleCatalog, getTrendBatch } from "../api";
import { Ic } from "../components/Icons";
import { Card, StatCard } from "../components/Card";
import { CatBadge, TrendBadge, catColor } from "../components/Badge";

interface RoleRow {
  name: string;
  nameZh: string;
  category: string;
  trend: string;
  demand: number;
  confidence: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [sortKey, setSortKey] = useState<"demand" | "name">("demand");
  const perPage = 18;

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [catalog, signals] = await Promise.all([getRoleCatalog(), getTrendBatch(3)]);
        const signalMap = new Map(signals.map((s) => [s.canonical_role, s]));
        const rows: RoleRow[] = catalog.map((role) => {
          const signal = signalMap.get(role.role_name);
          return {
            name: role.role_name,
            nameZh: signal?.role_name_zh || role.role_name_zh || role.role_name,
            category: role.coarse_role,
            trend: signal?.trend_direction || "flat",
            demand: Math.max(0, Math.round((signal?.predicted_demand_index ?? 0) * 100)),
            confidence: signal?.confidence ?? 0,
          };
        });
        if (alive) setRoles(rows);
      } finally {
        if (alive) setLoading(false);
      }
    }
    void load();
    return () => { alive = false; };
  }, []);

  const stats = useMemo(() => {
    const up = roles.filter((r) => r.trend === "up").length;
    const down = roles.filter((r) => r.trend === "down").length;
    const flat = roles.length - up - down;
    const cats = new Set(roles.map((r) => r.category)).size;
    const hottest = roles.reduce<RoleRow | null>((best, r) => (!best || r.demand > best.demand ? r : best), null);
    return { total: roles.length, up, down, flat, cats, hottest };
  }, [roles]);

  const catScores = useMemo(() => {
    const map = new Map<string, RoleRow[]>();
    for (const role of roles) map.set(role.category, [...(map.get(role.category) || []), role]);
    return Array.from(map.entries()).map(([category, rows]) => {
      const score = rows.reduce((sum, row) => sum + row.demand, 0) / Math.max(1, rows.length);
      return { category, score, count: rows.length };
    }).sort((a, b) => b.score - a.score);
  }, [roles]);

  const filtered = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    return roles
      .filter((r) => !keyword || r.name.toLowerCase().includes(keyword) || r.nameZh.includes(q.trim()) || r.category.toLowerCase().includes(keyword))
      .sort((a, b) => sortKey === "demand" ? b.demand - a.demand : a.nameZh.localeCompare(b.nameZh, "zh-CN"));
  }, [roles, q, sortKey]);

  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const currentPage = Math.min(page, pages - 1);
  const view = filtered.slice(currentPage * perPage, currentPage * perPage + perPage);

  const pieOption = useMemo(() => ({
    tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: 0, left: "center", textStyle: { color: "#4c5159", fontSize: 14 }, icon: "circle" },
    series: [{
      type: "pie",
      radius: ["58%", "80%"],
      center: ["50%", "44%"],
      label: { show: true, position: "center", formatter: () => `{v|${stats.total}}\n{l|岗位总数}`, rich: {
        v: { fontSize: 42, fontWeight: 500, color: "#1b1d22" },
        l: { fontSize: 14, color: "#767b85", padding: [6, 0, 0, 0] },
      } },
      data: [
        { value: stats.up, name: "上升", itemStyle: { color: "#10B981" } },
        { value: stats.flat, name: "平稳", itemStyle: { color: "#3B82F6" } },
        { value: stats.down, name: "下降", itemStyle: { color: "#FB5566" } },
      ],
    }],
  }), [stats]);

  if (loading) return <div className="loading-center"><div className="spinner" />加载趋势数据...</div>;
  if (roles.length === 0) return <div className="loading-center">无法加载岗位数据，请确认后端已启动。</div>;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-eyebrow">Dashboard / Trend Overview</div>
        <div className="page-title">IT 岗位<span className="lite">趋势总览</span></div>
        <div className="page-sub">基于 PatchTST 模型未来 3 个月短期预测（高置信度），汇总 69 个细分岗位的需求趋势。点击岗位可查看 24 个月预测曲线。</div>
      </div>

      <div className="stat-grid">
        <StatCard icon={Ic.layers} solid label="已加载岗位" value={stats.total} unit="个" sub={<span><b>{stats.cats}</b> 个方向</span>} />
        <StatCard icon={Ic.up} label="上升趋势" value={stats.up} unit="个" sub={<span>占比 <b>{stats.total ? Math.round(stats.up / stats.total * 100) : 0}%</b></span>} />
        <StatCard icon={Ic.down} label="下降趋势" value={stats.down} unit="个" sub={<span>占比 <b>{stats.total ? Math.round(stats.down / stats.total * 100) : 0}%</b></span>} />
        <StatCard icon={Ic.flame} label="最高需求岗位" value={stats.hottest?.nameZh || "-"} sub={stats.hottest && <span>指数 <b>{stats.hottest.demand}</b></span>} />
      </div>

      <div className="grid-2">
        <Card title="分类趋势概览" desc="按岗位大类汇总平均需求指数">
          <div className="catbar-list">
            {catScores.map((c) => (
              <div className="catbar" key={c.category} onClick={() => navigate("/graph")}>
                <div className="catbar-name"><span className="dot-cat" style={{ background: catColor(c.category) }} />{c.category}</div>
                <div className="catbar-track"><div className="catbar-fill" style={{ width: `${Math.min(100, c.score)}%`, background: catColor(c.category) }} /></div>
                <div className="catbar-val">{c.score.toFixed(0)}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="整体趋势分布" desc="所有岗位的预测方向占比">
          <ReactECharts option={pieOption} style={{ height: 320 }} />
        </Card>
      </div>

      <Card
        title="岗位列表"
        desc={`${filtered.length} 个岗位，点击行查看预测曲线和证据`}
        action={
          <div className="row">
            <div className="seg">
              <button className={sortKey === "demand" ? "active" : ""} onClick={() => { setSortKey("demand"); setPage(0); }}>按需求</button>
              <button className={sortKey === "name" ? "active" : ""} onClick={() => { setSortKey("name"); setPage(0); }}>按名称</button>
            </div>
            <div className="search" style={{ width: 232 }}>
              <Ic.search />
              <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="搜索岗位或大类..." />
            </div>
          </div>
        }
      >
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th style={{ width: "38%" }}>岗位</th><th>大类</th><th>趋势</th><th className="num">置信度</th><th className="num" style={{ width: 170 }}>需求指数</th></tr></thead>
            <tbody>
              {view.map((r, i) => (
                <tr key={r.name} onClick={() => navigate(`/role/${encodeURIComponent(r.name)}`)}>
                  <td><span className="role-link"><span className="rank-no">{String(currentPage * perPage + i + 1).padStart(2, "0")}</span>{r.nameZh}<small className="role-en">{r.name}</small></span></td>
                  <td><CatBadge category={r.category} /></td>
                  <td><TrendBadge trend={r.trend} /></td>
                  <td className="num mono">{(r.confidence * 100).toFixed(0)}%</td>
                  <td className="num"><div className="demand-bar"><div className="demand-track"><div className="demand-fill" style={{ width: `${Math.min(100, r.demand)}%` }} /></div><span className="demand-num">{r.demand}</span></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <div className="pager-info">第 {currentPage * perPage + 1}-{Math.min((currentPage + 1) * perPage, filtered.length)} 条，共 {filtered.length} 条</div>
          <div className="pager-ctrl">
            <button className="pager-btn" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>‹</button>
            {Array.from({ length: pages }).slice(0, 7).map((_, i) => <button key={i} className={"pager-btn" + (i === currentPage ? " active" : "")} onClick={() => setPage(i)}>{i + 1}</button>)}
            <button className="pager-btn" disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)}>›</button>
          </div>
        </div>
      </Card>
    </div>
  );
}
