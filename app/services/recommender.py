from app.schemas.domain import JobRole, RecommendationItem, SkillGap, UserPreference, UserProfile


MOCK_JOBS = [
    JobRole(
        job_id="job_rag_001",
        title="RAG应用工程师",
        fine_role="RAG应用工程师",
        coarse_role="AI工程师",
        city="上海",
        salary_min_k=25,
        salary_max_k=45,
        required_skills=["Python", "LangChain", "RAG", "向量数据库"],
    ),
    JobRole(
        job_id="job_agent_001",
        title="Agent应用工程师",
        fine_role="Agent应用工程师",
        coarse_role="AI工程师",
        city="北京",
        salary_min_k=28,
        salary_max_k=50,
        required_skills=["Python", "LangGraph", "Prompt Engineering", "工具调用"],
    ),
    JobRole(
        job_id="job_data_001",
        title="数据工程师",
        fine_role="数据工程师",
        coarse_role="数据方向",
        city="上海",
        salary_min_k=20,
        salary_max_k=35,
        required_skills=["Python", "SQL", "Spark", "Airflow"],
    ),
]


class RecommenderService:
    """Week-1 mock two-stage recommendation service."""

    @staticmethod
    def recommend(profile: UserProfile, preference: UserPreference, top_k: int) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        for job in MOCK_JOBS:
            overlap = sorted(set(profile.skills) & set(job.required_skills))
            missing = sorted(set(job.required_skills) - set(profile.skills))
            semantic_score = min(1.0, len(overlap) / max(1, len(job.required_skills)))
            constraint_score = 1.0 if not preference.preferred_city or preference.preferred_city == job.city else 0.8
            path_cost_score = max(0.3, 1.0 - 0.12 * len(missing))
            trend_reward_score = 0.9 if "AI" in job.coarse_role else 0.7
            final = round(
                0.5 * semantic_score + 0.2 * constraint_score + 0.15 * path_cost_score + 0.15 * trend_reward_score, 4
            )
            items.append(
                RecommendationItem(
                    job=job,
                    final_score=final,
                    semantic_score=semantic_score,
                    constraint_score=constraint_score,
                    path_cost_score=path_cost_score,
                    trend_reward_score=trend_reward_score,
                    explanation=f"{job.title} 与你的技能重合 {len(overlap)} 项，缺口 {len(missing)} 项。",
                    skill_gap=SkillGap(missing_skills=missing, overlap_skills=overlap),
                )
            )
        items.sort(key=lambda x: x.final_score, reverse=True)
        return items[:top_k]

