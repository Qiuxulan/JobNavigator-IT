from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.api import (
    CareerReportRequest,
    CareerReportResponse,
    CareerRankRequest,
    CareerRankResponse,
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
from app.schemas.domain import CareerRankedResult, CoarseMatch
from app.services.career_pathway_service import RecallSetupError, coarse_recall, rank_careers
from app.services.extractor import ExtractorService
from app.services.path_planner import PathPlannerService
from app.services.recommender import RecommenderService
from app.services.report_generator import ReportGenerationError, generate_career_report
from app.services.skill_norm import normalize_skill_id
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
    try:
        items = RecommenderService.recommend(req.profile, req.preference, req.top_k)
    except RecallSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RecommendResponse(items=items)


@router.post("/careers/rank", response_model=CareerRankResponse)
def careers_rank(req: CareerRankRequest) -> CareerRankResponse:
    profile = ExtractorService.extract(req.resume_text, req.github_url, req.user_id)
    try:
        coarse = coarse_recall(profile, top_n=max(10, req.top_k))
        ranked = rank_careers(profile, req.preference, top_n=max(10, req.top_k))
    except RecallSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CareerRankResponse(
        profile=profile,
        normalized_skill_ids=[
            skill_id
            for skill_id in (normalize_skill_id(skill) for skill in profile.skills)
            if skill_id
        ],
        coarse_matches=[
            {"job": row["job"], "semantic_score": row["semantic_score"]}
            for row in coarse
        ],
        ranked_results=[
            {
                "job": row["job"],
                "final_score": row["role_score"],
                "semantic_score": row["semantic_score"],
                "score_breakdown": row["score_breakdown"],
                "skill_gap": row["skill_gap"],
                "path": row["path"],
            }
            for row in ranked[: req.top_k]
        ],
    )


@router.post("/careers/report", response_model=CareerReportResponse)
def careers_report(req: CareerReportRequest) -> CareerReportResponse:
    profile = ExtractorService.extract(req.resume_text, req.github_url, req.user_id)
    normalized_skill_ids = [
        skill_id
        for skill_id in (normalize_skill_id(skill) for skill in profile.skills)
        if skill_id
    ]
    try:
        coarse = coarse_recall(profile, top_n=max(10, req.top_k))
        ranked = rank_careers(profile, req.preference, top_n=max(10, req.top_k))
        coarse_matches = [
            CoarseMatch(job=row["job"], semantic_score=row["semantic_score"])
            for row in coarse
        ]
        ranked_results = [
            CareerRankedResult(
                job=row["job"],
                final_score=row["role_score"],
                semantic_score=row["semantic_score"],
                score_breakdown=row["score_breakdown"],
                skill_gap=row["skill_gap"],
                path=row["path"],
            )
            for row in ranked[: req.top_k]
        ]
        report_markdown, report_model = generate_career_report(
            profile=profile,
            normalized_skill_ids=normalized_skill_ids,
            coarse_matches=coarse_matches,
            ranked_results=ranked_results,
            audience=req.audience,
            language=req.language,
        )
    except RecallSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ReportGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CareerReportResponse(
        profile=profile,
        normalized_skill_ids=normalized_skill_ids,
        coarse_matches=coarse_matches,
        ranked_results=ranked_results,
        report_markdown=report_markdown,
        report_model=report_model,
    )


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
