from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.domain import TrendEvidence, TrendSignal
from app.services.evidence import EvidenceService
from app.services.evidence_service_v2 import EvidenceServiceV2
from app.services.role_i18n import role_zh


class TrendServiceError(RuntimeError):
    pass


class TrendNotFoundError(TrendServiceError):
    pass


@dataclass
class ResolvedRole:
    role_id: str
    canonical_role: str


_TAXONOMY_V3_PATH = Path("data/gold/role_taxonomy_v3.json")
_TAXONOMY_V2_PATH = Path("data/gold/role_taxonomy_v2.json")
ROLE_TAXONOMY_PATH = (
    _TAXONOMY_V3_PATH if _TAXONOMY_V3_PATH.exists()
    else _TAXONOMY_V2_PATH if _TAXONOMY_V2_PATH.exists()
    else Path("data/gold/role_taxonomy.json")
)
ROLE_TREND_SCORES_PATH = Path("data/gold/role_trend_scores.json")
EVIDENCE_WINDOW = ("2026-08", "2026-10")  # 兜底窗口；实际用 _evidence_window() 动态滚动

_evidence_window_cache: dict[str, tuple[str, str]] = {}


def _evidence_window() -> tuple[str, str]:
    """动态证据窗口：分片目录最新月往前 3 个月（含最新月）。

    按当前自然月缓存，月度 cron 产出新分片后窗口自动前移；
    分片目录不可读时回退到 EVIDENCE_WINDOW 兜底值。
    """
    from app.services.evidence_service_v2 import latest_shard_month

    key = datetime.now().strftime("%Y-%m")
    if key in _evidence_window_cache:
        return _evidence_window_cache[key]
    window = EVIDENCE_WINDOW
    latest = latest_shard_month()
    if latest:
        try:
            y, m = int(latest[:4]), int(latest[5:7])
            m -= 2
            while m <= 0:
                m += 12
                y -= 1
            window = (f"{y:04d}-{m:02d}", latest)
        except (ValueError, IndexError):
            pass
    _evidence_window_cache[key] = window
    return window

# v2 重建资产（趋势预测 + 真实月度面板）。环境变量可覆盖；文件缺失时回退旧逻辑。
TREND_V2_FORECASTS = Path(
    os.environ.get("JOBNAV_TREND_V2_FORECASTS", "data/gold/trend_forecasts_v2.json")
)
TREND_V2_PANEL = Path(
    os.environ.get("JOBNAV_TREND_V2_PANEL", "data/gold/trend_panel_v2.json")
)

HISTORY_TAIL_MONTHS = 24
FORECAST_MONTHS = 12


def _load_json(path: Path) -> Any:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _v2_available() -> bool:
    return TREND_V2_FORECASTS.exists()


@lru_cache(maxsize=1)
def _load_v2_forecasts() -> dict[str, dict[str, Any]]:
    """trend_forecasts_v2.json: role_id -> 预测包（含 history/forecast 序列）。"""
    if not _v2_available():
        return {}
    try:
        with open(TREND_V2_FORECASTS, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _load_v2_panel() -> dict[str, dict[str, Any]]:
    """trend_panel_v2.json: role_id -> 月度真实面板（jd_share/demand_index/salary 等）。"""
    if not TREND_V2_PANEL.exists():
        return {}
    try:
        with open(TREND_V2_PANEL, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_role(job_role: str) -> ResolvedRole:
    query = str(job_role).strip().lower()
    if not query:
        raise TrendNotFoundError("job_role is empty")

    # v2 资产以 role_id 为键：先按 role_id / role_name 直接命中（含历史遗留 id）。
    if _v2_available():
        for role_id, pack in _load_v2_forecasts().items():
            if query == str(role_id).lower() or query == str(pack.get("role_name", "")).lower():
                return ResolvedRole(role_id=role_id, canonical_role=str(pack.get("role_name", role_id)))

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


# ---------------------------------------------------------------------------
# v2 信号构建（真实数据，无展示修形）
# ---------------------------------------------------------------------------

def _recent_jd_share_trend(pack: dict[str, Any], months: int = 3) -> str:
    """近 N 个月真实 jd_share 的变化方向描述。"""
    history = pack.get("history") or []
    tail = [float(row.get("jd_share") or 0.0) for row in history[-months:]]
    if len(tail) < 2:
        return f"近 {months} 个月 JD 份额数据不足，方向判断受限"
    first, last = tail[0], tail[-1]
    if last > first * 1.05 and last > first:
        return f"近 {months} 个月真实 JD 份额上升（{first:.4f} → {last:.4f}）"
    if last < first * 0.95:
        return f"近 {months} 个月真实 JD 份额下降（{first:.4f} → {last:.4f}）"
    return f"近 {months} 个月真实 JD 份额基本持平（{first:.4f} → {last:.4f}）"


def _v2_main_factors(pack: dict[str, Any]) -> list[str]:
    factors: list[str] = []
    model_used = pack.get("model_used")
    smape = pack.get("backtest_smape")
    if model_used:
        if smape is not None:
            factors.append(f"预测模型：{model_used}，回测 sMAPE {float(smape):.1%}")
        else:
            factors.append(f"预测模型：{model_used}（历史数据不足，未做回测）")
    acc = pack.get("direction_accuracy")
    if acc is not None:
        factors.append(f"方向命中率 {float(acc):.0%}（回测期涨跌方向判对比例）")
    factors.append(_recent_jd_share_trend(pack))
    if pack.get("sparse"):
        factors.append("岗位 JD 样本稀疏，预测置信度受限（如实标注，未做平滑修形）")
    return factors[:4]


def _v2_monthly_forecast(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """history 尾部 24 个月（真实值）+ forecast 12 个月（预测+80% 区间）。

    字段保持前端兼容：month + demand_index（历史真实值）/ predicted_demand_index（预测）。
    直接输出真实计算值，不做任何展示修形/平滑。
    """
    rows: list[dict[str, Any]] = []
    for item in (pack.get("history") or [])[-HISTORY_TAIL_MONTHS:]:
        rows.append({
            "month": item.get("month"),
            "demand_index": item.get("demand_index"),
            "jd_share": item.get("jd_share"),
            "salary_mid": item.get("salary_mid"),
            "low_confidence": item.get("low_confidence", False),
            "is_history": True,
        })
    for item in (pack.get("forecast") or [])[:FORECAST_MONTHS]:
        rows.append({
            "month": item.get("month"),
            "predicted_demand_index": item.get("demand_index_pred"),
            "jd_share_pred": item.get("jd_share_pred"),
            "lower80": item.get("lower80"),
            "upper80": item.get("upper80"),
            "salary_mid_pred": item.get("salary_mid_pred"),
            "is_history": False,
        })
    return rows


def _v2_signal(resolved: ResolvedRole, horizon: int) -> TrendSignal | None:
    pack = _load_v2_forecasts().get(resolved.role_id)
    if not pack:
        return None
    forecast = pack.get("forecast") or []
    if not forecast:
        return None
    horizon = max(1, min(int(horizon), len(forecast)))
    horizon_row = forecast[horizon - 1]
    evidence = _retrieve_trend_evidence(resolved.canonical_role, pack.get("trend_direction", "flat"))
    return TrendSignal(
        canonical_role=resolved.canonical_role,
        role_name_zh=role_zh(resolved.canonical_role),
        horizon_months=horizon,
        trend_direction=pack.get("trend_direction", "flat"),
        predicted_demand_index=float(horizon_row.get("demand_index_pred") or 0.0),
        confidence=float(pack.get("confidence") or 0.0),
        main_factors=_v2_main_factors(pack),
        evidence=evidence,
        monthly_forecast=_v2_monthly_forecast(pack),
        model_used=pack.get("model_used"),
        backtest_smape=pack.get("backtest_smape"),
        direction_accuracy=pack.get("direction_accuracy"),
        sparse=pack.get("sparse"),
    )


def v2_role_names() -> list[str]:
    """v2 预测覆盖的全部岗位名（trends/batch 用）。"""
    return [str(pack.get("role_name", rid)) for rid, pack in sorted(_load_v2_forecasts().items())]


# ---------------------------------------------------------------------------
# 证据（优先 v2 服务，缺文件回退旧 GDELT 索引服务）
# ---------------------------------------------------------------------------

def _retrieve_trend_evidence(role: str, direction: str, top_k: int = 5) -> list[TrendEvidence]:
    window = _evidence_window()
    try:
        res = EvidenceServiceV2.retrieve_evidence(role, window, top_k, direction)
    except Exception:
        try:
            res = EvidenceService.retrieve_evidence(role, window, top_k, direction)
        except Exception:
            return []

    fallback_date = f"{window[1]}-01"
    out: list[TrendEvidence] = []
    for ev in res.get("events", []):
        url = ev.get("url") or ""
        eid = "evt_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        published = str(ev.get("published_at") or ev.get("event_date") or fallback_date)
        summary_bits = [str(ev.get("event_type") or "news")]
        if ev.get("retrieval_score") is not None:
            summary_bits.append(f"relevance {float(ev['retrieval_score']):.2f}")
        if ev.get("source_domain"):
            summary_bits.append(str(ev["source_domain"]))
        out.append(
            TrendEvidence(
                event_id=eid,
                source=ev.get("source_domain") or ev.get("source") or "news",
                title=ev.get("title") or "行业事件",
                event_date=published[:10],
                summary=" · ".join(summary_bits),
                impact=ev.get("impact_direction") or "neutral",
                url=url or None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# 旧链路（PatchTST / 基线），仅作 v2 文件缺失时的回退
# ---------------------------------------------------------------------------

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

        if _v2_available():
            signal = _v2_signal(resolved, horizon)
            if signal is not None:
                return signal

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
