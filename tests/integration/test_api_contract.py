import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 推荐链路依赖离线流水线产物(岗位库 JSON + 已写入 pgvector 的岗位向量)。
# CI 不跑 build_job_vectors,缺这些产物时跳过依赖岗位库的用例,只做轻量冒烟。
_ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
_needs_roles = pytest.mark.skipif(
    not os.path.exists(_ROLES_JSON),
    reason=f"缺少岗位库 {_ROLES_JSON}(需先跑离线流水线 + build_job_vectors),跳过推荐用例",
)


def test_health():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@_needs_roles
def test_profile_extract_and_recommend():
    profile_resp = client.post(
        "/v1/profile/extract",
        json={"resume_text": "Python SQL LangChain", "github_url": "https://github.com/example", "user_id": "demo"},
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()["profile"]

    rec_resp = client.post("/v1/jobs/recommend", json={"profile": profile, "preference": {"preferred_city": "上海"}})
    assert rec_resp.status_code == 200
    assert len(rec_resp.json()["items"]) > 0


def test_paths_trends_and_reserved_chat():
    profile = client.post("/v1/profile/extract", json={"resume_text": "Python SQL", "user_id": "demo2"}).json()["profile"]
    path_resp = client.post(
        "/v1/paths/generate",
        json={"profile": profile, "target_job_id": "job_rag_001", "candidate_skills": ["RAG", "LangChain"]},
    )
    assert path_resp.status_code == 200

    trend_resp = client.get("/v1/trends/RAG应用工程师")
    assert trend_resp.status_code == 200

    chat_resp = client.post("/v1/chat/decision", json={"query": "给我职业建议", "profile": profile, "top_k": 3})
    assert chat_resp.status_code == 501
    assert "reserved" in chat_resp.json()["detail"].lower()

