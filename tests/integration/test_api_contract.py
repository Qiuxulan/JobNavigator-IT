from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


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

