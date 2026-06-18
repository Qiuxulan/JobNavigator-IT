from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class UserPreference(BaseModel):
    preferred_city: Optional[str] = None
    expected_salary_k: Optional[int] = None
    degree_floor: Optional[str] = None


class UserProfile(BaseModel):
    user_id: str
    skills: list[str] = Field(default_factory=list)
    target_role: Optional[str] = None
    years_experience: float = 0.0
    education: Optional[str] = None
    city: Optional[str] = None
    github_url: Optional[str] = None


class JobRole(BaseModel):
    job_id: str
    title: str
    fine_role: str
    coarse_role: str
    city: Optional[str] = None
    salary_min_k: Optional[int] = None
    salary_max_k: Optional[int] = None
    required_skills: list[str] = Field(default_factory=list)


class SkillGap(BaseModel):
    missing_skills: list[str] = Field(default_factory=list)
    overlap_skills: list[str] = Field(default_factory=list)
    # B 模块精排产出:加分技能(命中可加分,但不计入缺口,仅用于展示/解释)
    optional_skills: list[str] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    job: JobRole
    final_score: float
    semantic_score: float
    constraint_score: float
    path_cost_score: float
    trend_reward_score: float
    explanation: str
    skill_gap: SkillGap


class LearningResource(BaseModel):
    resource_id: str
    title: str
    url: str
    provider: str
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"


class LearningPathStep(BaseModel):
    step_no: int
    skill: str
    reason: str
    resources: list[LearningResource] = Field(default_factory=list)


class LearningPath(BaseModel):
    target_job_id: str
    total_steps: int
    total_estimated_hours: int
    score: float
    steps: list[LearningPathStep]


class TrendEvidence(BaseModel):
    event_id: str
    source: str
    title: str
    event_date: date
    summary: str
    impact: Literal["positive", "neutral", "negative"] = "neutral"
    url: Optional[str] = None


class TrendSignal(BaseModel):
    canonical_role: str
    role_name_zh: Optional[str] = None
    horizon_months: int = 3
    trend_direction: Literal["up", "flat", "down"] = "flat"
    predicted_demand_index: float = 0.5
    confidence: float = 0.0
    main_factors: list[str] = Field(default_factory=list)
    evidence: list[TrendEvidence] = Field(default_factory=list)
    monthly_forecast: list[dict[str, Any]] = Field(default_factory=list)


class CoarseMatch(BaseModel):
    job: JobRole
    semantic_score: float


class CareerRankedResult(BaseModel):
    job: JobRole
    final_score: float
    semantic_score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    skill_gap: SkillGap
    path: LearningPath
