"""PathPlannerV4 参数调优：坐标下降扫描 ZPD/权重参数，目标降 zpd_violation 且不掉个性化/覆盖。

    /var/lib/jobnav-env/bin/python experiments/tune_path_v4_params.py

指标口径与 experiments/eval_path_v4.py 一致（99 岗位 × 3 profile = 297 条），
只重算 v4。结果写 reports/eval/path_v4_param_tuning.json。
"""
from __future__ import annotations

import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

import app.services.path_planner_v4 as pp4
from app.services.graph_path_planner_v3 import load_role_profiles
from app.services.path_planner_v4 import PathPlannerV4, load_skill_graph_v4, _normalize_v4, _difficulty_of as _difficulty_of_v4
from experiments.eval_path_v4 import PROFILES, _zpd_violation_rate, _jaccard_distance, _order_distance, _resolve_targets_v4 as _unused  # noqa
from app.services.path_planner_v4 import _resolve_targets_v4

PARAM_GRID = {
    "ZPD_SKIP_GAP": [0.20, 0.25, 0.30, 0.35, 0.40],
    "ZPD_OFFSET": [0.05, 0.10, 0.15, 0.20, 0.25],
    "ZPD_SIGMA": [0.08, 0.12, 0.15, 0.20, 0.25],
    "ZPD_LEVEL_EMA": [0.15, 0.20, 0.30, 0.40, 0.50],
    "W_ZPD": [0.15, 0.25, 0.35, 0.45, 0.55],
}
BASE = {k: getattr(pp4, k) for k in PARAM_GRID}


def evaluate() -> dict:
    roles = load_role_profiles()
    role_ids = sorted(roles)
    records = {}
    for role_id in role_ids:
        for pname, profile in PROFILES.items():
            try:
                analysis = PathPlannerV4.analyze_role(profile, role_id)
                records[f"{role_id}|{pname}"] = analysis
            except Exception:
                pass
    graph = load_skill_graph_v4()

    def to_ids(names):
        out, seen = [], set()
        for n in names:
            ids = _normalize_v4([n])
            sid = next(iter(ids), None)
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)
        return out

    def difficulty(sid):
        return _difficulty_of_v4(sid, graph)

    zpd_rates, coverage, hours, order_dist = [], [], [], []
    for role_id in role_ids:
        idlists = []
        for pname in PROFILES:
            rec = records.get(f"{role_id}|{pname}")
            if not rec:
                continue
            step_ids = to_ids([s.skill for s in rec.path.steps])
            targets = _resolve_targets_v4(roles[role_id], None, graph)
            zpd_rates.append(_zpd_violation_rate(step_ids, difficulty))
            coverage.append(len(set(step_ids) & set(targets)) / max(1, len(set(targets))))
            hours.append(rec.path.total_estimated_hours)
            idlists.append(step_ids)
        if len(idlists) == 3:
            for a, b in ((0, 1), (0, 2), (1, 2)):
                order_dist.append(_order_distance(idlists[a], idlists[b]))
    return {
        "zpd_violation": round(statistics.fmean(zpd_rates), 4),
        "coverage": round(statistics.fmean(coverage), 4),
        "order_distance": round(statistics.fmean(order_dist), 4),
        "hours_mean": round(statistics.fmean(hours), 1),
    }


def score(m: dict) -> float:
    """主目标 zpd_violation 低；约束：order_distance 不低于基线 0.343-0.02，coverage 不低于 0.90。"""
    penalty = max(0.0, 0.323 - m["order_distance"]) * 5 + max(0.0, 0.90 - m["coverage"]) * 2
    return m["zpd_violation"] + penalty


def main():
    history = []
    best_params = dict(BASE)
    print("baseline:", BASE)
    m = evaluate()
    print(" baseline metrics:", m, "score:", round(score(m), 4))
    history.append({"params": dict(best_params), "metrics": m})
    best_score = score(m)

    for rnd in range(2):  # 两轮坐标下降
        improved = False
        for param, values in PARAM_GRID.items():
            for v in values:
                if v == best_params[param]:
                    continue
                setattr(pp4, param, v)
                m = evaluate()
                s = score(m)
                print(f"  round{rnd} {param}={v}: {m} score={s:.4f}")
                if s < best_score - 1e-4:
                    best_score = s
                    best_params[param] = v
                    improved = True
                    history.append({"params": dict(best_params), "metrics": m})
                else:
                    setattr(pp4, param, best_params[param])
        if not improved:
            break
    print("\nbest params:", best_params)
    print("best score:", round(best_score, 4))
    out = {"baseline_params": BASE, "best_params": best_params, "history": history}
    Path("reports/eval/path_v4_param_tuning.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> reports/eval/path_v4_param_tuning.json")


if __name__ == "__main__":
    main()
