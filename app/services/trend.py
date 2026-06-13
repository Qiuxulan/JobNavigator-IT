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
# PatchTST 预测未来、未来月无新闻 -> 证据统一取最近真实事件窗口
EVIDENCE_WINDOW = ("2026-01", "2026-06")


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


def _retrieve_trend_evidence(role: str, direction: str,
                             top_k: int = 5) -> list[TrendEvidence]:
    """从最近真实事件窗口取证据，映射成 TrendEvidence；索引缺失时返回空不报错。"""
    try:
        res = EvidenceService.retrieve_evidence(role, EVIDENCE_WINDOW, top_k, direction)
    except Exception:
        return []
    fallback_date = f"{EVIDENCE_WINDOW[1]}-01"
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


def _extract_factors(forecast_row: dict) -> list[str]:
    raw = forecast_row.get("supplemental_signals")
    if isinstance(raw, list):
        return [str(x) for x in raw][:3]
    if isinstance(raw, dict):
        return [str(k) for k in raw][:3]
    return []


def _patchtst_signal(canonical_role: str, horizon: int):
    """优先用组员1 PatchTST 预测。返回 (direction, idx, conf, factors) 或 None(缺失时)。"""
    try:
        from app.services.trend_predictor import predict   # 懒加载, 避免启动拽 torch
        p = predict(canonical_role, horizon)
    except Exception:
        return None
    forecast = p.get("monthly_forecast") or [{}]
    return (
        p.get("trend_direction", "flat"),
        float(p.get("predicted_demand_index", 0.0)),
        float(p.get("confidence", 0.0)),
        _extract_factors(forecast[-1]),
    )


def _baseline_signal(canonical_role: str):
    """回退：基线 role_trend_scores.json。返回 (direction, idx, conf, factors)。"""
    scores = _load_json(ROLE_TREND_SCORES_PATH)
    role_scores = [s for s in scores
                   if s.get("canonical_role", "").lower() == canonical_role.lower()]
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
        sig = _patchtst_signal(resolved.canonical_role, horizon)   # 优先 PatchTST
        if sig is None:                                            # 缺失 -> 回退基线
            sig = _baseline_signal(resolved.canonical_role)
        direction, idx, conf, factors = sig
        evidence = _retrieve_trend_evidence(resolved.canonical_role, direction)
        return TrendSignal(
            canonical_role=resolved.canonical_role,
            horizon_months=horizon,
            trend_direction=direction,
            predicted_demand_index=idx,
            confidence=conf,
            main_factors=factors,
            evidence=evidence,
        )
