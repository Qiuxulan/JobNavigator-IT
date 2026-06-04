"""
pipelines/graph/build_skill_graph.py  —  C部分技能图谱构建流水线
================================================================
职责：从 data/gold/skill_prerequisite_v1.json 加载技能先修关系，
      执行 DAG 无环验证，输出验证报告到 reports/dag_validation.json。

运行方式：
    python pipelines/graph/build_skill_graph.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "services"))

SKILL_PATH   = ROOT / "data" / "gold" / "skill_prerequisite_v1.json"
VOCAB_PATH   = ROOT / "data" / "gold" / "skill_vocab.json"
REPORT_PATH  = ROOT / "reports" / "dag_validation.json"
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── DAG 验证（DFS 三色标记法） ────────────────────────────────────
def detect_cycles(skill_data: dict, prereq_map: dict) -> tuple[bool, list]:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in skill_data}
    cycle_path: list = []

    def dfs(v: str, path: list) -> bool:
        color[v] = GRAY
        path.append(v)
        for nbr in prereq_map.get(v, []):
            if nbr not in color:
                continue
            if color[nbr] == GRAY:
                idx = path.index(nbr)
                cycle_path.extend(path[idx:] + [nbr])
                return True
            if color[nbr] == WHITE and dfs(nbr, path):
                return True
        path.pop()
        color[v] = BLACK
        return False

    for sid in skill_data:
        if color[sid] == WHITE and dfs(sid, []):
            return True, cycle_path
    return False, []


def build_and_validate() -> dict:
    print("=" * 55)
    print("  C部分 技能图谱构建流水线")
    print("=" * 55)

    # 1. 加载技能数据
    with open(SKILL_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    skill_data = {s["skill_id"]: s for s in raw["skills"]}
    prereq_map = {s["skill_id"]: s.get("prerequisites", []) for s in raw["skills"]}
    print(f"\n[1] 加载技能节点: {len(skill_data)} 个")

    # 2. 统计图谱拓扑
    in_deg  = defaultdict(int)
    out_deg = defaultdict(int)
    edges   = []
    for sid, prereqs in prereq_map.items():
        for p in prereqs:
            out_deg[p] += 1
            in_deg[sid] += 1
            edges.append((p, sid))

    root_nodes = [s for s in skill_data if in_deg[s] == 0]
    leaf_nodes = [s for s in skill_data if out_deg[s] == 0]
    print(f"[2] 图谱边数: {len(edges)}  根节点: {len(root_nodes)}  叶节点: {len(leaf_nodes)}")

    # 3. DAG 无环验证
    has_cycle, cycle = detect_cycles(skill_data, prereq_map)
    result = "PASS" if not has_cycle else "FAIL"
    print(f"[3] DAG验证: {result}")
    if has_cycle:
        print(f"    环路: {' -> '.join(cycle)}")

    # 4. 层级分布统计
    level_dist: dict[int, int] = defaultdict(int)
    diff_dist: dict[str, int] = defaultdict(int)
    for s in skill_data.values():
        level_dist[s.get("level", 0)] += 1
        diff_dist[s.get("difficulty", "unknown")] += 1

    # 5. 输出验证报告
    report = {
        "validation_date": str(date.today()),
        "algorithm":       "DFS三色标记法（WHITE/GRAY/BLACK）",
        "result":          result,
        "has_cycle":       has_cycle,
        "cycle_path":      cycle if has_cycle else [],
        "graph_stats": {
            "total_nodes":  len(skill_data),
            "total_edges":  len(edges),
            "root_nodes":   root_nodes,
            "leaf_nodes":   leaf_nodes,
            "level_dist":   dict(level_dist),
            "difficulty_dist": dict(diff_dist),
        },
        "target_roles": raw.get("target_roles", []),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[4] 报告已保存: {REPORT_PATH}")

    # 6. 加载词表校验
    if VOCAB_PATH.exists():
        with open(VOCAB_PATH, encoding="utf-8") as f:
            vocab = json.load(f)
        vocab_ids   = set(vocab["id_to_name"].keys())
        graph_ids   = set(skill_data.keys())
        missing_in_vocab = graph_ids - vocab_ids
        if missing_in_vocab:
            print(f"[!] 词表缺少 {len(missing_in_vocab)} 个技能ID: {missing_in_vocab}")
        else:
            print(f"[5] 词表校验: PASS ({len(vocab_ids)} 个技能均有词条)")
    else:
        print(f"[5] 词表文件不存在: {VOCAB_PATH}")

    print(f"\n{'=' * 55}")
    print(f"  结果: {result}  节点={len(skill_data)}  边={len(edges)}")
    print(f"{'=' * 55}")
    return report


if __name__ == "__main__":
    report = build_and_validate()
    sys.exit(0 if not report["has_cycle"] else 1)
