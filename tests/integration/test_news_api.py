"""新闻 API 集成测试：写入夹具行 → 走真实 HTTP 层断言 → 清理。

DB 不可用（连接失败 / 缺表）时整体 skip，不影响其他测试。
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)

FIXTURES = [
    {
        "news_id": "testnews_zh_fulltext_01",
        "title": "某科技公司宣布大规模招聘 AI 工程师",
        "url": "https://example.com/zh-hiring",
        "url_resolved": True,
        "source": "IT之家",
        "lang": "zh",
        "summary": "招聘详情摘要",
        "content_text": "这是一段用于测试的中文全文内容，包含 Python 与机器学习相关描述。",
        "category": "hiring",
        "skills": ["python"],
        "role_ids": [],
    },
    {
        "news_id": "testnews_en_ai_0002",
        "title": "OpenAI raises new funding for AI research",
        "url": "https://example.com/en-ai",
        "url_resolved": True,
        "source": "HackerNews",
        "lang": "en",
        "summary": "AI funding summary",
        "content_text": "English full text about artificial intelligence funding round.",
        "category": "funding",
        "skills": ["llm"],
        "role_ids": [],
    },
    {
        "news_id": "testnews_aged_layoff_03",
        "title": "Test layoff record older than 7 days",
        "url": "https://example.com/old-layoff",
        "url_resolved": False,
        "source": "layoffs.fyi",
        "lang": "en",
        "summary": "old layoff",
        "content_text": None,
        "category": "layoff",
        "skills": [],
        "role_ids": [],
        "published_offset_days": 30,
    },
]

_fixtures_default_offset = {"published_offset_days": 0}


def _db_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name='news_items'"
            )
            return cur.fetchone() is not None
    except Exception:
        return False


_needs_news_db = pytest.mark.skipif(
    not _db_available(), reason="news_items db unavailable"
)


@pytest.fixture(scope="module")
def news_fixtures():
    import psycopg

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for fx in FIXTURES:
            row = {**_fixtures_default_offset, **fx}
            cur.execute(
                """
                INSERT INTO news_items
                  (news_id, title, url, url_resolved, source, lang, published_at,
                   summary, content_text, category, skills, role_ids)
                VALUES (%(news_id)s, %(title)s, %(url)s, %(url_resolved)s,
                        %(source)s, %(lang)s,
                        NOW() - make_interval(days => %(published_offset_days)s),
                        %(summary)s, %(content_text)s,
                        %(category)s, %(skills)s, %(role_ids)s)
                ON CONFLICT (news_id) DO NOTHING
                """,
                row,
            )
        conn.commit()
    yield FIXTURES
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM news_items WHERE news_id LIKE 'testnews\\_%' "
            "ESCAPE '\\'"
        )
        conn.commit()


@_needs_news_db
def test_news_list_pagination(news_fixtures):
    resp = client.get("/v1/news", params={"page": 1, "page_size": 5})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 5
    assert len(payload["items"]) <= 5
    assert payload["total"] >= 3
    assert payload["freshness"]["sources_active"] >= 1
    item = payload["items"][0]
    for key in ("news_id", "title", "source", "lang", "category", "published_at"):
        assert key in item


@_needs_news_db
def test_news_list_page_size_capped(news_fixtures):
    resp = client.get("/v1/news", params={"page_size": 500})
    assert resp.status_code == 422  # page_size 上限 50


@_needs_news_db
def test_news_filter_category(news_fixtures):
    resp = client.get("/v1/news", params={"category": "hiring", "page_size": 50})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert all(it["category"] == "hiring" for it in payload["items"])
    assert any(it["lang"] == "zh" for it in payload["items"])


@_needs_news_db
def test_news_search_q(news_fixtures):
    resp = client.get("/v1/news", params={"q": "OpenAI", "page_size": 50})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert any("OpenAI" in it["title"] for it in payload["items"])


@_needs_news_db
def test_news_filter_lang_and_source(news_fixtures):
    resp = client.get(
        "/v1/news", params={"lang": "en", "source": "HackerNews", "page_size": 50}
    )
    assert resp.status_code == 200
    for it in resp.json()["items"]:
        assert it["lang"] == "en"
        assert it["source"] == "HackerNews"


@_needs_news_db
def test_news_categories(news_fixtures):
    resp = client.get("/v1/news/categories")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 7
    assert payload["categories"].get("hiring", 0) >= 1
    assert "funding" in payload["categories"]


@_needs_news_db
def test_news_sources(news_fixtures):
    resp = client.get("/v1/news/sources")
    assert resp.status_code == 200
    sources = {s["source"]: s for s in resp.json()["sources"]}
    assert "IT之家" in sources
    assert sources["IT之家"]["count"] >= 1
    assert sources["IT之家"]["latest_published_at"]
