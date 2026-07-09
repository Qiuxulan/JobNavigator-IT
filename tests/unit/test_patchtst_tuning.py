from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import pipelines.trend.tune_patchtst as tuning
from pipelines.trend.tune_patchtst import (
    TrainResult,
    TuningConfig,
    common_aligned_windows,
    last_value_forecast,
    linear_trend_forecast,
    moving_average_forecast,
    split_aligned_windows,
    validate_config,
)


def synthetic_panel(months: int = 70, roles: int = 2) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "canonical_role": f"Role {role}",
            "month": pd.Timestamp("2020-01-01") + pd.DateOffset(months=time_idx),
            "time_idx": time_idx,
            "jd_demand_index": 0.2 + 0.01 * time_idx,
            "jd_demand_observed": True,
        }
        for role in range(roles)
        for time_idx in range(months)
    ])


def test_baseline_forecasts():
    x = np.arange(1, 25, dtype=np.float32)[None, :, None]
    assert last_value_forecast(x, 3).tolist() == [[24.0, 24.0, 24.0]]
    assert moving_average_forecast(x, 2, 3).tolist() == [[23.0, 23.0]]
    assert moving_average_forecast(x, 2, 6).tolist() == [[21.5, 21.5]]
    assert np.allclose(linear_trend_forecast(x / 100, 2, 12), [[0.25, 0.26]])


def test_config_validation_rejects_invalid_shapes():
    with pytest.raises(ValueError, match="context_length"):
        validate_config(TuningConfig(context_length=6, patch_len=12))
    with pytest.raises(ValueError, match="divide"):
        validate_config(TuningConfig(d_model=32, n_heads=3))


def test_context_candidates_share_identical_targets_and_strict_split():
    aligned = common_aligned_windows(synthetic_panel(months=90), [12, 24, 36])
    split, partitions = split_aligned_windows(aligned)
    keys = []
    for context in (12, 24, 36):
        train, validation, test = partitions[context]
        keys.append([
            (item["canonical_role"], item["forecast_start_time_idx"])
            for group in (train, validation, test)
            for item in group.meta
        ])
        assert max(item["forecast_end_time_idx"] for item in train.meta) < split.validation_origin
        assert max(item["forecast_end_time_idx"] for item in validation.meta) < split.test_origin
    assert keys[0] == keys[1] == keys[2]


def test_quick_run_generates_complete_artifacts_without_using_test_for_ranking(tmp_path, monkeypatch):
    dataset = tmp_path / "panel.json"
    output = tmp_path / "output"
    synthetic_panel(months=64).to_json(dataset, orient="records", date_format="iso")

    def fake_evaluate(experiment_id, stage, config, partitions, seed, patience):
        _, validation, _ = partitions[config.context_length]
        score = 0.05 + config.patch_len / 1000 + config.d_model / 100000
        metrics = {"mae": score, "rmse": score + 0.01, "smape": score + 0.02, "direction_accuracy": 0.5}
        result = TrainResult(np.zeros_like(validation.y), 2, 0.01, metrics)
        return {
            "experiment_id": experiment_id, "stage": stage, "seed": seed,
            **config.__dict__, "validation_mae": metrics["mae"],
            "validation_rmse": metrics["rmse"], "validation_smape": metrics["smape"],
            "validation_direction_accuracy": metrics["direction_accuracy"],
            "best_epoch": 2, "train_seconds": 0.01, "status": "ok",
        }, result

    def fake_final(train, test, config, seed, epochs, device=None):
        return last_value_forecast(test.x, 12) + config.patch_len / 10000

    def fake_sarima(validation, test, quick):
        return last_value_forecast(test.x, 12), {"order": [0, 0, 0], "seasonal_order": [0, 0, 0, 12]}

    monkeypatch.setattr(tuning, "_evaluate_candidate", fake_evaluate)
    monkeypatch.setattr(tuning, "train_final_model", fake_final)
    monkeypatch.setattr(tuning, "_sarima_test_prediction", fake_sarima)
    result = tuning.run_tuning(dataset, output, mode="quick", max_epochs=2, patience=1)

    assert result["status"] == "ok"
    expected = {
        "tuning_results.csv", "seed_confirmation.csv", "best_config.json",
        "baseline_comparison.csv", "predictions.csv", "role_metrics.csv",
        "horizon_metrics.csv", "experiment_config.json", "tuning_report.md",
    }
    assert expected.issubset({path.name for path in output.iterdir()})
    assert len(list((output / "plots").glob("*.png"))) == 9
    payload = (output / "best_config.json").read_text(encoding="utf-8")
    assert "test_mae" not in payload
