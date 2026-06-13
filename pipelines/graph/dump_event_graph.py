"""按岗位分组打印事件图谱：每个岗位 + 趋势方向 + 挂上的所有事件(极性/类型/标题/url)。

用于人工核对"岗位对应的事件是否正确"。
用法：python -m pipelines.graph.dump_event_graph         # 简版(极性+类型+标题)
      python -m pipelines.graph.dump_event_graph --url   # 带 url
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

GRAPH = Path("data/processed/event_graph_v1.json")
TAXONOMY = Path("data/gold/role_taxonomy.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="store_true", help="同时打印事件 url")
    args = ap.parse_args()

    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    tax = {t["role_id"]: t["canonical_role"]
           for t in json.loads(TAXONOMY.read_text(encoding="utf-8"))}
    nd = {n["node_id"]: n["payload_json"] for n in g["nodes"]}

    by_role: dict[str, list] = collections.defaultdict(list)
    for e in g["edges"]:
        by_role[e["dst_id"]].append(e)

    print(f"岗位 {len(by_role)} | 事件节点 {len(g['nodes'])} | AFFECTS 边 {len(g['edges'])}\n")
    for rid in sorted(by_role, key=lambda r: tax.get(r, r)):
        edges = by_role[rid]
        dirs = sorted({e["meta_json"].get("trend_direction") for e in edges})
        # 该岗位事件极性小计
        pol = collections.Counter(
            e["meta_json"].get("trend_impact_direction") or e["meta_json"].get("impact_direction")
            for e in edges
        )
        print(f"【{tax.get(rid, rid)}】 方向={','.join(str(d) for d in dirs)} | {len(edges)}条 "
              f"(正{pol.get('positive',0)}/负{pol.get('negative',0)}/中{pol.get('neutral',0)})")
        for e in edges:
            m = e["meta_json"]
            p = nd.get(e["src_id"], {})
            title = (p.get("title") or "")[:55]
            layer = m.get("source_layer", "rag_event")
            trend_imp = m.get("trend_impact_direction") or m.get("impact_direction", "?")
            raw_imp = m.get("impact_direction", "?")
            line = f"   {trend_imp:8} raw={raw_imp:8} [{m.get('event_type','?'):22}] {layer:18s} {title}"
            if args.url:
                line += f"\n        {p.get('url')}"
            print(line)
        print()


if __name__ == "__main__":
    main()
