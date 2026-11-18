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


class SkillTransferableItem(BaseModel):
    known_skill: str
    target_skill: str
    category: Optional[str] = None


class SkillGap(BaseModel):
    missing_skills: list[str] = Field(default_factory=list)
    overlap_skills: list[str] = Field(default_factory=list)
    # B 模块精排产出:加分技能(命中可加分,但不计入缺口,仅用于展示/解释)
    optional_skills: list[str] = Field(default_factory=list)
    # v3:已知技能 -> 可迁移目标技能(同 category 且 level 相近)
    transferable: Optional[list[SkillTransferableItem]] = None


class RecommendationItem(BaseModel):
    job: JobRole
    final_score: float
    semantic_score: float
    constraint_score: float
    path_cost_score: float
    trend_reward_score: float
    explanation: str
    skill_gap: SkillGap
    # matching v5(2026-11-06):分数校准后的置信度标签(high/medium/low),
    # 可选字段,旧前端不受影响。
    confidence: Optional[str] = None


class LearningResource(BaseModel):
    resource_id: str
    title: str
    url: str
    provider: str
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    # v3 资源库扩展字段(可选,兼容旧序列化)
    difficulty: Optional[str] = None
    hours_estimate: Optional[float] = None
    language: Optional[str] = None
    quality_score: Optional[float] = None
    source: Optional[str] = None


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
    # v2 资产溯源字段（可选，旧数据缺失时为 None）
    model_used: Optional[str] = None
    backtest_smape: Optional[float] = None
    direction_accuracy: Optional[float] = None
    sparse: Optional[bool] = None


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


class RolePathAnalysis(BaseModel):
    role: dict[str, Any]
    semantic_score: float
    role_score: float
    score_breakdown: dict[str, float]
    skill_gap: SkillGap
    path: LearningPath
    formula_version: str = "v3"
