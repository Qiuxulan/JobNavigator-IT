from app.schemas.domain import LearningPath, LearningPathStep, UserPreference
from pipelines.graph.run_sample_rankings_v2 import build_report


def test_build_report_has_ranked_results(monkeypatch):
    monkeypatch.setattr(
        "pipelines.graph.run_sample_rankings_v2.recall_preflight",
        lambda: {"model_ready": True, "db_ready": True, "embedding_count": 69},
    )
    monkeypatch.setattr(
        "pipelines.graph.run_sample_rankings_v2.rank_careers",
        lambda profile, preference, top_n: [
            {
                "job": type("Job", (), {"job_id": "job_demo", "title": "Demo Role"})(),
                "role_score": 0.81,
                "semantic_score": 0.77,
                "score_breakdown": {"semantic": 0.77},
                "skill_gap": type(
                    "Gap",
                    (),
                    {"missing_skills": ["LangChain"], "overlap_skills": ["Python", "SQL"]},
                )(),
                "path": LearningPath(
                    target_job_id="job_demo",
                    total_steps=1,
                    total_estimated_hours=12,
                    score=0.8,
                    steps=[LearningPathStep(step_no=1, skill="LangChain", reason="demo", resources=[])],
                ),
            }
        ],
    )

    payload = build_report()
    assert len(payload) == 3
    for row in payload:
        assert row["profile"]["skills"]
        assert row["ranked_results"]
        assert row["ranked_results"][0]["path"]["total_steps"] >= 0
        assert row["preflight"]["model_ready"] is True
