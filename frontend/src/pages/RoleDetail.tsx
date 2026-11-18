import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getNews } from "../api";
import type { NewsItem } from "../api";
import { Card, StatCard } from "../components/Card";
import { CatBadge } from "../components/Badge";
import { Ic } from "../components/Icons";
import { formatInt, formatUsd } from "../utils";
import { compareRoles, coarseZh, getMarketRole, getMarketRoles, pct } from "../market";
import type { CompareRow, MarketRoleDetail, MarketRoleRow, NameShare } from "../market";

/** 岗位详情 + 岗位对比（原“岗位对比”页并入此处）。 */

function Dist({ rows, color }: { rows: NameShare[]; color: string }) {
  if (!rows.length) return <div className="movers-empty">暂无数据</div>;
  const max = rows[0].share || 1;
  return (
    <div>
      {rows.map((r) => (
        <div className="mk-row" key={r.name} style={{ gridTemplateColumns: "minmax(70px,120px) 1fr 52px" }}>
          <span className="mk-name">{r.name}</span>
          <div className="mk-bar"><div className="mk-bar-fill" style={{ width: `${(r.share / max) * 100}%`, background: color }} /></div>
          <span className="mk-val">{pct(r.share, 0)}</span>
        </div>
      ))}
    </div>
  );
}

function SkillCompare({ detail }: { detail: MarketRoleDetail }) {
  const option = useMemo(() => {
    const cn = new Map((detail.cn?.top_skills || []).map((s) => [s.name, s.share]));
    const gl = new Map(detail.global.top_skills.map((s) => [s.name, s.share]));
    const names = Array.from(new Set([...(detail.cn?.top_skills || []).slice(0, 10).map((s) => s.name),
      ...detail.global.top_skills.slice(0, 6).map((s) => s.name)])).slice(0, 14).reverse();
    return {
      legend: { top: 0, data: ["国内在招", "海外样本"] },
      grid: { left: 120, right: 40, top: 30, bottom: 10 },
      tooltip: { trigger: "axis" as const, valueFormatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      xAxis: { type: "value", axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: "#eef0f4" } } },
      yAxis: { type: "category", data: names, axisTick: { show: false } },
      series: [
        { name: "国内在招", type: "bar", data: names.map((n) => cn.get(n) ?? 0), itemStyle: { color: "#4f6ef7", borderRadius: 3 }, barGap: "10%" },
        { name: "海外样本", type: "bar", data: names.map((n) => gl.get(n) ?? 0), itemStyle: { color: "#c3cad8", borderRadius: 3 } },
      ],
    };
  }, [detail]);
  return <ReactECharts option={option} style={{ height: 420 }} />;
}

function GlobalShare({ detail }: { detail: MarketRoleDetail }) {
  const series = detail.global.share_series;
  const option = useMemo(() => ({
    grid: { left: 52, right: 20, top: 20, bottom: 30 },
    tooltip: { trigger: "axis" as const, formatter: (p: { axisValue: string; value: number; dataIndex: number }[]) =>
      `${p[0].axisValue}<br/>占当月 JD ${(p[0].value * 100).toFixed(2)}%（${series[p[0].dataIndex].count}/${series[p[0].dataIndex].total}）` },
    xAxis: { type: "category", data: series.map((x) => x.month), axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(1)}%` }, splitLine: { lineStyle: { color: "#eef0f4" } } },
    series: [{ type: "line", smooth: true, symbol: "circle", symbolSize: 5, data: series.map((x) => x.share),
      lineStyle: { color: "#7a5cff", width: 2 }, itemStyle: { color: "#7a5cff" }, areaStyle: { color: "rgba(122,92,255,0.08)" } }],
  }), [series]);
  if (series.length < 3) return <div className="movers-empty">海外样本不足，暂不展示走势</div>;
  return <ReactECharts option={option} style={{ height: 240 }} />;
}

function ComparePanel({ base, allRoles }: { base: MarketRoleDetail; allRoles: MarketRoleRow[] }) {
  const [params, setParams] = useSearchParams();
  const picked = (params.get("vs") || "").split(",").filter(Boolean).slice(0, 3);
  const [rows, setRows] = useState<CompareRow[]>([]);
  const [adding, setAdding] = useState("");

  useEffect(() => {
    if (!picked.length) { setRows([]); return; }
    compareRoles([base.role_id, ...picked]).then((r) => setRows(r.roles)).catch(() => setRows([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base.role_id, params]);

  const setPicked = (ids: string[]) => {
    const next = new URLSearchParams(params);
    if (ids.length) next.set("vs", ids.join(",")); else next.delete("vs");
    setParams(next, { replace: true });
  };

  const options = allRoles.filter((r) => r.role_id !== base.role_id && !picked.includes(r.role_id));
  const metric: { label: string; render: (r: CompareRow) => React.ReactNode }[] = [
    { label: "国内在招岗位", render: (r) => <b className="mono">{formatInt(r.cn_open_roles)}</b> },
    { label: "招聘最多的公司", render: (r) => r.cn_top_companies.join("、") || "—" },
    { label: "主要城市", render: (r) => r.cn_top_cities.join("、") || "—" },
    { label: "国内高频技能", render: (r) => <div className="mk-tags" style={{ marginTop: 0 }}>{r.cn_top_skills.map((s) => <span className="mk-tag" key={s}>{s}</span>)}</div> },
    { label: "经验要求（已注明的岗位）", render: (r) => {
      const known = r.cn_experience.filter((e) => e.name !== "未注明");
      const total = known.reduce((a, b) => a + b.count, 0);
      return known.length ? known.slice(0, 3).map((e) => `${e.name} ${Math.round((e.count / total) * 100)}%`).join(" · ") : "—";
    } },
    { label: "海外样本 JD 数", render: (r) => <span className="mono">{formatInt(r.global_jd_count)}</span> },
    { label: "海外薪资中位数（美元，参考）", render: (r) => <span className="mono">{formatUsd(r.global_salary_usd_median)}</span> },
  ];

  return (
    <Card title="岗位对比" desc="把当前岗位与最多 3 个岗位并排比较国内需求、技能和经验要求"
      action={
        <div className="row">
          <select className="select" style={{ width: 220 }} value={adding} disabled={picked.length >= 3}
            onChange={(e) => { if (e.target.value) setPicked([...picked, e.target.value]); setAdding(""); }}>
            <option value="">{picked.length >= 3 ? "最多对比 3 个岗位" : "+ 添加对比岗位"}</option>
            {options.map((r) => <option key={r.role_id} value={r.role_id}>{r.role_zh}（国内 {r.cn_open_roles}）</option>)}
          </select>
        </div>
      }
      style={{ marginBottom: 20 }}>
      {!picked.length && <div className="movers-empty">从右上角选择岗位开始对比，例如把“AI 智能体工程师”和“后端开发”放在一起看。</div>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="tbl cmp-tbl">
            <thead>
              <tr>
                <th style={{ width: 170 }}>指标</th>
                {rows.map((r, i) => (
                  <th key={r.role_id}>
                    {r.role_zh}
                    {i > 0 && <button className="btn ghost sm" style={{ marginLeft: 6 }} onClick={() => setPicked(picked.filter((x) => x !== r.role_id))}>移除</button>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metric.map((m) => (
                <tr key={m.label} style={{ cursor: "default" }}>
                  <td className="muted">{m.label}</td>
                  {rows.map((r) => <td key={r.role_id}>{m.render(r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function RoleDetail() {
  const { roleName = "" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<MarketRoleDetail | null>(null);
  const [allRoles, setAllRoles] = useState<MarketRoleRow[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    getMarketRoles().then((r) => setAllRoles(r.roles)).catch(() => setAllRoles([]));
  }, []);

  useEffect(() => {
    if (!roleName) return;
    let alive = true;
    setDetail(null);
    setError("");
    getMarketRole(decodeURIComponent(roleName))
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        getNews({ q: d.role_zh.replace(/工程师|开发|专家/g, "").trim() || d.role_name, pageSize: 6, hours: 24 * 60 })
          .then((r) => alive && setNews(r.items || []))
          .catch(() => alive && setNews([]));
      })
      .catch(() => alive && setError("未找到该岗位，请从下方列表重新选择。"));
    return () => { alive = false; };
  }, [roleName]);

  const hits = useMemo(() => {
    const kw = query.trim().toLowerCase();
    if (!kw) return [];
    return allRoles.filter((r) => r.role_zh.toLowerCase().includes(kw) || r.role_name.toLowerCase().includes(kw)).slice(0, 8);
  }, [allRoles, query]);

  const picker = (
    <div className="search" style={{ width: 280, position: "relative" }}>
      <Ic.search />
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="切换岗位：搜索中文或英文名" />
      {hits.length > 0 && (
        <div className="rd-suggest">
          {hits.map((r) => (
            <button key={r.role_id} onClick={() => { setQuery(""); navigate(`/role/${r.role_id}`); }}>
              {r.role_zh}<small>国内 {r.cn_open_roles}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );

  if (!roleName) {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-eyebrow">Role Insight / 岗位洞察</div>
          <div className="page-title">岗位<span className="lite">洞察与对比</span></div>
          <div className="page-sub">选择一个岗位，查看国内在招情况、技能要求、主要公司和城市，并可与其他岗位并排对比。</div>
        </div>
        <Card title="选择岗位" action={picker}>
          <div className="mk-tags">
            {allRoles.slice(0, 30).map((r) => (
              <button key={r.role_id} className="mk-tag clickable" onClick={() => navigate(`/role/${r.role_id}`)}>
                {r.role_zh} · {r.cn_open_roles}
              </button>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  if (error) return <div className="page"><div className="error-box">{error}</div><button className="btn" onClick={() => navigate("/role")}>返回岗位列表</button></div>;
  if (!detail) return <div className="loading-center"><div className="spinner" />加载岗位数据...</div>;

  const cn = detail.cn;
  const g = detail.global;
  const exp = (cn?.experience || []).filter((e) => e.name !== "未注明");
  const expTotal = exp.reduce((a, b) => a + b.count, 0);

  return (
    <div className="page">
      <div className="page-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 20, flexWrap: "wrap" }}>
        <div>
          <button className="btn ghost sm" onClick={() => navigate(-1)} style={{ marginBottom: 12 }}><Ic.back /> 返回</button>
          <div className="page-title">{detail.role_zh}<span className="lite" style={{ fontSize: "0.55em", marginLeft: 12 }}>{detail.role_name}</span></div>
          <div className="page-sub" style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <CatBadge category={detail.coarse_role} /> {coarseZh(detail.coarse_role)} · 国内数据截至 {detail.as_of}
          </div>
        </div>
        {picker}
      </div>

      <div className="stat-grid">
        <StatCard icon={Ic.layers} solid label="国内在招岗位" value={cn ? formatInt(cn.open_roles) : "—"} unit={cn ? "个" : undefined}
          sub={cn ? <span>占国内 IT 在招 <b>{pct(cn.share)}</b></span> : "6 家大厂官网暂无该方向岗位"} />
        <StatCard icon={Ic.dash} label="招聘最多的公司" value={cn?.companies[0]?.name || "—"}
          sub={cn ? cn.companies.slice(1, 4).map((c) => c.name).join("、") || "—" : "—"} />
        <StatCard icon={Ic.target} label="主要城市" value={cn?.cities[0]?.name || "—"}
          sub={cn ? cn.cities.slice(1, 4).map((c) => c.name).join("、") || "—" : "—"} />
        <StatCard icon={Ic.user} label="经验要求（已注明岗位）"
          value={exp.length ? exp.slice().sort((a, b) => b.count - a.count)[0].name : "—"}
          sub={exp.length ? exp.slice(0, 3).map((e) => `${e.name} ${Math.round((e.count / expTotal) * 100)}%`).join(" · ") : "多数岗位未注明年限"} />
      </div>

      <div className="grid-2">
        <Card title="技能要求：国内 vs 海外" desc="国内 = 官网在招岗位要求该技能的比例；海外 = 全球 JD 样本中的比例">
          {cn || g.top_skills.length ? <SkillCompare detail={detail} /> : <div className="movers-empty">暂无技能数据</div>}
        </Card>
        <Card title="国内公司与城市分布" desc="同一岗位在不同公司、城市的招聘量">
          <div className="mk-sub">公司</div>
          <Dist rows={cn?.companies.slice(0, 6) || []} color="#4f6ef7" />
          <div className="mk-sub" style={{ marginTop: 16 }}>城市</div>
          <Dist rows={(cn?.cities || []).filter((c) => c.name !== "未注明").slice(0, 6)} color="#33cfd5" />
        </Card>
      </div>

      <Card title="正在招聘的岗位" desc="来自公司官网的真实岗位，点击直达投递页面" style={{ marginBottom: 20 }}>
        {cn?.samples.length ? (
          <div className="rd-jobs">
            {cn.samples.map((s, i) => (
              <a key={i} className="rd-job" href={s.url} target="_blank" rel="noreferrer">
                <b>{s.title}</b>
                <span>{s.company} · {s.city || "多地"}{s.posted_at ? ` · ${s.posted_at}` : ""}</span>
                <Ic.ext />
              </a>
            ))}
          </div>
        ) : <div className="movers-empty">暂无国内在招岗位</div>}
      </Card>

      <ComparePanel base={detail} allRoles={allRoles} />

      <div className="grid-2">
        <Card title="海外需求占比走势（参考）" desc={`该岗位 JD 占海外样本当月总量的比例，只取样本量 ≥1000 的月份；${g.share_change_3m !== null ? `近 3 月较前 3 月 ${g.share_change_3m >= 0 ? "+" : ""}${(g.share_change_3m * 100).toFixed(0)}%` : ""}`}>
          <GlobalShare detail={detail} />
          <div className="data-note">{g.note}</div>
        </Card>
        <Card title="海外薪资与相关新闻" desc="薪资为海外岗位美元年薪，仅作国际参考">
          {g.salary_usd ? (
            <div className="rd-salary">
              <div><small>P25</small><b>{formatUsd(g.salary_usd.p25)}</b></div>
              <div className="mid"><small>中位数</small><b>{formatUsd(g.salary_usd.median)}</b></div>
              <div><small>P75</small><b>{formatUsd(g.salary_usd.p75)}</b></div>
              <span className="muted">样本 {formatInt(g.salary_usd.sample_size)} 条</span>
            </div>
          ) : <div className="movers-empty">海外薪资样本不足</div>}
          <div className="mk-sub" style={{ marginTop: 16 }}>相关新闻</div>
          {news.length ? news.map((n) => (
            <a key={n.news_id} className="rd-news" href={n.url} target="_blank" rel="noreferrer">
              <span>{n.title}</span><small>{n.source} · {String(n.published_at || "").slice(0, 10)}</small>
            </a>
          )) : <div className="movers-empty">近期暂无直接相关新闻</div>}
        </Card>
      </div>
    </div>
  );
}
