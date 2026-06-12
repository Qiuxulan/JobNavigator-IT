"""统计全量索引里"有用事件"的规模：过四重约束闸门的相关事件有多少。

复用 app/services/evidence.py 的 _is_relevant / _strong_skill_terms，
对 data/processed/evidence_index/events/ 全量流式统计。

用法：python -m pipelines.trend.count_useful_events
"""

from __future__ import annotations

import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.evidence import _is_relevant, _strong_skill_terms

EVENTS_GLOB = "data/processed/evidence_index/events/*/*.jsonl"


def main() -> None:
    t0 = time.time()
    total = kept = strong = 0
    by_month_total: Counter = Counter()
    by_month_kept: Counter = Counter()
    by_bucket_kept: Counter = Counter()
    by_role_kept: Counter = Counter()

    files = glob.glob(EVENTS_GLOB)
    print(f"扫描 {len(files)} 个分片 ...", flush=True)
    for fp in files:
        role = Path(fp).parent.name
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                mo = ev.get("month", "?")
                by_month_total[mo] += 1
                if _is_relevant(ev):
                    kept += 1
                    by_month_kept[mo] += 1
                    by_bucket_kept[ev.get("bucket_name", "?")] += 1
                    by_role_kept[role] += 1
                    terms = [str(t).lower() for t in (ev.get("matched_terms") or [])]
                    if _strong_skill_terms(terms):
                        strong += 1

    print("\n========== 有用事件统计 ==========")
    print(f"全量事件总数        : {total:,}")
    print(f"过四重约束(相关事件): {kept:,}  ({100*kept/max(total,1):.1f}%)")
    print(f"  其中靠真技能词命中: {strong:,}  (高置信子集)")
    print(f"  其中靠主题共现保留: {kept-strong:,}")
    print("\n按月份(相关/总):")
    for mo in sorted(by_month_total):
        print(f"  {mo}: {by_month_kept[mo]:,} / {by_month_total[mo]:,}")
    print("\n相关事件 按 bucket:")
    for b, c in by_bucket_kept.most_common():
        print(f"  {c:,}  {b}")
    print("\n相关事件最多的角色 top10:")
    for r, c in by_role_kept.most_common(10):
        print(f"  {c:,}  {r}")
    print(f"\n[done] 用时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
