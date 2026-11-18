"""用户个人数据 API（小程序「我的」页面）：profile / favorites / history。

无登录体系：客户端首次启动生成 UUID 存本地，之后每个请求带 header
`X-Client-Id: <uuid>`（8~64 字符，仅字母数字和 -_）。所有数据按 client_id 隔离，
新 client_id 首次写操作时自动在 user_profiles 建行。
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/me", tags=["me"])

_DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)

_MAX_PAYLOAD_BYTES = 32 * 1024

# favorites 与 history 的合法 item_type 集合不同，分开校验
_FAVORITE_TYPES = {"job", "news", "path"}
_HISTORY_TYPES = {"news", "trend", "match"}

ClientId = Annotated[
    str,
    Header(alias="X-Client-Id", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
]


class ProfileIn(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=32)


class ItemIn(BaseModel):
    item_type: str
    item_id: str = Field(..., min_length=1)
    title: str = ""
    payload: dict = Field(default_factory=dict)


def _connect():
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="psycopg not installed")
    try:
        return psycopg.connect(_DSN)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"user db unavailable: {exc}")


def _check_item_type(item_type: str, allowed: set[str]) -> None:
    if item_type not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"invalid item_type: {item_type!r}, allowed: {sorted(allowed)}",
        )


def _check_payload_size(payload: Any) -> None:
    try:
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="payload is not JSON serializable")
    if size > _MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="payload exceeds 32KB limit")


def _touch_profile(cur: Any, client_id: str) -> None:
    """确保 profile 行存在（首次写自动建行），并刷新 last_seen。"""
    cur.execute(
        "INSERT INTO user_profiles (client_id, last_seen) VALUES (%s, now()) "
        "ON CONFLICT (client_id) DO UPDATE SET last_seen = now()",
        (client_id,),
    )


def _item_row(row: Any) -> dict:
    item_type, item_id, title, payload, created_at = row
    return {
        "item_type": item_type,
        "item_id": item_id,
        "title": title,
        "payload": payload if payload is not None else {},
        "created_at": created_at.isoformat() if created_at else None,
    }


_ITEM_COLS = "item_type, item_id, title, payload, created_at"


@router.get("/overview")
def get_overview(client_id: ClientId) -> dict:
    """个人概览：nickname/joined_at（无 profile 行时为 null）+ 收藏/历史计数。只读，不自动建行。"""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nickname, joined_at FROM user_profiles WHERE client_id = %s",
                (client_id,),
            )
            row = cur.fetchone()
            nickname = row[0] if row else None
            joined_at = row[1].isoformat() if row and row[1] else None

            cur.execute(
                "SELECT item_type, COUNT(*) FROM user_favorites "
                "WHERE client_id = %s GROUP BY item_type",
                (client_id,),
            )
            fav_counts = {t: 0 for t in _FAVORITE_TYPES}
            fav_counts.update({t: n for t, n in cur.fetchall()})

            cur.execute(
                "SELECT item_type, COUNT(*) FROM user_history "
                "WHERE client_id = %s GROUP BY item_type",
                (client_id,),
            )
            hist_counts = {t: 0 for t in _HISTORY_TYPES}
            hist_counts.update({t: n for t, n in cur.fetchall()})

    return {
        "nickname": nickname,
        "joined_at": joined_at,
        "favorite_counts": fav_counts,
        "history_counts": hist_counts,
    }


@router.put("/profile")
def put_profile(client_id: ClientId, body: ProfileIn) -> dict:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_profiles (client_id, nickname, last_seen) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (client_id) DO UPDATE SET "
                "nickname = EXCLUDED.nickname, last_seen = now()",
                (client_id, body.nickname),
            )
    return {"ok": True, "nickname": body.nickname}


@router.get("/favorites")
def list_favorites(
    client_id: ClientId,
    item_type: str | None = None,
) -> dict:
    if item_type is not None:
        _check_item_type(item_type, _FAVORITE_TYPES)
    where, params = "client_id = %s", [client_id]
    if item_type:
        where += " AND item_type = %s"
        params.append(item_type)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_ITEM_COLS} FROM user_favorites WHERE {where} "
                "ORDER BY created_at DESC",
                params,
            )
            items = [_item_row(r) for r in cur.fetchall()]
    return {"items": items}


@router.put("/favorites")
def put_favorite(client_id: ClientId, body: ItemIn) -> dict:
    _check_item_type(body.item_type, _FAVORITE_TYPES)
    _check_payload_size(body.payload)
    with _connect() as conn:
        with conn.cursor() as cur:
            _touch_profile(cur, client_id)
            cur.execute(
                "INSERT INTO user_favorites (client_id, item_type, item_id, title, payload) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (client_id, item_type, item_id) DO UPDATE SET "
                "title = EXCLUDED.title, payload = EXCLUDED.payload",
                (client_id, body.item_type, body.item_id, body.title, json.dumps(body.payload)),
            )
    return {"ok": True, "favorited": True}


@router.delete("/favorites/{item_type}/{item_id}")
def delete_favorite(client_id: ClientId, item_type: str, item_id: str) -> dict:
    _check_item_type(item_type, _FAVORITE_TYPES)
    with _connect() as conn:
        with conn.cursor() as cur:
            _touch_profile(cur, client_id)
            cur.execute(
                "DELETE FROM user_favorites WHERE client_id = %s "
                "AND item_type = %s AND item_id = %s",
                (client_id, item_type, item_id),
            )
    return {"ok": True, "favorited": False}


@router.get("/history")
def list_history(
    client_id: ClientId,
    item_type: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    if item_type is not None:
        _check_item_type(item_type, _HISTORY_TYPES)
    where, params = "client_id = %s", [client_id]
    if item_type:
        where += " AND item_type = %s"
        params.append(item_type)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_ITEM_COLS} FROM user_history WHERE {where} "
                "ORDER BY created_at DESC LIMIT %s",
                [*params, limit],
            )
            items = [_item_row(r) for r in cur.fetchall()]
    return {"items": items}


@router.post("/history")
def add_history(client_id: ClientId, body: ItemIn) -> dict:
    _check_item_type(body.item_type, _HISTORY_TYPES)
    _check_payload_size(body.payload)
    with _connect() as conn:
        with conn.cursor() as cur:
            _touch_profile(cur, client_id)
            cur.execute(
                "INSERT INTO user_history (client_id, item_type, item_id, title, payload) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (client_id, item_type, item_id) DO UPDATE SET "
                "title = EXCLUDED.title, payload = EXCLUDED.payload, created_at = now()",
                (client_id, body.item_type, body.item_id, body.title, json.dumps(body.payload)),
            )
    return {"ok": True}


@router.delete("/history")
def clear_history(
    client_id: ClientId,
    item_type: str | None = None,
) -> dict:
    if item_type is not None:
        _check_item_type(item_type, _HISTORY_TYPES)
    where, params = "client_id = %s", [client_id]
    if item_type:
        where += " AND item_type = %s"
        params.append(item_type)
    with _connect() as conn:
        with conn.cursor() as cur:
            _touch_profile(cur, client_id)
            cur.execute(
                f"DELETE FROM user_history WHERE {where}",
                params,
            )
            deleted = cur.rowcount
    return {"ok": True, "deleted": deleted if deleted is not None else 0}
