from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.api import (
    ChatDecisionRequest,
    ChatDecisionResponse,
    PathGenerateRequest,
    PathGenerateResponse,
    ProfileExtractRequest,
    ProfileExtractResponse,
    RecommendRequest,
    RecommendResponse,
    TrendResponse,
)
from app.schemas.common import HealthResponse
from app.services.extractor import ExtractorService
from app.services.path_planner import PathPlannerService
from app.services.recommender import RecommenderService
from app.services.trend import TrendService

router = APIRouter(prefix="/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", env=settings.app_env, version="v1")


@router.post("/profile/extract", response_model=ProfileExtractResponse)
def profile_extract(req: ProfileExtractRequest) -> ProfileExtractResponse:
    profile = ExtractorService.extract(req.resume_text, req.github_url, req.user_id)
    return ProfileExtractResponse(profile=profile)


@router.post("/jobs/recommend", response_model=RecommendResponse)
def jobs_recommend(req: RecommendRequest) -> RecommendResponse:
    items = RecommenderService.recommend(req.profile, req.preference, req.top_k)
    return RecommendResponse(items=items)


@router.post("/paths/generate", response_model=PathGenerateResponse)
def paths_generate(req: PathGenerateRequest) -> PathGenerateResponse:
    path = PathPlannerService.generate(req.profile, req.target_job_id, req.candidate_skills)
    return PathGenerateResponse(path=path)


@router.get("/trends/{job_role}", response_model=TrendResponse)
def trends(job_role: str) -> TrendResponse:
    return TrendResponse(signal=TrendService.get_signal(job_role))


@router.post("/chat/decision", response_model=ChatDecisionResponse)
def chat_decision(req: ChatDecisionRequest) -> ChatDecisionResponse:
    raise HTTPException(
        status_code=501,
        detail="Agent orchestration is reserved for a later phase. Use /jobs/recommend + /paths/generate + /trends/{job_role}.",
    )
