import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
_needs_roles = pytest.mark.skipif(
    not os.path.exists(_ROLES_JSON),
    reason=f"missing roles json: {_ROLES_JSON}",
)


def test_health():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@_needs_roles
def test_profile_extract_and_recommend(monkeypatch):
    from app.schemas.domain import JobRole, LearningPath, RecommendationItem, SkillGap

    monkeypatch.setattr(
        "app.api.routes.RecommenderService.recommend",
        lambda profile, preference, top_k: [
            RecommendationItem(
                job=JobRole(
                    job_id="role_000",
                    title="Machine Learning Engineer",
                    fine_role="Machine Learning Engineer",
                    coarse_role="ai",
                    required_skills=["Python"],
                ),
                final_score=0.73,
                semantic_score=0.82,
                constraint_score=0.41,
                path_cost_score=0.23,
                trend_reward_score=0.19,
                explanation="stub recommendation",
                skill_gap=SkillGap(missing_skills=["Machine Learning"], overlap_skills=["Python"], optional_skills=[]),
            )
        ],
    )
    profile_resp = client.post(
        "/v1/profile/extract",
        json={"resume_text": "Python SQL LangChain", "github_url": "https://github.com/example", "user_id": "demo"},
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()["profile"]

    rec_resp = client.post("/v1/jobs/recommend", json={"profile": profile, "preference": {}})
    assert rec_resp.status_code == 200
    assert len(rec_resp.json()["items"]) > 0


@_needs_roles
def test_careers_rank(monkeypatch):
    from app.schemas.domain import JobRole, LearningPath, SkillGap

    job = JobRole(
        job_id="role_000",
        title="Machine Learning Engineer",
        fine_role="Machine Learning Engineer",
        coarse_role="ai",
        required_skills=["Python"],
    )
    gap = SkillGap(missing_skills=["Machine Learning"], overlap_skills=["Python"], optional_skills=[])
    path = LearningPath(target_job_id="role_000", total_steps=2, total_estimated_hours=40, score=0.6, steps=[])
    monkeypatch.setattr(
        "app.api.routes.coarse_recall",
        lambda profile, top_n: [
            {"job_id": "role_000", "semantic_score": 0.82, "job": job}
        ],
    )
    monkeypatch.setattr(
        "app.api.routes.rank_careers",
        lambda profile, preference, top_n: [
            {
                "job": job,
                "role_score": 0.73,
                "semantic_score": 0.82,
                "score_breakdown": {"semantic": 0.82, "coverage": 0.4},
                "skill_gap": gap,
                "path": path,
            }
        ],
    )
    resp = client.post(
        "/v1/careers/rank",
        json={
            "resume_text": "Python FastAPI SQL PostgreSQL Docker",
            "user_id": "career-demo",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["normalized_skill_ids"]
    assert len(payload["coarse_matches"]) >= 1
    assert len(payload["ranked_results"]) >= 1


def test_paths_trends_and_reserved_chat():
    profile = client.post("/v1/profile/extract", json={"resume_text": "Python SQL", "user_id": "demo2"}).json()["profile"]
    path_resp = client.post(
        "/v1/paths/generate",
        json={"profile": profile, "target_job_id": "job_rag_001", "candidate_skills": ["RAG", "LangChain"]},
    )
    assert path_resp.status_code == 200

    trend_resp = client.get("/v1/trends/rag-engineer")
    assert trend_resp.status_code == 200

    chat_resp = client.post("/v1/chat/decision", json={"query": "give me guidance", "profile": profile, "top_k": 3})
    assert chat_resp.status_code == 501
    assert "reserved" in chat_resp.json()["detail"].lower()


@_needs_roles
def test_careers_report(monkeypatch):
    from app.schemas.domain import JobRole, LearningPath, SkillGap

    job = JobRole(
        job_id="role_000",
        title="Machine Learning Engineer",
        fine_role="Machine Learning Engineer",
        coarse_role="ai",
        required_skills=["Python"],
    )
    gap = SkillGap(missing_skills=["Machine Learning"], overlap_skills=["Python"], optional_skills=[])
    path = LearningPath(target_job_id="role_000", total_steps=2, total_estimated_hours=40, score=0.6, steps=[])
    monkeypatch.setattr(
        "app.api.routes.coarse_recall",
        lambda profile, top_n: [
            {
                "job_id": "role_000",
                "semantic_score": 0.82,
                "job": job,
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.routes.rank_careers",
        lambda profile, preference, top_n: [
            {
                "job": job,
                "role_score": 0.73,
                "semantic_score": 0.82,
                "score_breakdown": {"semantic": 0.82, "coverage": 0.4},
                "skill_gap": gap,
                "path": path,
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.routes.generate_career_report",
        lambda profile, normalized_skill_ids, coarse_matches, ranked_results, audience, language: ("# Report", "stub-model"),
    )

    resp = client.post(
        "/v1/careers/report",
        json={
            "resume_text": "Python FastAPI SQL PostgreSQL Docker",
            "user_id": "career-report-demo",
            "top_k": 1,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["report_markdown"] == "# Report"
    assert payload["report_model"] == "stub-model"
    assert payload["ranked_results"]
