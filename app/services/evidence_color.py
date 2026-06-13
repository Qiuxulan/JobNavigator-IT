"""统一着色逻辑：事件/边/岗位颜色规则的单一来源。

谁用：本模块被各可视化脚本与组员3 的前端/Agent 共同 import，
确保"哪里都用同一套配色"，不再各处重复实现、避免不一致。

三个语义维度（各归各的载体）：
  - 事件节点颜色 = 这条消息本身好坏           -> event_color / event_polarity
  - 边颜色       = 该证据指向的岗位趋势方向   -> edge_color
  - 岗位节点边框 = 岗位的 PatchTST 趋势        -> trend_border

着色策略：先看 tone；tone 接近 0（|tone|<NEUTRAL_BAND）时按 event_type 兜底，
让"招聘/融资/突破"显绿、"裁员/安全事故/监管"显红，减少中性灰。
"""

from __future__ import annotations

COLOR = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#9ca3af"}
TREND_EDGE = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#3b82f6"}
TREND_EDGE_DIM = {
    "positive": "rgba(34,197,94,0.55)",
    "negative": "rgba(239,68,68,0.55)",
    "neutral": "rgba(59,130,246,0.38)",
}
TREND_BORDER = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#64748b"}
NEUTRAL_BAND = 0.1

_VISUAL_POSITIVE_TYPES = {
    "ai_coding_agent",
    "ai_infrastructure",
    "database_release",
    "data_orchestration_release",
    "design_ai_tool",
    "developer_platform_ai",
    "enterprise_ai_agent",
    "enterprise_ai_platform",
    "frontend_framework_release",
    "frontend_tooling_release",
    "game_asset_marketplace",
    "game_engine_release",
    "hardware_platform_launch",
    "language_release",
    "language_standard",
    "ml_framework_release",
    "mobile_framework_release",
    "mobile_platform_release",
    "model_release",
    "open_model_release",
    "platform_release",
    "product_release",
    "research_breakthrough",
    "runtime_release",
    "stream_processing_release",
    "testing_tool_release",
}

_VISUAL_NEGATIVE_TYPES = {
    "layoff",
    "policy",
    "quality_risk",
    "regulation",
    "security_incident",
    "supply_chain_incident",
}

_JOBLIKE_TITLE_TERMS = {
    "engineer", "developer", "job", "jobs", "hiring", "recruit", "vacancy",
    "on site", "remote", "senior", "junior", "middle", "mid level",
}

# event_type -> tone≈0 时的兜底极性
_TYPE_POLARITY = {
    "funding": "positive",
    "ai_infrastructure": "positive",
    "ai_coding_agent": "positive",
    "database_release": "positive",
    "design_ai_tool": "positive",
    "enterprise_ai_platform": "positive",
    "frontend_framework_release": "positive",
    "frontend_tooling_release": "positive",
    "game_engine_release": "positive",
    "language_release": "positive",
    "language_standard": "positive",
    "ml_framework_release": "positive",
    "model_release": "positive",
    "platform_release": "positive",
    "research_breakthrough": "positive",
    "product_release": "positive",
    "runtime_release": "positive",
    "testing_tool_release": "positive",
    "layoff": "negative",
    "regulation": "negative",
    "security_incident": "negative",
    "security_standard": "negative",
    "policy": "negative",
    "market_report": "neutral",
}


def _norm(direction: str | None) -> str:
    """把 up/down/flat 或 positive/negative/neutral 统一成 positive/negative/neutral。"""
    d = (direction or "").lower()
    if d in ("up", "positive"):
        return "positive"
    if d in ("down", "negative"):
        return "negative"
    return "neutral"


def event_polarity(ev: dict) -> str:
    """事件极性：先 tone，接近 0 时按 event_type 兜底（减少灰）。"""
    tone = float(ev.get("tone") or 0.0)
    if tone > NEUTRAL_BAND:
        return "positive"
    if tone < -NEUTRAL_BAND:
        return "negative"
    event_type = ev.get("event_type", "")
    if event_type in _TYPE_POLARITY:
        return _TYPE_POLARITY[event_type]
    if any(word in event_type for word in ("release", "framework", "platform", "tool", "research")):
        return "positive"
    if any(word in event_type for word in ("incident", "risk", "regulation", "layoff")):
        return "negative"
    return "neutral"


def event_color(ev: dict) -> str:
    """事件节点颜色（= 消息本身好坏）。"""
    return COLOR[event_polarity(ev)]


def edge_direction(trend_direction: str | None, ev: dict | None = None) -> str:
    """边的可视化方向。

    预测明确上升/下降时，颜色严格跟随预测方向；
    预测持平时，再用证据自身 impact_direction 做二级区分，避免全图一片蓝。
    """
    trend = _norm(trend_direction)
    if trend != "neutral":
        return trend
    ev = ev or {}
    event_type = ev.get("event_type", "")
    impact = _norm(ev.get("impact_direction"))
    if impact == "negative" and event_type in _VISUAL_NEGATIVE_TYPES:
        return "negative"
    if impact == "positive" and event_type in _VISUAL_POSITIVE_TYPES:
        title = str(ev.get("title") or "").lower()
        if not any(term in title for term in _JOBLIKE_TITLE_TERMS):
            return "positive"
    return "neutral"


def edge_color(trend_direction: str | None, ev: dict | None = None) -> str:
    """边颜色（= 预测方向优先，持平时由证据方向兜底）。"""
    return TREND_EDGE[edge_direction(trend_direction, ev)]


def edge_color_dim(trend_direction: str | None, ev: dict | None = None) -> str:
    """未选中时的边颜色，保留方向色但降低透明度。"""
    return TREND_EDGE_DIM[edge_direction(trend_direction, ev)]


def trend_border(trend_direction: str | None) -> str:
    """岗位节点边框色（= PatchTST 趋势）。"""
    return TREND_BORDER[_norm(trend_direction)]


def node_color_by_trends(trends, ev: dict) -> str:
    """事件节点颜色 = 它主要在解释的岗位趋势（主导方向）。

    一个事件可连多个岗位：多数连下降岗→红，多数连上升岗→绿；
    平局/混合/无方向时回退到事件本身极性（event_color），保证节点与其边视觉一致。
    """
    norm = [_norm(t) for t in (trends or [])]
    neg, pos = norm.count("negative"), norm.count("positive")
    if neg > pos:
        return COLOR["negative"]
    if pos > neg:
        return COLOR["positive"]
    return event_color(ev)
