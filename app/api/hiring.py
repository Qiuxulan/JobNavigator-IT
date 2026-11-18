"""招聘风向标 API：消费三份招聘/裁员信号数据文件。

- GET /v1/hiring/overview   公司招聘动能 + 裁员信号 + HN Who's Hiring 月度序列

数据文件由 pipelines/trend 下的采集/构建脚本产出，可能并发重写：
读取时校验 mtime，JSON 解析失败短暂等待后重试；单份文件缺失只让对应 section 为 null。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

MOMENTUM_PATH = Path(
    os.environ.get("JOBNAV_HIRING_MOMENTUM", "data/gold/company_hiring_momentum.json")
)
LAYOFF_PATH = Path(
    os.environ.get("JOBNAV_LAYOFF_SIGNALS", "data/gold/layoff_signals.json")
)
HN_HIRING_PATH = Path(
    os.environ.get("JOBNAV_HN_HIRING", "/data/shichaojian/JNIT/processed/hn_hiring_monthly.json")
)

router = APIRouter(prefix="/v1/hiring")

_TOP_COMPANIES = 12
_SECTOR_TOP = 3
_LAYOFF_RECENT_MONTHS = 24
_LAYOFF_TOP_WINDOW_MONTHS = 18
_LAYOFF_TOP_N = 10

_caches: dict[str, dict[str, Any]] = {
    "momentum": {"mtime": None, "data": None},
    "layoff": {"mtime": None, "data": None},
    "hn": {"mtime": None, "data": None},
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


def _company_momentum_section(raw: dict[str, Any]) -> dict[str, Any]:
    by_sector = raw.get("by_sector") or {}
    flat: list[dict[str, Any]] = []
    sector_out: dict[str, list[dict[str, Any]]] = {}
    if isinstance(by_sector, dict):
        for sector, payload in by_sector.items():
            companies = (payload or {}).get("companies") or []
            ranked = sorted(
                (c for c in companies if isinstance(c, dict)),
                key=lambda c: c.get("latest_open_roles") or 0,
                reverse=True,
            )
            sector_out[sector] = ranked[:_SECTOR_TOP]
            for c in ranked:
                entry = dict(c)
                entry.setdefault("sector", sector)
                flat.append(entry)
    flat.sort(key=lambda c: ((c.get("momentum_30d") or {}).get("delta") or 0), reverse=True)
    return {
        "window": raw.get("window"),
        "n_companies": raw.get("n_companies"),
        "top": flat[:_TOP_COMPANIES],
        "by_sector": sector_out,
    }


def _layoff_section(raw: dict[str, Any]) -> dict[str, Any]:
    monthly = raw.get("monthly_table") or {}
    recent: list[dict[str, Any]] = []
    if isinstance(monthly, dict):
        for month in sorted(monthly)[-_LAYOFF_RECENT_MONTHS:]:
            row = monthly[month] or {}
            recent.append({
                "month": month,
                "notices": row.get("notices", 0),
                "employees_affected": row.get("employees_affected", 0),
                "n_companies": row.get("n_companies", 0),
            })
    cutoff = recent[max(0, len(recent) - _LAYOFF_TOP_WINDOW_MONTHS)]["month"] if recent else "9999"
    top_employers = [
        e for e in (raw.get("top_companies_by_employees") or [])
        if isinstance(e, dict) and str(e.get("month", "")) >= cutoff
    ][: _LAYOFF_TOP_N]
    return {
        "window": raw.get("window"),
        "n_notices": raw.get("n_notices"),
        "recent_months": recent,
        "top_recent_employers": top_employers,
    }


def _hn_section(raw: dict[str, Any]) -> dict[str, Any]:
    months_raw = raw.get("months") or {}
    months = [
        {
            "month": month,
            "n_job_posts": (payload or {}).get("n_job_posts", 0),
            "remote_ratio": (payload or {}).get("remote_ratio"),
            "salary_disclosed_ratio": (payload or {}).get("salary_disclosed_ratio"),
        }
        for month, payload in sorted(months_raw.items())
    ]
    return {
        "months": months,
        "skill_mentions_top30": raw.get("skill_mentions_top30") or [],
    }


@router.get("/overview")
def hiring_overview() -> dict[str, Any]:
    momentum = _load(MOMENTUM_PATH, "momentum")
    layoff = _load(LAYOFF_PATH, "layoff")
    hn = _load(HN_HIRING_PATH, "hn")
    generated = [d.get("generated_at") for d in (momentum, layoff, hn) if d and d.get("generated_at")]
    return {
        "generated_at": max(generated) if generated else None,
        "company_momentum": _company_momentum_section(momentum) if momentum else None,
        "layoffs": _layoff_section(layoff) if layoff else None,
        "hn_hiring": _hn_section(hn) if hn else None,
    }
