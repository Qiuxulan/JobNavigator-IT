from __future__ import annotations

from dataclasses import dataclass

from pipelines.extract.model_extractor import safe_extract_model_skills
from pipelines.extract.rule_extractor import normalize_role

from app.schemas.domain import UserProfile
from app.services.skill_norm import match_skills_in_text, normalize_list


def _infer_target_role(text: str) -> str | None:
    normalized = normalize_role(text)
    if normalized:
        return normalized
    lowered = text.lower()
    if "rag" in lowered or "langchain" in lowered or "llm" in lowered:
        return "AI Engineer"
    if "spring" in lowered or "java" in lowered:
        return "Backend Engineer"
    if "tableau" in lowered or "pandas" in lowered:
        return "Data Engineer"
    return None


@dataclass
class ExtractorDiagnostics:
    rule_skills: list[str]
    model_skills: list[str]
    merged_skills: list[str]
    model_attempted: bool
    model_empty: bool


class ExtractorService:
    """Resume skill extraction with finetuned-model attempt plus rules fallback."""

    @staticmethod
    def diagnose(resume_text: str | None) -> ExtractorDiagnostics:
        text = (resume_text or "").strip()
        rule_skills = match_skills_in_text(text, max_skills=40)
        model_skills = safe_extract_model_skills(text)
        merged_skills = normalize_list([*rule_skills, *model_skills])
        return ExtractorDiagnostics(
            rule_skills=rule_skills,
            model_skills=model_skills,
            merged_skills=merged_skills,
            model_attempted=bool(text),
            model_empty=bool(text) and not bool(model_skills),
        )

    @staticmethod
    def extract(resume_text: str | None, github_url: str | None, user_id: str) -> UserProfile:
        text = (resume_text or "").strip()
        diagnostics = ExtractorService.diagnose(text)
        normalized_skills = diagnostics.merged_skills
        if not normalized_skills:
            normalized_skills = normalize_list(["Python", "SQL"])

        target_role = _infer_target_role(text)
        return UserProfile(
            user_id=user_id,
            skills=normalized_skills,
            target_role=target_role,
            years_experience=1.0,
            education="本科",
            city=None,
            github_url=github_url,
        )
