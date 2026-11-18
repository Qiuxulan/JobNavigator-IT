"""技能趋势 v3 API：消费 data/gold/skill_trend_panel_v3.json 月度面板。

与旧 /v1/trends（岗位维度）并存，本模块提供技能维度的真实面板数据：
- GET /v1/trends/skills           新兴/上升/衰退技能榜 + 状态分布
- GET /v1/trends/skills/{skill}   单技能完整月度序列 + 预测 + 薪资/远程比例

面板文件可能由流水线并发重写：读取时校验 mtime，JSON 解析失败短暂等待后重试。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

PANEL_PATH = Path(
    os.environ.get("JOBNAV_SKILL_TREND_PANEL_V3", "data/gold/skill_trend_panel_v4_chronos.json")
)
PANEL_FALLBACK_PATH = Path("data/gold/skill_trend_panel_v3.json")
SKILL_VOCAB_PATH = Path("data/gold/skill_vocab_v2.json")

router = APIRouter(prefix="/v1/trends")

_SPARK_MONTHS = 12
_TOP_N = 20

_panel_cache: dict[str, Any] = {"mtime": None, "data": None}
_vocab_cache: dict[str, Any] = {"mtime": None, "data": None}


def _load_json_retry(path: Path, attempts: int = 3, wait_s: float = 2.0) -> Any:
    """读取可能被并发写入的 JSON 文件，解析失败时等待重试。"""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(wait_s)
    raise last_exc  # type: ignore[misc]


def _load_panel() -> dict[str, Any]:
    path = PANEL_PATH if PANEL_PATH.exists() else PANEL_FALLBACK_PATH
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"skill trend panel not found: {path}") from exc
    if _panel_cache["mtime"] != mtime or _panel_cache["data"] is None or _panel_cache.get("path") != path:
        data = _load_json_retry(path, attempts=4, wait_s=2.0)
        if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
            raise HTTPException(status_code=500, detail="skill trend panel malformed")
        _panel_cache["mtime"] = mtime
        _panel_cache["path"] = path
        _panel_cache["data"] = data
    return _panel_cache["data"]


def _load_vocab_names() -> dict[str, str]:
    """skill_slug -> 展示名（skill_vocab_v2 id_to_name，无中文名，仅做大小写/格式美化）。"""
    try:
        mtime = SKILL_VOCAB_PATH.stat().st_mtime
    except FileNotFoundError:
        return {}
    if _vocab_cache["mtime"] != mtime or _vocab_cache["data"] is None:
        try:
            data = json.loads(SKILL_VOCAB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        id_to_name = data.get("id_to_name") if isinstance(data, dict) else None
        _vocab_cache["mtime"] = mtime
        _vocab_cache["data"] = id_to_name if isinstance(id_to_name, dict) else {}
    return _vocab_cache["data"]


def _display_name(skill: str) -> str:
    name = _load_vocab_names().get(skill)
    if name:
        return str(name)
    return skill.replace("-", " ").replace("/", " / ").title()


def _sparkline(monthly: list[dict[str, Any]], months: int = _SPARK_MONTHS) -> list[dict[str, Any]]:
    """最近 N 个月 share 序列；share 为 null 的月份跳过（低覆盖月容错）。"""
    tail = monthly[-months:]
    return [
        {"month": row.get("month"), "share": row.get("share")}
        for row in tail
        if row.get("share") is not None
    ]


def _item(skill: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill": skill,
        "name": _display_name(skill),
        "status": entry.get("status"),
        "momentum_3m": entry.get("momentum_3m"),
        "yoy": entry.get("yoy"),
        "spark": _sparkline(entry.get("monthly") or []),
    }


_MIN_BASE = 30          # 前 3 个月至少出现这么多次才参与上升/衰退排名，避免“从 1 条涨到 5 条 = +400%”
_MIN_MONTH_TOTAL = 1000  # 当月 JD 总量低于此值视为样本不足，不参与计算


def _robust_momentum(panel: dict[str, Any], entry: dict[str, Any]) -> tuple[float | None, int]:
    """最近 3 个样本充足月 vs 之前 3 个样本充足月的份额变化（比例），返回 (变化, 基期出现次数)。"""
    totals = panel.get("total_jd_by_month") or {}
    rows = [r for r in entry.get("monthly") or []
            if totals.get(r.get("month"), 0) >= _MIN_MONTH_TOTAL and r.get("share") is not None]
    if len(rows) < 6:
        return None, 0
    recent, prev = rows[-3:], rows[-6:-3]
    base = sum(int(r.get("count") or 0) for r in prev)
    prev_share = sum(r["share"] for r in prev) / 3
    if base < _MIN_BASE or prev_share <= 0:
        return None, base
    return round(sum(r["share"] for r in recent) / 3 / prev_share - 1, 4), base


def _ranked(panel: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """新兴：基期很少、近期明显出现；上升/衰退：基期样本充足时的份额变化。三张榜互不重复。"""
    rows = []
    for skill, entry in (panel.get("skills") or {}).items():
        mom, base = _robust_momentum(panel, entry)
        status = entry.get("status")
        if kind == "emerging":
            if status == "emerging":
                rows.append((entry.get("momentum_3m") or 0, skill, entry, None))
        elif mom is not None and status != "emerging":
            if (kind == "rising" and mom >= 0.1) or (kind == "declining" and mom <= -0.1):
                rows.append((mom, skill, entry, mom))
    rows.sort(key=lambda x: x[0], reverse=kind != "declining")
    out = []
    for _, skill, entry, mom in rows[:_TOP_N]:
        item = _item(skill, entry)
        if mom is not None:
            item["momentum_3m"] = mom
        out.append(item)
    return out


@router.get("/skills")
def skill_trends_overview() -> dict[str, Any]:
    panel = _load_panel()
    skills = panel.get("skills") or {}

    status_distribution: dict[str, int] = {}
    for entry in skills.values():
        status = str(entry.get("status") or "unknown")
        status_distribution[status] = status_distribution.get(status, 0) + 1

    window = panel.get("window") or {}
    months = panel.get("months") or []
    return {
        "generated_at": panel.get("generated_at"),
        "analysis_end": panel.get("analysis_end") or (months[-1] if months else None),
        "window": window,
        "months": months,
        "total_skills": len(skills),
        "status_distribution": status_distribution,
        "emerging": _ranked(panel, "emerging"),
        "rising": _ranked(panel, "rising"),
        "declining": _ranked(panel, "declining"),
        "momentum_unit": "ratio",
    }


@router.get("/skills/{skill}")
def skill_trend_detail(skill: str) -> dict[str, Any]:
    panel = _load_panel()
    skills = panel.get("skills") or {}

    entry = skills.get(skill)
    if entry is None:
        lowered = skill.strip().lower()
        for key, value in skills.items():
            if key.lower() == lowered:
                entry = value
                skill = key
                break
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown skill: {skill}")

    forecast = entry.get("forecast")
    return {
        "skill": skill,
        "name": _display_name(skill),
        "status": entry.get("status"),
        "momentum_3m": entry.get("momentum_3m"),
        "yoy": entry.get("yoy"),
        "trend_slope": entry.get("trend_slope"),
        "volatility": entry.get("volatility"),
        "forecast": forecast if isinstance(forecast, dict) else None,
        "monthly": entry.get("monthly") or [],
        "generated_at": panel.get("generated_at"),
        "analysis_end": panel.get("analysis_end"),
    }
