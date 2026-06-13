"""C 模块 ③/⑤：批量产出趋势证据文件 + 评估报告（完整版，复用 EvidenceService）。

对 B 的每条趋势结论，调用统一检索核心取「聚合信号 + 干净样本事件 + JD 证据」，
按契约 §5 写 data/gold/trend_evidence_v1.jsonl，并生成评估报告。

与运行时接口 retrieve_evidence 共用同一个检索核心，不重复实现检索逻辑。

用法：
  python -m pipelines.trend.build_trend_evidence
  python pipelines/trend/build_trend_evidence.py
前置：先跑 build_evidence_index.py 生成索引。
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.evidence import EvidenceService
from pipelines.trend._trend_source import EVENT_WINDOW, load_conclusions

TAXONOMY_PATH = Path("data/gold/role_taxonomy.json")
OUT_JSONL = Path("data/gold/trend_evidence_v1.jsonl")
OUT_JSONL_MONTHLY = Path("data/gold/trend_evidence_monthly_v1.jsonl")
OUT_REPORT = Path("reports/trend_explanation_eval_v1.md")
MAJOR_EVENTS_PATH = Path("data/gold/major_industry_events_v1.json")

DIRECTION_NORMALIZE = {"up": "up", "flat": "stable", "stable": "stable", "down": "down"}
DIRECTION_CN = {"up": "上升", "stable": "持平", "down": "下降"}
TOPK = 5


def _load_major_events() -> tuple[dict[str, dict], dict[tuple[str, str], list[str]]]:
    if not MAJOR_EVENTS_PATH.exists():
        return {}, {}
    data = json.loads(MAJOR_EVENTS_PATH.read_text(encoding="utf-8"))
    catalog = {e["event_id"]: e for e in data.get("event_catalog", [])}
    mapping = {
        (r["canonical_role"], r["trend_direction"]): r.get("major_event_ids", [])
        for r in data.get("role_trend_evidence", [])
    }
    return catalog, mapping


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _make_evidence_topk(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        out.append({
            "source_name": "GDELT",
            "source_url": ev.get("url"),
            "title": ev.get("title"),
            "published_at": ev.get("published_at"),
            "evidence_text": f"{ev.get('source_domain', '')} · {ev.get('event_type', '')} · tone {ev.get('tone')}",
            "retrieval_score": ev.get("retrieval_score"),
            "evidence_type": ev.get("event_type"),
            "impact_direction": ev.get("impact_direction"),
            "evidence_strength": ev.get("evidence_strength", "strong"),
        })
    return out


def _make_jd_evidence(jobs: list[dict]) -> list[dict]:
    out = []
    for j in jobs:
        out.append({
            "evidence_type": "job_posting",
            "company_name": j.get("company_name"),
            "title": j.get("title"),
            "post_date": j.get("post_date"),
            "salary_mid": j.get("salary_mid"),
            "job_url": j.get("job_url"),
            "out_of_range": j.get("out_of_range"),
        })
    return out


def _make_major_events(role: str, raw_direction: str, role_family: str | None,
                       catalog: dict[str, dict],
                       mapping: dict[tuple[str, str], list[str]]) -> list[dict]:
    lookup_direction = "flat" if raw_direction == "stable" else raw_direction
    ids = mapping.get((role, lookup_direction), [])
    if not ids and role_family:
        ids = [
            event_id
            for event_id, ev in sorted(
                catalog.items(),
                key=lambda item: float(item[1].get("event_importance") or 0.0),
                reverse=True,
            )
            if role_family in (ev.get("categories") or [])
            and lookup_direction in (ev.get("trend_fit") or [])
        ][:5]
    out = []
    for event_id in ids:
        ev = catalog.get(event_id)
        if not ev:
            continue
        out.append({
            "event_id": event_id,
            "title": ev.get("title"),
            "event_date": ev.get("event_date"),
            "source_name": ev.get("source_name"),
            "source_url": ev.get("source_url"),
            "event_type": ev.get("event_type"),
            "impact_direction": ev.get("impact_direction"),
            "event_importance": ev.get("event_importance"),
            "summary_zh": ev.get("summary_zh"),
        })
    return out


def _risk_notes(direction: str, agg: dict | None, events: list[dict]) -> list[str]:
    notes = ["证据相关性为近似（GDELT 无正文，基于技能白名单+主题共现约束）。"]
    if agg:
        net = agg.get("net_signal")
        if direction == "up" and net == "negative":
            notes.append("聚合净信号偏负，与上升结论不一致，需谨慎。")
        elif direction == "down" and net == "positive":
            notes.append("聚合净信号偏正，与下降结论不一致，需谨慎。")
        if agg.get("article_count", 0) < 20:
            notes.append(f"本月相关新闻仅 {agg.get('article_count')} 篇，样本偏小。")
    weak_count = sum(1 for ev in events if ev.get("evidence_strength") == "weak")
    if weak_count:
        notes.append(f"含 {weak_count} 条弱相关补充事件；强结论以 aggregate/JD 为准。")
    if not events:
        notes.append("无通过四重约束的干净事件样本，趋势佐证以 aggregate 为准。")
    notes.append("证据多为英文新闻源，中文本土市场需补充。")
    return notes


def main(granularity: str = "milestone") -> None:
    conclusions = load_conclusions(granularity=granularity)   # 里程碑 或 逐月全量
    tax = {t["canonical_role"]: t for t in json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))}
    out_path = OUT_JSONL_MONTHLY if granularity == "monthly" else OUT_JSONL

    t0 = time.time()
    rows_out = []
    ev_cache: dict = {}                         # (role,方向)->检索结果; 逐月模式避免重复检索
    major_catalog, major_mapping = _load_major_events()
    stats = {"total": 0, "with_events": 0, "with_aggregate": 0,
             "aligned": 0, "event_counts": [], "roles": set(), "roles_with_events": set()}

    n = len(conclusions)
    src = conclusions[0]["source"] if conclusions else "?"
    print(f"[trend_evidence] {n} 条结论(来源={src})，证据窗口 {EVENT_WINDOW}，逐个检索 ...", flush=True)
    for i, row in enumerate(conclusions, 1):
        role = row["canonical_role"]
        month = row["month"]                   # 预测月份(可能在未来)
        horizon = int(row.get("horizon_months", 3))
        horizon_label = row.get("horizon_label", f"{horizon}_month")
        raw_dir = row.get("trend_direction", "flat")
        direction = DIRECTION_NORMALIZE.get(raw_dir, "stable")
        idx = float(row.get("predicted_demand_index", 0.0))
        conf = float(row.get("confidence", 0.0))
        factors = row.get("factors", [])
        info = tax.get(role, {})

        if i % 50 == 0 or i == n:
            print(f"  ... {i}/{n}", flush=True)

        # 预测在未来无新闻 -> 证据从最近真实事件窗口取；同(角色,方向)缓存复用
        ck = (role, raw_dir)
        res = ev_cache.get(ck)
        if res is None:
            res = EvidenceService.retrieve_evidence(role, EVENT_WINDOW, TOPK, raw_dir)
            ev_cache[ck] = res
        events = res.get("events", [])
        agg = res.get("aggregate")
        major_events = _make_major_events(role, raw_dir, info.get("category"), major_catalog, major_mapping)

        conclusion = (f"{role} 预计未来 {horizon} 个月需求{DIRECTION_CN[direction]}"
                      f"（预测月 {month}，需求指数 {idx:.2f}，置信度 {conf:.0%}）。")
        if agg:
            conclusion += f" 近 6 个月相关新闻 {agg['article_count']} 篇，净信号 {agg['net_signal']}。"

        rows_out.append({
            "trend_id": f"{_slug(role)}_{horizon_label}",
            "role_family": info.get("category"),
            "canonical_role": role,
            "skill_name": None,
            "month": month,
            "horizon_months": horizon,
            "evidence_window": list(EVENT_WINDOW),
            "conclusion": conclusion,
            "trend_direction": direction,
            "trend_direction_raw": raw_dir,
            "predicted_demand_index": round(idx, 4),
            "confidence": round(conf, 4),
            "main_factors": factors,
            "aggregate": agg,
            "evidence_topk": _make_evidence_topk(events),
            "major_industry_events": major_events,
            "jd_evidence": _make_jd_evidence(res.get("jobs", [])),
            "risk_notes": _risk_notes(direction, agg, events),
            "model_version": "trend-evidence-v2-constrained",
        })

        # 统计
        stats["total"] += 1
        stats["roles"].add(role)
        if agg:
            stats["with_aggregate"] += 1
        if events:
            stats["with_events"] += 1
            stats["roles_with_events"].add(role)
            stats["event_counts"].append(len(events))
            # 方向对齐：聚合净信号方向与结论一致
            if agg and ((direction == "up" and agg["net_signal"] == "positive")
                        or (direction == "down" and agg["net_signal"] == "negative")
                        or (direction == "stable")):
                stats["aligned"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if granularity != "monthly":
        _write_report(stats, rows_out)         # 评估报告只为里程碑版生成
    cov = stats["with_events"] / stats["total"] if stats["total"] else 0
    print(f"[ok] {len(rows_out)} 行 -> {out_path}")
    print(f"[ok] 报告 -> {OUT_REPORT}")
    print(f"[stat] 含干净事件: {stats['with_events']}/{stats['total']} = {cov:.1%} | "
          f"含聚合: {stats['with_aggregate']}/{stats['total']} | 用时 {time.time()-t0:.1f}s")


def _write_report(stats: dict, rows_out: list[dict]) -> None:
    total = stats["total"]
    we = stats["with_events"]
    wa = stats["with_aggregate"]
    cov = we / total if total else 0
    agg_cov = wa / total if total else 0
    counts = stats["event_counts"]
    avg_ev = sum(counts) / len(counts) if counts else 0

    L = []
    L.append("# 趋势证据评估报告 (trend_explanation_eval_v1)\n")
    L.append(f"- 生成：{datetime.now().isoformat(timespec='seconds')}")
    L.append("- 模块：C（证据检索 RAG，完整版四重约束 + 聚合信号）")
    L.append("- 输出：`data/gold/trend_evidence_v1.jsonl`\n")
    L.append("## 1. 核心指标\n")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 趋势结论总数 | {total} |")
    L.append(f"| **含聚合信号(aggregate)覆盖率** | **{agg_cov:.1%}**（{wa}/{total}） |")
    L.append(f"| 含干净事件样本覆盖率 | {cov:.1%}（{we}/{total}） |")
    L.append(f"| 平均干净事件数/条 | {avg_ev:.2f}（TopK={TOPK}） |")
    L.append(f"| 聚合方向与结论一致 | {stats['aligned']}/{total} |")
    L.append(f"| 覆盖角色 | {len(stats['roles'])} |\n")
    L.append("## 2. 两层证据说明\n")
    L.append("**主力 = 聚合信号**：每条结论几乎都有 aggregate（篇数/情绪/机会·风险/净信号），"
             "由多篇文档统计而来，对单篇噪音稳健，是趋势佐证主力，覆盖率远高于干净事件。\n")
    L.append("**佐证 = 干净事件样本**：过四重约束（技能白名单+主题共现+域名黑名单+方向一致）才入选，"
             "少而精，标注“相关性近似”。\n")
    L.append("## 3. 数据质量与口径\n")
    L.append("1. GDELT 无标题/正文，匹配多为关键词/URL 伪词；本模块用约束换精度，召回不足由聚合兜底。")
    L.append("2. 方向归一：B 的 `flat` → 契约 `stable`，原值存 `trend_direction_raw`。")
    L.append("3. 粒度：按 `canonical_role` 出行，`role_family`=taxonomy.category，D 可聚合。")
    L.append("4. JD 证据 `job_url` 源数据为空，降级为存在性证据（公司/标题/薪资）。\n")
    sample = next((r for r in rows_out if r["evidence_topk"]), rows_out[0] if rows_out else None)
    if sample:
        L.append("## 4. 抽检样例\n")
        slim = dict(sample)
        slim["evidence_topk"] = slim["evidence_topk"][:2]
        slim["jd_evidence"] = slim["jd_evidence"][:1]
        L.append("```json")
        L.append(json.dumps(slim, ensure_ascii=False, indent=2))
        L.append("```")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly", action="store_true",
                    help="逐月全量(69×36=2484行,带缓存,出 trend_evidence_monthly_v1.jsonl)；默认里程碑(345行)")
    args = ap.parse_args()
    main(granularity="monthly" if args.monthly else "milestone")
