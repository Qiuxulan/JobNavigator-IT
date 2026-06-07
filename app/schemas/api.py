from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.domain import (
    CareerRankedResult,
    CoarseMatch,
    LearningPath,
    RecommendationItem,
    TrendSignal,
    UserPreference,
    UserProfile,
)


class ProfileExtractRequest(BaseModel):
    resume_text: Optional[str] = None
    resume_file: Optional[str] = None
    github_url: Optional[str] = None
    user_id: str = "anonymous"


class ProfileExtractResponse(BaseModel):
    profile: UserProfile


class RecommendRequest(BaseModel):
    profile: UserProfile
    preference: UserPreference = Field(default_factory=UserPreference)
    top_k: int = 5


class RecommendResponse(BaseModel):
    items: list[RecommendationItem]


class PathGenerateRequest(BaseModel):
    profile: UserProfile
    target_job_id: str
    candidate_skills: list[str] = Field(default_factory=list)


class PathGenerateResponse(BaseModel):
    path: LearningPath


class CareerRankRequest(BaseModel):
    resume_text: str
    github_url: Optional[str] = None
    user_id: str = "anonymous"
    preference: UserPreference = Field(default_factory=UserPreference)
    top_k: int = 10


class CareerRankResponse(BaseModel):
    profile: UserProfile
    normalized_skill_ids: list[str] = Field(default_factory=list)
    coarse_matches: list[CoarseMatch] = Field(default_factory=list)
    ranked_results: list[CareerRankedResult] = Field(default_factory=list)


class CareerReportRequest(BaseModel):
    resume_text: str
    github_url: Optional[str] = None
    user_id: str = "anonymous"
    preference: UserPreference = Field(default_factory=UserPreference)
    top_k: int = 5
    audience: str = "candidate"
    language: str = "zh-CN"
    report_style: str = "markdown"


class CareerReportResponse(BaseModel):
    profile: UserProfile
    normalized_skill_ids: list[str] = Field(default_factory=list)
    coarse_matches: list[CoarseMatch] = Field(default_factory=list)
    ranked_results: list[CareerRankedResult] = Field(default_factory=list)
    report_markdown: str
    report_model: str


class TrendResponse(BaseModel):
    signal: TrendSignal


class ChatDecisionRequest(BaseModel):
    query: str
    profile: UserProfile
    top_k: int = 5


class ChatDecisionResponse(BaseModel):
    summary: str
    recommendations: list[RecommendationItem]
    path: Optional[LearningPath] = None
    trend: Optional[TrendSignal] = None

