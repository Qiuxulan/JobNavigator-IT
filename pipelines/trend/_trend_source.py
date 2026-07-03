"""趋势结论数据源适配器：统一从 PatchTST 里程碑 或 基线分数 读出结论。

让证据批处理（build_trend_evidence）与上游趋势模型解耦：
- 优先读组员1 的 PatchTST 里程碑（3/6/12 个月预测）；
- 缺失时回退到基线 role_trend_scores.json。

关键：PatchTST 预测的是未来月份（无新闻），证据统一从最近真实事件窗口 EVENT_WINDOW 取。
"""

from __future__ import annotations

import json
from pathlib import Path

MILESTONES_PATH = Path("data/gold/patchtst_prediction_milestones.json")
PREDICTIONS_36M_PATH = Path("data/gold/patchtst_predictions_36m.json")
BASELINE_PATH = Path("data/gold/role_trend_scores.json")

# 真实事件可用窗口（GDELT 覆盖 2026-01~06）。预测在未来，证据取此窗口内最近新闻。
EVENT_WINDOW = ("2026-01", "2026-06")


def _factors(raw) -> list[str]:
    """supplemental_signals/main_factors 容错成 list[str]。"""
    if isinstance(raw, list):
        return [str(x) for x in raw][:5]
    if isinstance(raw, dict):
        return [str(k) for k in raw.keys()][:5]
    if isinstance(raw, str):
        try:
            return _factors(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return [raw] if raw else []
    return []


def _record(role, m, src) -> dict:
    return {
        "canonical_role": role,
        "month": m.get("month"),
        "horizon_months": int(m.get("step", 3)),
        "horizon_label": m.get("label", f"{m.get('step', 3)}_month"),
        "trend_direction": m.get("trend_direction", "flat"),
        "predicted_demand_index": float(m.get("predicted_demand_index", 0.0)),
        "confidence": float(m.get("confidence", 0.0)),
        "factors": _factors(m.get("supplemental_signals")),
        "source": src,
    }


def load_conclusions(source: str = "auto", granularity: str = "milestone") -> list[dict]:
    """返回统一结论列表。
    granularity: 'milestone'(每角色5个里程碑) 或 'monthly'(每角色36个月全量)。
    字段: {canonical_role, month, horizon_months, horizon_label, trend_direction,
           predicted_demand_index, confidence, factors, source}
    """
    # 逐月全量（前端画曲线用）
    if granularity == "monthly" and source in ("auto", "patchtst") and PREDICTIONS_36M_PATH.exists():
        data = json.loads(PREDICTIONS_36M_PATH.read_text(encoding="utf-8"))
        return [_record(m.get("canonical_role"), m, "patchtst-monthly") for m in data]

    # 里程碑（默认）
    if source in ("auto", "patchtst") and MILESTONES_PATH.exists():
        data = json.loads(MILESTONES_PATH.read_text(encoding="utf-8"))
        out = []
        for role_entry in data:
            role = role_entry.get("canonical_role")
            for m in role_entry.get("milestones", []):
                out.append(_record(role, m, "patchtst"))
        return out

    # 回退：基线分数
    scores = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    out = []
    for s in scores:
        out.append({
            "canonical_role": s.get("canonical_role"),
            "month": s.get("month"),
            "horizon_months": int(s.get("horizon_months", 3)),
            "horizon_label": f"{s.get('horizon_months', 3)}_month",
            "trend_direction": s.get("trend_direction", "flat"),
            "predicted_demand_index": float(s.get("predicted_demand_index", 0.0)),
            "confidence": float(s.get("confidence", 0.0)),
            "factors": _factors(s.get("main_factors_json")),
            "source": "baseline",
        })
    return out
