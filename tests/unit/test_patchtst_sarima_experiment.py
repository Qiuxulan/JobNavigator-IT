from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipelines.trend.compare_patchtst_sarima import (
    WindowSet,
    assert_non_overlapping_targets,
    build_observed_windows,
    choose_temporal_split,
    direction_labels,
    metric_values,
    prediction_rows,
    safe_sarima_forecast,
    seasonal_naive_forecast,
    split_windows,
)


def synthetic_panel(months: int = 64, roles: int = 2) -> pd.DataFrame:
    rows = []
    for role_index in range(roles):
        for time_idx in range(months):
            rows.append(
                {
                    "canonical_role": f"Role {role_index}",
                    "month": pd.Timestamp("2020-01-01") + pd.DateOffset(months=time_idx),
                    "time_idx": time_idx,
                    "jd_demand_index": 0.4 + 0.1 * np.sin(2 * np.pi * time_idx / 12),
                    "jd_demand_observed": True,
                }
            )
    return pd.DataFrame(rows)


def test_temporal_split_has_non_overlapping_target_intervals():
    windows = build_observed_windows(synthetic_panel(), context_length=24, horizon=12)
    split = choose_temporal_split(windows, horizon=12)
    train, validation, test = split_windows(windows, split)

    assert split.train_max_origin == 28
    assert split.validation_origin == 40
    assert split.test_origin == 52
    assert_non_overlapping_targets(train, validation, test)
    assert max(item["forecast_end_time_idx"] for item in train.meta) < min(
        item["forecast_start_time_idx"] for item in validation.meta
    )
    assert max(item["forecast_end_time_idx"] for item in validation.meta) < min(
        item["forecast_start_time_idx"] for item in test.meta
    )


def test_observed_windows_exclude_missing_context_and_target_values():
    panel = synthetic_panel(months=70, roles=1)
    panel.loc[panel["time_idx"] == 5, "jd_demand_observed"] = False
    windows = build_observed_windows(panel, context_length=24, horizon=12)
    assert all(item["context_start_time_idx"] > 5 for item in windows.meta)


def test_metrics_handle_zero_values_and_direction_threshold():
    true = np.array([[0.0, 0.5, 0.7]], dtype=float)
    pred = np.array([[0.0, 0.4, 0.6]], dtype=float)
    baselines = np.array([0.5], dtype=float)
    metrics = metric_values(true, pred, baselines)

    assert all(np.isfinite(value) for value in metrics.values())
    assert metrics["mae"] == pytest.approx(0.2 / 3)
    assert direction_labels(true, baselines).tolist() == [[-1, 0, 1]]


def test_seasonal_naive_repeats_last_year():
    history = np.arange(24, dtype=float)
    prediction = seasonal_naive_forecast(history, horizon=12, period=12)
    assert prediction.tolist() == list(range(12, 24))


def test_sarima_failure_is_returned_instead_of_raised():
    def failing_factory(*args, **kwargs):
        raise RuntimeError("synthetic fit failure")

    result = safe_sarima_forecast(
        np.arange(24, dtype=float),
        horizon=12,
        order=(1, 0, 0),
        seasonal_order=(0, 0, 0, 12),
        model_factory=failing_factory,
    )
    assert result.prediction is None
    assert "synthetic fit failure" in result.error


def test_models_can_share_the_exact_same_test_samples():
    windows = build_observed_windows(synthetic_panel(), context_length=24, horizon=12)
    _, _, test = split_windows(windows, choose_temporal_split(windows, horizon=12))
    model_a = np.zeros_like(test.y)
    model_b = np.ones_like(test.y)
    assert model_a.shape == model_b.shape == test.y.shape
    assert [item["canonical_role"] for item in test.meta] == ["Role 0", "Role 1"]

    rows = prediction_rows(test, {"model_a": model_a, "model_b": model_b})
    assert len(rows) == 2 * 12
    assert set(rows[0]) == {"canonical_role", "month", "step", "actual", "model_a", "model_b"}
