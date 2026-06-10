import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd

from pipelines.trend.common import (
    build_processed_jd_rows,
    compute_jd_demand_index,
    find_candidate_jd_tables,
    looks_it_related_loose,
    normalize_optional_float,
)
from pipelines.trend.score_role_trends import compute_confidence, score_direction


def test_build_processed_jd_rows_prefers_best_role():
    taxonomy = [
        {
            "role_id": "role_001",
            "canonical_role": "AI Agent Engineer",
            "aliases": ["agentic ai engineer"],
            "top_skills": ["AI Agent", "LangChain", "RAG", "Python"],
        },
        {
            "role_id": "role_011",
            "canonical_role": "RAG Engineer",
            "aliases": ["generative ai engineer"],
            "top_skills": ["RAG", "Vector Database", "LangChain", "Embedding"],
        },
    ]
    raw_rows = [
        {
            "source": "test",
            "source_job_id": "1",
            "raw_job_title": "Agentic AI Engineer",
            "raw_jd_text": "Build AI Agent systems with LangChain and Python",
            "salary_mid": 220000,
            "post_date": "2026-06-01T00:00:00Z",
            "education_required": "Bachelor",
            "experience_required_years": 3,
            "company_name": "A",
            "work_arrangement": "remote",
            "job_url": "https://example.com/1",
        }
    ]

    rows = build_processed_jd_rows(raw_rows, taxonomy)
    assert len(rows) == 1
    assert rows[0]["canonical_role"] == "AI Agent Engineer"
    assert rows[0]["matched_by"] in {"alias", "mixed"}


def test_compute_jd_demand_index():
    df = pd.DataFrame(
        [
            {"job_post_count": 100, "unique_company_count": 50, "avg_salary_mid": 200000, "median_salary_mid": 210000, "jd_skill_hit_rate": 0.8},
            {"job_post_count": 10, "unique_company_count": 5, "avg_salary_mid": 100000, "median_salary_mid": 100000, "jd_skill_hit_rate": 0.2},
        ]
    )
    scores = compute_jd_demand_index(df)
    assert scores.iloc[0] > scores.iloc[1]
    assert 0.0 <= scores.iloc[0] <= 1.0
    assert 0.0 <= scores.iloc[1] <= 1.0


def test_score_direction_and_confidence():
    assert score_direction(0.7) == "up"
    assert score_direction(0.5) == "flat"
    assert score_direction(0.2) == "down"

    low = compute_confidence(pd.Series({"available_source_count": 1, "job_post_count": 0, "gdelt_article_count": 0, "google_trend_index": 0, "github_repo_count": 0, "arxiv_paper_count": 0}))
    high = compute_confidence(pd.Series({"available_source_count": 3, "job_post_count": 20, "gdelt_article_count": 10, "google_trend_index": 30, "github_repo_count": 4, "arxiv_paper_count": 2}))
    assert high > low


def test_find_candidate_jd_tables_and_loose_it_filter():
    tmp_path = Path(f"tests/.tmp_trend_pipeline_{uuid4().hex}")
    tmp_path.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "job_title": "Backend Python Engineer",
                "job_description": "Build APIs with Python, FastAPI, SQL and Docker.",
                "posted_date": "2024-06-01",
            },
            {
                "job_title": "Marketing Manager",
                "job_description": "Own campaigns and brand.",
                "posted_date": "2024-06-01",
            },
        ]
    )
    csv_path = tmp_path / "jobs.csv"
    df.to_csv(csv_path, index=False)
    matches = find_candidate_jd_tables(tmp_path)
    assert len(matches) == 1
    _, _, column_map = matches[0]
    assert column_map["title"] == "job_title"
    assert column_map["desc"] == "job_description"
    taxonomy = [
        {"canonical_role": "Backend Python Engineer", "aliases": ["python backend engineer"], "top_skills": ["Python", "FastAPI", "SQL"]},
        {"canonical_role": "RAG Engineer", "aliases": ["generative ai engineer"], "top_skills": ["RAG", "LangChain", "LLM"]},
    ]
    assert looks_it_related_loose("Backend Python Engineer", "Python FastAPI SQL Docker", taxonomy) is True
    assert looks_it_related_loose("Marketing Manager", "brand growth and campaigns", taxonomy) is False
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_build_processed_jd_rows_skips_weak_skill_only_match():
    taxonomy = [
        {
            "role_id": "role_java",
            "canonical_role": "Backend Java Engineer",
            "aliases": [],
            "top_skills": ["Java", "Spring", "REST API", "Microservices", "AWS"],
        }
    ]
    raw_rows = [
        {
            "source": "test",
            "source_job_id": "1",
            "raw_job_title": "Senior Software Engineer",
            "raw_jd_text": "Need Java, Spring and AWS experience.",
            "salary_mid": 180000,
            "post_date": "2026-06-01T00:00:00Z",
            "education_required": "Bachelor",
            "experience_required_years": 5,
            "company_name": "A",
            "work_arrangement": "remote",
            "job_url": "https://example.com/1",
        }
    ]
    assert build_processed_jd_rows(raw_rows, taxonomy) == []


def test_normalize_optional_float_cleans_nan():
    assert normalize_optional_float(None) is None
    assert normalize_optional_float(float("nan")) is None
    assert normalize_optional_float(float("inf")) is None
    assert normalize_optional_float("123.4") == 123.4


def test_generic_role_requires_role_family_title_evidence_for_skill_only():
    taxonomy = [
        {
            "role_id": "role_delivery",
            "canonical_role": "Delivery Manager",
            "aliases": [],
            "top_skills": ["Agile", "Jira", "Confluence", "Scrum", "Kanban"],
        }
    ]
    raw_rows = [
        {
            "source": "test",
            "source_job_id": "1",
            "raw_job_title": "Agile Coach",
            "raw_jd_text": "Agile, Jira, Confluence, Scrum, Kanban.",
            "salary_mid": None,
            "post_date": "2026-06-01T00:00:00Z",
            "education_required": None,
            "experience_required_years": None,
            "company_name": "A",
            "work_arrangement": "remote",
            "job_url": "https://example.com/1",
        }
    ]
    assert build_processed_jd_rows(raw_rows, taxonomy) == []
