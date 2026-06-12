from pathlib import Path
from importlib.util import find_spec

import pytest

HAS_TORCH = find_spec("torch") is not None


def test_patchtst_torch_dependency_is_declared():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "torch" in requirements


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_load_patchtst_panel_uses_allowed_dataset_only(tmp_path):
    from pipelines.trend.patchtst_predictor import load_patchtst_panel

    with pytest.raises(ValueError):
        load_patchtst_panel(tmp_path / "other.json")


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_build_supervised_windows_keeps_roles_separate():
    from pipelines.trend.patchtst_predictor import PatchTSTConfig, build_supervised_windows, load_patchtst_panel

    panel = load_patchtst_panel()
    config = PatchTSTConfig(context_length=24, horizon=36)
    x, y, meta = build_supervised_windows(panel, config)
    assert x.shape[1:] == (24, 1)
    assert y.shape[1] == 36
    assert len(meta) == len(x)
    assert all("canonical_role" in item for item in meta)


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_build_supervised_windows_excludes_unobserved_targets():
    import pandas as pd

    from pipelines.trend.patchtst_predictor import FEATURE_COLS, PatchTSTConfig, build_supervised_windows

    rows = []
    for time_idx in range(8):
        row = {
            "canonical_role": "AI Engineer",
            "time_idx": time_idx,
            "month": pd.Timestamp("2025-01-01") + pd.DateOffset(months=time_idx),
            "jd_demand_observed": time_idx < 7,
        }
        row.update({feature: 0.5 for feature in FEATURE_COLS})
        rows.append(row)

    x, y, _ = build_supervised_windows(pd.DataFrame(rows), PatchTSTConfig(context_length=3, horizon=2))

    assert len(x) == 3
    assert len(y) == 3


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_patchtst_forward_shape():
    import torch

    from pipelines.trend.patchtst_predictor import PatchTST, PatchTSTConfig

    config = PatchTSTConfig(context_length=24, horizon=36, patch_len=6, stride=3)
    model = PatchTST(config, n_features=1)
    x = torch.zeros(4, 24, 1)
    y = model(x)
    assert tuple(y.shape) == (4, 36)


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_patchtst_training_uses_jd_only():
    from pipelines.trend.patchtst_predictor import FEATURE_COLS

    assert FEATURE_COLS == ["jd_demand_index"]
    assert "google_trend_index" not in FEATURE_COLS


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_trend_direction_uses_change_from_latest():
    from pipelines.trend.patchtst_predictor import direction_from_change

    assert direction_from_change(0.03) == "up"
    assert direction_from_change(0.02) == "flat"
    assert direction_from_change(-0.02) == "flat"
    assert direction_from_change(-0.03) == "down"


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_supplemental_signals_ignore_missing_and_single_month_sources():
    import pandas as pd

    from pipelines.trend.patchtst_predictor import build_supplemental_signals

    group = pd.DataFrame(
        [
            {
                "month": pd.Timestamp("2026-04-01"),
                "gdelt_observed": False,
                "github_observed": True,
                "arxiv_observed": True,
                "gdelt_sentiment_index": 0.0,
                "gdelt_opportunity_index": 0.0,
                "gdelt_risk_index": 0.0,
                "gdelt_event_impact_score": 0.0,
                "github_repo_count": 100.0,
                "github_repo_stars": 10.0,
                "arxiv_paper_count": 2.0,
            },
            {
                "month": pd.Timestamp("2026-05-01"),
                "gdelt_observed": False,
                "github_observed": True,
                "arxiv_observed": False,
                "gdelt_sentiment_index": 0.0,
                "gdelt_opportunity_index": 0.0,
                "gdelt_risk_index": 0.0,
                "gdelt_event_impact_score": 0.0,
                "github_repo_count": 120.0,
                "github_repo_stars": 12.0,
                "arxiv_paper_count": 0.0,
            },
        ]
    )

    signals = build_supplemental_signals(group, pd.Timestamp("2026-05-01"))

    assert signals["gdelt"]["signal"] is None
    assert not signals["gdelt"]["eligible"]
    assert signals["github"]["eligible"]
    assert signals["github"]["base_contribution"] > 0
    assert signals["arxiv"]["observed"]
    assert not signals["arxiv"]["eligible"]
    assert signals["arxiv"]["base_contribution"] == 0.0


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_github_signal_uses_within_role_log_trend():
    import numpy as np

    from pipelines.trend.patchtst_predictor import _robust_trend

    small = _robust_trend(np.array([100.0, 120.0, 150.0]), log_scale=True)
    large = _robust_trend(np.array([10000.0, 12000.0, 15000.0]), log_scale=True)

    assert small > 0
    assert large > 0
    assert abs(small - large) < 0.05


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_supplemental_adjustment_caps_and_decays():
    from pipelines.trend.patchtst_predictor import calibration_for_step, signal_decay

    signals = {
        source: {
            "eligible": True,
            "base_contribution": contribution,
        }
        for source, contribution in {"gdelt": 0.03, "github": 0.015, "arxiv": 0.01}.items()
    }

    step_1, _, details_1 = calibration_for_step(signals, 1)
    step_4, _, _ = calibration_for_step(signals, 4)
    step_6, _, _ = calibration_for_step(signals, 6)
    step_7, _, details_7 = calibration_for_step(signals, 7)

    assert step_1 == pytest.approx(0.05)
    assert step_4 == pytest.approx(0.0375)
    assert step_6 == pytest.approx(0.0125)
    assert step_7 == 0.0
    assert signal_decay(3) == 1.0
    assert sum(item["contribution"] for item in details_1.values()) == pytest.approx(step_1, abs=1e-6)
    assert all(item["contribution"] == 0.0 for item in details_7.values())


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_missing_or_stale_supplemental_data_does_not_adjust_prediction():
    import pandas as pd

    from pipelines.trend.patchtst_predictor import build_supplemental_signals, calibration_for_step

    group = pd.DataFrame(
        [
            {
                "month": pd.Timestamp("2025-01-01"),
                "gdelt_observed": False,
                "github_observed": True,
                "arxiv_observed": False,
                "gdelt_sentiment_index": 0.0,
                "gdelt_opportunity_index": 0.0,
                "gdelt_risk_index": 0.0,
                "gdelt_event_impact_score": 0.0,
                "github_repo_count": 100.0,
                "github_repo_stars": 10.0,
                "arxiv_paper_count": 0.0,
            },
            {
                "month": pd.Timestamp("2025-02-01"),
                "gdelt_observed": False,
                "github_observed": True,
                "arxiv_observed": False,
                "gdelt_sentiment_index": 0.0,
                "gdelt_opportunity_index": 0.0,
                "gdelt_risk_index": 0.0,
                "gdelt_event_impact_score": 0.0,
                "github_repo_count": 120.0,
                "github_repo_stars": 12.0,
                "arxiv_paper_count": 0.0,
            },
        ]
    )

    signals = build_supplemental_signals(group, pd.Timestamp("2026-05-01"))
    adjustment, quality, _ = calibration_for_step(signals, 1)

    assert signals["github"]["stale"]
    assert not signals["github"]["eligible"]
    assert adjustment == 0.0
    assert quality == 0.0


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_service_prediction_interfaces_return_stable_structures():
    from app.services import trend_predictor as service
    from pipelines.trend.patchtst_predictor import MILESTONE_STEPS

    if not Path("data/gold/patchtst_predictions_36m.json").exists():
        pytest.skip("PatchTST prediction deliverables have not been generated")
    service.clear_cache()
    forecast = service.predict("AI Engineer", months=36)
    assert forecast["canonical_role"] == "AI Engineer"
    assert len(forecast["monthly_forecast"]) == 36

    milestones = service.get_milestones("AI Engineer")
    assert [item["step"] for item in milestones["milestones"]] == MILESTONE_STEPS

    evidence = service.get_evidence("AI Engineer", "2029-05-01")
    assert evidence["canonical_role"] == "AI Engineer"
    assert evidence["history_window"] == "full_77_months"
    assert "jd_demand_index" in evidence["historical_trend"]
    assert len(evidence["historical_trend"]["months"]) == 77
    assert "gdelt_sentiment_index" in evidence["historical_trend"]
    assert "github_repo_count" in evidence["historical_trend"]
    assert evidence["jd_observed_range"]["last_nonzero_month"] == "2025-04-01"
    assert evidence["recent_window"]["jd_demand_index_all_zero"] is True
    assert isinstance(evidence["key_factors"], list)
    for point in evidence["turning_points"]:
        assert point["change_ratio"] is None or abs(point["change_ratio"]) < 1000


@pytest.mark.skipif(not HAS_TORCH, reason="torch is required for PatchTST tests")
def test_alias_resolution_for_service_if_deliverables_exist():
    from app.services import trend_predictor as service

    if not Path("data/gold/patchtst_predictions_36m.json").exists():
        pytest.skip("PatchTST prediction deliverables have not been generated")
    service.clear_cache()
    taxonomy = service._load_taxonomy()
    role_with_alias = next((role for role in taxonomy if role.get("aliases")), None)
    if role_with_alias is None:
        pytest.skip("No aliases in role taxonomy")
    alias = role_with_alias["aliases"][0]
    forecast = service.predict(alias, months=3)
    assert forecast["canonical_role"] == role_with_alias["canonical_role"]
    assert len(forecast["monthly_forecast"]) == 3
