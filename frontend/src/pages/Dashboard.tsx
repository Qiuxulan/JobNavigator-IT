import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  getCompanies,
  getCompanyDetail,
  getHiringOverview,
  getSkillTrendDetail,
  getSkillTrends,
} from "../api";
import { coarseZh, getMarketOverview, getMarketRoles, pct } from "../market";
import type { MarketOverview, MarketRoleRow } from "../market";
import type {
  CompanyDetail,
  CompanyListItem,
  HiringCompany,
  HiringCompanyMomentum,
  HiringLayoffs,
  HiringOverview,
  HnHiring,
  SkillTrendDetail,
  SkillTrendsOverview,
} from "../api";
import { Ic } from "../components/Icons";
import { Card, StatCard } from "../components/Card";
import { CatBadge, CompanyStatusBadge, catColor } from "../components/Badge";
import { formatInt, formatUsd } from "../utils";

const STATUS_ZH: Record<string, string> = {
  emerging: "新兴",
  growing: "增长",
  stable: "平稳",
  declining: "衰退",
  insufficient_data: "数据不足",
};

const METHOD_ZH: Record<string, string> = {
  holt: "Holt 指数平滑",
  "chronos-bolt": "Chronos-Bolt 时序基础模型",
  theta: "Theta",
  ets: "ETS",
  naive: "朴素法",
  seasonal_naive: "季节朴素法",
  patchtst: "PatchTST",
};

function statusBadgeClass(status: string): string {
  if (status === "emerging") return "badge conf-mid";
  if (status === "growing") return "badge up";
  if (status === "declining") return "badge down";
  return "badge neutral";
}

function fmtMomentum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function addMonths(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, (m - 1) + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}



function buildShareOption(detail: SkillTrendDetail | null) {
  const rows = (detail?.monthly || []).slice(-24);
  const histMonths = rows.map((r) => r.month || "");
  const histShares = rows.map((r) => (r.share === null || r.share === undefined ? null : r.share));
  const fc = detail?.forecast;
  const lastMonth = histMonths[histMonths.length - 1] || detail?.analysis_end || "";
  const fcMonths = fc && lastMonth
    ? [1, 2, 3, 4, 5, 6].map((d) => `${addMonths(lastMonth, d)}(预测)`)
    : [];
  const xData = [...histMonths, ...fcMonths];
  const histData = [...histShares, ...fcMonths.map(() => null)];
  let fcData: (number | null)[] = [];
  if (fc && fc.m3 !== null && fc.m3 !== undefined && fc.m6 !== null && fc.m6 !== undefined && lastMonth) {
    const lastShare = histShares[histShares.length - 1];
    fcData = [
      ...histMonths.slice(0, -1).map(() => null),
      lastShare ?? null,
      null, null, fc.m3,
      null, null, fc.m6,
    ];
  }
  return {
    tooltip: {
      trigger: "axis" as const,
      valueFormatter: (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(2)}%` : "—"),
    },
    grid: { left: 56, right: 20, top: 34, bottom: 28 },
    xAxis: { type: "category" as const, data: xData, axisLabel: { color: "#767b85", fontSize: 11 } },
    yAxis: {
      type: "value" as const,
      axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      splitLine: { lineStyle: { color: "#ececef" } },
    },
    legend: { top: 0, right: 8, textStyle: { color: "#4c5159", fontSize: 12 }, icon: "circle" },
    series: [
      {
        name: "JD 份额（历史）",
        type: "line",
        data: histData,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2.2, color: "#3B82F6" },
        itemStyle: { color: "#3B82F6" },
        connectNulls: false,
      },
      ...(fcData.length
        ? [{
            name: "份额预测",
            type: "line" as const,
            data: fcData,
            showSymbol: true,
            symbolSize: 5,
            lineStyle: { width: 2, type: "dashed" as const, color: "#B45309" },
            itemStyle: { color: "#B45309" },
            connectNulls: true,
          }]
        : []),
    ],
  };
}

function buildCompOption(detail: SkillTrendDetail | null) {
  const rows = (detail?.monthly || []).slice(-24);
  const months = rows.map((r) => r.month || "");
  const salaries = rows.map((r) => (r.salary_median === null || r.salary_median === undefined ? null : r.salary_median));
  const remotes = rows.map((r) => (r.remote_share === null || r.remote_share === undefined ? null : r.remote_share));
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: Array<{ seriesName: string; value: number | null }>) => {
        const parts = params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `${p.seriesName}：${p.seriesName.includes("远程") ? `${(Number(p.value) * 100).toFixed(1)}%` : formatUsd(Number(p.value))}`);
        return parts.length ? parts.join("<br/>") : "该月样本不足";
      },
    },
    grid: { left: 64, right: 52, top: 34, bottom: 28 },
    xAxis: { type: "category" as const, data: months, axisLabel: { color: "#767b85", fontSize: 11 } },
    yAxis: [
      {
        type: "value" as const,
        name: "薪资",
        axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => `$${Math.round(v / 1000)}k` },
        splitLine: { lineStyle: { color: "#ececef" } },
      },
      {
        type: "value" as const,
        name: "远程",
        min: 0,
        max: 1,
        axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => `${Math.round(v * 100)}%` },
        splitLine: { show: false },
      },
    ],
    legend: { top: 0, right: 8, textStyle: { color: "#4c5159", fontSize: 12 }, icon: "circle" },
    series: [
      {
        name: "薪资中位数",
        type: "line",
        data: salaries,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2.2, color: "#10B981" },
        itemStyle: { color: "#10B981" },
        connectNulls: true,
      },
      {
        name: "远程岗位比例",
        type: "line",
        yAxisIndex: 1,
        data: remotes,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: "#8b7bb8" },
        itemStyle: { color: "#8b7bb8" },
        connectNulls: true,
      },
    ],
  };
}

function buildHnHiringOption(hn: HnHiring | null) {
  const rows = (hn?.months || []).slice(-24);
  const months = rows.map((r) => r.month || "");
  const posts = rows.map((r) => r.n_job_posts ?? 0);
  const remotes = rows.map((r) => (r.remote_ratio === null || r.remote_ratio === undefined ? null : +(r.remote_ratio * 100).toFixed(1)));
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: Array<{ seriesName: string; value: number | null }>) => {
        const parts = params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `${p.seriesName}：${p.seriesName.includes("远程") ? `${Number(p.value).toFixed(1)}%` : formatInt(Number(p.value))}`);
        return parts.length ? parts.join("<br/>") : "该月数据缺失";
      },
    },
    grid: { left: 52, right: 52, top: 34, bottom: 28 },
    xAxis: { type: "category" as const, data: months, axisLabel: { color: "#767b85", fontSize: 11 } },
    yAxis: [
      {
        type: "value" as const,
        name: "岗位帖",
        axisLabel: { color: "#767b85", fontSize: 11 },
        splitLine: { lineStyle: { color: "#ececef" } },
      },
      {
        type: "value" as const,
        name: "远程",
        min: 0,
        max: 100,
        axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => `${v}%` },
        splitLine: { show: false },
      },
    ],
    legend: { top: 0, right: 8, textStyle: { color: "#4c5159", fontSize: 12 }, icon: "circle" },
    series: [
      {
        name: "招聘帖数量",
        type: "bar",
        data: posts,
        barMaxWidth: 18,
        itemStyle: { color: "#3B82F6", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "远程岗位比例",
        type: "line",
        yAxisIndex: 1,
        data: remotes,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: "#8b7bb8" },
        itemStyle: { color: "#8b7bb8" },
        connectNulls: true,
      },
    ],
  };
}

function buildLayoffOption(layoffs: HiringLayoffs | null) {
  const rows = (layoffs?.recent_months || []).slice(-12);
  const months = rows.map((r) => r.month || "");
  const affected = rows.map((r) => r.employees_affected ?? 0);
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: Array<{ seriesName: string; value: number | null }>) => {
        const parts = params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `${p.seriesName}：${formatInt(Number(p.value))} 人`);
        return parts.length ? parts.join("<br/>") : "该月数据缺失";
      },
    },
    grid: { left: 56, right: 16, top: 30, bottom: 28 },
    xAxis: { type: "category" as const, data: months, axisLabel: { color: "#767b85", fontSize: 11 } },
    yAxis: {
      type: "value" as const,
      axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)) },
      splitLine: { lineStyle: { color: "#ececef" } },
    },
    series: [{
      name: "受影响人数",
      type: "bar",
      data: affected,
      barMaxWidth: 22,
      itemStyle: { color: "#FB5566", borderRadius: [3, 3, 0, 0] },
    }],
  };
}

function buildCompanyRolesOption(detail: CompanyDetail | null) {
  const rows = detail?.open_roles_daily || [];
  const dates = rows.map((r) => (r.date || "").slice(5));
  const counts = rows.map((r) => r.count ?? 0);
  const windowLabel = detail?.window?.length === 2 ? `${detail.window[0]} ~ ${detail.window[1]}` : "近 28 天";
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: Array<{ seriesName: string; value: number | null }>) => {
        const parts = params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `${p.seriesName}：${formatInt(Number(p.value))} 个`);
        return parts.length ? parts.join("<br/>") : "该日数据缺失";
      },
    },
    grid: { left: 52, right: 16, top: 34, bottom: 28 },
    xAxis: { type: "category" as const, data: dates, axisLabel: { color: "#767b85", fontSize: 11 } },
    yAxis: {
      type: "value" as const,
      name: "在招岗位",
      axisLabel: { color: "#767b85", fontSize: 11, formatter: (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)) },
      splitLine: { lineStyle: { color: "#ececef" } },
    },
    series: [{
      name: "在招岗位",
      type: "bar",
      data: counts,
      barMaxWidth: 14,
      itemStyle: {
        borderRadius: [3, 3, 0, 0],
        color: {
          type: "linear" as const,
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "#7a5cff" },
            { offset: 1, color: "#4f6ef7" },
          ],
        },
      },
    }],
    graphic: rows.length ? [] : [{ type: "text" as const, left: "center", top: "middle", style: { text: `${windowLabel} 暂无每日数据`, fill: "#a3a8b1", fontSize: 13 } }],
  };
}

function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(0)}`;
}

function deltaClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "";
  return v > 0 ? "up" : "down";
}

function relativeDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const d = Math.floor((Date.now() - t) / 86_400_000);
  if (d <= 0) return "今天";
  if (d === 1) return "昨天";
  if (d < 30) return `${d} 天前`;
  return new Date(t).toLocaleDateString("zh-CN");
}

const SECTOR_COLORS: Record<string, string> = {
  AI: "#9B72F0",
  "数据/云": "#33CFD5",
  金融科技: "#1FC8A9",
  "消费/平台": "#FFB13D",
  "安全/企业软件": "#FF7A90",
  开发者工具: "#6E8AFF",
};
const SECTOR_FALLBACK = ["#5B8DEF", "#86CB3C", "#FF9466", "#FF6FA5", "#8A72F0"];

function sectorColor(sector: string | null | undefined): string {
  if (!sector) return "#9aa0a9";
  if (SECTOR_COLORS[sector]) return SECTOR_COLORS[sector];
  let h = 0;
  for (let i = 0; i < sector.length; i++) h = (h * 31 + sector.charCodeAt(i)) >>> 0;
  return SECTOR_FALLBACK[h % SECTOR_FALLBACK.length];
}

function HiringSection({ hiring, failed, bare = false }: { hiring: HiringOverview | null; failed: boolean; bare?: boolean }) {
  const momentum: HiringCompanyMomentum | null = hiring?.company_momentum ?? null;
  const layoffs: HiringLayoffs | null = hiring?.layoffs ?? null;
  const hn: HnHiring | null = hiring?.hn_hiring ?? null;
  const companies: HiringCompany[] = (momentum?.top || []).slice(0, 10);
  const employers = (layoffs?.top_recent_employers || []).slice(0, 10);
  const generated = hiring?.generated_at ? hiring.generated_at.slice(0, 16).replace("T", " ") : "—";

  const [tagByDomain, setTagByDomain] = useState<Map<string, CompanyListItem> | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  // 公司状态标签（扩张/降温/平稳/裁员备案）来自 /v1/companies；失败时静默降级为无胶囊
  useEffect(() => {
    let alive = true;
    getCompanies()
      .then((list) => {
        if (!alive) return;
        setTagByDomain(new Map(list.filter((c) => c.domain).map((c) => [c.domain, c])));
      })
      .catch(() => { if (alive) setTagByDomain(new Map()); });
    return () => { alive = false; };
  }, []);

  const empty = (text = "数据更新中") => <div className="movers-empty">{text}</div>;

  return (
    <div className={bare ? "" : "card"} style={bare ? undefined : { marginBottom: 20 }}>
      {(!hiring || failed) && !hiring?.company_momentum && !hiring?.layoffs && !hiring?.hn_hiring
        ? <div className="error-box">招聘风向标数据更新中，请稍后刷新查看。</div>
        : (
          <>
            <div className="profile-label">HN &quot;Who is Hiring&quot; 月度招聘帖</div>
            {hn?.months?.length
              ? <ReactECharts option={buildHnHiringOption(hn)} style={{ height: 300, marginBottom: 22 }} />
              : empty()}

            <div className="profile-label">公司招聘动能榜 · Top 10<span className="hiring-hint">点击行查看公司雷达</span></div>
            {companies.length ? (
              <div className="hiring-list" style={{ marginBottom: 22 }}>
                {companies.map((c, i) => {
                  const delta = c.momentum_30d?.delta;
                  const pct = c.momentum_30d?.pct;
                  const tag = c.domain ? tagByDomain?.get(c.domain) : undefined;
                  return (
                    <button
                      className="hiring-row hiring-row-link"
                      key={c.domain || c.company || i}
                      disabled={!c.domain}
                      onClick={() => c.domain && setSelectedDomain(c.domain)}
                      title={c.domain ? `查看 ${c.company || c.domain} 的 28 天招聘雷达` : undefined}
                    >
                      <span className="rank-no">{String(i + 1).padStart(2, "0")}</span>
                      <span className="hiring-cname">{c.company || c.domain}<small className="role-en">{c.domain}</small></span>
                      <span className="hiring-sector" style={{ color: sectorColor(c.sector), background: `${sectorColor(c.sector)}1a` }}>{c.sector || "其他"}</span>
                      <CompanyStatusBadge status={tag?.status_tag} />
                      <span className="hiring-roles">{formatInt(c.latest_open_roles ?? null)} 在招</span>
                      {delta === null || delta === undefined
                        ? <span className="mover-delta">—</span>
                        : (
                          <span
                            className="mover-delta"
                            style={delta < 0 ? { color: "var(--ink-4)" } : undefined}
                            title={pct !== null && pct !== undefined ? `30 日 ${(pct * 100).toFixed(1)}%` : undefined}
                          >
                            {delta > 0 ? "▲ +" : delta < 0 ? "▼ " : ""}{delta.toFixed(0)}
                          </span>
                        )}
                      <Ic.back className="hiring-chevron" style={{ transform: "rotate(180deg)" }} />
                    </button>
                  );
                })}
              </div>
            ) : empty()}

            <div className="hiring-grid">
              <div>
                <div className="profile-label">裁员信号 · 近 12 个月 WARN 受影响人数</div>
                {layoffs?.recent_months?.length
                  ? <ReactECharts option={buildLayoffOption(layoffs)} style={{ height: 280 }} />
                  : empty()}
              </div>
              <div>
                <div className="profile-label">近 18 月裁员雇主 Top {employers.length || ""}</div>
                {employers.length ? (
                  <div className="hiring-list">
                    {employers.map((e, i) => (
                      <div className="hiring-row" key={`${e.employer}-${i}`}>
                        <span className="rank-no">{String(i + 1).padStart(2, "0")}</span>
                        <span className="hiring-cname">{e.employer}</span>
                        <span className="hiring-emp-month">{e.month}</span>
                        <span className="mover-delta down">{formatInt(e.employees_affected ?? null)}</span>
                      </div>
                    ))}
                  </div>
                ) : empty()}
              </div>
            </div>
            <div className="data-note">
              公司动能基于 {momentum?.n_companies ?? "—"} 家公司官网招聘页近 30 天岗位净增（窗口 {momentum?.window?.[0] || "—"} ~ {momentum?.window?.[1] || "—"}）；
              HN 数据来自 Hacker News &quot;Who is Hiring&quot; 月度帖（远程/薪资披露为帖内自述比例）；
              裁员数据来自美国各州 WARN 公告（累计 {formatInt(layoffs?.n_notices ?? null)} 条）。风向标生成于 {generated}。
            </div>
          </>
        )}
      {selectedDomain && (
        <CompanyDrawer
          domain={selectedDomain}
          listItem={tagByDomain?.get(selectedDomain)}
          onClose={() => setSelectedDomain(null)}
        />
      )}
    </div>
  );
}

function CompanyDrawer({ domain, listItem, onClose }: { domain: string; listItem?: CompanyListItem; onClose: () => void }) {
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    getCompanyDetail(domain)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [domain]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rolesOption = useMemo(() => buildCompanyRolesOption(detail), [detail]);
  const d = detail;
  const mom7 = d?.momentum_7d?.delta;
  const mom30 = d?.momentum_30d?.delta;
  const layoffRows = d?.layoff_events ?? [];
  const newsRows = (d?.related_news ?? []).slice(0, 10);

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-hd">
          <div className="spread">
            <div>
              <div className="drawer-title">
                {d?.name || listItem?.name || domain}
                <CompanyStatusBadge status={d?.status_tag ?? listItem?.status_tag} />
              </div>
              <div className="drawer-sub">
                {domain}{(d?.sector || listItem?.sector) ? ` · ${d?.sector || listItem?.sector}` : ""} · 公司招聘雷达
              </div>
            </div>
            <button className="btn ghost sm" onClick={onClose}>关闭 ✕</button>
          </div>
        </div>
        <div className="drawer-bd">
          {!detail && !failed && (
            <div className="company-skel" aria-label="加载中">
              <div className="company-skel-metrics">
                {[0, 1, 2].map((n) => <div className="skel" key={n} style={{ height: 74 }} />)}
              </div>
              <div className="skel" style={{ width: "100%", height: 280, borderRadius: 14 }} />
            </div>
          )}
          {failed && <div className="error-box">公司雷达数据更新中，请稍后重试。</div>}
          {d && (
            <>
              <div className="wind-metrics">
                <div className="wind-metric">
                  <span>最新在招岗位</span>
                  <b>{formatInt(d.latest_open_roles ?? null)}</b>
                </div>
                <div className="wind-metric">
                  <span>近 30 天日均在招</span>
                  <b>{d.open_roles_avg_30d !== null && d.open_roles_avg_30d !== undefined ? d.open_roles_avg_30d.toFixed(0) : "—"}</b>
                </div>
                <div className="wind-metric">
                  <span>在招动量 · 7 日 / 30 日</span>
                  <b>
                    <i className={"company-delta " + deltaClass(mom7)}>{fmtDelta(mom7)}</i>
                    {" / "}
                    <i className={"company-delta " + deltaClass(mom30)}>{fmtDelta(mom30)}</i>
                  </b>
                </div>
              </div>

              <div className="profile-label">在招岗位 · 近 28 天每日快照</div>
              <ReactECharts option={rolesOption} style={{ height: 280, marginBottom: 22 }} />

              <div className="profile-label">WARN 裁员备案 · 近 12 个月</div>
              {layoffRows.length ? (
                <div className="table-wrap" style={{ marginBottom: 22 }}>
                  <table className="tbl">
                    <thead>
                      <tr><th>月份</th><th>雇主</th><th className="num">受影响人数</th><th>州</th></tr>
                    </thead>
                    <tbody>
                      {layoffRows.map((e, i) => (
                        <tr key={`${e.month}-${e.employer}-${i}`} style={{ cursor: "default" }}>
                          <td className="mono">{e.month || "—"}</td>
                          <td>{e.employer || "—"}</td>
                          <td className="num">{formatInt(e.employees_affected ?? null)}</td>
                          <td>{e.states?.length ? e.states.join(", ") : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="movers-empty">近 12 个月无 WARN 裁员备案记录。</div>}

              <div className="profile-label">相关新闻 · 最近 {newsRows.length || ""} 条</div>
              {newsRows.length ? (
                <div className="company-news-list">
                  {newsRows.map((n, i) => (
                    <a
                      className="company-news-item"
                      key={n.url || `${n.title}-${i}`}
                      href={n.url || undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <span className="company-news-title">{n.title}</span>
                      <span className="company-news-meta">
                        {n.source && <span className="news-card-src">{n.source}</span>}
                        <span className="news-card-time">{relativeDay(n.published_at)}</span>
                        <Ic.ext className="company-news-ext" />
                      </span>
                    </a>
                  ))}
                </div>
              ) : <div className="movers-empty">近期无相关新闻。</div>}

              <div className="data-note">
                公司雷达基于官网招聘页每日抓取的在招岗位数；窗口 {d.window?.[0] || "—"} ~ {d.window?.[1] || "—"}，
                生成于 {d.generated_at ? d.generated_at.slice(0, 16).replace("T", " ") : "—"}。裁员备案来自美国各州 WARN 公告。
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillDrawer({ skill, onClose }: { skill: string; onClose: () => void }) {
  const [detail, setDetail] = useState<SkillTrendDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setDetail(null);
    setFailed(false);
    getSkillTrendDetail(skill)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [skill]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shareOption = useMemo(() => buildShareOption(detail), [detail]);
  const compOption = useMemo(() => buildCompOption(detail), [detail]);
  const fc = detail?.forecast;
  const mom = detail?.momentum_3m;
  const momClass = mom === null || mom === undefined ? "" : mom > 0 ? "up" : mom < 0 ? "down" : "";

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-hd">
          <div className="spread">
            <div>
              <div className="drawer-title">
                {detail?.name || skill}
                {detail && <span className={statusBadgeClass(detail.status)} style={{ marginLeft: 10 }}>{STATUS_ZH[detail.status] || detail.status}</span>}
              </div>
              <div className="drawer-sub">{skill} · 月度 JD 份额面板</div>
            </div>
            <button className="btn ghost sm" onClick={onClose}>关闭 ✕</button>
          </div>
        </div>
        <div className="drawer-bd">
          {!detail && !failed && <div className="loading-center"><div className="spinner" />加载技能详情...</div>}
          {failed && <div className="error-box">技能详情加载失败，请稍后重试。</div>}
          {detail && (
            <>
              <div className="wind-metrics">
                <div className="wind-metric"><span>近 3 月动量</span><b className={momClass}>{fmtMomentum(mom)}</b></div>
                <div className="wind-metric"><span>同比（YoY）</span><b>{fmtMomentum(detail.yoy)}</b></div>
                <div className="wind-metric"><span>最新月 JD 份额</span><b>{fmtPct(detail.monthly[detail.monthly.length - 1]?.share)}</b></div>
                <div className="wind-metric"><span>预测 · 3 个月后</span><b>{fc ? fmtPct(fc.m3) : "—"}</b></div>
                <div className="wind-metric"><span>预测 · 6 个月后</span><b>{fc ? fmtPct(fc.m6) : "—"}</b></div>
                <div className="wind-metric"><span>回测 MAPE</span><b>{fc?.mape !== null && fc?.mape !== undefined ? `${(fc.mape * 100).toFixed(0)}%` : "—"}</b></div>
              </div>
              <div className="profile-label">JD 份额 · 历史与预测</div>
              <ReactECharts option={shareOption} style={{ height: 300, marginBottom: 22 }} />
              <div className="profile-label">薪资中位数与远程岗位比例</div>
              <ReactECharts option={compOption} style={{ height: 280, marginBottom: 18 }} />
              <div className="data-note">
                {fc
                  ? <>预测方法：{METHOD_ZH[fc.method || ""] || (fc.method ?? "未知")}；未来 3/6 月预测为模型点预测（虚线），回测 MAPE {(Number(fc.mape ?? 0) * 100).toFixed(0)}%。</>
                  : <>该技能历史数据不足，未生成预测；曲线仅展示真实历史值。</>}
                {detail.generated_at && <> 面板生成于 {detail.generated_at.slice(0, 16).replace("T", " ")}</>}
                {detail.analysis_end && <> · 分析截止 {detail.analysis_end}</>}。
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ShareBar({ value, max, color = "var(--brand)" }: { value: number; max: number; color?: string }) {
  return (
    <div className="mk-bar"><div className="mk-bar-fill" style={{ width: `${Math.max(2, (value / (max || 1)) * 100)}%`, background: color }} /></div>
  );
}

function CnSkillBoard({ data, onSkill }: { data: MarketOverview; onSkill: (s: string) => void }) {
  const top = data.top_skills.slice(0, 12);
  const max = top[0]?.share_cn || 1;
  return (
    <div className="mk-grid-2">
      <div>
        <div className="mk-sub">国内在招岗位要求最多的技能（占比 = 要求该技能的岗位 / 全部在招岗位）</div>
        {top.map((s, i) => (
          <div className="mk-row clickable" key={s.skill_id} onClick={() => onSkill(s.skill_id)}>
            <span className="rank-no">{String(i + 1).padStart(2, "0")}</span>
            <span className="mk-name">{s.name}</span>
            <ShareBar value={s.share_cn} max={max} />
            <span className="mk-val">{pct(s.share_cn)}</span>
          </div>
        ))}
      </div>
      <div>
        <div className="mk-sub">国内明显比海外更看重的技能（国内占比 / 海外样本占比）</div>
        {data.cn_hotter_skills.slice(0, 10).map((s) => (
          <div className="mk-row clickable" key={s.skill_id} onClick={() => onSkill(s.skill_id)}>
            <span className="mk-name">{s.name}</span>
            <span className="mk-pair"><b>{pct(s.share_cn)}</b><small>海外 {pct(s.share_global)}</small></span>
            <span className="badge up">×{s.share_global ? (s.share_cn / s.share_global).toFixed(1) : "—"}</span>
          </div>
        ))}
        {data.cn_hotter_skills.length === 0 && <div className="movers-empty">暂无</div>}
      </div>
    </div>
  );
}

function CnCompanyBoard({ data }: { data: MarketOverview }) {
  const max = Math.max(...data.companies.map((c) => c.open_roles), 1);
  return (
    <div className="mk-company-grid">
      {data.companies.map((c) => (
        <div className="mk-company" key={c.source}>
          <div className="mk-company-hd">
            <b>{c.company}</b>
            <span className="mono">{formatInt(c.open_roles)} <small>在招</small></span>
          </div>
          <ShareBar value={c.open_roles} max={max} />
          <div className="mk-company-meta">
            {c.days_observed >= 8 && c.momentum_7d !== null
              ? <span className={c.momentum_7d >= 0 ? "up" : "down"}>近 7 天 {c.momentum_7d >= 0 ? "+" : ""}{c.momentum_7d}</span>
              : <span className="muted">已连续采集 {c.days_observed} 天</span>}
            <span className="muted">{c.top_cities.slice(0, 3).map((x) => x.name).join(" · ")}</span>
          </div>
          <div className="mk-tags">
            {c.top_roles.slice(0, 4).map((r) => <span className="mk-tag" key={r.role_id}>{r.role_zh} {r.count}</span>)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [market, setMarket] = useState<MarketOverview | null>(null);
  const [roles, setRoles] = useState<MarketRoleRow[]>([]);
  const [skills, setSkills] = useState<SkillTrendsOverview | null>(null);
  const [hiring, setHiring] = useState<HiringOverview | null>(null);
  const [hiringFailed, setHiringFailed] = useState(false);
  const [region, setRegion] = useState<"cn" | "global">("cn");
  const [activeSkill, setActiveSkill] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [page, setPage] = useState(0);
  const perPage = 15;

  useEffect(() => {
    let alive = true;
    Promise.all([getMarketOverview(), getMarketRoles(), getSkillTrends().catch(() => null)])
      .then(([m, r, s]) => {
        if (!alive) return;
        setMarket(m);
        setRoles(r.roles);
        setSkills(s);
      })
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (region !== "global" || hiring || hiringFailed) return;
    getHiringOverview().then(setHiring).catch(() => setHiringFailed(true));
  }, [region, hiring, hiringFailed]);

  const cats = useMemo(() => Array.from(new Set(roles.map((r) => r.coarse_role))).filter(Boolean), [roles]);
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return roles.filter((r) => (cat === "all" || r.coarse_role === cat)
      && (!kw || r.role_zh.toLowerCase().includes(kw) || r.role_name.toLowerCase().includes(kw)));
  }, [roles, q, cat]);
  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const currentPage = Math.min(page, pages - 1);
  const view = filtered.slice(currentPage * perPage, currentPage * perPage + perPage);
  const maxOpen = Math.max(...roles.map((r) => r.cn_open_roles), 1);

  const coarseOption = useMemo(() => {
    if (!market) return {};
    const rows = market.summary.coarse_roles.slice(0, 10);
    return {
      tooltip: { trigger: "item" as const, formatter: "{b}：{c} 个（{d}%）" },
      series: [{
        type: "pie", radius: ["45%", "72%"], center: ["50%", "52%"], avoidLabelOverlap: true,
        label: { formatter: "{b}\n{d}%", fontSize: 12, color: "#4c5159" },
        data: rows.map((r) => ({ name: coarseZh(r.name), value: r.count, itemStyle: { color: catColor(r.name) } })),
      }],
    };
  }, [market]);

  const cityOption = useMemo(() => {
    if (!market) return {};
    const rows = market.summary.cities.filter((c) => c.name !== "未注明").slice(0, 8).reverse();
    return {
      grid: { left: 56, right: 48, top: 8, bottom: 8 },
      xAxis: { type: "value", show: false },
      yAxis: { type: "category", data: rows.map((r) => r.name), axisTick: { show: false }, axisLine: { show: false } },
      tooltip: { trigger: "axis" as const, formatter: (p: { name: string; value: number }[]) => `${p[0].name}：${p[0].value} 个岗位` },
      series: [{ type: "bar", data: rows.map((r) => r.count), barWidth: 14, itemStyle: { color: "#5b8def", borderRadius: 4 },
        label: { show: true, position: "right", formatter: "{c}", color: "#4c5159" } }],
    };
  }, [market]);

  if (loading) return <div className="loading-center"><div className="spinner" />加载国内市场数据...</div>;
  if (error || !market) {
    return (
      <div className={embedded ? "" : "page"}>
        <div className="cmp-empty">
          <div>数据加载失败，请确认后端服务已启动后刷新重试。</div>
          <button className="btn" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>重新加载</button>
        </div>
      </div>
    );
  }

  const s = market.summary;
  const aiShare = s.coarse_roles.find((c) => c.name === "Emerging AI")?.share ?? 0;
  const topCity = s.cities[0];

  const body = (
    <>
      <div className="stat-grid">
        <StatCard icon={Ic.layers} solid label="国内在招 IT 岗位" value={formatInt(s.open_roles)} unit="个"
          sub={<span>{s.n_companies} 家科技公司官网 · 截至 <b>{market.as_of}</b></span>} />
        <StatCard icon={Ic.flame} label="AI / 大模型方向" value={pct(aiShare, 0)}
          sub={<span>占全部在招岗位，大模型相关技能需求 <b>{pct(market.top_skills.find((x) => x.skill_id === "llm")?.share_cn)}</b></span>} />
        <StatCard icon={Ic.dash} label="岗位最集中城市" value={topCity?.name || "—"}
          sub={<span>占 <b>{pct(topCity?.share, 0)}</b>，其后 {s.cities.slice(1, 4).map((c) => c.name).join("、")}</span>} />
        <StatCard icon={Ic.spark} label="实时更新" value={`${market.days_observed} 天`}
          sub={<span>每日采集官网岗位，自 {market.first_day} 起累积</span>} />
      </div>

      <Card title="国内技能需求" desc={`来自 ${s.n_companies} 家公司官网直采 + 国聘平台（央企国企聚合）当天在招的 IT 岗位；点击技能查看全球趋势参考`}
        style={{ marginBottom: 20 }}>
        <CnSkillBoard data={market} onSkill={setActiveSkill} />
        {skills && skills.emerging.length > 0 && (
          <div className="mk-emerging">
            <span className="mk-sub" style={{ margin: 0 }}>海外样本中的新兴技能（参考）：</span>
            {skills.emerging.slice(0, 10).map((x) => (
              <button key={x.skill} className="mk-tag clickable" onClick={() => setActiveSkill(x.skill)}>{x.name}</button>
            ))}
          </div>
        )}
      </Card>

      <Card title="招聘风向标" desc={region === "cn" ? "国内科技公司官网每日在招 IT 岗位数与主要招聘方向" : "海外科技公司在招数、HN 招聘帖与美国裁员公告（国际参考）"}
        action={<div className="seg">
          <button className={region === "cn" ? "active" : ""} onClick={() => setRegion("cn")}>国内</button>
          <button className={region === "global" ? "active" : ""} onClick={() => setRegion("global")}>海外参考</button>
        </div>}
        style={{ marginBottom: 20 }}>
        {region === "cn" ? <CnCompanyBoard data={market} /> : <HiringSection hiring={hiring} failed={hiringFailed} bare />}
      </Card>

      <div className="grid-2">
        <Card title="岗位方向分布" desc="国内在招 IT 岗位按方向归类">
          <ReactECharts option={coarseOption} style={{ height: 320 }} />
        </Card>
        <Card title="城市分布" desc="在招岗位数最多的城市（一个岗位可在多城招聘，按首选城市计）">
          <ReactECharts option={cityOption} style={{ height: 320 }} />
        </Card>
      </div>

      <Card title="岗位榜单" desc={`${filtered.length} 个细分岗位，按国内在招数排序；点击查看岗位详情与对比`}
        action={
          <div className="row">
            <select className="select" style={{ width: 150 }} value={cat} onChange={(e) => { setCat(e.target.value); setPage(0); }}>
              <option value="all">全部方向</option>
              {cats.map((c) => <option key={c} value={c}>{coarseZh(c)}</option>)}
            </select>
            <div className="search" style={{ width: 220 }}>
              <Ic.search />
              <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="搜索岗位..." />
            </div>
          </div>
        }>
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: "32%" }}>岗位</th>
                <th>方向</th>
                <th style={{ width: "26%" }}>国内在招</th>
                <th>招聘最多的公司</th>
                <th className="num">海外样本</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r, i) => (
                <tr key={r.role_id} onClick={() => navigate(`/role/${r.role_id}`)}>
                  <td><span className="role-link"><span className="rank-no">{String(currentPage * perPage + i + 1).padStart(2, "0")}</span>{r.role_zh}<small className="role-en">{r.role_name}</small></span></td>
                  <td><CatBadge category={r.coarse_role} /></td>
                  <td>{r.cn_open_roles > 0
                    ? <div className="mk-cell-bar"><ShareBar value={r.cn_open_roles} max={maxOpen} /><span className="mono">{formatInt(r.cn_open_roles)}</span></div>
                    : <span className="muted">国内样本暂无</span>}</td>
                  <td>{r.cn_top_company || <span className="muted">—</span>}</td>
                  <td className="num mono">{formatInt(r.global_jd_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <div className="pager-info">第 {filtered.length ? currentPage * perPage + 1 : 0}-{Math.min((currentPage + 1) * perPage, filtered.length)} 条，共 {filtered.length} 条</div>
          <div className="pager-ctrl">
            <button className="pager-btn" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>‹</button>
            {Array.from({ length: pages }).map((_, i) => <button key={i} className={"pager-btn" + (i === currentPage ? " active" : "")} onClick={() => setPage(i)}>{i + 1}</button>)}
            <button className="pager-btn" disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)}>›</button>
          </div>
        </div>
        <div className="data-note">{market.notes.join(" ")}</div>
      </Card>

      {activeSkill && <SkillDrawer skill={activeSkill} onClose={() => setActiveSkill(null)} />}
    </>
  );
  return embedded ? body : <div className="page">{body}</div>;
}
