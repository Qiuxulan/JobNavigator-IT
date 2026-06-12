from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipelines.trend.patchtst_predictor import (
    FEATURE_COLS,
    MILESTONES_PATH,
    PATCHTST_DATASET_PATH,
    PREDICTIONS_PATH,
    ROLE_TAXONOMY_PATH,
    TARGET_COL,
    direction_from_score,
    resolve_role,
)


class TrendPredictorError(RuntimeError):
    pass


class TrendPredictionNotFoundError(TrendPredictorError):
    pass


EVIDENCE_COLS = [
    "jd_demand_index",
    "gdelt_sentiment_index",
    "github_repo_count",
    "gdelt_article_count",
    "arxiv_paper_count",
]


@lru_cache(maxsize=1)
def _load_taxonomy() -> list[dict[str, Any]]:
    with open(ROLE_TAXONOMY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_predictions() -> list[dict[str, Any]]:
    if not PREDICTIONS_PATH.exists():
        raise TrendPredictionNotFoundError(
            "patchtst predictions not found; run pipelines/trend/generate_patchtst_predictions.py"
        )
    with open(PREDICTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_milestones() -> list[dict[str, Any]]:
    if not MILESTONES_PATH.exists():
        raise TrendPredictionNotFoundError(
            "patchtst milestones not found; run pipelines/trend/generate_patchtst_predictions.py"
        )
    with open(MILESTONES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_panel() -> pd.DataFrame:
    df = pd.read_json(PATCHTST_DATASET_PATH)
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    for col in [*FEATURE_COLS, "time_idx"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.sort_values(["canonical_role", "time_idx"]).reset_index(drop=True)


def _canonical_role(role: str) -> str:
    try:
        return resolve_role(role, _load_taxonomy())
    except KeyError as exc:
        raise TrendPredictionNotFoundError(str(exc)) from exc


def predict(role: str, months: int = 36) -> dict[str, Any]:
    canonical = _canonical_role(role)
    rows = [row for row in _load_predictions() if row.get("canonical_role") == canonical]
    rows = sorted(rows, key=lambda row: int(row.get("step", 0)))
    if not rows:
        raise TrendPredictionNotFoundError(f"no PatchTST prediction found for {canonical}")
    months = max(1, min(int(months), 36))
    selected = rows[:months]
    final = selected[-1]
    return {
        "canonical_role": canonical,
        "horizon_months": months,
        "trend_direction": final["trend_direction"],
        "predicted_demand_index": final["predicted_demand_index"],
        "confidence": final["confidence"],
        "monthly_forecast": selected,
    }


def get_milestones(role: str) -> dict[str, Any]:
    canonical = _canonical_role(role)
    for item in _load_milestones():
        if item.get("canonical_role") == canonical:
            return item
    raise TrendPredictionNotFoundError(f"no PatchTST milestones found for {canonical}")


def _series_slope(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    return float(np.polyfit(x, values.astype(float), 1)[0])


def _metric_change(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    return float(values[-1] - values[0])


def _factor_sentence(metric: str, values: np.ndarray, window_label: str = "全历史") -> str | None:
    change = _metric_change(values)
    slope = _series_slope(values)
    if abs(change) < 1e-6 and abs(slope) < 1e-6:
        return None
    labels = {
        "jd_demand_index": "JD 需求指数",
        "gdelt_sentiment_index": "GDELT 新闻情绪",
        "github_repo_count": "GitHub 仓库活跃度",
        "gdelt_article_count": "GDELT 文章数",
        "gdelt_event_impact_score": "重大事件冲击",
        "arxiv_paper_count": "arXiv 论文数",
    }
    direction = "上升" if change > 0 else "下降"
    return f"{labels.get(metric, metric)}{window_label}整体{direction}"


def _turning_points(history: pd.DataFrame) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for metric in EVIDENCE_COLS:
        values = history[metric].to_numpy(dtype=float)
        if len(values) < 3:
            continue
        diffs = np.diff(values)
        std = float(np.std(diffs))
        if std < 1e-6:
            continue
        zscores = (diffs - float(np.mean(diffs))) / std
        for idx, zscore in enumerate(zscores, start=1):
            if abs(float(zscore)) >= 1.5:
                prev = float(values[idx - 1])
                curr = float(values[idx])
                change = curr - prev
                from_zero = abs(prev) < 1e-6 and abs(curr) >= 1e-6
                pct = None if from_zero else change / max(abs(prev), 1e-6)
                points.append(
                    {
                        "month": history.iloc[idx]["month"].strftime("%Y-%m-%d"),
                        "metric": metric,
                        "change": round(change, 6),
                        "change_ratio": None if pct is None else round(float(pct), 6),
                        "from_zero": from_zero,
                        "description": (
                            f"{metric} 从 0 基线出现新信号"
                            if from_zero
                            else f"{metric} 出现明显{'增长' if change > 0 else '下降'}"
                        ),
                    }
                )
    return sorted(
        points,
        key=lambda item: abs(float(item["change_ratio"])) if item["change_ratio"] is not None else abs(float(item["change"])),
        reverse=True,
    )[:5]


def _prediction_for_month(canonical: str, month: str) -> dict[str, Any] | None:
    target = str(month)
    for row in _load_predictions():
        if row.get("canonical_role") == canonical and str(row.get("month")) == target:
            return row
    return None


def _jd_observed_range(role_panel: pd.DataFrame) -> dict[str, Any]:
    observed = role_panel
    if "jd_demand_observed" in role_panel:
        observed = role_panel[role_panel["jd_demand_observed"].fillna(False).astype(bool)]
    nonzero = observed[observed["jd_demand_index"].abs() > 1e-9]
    if nonzero.empty:
        return {
            "first_nonzero_month": None,
            "last_nonzero_month": None,
            "nonzero_month_count": 0,
        }
    return {
        "first_nonzero_month": nonzero["month"].min().strftime("%Y-%m-%d"),
        "last_nonzero_month": nonzero["month"].max().strftime("%Y-%m-%d"),
        "nonzero_month_count": int(nonzero["month"].nunique()),
    }


def _recent_window_summary(role_panel: pd.DataFrame, months: int = 12) -> dict[str, Any]:
    recent = role_panel.tail(months).copy()
    observed_jd = recent
    if "jd_demand_observed" in recent:
        observed_jd = recent[recent["jd_demand_observed"].fillna(False).astype(bool)]
    summary: dict[str, Any] = {
        "months": [value.strftime("%Y-%m-%d") for value in recent["month"]],
        "jd_demand_observed_count": int(len(observed_jd)),
        "jd_demand_index_all_zero": bool(
            observed_jd.empty or (observed_jd["jd_demand_index"].abs() <= 1e-9).all()
        ),
    }
    for metric in EVIDENCE_COLS:
        values = recent[metric].to_numpy(dtype=float)
        summary[metric] = {
            "first": round(float(values[0]), 6) if len(values) else 0.0,
            "last": round(float(values[-1]), 6) if len(values) else 0.0,
            "change": round(_metric_change(values), 6),
            "slope": round(_series_slope(values), 6),
        }
    return summary


def _build_key_factors(history: pd.DataFrame, recent: pd.DataFrame, jd_range: dict[str, Any]) -> list[str]:
    factors: list[str] = []
    jd_values = history["jd_demand_index"].to_numpy(dtype=float)
    jd_sentence = _factor_sentence("jd_demand_index", jd_values, "全历史")
    if jd_sentence:
        factors.append(jd_sentence)
    for metric in ["gdelt_sentiment_index", "github_repo_count", "gdelt_article_count", "arxiv_paper_count"]:
        sentence = _factor_sentence(metric, recent[metric].to_numpy(dtype=float), "最近 12 个月")
        if sentence:
            factors.append(sentence)
    if not factors:
        factors = ["全历史核心指标整体变化不明显，预测更偏向平稳参考"]
    return factors[:6]


def get_evidence(role: str, month: str, history_months: int | None = None) -> dict[str, Any]:
    canonical = _canonical_role(role)
    panel = _load_panel()
    role_panel = panel[panel["canonical_role"] == canonical].sort_values("time_idx")
    if role_panel.empty:
        raise TrendPredictionNotFoundError(f"no history found for {canonical}")
    if history_months is None:
        history = role_panel.copy()
    else:
        history = role_panel.tail(max(1, int(history_months))).copy()
    recent = role_panel.tail(12).copy()
    jd_range = _jd_observed_range(role_panel)
    prediction = _prediction_for_month(canonical, month)
    latest_score = float(history[TARGET_COL].iloc[-1])
    predicted_score = float(prediction["predicted_demand_index"]) if prediction else latest_score
    factors = _build_key_factors(history, recent, jd_range)
    historical_trend = {
        "months": [value.strftime("%Y-%m-%d") for value in history["month"]],
    }
    for metric in EVIDENCE_COLS:
        historical_trend[metric] = [round(float(value), 6) for value in history[metric].to_numpy(dtype=float)]
    return {
        "canonical_role": canonical,
        "prediction_month": month,
        "predicted_demand_index": round(predicted_score, 6),
        "trend_direction": prediction["trend_direction"] if prediction else direction_from_score(predicted_score),
        "history_window": f"full_{len(history)}_months" if history_months is None else f"last_{len(history)}_months",
        "jd_observed_range": jd_range,
        "historical_trend": historical_trend,
        "recent_window": _recent_window_summary(role_panel, months=12),
        "key_factors": factors,
        "turning_points": _turning_points(history),
        "note": "This is metric-level evidence from PatchTST input features, not news/JD document retrieval.",
    }


def clear_cache() -> None:
    _load_taxonomy.cache_clear()
    _load_predictions.cache_clear()
    _load_milestones.cache_clear()
    _load_panel.cache_clear()
