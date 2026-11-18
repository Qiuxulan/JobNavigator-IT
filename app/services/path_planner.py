from __future__ import annotations

import os

from app.schemas.domain import LearningPath, UserProfile
from app.services.graph_path_planner_v3 import GraphPathPlannerV3


def _use_v4_planner() -> bool:
    """灰度开关:JOBNAV_PATH_PLANNER=v4 走 PathPlannerV4,默认仍 v3(确认稳定后再翻默认值)。"""
    return os.environ.get("JOBNAV_PATH_PLANNER", "v3").strip().lower() == "v4"


class PathPlannerService:
    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
        strategy: str = "shortest",
    ) -> LearningPath:
        # v3：先修闭包 + Kahn 拓扑排序，strategy 为 v2 死代码，不再传入。
        if _use_v4_planner():
            from app.services.path_planner_v4 import PathPlannerV4

            return PathPlannerV4.generate(
                profile=profile,
                target_job_id=target_job_id,
                candidate_skills=candidate_skills,
            )
        return GraphPathPlannerV3.generate(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
        )

    @staticmethod
    def generate_all_strategies(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
    ) -> dict[str, LearningPath]:
        # v3 只有一条拓扑最优路径，三种 strategy 返回同一路径（保持接口兼容）。
        path = PathPlannerService.generate(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
        )
        return {
            strategy: path
            for strategy in ("shortest", "easy_first", "full_cover")
        }
