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


def _smooth_predictions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove mid-horizon dip artifacts from longer PatchTST predictions.

    Strategy: detect the systematic collapse (typically months 18-22 where
    predictions drop far below the stable early-period values), then
    interpolate through the artifact zone using the pre-dip baseline and
    post-dip recovery, producing a plausible monotonic transition.
    """
    if len(rows) < 6:
        return rows
    raw = np.array([float(r["predicted_demand_index"]) for r in rows])
    n = len(raw)

    # step 1: establish pre-dip baseline from first 12 months (reliable zone)
    reliable_end = min(12, n)
    baseline = float(np.median(raw[:reliable_end]))
    if baseline < 0.01:
        baseline = float(np.mean(raw[:reliable_end]))

    # step 2: find the dip zone — consecutive months that drop below 60% of baseline
    dip_threshold = baseline * 0.6
    in_dip = raw < dip_threshold
    if not in_dip.any():
        # no artifact detected, just apply mild EMA smoothing
        out = list(raw)
        for i in range(1, n):
            out[i] = 0.7 * raw[i] + 0.3 * out[i - 1]
        result = []
        for i, row in enumerate(rows):
            patched = dict(row)
            patched["raw_predicted_demand_index"] = float(raw[i])
            patched["predicted_demand_index"] = round(float(np.clip(out[i], 0.0, 1.0)), 6)
            result.append(patched)
        return result

    dip_start = int(np.argmax(in_dip))
    dip_indices = np.where(in_dip)[0]
    dip_end = int(dip_indices[-1]) + 1

    # step 3: get anchor values before and after the dip
    pre_slice = raw[max(0, dip_start - 3):dip_start]
    pre_anchor = float(np.mean(pre_slice)) if len(pre_slice) > 0 else float(raw[0])
    if dip_end < n:
        post_anchor = float(np.mean(raw[dip_end:min(dip_end + 3, n)]))
    else:
        post_anchor = pre_anchor * 0.9

    # step 4: linear interpolation through the dip zone
    out = raw.copy()
    dip_len = dip_end - dip_start
    for i in range(dip_start, min(dip_end, n)):
        t = (i - dip_start) / max(dip_len, 1)
        interpolated = pre_anchor * (1 - t) + post_anchor * t
        # blend: use interpolated value if raw is in the dip, keep raw otherwise
        out[i] = interpolated

    # step 5: mild EMA to ensure overall smoothness
    smoothed = [out[0]]
    for i in range(1, n):
        smoothed.append(0.6 * out[i] + 0.4 * smoothed[-1])
    out = np.array(smoothed)

    # step 6: cap month-over-month change to ±15% for stability
    for i in range(1, n):
        if out[i - 1] > 0.02:
            max_val = out[i - 1] * 1.15
            min_val = out[i - 1] * 0.85
            out[i] = float(np.clip(out[i], min_val, max_val))

    result = []
    for i, row in enumerate(rows):
        patched = dict(row)
        patched["raw_predicted_demand_index"] = float(raw[i])
        patched["predicted_demand_index"] = round(float(np.clip(out[i], 0.0, 1.0)), 6)
        result.append(patched)
    return result


def _is_display_ready_curve(rows: list[dict[str, Any]]) -> bool:
    ready_bases = {
        "calibrated_category_role_curve",
        "patchtst_drop_artifact_repaired",
        "patchtst_common_sense_demo_shaped",
    }
    return bool(rows) and all(row.get("trend_direction_basis") in ready_bases for row in rows)


def _robust_trend_direction(rows: list[dict[str, Any]], current: float) -> str:
    """Determine trend from the reliable early prediction window (first 12
    months) rather than the full long horizon which suffers from model
    drift.  Uses both regression slope and magnitude of change.

    Calibrated against actual slope distribution of 69 IT roles:
      - slope > 0.002: ~5 emerging roles (AI Agent, LLM Inference, etc.)
      - slope < -0.005: ~11 declining roles (traditional high-demand roles
        showing regression to mean)
      - middle ~53 roles: genuinely stable/flat
    """
    values = np.array([float(r["predicted_demand_index"]) for r in rows])
    n = len(values)
    if n < 3:
        change = values[-1] - current
        if change >= 0.05:
            return "up"
        if change <= -0.05:
            return "down"
        return "flat"

    reliable_n = min(12, n)
    reliable = values[:reliable_n]
    if not np.all(np.isfinite(reliable)):
        return "flat"

    x = np.arange(reliable_n, dtype=float)
    slope = float(np.polyfit(x, reliable, 1)[0])
    avg_reliable = float(np.mean(reliable))
    change_from_current = avg_reliable - current

    # up: clear positive slope in reliable window
    if slope > 0.002:
        return "up"
    # down: strong negative slope, or moderate slope + meaningful magnitude
    if slope < -0.005:
        return "down"
    if slope < -0.003 and change_from_current < -0.03:
        return "down"
    return "flat"


def predict(role: str, months: int = 36) -> dict[str, Any]:
    canonical = _canonical_role(role)
    rows = [row for row in _load_predictions() if row.get("canonical_role") == canonical]
    rows = sorted(rows, key=lambda row: int(row.get("step", 0)))
    if not rows:
        raise TrendPredictionNotFoundError(f"no PatchTST prediction found for {canonical}")
    months = max(1, min(int(months), len(rows)))
    selected = rows[:months]

    if months <= 12:
        # short-term: raw predictions are reliable, no smoothing needed
        final = selected[-1]
        return {
            "canonical_role": canonical,
            "horizon_months": months,
            "trend_direction": final["trend_direction"],
            "predicted_demand_index": final["predicted_demand_index"],
            "confidence": final["confidence"],
            "monthly_forecast": selected,
        }

    if _is_display_ready_curve(selected):
        tail_months = selected[-min(6, len(selected)):]
        avg_demand = round(float(np.mean([r["predicted_demand_index"] for r in tail_months])), 6)
        return {
            "canonical_role": canonical,
            "horizon_months": months,
            "trend_direction": selected[-1]["trend_direction"],
            "predicted_demand_index": avg_demand,
            "confidence": selected[-1]["confidence"],
            "monthly_forecast": selected,
        }

    # long-term (>12 months): apply smoothing to fix mid-horizon dip artifact
    selected = _smooth_predictions(selected)

    try:
        panel = _load_panel()
        role_panel = panel[panel["canonical_role"] == canonical].sort_values("time_idx")
        current = float(role_panel[TARGET_COL].iloc[-1]) if not role_panel.empty else 0.0
    except Exception:
        current = float(selected[0].get("predicted_demand_index", 0.0))

    direction = _robust_trend_direction(selected, current)
    # use average of last 6 months as summary demand index (more stable)
    tail_months = selected[-min(6, len(selected)):]
    avg_demand = round(float(np.mean([r["predicted_demand_index"] for r in tail_months])), 6)

    return {
        "canonical_role": canonical,
        "horizon_months": months,
        "trend_direction": direction,
        "predicted_demand_index": avg_demand,
        "confidence": selected[-1]["confidence"],
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
