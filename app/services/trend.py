from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.schemas.domain import TrendSignal


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

        return TrendSignal(
            canonical_role=resolved.canonical_role,
            horizon_months=int(horizon_months or settings.trend_horizon_months),
            trend_direction=trend_direction,
            predicted_demand_index=predicted_demand_index,
            confidence=confidence,
            main_factors=factors,
        )
