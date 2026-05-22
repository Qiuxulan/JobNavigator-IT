from app.schemas.domain import UserProfile


class ExtractorService:
    """Week-1 mock extractor; Week-2 will replace with finetuned model."""

    @staticmethod
    def extract(resume_text: str | None, github_url: str | None, user_id: str) -> UserProfile:
        text = resume_text or ""
        skills = []
        candidates = [
            "python",
            "sql",
            "pytorch",
            "langchain",
            "rag",
            "docker",
            "fastapi",
            "machine learning",
        ]
        lowered = text.lower()
        for c in candidates:
            if c in lowered:
                skills.append(c.upper() if c == "sql" else c.title())
        if not skills:
            skills = ["Python", "SQL"]
        return UserProfile(
            user_id=user_id,
            skills=sorted(set(skills)),
            target_role="RAG应用工程师",
            years_experience=1.0,
            education="本科",
            city="上海",
            github_url=github_url,
        )

