from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.schemas.domain import TrendEvidence, TrendSignal
from app.services.evidence import EvidenceService


class TrendServiceError(RuntimeError):
    pass


class TrendNotFoundError(TrendServiceError):
    pass


@dataclass
class ResolvedRole:
    role_id: str
    canonical_role: str


ROLE_TAXONOMY_PATH = Path("data/gold/role_taxonomy.json")
ROLE_TREND_SCORES_PATH = Path("data/gold/role_trend_scores.json")


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _month_minus(month: str, k: int) -> str:
    """'2026-05-01' 往前推 k 个月 -> '2026-03'。"""
    try:
        y, m = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return str(month)[:7]
    idx = y * 12 + (m - 1) - k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _retrieve_trend_evidence(role: str, month: str, direction: str,
                             top_k: int = 5) -> list[TrendEvidence]:
    """调 EvidenceService 取近 3 个月证据，映射成 TrendEvidence；索引缺失时返回空不报错。"""
    try:
        end = str(month)[:7]
        start = _month_minus(month, 2)
        res = EvidenceService.retrieve_evidence(role, (start, end), top_k, direction)
    except Exception:
        return []
    fallback_date = str(month)[:10] if len(str(month)) >= 10 else "2026-01-01"
    out: list[TrendEvidence] = []
    for ev in res.get("events", []):
        url = ev.get("url") or ""
        eid = "evt_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        out.append(TrendEvidence(
            event_id=eid,
            source=ev.get("source_domain") or "GDELT",
            title=ev.get("title") or "事件",
            event_date=ev.get("published_at") or fallback_date,
            summary=f"{ev.get('event_type', 'news')} · tone {ev.get('tone')} · 来源 {ev.get('source_domain')}",
            impact=ev.get("impact_direction") or "neutral",
            url=url or None,
        ))
    return out


def _resolve_role(job_role: str) -> ResolvedRole:
    query = str(job_role).strip().lower()
    if not query:
        raise TrendNotFoundError("job_role is empty")

    taxonomy = _load_json(ROLE_TAXONOMY_PATH)
    for role in taxonomy:
        name = str(role.get("canonical_role", "")).lower()
        if query == name or query == name.replace(" ", "-"):
            return ResolvedRole(
                role_id=role.get("role_id", role["canonical_role"]),
                canonical_role=role["canonical_role"],
            )
        for alias in role.get("aliases", []):
            if query == str(alias).strip().lower():
                return ResolvedRole(
                    role_id=role.get("role_id", role["canonical_role"]),
                    canonical_role=role["canonical_role"],
                )
    raise TrendNotFoundError(f"no canonical role found for {job_role!r}")


class TrendService:
    @staticmethod
    def get_signal(job_role: str, horizon_months: int | None = None) -> TrendSignal:
        resolved = _resolve_role(job_role)

        scores = _load_json(ROLE_TREND_SCORES_PATH)
        role_scores = [
            s for s in scores
            if s.get("canonical_role", "").lower() == resolved.canonical_role.lower()
        ]
        if not role_scores:
            raise TrendNotFoundError(f"no trend result found for {resolved.canonical_role}")

        role_scores.sort(key=lambda x: str(x.get("month", "")), reverse=True)
        latest = role_scores[0]

        predicted_demand_index = float(latest.get("predicted_demand_index", 0.0))
        confidence = float(latest.get("confidence", 0.0))

        if predicted_demand_index >= 0.58:
            trend_direction = "up"
        elif predicted_demand_index <= 0.42:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        contributions = latest.get("contributions", {})
        if isinstance(contributions, str):
            contributions = json.loads(contributions)

        factors = sorted(contributions.keys(), key=lambda k: abs(float(contributions.get(k, 0))), reverse=True)[:3]
        if not factors:                       # 兼容 main_factors_json 字段
            try:
                factors = json.loads(latest.get("main_factors_json", "[]"))[:3]
            except (json.JSONDecodeError, TypeError):
                factors = []

        evidence = _retrieve_trend_evidence(
            resolved.canonical_role, str(latest.get("month", "")), trend_direction
        )

        return TrendSignal(
            canonical_role=resolved.canonical_role,
            horizon_months=int(horizon_months or settings.trend_horizon_months),
            trend_direction=trend_direction,
            predicted_demand_index=predicted_demand_index,
            confidence=confidence,
            main_factors=factors,
            evidence=evidence,
        )
