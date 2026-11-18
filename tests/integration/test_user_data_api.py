"""用户个人数据 API（/v1/me）测试：monkeypatch _connect 换内存假连接，不连真实数据库。

假连接按 SQL 特征分发到内存 store，模拟 PG 的 upsert / ON CONFLICT 置顶语义，
覆盖 overview 空用户、favorite upsert/delete、history 去重置顶、非法 item_type 422、
缺 X-Client-Id 报错、payload 超 32KB 413。
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import user_data
from app.main import app

client = TestClient(app)

CID = "test-client-0001"
H = {"X-Client-Id": CID}


def _dt(seq: int) -> datetime:
    return datetime(2026, 1, 1) + timedelta(seconds=seq)


class _FakeCursor:
    """只实现 user_data.py 用到的语句子集。"""

    def __init__(self, store: dict):
        self._s = store
        self._rows: list = []
        self.rowcount: int = 0

    def execute(self, sql: str, params=None):
        p = list(params or [])
        s = self._s
        self._rows = []
        self.rowcount = 0

        if sql.startswith("SELECT nickname, joined_at FROM user_profiles"):
            prof = s["profiles"].get(p[0])
            self._rows = [(prof["nickname"], prof["joined_at"])] if prof else []
        elif "FROM user_favorites" in sql and "COUNT(*)" in sql:
            counts: dict = {}
            for (cid, t, _iid) in s["favorites"]:
                if cid == p[0]:
                    counts[t] = counts.get(t, 0) + 1
            self._rows = list(counts.items())
        elif "FROM user_history" in sql and "COUNT(*)" in sql:
            counts = {}
            for (cid, t, _iid) in s["history"]:
                if cid == p[0]:
                    counts[t] = counts.get(t, 0) + 1
            self._rows = list(counts.items())
        elif sql.startswith("INSERT INTO user_profiles"):
            s["seq"] += 1
            prof = s["profiles"].setdefault(
                p[0],
                {"nickname": None, "joined_at": _dt(s["seq"]), "last_seen": None},
            )
            if len(p) >= 2:
                prof["nickname"] = p[1]
            prof["last_seen"] = _dt(s["seq"])
        elif sql.startswith("INSERT INTO user_favorites"):
            s["seq"] += 1
            s["favorites"][(p[0], p[1], p[2])] = {
                "title": p[3],
                "payload": json.loads(p[4]),
                "created_at": _dt(s["seq"]),
                "seq": s["seq"],
            }
        elif sql.startswith("DELETE FROM user_favorites"):
            self.rowcount = (
                1 if s["favorites"].pop((p[0], p[1], p[2]), None) is not None else 0
            )
        elif sql.startswith("INSERT INTO user_history"):
            s["seq"] += 1
            s["history"][(p[0], p[1], p[2])] = {
                "title": p[3],
                "payload": json.loads(p[4]),
                "created_at": _dt(s["seq"]),
                "seq": s["seq"],
            }
        elif sql.startswith("DELETE FROM user_history"):
            keys = [
                k
                for k in s["history"]
                if k[0] == p[0] and (len(p) < 2 or k[1] == p[1])
            ]
            for k in keys:
                del s["history"][k]
            self.rowcount = len(keys)
        elif "FROM user_favorites" in sql:
            has_type_filter = "item_type = %s" in sql
            rows = [
                (k[1], k[2], v["title"], v["payload"], v["created_at"])
                for k, v in s["favorites"].items()
                if k[0] == p[0] and (not has_type_filter or k[1] == p[1])
            ]
            rows.sort(key=lambda r: r[4], reverse=True)
            self._rows = rows
        elif "FROM user_history" in sql:
            has_type_filter = "item_type = %s" in sql
            rows = [
                (k[1], k[2], v["title"], v["payload"], v["created_at"])
                for k, v in s["history"].items()
                if k[0] == p[0] and (not has_type_filter or k[1] == p[1])
            ]
            rows.sort(key=lambda r: r[4], reverse=True)
            limit = p[-1] if "LIMIT" in sql else None
            self._rows = rows[:limit] if limit else rows
        else:  # pragma: no cover
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, store: dict):
        self._store = store

    def cursor(self):
        return _FakeCursor(self._store)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def fake_db(monkeypatch):
    store = {"profiles": {}, "favorites": {}, "history": {}, "seq": 0}
    monkeypatch.setattr(user_data, "_connect", lambda: _FakeConn(store))
    return store


def _put_favorite(item_type="job", item_id="role_001", title="测试岗位", payload=None):
    return client.put(
        "/v1/me/favorites",
        headers=H,
        json={
            "item_type": item_type,
            "item_id": item_id,
            "title": title,
            "payload": payload or {"score": 0.9},
        },
    )


def _post_history(item_type="news", item_id="news_001", title="测试新闻", payload=None):
    return client.post(
        "/v1/me/history",
        headers=H,
        json={
            "item_type": item_type,
            "item_id": item_id,
            "title": title,
            "payload": payload or {},
        },
    )


def test_overview_empty_user(fake_db):
    resp = client.get("/v1/me/overview", headers=H)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["nickname"] is None
    assert payload["joined_at"] is None
    assert payload["favorite_counts"] == {"job": 0, "news": 0, "path": 0}
    assert payload["history_counts"] == {"news": 0, "trend": 0, "match": 0}
    # 只读接口不自动建行
    assert fake_db["profiles"] == {}


def test_put_profile_and_overview(fake_db):
    resp = client.put("/v1/me/profile", headers=H, json={"nickname": "小明"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "nickname": "小明"}

    overview = client.get("/v1/me/overview", headers=H).json()
    assert overview["nickname"] == "小明"
    assert overview["joined_at"]

    # upsert：改名覆盖
    resp = client.put("/v1/me/profile", headers=H, json={"nickname": "阿强"})
    assert resp.json() == {"ok": True, "nickname": "阿强"}
    assert client.get("/v1/me/overview", headers=H).json()["nickname"] == "阿强"
    assert len(fake_db["profiles"]) == 1


def test_profile_nickname_too_long(fake_db):
    resp = client.put("/v1/me/profile", headers=H, json={"nickname": "x" * 33})
    assert resp.status_code == 422


def test_favorite_upsert_and_list(fake_db):
    resp = _put_favorite()
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "favorited": True}

    items = client.get("/v1/me/favorites", headers=H).json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["item_type"] == "job"
    assert item["item_id"] == "role_001"
    assert item["title"] == "测试岗位"
    assert item["payload"] == {"score": 0.9}
    assert item["created_at"]

    # 重复调用更新 payload，不报错且只有一行
    _put_favorite(title="新标题", payload={"score": 0.5})
    items = client.get("/v1/me/favorites", headers=H).json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "新标题"
    assert items[0]["payload"] == {"score": 0.5}
    # 首次写自动建行 + last_seen 刷新
    assert CID in fake_db["profiles"]
    assert fake_db["profiles"][CID]["last_seen"] is not None


def test_favorite_type_filter_and_desc_order(fake_db):
    _put_favorite(item_type="job", item_id="role_001", title="岗位A")
    _put_favorite(item_type="news", item_id="news_001", title="新闻B")
    _put_favorite(item_type="job", item_id="role_002", title="岗位C")

    items = client.get("/v1/me/favorites", headers=H).json()["items"]
    assert [i["item_id"] for i in items] == ["role_002", "news_001", "role_001"]

    filtered = client.get(
        "/v1/me/favorites", headers=H, params={"item_type": "job"}
    ).json()["items"]
    assert [i["item_id"] for i in filtered] == ["role_002", "role_001"]
    assert all(i["item_type"] == "job" for i in filtered)

    bad = client.get("/v1/me/favorites", headers=H, params={"item_type": "trend"})
    assert bad.status_code == 422


def test_favorite_delete(fake_db):
    _put_favorite()
    resp = client.delete("/v1/me/favorites/job/role_001", headers=H)
    assert resp.json() == {"ok": True, "favorited": False}
    assert client.get("/v1/me/favorites", headers=H).json()["items"] == []

    # 不存在也返回成功
    resp = client.delete("/v1/me/favorites/job/role_404", headers=H)
    assert resp.json() == {"ok": True, "favorited": False}


def test_history_dedup_bump_to_top(fake_db):
    assert _post_history(item_id="news_001", title="新闻一").json() == {"ok": True}
    assert _post_history(item_id="news_002", title="新闻二").json() == {"ok": True}

    items = client.get("/v1/me/history", headers=H).json()["items"]
    assert [i["item_id"] for i in items] == ["news_002", "news_001"]

    # 重复浏览 news_001：去重且置顶
    _post_history(item_id="news_001", title="新闻一")
    items = client.get("/v1/me/history", headers=H).json()["items"]
    assert [i["item_id"] for i in items] == ["news_001", "news_002"]
    assert len(fake_db["history"]) == 2


def test_history_filter_limit_and_clear(fake_db):
    for i in range(3):
        _post_history(item_type="news", item_id=f"news_{i}", title=f"新闻{i}")
    _post_history(item_type="match", item_id="match_001", title="匹配一")

    limited = client.get("/v1/me/history", headers=H, params={"limit": 2}).json()["items"]
    assert len(limited) == 2
    assert client.get("/v1/me/history", headers=H, params={"limit": 101}).status_code == 422

    filtered = client.get(
        "/v1/me/history", headers=H, params={"item_type": "match"}
    ).json()["items"]
    assert [i["item_id"] for i in filtered] == ["match_001"]

    # 按类型清空
    resp = client.delete("/v1/me/history", headers=H, params={"item_type": "news"})
    assert resp.json() == {"ok": True, "deleted": 3}
    remaining = client.get("/v1/me/history", headers=H).json()["items"]
    assert [i["item_id"] for i in remaining] == ["match_001"]

    # 不传 item_type 清空全部
    resp = client.delete("/v1/me/history", headers=H)
    assert resp.json() == {"ok": True, "deleted": 1}
    assert client.get("/v1/me/history", headers=H).json()["items"] == []


def test_overview_counts(fake_db):
    _put_favorite(item_type="job", item_id="role_001")
    _put_favorite(item_type="news", item_id="news_001")
    _post_history(item_type="news", item_id="news_001")
    _post_history(item_type="trend", item_id="trend_001")

    overview = client.get("/v1/me/overview", headers=H).json()
    assert overview["favorite_counts"] == {"job": 1, "news": 1, "path": 0}
    assert overview["history_counts"] == {"news": 1, "trend": 1, "match": 0}


def test_invalid_item_type(fake_db):
    # favorites 只允许 job/news/path
    resp = client.put(
        "/v1/me/favorites",
        headers=H,
        json={"item_type": "trend", "item_id": "x1", "title": "", "payload": {}},
    )
    assert resp.status_code == 422
    resp = client.delete("/v1/me/favorites/match/x1", headers=H)
    assert resp.status_code == 422

    # history 只允许 news/trend/match
    resp = client.post(
        "/v1/me/history",
        headers=H,
        json={"item_type": "job", "item_id": "x1", "title": "", "payload": {}},
    )
    assert resp.status_code == 422
    resp = client.delete("/v1/me/history", headers=H, params={"item_type": "job"})
    assert resp.status_code == 422


def test_client_id_header_validation(fake_db):
    # 缺失 header
    assert client.get("/v1/me/overview").status_code == 422
    assert client.put("/v1/me/profile", json={"nickname": "a"}).status_code == 422

    # 非法字符 / 过短 / 过长
    for bad in ("bad id!", "ab", "x" * 65):
        resp = client.get("/v1/me/overview", headers={"X-Client-Id": bad})
        assert resp.status_code == 422, bad

    # 合法边界：8 字符与 64 字符
    assert client.get("/v1/me/overview", headers={"X-Client-Id": "a" * 8}).status_code == 200
    assert client.get("/v1/me/overview", headers={"X-Client-Id": "a" * 64}).status_code == 200


def test_payload_too_large(fake_db):
    big = {"blob": "x" * 33000}
    resp = _put_favorite(payload=big)
    assert resp.status_code == 413

    resp = _post_history(payload=big)
    assert resp.status_code == 413

    # 32KB 以内正常
    ok = _put_favorite(payload={"blob": "x" * 1000})
    assert ok.status_code == 200
