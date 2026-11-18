import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_PROFILES_JSON = "data/gold/role_profiles_v3.json"
_needs_profiles = pytest.mark.skipif(
    not os.path.exists(_PROFILES_JSON),
    reason=f"missing role profiles json: {_PROFILES_JSON}",
)


@_needs_profiles
def test_roles_overview():
    resp = client.get("/v1/roles/overview")
    assert resp.status_code == 200
    payload = resp.json()
    dataset = payload["dataset"]
    assert dataset["total_jd"] > 0
    assert dataset["assigned_jd"] > 0
    assert dataset["data_through"]
    assert len(payload["roles"]) == dataset["role_count"] > 0

    row = payload["roles"][0]
    assert row["role_id"]
    assert row["role_name"]
    assert row["salary"]["median"] is not None
    assert len(row["jd_share_3m"]) <= 3
    assert len(row["monthly_jd_tail"]) <= 6


@_needs_profiles
def test_role_insights_by_id():
    with open(_PROFILES_JSON, encoding="utf-8") as f:
        first_role = json.load(f)["roles"][0]["role_id"]
    resp = client.get(f"/v1/roles/{first_role}/insights")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["role_id"] == first_role
    assert payload["role_name"]
    assert payload["jd_count"] > 0
    salary = payload["salary"]
    assert salary["p25"] <= salary["median"] <= salary["p75"]
    assert salary["sample_size"] > 0
    assert len(payload["top_skills"]) > 0
    assert payload["top_skills"][0]["freq"] >= payload["top_skills"][-1]["freq"]
    assert len(payload["monthly_jd_counts"]) <= 24
    assert payload["remote_ratio"] is not None
    assert payload["seniority_distribution"]
    assert "model_used" in payload["model"]
    assert "confidence" in payload["model"]


@_needs_profiles
def test_role_insights_resolves_by_name():
    with open(_PROFILES_JSON, encoding="utf-8") as f:
        first_name = json.load(f)["roles"][0]["role_name"]
    resp = client.get(f"/v1/roles/{first_name}/insights")
    assert resp.status_code == 200
    assert resp.json()["role_name"] == first_name


def test_role_insights_not_found():
    resp = client.get("/v1/roles/role_does_not_exist/insights")
    assert resp.status_code == 404
