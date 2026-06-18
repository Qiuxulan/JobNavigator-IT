from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
from app.services.evidence import EvidenceService
from app.services.role_i18n import role_zh
from app.services.skill_norm import normalize_skill_id
from app.services.trend import (
    TrendNotFoundError,
    TrendService,
    TrendServiceError,
    _resolve_role,
)

router = APIRouter(prefix="/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", env=settings.app_env, version="v1")


@router.get("/roles")
def roles() -> dict:
    """Return available role taxonomy grouped by category."""
    from app.services.agent import _get_taxonomy

    by_category: dict[str, list[str]] = {}
    for role in _get_taxonomy():
        name = role["canonical_role"]
        by_category.setdefault(role.get("category", "Other"), []).append(name)
    return {"roles": by_category}


@router.get("/roles/catalog")
def roles_catalog() -> dict:
    """Return fine-grained roles with ids needed by recommendation/path APIs."""
    import json
    from pathlib import Path

    def clean_strings(values: list | None) -> list[str]:
        return [str(value) for value in (values or []) if value]

    roles_path = Path("data/gold/fine_grained_roles_v1.json")
    roles_data = json.loads(roles_path.read_text(encoding="utf-8"))
    return {
        "roles": [
            {
                "role_id": role.get("role_id"),
                "role_name": role.get("fine_role") or role.get("role_name"),
                "role_name_zh": role_zh(role.get("fine_role") or role.get("role_name")),
                "coarse_role": role.get("coarse_role", "Other"),
                "size": role.get("size"),
                "required_skill_ids": clean_strings(role.get("required_skill_ids")),
                "core_skill_ids": clean_strings(role.get("core_skill_ids")),
                "required_skills": clean_strings(role.get("required_skills")),
                "core_skills": clean_strings(role.get("core_skills")),
            }
            for role in roles_data
        ]
    }


@router.get("/graph")
def graph() -> dict:
    """Return delivered role-skill and event evidence graph for visualization."""
    import json
    from pathlib import Path

    roles_path = Path("data/gold/fine_grained_roles_v1.json")
    skill_graph_path = Path("data/gold/skill_prerequisite_v2.json")
    events_path = Path("data/gold/major_industry_events_v1.json")

    roles_data = json.loads(roles_path.read_text(encoding="utf-8"))
    skill_payload = json.loads(skill_graph_path.read_text(encoding="utf-8"))
    event_payload = json.loads(events_path.read_text(encoding="utf-8"))

    skill_rows = skill_payload.get("skills", [])
    skill_by_id = {s.get("skill_id"): s for s in skill_rows}
    event_catalog = {e.get("event_id"): e for e in event_payload.get("event_catalog", [])}

    nodes: list[dict] = []
    links: list[dict] = []
    seen_nodes: set[str] = set()
    seen_links: set[tuple[str, str, str]] = set()

    def add_node(node: dict) -> None:
        node_id = node["id"]
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append(node)

    def add_link(source: str, target: str, relation: str, **extra) -> None:
        key = (source, target, relation)
        if key not in seen_links:
            seen_links.add(key)
            links.append({"source": source, "target": target, "relation": relation, **extra})

    for skill in skill_rows:
        skill_id = skill["skill_id"]
        add_node({
            "id": f"skill:{skill_id}",
            "label": skill.get("skill_name", skill_id),
            "kind": "skill",
            "category": skill.get("category", "skill"),
            "hot": bool(skill.get("hot", False)),
            "level": skill.get("level"),
            "difficulty": skill.get("difficulty"),
            "hours_estimate": skill.get("hours_estimate"),
        })
        for prereq_id in skill.get("prerequisites", []):
            if prereq_id in skill_by_id:
                add_link(f"skill:{prereq_id}", f"skill:{skill_id}", "PREREQ")

    for role in roles_data:
        role_name = role.get("fine_role") or role.get("role_name")
        role_id = f"role:{role.get('role_id', role_name)}"
        add_node({
            "id": role_id,
            "label": role_name,
            "label_zh": role_zh(role_name),
            "kind": "role",
            "category": role.get("coarse_role", "Other"),
            "size": role.get("size"),
            "role_id": role.get("role_id"),
            "source_mix": role.get("source_mix", {}),
        })
        for rank, skill_id in enumerate((role.get("required_skill_ids") or [])[:15], start=1):
            if skill_id in skill_by_id:
                add_link(role_id, f"skill:{skill_id}", "REQUIRES", rank=rank)
        for skill_id in role.get("core_skill_ids") or []:
            if skill_id in skill_by_id:
                add_link(role_id, f"skill:{skill_id}", "CORE_SKILL")

    role_name_to_id = {
        (role.get("fine_role") or role.get("role_name")): f"role:{role.get('role_id', role.get('fine_role') or role.get('role_name'))}"
        for role in roles_data
    }
    for rel in event_payload.get("role_trend_evidence", []):
        role_id = role_name_to_id.get(rel.get("canonical_role"))
        if not role_id:
            continue
        for event_id in rel.get("major_event_ids", []):
            event = event_catalog.get(event_id)
            if not event:
                continue
            node_id = f"event:{event_id}"
            add_node({
                "id": node_id,
                "label": event.get("title", event_id),
                "kind": "event",
                "category": event.get("event_type", "event"),
                "event_date": event.get("event_date"),
                "impact_direction": event.get("impact_direction"),
                "source_name": event.get("source_name"),
                "source_url": event.get("source_url"),
                "importance": event.get("event_importance"),
                "summary_zh": event.get("summary_zh"),
            })
            add_link(node_id, role_id, "AFFECTS", trend_direction=rel.get("trend_direction"))

    summary = {
        "roles": sum(1 for n in nodes if n["kind"] == "role"),
        "skills": sum(1 for n in nodes if n["kind"] == "skill"),
        "events": sum(1 for n in nodes if n["kind"] == "event"),
        "links": len(links),
    }
    return {"nodes": nodes, "links": links, "summary": summary}


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


@router.get("/trends/batch")
def trends_batch(horizon_months: int = 3) -> dict:
    """Return trend predictions for all roles in a single call."""
    from app.services.trend_predictor import _load_predictions

    all_roles = sorted(set(r["canonical_role"] for r in _load_predictions()))
    results = []
    for role_name in all_roles:
        try:
            signal = TrendService.get_signal(role_name, horizon_months=horizon_months)
            results.append({
                "canonical_role": signal.canonical_role,
                "role_name_zh": signal.role_name_zh,
                "trend_direction": signal.trend_direction,
                "predicted_demand_index": signal.predicted_demand_index,
                "confidence": signal.confidence,
            })
        except Exception:
            pass
    return {"signals": results, "horizon_months": horizon_months}


@router.get("/trends/{job_role}", response_model=TrendResponse)
def trends(job_role: str, horizon_months: int = 3) -> TrendResponse:
    try:
        signal = TrendService.get_signal(job_role, horizon_months=horizon_months)
    except TrendNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrendServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TrendResponse(signal=signal)


@router.get("/evidence/{job_role}")
def evidence(
    job_role: str,
    start_month: str = "2026-01",
    end_month: str = "2026-06",
    top_k: int = 5,
    direction: str | None = None,
) -> dict:
    """证据检索：给岗位(+月份区间+方向)，返回 aggregate + 干净事件 + JD 证据。

    direction 可选（up/flat/down）；给了就做方向归因排序。
    """
    try:
        resolved = _resolve_role(job_role)
    except TrendNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvidenceService.retrieve_evidence(
        resolved.canonical_role, (start_month, end_month), top_k, direction
    )


@router.get("/cot/{job_role}")
def cot_context(job_role: str, horizon: int = 3) -> dict:
    """Return grounded evidence-chain context used by Agent CoT summaries."""
    from app.services.trend_explanation import assemble_cot_context, build_cot_prompt

    try:
        ctx = assemble_cot_context(job_role, horizon)
    except TrendNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "context": ctx,
        "cot_prompt": build_cot_prompt(ctx),
    }


@router.post("/chat/decision", response_model=ChatDecisionResponse)
def chat_decision(req: ChatDecisionRequest) -> ChatDecisionResponse:
    from app.services.agent import chat as agent_chat

    messages = [{"role": "user", "content": req.query}]
    answer = agent_chat(messages)
    return ChatDecisionResponse(
        summary=answer,
        recommendations=[],
    )


class AgentChatRequest(BaseModel):
    messages: list[dict]


class AgentChatResponse(BaseModel):
    reply: str


@router.post("/agent/chat", response_model=AgentChatResponse)
def agent_chat_endpoint(req: AgentChatRequest) -> AgentChatResponse:
    from app.services.agent import chat as agent_chat

    reply = agent_chat(req.messages, max_rounds=4)
    return AgentChatResponse(reply=reply)
