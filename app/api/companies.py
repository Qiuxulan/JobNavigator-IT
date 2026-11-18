"""公司雷达 API：公司级招聘/裁员/HC 视图。

- GET /v1/companies            公司列表（动能 + 近 12 月裁员统计 + 状态标签）
- GET /v1/companies/{domain}   公司详情（日度在招序列 + WARN 记录 + 相关新闻）

数据文件由 pipelines/trend 下的构建脚本产出，可能并发重写：
读取时校验 mtime，JSON 解析失败短暂等待后重试；文件缺失返回空结果不报错。
裁员公司名与 momentum 公司名口径不一致（"Meta Platforms" vs "meta"），
匹配时归一化去法律后缀后做词边界包含；新闻用 PG 正则词边界匹配避免 pineapple 误中。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

MOMENTUM_PATH = Path(
    os.environ.get("JOBNAV_HIRING_MOMENTUM", "data/gold/company_hiring_momentum.json")
)
LAYOFF_PATH = Path(
    os.environ.get("JOBNAV_LAYOFF_SIGNALS", "data/gold/layoff_signals.json")
)

_DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)

_LAYOFF_WINDOW_MONTHS = 12
_NEWS_LIMIT = 10

router = APIRouter(prefix="/v1/companies")

_caches: dict[str, dict[str, Any]] = {
    "momentum": {"mtime": None, "data": None},
    "layoff": {"mtime": None, "data": None},
}

# 公司归一化时丢弃的法律/组织形式后缀
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "llp", "lp", "ltd", "corp", "corporation",
    "co", "company", "group", "holdings", "plc", "gmbh",
}


def _load(path: Path, cache_key: str) -> dict[str, Any] | None:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    cache = _caches[cache_key]
    if cache["mtime"] != mtime or cache["data"] is None:
        data: dict[str, Any] | None = None
        for attempt in range(3):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
            except (json.JSONDecodeError, OSError):
                if attempt < 2:
                    time.sleep(2.0)
        if not isinstance(data, dict):
            return None
        cache["mtime"] = mtime
        cache["data"] = data
    return cache["data"]


def _norm_words(name: str) -> list[str]:
    words = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    return [w for w in words if w not in _LEGAL_SUFFIXES]


def _company_pattern(name: str) -> re.Pattern[str] | None:
    """公司名归一化后构造词边界匹配：apple 命中 Apple Computer / APPLE INC，
    不命中 pineapple；返回 None 表示名字太短/空，放弃匹配。"""
    words = _norm_words(name)
    if not words or (len(words) == 1 and len(words[0]) < 3):
        return None
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<!\w){body}(?!\w)")


def _employer_matches(pattern: re.Pattern[str] | None, employer: str) -> bool:
    if pattern is None:
        return False
    norm = " ".join(_norm_words(employer))
    return bool(pattern.search(norm))


def _shift_month(month: str, delta: int) -> str:
    if not _MONTH_RE.match(month or ""):
        return "0000-00"
    y, m = int(month[:4]), int(month[5:7])
    total = y * 12 + (m - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _max_record_month(records: list[dict[str, Any]]) -> str:
    months = [str(r.get("month") or "") for r in records if r.get("month")]
    months = [m for m in months if _MONTH_RE.match(m)]
    return max(months) if months else "0000-00"


def _load_records(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """(WARN 记录列表, 数据锚点月=记录中最新月)。量小（约 1k 条），逐公司归一化匹配即可。"""
    records = [r for r in (raw.get("records") or []) if isinstance(r, dict)]
    return records, _max_record_month(records)


def _company_layoffs(
    records: list[dict[str, Any]], name: str
) -> list[dict[str, Any]]:
    pattern = _company_pattern(name)
    hits = [
        r for r in records
        if _employer_matches(pattern, str(r.get("employer") or ""))
    ]
    hits.sort(key=lambda r: str(r.get("month") or ""), reverse=True)
    return [
        {
            "month": r.get("month"),
            "employer": r.get("employer"),
            "employees_affected": r.get("employees_affected", 0),
            "n_notices": r.get("n_notices", 0),
            "states": r.get("states") or [],
            "event_types": r.get("event_types") or [],
            "latest_effective_date": r.get("latest_effective_date"),
        }
        for r in hits
    ]


def _status_tag(delta_30d: float, layoffs_12m: int) -> str:
    if layoffs_12m > 0:
        return "shrinking"
    if delta_30d > 0:
        return "expanding"
    if delta_30d < 0:
        return "cooling"
    return "stable"


def _connect():
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="psycopg not installed")
    try:
        return psycopg.connect(_DSN)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"news db unavailable: {exc}")


def _fetch_related_news(name: str, limit: int = _NEWS_LIMIT) -> list[dict[str, Any]]:
    """news_items 按公司名正则词边界匹配（title/summary），取最近 N 条。"""
    words = _norm_words(name)
    if not words or (len(words) == 1 and len(words[0]) < 3):
        return []
    body = r"\s+".join(re.escape(w) for w in words)
    pattern = rf"\m{body}\M"
    sql = (
        "SELECT title, url, source, published_at FROM news_items "
        "WHERE (title ~* %s OR summary ~* %s) AND lang IN ('zh','en') "
        "ORDER BY published_at DESC NULLS LAST LIMIT %s"
    )
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (pattern, pattern, limit))
            rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception:
        return []
    return [
        {
            "title": row[0],
            "url": row[1],
            "source": row[2],
            "published_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


def _empty_listing() -> dict[str, Any]:
    return {"generated_at": None, "window": None, "n_companies": 0, "companies": []}


@router.get("")
def list_companies() -> dict[str, Any]:
    momentum = _load(MOMENTUM_PATH, "momentum")
    layoff = _load(LAYOFF_PATH, "layoff")
    if not momentum:
        return _empty_listing()

    companies_raw = momentum.get("companies") or {}
    records, anchor = _load_records(layoff) if layoff else ([], "0000-00")
    cutoff = _shift_month(anchor, -(_LAYOFF_WINDOW_MONTHS - 1)) if anchor != "0000-00" else None

    out: list[dict[str, Any]] = []
    for domain, c in companies_raw.items():
        if not isinstance(c, dict):
            continue
        name = str(c.get("company") or domain)
        events = _company_layoffs(records, name) if records else []
        recent = [
            e for e in events
            if cutoff is None or str(e.get("month") or "") >= cutoff
        ]
        delta_30d = float(((c.get("momentum_30d") or {}).get("delta")) or 0)
        out.append({
            "domain": domain,
            "name": name,
            "sector": c.get("sector"),
            "latest_open_roles": (c.get("latest") or {}).get("open_roles"),
            "momentum_7d": c.get("momentum_7d"),
            "momentum_30d": c.get("momentum_30d"),
            "layoff_events_12m": {
                "notices": sum(int(e.get("n_notices") or 0) for e in recent),
                "employees": sum(int(e.get("employees_affected") or 0) for e in recent),
            },
            "status_tag": _status_tag(delta_30d, len(recent)),
        })
    out.sort(key=lambda c: (c.get("latest_open_roles") or 0), reverse=True)
    return {
        "generated_at": momentum.get("generated_at"),
        "window": momentum.get("window"),
        "n_companies": len(out),
        "companies": out,
    }


@router.get("/{domain}")
def company_detail(domain: str) -> dict[str, Any]:
    momentum = _load(MOMENTUM_PATH, "momentum")
    layoff = _load(LAYOFF_PATH, "layoff")
    if not momentum:
        raise HTTPException(status_code=404, detail="company data unavailable")

    c = (momentum.get("companies") or {}).get(domain)
    if not isinstance(c, dict):
        raise HTTPException(status_code=404, detail=f"unknown company: {domain}")

    name = str(c.get("company") or domain)
    records, _anchor = _load_records(layoff) if layoff else ([], "0000-00")
    layoff_events = _company_layoffs(records, name) if records else []
    delta_30d = float(((c.get("momentum_30d") or {}).get("delta")) or 0)
    recent_12m = [
        e for e in layoff_events
        if str(e.get("month") or "") >= _shift_month(_max_record_month(layoff_events), -11)
    ]

    daily = [
        {"date": d.get("date"), "count": d.get("open_roles")}
        for d in (c.get("daily") or [])
        if isinstance(d, dict)
    ]
    return {
        "domain": domain,
        "name": name,
        "sector": c.get("sector"),
        "status_tag": _status_tag(delta_30d, len(recent_12m)),
        "latest_open_roles": (c.get("latest") or {}).get("open_roles"),
        "open_roles_avg_30d": c.get("open_roles_avg_30d"),
        "momentum_7d": c.get("momentum_7d"),
        "momentum_30d": c.get("momentum_30d"),
        "window": momentum.get("window"),
        "generated_at": momentum.get("generated_at"),
        "layoff_source": (layoff or {}).get("source"),
        "open_roles_daily": daily,
        "layoff_events": layoff_events,
        "related_news": _fetch_related_news(name),
    }
