"""把 event_graph_v1.json 渲染成可双击打开的交互式 HTML（vis-network，数据内联）。

用法：
  python pipelines/graph/build_event_graph_view.py
  -> reports/event_graph_view.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 统一着色：单一来源，与组员3/融合图共用
from app.services.evidence_color import (  # noqa: E402
    COLOR, TREND_EDGE, edge_color, event_polarity, trend_border,
)

GRAPH = Path("data/processed/event_graph_v1.json")
TAXONOMY = Path("data/gold/role_taxonomy.json")
OUT = Path("reports/event_graph_view.html")


def main() -> None:
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    tax = {t["role_id"]: t["canonical_role"]
           for t in json.loads(TAXONOMY.read_text(encoding="utf-8"))}
    pj = {n["node_id"]: n["payload_json"] for n in g["nodes"]}
    # 岗位趋势(给 job 节点描边)：同一岗位所有边的 trend 方向一致
    job_trend = {e["dst_id"]: (e["meta_json"].get("trend_impact_direction") or "neutral")
                 for e in g["edges"]}
    # 每个事件的边趋势：节点颜色跟随其主导解释的趋势方向（与边一致）
    ev_trends: dict[str, list[str]] = {}
    for e in g["edges"]:
        ev_trends.setdefault(e["src_id"], []).append(
            e["meta_json"].get("trend_impact_direction") or "neutral")

    vnodes, vedges, seen_job, seen_ev = [], [], set(), set()
    for e in g["edges"]:
        rid, eid = e["dst_id"], e["src_id"]
        p = pj.get(eid, {})
        trend = e["meta_json"].get("trend_impact_direction") or "neutral"
        if rid not in seen_job:
            seen_job.add(rid)
            jt = job_trend.get(rid, "neutral")
            vnodes.append({"id": rid, "label": tax.get(rid, rid), "group": "job",
                           "shape": "box", "borderWidth": 4,
                           "color": {"background": "#1e3a8a", "border": trend_border(jt)},
                           "font": {"color": "#fff", "size": 16},
                           "title": f"岗位 | PatchTST 趋势 {jt}"})
        if eid not in seen_ev:
            seen_ev.add(eid)
            vnodes.append({"id": eid, "label": (p.get("title") or "事件")[:38], "group": "event",
                           "shape": "dot", "size": 10, "color": COLOR["neutral"],
                           "title": f"{p.get('source_domain','')} | {p.get('event_type','')} | 消息极性 {event_polarity(p)} | tone {p.get('tone','')}"})
        p_for_color = {**p, "impact_direction": e["meta_json"].get("impact_direction")}
        vedges.append({"from": eid, "to": rid, "color": {"color": edge_color(trend, p_for_color)},  # 边=预测优先，证据兜底
                       "width": round(1 + 4 * e["weight"], 1),
                       "title": f"{e['meta_json']['event_type']} | 预测方向 {trend} | 证据方向 {e['meta_json'].get('impact_direction')} | w={e['weight']:.2f}"})

    st = g["stats"]
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>事件→岗位 AFFECTS 图谱</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.6/dist/vis-network.min.js"></script>
<style>
 body{{margin:0;font-family:system-ui,'Microsoft YaHei',sans-serif;background:#0b1220;color:#e5e7eb}}
 #h{{padding:12px 18px;border-bottom:1px solid #1f2937}} #h b{{font-size:18px}}
 .pill{{margin-left:14px;font-size:13px;color:#9ca3af}} .lg{{margin-left:14px;font-size:13px}}
 .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 4px -1px 10px}}
 #net{{width:100vw;height:calc(100vh - 58px)}}
</style></head><body>
<div id="h"><b>事件 → 岗位 AFFECTS 图谱</b>
 <span class="pill">event 节点 {st['kept_event_nodes']} · AFFECTS 边 {st['kept_edges']} · 受影响岗位 {st['distinct_jobs_affected']} · 阈值 {st['threshold']}</span>
 <span class="lg"><span class="dot" style="background:#1e3a8a"></span>岗位
 <span class="dot" style="background:#9ca3af"></span>事件
 <span class="dot" style="background:#22c55e"></span>上升影响边<span class="dot" style="background:#ef4444"></span>下降影响边<span class="dot" style="background:#3b82f6"></span>持平影响边</span>
</div><div id="net"></div>
<script>
const nodes=new vis.DataSet({json.dumps(vnodes, ensure_ascii=False)});
const edges=new vis.DataSet({json.dumps(vedges, ensure_ascii=False)});
new vis.Network(document.getElementById('net'),{{nodes,edges}},{{
 physics:{{barnesHut:{{gravitationalConstant:-9000,springLength:130}},stabilization:{{iterations:250}}}},
 interaction:{{hover:true,tooltipDelay:120}},edges:{{smooth:{{type:'continuous'}}}}}});
</script></body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"已写 {OUT} | {len(vnodes)} 节点 / {len(vedges)} 边")


if __name__ == "__main__":
    main()
