"""公司雷达 API（/v1/companies）测试：临时 JSON 夹具 + monkeypatch 新闻 DB 层。

覆盖：列表排序与 status_tag 派生（裁员>30d 正增>cooling）、雇主名归一化匹配
（Meta Platforms 命中 meta，pineapple 不命中 apple）、详情 404、
日度序列透传、相关新闻为空时返回空数组。
"""

import json

import pytest
from fastapi.testclient import TestClient

import app.api.companies as companies
from app.main import app

client = TestClient(app)


def _momentum_payload() -> dict:
    return {
        "generated_at": "2026-11-01T00:00:00+00:00",
        "window": ["2026-10-04", "2026-11-02"],
        "n_companies": 3,
        "companies": {
            "meta.com": {
                "company": "meta", "domain": "meta.com", "sector": "AI",
                "latest": {"date": "2026-11-02", "open_roles": 500},
                "open_roles_avg_30d": 480.0,
                "momentum_7d": {"delta": 10.0, "pct": 0.02, "window_days": 7},
                "momentum_30d": {"delta": 50.0, "pct": 0.11, "window_days": 29},
                "daily": [
                    {"date": "2026-11-01", "open_roles": 490},
                    {"date": "2026-11-02", "open_roles": 500},
                ],
            },
            "apple.com": {
                "company": "apple", "domain": "apple.com", "sector": "硬件",
                "latest": {"date": "2026-11-02", "open_roles": 900},
                "momentum_30d": {"delta": -20.0, "pct": -0.02, "window_days": 29},
                "daily": [{"date": "2026-11-02", "open_roles": 900}],
            },
            "ok.com": {
                "company": "ok", "domain": "ok.com", "sector": "消费",
                "latest": {"date": "2026-11-02", "open_roles": 10},
                "momentum_30d": {"delta": 0.0, "pct": 0.0, "window_days": 29},
                "daily": [],
            },
        },
    }


def _layoff_payload() -> dict:
    return {
        "generated_at": "2026-11-02T00:00:00+00:00",
        "source": "WARN test",
        "records": [
            {"month": "2026-09", "employer": "Meta Platforms",
             "employees_affected": 100, "n_notices": 2, "states": ["CA"],
             "event_types": ["layoff"], "latest_effective_date": "2026-10-01"},
            {"month": "2026-08", "employer": "Pineapple Foods Inc",
             "employees_affected": 200, "n_notices": 1, "states": ["FL"],
             "event_types": ["closure"], "latest_effective_date": "nan"},
            {"month": "2025-01", "employer": "Meta Platforms",
             "employees_affected": 999, "n_notices": 9, "states": ["WA"],
             "event_types": ["layoff"], "latest_effective_date": "2025-03-01"},
        ],
    }


@pytest.fixture()
def fixture_paths(tmp_path, monkeypatch):
    momentum = tmp_path / "momentum.json"
    momentum.write_text(json.dumps(_momentum_payload()), encoding="utf-8")
    layoff = tmp_path / "layoff.json"
    layoff.write_text(json.dumps(_layoff_payload()), encoding="utf-8")
    monkeypatch.setattr(companies, "MOMENTUM_PATH", momentum)
    monkeypatch.setattr(companies, "LAYOFF_PATH", layoff)
    for cache in companies._caches.values():
        cache["mtime"] = None
        cache["data"] = None
    monkeypatch.setattr(companies, "_fetch_related_news", lambda name, limit=10: [
        {"title": f"{name} news", "url": "https://x/1", "source": "t",
         "published_at": "2026-11-01T00:00:00+00:00"},
    ])
    return tmp_path


def _reset_caches():
    for cache in companies._caches.values():
        cache["mtime"] = None
        cache["data"] = None


def test_list_companies(fixture_paths):
    r = client.get("/v1/companies")
    assert r.status_code == 200
    body = r.json()
    assert body["n_companies"] == 3
    # 按在招数排序：apple(900) > meta(500) > ok(10)
    items = body["companies"]
    assert [c["name"] for c in items] == ["apple", "meta", "ok"]

    meta = items[1]
    assert meta["domain"] == "meta.com"
    assert meta["sector"] == "AI"
    # 近 12 月窗口（锚点 2026-09 → cutoff 2025-10）：只统计 2026-09 那条
    assert meta["layoff_events_12m"] == {"notices": 2, "employees": 100}
    # 有近期裁员 → shrinking，即使 30d 在涨
    assert meta["status_tag"] == "shrinking"

    apple = items[0]
    assert apple["status_tag"] == "cooling"
    # pineapple 不算 apple 的裁员
    assert apple["layoff_events_12m"] == {"notices": 0, "employees": 0}

    assert items[2]["status_tag"] == "stable"


def test_list_companies_expanding_tag(fixture_paths, monkeypatch):
    payload = _momentum_payload()
    del payload["companies"]["meta.com"]
    monkeypatch.setattr(
        companies, "_fetch_related_news", lambda name, limit=10: [])
    path = companies.MOMENTUM_PATH
    path.write_text(json.dumps(payload), encoding="utf-8")
    _reset_caches()
    r = client.get("/v1/companies")
    # 无裁员 + 30d 正增 → expanding
    tags = {c["name"]: c["status_tag"] for c in r.json()["companies"]}
    assert tags == {"apple": "cooling", "ok": "stable"}


def test_list_companies_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(companies, "MOMENTUM_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(companies, "LAYOFF_PATH", tmp_path / "nope2.json")
    _reset_caches()
    r = client.get("/v1/companies")
    assert r.status_code == 200
    assert r.json() == {
        "generated_at": None, "window": None, "n_companies": 0, "companies": [],
    }


def test_company_detail(fixture_paths):
    r = client.get("/v1/companies/meta.com")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "meta"
    assert body["status_tag"] == "shrinking"
    assert body["latest_open_roles"] == 500
    assert body["momentum_30d"]["delta"] == 50.0
    assert body["open_roles_daily"] == [
        {"date": "2026-11-01", "count": 490},
        {"date": "2026-11-02", "count": 500},
    ]
    # WARN 全量记录：2025-01 的也算；pineapple 不命中
    assert [e["month"] for e in body["layoff_events"]] == ["2026-09", "2025-01"]
    assert body["layoff_events"][0]["states"] == ["CA"]
    assert len(body["related_news"]) == 1
    assert body["related_news"][0]["title"] == "meta news"


def test_company_detail_not_found(fixture_paths):
    r = client.get("/v1/companies/unknown.com")
    assert r.status_code == 404


def test_company_detail_no_news(fixture_paths, monkeypatch):
    monkeypatch.setattr(companies, "_fetch_related_news", lambda name, limit=10: [])
    r = client.get("/v1/companies/apple.com")
    assert r.status_code == 200
    assert r.json()["related_news"] == []
    assert r.json()["layoff_events"] == []
