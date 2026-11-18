"""实时新闻情报 API：news_items 只读查询。禁止在请求路径上抓站。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/v1", tags=["news"])

_DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


def _connect():
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="psycopg not installed")
    try:
        return psycopg.connect(_DSN)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"news db unavailable: {exc}")


def _row_to_item(row: Any) -> dict:
    return {
        "news_id": row[0],
        "title": row[1],
        "url": row[2],
        "url_resolved": row[3],
        "source": row[4],
        "lang": row[5],
        "published_at": row[6].isoformat() if row[6] else None,
        "summary": row[7],
        "content_text": row[8],
        "category": row[9],
        "skills": row[10] or [],
        "role_ids": row[11] or [],
    }


_ITEM_COLS = (
    "news_id, title, url, url_resolved, source, lang, published_at, "
    "summary, content_text, category, skills, role_ids"
)


@router.get("/news")
def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    category: str | None = None,
    source: str | None = None,
    lang: str | None = None,
    hours: float | None = Query(None, gt=0),
    q: str | None = None,
) -> dict:
    """分页新闻列表：过滤 category/source/lang/hours，搜索 q（title ILIKE）。"""
    where, params = ["TRUE"], []
    if category:
        where.append("category = %s")
        params.append(category)
    if source:
        where.append("source = %s")
        params.append(source)
    if lang:
        where.append("lang = %s")
        params.append(lang)
    if hours:
        where.append("published_at >= NOW() - (%s || ' hours')::interval")
        params.append(str(hours))
    if q:
        where.append("title ILIKE %s")
        params.append(f"%{q}%")
    cond = " AND ".join(where)

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM news_items WHERE {cond}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT {_ITEM_COLS} FROM news_items WHERE {cond} "
                "ORDER BY published_at DESC NULLS LAST "
                "LIMIT %s OFFSET %s",
                [*params, page_size, (page - 1) * page_size],
            )
            items = [_row_to_item(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT MAX(published_at), COUNT(DISTINCT source) FROM news_items"
            )
            latest, sources_active = cur.fetchone()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "freshness": {
            "latest_published_at": latest.isoformat() if latest else None,
            "sources_active": sources_active or 0,
        },
    }


@router.get("/news/categories")
def news_categories() -> dict:
    """各类别近 7 天计数。"""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, COUNT(*) FROM news_items "
                "WHERE published_at >= NOW() - INTERVAL '7 days' "
                "GROUP BY category ORDER BY COUNT(*) DESC"
            )
            counts = {cat: n for cat, n in cur.fetchall()}
    return {"days": 7, "categories": counts}


@router.get("/news/sources")
def news_sources() -> dict:
    """源清单与各自最新条目时间。"""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source, COUNT(*), MAX(published_at) FROM news_items "
                "GROUP BY source ORDER BY MAX(published_at) DESC NULLS LAST"
            )
            sources = [
                {
                    "source": s,
                    "count": n,
                    "latest_published_at": latest.isoformat() if latest else None,
                }
                for s, n, latest in cur.fetchall()
            ]
    return {"sources": sources}
