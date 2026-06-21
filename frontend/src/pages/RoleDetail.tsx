import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getCotContext, getEvidence, getTrend } from "../api";
import type { CotContext, EvidenceResponse, TrendEvidence, TrendSignal } from "../api";
import { Ic } from "../components/Icons";
import { Card } from "../components/Card";
import { TrendBadge } from "../components/Badge";

function eventTypeLabel(type?: string): string {
  const map: Record<string, string> = {
    model_release: "模型发布",
    ai_coding_agent: "AI 编程工具",
    market_research: "市场研究",
    regulation: "政策监管",
    funding: "投融资",
    product_launch: "产品发布",
    platform_release: "平台发布",
    security_incident: "安全事件",
  };
  return map[type || ""] || type || "行业事件";
}

function impactLabel(value?: string): string {
  if (value === "positive") return "正向";
  if (value === "negative") return "负向";
  if (value === "mixed") return "混合";
  if (value === "neutral") return "中性";
  return value || "中性";
}

function trendText(value?: string): string {
  if (value === "up") return "上升";
  if (value === "down") return "下降";
  return "平稳";
}

function citeList(items: Array<{ cite: string; title?: string }> | undefined, empty: string) {
  if (!items?.length) return <span className="cot-muted">{empty}</span>;
  return (
    <div className="cot-cites">
      {items.slice(0, 4).map((item) => (
        <span key={item.cite} className="cot-cite">[{item.cite}] {item.title || "证据"}</span>
      ))}
    </div>
  );
}

function CotCard({ cot }: { cot: CotContext | null }) {
  const [open, setOpen] = useState(false);

  if (!cot) return null;
  const p = cot.prediction || {};
  const agg = cot.aggregate;
  const counter = cot.events?.filter((event) => event.is_counter_signal) || [];
  return (
    <Card
      title="证据链摘要（CoT）"
      desc="默认折叠；用于查看 PatchTST、证据检索、重大事件和 JD 证据如何串联。"
      action={
        <button className="btn sm" onClick={() => setOpen((value) => !value)}>
          {open ? "收起" : "展开"}
        </button>
      }
      style={{ marginBottom: 20 }}
    >
      {!open && (
        <div className="cot-collapsed">
          <span>已生成 {cot.events?.length || 0} 条事件证据、{cot.major_events?.length || 0} 条重大事件、{cot.jobs?.length || 0} 条 JD 引用。</span>
          <button className="btn ghost sm" onClick={() => setOpen(true)}>查看证据链</button>
        </div>
      )}
      {open && (
        <div className="cot-steps">
          <div className="cot-step">
            <div className="cot-no">Step 1</div>
            <div>
              <b>模型预测</b>
              <p>PatchTST 判断未来 {cot.horizon_months} 个月趋势为 {trendText(p.trend_direction)}，需求指数 {Number(p.predicted_demand_index ?? 0).toFixed(4)}，置信度 {Math.round(Number(p.confidence ?? 0) * 100)}%。</p>
            </div>
          </div>
          <div className="cot-step">
            <div className="cot-no">Step 2</div>
            <div>
              <b>聚合信号</b>
              <p>{agg ? `证据检索覆盖 ${agg.article_count ?? 0} 条相关新闻，机会事件 ${agg.opportunity_events ?? 0} 条，风险事件 ${agg.risk_events ?? 0} 条，净信号为 ${agg.net_signal ?? "N/A"}。` : "当前证据聚合信息不足。"}</p>
            </div>
          </div>
          <div className="cot-step">
            <div className="cot-no">Step 3</div>
            <div>
              <b>关键事件</b>
              {citeList(cot.major_events, "暂无重大行业事件引用")}
              {counter.length > 0 && <p className="cot-warn">存在反向信号：{counter.map((item) => `[${item.cite}]`).join("、")}，综合判断时需要降低单向结论的确定性。</p>}
            </div>
          </div>
          <div className="cot-step">
            <div className="cot-no">Step 4</div>
            <div>
              <b>JD 证据</b>
              {citeList(cot.jobs, "暂无可引用 JD 证据")}
            </div>
          </div>
          <div className="cot-step">
            <div className="cot-no">Step 5</div>
            <div>
              <b>综合判断</b>
              <p>页面结论只来自 PatchTST、证据检索、重大事件和 JD 证据；如果某一类证据为空，前端会直接显示证据不足，不会补写外部事实。</p>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function RoleDetail() {
  const { roleName = "" } = useParams();
  const navigate = useNavigate();
  const [signal, setSignal] = useState<TrendSignal | null>(null);
  const [shortSignal, setShortSignal] = useState<TrendSignal | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [cot, setCot] = useState<CotContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      try {
        const [shortTrendRes, trendRes, evidenceRes, cotRes] = await Promise.all([
          getTrend(roleName, 3),
          getTrend(roleName, 24),
          getEvidence(roleName, 8).catch(() => null),
          getCotContext(roleName, 3).catch(() => null),
        ]);
        if (alive) {
          setShortSignal(shortTrendRes);
          setSignal(trendRes);
          setEvidence(evidenceRes);
          setCot(cotRes);
        }
      } finally {
        if (alive) setLoading(false);
      }
    }
    if (roleName) void load();
    return () => { alive = false; };
  }, [roleName]);

  const lineOption = useMemo(() => {
    if (!signal?.monthly_forecast?.length) return null;
    const rows = signal.monthly_forecast;
    const months = rows.map((row) => String(row.month ?? row.date ?? "").slice(0, 7));
    const values = rows.map((row) => Number(row.predicted_demand_index ?? row.demand_index ?? row.value ?? 0));
    return {
      tooltip: { trigger: "axis" as const, valueFormatter: (value: number) => value.toFixed(4) },
      grid: { left: 8, right: 22, top: 28, bottom: 16, containLabel: true },
      xAxis: { type: "category" as const, data: months, boundaryGap: false, axisLabel: { color: "#767b85", interval: 3 }, axisLine: { lineStyle: { color: "#dde0e5" } } },
      yAxis: { type: "value" as const, scale: true, axisLabel: { color: "#767b85" }, splitLine: { lineStyle: { color: "rgba(28,30,35,0.08)" } } },
      series: [{
        name: "预测需求指数",
        type: "line",
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { width: 2.5, color: "#5B8DEF" },
        itemStyle: { color: "#5B8DEF" },
        areaStyle: { color: "rgba(91,141,239,0.12)" },
      }],
    };
  }, [signal]);

  if (loading) return <div className="loading-center"><div className="spinner" />加载岗位数据...</div>;
  if (!signal) {
    return (
      <div className="page">
        <div className="cmp-empty">
          <div>未找到岗位：{roleName}</div>
          <button className="btn" style={{ marginTop: 16 }} onClick={() => navigate("/dashboard")}>返回仪表盘</button>
        </div>
      </div>
    );
  }

  const eventRows: TrendEvidence[] = evidence?.events?.length ? evidence.events : signal.evidence || [];
  const aggregate = evidence?.aggregate;
  const majorRows = evidence?.major_industry_events || [];
  const headlineSignal = shortSignal || signal;

  return (
    <div className="page">
      <button className="back-link" onClick={() => navigate("/dashboard")}><Ic.back /> 返回仪表盘</button>

      <div className="detail-head">
        <div>
          <div className="detail-title">{signal.role_name_zh || signal.canonical_role}</div>
          <div className="detail-meta">
            <TrendBadge trend={headlineSignal.trend_direction || "flat"} />
            <span className="badge neutral">{signal.canonical_role}</span>
            <span className="badge neutral">置信度 {(headlineSignal.confidence * 100).toFixed(0)}%</span>
            <span className="badge neutral">主结论：3 个月短期预测</span>
            <span className="badge neutral">曲线：{signal.monthly_forecast?.length || 0} 个月趋势参考</span>
          </div>
        </div>
        <div className="metric-cluster">
          <div className="metric">
            <div className="metric-label">需求指数</div>
            <div className="metric-value">{headlineSignal.predicted_demand_index.toFixed(4)}</div>
          </div>
          <div className="metric">
            <div className="metric-label">趋势判断</div>
            <div className="metric-value">{trendText(headlineSignal.trend_direction)}</div>
          </div>
        </div>
      </div>

      <Card title="PatchTST 趋势预测" desc="基于 2020-01 至 2026-05 的岗位月度特征，输出未来 24 个月需求指数" style={{ marginBottom: 20 }}>
        {lineOption ? <ReactECharts option={lineOption} style={{ height: 320 }} /> : <div className="cmp-empty">暂无可展示的预测序列。</div>}
        {signal.main_factors?.length > 0 && (
          <div className="factor-list">
            {signal.main_factors.map((factor) => <div className="factor-item" key={factor}>{factor}</div>)}
          </div>
        )}
      </Card>

      <CotCard cot={cot} />

      {aggregate && (
        <Card title="证据检索概览" style={{ marginBottom: 20 }}>
          <div className="stat-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <div className="stat" style={{ padding: 16 }}><div className="stat-label">相关新闻</div><div className="stat-value" style={{ fontSize: 28 }}>{aggregate.article_count ?? 0}<span className="unit">条</span></div></div>
            <div className="stat" style={{ padding: 16 }}><div className="stat-label">平均情绪</div><div className="stat-value" style={{ fontSize: 28 }}>{Number(aggregate.mean_tone ?? 0).toFixed(2)}</div></div>
            <div className="stat" style={{ padding: 16 }}><div className="stat-label">综合信号</div><div className="stat-value" style={{ fontSize: 28 }}>{aggregate.net_signal ?? "N/A"}</div></div>
          </div>
        </Card>
      )}

      <Card title="证据检索结果" desc={`${eventRows.length} 条相关新闻或事件证据`} style={{ marginBottom: 20 }}>
        {eventRows.length === 0 && <div className="cmp-empty">暂无证据。</div>}
        {eventRows.map((ev, index) => (
          <div className="news-item" key={`${ev.title}-${index}`}>
            <div className="news-sent" style={{ color: (ev.tone ?? 0) >= 0 ? "var(--up)" : "var(--down)" }}>{(ev.tone ?? 0).toFixed(2)}</div>
            <div className="news-body">
              <div className="news-title">{ev.title || "新闻事件"}</div>
              <div className="news-foot">
                <span className="news-src">{ev.source || ev.source_domain || "GDELT"}</span>
                <span>·</span>
                <span>{ev.published_at || ev.event_date || ""}</span>
                {ev.impact_direction && <><span>·</span><span>{impactLabel(ev.impact_direction)}</span></>}
                {ev.url && <a href={ev.url} target="_blank" rel="noreferrer" style={{ marginLeft: "auto" }}><Ic.ext style={{ width: 12, height: 12 }} /></a>}
              </div>
            </div>
          </div>
        ))}
      </Card>

      {majorRows.length > 0 && (
        <Card title="重大行业事件">
          <div className="major-event-list">
            {majorRows.slice(0, 6).map((ev, index) => (
              <article className="major-event" key={`${ev.title}-${index}`}>
                <div className="major-event-top">
                  <span className="major-event-type">{eventTypeLabel(ev.event_type)}</span>
                  <span className={`major-event-impact ${ev.impact_direction || "neutral"}`}>{impactLabel(ev.impact_direction)}</span>
                </div>
                <div className="major-event-title">{ev.title}</div>
                <div className="major-event-date">{ev.event_date}</div>
              </article>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
