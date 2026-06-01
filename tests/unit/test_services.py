import os

import pytest

from app.schemas.domain import UserPreference
from app.services.extractor import ExtractorService
from app.services.path_planner import PathPlannerService
from app.services.recommender import RecommenderService

# 推荐链路依赖离线流水线产物(岗位库 JSON + 已写入 pgvector 的岗位向量)。
# CI 不跑 build_job_vectors,缺这些产物时跳过依赖岗位库的用例,只做轻量冒烟。
_ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
_needs_roles = pytest.mark.skipif(
    not os.path.exists(_ROLES_JSON),
    reason=f"缺少岗位库 {_ROLES_JSON}(需先跑离线流水线 + build_job_vectors),跳过推荐用例",
)


def test_extract_profile():
    profile = ExtractorService.extract("I use python and sql and rag", None, "u1")
    assert profile.user_id == "u1"
    assert "Python" in profile.skills


@_needs_roles
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

