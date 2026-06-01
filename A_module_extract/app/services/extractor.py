import os

from app.schemas.domain import UserProfile
from pipelines.extract.rule_extractor import parse_resume, to_app_user_profile


DEFAULT_RESUME_TEXT = """
技能：Python、SQL。
学历：本科
工作年限：0年
目标岗位：数据分析师
"""


class ExtractorService:
    """Rule-based A-module extractor used by the V1 API."""

    @staticmethod
    def extract(resume_text: str | None, github_url: str | None, user_id: str) -> UserProfile:
        use_model = os.getenv("JNIT_ENABLE_JOBBERT", "").strip().lower() in {"1", "true", "yes", "on"}
        profile = parse_resume(
            resume_text or DEFAULT_RESUME_TEXT,
            user_id=user_id,
            github_url=github_url,
            use_model=use_model,
        )
        return UserProfile(**to_app_user_profile(profile))
