from __future__ import annotations

import os
from functools import lru_cache
from importlib.util import find_spec
from typing import Any

from app.schemas.domain import RecommendationItem, SkillGap, UserPreference, UserProfile
from app.services.career_catalog import jobrole_from_role, load_roles, role_top_skills
from app.services.graph_path_planner_v2 import GraphPathPlannerV2
from app.services.skill_norm import normalize_skill_id

MODEL_NAME = "TechWolf/JobBERT-v3"
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


class RecallSetupError(RuntimeError):
    pass


def _sanitize_runtime_env() -> None:
    ssl_keylog = os.environ.get("SSLKEYLOGFILE")
    if ssl_keylog and not os.path.exists(ssl_keylog):
        os.environ.pop("SSLKEYLOGFILE", None)


@lru_cache(maxsize=1)
def _load_engine():
    _sanitize_runtime_env()
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, local_files_only=True)


def _recall_topn(user_vec: Any, top_n: int, dsn: str) -> list[dict[str, Any]]:
    from pipelines.taxonomy.recall import recall_topn

    return recall_topn(user_vec, top_n, dsn)


def _profile_to_query_text(profile: UserProfile) -> str:
    return f"Target role: {profile.target_role or ''}. My skills: {', '.join(profile.skills or [])}"


def recall_preflight() -> dict[str, Any]:
    status: dict[str, Any] = {
        "model_name": MODEL_NAME,
        "dsn": DSN,
        "sentence_transformers": find_spec("sentence_transformers") is not None,
        "psycopg": find_spec("psycopg") is not None,
        "pgvector": find_spec("pgvector") is not None,
        "model_ready": False,
        "db_ready": False,
        "embedding_count": 0,
    }
    if not status["sentence_transformers"]:
        raise RecallSetupError("Missing dependency: sentence-transformers")
    if not status["psycopg"] or not status["pgvector"]:
        raise RecallSetupError("Missing dependency: psycopg and/or pgvector")

    try:
        _load_engine()
        status["model_ready"] = True
    except Exception as exc:
        raise RecallSetupError(f"TechWolf/JobBERT-v3 is not available in local cache: {exc}") from exc

    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=3, options="-c statement_timeout=2000") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM job_roles
                    WHERE embedding IS NOT NULL
                    """
                )
                count = int(cur.fetchone()[0])
        status["embedding_count"] = count
        status["db_ready"] = count > 0
    except Exception as exc:
        raise RecallSetupError(f"Vector database is unavailable: {exc}") from exc

    if status["embedding_count"] <= 0:
        raise RecallSetupError("job_roles.embedding is empty. Run pipelines.taxonomy.build_job_vectors first.")
    return status


def coarse_recall(profile: UserProfile, top_n: int = 10) -> list[dict[str, Any]]:
    roles_by_id = load_roles()
    recall_preflight()
    model = _load_engine()
    vector = model.encode(_profile_to_query_text(profile), normalize_embeddings=True)
    rows = _recall_topn(vector, top_n, DSN)
    return [
        {
            "job_id": row["job_id"],
            "semantic_score": round(float(row["score"]), 4),
            "job": jobrole_from_role(roles_by_id[row["job_id"]]),
        }
        for row in rows
        if row["job_id"] in roles_by_id
    ]


def rank_careers(profile: UserProfile, preference: UserPreference, top_n: int = 10) -> list[dict[str, Any]]:
    roles_by_id = load_roles()
    ranked = []
    for coarse in coarse_recall(profile, top_n=top_n):
        role = roles_by_id[coarse["job_id"]]
        analysis = GraphPathPlannerV2.analyze_role(
            profile=profile,
            target_job_id=coarse["job_id"],
            semantic_score=coarse["semantic_score"],
        )
        item = RecommendationItem(
            job=jobrole_from_role(role),
            final_score=analysis.role_score,
            semantic_score=analysis.semantic_score,
            constraint_score=analysis.score_breakdown["coverage"],
            path_cost_score=round(
                analysis.score_breakdown["prereq_penalty"] + analysis.score_breakdown["hours_penalty"],
                4,
            ),
            trend_reward_score=round(
                analysis.score_breakdown["resource_reward"] + analysis.score_breakdown["graph_reward"],
                4,
            ),
            explanation=(
                f"covered={len(analysis.skill_gap.overlap_skills)} "
                f"missing={len(analysis.skill_gap.missing_skills)} "
                f"hours={analysis.path.total_estimated_hours} "
                f"semantic={analysis.semantic_score:.2f}"
            ),
            skill_gap=SkillGap(
                missing_skills=analysis.skill_gap.missing_skills,
                overlap_skills=analysis.skill_gap.overlap_skills,
                optional_skills=[],
            ),
        )
        ranked.append(
            {
                "job_id": coarse["job_id"],
                "job": item.job,
                "semantic_score": analysis.semantic_score,
                "role_score": analysis.role_score,
                "recommendation": item,
                "score_breakdown": analysis.score_breakdown,
                "skill_gap": analysis.skill_gap,
                "path": analysis.path,
            }
        )
    ranked.sort(key=lambda row: row["role_score"], reverse=True)
    return ranked
