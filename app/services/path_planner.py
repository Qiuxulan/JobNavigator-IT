from __future__ import annotations

from app.schemas.domain import LearningPath, UserProfile
from app.services.graph_path_planner_v2 import GraphPathPlannerV2


class PathPlannerService:
    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
        strategy: str = "shortest",
    ) -> LearningPath:
        return GraphPathPlannerV2.generate(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
            strategy=strategy,
        )

    @staticmethod
    def generate_all_strategies(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
    ) -> dict[str, LearningPath]:
        return {
            strategy: PathPlannerService.generate(
                profile=profile,
                target_job_id=target_job_id,
                candidate_skills=candidate_skills,
                strategy=strategy,
            )
            for strategy in ("shortest", "easy_first", "full_cover")
        }
