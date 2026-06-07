from __future__ import annotations

import json
from pathlib import Path

from app.schemas.domain import UserPreference
from app.services.career_pathway_service import RecallSetupError, rank_careers, recall_preflight
from app.services.extractor import ExtractorService
from app.services.skill_norm import normalize_skill_id

ROOT = Path(__file__).parents[2]
REPORT_PATH = ROOT / "reports" / "sample_resume_rankings_v2.json"

SAMPLES = [
    {
        "sample_id": "backend_to_rag",
        "resume_text": (
            "5 years backend experience. Built FastAPI services with Python, PostgreSQL, Redis and Docker. "
            "Recently explored RAG, LangChain, vector databases and LLM applications."
        ),
    },
    {
        "sample_id": "analyst_to_data_eng",
        "resume_text": (
            "Data analyst with strong SQL, Python, Pandas, Excel and Tableau. "
            "Built ETL reports, dashboards, and used Airflow for scheduled jobs."
        ),
    },
    {
        "sample_id": "java_backend_to_ai",
        "resume_text": (
            "Java backend engineer using Spring Boot, MySQL, Redis, Linux and Docker. "
            "Interested in machine learning, PyTorch, NLP and AI agent systems."
        ),
    },
]


def build_report() -> list[dict]:
    preflight = recall_preflight()
    rows: list[dict] = []
    for sample in SAMPLES:
        profile = ExtractorService.extract(sample["resume_text"], None, sample["sample_id"])
        ranked = rank_careers(profile, UserPreference(), top_n=5)
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "resume_text": sample["resume_text"],
                "profile": {
                    "skills": profile.skills,
                    "skill_ids": [
                        skill_id
                        for skill_id in (normalize_skill_id(skill) for skill in profile.skills)
                        if skill_id
                    ],
                    "target_role": profile.target_role,
                },
                "ranked_results": [
                    {
                        "job_id": row["job"].job_id,
                        "title": row["job"].title,
                        "final_score": row["role_score"],
                        "semantic_score": row["semantic_score"],
                        "score_breakdown": row["score_breakdown"],
                        "skill_gap": {
                            "missing_skills": row["skill_gap"].missing_skills,
                            "overlap_skills": row["skill_gap"].overlap_skills,
                        },
                        "path": {
                            "target_job_id": row["path"].target_job_id,
                            "total_steps": row["path"].total_steps,
                            "total_estimated_hours": row["path"].total_estimated_hours,
                            "score": row["path"].score,
                            "steps": [
                                {
                                    "step_no": step.step_no,
                                    "skill": step.skill,
                                    "reason": step.reason,
                                    "resources": [
                                        {
                                            "resource_id": resource.resource_id,
                                            "title": resource.title,
                                            "provider": resource.provider,
                                            "level": resource.level,
                                        }
                                        for resource in step.resources
                                    ],
                                }
                                for step in row["path"].steps
                            ],
                        },
                    }
                    for row in ranked
                ],
                "preflight": preflight,
            }
        )
    return rows


def main() -> None:
    try:
        payload = build_report()
    except RecallSetupError as exc:
        print(json.dumps({"status": "setup_error", "detail": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "report": str(REPORT_PATH), "samples": len(payload)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
