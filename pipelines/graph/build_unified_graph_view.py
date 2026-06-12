"""融合视图：队友的「岗位-技能-资源」图谱 + 本模块的「事件证据」一张图。

复用 export_graph_interactive_v2 的 build_role_graph 与渲染器 _build_html，
把 event_graph_v1.json 里指向该岗位的 AFFECTS 事件，作为新节点挂到 job 节点上。
事件按影响方向着色（绿=正面/红=负面/灰=中性）。

用法：
  python pipelines/graph/build_unified_graph_view.py --role "Machine Learning Engineer"
  python pipelines/graph/build_unified_graph_view.py --role-id role_000
  -> reports/<role_id>_unified_graph.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.graph.export_graph_interactive_v2 import (  # noqa: E402
    COLORS, REPORT_DIR, _build_html, _node_key, build_full_graph, build_role_graph,
)

EVENT_GRAPH = Path("data/processed/event_graph_v1.json")
TAXONOMY = Path("data/gold/role_taxonomy.json")
EVENT_COLOR = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#9ca3af"}


def _resolve_role_id(role: str | None, role_id: str | None) -> tuple[str, str]:
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    by_id = {t["role_id"]: t["canonical_role"] for t in tax}
    by_name = {t["canonical_role"].lower(): t["role_id"] for t in tax}
    if role_id:
        return role_id, by_id.get(role_id, role_id)
    if role and role.lower() in by_name:
        rid = by_name[role.lower()]
        return rid, by_id[rid]
    raise SystemExit(f"找不到角色：{role or role_id}")


def _attach_events(data: dict, only_role_id: str | None) -> int:
    """把 event_graph_v1.json 的 AFFECTS 事件挂到对应 job 节点。返回挂载数。"""
    g = json.loads(EVENT_GRAPH.read_text(encoding="utf-8"))
    pj = {n["node_id"]: n["payload_json"] for n in g["nodes"]}
    job_ids = {n["meta"].get("role_id") for n in data["nodes"] if n.get("kind") == "job"}
    existing = {n["id"] for n in data["nodes"]}
    added = 0
    for e in g["edges"]:
        rid = e["dst_id"]
        if only_role_id and rid != only_role_id:
            continue
        if rid not in job_ids:                 # 该岗位不在当前图里，跳过
            continue
        eid = e["src_id"]
        imp = e["meta_json"].get("impact_direction", "neutral")
        col = EVENT_COLOR.get(imp, "#9ca3af")
        ekey = _node_key("event", eid)
        if ekey not in existing:
            existing.add(ekey)
            p = pj.get(eid, {})
            data["nodes"].append({
                "id": ekey,
                "label": (p.get("title") or "事件")[:36],
                "kind": "event",
                "color": col,
                "payload": p,
                "meta": {"event_type": p.get("event_type"), "tone": p.get("tone"),
                         "source": p.get("source_domain")},
            })
            added += 1
        data["edges"].append({
            "source": ekey,
            "target": _node_key("job", rid),
            "label": f"affects/{e['meta_json'].get('event_type', '')}",
            "color": col,
            "colorDim": "rgba(71,85,105,0.3)",
            "length": 150,
        })
    data.setdefault("summaryLines", []).append(f"事件证据: 挂载 {added} 条 AFFECTS")
    data.setdefault("legend", []).extend([
        {"label": "事件·正面", "color": EVENT_COLOR["positive"]},
        {"label": "事件·负面", "color": EVENT_COLOR["negative"]},
        {"label": "事件·中性", "color": EVENT_COLOR["neutral"]},
    ])
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="全量所有岗位一张大图")
    ap.add_argument("--role", default=None, help="canonical_role 名称")
    ap.add_argument("--role-id", default=None, help="role_000 形式")
    ap.add_argument("--top-n", type=int, default=12)
    ap.add_argument("--prereq-depth", type=int, default=1)
    args = ap.parse_args()

    if args.full:
        data = build_full_graph(include_resources=False, top_n=args.top_n)
        added = _attach_events(data, only_role_id=None)
        html = _build_html("全岗位 · 技能图谱 + 事件证据链", data)
        out = REPORT_DIR / "full_unified_graph.html"
        out.write_text(html, encoding="utf-8")
        print(f"[ok] 全量: {len(data['nodes']) - added} 技能/岗位节点 + 事件 {added} -> {out}")
        return

    role_id, role_name = _resolve_role_id(args.role, args.role_id)
    data = build_role_graph(role_id, prereq_depth=args.prereq_depth,
                            resource_limit=1, top_n=args.top_n)
    added = _attach_events(data, only_role_id=role_id)
    html = _build_html(f"{role_name} · 技能图谱 + 事件证据链", data)
    out = REPORT_DIR / f"{role_id}_unified_graph.html"
    out.write_text(html, encoding="utf-8")
    print(f"[ok] {role_name}: 技能侧 {len(data['nodes']) - added} 节点 + 事件 {added} -> {out}")


if __name__ == "__main__":
    main()
