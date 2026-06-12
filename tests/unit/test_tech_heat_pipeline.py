import pandas as pd
import pytest

from pipelines.trend.build_role_month_features import aggregate_tech
from datetime import date

from pipelines.trend.collect_tech_heat import build_role_query_terms, build_term_role_map, complete_month_windows, consolidate_rows, expand_keyword_rows, selected_role_records
from pipelines.trend.prepare_trend_model_dataset import build_patchtst_panel


def test_selected_role_records_respects_limits(monkeypatch):
    import pipelines.trend.collect_tech_heat as tech_heat_module

    monkeypatch.setattr(tech_heat_module.settings, "trend_tech_role_limit", 1)
    monkeypatch.setattr(tech_heat_module.settings, "trend_tech_skill_limit", 2)
    rows = selected_role_records(
        [
            {"canonical_role": "RAG Engineer", "top_skills": ["RAG", "LangChain", "Vector Database"]},
            {"canonical_role": "AI Agent Engineer", "top_skills": ["AI Agent", "LLM"]},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["canonical_role"] == "RAG Engineer"
    assert len(rows[0]["top_skills"]) == 2
    assert all(rows[0]["top_skills"])


def test_consolidate_rows_merges_same_keyword_month():
    df = consolidate_rows(
        [
            {
                "canonical_role": "RAG Engineer",
                "keyword": "RAG",
                "month": "2026-01-01",
                "google_trend_index": 40.0,
                "github_repo_count": None,
                "github_repo_stars": None,
                "arxiv_paper_count": None,
            },
            {
                "canonical_role": "RAG Engineer",
                "keyword": "RAG",
                "month": "2026-01-01",
                "google_trend_index": 55.0,
                "github_repo_count": 12,
                "github_repo_stars": 100.0,
                "arxiv_paper_count": 3,
            },
        ]
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["google_trend_index"] == 55.0
    assert row["github_repo_count"] == 12
    assert row["github_repo_stars"] == 100.0
    assert row["arxiv_paper_count"] == 3


def test_term_role_map_and_expand_rows():
    records = [
        {"canonical_role": "RAG Engineer", "aliases": ["Generative AI Engineer"], "top_skills": ["Python", "RAG"]},
        {"canonical_role": "AI Agent Engineer", "aliases": ["Agentic AI Engineer"], "top_skills": ["Python", "LLM"]},
    ]
    mapping = build_term_role_map(records)
    assert "Python" not in mapping
    assert "RAG Engineer" in build_role_query_terms(records[0])
    assert "Generative AI Engineer" in build_role_query_terms(records[0])
    assert mapping["RAG"] == ["RAG Engineer"]
    expanded = expand_keyword_rows(
        [
            {
                "keyword": "Agentic AI Engineer",
                "month": "2026-06-01",
                "google_trend_index": None,
                "github_repo_count": 10,
                "github_repo_stars": 50.0,
                "arxiv_paper_count": 2,
            }
        ],
        mapping,
    )
    assert len(expanded) == 1
    assert {row["canonical_role"] for row in expanded} == {"AI Agent Engineer"}


def test_complete_month_windows_excludes_current_partial_month():
    windows = complete_month_windows(6, today=date(2026, 6, 9))
    assert [window.month for window in windows] == [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
    ]


def test_aggregate_tech_uses_skill_weights():
    taxonomy = [
        {"canonical_role": "RAG Engineer", "top_skills": ["RAG", "LangChain"]},
    ]
    tech = pd.DataFrame(
        [
            {
                "canonical_role": "RAG Engineer",
                "keyword": "RAG",
                "month": "2026-01-01",
                "google_trend_index": 90.0,
                "github_repo_count": 20.0,
                "github_repo_stars": 300.0,
                "arxiv_paper_count": 4.0,
            },
            {
                "canonical_role": "RAG Engineer",
                "keyword": "LangChain",
                "month": "2026-01-01",
                "google_trend_index": 30.0,
                "github_repo_count": 10.0,
                "github_repo_stars": 100.0,
                "arxiv_paper_count": 2.0,
            },
        ]
    )
    result = aggregate_tech(tech, taxonomy)
    row = result.iloc[0]
    assert row["google_trend_index"] > 50.0
    assert row["google_trend_index"] < 90.0
    assert row["github_repo_count"] > 10.0
    assert row["github_repo_stars"] > 100.0


def test_build_patchtst_panel_creates_dense_role_month_grid(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "trend_patchtst_lookback_months", 3)
    role_month = pd.DataFrame(
        [
            {"canonical_role": "RAG Engineer", "month": "2026-01-01", "jd_demand_index": 0.8, "job_post_count": 10},
            {"canonical_role": "RAG Engineer", "month": "2026-03-01", "jd_demand_index": 0.7, "job_post_count": 8},
            {"canonical_role": "AI Agent Engineer", "month": "2026-02-01", "jd_demand_index": 0.9, "job_post_count": 12},
        ]
    )
    taxonomy = pd.DataFrame(
        [
            {"role_id": "role_011", "canonical_role": "RAG Engineer"},
            {"role_id": "role_002", "canonical_role": "AI Agent Engineer"},
        ]
    )
    panel = build_patchtst_panel(role_month, taxonomy)
    assert len(panel) == 6
    rag_feb = panel[(panel["canonical_role"] == "RAG Engineer") & (panel["month"] == "2026-02-01")].iloc[0]
    assert rag_feb["jd_demand_index"] == 0.0
    assert rag_feb["time_idx"] == 1
    ai_jan = panel[(panel["canonical_role"] == "AI Agent Engineer") & (panel["month"] == "2026-01-01")].iloc[0]
    assert ai_jan["job_post_count"] == 0.0


def test_build_patchtst_panel_does_not_turn_missing_future_jd_data_into_zero(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "trend_patchtst_lookback_months", 4)
    role_month = pd.DataFrame(
        [
            {"canonical_role": "AI Engineer", "month": "2026-01-01", "jd_demand_index": 0.6, "job_post_count": 10},
            {"canonical_role": "AI Engineer", "month": "2026-02-01", "jd_demand_index": 0.7, "job_post_count": 12},
            {"canonical_role": "AI Engineer", "month": "2026-04-01", "gdelt_article_count": 5},
        ]
    )
    taxonomy = pd.DataFrame([{"role_id": "role_001", "canonical_role": "AI Engineer"}])

    panel = build_patchtst_panel(role_month, taxonomy)
    march = panel[panel["month"] == "2026-03-01"].iloc[0]
    april = panel[panel["month"] == "2026-04-01"].iloc[0]

    assert march["jd_demand_index"] == pytest.approx(0.7)
    assert april["jd_demand_index"] == pytest.approx(0.7)
    assert not bool(march["jd_demand_observed"])
    assert not bool(april["jd_demand_observed"])


def test_build_patchtst_panel_does_not_mark_roles_without_jd_labels_as_observed(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "trend_patchtst_lookback_months", 2)
    role_month = pd.DataFrame(
        [
            {"canonical_role": "AI Engineer", "month": "2026-01-01", "jd_demand_index": 0.6, "job_post_count": 10},
            {"canonical_role": "RAG Engineer", "month": "2026-01-01", "gdelt_article_count": 5},
            {"canonical_role": "RAG Engineer", "month": "2026-02-01", "gdelt_article_count": 8},
        ]
    )
    taxonomy = pd.DataFrame(
        [
            {"role_id": "role_001", "canonical_role": "AI Engineer"},
            {"role_id": "role_002", "canonical_role": "RAG Engineer"},
        ]
    )

    panel = build_patchtst_panel(role_month, taxonomy)

    assert panel.loc[panel["canonical_role"] == "AI Engineer", "jd_demand_observed"].any()
    assert not panel.loc[panel["canonical_role"] == "RAG Engineer", "jd_demand_observed"].any()


def test_build_patchtst_panel_marks_only_real_supplemental_source_rows(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "trend_patchtst_lookback_months", 2)
    role_month = pd.DataFrame(
        [
            {
                "canonical_role": "AI Engineer",
                "month": "2026-01-01",
                "gdelt_article_count": 4,
                "github_repo_count": 20,
                "arxiv_paper_count": 0,
            },
            {
                "canonical_role": "AI Engineer",
                "month": "2026-02-01",
                "gdelt_article_count": 0,
                "github_repo_count": 25,
                "arxiv_paper_count": 3,
            },
        ]
    )
    taxonomy = pd.DataFrame([{"role_id": "role_001", "canonical_role": "AI Engineer"}])

    panel = build_patchtst_panel(role_month, taxonomy).sort_values("month")

    assert panel["gdelt_observed"].tolist() == [True, False]
    assert panel["github_observed"].tolist() == [True, True]
    assert panel["arxiv_observed"].tolist() == [False, True]


def test_prepare_patchtst_dataset_uses_corrected_local_json(monkeypatch, tmp_path):
    from pipelines.trend import prepare_trend_model_dataset as dataset_module

    source_path = tmp_path / "role_month_features.json"
    source_path.write_text("[]", encoding="utf-8")
    role_month = pd.DataFrame(
        [
            {
                "canonical_role": "AI Engineer",
                "month": "2026-01-01",
                "jd_demand_index": 0.6,
                "job_post_count": 10,
            }
        ]
    )
    read_paths = []
    written = {}

    def fake_read_json(path):
        read_paths.append(path)
        return role_month.copy()

    def fake_write(panel, parquet_path, json_path):
        written["panel"] = panel
        written["parquet_path"] = parquet_path
        written["json_path"] = json_path

    monkeypatch.setattr(dataset_module, "ROLE_MONTH_FEATURES_JSON", source_path)
    monkeypatch.setattr(dataset_module.settings, "trend_patchtst_lookback_months", 1)
    monkeypatch.setattr(dataset_module.pd, "read_json", fake_read_json)
    monkeypatch.setattr(
        dataset_module,
        "load_role_taxonomy_local",
        lambda: [{"role_id": "role_001", "canonical_role": "AI Engineer"}],
    )
    monkeypatch.setattr(dataset_module, "safe_write_dataframe", fake_write)

    dataset_module.main()

    assert read_paths == [source_path]
    assert len(written["panel"]) == 1
    assert written["panel"].iloc[0]["canonical_role"] == "AI Engineer"
