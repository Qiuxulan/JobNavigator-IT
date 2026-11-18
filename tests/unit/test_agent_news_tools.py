"""Agent 实时新闻工具单元测试：search_news / get_market_pulse / get_latest_role_news / 新闻意图识别。

查询构造测试用 monkeypatch 替换 _news_connect（捕获 SQL 与参数，不触库）；
结构测试允许直连本地 news_items 真实库（若可用则跳过）。
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.services import agent as agent_mod


def _fake_row(title="T", source="S", published_at=None, category="tech_general",
              url="https://example.com/x", summary="摘要内容", lang="zh"):
    return (title, source, published_at or dt.datetime(2026, 10, 19, tzinfo=dt.timezone.utc),
            category, url, summary, lang)


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._conn.executed.append((sql, params))

    def fetchall(self):
        return self._conn.rows

    def fetchone(self):
        # MAX()/COUNT() 新鲜度查询不返回数据行
        sql = self._conn.executed[-1][0] if self._conn.executed else ""
        if any(k in sql for k in ("MAX(", "COUNT(")):
            return (None, 0) if "COUNT(" in sql else (None,)
        rows = self._conn.rows
        return rows[0] if rows else None


class _FakeConn:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _FakeCursor(self)


@pytest.fixture
def captured(monkeypatch):
    """Capture SQL/params sent through _news_connect without touching the DB."""
    conn = _FakeConn(rows=[_fake_row()])
    monkeypatch.setattr(agent_mod, "_news_connect", lambda: conn)
    return conn


# ── search_news 查询构造 ──────────────────────────────────────────────────────

def test_search_news_query_construction(captured):
    result = agent_mod._tool_search_news({
        "query": "AI 大模型", "days": 7, "category": "layoff", "lang": "zh", "limit": 8,
    })
    sql, params = captured.executed[0]
    # 时间窗过滤
    assert "published_at >= NOW() - (%s || ' days')::interval" in sql
    assert str(7) in [str(p) for p in params]
    # 中英文拆词后 OR 匹配 title/summary
    assert sql.count("title ILIKE %s OR summary ILIKE %s") == 2
    assert "%AI%" in params and "%大模型%" in params
    # category / lang 过滤
    assert "category = %s" in sql and "lang = %s" in sql
    assert "layoff" in params and "zh" in params
    # 时间倒序 + LIMIT
    assert "ORDER BY published_at DESC" in sql
    assert params[-1] == 8
    # 返回结构
    assert result["count"] == 1
    item = result["items"][0]
    assert set(item) >= {"title", "source", "published_at", "category", "url", "summary_snippet"}
    assert item["published_at"].startswith("2026-10-19")
    assert item["summary_snippet"] == "摘要内容"


def test_search_news_multi_term_uses_or(captured):
    agent_mod._tool_search_news({"query": "kubernetes docker sre", "days": 14, "limit": 5})
    sql, params = captured.executed[0]
    assert sql.count("title ILIKE %s OR summary ILIKE %s") == 3
    joined = " OR ".join(["(title ILIKE %s OR summary ILIKE %s)"] * 3)
    assert f"({joined})" in sql


def test_search_news_empty_result_reports_honestly(monkeypatch):
    monkeypatch.setattr(agent_mod, "_news_connect", lambda: _FakeConn(rows=[]))
    result = agent_mod._tool_search_news({"query": "量子计算就业", "days": 7})
    assert result["count"] == 0
    assert result["items"] == []
    assert "note" in result and "没有匹配" in result["note"]


def test_search_news_db_error_returns_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(agent_mod, "_news_connect", _boom)
    result = agent_mod._tool_search_news({"query": "ai"})
    assert "error" in result


# ── get_market_pulse 返回结构（真实库，不可用时跳过） ─────────────────────────

_real_pulse = pytest.mark.skipif(
    "error" in agent_mod._tool_get_market_pulse(),
    reason="news_items DB unavailable",
)


@_real_pulse
def test_market_pulse_structure():
    pulse = agent_mod._tool_get_market_pulse()
    assert pulse["window_days"] == 7
    assert isinstance(pulse["category_counts_last_7d"], dict)
    assert pulse["news_count_last_7d"] == sum(pulse["category_counts_last_7d"].values())
    assert isinstance(pulse["top_skills_last_7d"], list)
    for row in pulse["top_skills_last_7d"]:
        assert set(row) == {"skill", "mentions_last_7d", "mentions_prev_7d", "delta"}
    assert pulse["news_latest_published_at"] is not None
    for key in ("latest_layoff_events", "latest_funding_events"):
        assert isinstance(pulse[key], list)
        for ev in pulse[key][:1]:
            assert set(ev) >= {"title", "source", "published_at", "url", "summary_snippet"}


# ── get_latest_role_news ─────────────────────────────────────────────────────

def test_latest_role_news_matches_by_role_ids(captured, monkeypatch):
    monkeypatch.setattr(
        agent_mod, "_get_taxonomy",
        lambda: [{"role_id": "role_001", "canonical_role": "SRE Test Role", "top_skills": ["Linux"]}],
    )
    result = agent_mod._tool_get_latest_role_news({"role_name": "SRE Test Role", "days": 30, "limit": 6})
    sql, params = captured.executed[0]
    assert "role_ids @> ARRAY[%s]::text[]" in sql
    assert "role_001" in params
    assert result["matched_role_id"] == "role_001"
    assert result["count"] == 1


def test_latest_role_news_keyword_fallback_when_role_ids_empty(captured, monkeypatch):
    """role_ids 命中 0 条时应回退到岗位名 + top_skills 关键词匹配。"""
    conn_ids = _FakeConn(rows=[])          # role_ids 查询无结果
    conn_kw = _FakeConn(rows=[_fake_row(title="Karmada 毕业")])
    connections = iter([conn_ids, conn_kw])
    monkeypatch.setattr(agent_mod, "_news_connect", lambda: next(connections))
    monkeypatch.setattr(
        agent_mod, "_get_taxonomy",
        lambda: [{"role_id": "role_002", "canonical_role": "Kube Role", "top_skills": ["Kubernetes", "Docker"]}],
    )
    result = agent_mod._tool_get_latest_role_news({"role_name": "Kube Role", "days": 30, "limit": 6})
    assert result["matched_by"] == "keywords_fallback"
    assert result["count"] == 1
    assert result["items"][0]["title"] == "Karmada 毕业"
    kw_sql, kw_params = conn_kw.executed[0]
    assert "%Kubernetes%" in kw_params and "%Docker%" in kw_params


# ── 新闻意图识别 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "最近 AI 行业有什么新闻？",
    "最近有什么新动态",
    "这周发生了什么",
    "现在裁员情况怎么样？",
    "给我讲讲市场脉搏",
    "DevOps Engineer 未来怎么样，有什么最新动态？",
])
def test_news_intent_detected(msg):
    assert agent_mod._has_news_intent(msg)


@pytest.mark.parametrize("msg", [
    "AI Engineer 前景怎么样",
    "帮我规划学习路径",
    "对比 Backend 和 Frontend",
    "我会 Python 和 SQL，推荐岗位",
])
def test_non_news_intent_not_detected(msg):
    assert not agent_mod._has_news_intent(msg)


def test_controlled_news_answer_generic_search(monkeypatch):
    calls = {}

    def _fake_search(args):
        calls["search"] = args
        return {"query": args["query"], "days": 7, "count": 1, "items": [
            {"title": "某 AI 新闻", "source": "InfoQ中文", "published_at": "2026-10-19T10:00:00+00:00",
             "category": "tech_general", "url": "https://x", "summary_snippet": "snippet"},
        ]}

    monkeypatch.setattr(agent_mod, "_tool_search_news", _fake_search)
    out = agent_mod._controlled_news_answer("最近 AI 行业有什么新闻？", [])
    assert out is not None and "某 AI 新闻" in out
    assert "[InfoQ中文, 2026-10-19]" in out
    assert calls["search"]["query"] == "AI"


def test_controlled_news_answer_role_mixed(monkeypatch):
    monkeypatch.setattr(agent_mod, "_tool_get_latest_role_news", lambda a: {
        "role_name": a["role_name"], "days": 30, "count": 1, "items": [
            {"title": "DevOps 动态", "source": "Src", "published_at": "2026-10-18T09:00:00+00:00",
             "category": "tech_general", "url": "", "summary_snippet": "s"},
        ]})
    monkeypatch.setattr(agent_mod, "_tool_query_trend", lambda a: {
        "canonical_role": a["role"], "trend_direction": "up",
        "predicted_demand_index": 0.5, "confidence": 0.6, "main_factors": [],
    })
    out = agent_mod._controlled_news_answer(
        "DevOps Engineer 未来怎么样，有什么最新动态？", ["DevOps Engineer"])
    assert out is not None
    assert "统计趋势" in out and "最新动态" in out
    assert "[Src, 2026-10-18]" in out


def test_controlled_news_answer_layoff_uses_news_search(monkeypatch):
    calls = {}

    def _fake_search(args):
        calls["search"] = args
        return {"query": args["query"], "days": 14, "count": 2, "items": [
            {"title": "某公司裁员", "source": "layoffs.fyi", "published_at": "2026-10-19T08:00:00+00:00",
             "category": "layoff", "url": "https://y", "summary_snippet": "s"},
            {"title": "另一裁员", "source": "Src2", "published_at": "2026-10-18T08:00:00+00:00",
             "category": "layoff", "url": "https://z", "summary_snippet": "s"},
        ]}

    monkeypatch.setattr(agent_mod, "_tool_search_news", _fake_search)
    out = agent_mod._controlled_news_answer("现在裁员情况怎么样？", [])
    assert out is not None and "某公司裁员" in out
    assert calls["search"]["category"] == "layoff"


def test_controlled_news_answer_none_for_non_news():
    assert agent_mod._controlled_news_answer("AI Engineer 前景如何？", []) is None
