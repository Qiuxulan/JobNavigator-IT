"""四维精排权重网格调优(matching v3,2026-10-19)。

背景:v3.1 评分公式引入真实趋势动量(role_profiles_v3.trend_momentum 经
sigmoid 归一化),替代原三公式;同时岗位 embedding 文本升级为 JD 语义风格、
画像 skill_freq 改为 12 万 JD 近期加权频率。权重需要重调。

本脚本:
  1. 合并 eval_set_v1(18 例)+ eval_set_v2(40 例)= 58 例。
  2. 每用例一次模型编码 + pgvector 召回 top10(与线上一致),每个候选跑
     GraphPathPlannerV3.analyze_role,缓存四分项(coverage_weighted,
     semantic, trend_momentum_norm, learning_feasibility)。
  3. 纯内存四维网格扫描(步长 0.05,和=1,w_sem ∈ [0.3, 0.7],
     w_cov/w_feas/w_trend >= 0),按 NDCG@5 排序,tie 看 Hit@1。
  4. 与当前线上旧权重 (0.15/0.80/0/0.05) 基线对比。
  5. 报告写 reports/eval/matching_v3_eval.json(含逐例对比)。

运行:python -m experiments.tune_ranking_weights
注意:召回分与候选集与权重无关,扫描只重算 role_score 再排序,不重复编码/查询。
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"

os.chdir(ROOT)

EVAL_SET_PATHS = [
    ROOT / "data" / "gold" / "eval_set_v1.json",
    ROOT / "data" / "gold" / "eval_set_v2.json",
]
REPORT_PATH = ROOT / "reports" / "eval" / "matching_v3_eval.json"
TOP_K = 5
RECALL_TOP_N = 10  # 与线上 RecommenderService(rank top_n=max(top_k,10))一致

# 扫描约束(任务书规定)
W_SEM_MIN, W_SEM_MAX, W_STEP = 0.3, 0.7, 0.05

# 线上旧基线(2026-10-17 三公式调参定版,无趋势项)
BASELINE_WEIGHTS = (0.15, 0.80, 0.0, 0.05)  # (cov, sem, trend, feas)


def _frange(start: float, stop: float, step: float):
    vals = []
    v = start
    while v <= stop + 1e-9:
        vals.append(round(v, 4))
        v += step
    return vals


def build_candidate_cache() -> tuple[list[dict], list[dict]]:
    """每用例:编码一次 → ANN 召回 top 10 → 每候选 analyze_role 缓存分项。"""
    from app.schemas.domain import UserProfile
    from app.services.career_catalog import load_roles
    from app.services.career_pathway_service import _load_engine, _profile_to_query_text
    from pipelines.taxonomy.recall import recall_topn
    from app.services.graph_path_planner_v3 import GraphPathPlannerV3

    roles = load_roles()
    name2id = {r["role_name"]: r["role_id"] for r in roles.values()}
    model = _load_engine()

    eval_set: list[dict] = []
    unresolved: list[dict] = []
    for path in EVAL_SET_PATHS:
        for case in json.loads(path.read_text(encoding="utf-8")):
            case = dict(case, eval_set=path.stem)
            skipped = [n for n in case["relevant_role_names"] if n not in name2id]
            if skipped:
                unresolved.append({"case": case["name"], "eval_set": path.stem, "skipped": skipped})
            eval_set.append(case)

    cache = []
    for case in eval_set:
        profile = UserProfile(user_id="eval", skills=case["skills"], target_role=case.get("target_role"))
        vec = model.encode(_profile_to_query_text(profile), normalize_embeddings=True)
        rows = recall_topn(vec, RECALL_TOP_N, os.environ.get(
            "JOBNAV_POSTGRES_DSN", "postgresql://jobnav:jobnav@localhost:5432/jobnavigator"))
        cands = []
        for row in rows:
            job_id = row["job_id"]
            if job_id not in roles:
                continue
            try:
                analysis = GraphPathPlannerV3.analyze_role(
                    profile=profile, target_job_id=job_id, semantic_score=float(row["score"]))
            except ValueError:
                continue  # 技能图无覆盖的岗,跳过该候选
            bd = analysis.score_breakdown
            cands.append({
                "job_id": job_id,
                "title": roles[job_id]["role_name"],
                "coverage": bd["coverage_weighted"],
                "semantic": bd["semantic"],
                "trend": bd["trend_momentum_norm"],
                "feasibility": bd["learning_feasibility"],
            })
        cache.append({
            "name": case["name"],
            "eval_set": case["eval_set"],
            "target_role": case.get("target_role"),
            "relevant_ids": sorted({name2id[n] for n in case["relevant_role_names"] if n in name2id}),
            "cands": cands,
        })
        print(f"[cache] [{case['eval_set']}] {case['name']}: {len(cands)} 候选", flush=True)
    return cache, unresolved


def score_rank(cands: list[dict], w: tuple[float, float, float, float]) -> list[str]:
    w_cov, w_sem, w_trend, w_feas = w

    def role_score(c: dict) -> float:
        s = (w_cov * c["coverage"] + w_sem * c["semantic"]
             + w_trend * c["trend"] + w_feas * c["feasibility"])
        return max(0.0, min(1.0, round(s, 4)))

    return [c["job_id"] for c in sorted(cands, key=role_score, reverse=True)]


def metrics_for_weights(cache: list[dict], w: tuple[float, float, float, float]) -> dict:
    hit1 = hit5 = mrr_sum = ndcg_sum = 0.0
    for case in cache:
        rel = set(case["relevant_ids"])
        ranked = score_rank(case["cands"], w)
        topk = ranked[:TOP_K]
        hit1 += int(ranked[0] in rel) if ranked else 0
        hit5 += int(any(j in rel for j in topk))
        for rank, j in enumerate(topk, start=1):
            if j in rel:
                mrr_sum += 1.0 / rank
                break
        dcg = sum(1.0 / math.log2(r + 1) for r, j in enumerate(topk, start=1) if j in rel)
        idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(rel), TOP_K) + 1))
        ndcg_sum += dcg / idcg if idcg else 0.0
    n = len(cache)
    return {
        "w_coverage": round(w[0], 2),
        "w_semantic": round(w[1], 2),
        "w_trend": round(w[2], 2),
        "w_feasibility": round(w[3], 2),
        "hit@1": round(hit1 / n, 4),
        "hit@5": round(hit5 / n, 4),
        "mrr": round(mrr_sum / n, 4),
        "ndcg@5": round(ndcg_sum / n, 4),
    }


def main() -> dict:
    cache, unresolved = build_candidate_cache()

    results = []
    for w_sem in _frange(W_SEM_MIN, W_SEM_MAX, W_STEP):
        for w_cov in _frange(0.0, 1.0 - w_sem, W_STEP):
            for w_feas in _frange(0.0, 1.0 - w_sem - w_cov, W_STEP):
                w_trend = round(1.0 - w_cov - w_sem - w_feas, 4)
                results.append(metrics_for_weights(cache, (w_cov, w_sem, w_trend, w_feas)))

    results.sort(key=lambda r: (r["ndcg@5"], r["hit@1"], r["mrr"]), reverse=True)
    baseline = metrics_for_weights(cache, BASELINE_WEIGHTS)
    top = results[0]

    print("\n# 线上旧基线 (0.15/0.80/0/0.05,无趋势项)")
    print(f"  Hit@1={baseline['hit@1']} Hit@5={baseline['hit@5']} "
          f"MRR={baseline['mrr']} NDCG@5={baseline['ndcg@5']}")

    print(f"\n# 四维扫描 top 10(按 NDCG@5,约束: w_sem∈[0.3,0.7], 和=1, 步长 0.05)")
    print("| # | w_cov | w_sem | w_trend | w_feas | Hit@1 | Hit@5 | MRR | NDCG@5 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(results[:10], 1):
        print(f"| {i} | {r['w_coverage']:.2f} | {r['w_semantic']:.2f} | "
              f"{r['w_trend']:.2f} | {r['w_feasibility']:.2f} | "
              f"{r['hit@1']} | {r['hit@5']} | {r['mrr']} | {r['ndcg@5']} |")

    print(f"\n# 最优: cov={top['w_coverage']} sem={top['w_semantic']} "
          f"trend={top['w_trend']} feas={top['w_feasibility']}")
    print(f"  Hit@1 {baseline['hit@1']} → {top['hit@1']}, "
          f"NDCG@5 {baseline['ndcg@5']} → {top['ndcg@5']}")

    # ---- 逐例对比(基线 vs 最优) ----
    best_w = (top["w_coverage"], top["w_semantic"], top["w_trend"], top["w_feasibility"])
    per_case = []
    for case in cache:
        rel = set(case["relevant_ids"])
        base_rank = score_rank(case["cands"], BASELINE_WEIGHTS)
        best_rank = score_rank(case["cands"], best_w)
        title = {c["job_id"]: c["title"] for c in case["cands"]}
        per_case.append({
            "name": case["name"],
            "eval_set": case["eval_set"],
            "target_role": case["target_role"],
            "baseline_top5": [title.get(j, j) for j in base_rank[:TOP_K]],
            "tuned_top5": [title.get(j, j) for j in best_rank[:TOP_K]],
            "baseline_hit@1": int(bool(base_rank) and base_rank[0] in rel),
            "tuned_hit@1": int(bool(best_rank) and best_rank[0] in rel),
        })

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "eval_sets": [p.name for p in EVAL_SET_PATHS],
        "n_cases": len(cache),
        "recall_top_n": RECALL_TOP_N,
        "grid": {"w_sem_range": [W_SEM_MIN, W_SEM_MAX], "step": W_STEP,
                 "sum_to_one": True, "n_combinations": len(results)},
        "baseline": {"weights": {"coverage": BASELINE_WEIGHTS[0], "semantic": BASELINE_WEIGHTS[1],
                                 "trend": BASELINE_WEIGHTS[2], "feasibility": BASELINE_WEIGHTS[3]},
                     "metrics": baseline,
                     "note": "线上旧三公式权重(0.15/0.80/0/0.05,无趋势项,trend 张冠李戴)"},
        "best": {"weights": {"coverage": top["w_coverage"], "semantic": top["w_semantic"],
                             "trend": top["w_trend"], "feasibility": top["w_feasibility"]},
                 "metrics": top},
        "improvement": {
            "ndcg@5_delta": round(top["ndcg@5"] - baseline["ndcg@5"], 4),
            "hit@1_delta": round(top["hit@1"] - baseline["hit@1"], 4),
        },
        "unresolved_role_names": unresolved,
        "per_case": per_case,
        "top10_grid": results[:10],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] 报告已写入 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    main()
