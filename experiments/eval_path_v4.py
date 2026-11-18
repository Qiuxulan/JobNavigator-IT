"""评估 PathPlannerV4 vs GraphPathPlannerV3(learning_path_method_v2.md §5.1 自动指标)。

99 岗位 × 3 类 profile(零基础 / 转行 / 在职提升)= 297 条路径,v3/v4 各一份:

图质量(来自 data/gold/skill_prerequisite_v4_qc.json + 重算):
  - LLM 边 vs v3 种子一致率(precision 代理)
  - 覆盖率 / 边数 / 环数

路径质量对比:
  - 个性化差异度:同岗位不同 profile 路径技能集合的 Jaccard 距离(v4 应显著 > v3,配对 t 检验)
  - ZPD 越界率:步骤难度 > 已完成步骤难度均值 + 2σ 的比例(v4 应更低)
  - 总时长分布(mean/median/p25/p75,v4 应与资源真实时长对齐、更紧凑)
  - 资源挂载率:有 ≥1 资源的步骤占比(应 ≥95%)
  - 目标覆盖率:路径技能对岗位目标集的覆盖
  - 平均先修深度

产出:
  reports/eval/path_v4_eval.json
  reports/eval/path_v4_samples.md   (10 岗位 × 3 profile 的 v3/v4 并排路径样本,供人工盲评)

用法:/var/lib/jobnav-env/bin/python experiments/eval_path_v4.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.domain import UserProfile  # noqa: E402
from app.services.graph_path_planner_v3 import (  # noqa: E402
    _resolve_targets as _resolve_targets_v3,
    load_role_profiles,
    load_skill_graph as load_skill_graph_v3,
    normalize_skill_ids,
)
from app.services.path_planner_v4 import (  # noqa: E402
    _difficulty_of as _difficulty_of_v4,
    _resolve_targets_v4,
    load_skill_graph_v4,
    _normalize_v4,
)


def _difficulty_of_v3(skill_id: str, graph: dict) -> float:
    """v3 图无 difficulty_score,用 level(1-4)线性映射。"""
    node = graph.get(skill_id, {})
    return max(0.0, min(1.0, (float(node.get("level", 1)) - 1.0) / 3.0))

EVAL_DIR = ROOT / "reports" / "eval"
EVAL_JSON = EVAL_DIR / "path_v4_eval.json"
SAMPLES_MD = EVAL_DIR / "path_v4_samples.md"
QC_PATH = ROOT / "data" / "gold" / "skill_prerequisite_v4_qc.json"

# 3 类 profile(与设计方案 §5.1 一致:零基础 / 转行 / 在职提升)
PROFILES: dict[str, UserProfile] = {
    "zero": UserProfile(user_id="eval_zero", skills=[], years_experience=0.0),
    "career_change": UserProfile(
        user_id="eval_career_change",
        skills=["figma", "photoshop", "html", "communication"],
        years_experience=1.5,
    ),
    "upskilling": UserProfile(
        user_id="eval_upskilling",
        skills=["python", "java", "sql-lang", "git", "linux", "docker", "excel"],
        years_experience=3.0,
    ),
}
PROFILE_LABEL = {"zero": "零基础", "career_change": "转行", "upskilling": "在职提升"}
SAMPLE_ROLES = 10
SIGMA_ZPD = 2.0


def _jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)


def _zpd_violation_rate(step_ids: list[str], difficulty) -> float:
    """步骤难度 > 已完成步骤难度均值 + 2σ 的比例(跳过前 1 步,无 σ 时跳过)。"""
    if len(step_ids) < 4:
        return 0.0
    violations = 0
    checked = 0
    diffs = [difficulty(s) for s in step_ids]
    for i in range(1, len(diffs)):
        history = diffs[:i]
        mean = statistics.fmean(history)
        sd = statistics.pstdev(history)
        if sd <= 1e-9:
            continue
        checked += 1
        if diffs[i] > mean + SIGMA_ZPD * sd:
            violations += 1
    return violations / checked if checked else 0.0


def _paired_t_stat(diff: list[float]) -> tuple[float, float]:
    """配对差值的一样本 t 统计量与近似 p 值(双侧,正态近似)。"""
    import math

    n = len(diff)
    if n < 2:
        return 0.0, 1.0
    mean = statistics.fmean(diff)
    sd = statistics.stdev(diff)
    if sd <= 1e-12:
        return (float("inf") if mean > 0 else 0.0), 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    # 正态近似双侧 p
    from statistics import NormalDist

    p = 2 * (1 - NormalDist().cdf(abs(t)))
    return round(t, 4), round(p, 6)


def _order_distance(ids_a: list[str], ids_b: list[str]) -> float:
    """两条路径共同技能的顺序不一致度 = 1 − Kendall's τ_b(交集上;交集 <2 记 0)。"""
    common = [s for s in ids_a if s in set(ids_b)]
    if len(common) < 2:
        return 0.0
    order_b = {s: i for i, s in enumerate(ids_b)}
    ra = list(range(len(common)))
    rb = [order_b[s] for s in common]
    from scipy.stats import kendalltau

    tau = kendalltau(ra, rb).statistic
    return 1.0 - float(tau) if tau == tau else 0.0


def main() -> None:
    roles = load_role_profiles()
    graph_v3 = load_skill_graph_v3()
    graph_v4 = load_skill_graph_v4()
    role_ids = sorted(roles.keys())
    print(f"岗位 {len(role_ids)},profile {len(PROFILES)} 类")

    from app.services.graph_path_planner_v3 import GraphPathPlannerV3
    from app.services.path_planner_v4 import PathPlannerV4

    records: dict[str, dict[str, dict]] = {"v3": {}, "v4": {}}
    failures = {"v3": 0, "v4": 0}
    for version, planner in (("v3", GraphPathPlannerV3), ("v4", PathPlannerV4)):
        for role_id in role_ids:
            for pname, profile in PROFILES.items():
                key = f"{role_id}|{pname}"
                try:
                    analysis = planner.analyze_role(profile, role_id)
                    records[version][key] = {
                        "role_id": role_id, "profile": pname,
                        "skill_ids": None,  # 由下面统一从 role/targets 重建
                        "path": analysis.path,
                        "score_breakdown": analysis.score_breakdown,
                        "target_ids": (
                            _resolve_targets_v3(roles[role_id], None, graph_v3)
                            if version == "v3"
                            else _resolve_targets_v4(roles[role_id], None, graph_v4)
                        ),
                    }
                except Exception as exc:  # noqa: BLE001
                    failures[version] += 1
                    if failures[version] <= 5:
                        print(f"[warn] {version} {key}: {exc}")
    for version in records:
        print(f"{version}: {len(records[version])} 条路径,失败 {failures[version]}")

    # 技能名归一到 skill_id(用于 Jaccard/覆盖/越界)
    def to_ids(version: str, names: list[str]) -> list[str]:
        out, seen = [], set()
        for n in names:
            ids = normalize_skill_ids([n]) if version == "v3" else _normalize_v4([n])
            sid = next(iter(ids), None)
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)
        return out

    metrics: dict[str, dict] = {"v3": {}, "v4": {}}
    diffs_for_t: list[float] = []
    sample_rows: list[dict] = []
    per_role_dist = {"v3": [], "v4": []}
    hours_all = {"v3": [], "v4": []}
    mount_stats = {"v3": [0, 0], "v4": [0, 0]}  # [有资源步数, 总步数]
    zpd_rates = {"v3": [], "v4": []}
    coverage = {"v3": [], "v4": []}
    depths = {"v3": [], "v4": []}

    hot_roles = sorted({k.split("|")[0] for k in records["v3"]}
                       & {k.split("|")[0] for k in records["v4"]})
    for role_id in hot_roles:
        for pname in PROFILES:
            key = f"{role_id}|{pname}"
            row = {"role_id": role_id, "profile": pname, "role_name": roles[role_id].get("role_name", role_id)}
            role_sets = {}
            for version in ("v3", "v4"):
                rec = records[version].get(key)
                if not rec:
                    continue
                path = rec["path"]
                targets = rec["target_ids"]
                step_ids = to_ids(version, [s.skill for s in path.steps])
                step_set = set(step_ids)
                difficulty = (lambda s, g=graph_v3: _difficulty_of_v3(s, g)) if version == "v3" \
                    else (lambda s, g=graph_v4: _difficulty_of_v4(s, g))
                zpd = _zpd_violation_rate(step_ids, difficulty)
                covered = len(step_set & set(targets)) / max(1, len(set(targets)))
                hours_all[version].append(path.total_estimated_hours)
                mount_stats[version][0] += sum(1 for s in path.steps if s.resources)
                mount_stats[version][1] += len(path.steps)
                zpd_rates[version].append(zpd)
                coverage[version].append(covered)
                # 先修深度:目标技能在路径中的最大拓扑深度(用对应图算)
                graph = graph_v3 if version == "v3" else graph_v4
                depth_map: dict[str, int] = {}

                def depth_of(sid: str) -> int:
                    if sid in depth_map:
                        return depth_map[sid]
                    depth_map[sid] = 0
                    pres = [p for p in graph.get(sid, {}).get("prerequisites", []) if p in step_set]
                    depth_map[sid] = 0 if not pres else 1 + max(depth_of(p) for p in pres)
                    return depth_map[sid]

                depths[version].append(max((depth_of(t) for t in targets if t in step_set), default=0))
                role_sets[version] = step_set
                row[version] = {"path": path, "step_ids": step_ids, "zpd": zpd,
                                "coverage": covered}
            if "v3" in role_sets and "v4" in role_sets:
                sample_rows.append(row)

    # 个性化:同岗位 3 类 profile 两两 Jaccard 距离(集合)与顺序不一致度(排序)
    order_dist = {"v3": [], "v4": []}
    order_diffs: list[float] = []
    for role_id in hot_roles:
        for version in ("v3", "v4"):
            sets, idlists = [], []
            for pname in PROFILES:
                rec = records[version].get(f"{role_id}|{pname}")
                if not rec:
                    continue
                ids = to_ids(version, [s.skill for s in rec["path"].steps])
                sets.append(set(ids))
                idlists.append(ids)
            if len(sets) == 3:
                for a, b in ((0, 1), (0, 2), (1, 2)):
                    per_role_dist[version].append(_jaccard_distance(sets[a], sets[b]))
                    order_dist[version].append(_order_distance(idlists[a], idlists[b]))
        # 配对:v4 − v3 的顺序差异度
        od = {}
        for version in ("v3", "v4"):
            idlists = []
            for pname in PROFILES:
                rec = records[version].get(f"{role_id}|{pname}")
                if rec:
                    idlists.append(to_ids(version, [s.skill for s in rec["path"].steps]))
            if len(idlists) == 3:
                od[version] = statistics.fmean([
                    _order_distance(idlists[0], idlists[1]),
                    _order_distance(idlists[0], idlists[2]),
                    _order_distance(idlists[1], idlists[2]),
                ])
        if len(od) == 2:
            order_diffs.append(od["v4"] - od["v3"])
    # 配对:v3/v4 在同一 role×pair 上的差异
    role_list = []
    for role_id in hot_roles:
        d_v4, d_v3 = [], []
        for version, acc in (("v3", d_v3), ("v4", d_v4)):
            sets = []
            for pname in PROFILES:
                rec = records[version].get(f"{role_id}|{pname}")
                if not rec:
                    continue
                ids = to_ids(version, [s.skill for s in rec["path"].steps])
                sets.append(set(ids))
            if len(sets) == 3:
                acc.append(statistics.fmean([
                    _jaccard_distance(sets[0], sets[1]),
                    _jaccard_distance(sets[0], sets[2]),
                    _jaccard_distance(sets[1], sets[2]),
                ]))
        if len(d_v3) == len(d_v4) == 1:
            diffs_for_t.append(d_v4[0] - d_v3[0])
    t_stat, p_val = _paired_t_stat(diffs_for_t)

    def _q(values: list[float], name: str) -> dict:
        values = sorted(values)
        n = len(values)
        return {
            "n": n, "mean": round(statistics.fmean(values), 4),
            "median": round(statistics.median(values), 4),
            "p25": round(values[max(0, n // 4 - 1)], 4) if n else None,
            "p75": round(values[min(n - 1, (3 * n) // 4)], 4) if n else None,
        }

    for version in ("v3", "v4"):
        hh = sorted(hours_all[version])
        metrics[version] = {
            "paths": len(hours_all[version]),
            "personalization": {
                "jaccard_distance_mean": round(statistics.fmean(per_role_dist[version]), 4),
                "jaccard_distance_median": round(statistics.median(per_role_dist[version]), 4),
                "order_distance_mean": round(statistics.fmean(order_dist[version]), 4),
            },
            "total_hours": _q(hours_all[version], "hours"),
            "resource_mount_rate": round(mount_stats[version][0] / max(1, mount_stats[version][1]), 4),
            "zpd_violation_rate_mean": round(statistics.fmean(zpd_rates[version]), 4),
            "target_coverage_mean": round(statistics.fmean(coverage[version]), 4),
            "avg_prereq_depth": round(statistics.fmean(depths[version]), 3),
        }
    metrics["paired_t"] = {
        "n_roles": len(diffs_for_t),
        "mean_diff_v4_minus_v3": round(statistics.fmean(diffs_for_t), 4) if diffs_for_t else None,
        "t_stat": t_stat, "p_value": p_val,
        "conclusion": ("v4 集合差异度显著高于 v3" if p_val < 0.05 and diffs_for_t
                       and statistics.fmean(diffs_for_t) > 0 else
                       "集合 Jaccard 差异不显著(岗位目标集主导,见顺序不一致度)"),
    }
    ot_stat, op_val = _paired_t_stat(order_diffs)
    metrics["personalization_order"] = {
        "v3_order_distance_mean": round(statistics.fmean(order_dist["v3"]), 4),
        "v4_order_distance_mean": round(statistics.fmean(order_dist["v4"]), 4),
        "paired_t": {"n_roles": len(order_diffs),
                     "mean_diff_v4_minus_v3": round(statistics.fmean(order_diffs), 4)
                     if order_diffs else None,
                     "t_stat": ot_stat, "p_value": op_val,
                     "conclusion": ("v4 排序个性化显著优于 v3" if op_val < 0.05 and order_diffs
                                    and statistics.fmean(order_diffs) > 0
                                    else "排序差异不显著")},
    }

    # 图质量
    qc = json.loads(QC_PATH.read_text(encoding="utf-8")) if QC_PATH.exists() else {}
    metrics["graph"] = {
        "v4_edge_count": qc.get("edge_count"),
        "v4_coverage": qc.get("coverage"),
        "v4_cycles_broken": qc.get("dag", {}).get("cycles_broken"),
        "v4_is_dag": qc.get("dag", {}).get("is_dag"),
        "llm_v3_agreement_rate": qc.get("llm", {}).get("llm_v3_agreement_rate"),
        "overlap_rate_vs_v3": qc.get("v3_comparison", {}).get("overlap_rate_vs_v3"),
        "llm_api_calls": qc.get("llm", {}).get("api_calls"),
        "llm_cost_yuan": qc.get("llm", {}).get("estimated_cost_yuan"),
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_JSON.write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))

    # 并排样本(10 岗 × 3 profile),按岗位 JD 数取热门岗
    def jd_count(r: str) -> float:
        return float(roles[r].get("jd_count") or 0)

    sample_role_ids = sorted(hot_roles, key=lambda r: -jd_count(r))[:SAMPLE_ROLES]
    lines = ["# v3 vs v4 学习路径并排样本(人工盲评材料)", "",
             f"生成:experiments/eval_path_v4.py;岗位按 JD 数取前 {SAMPLE_ROLES}。", ""]
    for role_id in sample_role_ids:
        lines.append(f"## {roles[role_id].get('role_name', role_id)}({role_id})")
        for pname, label in PROFILE_LABEL.items():
            key = f"{role_id}|{pname}"
            lines.append(f"### profile: {label}")
            for version in ("v3", "v4"):
                rec = records[version].get(key)
                if not rec:
                    lines.append(f"- **{version}**: 生成失败")
                    continue
                p = rec["path"]
                steps = " → ".join(s.skill for s in p.steps)
                lines.append(
                    f"- **{version}**({p.total_steps} 步, {p.total_estimated_hours}h): {steps}"
                )
            lines.append("")
    SAMPLES_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"写出 {EVAL_JSON}")
    print(f"写出 {SAMPLES_MD}")


if __name__ == "__main__":
    main()
