"""趋势证据动态窗口测试：分片最新月滚动、跨年、目录缺失兜底。"""

import app.services.trend as trend


def _reset_cache():
    trend._evidence_window_cache.clear()


def test_window_rolls_with_latest_shard(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        "app.services.evidence_service_v2.latest_shard_month", lambda: "2026-11"
    )
    assert trend._evidence_window() == ("2026-09", "2026-11")


def test_window_crosses_year_boundary(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        "app.services.evidence_service_v2.latest_shard_month", lambda: "2027-01"
    )
    assert trend._evidence_window() == ("2026-11", "2027-01")


def test_window_fallback_when_shards_missing(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        "app.services.evidence_service_v2.latest_shard_month", lambda: None
    )
    assert trend._evidence_window() == trend.EVIDENCE_WINDOW


def test_window_cached_within_same_month(monkeypatch):
    _reset_cache()
    calls = []

    def fake_latest():
        calls.append(1)
        return "2026-11"

    monkeypatch.setattr(
        "app.services.evidence_service_v2.latest_shard_month", fake_latest
    )
    trend._evidence_window()
    trend._evidence_window()
    assert len(calls) == 1
