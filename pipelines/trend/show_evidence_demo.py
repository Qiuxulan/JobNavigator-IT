"""一键查看某角色的完整证据链效果：PatchTST 预测 + 聚合 + 事件 + JD。

用法：
  python -m pipelines.trend.show_evidence_demo --role "AI Engineer"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.evidence import EvidenceService
from pipelines.trend._trend_source import EVENT_WINDOW

DIR_CN = {"up": "↑上升", "down": "↓下降", "flat": "→持平", "stable": "→持平"}
MAJOR_EVENTS_PATH = Path("data/gold/major_industry_events_v1.json")


def _load_major_events(role: str, direction: str) -> list[dict]:
    if not MAJOR_EVENTS_PATH.exists():
        return []
    import json
    data = json.loads(MAJOR_EVENTS_PATH.read_text(encoding="utf-8"))
    catalog = {e["event_id"]: e for e in data.get("event_catalog", [])}
    lookup_direction = "flat" if direction == "stable" else direction
    row = next((r for r in data.get("role_trend_evidence", [])
                if r.get("canonical_role") == role and r.get("trend_direction") == lookup_direction), None)
    if not row:
        return []
    return [catalog[eid] for eid in row.get("major_event_ids", []) if eid in catalog]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="AI Engineer")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    try:
        from app.services.trend_predictor import get_milestones
        ms = get_milestones(args.role)
    except Exception as e:
        print(f"[!] 取 PatchTST 里程碑失败: {e}")
        return
    role = ms["canonical_role"]

    print("=" * 70)
    print(f"角色: {role}")
    print("=" * 70)
    print("\n【PatchTST 趋势预测(里程碑)】")
    near_dir = "flat"
    for i, m in enumerate(ms["milestones"]):
        d = m.get("trend_direction", "flat")
        if i == 0:
            near_dir = d
        print(f"  {m.get('label'):>9}  {m.get('month')}  {DIR_CN.get(d, d):6s} "
              f"指数 {m.get('predicted_demand_index'):.3f}  置信 {m.get('confidence', 0):.0%}")

    # 用近期(3个月)方向检索证据
    res = EvidenceService.retrieve_evidence(role, EVENT_WINDOW, args.top_k, near_dir)
    agg = res.get("aggregate")
    print(f"\n【证据(按近期方向 {DIR_CN.get(near_dir)} 检索, 窗口 {EVENT_WINDOW})】")
    if agg:
        print(f"  聚合: 相关新闻 {agg['article_count']} 篇 | 平均情绪 {agg['mean_tone']} | "
              f"机会 {agg['opportunity_events']} / 风险 {agg['risk_events']} | 净信号 {agg['net_signal']}")
    print(f"\n  事件证据 TopK ({len(res['events'])} 条，strong=强相关 / weak=补充):")
    for e in res["events"]:
        strength = e.get("evidence_strength", "strong")
        print(f"    [{strength:6s}] [{e['event_type']:16s}] {e['impact_direction']:8s} tone={e['tone']:>5} "
              f"{(e['title'] or '')[:46]}")
        print(f"       {e['url']}")
    print(f"\n  JD 在招 ({len(res['jobs'])} 条):")
    for j in res["jobs"][:3]:
        sal = f"{int(j['salary_mid'])}" if j.get("salary_mid") else "NA"
        print(f"    {(j.get('title') or '')[:36]:36s} @ {(j.get('company_name') or '')[:22]:22s} 薪资 {sal}")

    major_events = _load_major_events(role, near_dir)
    print(f"\n  重大行业事件 ({len(major_events)} 条，公开来源):")
    for ev in major_events[:5]:
        print(f"    [{ev.get('impact_direction','mixed'):8s}] {ev.get('event_date')} "
              f"{(ev.get('title') or '')[:58]}")
        print(f"       {ev.get('source_url')}")
    if res.get("note"):
        print(f"\n  note: {res['note']}")
    print()


if __name__ == "__main__":
    main()
