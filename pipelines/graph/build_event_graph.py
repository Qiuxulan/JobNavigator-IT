"""C 模块 ④ 事件入图：把检索选出的代表性事件接到知识图谱。

复用 EvidenceService 的同一份"方向归因"选择结果（不二次检索）：
  对 B 的每条趋势结论，取 TopK 干净样本事件 ->
    event 节点（按 url 去重，跨角色共享）+ AFFECTS(event -> job) 边

接入既有图谱（docs/02-system-data §4 的 AFFECTS(TrendEvent->JobRole)）：
  - 复用 graph_nodes / graph_edges 两张表，仅新增 node_type='event'、relation='AFFECTS'
  - dst_id 用 role_taxonomy 的 role_id（与现有 job 节点一致）
  - 与 build_career_graph_v2 解耦：自管 AFFECTS 的 DELETE + INSERT

阈值（决策）：用检索复合分 retrieval_score 当 weight；§4 的 0.5 在当前数据几乎无边能过，
  改按分布 P60 动态定阈值 + 绝对地板 FLOOR，并在统计里说明口径。

默认产出可移植 JSON（无需数据库即可验证）；--write-db 才写 Postgres。

用法：
  python pipelines/graph/build_event_graph.py                 # 仅出 JSON
  python pipelines/graph/build_event_graph.py --sample        # 用样本索引
  python pipelines/graph/build_event_graph.py --write-db      # 同时写图库
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# 路径兜底：直接 `python pipelines/graph/build_event_graph.py` 时也能找到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.evidence import EvidenceService
from pipelines.trend._trend_source import EVENT_WINDOW, load_conclusions

TAXONOMY_PATH = Path("data/gold/role_taxonomy.json")
MAJOR_EVENTS_PATH = Path("data/gold/major_industry_events_v1.json")
OUT_JSON = Path("data/processed/event_graph_v1.json")

DIRECTION_NORMALIZE = {"up": "up", "flat": "flat", "stable": "flat", "down": "down"}
TOPK_GRAPH = 3          # 图谱比 jsonl 更严，只挂方向对齐最强的少量
WEIGHT_FLOOR = 0.35     # 绝对地板，低于此一律不入图
PCTL = 60               # 动态阈值分位数
TITLE_QUALITY_MIN = 0.5  # 入图最低标题可解释性分（低于此=噪音，不入图）
ROLE_AFFINITY_MIN = 0.5  # 入图最低岗位相关性（避免泛技术新闻挂到错误岗位）
MAJOR_EVENT_MAX_PER_ROLE_DIRECTION = 5


def _trend_impact_direction(direction: str) -> str:
    """Visualization polarity: explain the predicted role trend, not raw news tone."""
    if direction == "down":
        return "negative"
    if direction == "up":
        return "positive"
    return "neutral"


def _event_node_id(url: str) -> str:
    h = hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]
    return f"evt_{h}"


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


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def collect(sample: bool) -> dict:
    conclusions = load_conclusions()          # 优先 PatchTST 里程碑
    # 图谱锚在近期(最短视野，通常3个月)：每个岗位只取一条，避免 24/36 月远期预测(2028/2029)进图
    nearest: dict[str, dict] = {}
    for c in conclusions:
        r = c["canonical_role"]
        if r not in nearest or int(c.get("horizon_months", 99)) < int(nearest[r].get("horizon_months", 99)):
            nearest[r] = c
    conclusions = list(nearest.values())
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    role_id = {t["canonical_role"]: t["role_id"] for t in tax}
    category = {t["canonical_role"]: t.get("category") for t in tax}
    major_catalog, major_mapping = _load_major_events()

    nodes: dict[str, dict] = {}          # node_id -> event node
    raw_edges: list[dict] = []

    # 自动 RAG 事件按角色去重；公开来源重大事件按 (岗位,趋势方向) 去重。
    seen_rag_roles: set[str] = set()
    seen_role_directions: set[tuple[str, str]] = set()

    n_rows = len(conclusions)
    src = conclusions[0]["source"] if conclusions else "?"
    print(f"[collect] {n_rows} 条趋势结论(来源={src})，证据窗口 {EVENT_WINDOW}，构建事件边 ...", flush=True)
    for i, row in enumerate(conclusions, 1):
        role = row["canonical_role"]
        rid = role_id.get(role)
        if not rid:
            continue
        month = row["month"]
        if i % 30 == 0 or i == 1 or i == n_rows:
            print(f"  ... {i}/{n_rows}  当前 {role} {month} | 已收事件 {len(nodes)}", flush=True)
        direction = DIRECTION_NORMALIZE.get(row.get("trend_direction", "flat"), "flat")
        raw_direction = row.get("trend_direction", "flat")
        major_direction = "flat" if raw_direction == "stable" else raw_direction
        # 预测在未来无新闻 -> 证据从最近真实事件窗口取
        if role not in seen_rag_roles:
            seen_rag_roles.add(role)
            res = EvidenceService.retrieve_evidence(role, EVENT_WINDOW, TOPK_GRAPH, direction)
            for ev in res["events"]:
                url = ev.get("url")
                if not url:
                    continue
                # 图谱比普通 RAG 更易被肉眼检查：只吃高可解释性标题 + 方向一致的事件
                if (ev.get("title_quality") or 0) < TITLE_QUALITY_MIN:
                    continue
                if (ev.get("role_affinity") or 0) < ROLE_AFFINITY_MIN:
                    continue
                imp = ev.get("impact_direction")
                if (direction == "up" and imp == "negative") or (direction == "down" and imp == "positive"):
                    continue
                nid = _event_node_id(url)
                if nid not in nodes:
                    nodes[nid] = {
                        "node_type": "event",
                        "node_id": nid,
                        "payload_json": {
                            "title": ev.get("title"),
                            "url": url,
                            "source_domain": ev.get("source_domain"),
                            "published_at": ev.get("published_at"),
                            "tone": ev.get("tone"),
                            "event_type": ev.get("event_type"),
                            "role_affinity": ev.get("role_affinity"),
                            "title_quality": ev.get("title_quality"),
                            "themes": ev.get("themes"),
                            "source_layer": "rag_event",
                        },
                    }
                raw_edges.append({
                    "src_type": "event",
                    "src_id": nid,
                    "dst_type": "job",
                    "dst_id": rid,
                    "relation": "AFFECTS",
                    "weight": float(ev.get("retrieval_score") or 0.0),
                    "confidence": float(ev.get("direction_align") or 0.5),
                    "meta_json": {
                        "impact_direction": ev.get("impact_direction"),
                        "trend_impact_direction": _trend_impact_direction(direction),
                        "event_type": ev.get("event_type"),
                        "month": month,
                        "trend_direction": direction,
                        "role_family": category.get(role),
                        "source_layer": "rag_event",
                    },
                    "source_time": ev.get("published_at"),
                })

        rd_key = (role, major_direction)
        if rd_key not in seen_role_directions:
            seen_role_directions.add(rd_key)
            for event_id in major_mapping.get(rd_key, [])[:MAJOR_EVENT_MAX_PER_ROLE_DIRECTION]:
                ev = major_catalog.get(event_id)
                if not ev or not ev.get("source_url"):
                    continue
                nid = _event_node_id(ev["source_url"])
                if nid not in nodes:
                    nodes[nid] = {
                        "node_type": "event",
                        "node_id": nid,
                        "payload_json": {
                            "title": ev.get("title"),
                            "url": ev.get("source_url"),
                            "source_domain": ev.get("source_name"),
                            "published_at": ev.get("event_date"),
                            "tone": None,
                            "event_type": ev.get("event_type"),
                            "impact_direction": ev.get("impact_direction"),
                            "event_importance": ev.get("event_importance"),
                            "summary_zh": ev.get("summary_zh"),
                            "source_layer": "public_major_event",
                        },
                    }
                raw_edges.append({
                    "src_type": "event",
                    "src_id": nid,
                    "dst_type": "job",
                    "dst_id": rid,
                    "relation": "AFFECTS",
                    "weight": float(ev.get("event_importance") or 0.75),
                    "confidence": 0.85,
                    "meta_json": {
                        "impact_direction": ev.get("impact_direction"),
                        "trend_impact_direction": _trend_impact_direction(direction),
                        "event_type": ev.get("event_type"),
                        "month": month,
                        "trend_direction": direction,
                        "role_family": category.get(role),
                        "source_layer": "public_major_event",
                    },
                    "source_time": ev.get("event_date"),
                })

    # 阈值标定
    rag_edges = [e for e in raw_edges if e["meta_json"].get("source_layer") != "public_major_event"]
    major_edges = [e for e in raw_edges if e["meta_json"].get("source_layer") == "public_major_event"]
    weights = [e["weight"] for e in rag_edges]
    thr = max(_percentile(weights, PCTL), WEIGHT_FLOOR) if weights else WEIGHT_FLOOR
    edges = [e for e in rag_edges if e["weight"] >= thr] + major_edges
    kept_nodes_ids = {e["src_id"] for e in edges}
    kept_nodes = [n for nid, n in nodes.items() if nid in kept_nodes_ids]

    return {
        "nodes": kept_nodes,
        "edges": edges,
        "stats": {
            "candidate_edges": len(raw_edges),
            "threshold": round(thr, 4),
            "pctl": PCTL,
            "weight_floor": WEIGHT_FLOOR,
            "kept_edges": len(edges),
            "kept_rag_edges": len([e for e in edges if e["meta_json"].get("source_layer") != "public_major_event"]),
            "kept_major_edges": len([e for e in edges if e["meta_json"].get("source_layer") == "public_major_event"]),
            "kept_event_nodes": len(kept_nodes),
            "distinct_jobs_affected": len({e["dst_id"] for e in edges}),
        },
    }


def write_db(payload: dict) -> None:
    import psycopg

    dsn = os.environ.get(
        "JOBNAV_POSTGRES_DSN",
        "postgresql://postgres:postgres@localhost:5432/jobnav",
    )
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # 自管增量：先清掉旧的 event 节点与 AFFECTS 边
            cur.execute("DELETE FROM graph_edges WHERE relation = 'AFFECTS'")
            cur.execute("DELETE FROM graph_nodes WHERE node_type = 'event'")
            for n in payload["nodes"]:
                cur.execute(
                    """INSERT INTO graph_nodes (node_type, node_id, payload_json, updated_at)
                       VALUES (%s, %s, %s, now())
                       ON CONFLICT (node_type, node_id) DO UPDATE
                       SET payload_json = EXCLUDED.payload_json, updated_at = now()""",
                    (n["node_type"], n["node_id"], json.dumps(n["payload_json"], ensure_ascii=False)),
                )
            for e in payload["edges"]:
                cur.execute(
                    """INSERT INTO graph_edges
                       (src_type, src_id, dst_type, dst_id, relation, weight, confidence, meta_json, source_time)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (e["src_type"], e["src_id"], e["dst_type"], e["dst_id"], e["relation"],
                     e["weight"], e["confidence"], json.dumps(e["meta_json"], ensure_ascii=False),
                     e["source_time"]),
                )
        conn.commit()
    print(f"[db] 写入 {len(payload['nodes'])} event 节点 / {len(payload['edges'])} AFFECTS 边")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--write-db", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    payload = collect(args.sample)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    s = payload["stats"]
    print("=== 事件入图统计 ===")
    print(f"候选边 {s['candidate_edges']} -> 阈值 {s['threshold']} (P{s['pctl']}/地板{s['weight_floor']})"
          f" -> 入图边 {s['kept_edges']}")
    print(f"  其中 RAG 边 {s.get('kept_rag_edges', 0)} | 重大行业事件边 {s.get('kept_major_edges', 0)}")
    print(f"event 节点 {s['kept_event_nodes']} | 受影响岗位 {s['distinct_jobs_affected']}")
    print(f"JSON -> {OUT_JSON}")

    if args.write_db:
        write_db(payload)
    print(f"[done] 用时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
