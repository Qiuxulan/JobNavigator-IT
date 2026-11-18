"""C 模块：把证据链组装成 CoT 推理上下文（grounding），供组员3 Agent 接 LLM。

边界清晰：
  - 本模块只做「事实组装 + 带引用编号的 grounded prompt 上下文」，不调用 LLM。
  - LLM 链式推理由组员3 的 Agent 层完成（调用 build_cot_prompt 的返回值即可）。

数据来源（v2 重建资产优先，旧链路回退）：
  - TrendService 信号（trend_forecasts_v2.json，含 model_used/sMAPE/稀疏标记）
  - EvidenceServiceV2 证据链（aggregate + 分片事件，旧 GDELT 索引缺失时回退）
  - 重大行业事件目录（data/gold/major_industry_events_v1.json，公开来源高可信）
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.evidence_service_v2 import EvidenceServiceV2
from app.services.trend import EVIDENCE_WINDOW, TrendNotFoundError, TrendService, _resolve_role

MAJOR_EVENTS_PATH = Path("data/gold/major_industry_events_v1.json")
DIR_CN = {"up": "上升", "down": "下降", "flat": "持平", "stable": "持平"}


def _normalize_aggregate(agg: dict | None) -> dict | None:
    """把 v2 aggregate（by_type 统计）归一成 build_cot_prompt 期望的形状。"""
    if not agg:
        return None
    normalized = dict(agg)
    normalized.setdefault("article_count", agg.get("total_items", 0))
    by_type = agg.get("by_type") or {}
    positive_types = {"funding", "product_release", "research_breakthrough", "hiring", "ai_adoption"}
    negative_types = {"layoff", "security_incident", "policy"}
    normalized.setdefault(
        "opportunity_events",
        sum(c for t, c in by_type.items() if t in positive_types),
    )
    normalized.setdefault(
        "risk_events",
        sum(c for t, c in by_type.items() if t in negative_types),
    )
    normalized.setdefault("net_signal", "mixed")
    return normalized


def _major_events(role: str, direction: str) -> list[dict]:
    if not MAJOR_EVENTS_PATH.exists():
        return []
    try:
        data = json.loads(MAJOR_EVENTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    catalog = {e["event_id"]: e for e in data.get("event_catalog", [])}
    d = "flat" if direction == "stable" else direction
    row = next((r for r in data.get("role_trend_evidence", [])
                if r.get("canonical_role") == role and r.get("trend_direction") == d), None)
    if not row:
        return []
    return [catalog[i] for i in row.get("major_event_ids", []) if i in catalog]


def assemble_cot_context(role: str, horizon: int = 3) -> dict:
    """组装 CoT 上下文（grounding）。返回结构化事实 + 带引用编号的证据。

    引用编号约定：E#=新闻事件证据，M#=重大行业事件，J#=在招 JD。
    """
    resolved = _resolve_role(role)
    canonical = resolved.canonical_role

    signal = TrendService.get_signal(canonical, horizon_months=horizon)
    direction = signal.trend_direction

    res = EvidenceServiceV2.retrieve_evidence(canonical, EVIDENCE_WINDOW, 5, direction)
    agg = _normalize_aggregate(res.get("aggregate"))

    events = []
    for i, e in enumerate(res.get("events", []), 1):
        events.append({
            "cite": f"E{i}",
            "title": e.get("title"),
            "impact": e.get("impact_direction"),
            "event_type": e.get("event_type"),
            "tone": e.get("tone"),
            "is_counter_signal": e.get("is_counter_signal", False),
            "evidence_strength": e.get("evidence_strength", "strong"),
            "url": e.get("url"),
        })
    jobs = [{"cite": f"J{i}", "company": j.get("company_name"), "title": j.get("title"),
             "salary_mid": j.get("salary_mid")}
            for i, j in enumerate(res.get("jobs", [])[:3], 1)]
    majors = [{"cite": f"M{i}", "title": m.get("title"), "date": m.get("event_date"),
               "impact": m.get("impact_direction"), "source_url": m.get("source_url")}
              for i, m in enumerate(_major_events(canonical, direction), 1)]

    return {
        "canonical_role": canonical,
        "horizon_months": horizon,
        "prediction": {
            "trend_direction": direction,
            "predicted_demand_index": signal.predicted_demand_index,
            "confidence": signal.confidence,
            "model_used": signal.model_used,
            "backtest_smape": signal.backtest_smape,
            "sparse": signal.sparse,
        },
        "main_factors": signal.main_factors,
        "aggregate": agg,
        "events": events,
        "major_events": majors,
        "jobs": jobs,
        "note": res.get("note"),
    }


COT_SYSTEM_PROMPT = (
    "你是 JobNavigator-IT 的趋势证据分析助手。只能依据用户消息中的结构化证据回答，"
    "不得引入证据之外的事实、新闻、岗位或统计数字。不要输出隐藏思维链，"
    "只输出可审计的 5 步证据链摘要：模型预测、聚合信号、关键事件、JD 证据、综合判断。"
    "每个判断后必须标注 [E#]、[M#] 或 [J#]；如果证据不足，必须明确写出证据不足。"
)


def build_cot_prompt(ctx: dict) -> str:
    """把上下文渲染成 grounded CoT 的 user prompt（组员3 拿去喂 LLM）。"""
    p = ctx["prediction"]
    model_info = p.get("model_used") or "unknown"
    smape = p.get("backtest_smape")
    model_desc = f"模型={model_info}"
    if smape is not None:
        model_desc += f"（回测 sMAPE {float(smape):.1%}）"
    if p.get("sparse"):
        model_desc += "，岗位 JD 样本稀疏、置信度受限"
    L = [f"# 角色：{ctx['canonical_role']}   预测视野：{ctx['horizon_months']} 个月",
         f"## 模型预测：方向={DIR_CN.get(p.get('trend_direction'), p.get('trend_direction'))} "
         f"需求指数={p.get('predicted_demand_index')} 置信度={p.get('confidence')} {model_desc}"]
    factors = ctx.get("main_factors") or []
    if factors:
        L.append("## 预测归因（真实数据）：")
        for factor in factors:
            L.append(f"  - {factor}")
    a = ctx.get("aggregate")
    if a:
        L.append(f"## 新闻聚合：相关 {a['article_count']} 篇，机会 {a['opportunity_events']} / "
                 f"风险 {a['risk_events']}，净信号 {a['net_signal']}")
        months_covered = a.get("months_covered")
        if months_covered:
            L.append(f"  覆盖月份：{months_covered[0]} ~ {months_covered[-1]}，"
                     f"月均 {a.get('avg_items_per_month', '?')} 条")
    if ctx["events"]:
        L.append("## 事件证据：")
        for e in ctx["events"]:
            tag = "（反向信号）" if e["is_counter_signal"] else ""
            L.append(f"  [{e['cite']}]{tag} {e['impact']} · {e['event_type']} · {e['title']} | {e['url']}")
    if ctx["major_events"]:
        L.append("## 重大行业事件（公开来源，高可信）：")
        for m in ctx["major_events"]:
            L.append(f"  [{m['cite']}] {m['date']} · {m['impact']} · {m['title']} | {m['source_url']}")
    if ctx["jobs"]:
        L.append("## 在招 JD：")
        for j in ctx["jobs"]:
            L.append(f"  [{j['cite']}] {j['company']} · {j['title']} · 薪资 {j.get('salary_mid')}")
    L.append(
        "\n## 任务：按以下步骤链式推理（每步引用证据编号），最后给结论：\n"
        "Step1 模型预测说了什么；Step2 新闻面整体情绪如何；"
        "Step3 关键事件怎样支撑或反驳该预测（含对反向信号的权衡）；"
        "Step4 在招 JD 反映的短期需求；Step5 综合判断该岗位趋势及主因。"
    )
    return "\n".join(L)


if __name__ == "__main__":  # 快速自检：python -m app.services.trend_explanation [角色]
    import sys
    r = sys.argv[1] if len(sys.argv) > 1 else "AI Engineer"
    try:
        ctx = assemble_cot_context(r)
        print(build_cot_prompt(ctx))
    except TrendNotFoundError as exc:
        print(f"[!] {exc}")
