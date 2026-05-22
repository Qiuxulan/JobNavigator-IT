from app.schemas.domain import UserPreference
from app.services.extractor import ExtractorService
from app.services.path_planner import PathPlannerService
from app.services.recommender import RecommenderService


def test_extract_profile():
    profile = ExtractorService.extract("I use python and sql and rag", None, "u1")
    assert profile.user_id == "u1"
    assert "Python" in profile.skills


def test_recommendation():
    profile = ExtractorService.extract("python sql", None, "u2")
    recs = RecommenderService.recommend(profile, UserPreference(preferred_city="上海"), 5)
    assert len(recs) >= 1
    assert recs[0].final_score > 0


def test_path_generation():
    profile = ExtractorService.extract("python sql", None, "u3")
    path = PathPlannerService.generate(profile, "job_rag_001", ["LangChain", "RAG"])
    assert path.total_steps >= 1
    assert path.total_estimated_hours > 0

