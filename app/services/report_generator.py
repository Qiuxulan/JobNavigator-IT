from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.schemas.domain import CareerRankedResult, CoarseMatch, UserProfile


class ReportGenerationError(RuntimeError):
    pass


def _compact_ranked_result(row: CareerRankedResult) -> dict[str, Any]:
    return {
        "job_id": row.job.job_id,
        "title": row.job.title,
        "coarse_role": row.job.coarse_role,
        "final_score": row.final_score,
        "semantic_score": row.semantic_score,
        "score_breakdown": row.score_breakdown,
        "skill_gap": {
            "missing_skills": row.skill_gap.missing_skills[:12],
            "overlap_skills": row.skill_gap.overlap_skills[:12],
        },
        "path": {
            "target_job_id": row.path.target_job_id,
            "total_steps": row.path.total_steps,
            "total_estimated_hours": row.path.total_estimated_hours,
            "score": row.path.score,
            "steps": [
                {
                    "step_no": step.step_no,
                    "skill": step.skill,
                    "reason": step.reason,
                    "resources": [
                        {"title": resource.title, "provider": resource.provider, "level": resource.level}
                        for resource in step.resources[:2]
                    ],
                }
                for step in row.path.steps[:8]
            ],
        },
    }


def _compact_coarse_match(row: CoarseMatch) -> dict[str, Any]:
    return {
        "job_id": row.job.job_id,
        "title": row.job.title,
        "coarse_role": row.job.coarse_role,
        "semantic_score": row.semantic_score,
    }


def build_report_messages(
    profile: UserProfile,
    normalized_skill_ids: list[str],
    coarse_matches: list[CoarseMatch],
    ranked_results: list[CareerRankedResult],
    audience: str,
    language: str,
) -> list[dict[str, str]]:
    compact_payload = {
        "profile": {
            "user_id": profile.user_id,
            "skills": profile.skills,
            "normalized_skill_ids": normalized_skill_ids,
            "target_role": profile.target_role,
            "years_experience": profile.years_experience,
            "education": profile.education,
            "city": profile.city,
        },
        "coarse_matches": [_compact_coarse_match(row) for row in coarse_matches[:10]],
        "ranked_results": [_compact_ranked_result(row) for row in ranked_results[:5]],
    }
    system_prompt = (
        "You are a career strategy analyst. "
        "Write a grounded report only from the provided data. "
        "Do not invent jobs, skills, salaries, or learning resources. "
        "Explain tradeoffs clearly and structure the answer in Markdown. "
        "Do not just list fields; provide analysis, interpretation, and practical judgment."
    )
    user_prompt = (
        f"Please write the final report in {language} for a {audience} audience.\n"
        "The report must be written in Markdown and include these sections:\n"
        "1. Candidate profile summary\n"
        "2. Top10 coarse recall observations\n"
        "3. Final ranked career interpretation (focus on top 3)\n"
        "4. Skill-gap analysis for the #1 recommended role\n"
        "5. Learning-path recommendation for the #1 role\n"
        "6. Risks and caveats\n"
        "7. A practical next-two-weeks action plan\n\n"
        "Important writing requirements:\n"
        "- Do not merely list skills or scores. Every section must contain analysis.\n"
        "- For overlap analysis, explain whether the candidate's current skill set is strongly aligned, partially aligned, or weakly aligned, and why.\n"
        "- For coarse recall, explain what the semantic similarity suggests about likely role direction.\n"
        "- For the final ranking, explain why the top role outranks the others using both semantic score and graph/path factors.\n"
        "- For the skill-gap section, interpret the missing skills by importance, difficulty, and expected transition cost.\n"
        "- For the learning path, summarize the path logic instead of only repeating step names; point out which steps are foundational, which are role-critical, and which are optional extensions.\n"
        "- If the path contains suspicious, low-relevance, or noisy skills, explicitly call them out and explain why they may be artifacts of the current graph data.\n"
        "- Make the tone analytical and concrete, not template-like.\n"
        "- Use compact paragraphs plus bullet points where appropriate.\n\n"
        f"Structured data:\n{compact_payload}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_career_report(
    profile: UserProfile,
    normalized_skill_ids: list[str],
    coarse_matches: list[CoarseMatch],
    ranked_results: list[CareerRankedResult],
    audience: str = "candidate",
    language: str = "zh-CN",
) -> tuple[str, str]:
    if not settings.llm_api_key:
        raise ReportGenerationError("Missing JOBNAV_LLM_API_KEY for report generation.")
    if not settings.llm_model:
        raise ReportGenerationError("Missing JOBNAV_LLM_MODEL for report generation.")

    messages = build_report_messages(
        profile=profile,
        normalized_skill_ids=normalized_skill_ids,
        coarse_matches=coarse_matches,
        ranked_results=ranked_results,
        audience=audience,
        language=language,
    )
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.35,
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_sec) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except Exception as exc:
        raise ReportGenerationError(f"LLM request failed: {exc}") from exc

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise ReportGenerationError(f"Invalid LLM response payload: {exc}") from exc

    if not content:
        raise ReportGenerationError("LLM returned an empty report.")
    return content, settings.llm_model
