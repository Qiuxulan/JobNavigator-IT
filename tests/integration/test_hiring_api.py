"""招聘风向标 API 测试：临时 JSON 夹具 + monkeypatch 文件路径，走真实 HTTP 层。"""

import json

import pytest
from fastapi.testclient import TestClient

import app.api.hiring as hiring
from app.main import app

client = TestClient(app)


@pytest.fixture()
def fixture_paths(tmp_path, monkeypatch):
    momentum = tmp_path / "momentum.json"
    momentum.write_text(json.dumps({
        "generated_at": "2026-11-01T00:00:00+00:00",
        "window": ["2026-10-01", "2026-10-31"],
        "n_companies": 2,
        "by_sector": {
            "AI": {"companies": [
                {"domain": "a.com", "company": "alpha", "latest_open_roles": 500,
                 "momentum_7d": {"delta": 5.0, "pct": 0.01, "window_days": 7},
                 "momentum_30d": {"delta": 40.0, "pct": 0.08, "window_days": 30}},
                {"domain": "b.com", "company": "beta", "latest_open_roles": 300,
                 "momentum_30d": {"delta": 10.0, "pct": 0.03, "window_days": 30}},
            ]},
            "数据/云": {"companies": [
                {"domain": "c.com", "company": "gamma", "latest_open_roles": 900,
                 "momentum_30d": {"delta": 80.0, "pct": 0.10, "window_days": 30}},
            ]},
        },
    }), encoding="utf-8")
    layoff = tmp_path / "layoff.json"
    layoff.write_text(json.dumps({
        "generated_at": "2026-11-02T00:00:00+00:00",
        "window": ["2020-01-01", "2026-10-31"],
        "n_notices": 100,
        "monthly_table": {
            f"2026-{m:02d}": {"notices": m, "employees_affected": m * 100, "n_companies": 2}
            for m in range(1, 11)
        },
        "top_companies_by_employees": [
            {"month": "2026-09", "employer": "BigTech", "employees_affected": 3000},
            {"month": "2020-01", "employer": "OldCorp", "employees_affected": 9999},
        ],
    }), encoding="utf-8")
    hn = tmp_path / "hn.json"
    hn.write_text(json.dumps({
        "generated_at": "2026-11-03T00:00:00+00:00",
        "months": {
            "2026-10": {"n_job_posts": 229, "remote_ratio": 0.52, "salary_disclosed_ratio": 0.10},
            "2026-09": {"n_job_posts": 235, "remote_ratio": 0.51, "salary_disclosed_ratio": 0.11},
        },
        "skill_mentions_top30": [{"skill": "python", "count": 80}],
    }), encoding="utf-8")
    monkeypatch.setattr(hiring, "MOMENTUM_PATH", momentum)
    monkeypatch.setattr(hiring, "LAYOFF_PATH", layoff)
    monkeypatch.setattr(hiring, "HN_HIRING_PATH", hn)
    for cache in hiring._caches.values():
        cache["mtime"] = None
        cache["data"] = None
    return tmp_path


def test_overview_happy_path(fixture_paths):
    r = client.get("/v1/hiring/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["generated_at"] == "2026-11-03T00:00:00+00:00"

    cm = body["company_momentum"]
    assert cm["n_companies"] == 2
    # 按 30d delta 排序：gamma(80) > alpha(40) > beta(10)
    assert [c["company"] for c in cm["top"]] == ["gamma", "alpha", "beta"]
    assert cm["top"][0]["sector"] == "数据/云"
    assert set(cm["by_sector"]) == {"AI", "数据/云"}

    lo = body["layoffs"]
    assert lo["n_notices"] == 100
    assert lo["recent_months"][0]["month"] == "2026-01"
    assert len(lo["recent_months"]) == 10
    # 窗口外（2020-01）的雇主被过滤
    assert [e["employer"] for e in lo["top_recent_employers"]] == ["BigTech"]

    hn = body["hn_hiring"]
    assert [m["month"] for m in hn["months"]] == ["2026-09", "2026-10"]
    assert hn["months"][1]["remote_ratio"] == 0.52
    assert hn["skill_mentions_top30"][0]["skill"] == "python"


def test_overview_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(hiring, "MOMENTUM_PATH", tmp_path / "nope1.json")
    monkeypatch.setattr(hiring, "LAYOFF_PATH", tmp_path / "nope2.json")
    monkeypatch.setattr(hiring, "HN_HIRING_PATH", tmp_path / "nope3.json")
    for cache in hiring._caches.values():
        cache["mtime"] = None
        cache["data"] = None
    r = client.get("/v1/hiring/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["company_momentum"] is None
    assert body["layoffs"] is None
    assert body["hn_hiring"] is None
    assert body["generated_at"] is None
