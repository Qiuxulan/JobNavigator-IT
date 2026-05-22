from app.schemas.domain import LearningPath, LearningPathStep, LearningResource, UserProfile


class PathPlannerService:
    @staticmethod
    def generate(profile: UserProfile, target_job_id: str, missing_skills: list[str]) -> LearningPath:
        steps: list[LearningPathStep] = []
        for idx, skill in enumerate(missing_skills[:6], start=1):
            steps.append(
                LearningPathStep(
                    step_no=idx,
                    skill=skill,
                    reason=f"补足 {skill} 能力以匹配目标岗位。",
                    resources=[
                        LearningResource(
                            resource_id=f"res_{skill}_{idx}",
                            title=f"{skill} 实战课程",
                            url=f"https://example.com/{skill}",
                            provider="coursera",
                            level="beginner" if idx <= 2 else "intermediate",
                        )
                    ],
                )
            )
        if not steps:
            steps.append(
                LearningPathStep(
                    step_no=1,
                    skill="项目实战",
                    reason="当前技能基本匹配，建议补项目深度。",
                    resources=[
                        LearningResource(
                            resource_id="res_project_1",
                            title="RAG系统项目实战",
                            url="https://example.com/rag-project",
                            provider="github",
                            level="intermediate",
                        )
                    ],
                )
            )
        return LearningPath(
            target_job_id=target_job_id,
            total_steps=len(steps),
            total_estimated_hours=len(steps) * 24,
            score=max(0.6, 1.0 - 0.08 * len(missing_skills)),
            steps=steps,
        )

