from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.domain import LearningPath, RecommendationItem, TrendSignal, UserPreference, UserProfile


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

