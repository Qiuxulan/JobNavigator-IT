from __future__ import annotations

from app.schemas.domain import RecommendationItem, UserPreference, UserProfile
from app.services.career_pathway_service import rank_careers


class RecommenderService:
    @staticmethod
    def recommend(profile: UserProfile, preference: UserPreference, top_k: int) -> list[RecommendationItem]:
        ranked = rank_careers(profile=profile, preference=preference, top_n=max(top_k, 10))
        return [row["recommendation"] for row in ranked[:top_k]]
