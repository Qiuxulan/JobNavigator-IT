"""岗位画像 insights 接口。

数据源（均为重建的真实资产，不做展示修形）：
- data/gold/role_profiles_v3.json：岗位画像（12 万 JD 近期加权技能频率 /
  趋势动量 / 薪资分位 / 远程比例 / seniority / 月度 JD 序列）;
  缺文件回退 role_profiles_v2.json(v2 重建画像)
- data/gold/trend_forecasts_v2.json：趋势预测包（模型信息 / 置信度 / sparse 标记）
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.role_i18n import role_zh

router = APIRouter(prefix="/v1")

_ROLE_PROFILES_V3 = Path("data/gold/role_profiles_v3.json")
_ROLE_PROFILES_V2 = Path("data/gold/role_profiles_v2.json")
ROLE_PROFILES_V2_PATH = Path(
    os.environ.get(
        "JOBNAV_ROLE_PROFILES_V2",
        str(_ROLE_PROFILES_V3 if _ROLE_PROFILES_V3.exists() else _ROLE_PROFILES_V2),
    )
)
TREND_V2_FORECASTS_PATH = Path(
    os.environ.get("JOBNAV_TREND_V2_FORECASTS", "data/gold/trend_forecasts_v2.json")
)

MONTHLY_TAIL_MONTHS = 24
TOP_SKILLS = 10
JD_SHARE_TREND_MONTHS = 3


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _profiles_payload() -> dict[str, Any]:
    data = _load_json(ROLE_PROFILES_V2_PATH)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _profiles_by_id() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for role in _profiles_payload().get("roles") or []:
        role_id = str(role.get("role_id") or "")
        if role_id:
            out[role_id] = role
    return out


@lru_cache(maxsize=1)
def _profiles_by_name() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for role in _profiles_payload().get("roles") or []:
        name = str(role.get("role_name") or "").strip().lower()
        if name:
            out[name] = role
    return out


@lru_cache(maxsize=1)
def _forecast_packs() -> dict[str, dict[str, Any]]:
    data = _load_json(TREND_V2_FORECASTS_PATH)
    return data if isinstance(data, dict) else {}


def _resolve_profile(key: str) -> dict[str, Any] | None:
    query = str(key).strip()
    if not query:
        return None
    by_id = _profiles_by_id()
    if query in by_id:
        return by_id[query]
    return _profiles_by_name().get(query.lower())


def _pack_for(role_id: str) -> dict[str, Any] | None:
    return _forecast_packs().get(role_id)


def _jd_share_trend(pack: dict[str, Any]) -> tuple[list[float], str]:
    """近 N 个月真实 jd_share 序列 + 方向（up/down/flat，数据不足时为 unknown）。"""
    history = pack.get("history") or []
    tail = [float(row.get("jd_share") or 0.0) for row in history[-JD_SHARE_TREND_MONTHS:]]
    if len(tail) < 2:
        return tail, "unknown"
    first, last = tail[0], tail[-1]
    if last > first * 1.05:
        return tail, "up"
    if last < first * 0.95:
        return tail, "down"
    return tail, "flat"


def _compact_role_row(profile: dict[str, Any]) -> dict[str, Any]:
    role_id = str(profile.get("role_id") or "")
    pack = _pack_for(role_id) or {}
    salary = profile.get("salary") if isinstance(profile.get("salary"), dict) else {}
    jd_share_3m, jd_share_trend = _jd_share_trend(pack)
    monthly = [
        {"month": row.get("month"), "count": row.get("count")}
        for row in (profile.get("monthly_jd_counts") or [])[-6:]
    ]
    return {
        "role_id": role_id,
        "role_name": profile.get("role_name"),
        "role_name_zh": role_zh(profile.get("role_name") or role_id),
        "coarse_role": profile.get("coarse_role", "Other"),
        "jd_count": profile.get("jd_count"),
        "remote_ratio": profile.get("remote_ratio"),
        "salary": {
            "currency": salary.get("currency"),
            "median": salary.get("median"),
            "p25": salary.get("p25"),
            "p75": salary.get("p75"),
            "sample_size": salary.get("sample_size"),
        },
        "trend": {
            "trend_direction": pack.get("trend_direction"),
            "confidence": pack.get("confidence"),
            "sparse": pack.get("sparse"),
            "model_used": pack.get("model_used"),
        },
        "jd_share_3m": jd_share_3m,
        "jd_share_trend": jd_share_trend,
        "monthly_jd_tail": monthly,
    }


@router.get("/roles/overview")
def roles_overview() -> dict:
    """仪表盘聚合：数据集元信息 + 每岗位紧凑画像行（一次调用避免 N 次请求）。"""
    payload = _profiles_payload()
    months = list(payload.get("months") or [])
    roles = [_compact_role_row(profile) for profile in payload.get("roles") or []]
    return {
        "dataset": {
            "version": payload.get("version"),
            "total_jd": payload.get("total_jd"),
            "assigned_jd": payload.get("assigned_jd"),
            "assignment_rate": payload.get("assignment_rate"),
            "months": months,
            "data_through": months[-1] if months else None,
            "role_count": len(roles),
        },
        "roles": roles,
    }


@router.get("/roles/{role_id}/insights")
def role_insights(role_id: str) -> dict:
    """单岗位画像：薪资分位 / 远程比例 / seniority / top 技能 / 月度 JD + 预测模型信息。

    role_id 也接受 role_name（大小写不敏感）。找不到岗位返回 404。
    模型字段缺失时保留 null，不做默认值填充。
    """
    profile = _resolve_profile(role_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"no role profile found for {role_id!r}")
    resolved_id = str(profile.get("role_id") or "")
    pack = _pack_for(resolved_id) or {}

    salary = profile.get("salary") if isinstance(profile.get("salary"), dict) else {}
    skill_freq = profile.get("skill_freq") if isinstance(profile.get("skill_freq"), dict) else {}
    top_skills = [
        {"skill_id": skill_id, "freq": freq}
        for skill_id, freq in sorted(
            skill_freq.items(),
            key=lambda kv: float(kv[1] or 0.0),
            reverse=True,
        )[:TOP_SKILLS]
    ]
    monthly_tail = [
        {"month": row.get("month"), "count": row.get("count")}
        for row in (profile.get("monthly_jd_counts") or [])[-MONTHLY_TAIL_MONTHS:]
    ]

    return {
        "role_id": resolved_id,
        "role_name": profile.get("role_name"),
        "role_name_zh": role_zh(profile.get("role_name") or resolved_id),
        "coarse_role": profile.get("coarse_role", "Other"),
        "jd_count": profile.get("jd_count"),
        "remote_ratio": profile.get("remote_ratio"),
        "salary": {
            "currency": salary.get("currency"),
            "median": salary.get("median"),
            "p25": salary.get("p25"),
            "p75": salary.get("p75"),
            "sample_size": salary.get("sample_size"),
        },
        "seniority_distribution": profile.get("seniority_distribution") or {},
        "top_skills": top_skills,
        "monthly_jd_counts": monthly_tail,
        "model": {
            "model_used": pack.get("model_used"),
            "backtest_smape": pack.get("backtest_smape"),
            "direction_accuracy": pack.get("direction_accuracy"),
            "n_reliable_train_months": pack.get("n_reliable_train_months"),
            "confidence": pack.get("confidence"),
            "trend_direction": pack.get("trend_direction"),
            "sparse": pack.get("sparse"),
        },
    }
