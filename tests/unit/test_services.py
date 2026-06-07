import os

import pytest

from app.schemas.domain import UserPreference
from app.services.career_pathway_service import RecallSetupError, coarse_recall, rank_careers
from app.services.extractor import ExtractorService
from app.services.path_planner import PathPlannerService
from app.services.recommender import RecommenderService
from app.services.report_generator import build_report_messages

_ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
_needs_roles = pytest.mark.skipif(
    not os.path.exists(_ROLES_JSON),
    reason=f"missing roles json: {_ROLES_JSON}",
)


def test_extract_profile():
    profile = ExtractorService.extract("I use python and sql and rag", None, "u1")
    assert profile.user_id == "u1"
    assert "Python" in profile.skills


def test_extract_profile_merges_model_and_rules():
    profile = ExtractorService.extract("Python, SQL, machine learning, PyTorch and Docker", None, "u1b")
    assert {"Python", "SQL", "Machine Learning", "PyTorch", "Docker"} <= set(profile.skills)

    diagnostics = ExtractorService.diagnose("Python, SQL, machine learning, PyTorch and Docker")
    assert "Python" in diagnostics.rule_skills
    assert diagnostics.model_attempted is True
    assert "Machine Learning" in diagnostics.merged_skills


@_needs_roles
def test_recommendation(monkeypatch):
    profile = ExtractorService.extract("python sql", None, "u2")
    monkeypatch.setattr(
        "app.services.career_pathway_service.coarse_recall",
        lambda profile, top_n: [
            {
                "job_id": "role_000",
                "semantic_score": 0.8,
                "job": type("Job", (), {"job_id": "role_000"})(),
            }
        ],
    )
    recs = RecommenderService.recommend(profile, UserPreference(), 5)
    assert len(recs) >= 1
    assert recs[0].final_score >= 0


def test_path_generation():
    profile = ExtractorService.extract("python sql", None, "u3")
    path = PathPlannerService.generate(profile, "job_rag_001", ["LangChain", "RAG"])
    assert path.total_steps >= 1
    assert path.total_estimated_hours >= 0


@_needs_roles
def test_rank_careers_returns_paths(monkeypatch):
    profile = ExtractorService.extract("Python FastAPI SQL PostgreSQL Docker", None, "u4")
    monkeypatch.setattr(
        "app.services.career_pathway_service.coarse_recall",
        lambda profile, top_n: [
            {
                "job_id": "role_000",
                "semantic_score": 0.8,
                "job": type("Job", (), {"job_id": "role_000"})(),
            }
        ],
    )
    ranked = rank_careers(profile, UserPreference(), 10)
    assert ranked
    assert ranked[0]["path"].target_job_id
    assert "semantic" in ranked[0]["score_breakdown"]


@_needs_roles
def test_coarse_recall_returns_candidates(monkeypatch):
    profile = ExtractorService.extract("Python SQL machine learning Docker", None, "u5")
    monkeypatch.setattr(
        "app.services.career_pathway_service.recall_preflight",
        lambda: {
            "model_ready": True,
            "db_ready": True,
            "embedding_count": 69,
        },
    )
    monkeypatch.setattr(
        "app.services.career_pathway_service._load_engine",
        lambda: type("StubModel", (), {"encode": lambda self, text, normalize_embeddings=True: [0.1, 0.2, 0.3]})(),
    )
    monkeypatch.setattr(
        "app.services.career_pathway_service._recall_topn",
        lambda user_vec, n, dsn: [
            {"job_id": "role_000", "score": 0.81},
            {"job_id": "role_001", "score": 0.78},
        ],
    )
    candidates = coarse_recall(profile, top_n=5)
    assert candidates
    assert candidates[0]["job"].job_id


def test_coarse_recall_fails_fast_without_vector_setup(monkeypatch):
    profile = ExtractorService.extract("Python SQL machine learning Docker", None, "u6")

    def _fail():
        raise RecallSetupError("job_roles.embedding is empty. Run build_job_vectors first.")

    monkeypatch.setattr("app.services.career_pathway_service.recall_preflight", _fail)
    with pytest.raises(RecallSetupError):
        coarse_recall(profile, top_n=5)


@_needs_roles
def test_report_prompt_contains_ranked_context(monkeypatch):
    profile = ExtractorService.extract("Python FastAPI SQL PostgreSQL Docker", None, "u7")
    monkeypatch.setattr(
        "app.services.career_pathway_service.coarse_recall",
        lambda profile, top_n: [
            {
                "job_id": "role_000",
                "semantic_score": 0.8,
                "job": type("Job", (), {"job_id": "role_000"})(),
            }
        ],
    )
    ranked = rank_careers(profile, UserPreference(), 10)
    coarse_matches = [
        type(
            "CoarseMatchStub",
            (),
            {
                "job": ranked[0]["job"],
                "semantic_score": 0.8,
            },
        )()
    ]
    ranked_results = [
        type(
            "CareerRankedResultStub",
            (),
            {
                "job": ranked[0]["job"],
                "final_score": ranked[0]["role_score"],
                "semantic_score": ranked[0]["semantic_score"],
                "score_breakdown": ranked[0]["score_breakdown"],
                "skill_gap": ranked[0]["skill_gap"],
                "path": ranked[0]["path"],
            },
        )()
    ]
    messages = build_report_messages(
        profile=profile,
        normalized_skill_ids=["python", "sql-lang"],
        coarse_matches=coarse_matches,
        ranked_results=ranked_results,
        audience="candidate",
        language="zh-CN",
    )
    assert len(messages) == 2
    assert "Top10 粗召回观察" in messages[1]["content"]
    assert "python" in messages[1]["content"].lower()
