"""EvidenceServiceV2 — 基于重建的 evidence_v2 资产的证据检索。

数据源：
  - data/gold/evidence_v2_summary.json：每岗位聚合统计 + 分月 top_items
    {role_id, canonical_role, months_covered, total_items, by_type,
     top_items: {YYYY-MM: [{evidence_id, title, url, source_name,
                            published_at, event_type, relevance_score, ...}]}}
  - 月度分片 {SHARD_DIR}/{role_id}/{YYYY-MM}.jsonl（同结构逐条证据）

对外契约与旧 EvidenceService.retrieve_evidence 对齐（routes /v1/evidence 响应结构不变）：
    {role, months, direction, aggregate, events, jobs,
     candidates_total, candidates_kept, note}
  - aggregate 用真实统计：total_items / by_type / 月均条数 / 最新月 / 净信号
  - events 取时间窗内分片（缺分片回退 summary top_items），按 relevance_score 排序
  - jobs 暂无 v2 数据源：空列表 + note 说明
  - summary 文件缺失时整体回退旧 EvidenceService（GDELT 索引链路）
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

EVIDENCE_V2_SUMMARY_PATH = Path(
    os.environ.get("JOBNAV_EVIDENCE_V2_SUMMARY", "data/gold/evidence_v2_summary.json")
)
# 月度分片在仓库外（重建管线输出目录），可用环境变量覆盖。
EVIDENCE_V2_SHARD_DIR = Path(
    os.environ.get(
        "JOBNAV_EVIDENCE_V2_DIR",
        "/data/shichaojian/JNIT/processed/evidence_v2",
    )
)

# event_type → 影响方向（与旧链路 impact_direction 语义一致）
_POSITIVE_TYPES = {"funding", "product_release", "research_breakthrough", "hiring", "ai_adoption"}
_NEGATIVE_TYPES = {"layoff", "security_incident", "policy"}


def _ym(month: str) -> str:
    return str(month or "")[:7]


def _impact(event_type: str | None) -> str:
    et = str(event_type or "")
    if et in _POSITIVE_TYPES:
        return "positive"
    if et in _NEGATIVE_TYPES:
        return "negative"
    return "neutral"


def latest_shard_month() -> str | None:
    """分片目录中观测到的最新月份（YYYY-MM），目录不可读或无分片返回 None。

    供趋势证据窗口动态滚动用：月度 cron 每新增一个分片，窗口自动前移。
    """
    try:
        latest: str | None = None
        for role_dir in EVIDENCE_V2_SHARD_DIR.iterdir():
            if not role_dir.is_dir():
                continue
            for shard in role_dir.glob("*.jsonl"):
                m = _ym(shard.stem)
                if len(m) == 7 and (latest is None or m > latest):
                    latest = m
        return latest
    except OSError:
        return None


@lru_cache(maxsize=1)
def _load_summary() -> dict[str, dict[str, Any]]:
    """canonical_role(lower) 与 role_id 双索引，方便两种入参都能解析。"""
    if not EVIDENCE_V2_SUMMARY_PATH.exists():
        return {}
    try:
        rows = json.loads(EVIDENCE_V2_SUMMARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        index[str(row.get("canonical_role", "")).lower()] = row
        index[str(row.get("role_id", "")).lower()] = row
    return index


class EvidenceServiceV2:
    @staticmethod
    def is_available() -> bool:
        return bool(_load_summary())

    # ---- 分片读取 ----
    @staticmethod
    def _load_shard_items(role_id: str, months: tuple[str, str]) -> list[dict[str, Any]]:
        d = EVIDENCE_V2_SHARD_DIR / str(role_id)
        if not d.is_dir():
            return []
        lo, hi = _ym(months[0]), _ym(months[1])
        items: list[dict[str, Any]] = []
        for shard in sorted(d.glob("*.jsonl")):
            if not (lo <= _ym(shard.stem) <= hi):
                continue
            try:
                with open(shard, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            items.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
        return items

    @staticmethod
    def _summary_items(row: dict[str, Any], months: tuple[str, str]) -> list[dict[str, Any]]:
        lo, hi = _ym(months[0]), _ym(months[1])
        items: list[dict[str, Any]] = []
        for month, month_items in (row.get("top_items") or {}).items():
            if lo <= _ym(month) <= hi:
                items.extend(month_items or [])
        return items

    # ---- 聚合统计（真实数据） ----
    @staticmethod
    def _aggregate(row: dict[str, Any]) -> dict[str, Any]:
        months_covered = list(row.get("months_covered") or [])
        total = int(row.get("total_items") or 0)
        by_type = dict(row.get("by_type") or {})
        opportunity = sum(c for t, c in by_type.items() if t in _POSITIVE_TYPES)
        risk = sum(c for t, c in by_type.items() if t in _NEGATIVE_TYPES)
        net_signal = "positive" if opportunity > risk else "negative" if risk > opportunity else "mixed"
        agg: dict[str, Any] = {
            "article_count": total,
            "by_type": by_type,
            "months_covered": months_covered,
            "latest_month": months_covered[-1] if months_covered else None,
            "avg_items_per_month": round(total / max(len(months_covered), 1), 2),
            "opportunity_events": opportunity,
            "risk_events": risk,
            "net_signal": net_signal,
        }
        # 相关性均值：summary top_items 的 relevance_score 平均（真实统计）
        scores = [
            float(item.get("relevance_score") or 0.0)
            for items in (row.get("top_items") or {}).values()
            for item in (items or [])
            if item.get("relevance_score") is not None
        ]
        if scores:
            agg["mean_relevance"] = round(sum(scores) / len(scores), 3)
        return agg

    # ---- 主入口（契约同旧 EvidenceService.retrieve_evidence） ----
    @classmethod
    def retrieve_evidence(cls, role: str, months: tuple[str, str],
                          top_k: int = 5, direction: Optional[str] = None) -> dict:
        row = _load_summary().get(str(role).lower())
        if row is None:
            # v2 资产缺失（或岗位未覆盖）：回退旧 GDELT 索引链路
            from app.services.evidence import EvidenceService

            return EvidenceService.retrieve_evidence(role, months, top_k, direction)

        role_id = str(row.get("role_id", role))
        shard_items = cls._load_shard_items(role_id, months)
        pool = shard_items if shard_items else cls._summary_items(row, months)
        source = "月度分片" if shard_items else "evidence_v2_summary top_items"

        seen_urls: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in sorted(
            pool,
            key=lambda it: float(it.get("relevance_score") or 0.0),
            reverse=True,
        ):
            url = item.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(item)

        events = []
        for item in deduped[:top_k]:
            score = item.get("relevance_score")
            events.append({
                "evidence_type": "news_event",
                "url": item.get("url"),
                "source_domain": item.get("source_name"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "tone": None,
                "themes": item.get("anchor_hits") or [],
                "match_weight": score,
                "event_type": item.get("event_type") or "general",
                "impact_direction": _impact(item.get("event_type")),
                "is_counter_signal": False,
                "direction_align": None,
                "title_quality": None,
                "role_affinity": None,
                "evidence_strength": "strong" if float(score or 0) >= 0.5 else "weak",
                "retrieval_score": score,
            })

        months_covered = list(row.get("months_covered") or [])
        note = (
            f"evidence v2：数据来自 {source}，覆盖 {months_covered[0] if months_covered else 'N/A'}"
            f"~{months_covered[-1] if months_covered else 'N/A'} 共 {row.get('total_items', 0)} 条，"
            f"月均 {cls._aggregate(row)['avg_items_per_month']} 条；"
            f"v2 暂无在招 JD 证据（jobs 为空列表）"
        )
        return {
            "role": row.get("canonical_role", role),
            "months": list(months),
            "direction": direction,
            "aggregate": cls._aggregate(row),
            "events": events,
            "jobs": [],
            "candidates_total": int(row.get("total_items") or 0),
            "candidates_kept": len(events),
            "note": note,
        }
