from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.domain import TrendEvidence, TrendSignal
from app.services.evidence import EvidenceService
from app.services.role_i18n import role_zh


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
EVIDENCE_WINDOW = ("2026-01", "2026-06")


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _retrieve_trend_evidence(role: str, direction: str, top_k: int = 5) -> list[TrendEvidence]:
    try:
        res = EvidenceService.retrieve_evidence(role, EVIDENCE_WINDOW, top_k, direction)
    except Exception:
        return []

    fallback_date = f"{EVIDENCE_WINDOW[1]}-01"
    out: list[TrendEvidence] = []
    for ev in res.get("events", []):
        url = ev.get("url") or ""
        eid = "evt_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        out.append(
            TrendEvidence(
                event_id=eid,
                source=ev.get("source_domain") or ev.get("source") or "GDELT",
                title=ev.get("title") or "行业事件",
                event_date=ev.get("published_at") or ev.get("event_date") or fallback_date,
                summary=f"{ev.get('event_type', 'news')} · tone {ev.get('tone')} · {ev.get('source_domain') or ''}",
                impact=ev.get("impact_direction") or "neutral",
                url=url or None,
            )
        )
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


def _extract_factors(forecast_row: dict[str, Any]) -> list[str]:
    raw = forecast_row.get("supplemental_signals")
    if isinstance(raw, list):
        return [str(x) for x in raw][:3]
    if not isinstance(raw, dict):
        return []

    labels = {
        "gdelt": "新闻情绪信号参与修正",
        "github": "GitHub 活跃度信号参与修正",
        "arxiv": "论文热度信号参与修正",
    }
    factors: list[str] = []
    for key, value in raw.items():
        if not isinstance(value, dict):
            factors.append(labels.get(str(key), str(key)))
            continue
        contribution = float(value.get("contribution") or 0.0)
        signal = value.get("signal")
        observed = bool(value.get("observed"))
        if not observed and contribution == 0:
            continue
        direction = "正向" if contribution > 0 else "负向" if contribution < 0 else "中性"
        signal_text = "" if signal is None else f"，信号值 {float(signal):.3f}"
        factors.append(f"{labels.get(str(key), str(key))}：{direction}贡献 {contribution:.4f}{signal_text}")
    return factors[:3]


def _patchtst_signal(canonical_role: str, horizon: int) -> tuple[str, float, float, list[str], list[dict[str, Any]], int] | None:
    try:
        from app.services.trend_predictor import predict

        payload = predict(canonical_role, horizon)
    except Exception:
        return None

    forecast = payload.get("monthly_forecast") or []
    final_row = forecast[-1] if forecast else {}
    return (
        payload.get("trend_direction", "flat"),
        float(payload.get("predicted_demand_index", 0.0)),
        float(payload.get("confidence", 0.0)),
        _extract_factors(final_row),
        forecast,
        int(payload.get("horizon_months") or len(forecast) or horizon),
    )


def _baseline_signal(canonical_role: str) -> tuple[str, float, float, list[str]]:
    scores = _load_json(ROLE_TREND_SCORES_PATH)
    role_scores = [
        s for s in scores
        if s.get("canonical_role", "").lower() == canonical_role.lower()
    ]
    if not role_scores:
        raise TrendNotFoundError(f"no trend result found for {canonical_role}")

    role_scores.sort(key=lambda x: str(x.get("month", "")), reverse=True)
    latest = role_scores[0]
    idx = float(latest.get("predicted_demand_index", 0.0))
    conf = float(latest.get("confidence", 0.0))
    direction = "up" if idx >= 0.58 else "down" if idx <= 0.42 else "flat"
    try:
        factors = json.loads(latest.get("main_factors_json", "[]"))[:3]
    except (json.JSONDecodeError, TypeError):
        factors = []
    return direction, idx, conf, factors


class TrendService:
    @staticmethod
    def get_signal(job_role: str, horizon_months: int | None = None) -> TrendSignal:
        resolved = _resolve_role(job_role)
        horizon = int(horizon_months or settings.trend_horizon_months)
        patchtst = _patchtst_signal(resolved.canonical_role, horizon)

        if patchtst is None:
            direction, idx, conf, factors = _baseline_signal(resolved.canonical_role)
            monthly_forecast: list[dict[str, Any]] = []
        else:
            direction, idx, conf, factors, monthly_forecast, horizon = patchtst

        evidence = _retrieve_trend_evidence(resolved.canonical_role, direction)
        return TrendSignal(
            canonical_role=resolved.canonical_role,
            role_name_zh=role_zh(resolved.canonical_role),
            horizon_months=horizon,
            trend_direction=direction,
            predicted_demand_index=idx,
            confidence=conf,
            main_factors=factors,
            evidence=evidence,
            monthly_forecast=monthly_forecast,
        )
