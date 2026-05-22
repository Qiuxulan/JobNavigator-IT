from datetime import date
from typing import Literal, Optional

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


class TrendSignal(BaseModel):
    job_role: str
    horizon_months: int = 12
    short_term: Literal["up", "flat", "down"] = "flat"
    long_term: Literal["up", "flat", "down"] = "up"
    confidence: float = 0.7
    evidence: list[TrendEvidence] = Field(default_factory=list)

