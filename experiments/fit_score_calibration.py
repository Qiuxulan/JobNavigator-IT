"""score_calibration v1 拟合:粗召回原始 cosine 分布统计 + 分段线性锚点选择。

背景:Qwen3-Embedding-4B 的原始余弦相似度集中在 0.5~0.65 窄带,
用户无法从分数区分匹配强弱。本脚本在 eval_set_v1+v2 合并 58 例上
逐例跑与线上一致的召回路径(career_pathway_service 内部原语),
收集全部 (case, role) 原始分分布,选分段线性锚点 p_low/p_high:

    sem_cal = clip((raw - p_low) / (p_high - p_low), 0, 1)

锚点理由:p_low=p5、p_high=p95 —— 中间 90% 的分对线性拉开到 [0,1],
头部/尾部 5% 饱和到 1/0(饱和区不影响排序,单调性保持)。

校准是单调变换,粗召回列表内部顺序不变;但 rank_careers 的
role_score = 0.15*cov + 0.70*sem + 0.15*trend 里 cov/trend 与 sem
是加法关系,非仿射的 sem 变换理论上可能改变跨岗排序。因此本脚本
内置排序不变性探针:对同一批召回结果分别用 raw/cal 语义分跑
GraphPathPlannerV3.analyze_role,对比公式排序的 Hit@1/NDCG@5 是否与
raw 完全一致,并对多组候选锚点做敏感性检查。

运行:python -m experiments.fit_score_calibration
前置:postgres(migration 006 + build_job_vectors)已就绪。
产出:data/gold/score_calibration_v1.json
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"

os.chdir(ROOT)

from experiments.eval_matching_v4 import load_cases  # noqa: E402

CALIBRATION_PATH = ROOT / "data" / "gold" / "score_calibration_v1.json"
TOP_N = 30  # 拟合分布用更大的召回窗,充分覆盖尾部
PROBE_TOP_N = 10  # 与线上/评估一致的召回窗,探针按此口径算指标
PROBE_TOP_K = 5
# 候选锚点(分位数口径),探针逐组验证排序不变性后选首选组写入参数文件
ANCHOR_CANDIDATES = [
    ("p5_p95", 5.0, 95.0),
    ("p10_p90", 10.0, 90.0),
    ("min_max", 0.0, 100.0),
]
PRIMARY_ANCHOR = "p5_p95"


def collect_raw_scores(cases: list[dict]) -> tuple[list[float], list[dict]]:
    """逐例复用线上召回原语,收集原始 cosine 分布。"""
    import numpy as np

    from app.schemas.domain import UserProfile
    from app.services import career_pathway_service as cps

    cps.recall_preflight()
    engine = cps._load_engine()
    all_scores: list[float] = []
    per_case: list[dict] = []
    for i, case in enumerate(cases, 1):
        profile = UserProfile(
            user_id="calib-fit", skills=case["skills"], target_role=case.get("target_role")
        )
        vec = engine.encode(cps._profile_to_query_text(profile), normalize_embeddings=True)
        rows = cps._recall_topn(vec, TOP_N, cps.DSN)
        scores = [round(float(r["score"]), 4) for r in rows if r["job_id"]]
        all_scores.extend(scores)
        per_case.append(
            {
                "name": case["name"],
                "scores": scores,
                "job_ids": [r["job_id"] for r in rows],
                "top1": scores[0] if scores else None,
            }
        )
        print(f"[{i}/{len(cases)}] {case['name']}: n={len(scores)} "
              f"min={min(scores):.4f} max={max(scores):.4f}", flush=True)
    return all_scores, per_case


def distribution_stats(scores: list[float]) -> dict:
    import numpy as np

    arr = np.asarray(sorted(scores), dtype=float)
    qs = np.percentile(arr, [1, 5, 10, 25, 50, 75, 90, 95, 99])
    return {
        "n_pairs": int(arr.size),
        "min": round(float(arr[0]), 4),
        "p1": round(float(qs[0]), 4),
        "p5": round(float(qs[1]), 4),
        "p10": round(float(qs[2]), 4),
        "p25": round(float(qs[3]), 4),
        "p50": round(float(qs[4]), 4),
        "p75": round(float(qs[5]), 4),
        "p90": round(float(qs[6]), 4),
        "p95": round(float(qs[7]), 4),
        "p99": round(float(qs[8]), 4),
        "max": round(float(arr[-1]), 4),
        "mean": round(float(arr.mean()), 4),
        "std": round(float(arr.std()), 4),
    }


def make_calibrator(p_low: float, p_high: float):
    span = p_high - p_low

    def cal(raw: float) -> float:
        if span <= 0:
            return raw
        return max(0.0, min(1.0, (raw - p_low) / span))

    return cal


def probe_order_invariance(
    cases: list[dict], per_case_scores: list[dict], p_low: float, p_high: float
) -> dict:
    """对每组锚点,用 raw/cal 两套语义分跑 analyze_role,对比公式排序指标。

    走与 rank_careers 相同的公式排序(稳定排序、role_score 降序、top_k 截断),
    只关 semantic 输入的口径差异。
    """
    from app.schemas.domain import UserProfile
    from app.services.graph_path_planner_v3 import GraphPathPlannerV3

    cal = make_calibrator(p_low, p_high)

    def metrics_for(transform) -> tuple[dict, int, list[str]]:
        hit1 = hit5 = mrr_sum = ndcg_sum = 0.0
        mismatched = 0
        details: list[str] = []
        for case, pc in zip(cases, per_case_scores):
            profile = UserProfile(
                user_id="calib-probe", skills=case["skills"], target_role=case.get("target_role")
            )
            rows = []
            for raw, job_id in zip(pc["scores"][:PROBE_TOP_N], pc["job_ids"][:PROBE_TOP_N]):
                analysis = GraphPathPlannerV3.analyze_role(
                    profile=profile, target_job_id=job_id,
                    semantic_score=round(transform(raw), 4),
                )
                rows.append((analysis.role_score, job_id))
            rows.sort(key=lambda r: r[0], reverse=True)  # 与 ranked.sort 一致:稳定排序
            ranked_ids = [job_id for _, job_id in rows]
            topk = ranked_ids[:PROBE_TOP_K]
            rel = set(case["relevant_ids"])
            hit1 += int(bool(ranked_ids) and ranked_ids[0] in rel)
            hit5 += int(any(j in rel for j in topk))
            for rank, j in enumerate(topk, start=1):
                if j in rel:
                    mrr_sum += 1.0 / rank
                    break
            dcg = sum(1.0 / math.log2(r + 1) for r, j in enumerate(topk, start=1) if j in rel)
            idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(rel), PROBE_TOP_K) + 1))
            ndcg_sum += dcg / idcg if idcg else 0.0
            details.append(ranked_ids[0] if ranked_ids else "")
        n = len(cases)
        return (
            {
                "hit@1": round(hit1 / n, 4),
                "hit@5": round(hit5 / n, 4),
                "mrr": round(mrr_sum / n, 4),
                "ndcg@5": round(ndcg_sum / n, 4),
            },
            mismatched,
            details,
        )

    m_raw, _, top1_raw = metrics_for(lambda s: s)
    m_cal, _, top1_cal = metrics_for(cal)
    same = m_raw == m_cal and top1_raw == top1_cal
    changed_cases = [
        c["name"] for c, a, b in zip(cases, top1_raw, top1_cal) if a != b
    ]
    return {"raw": m_raw, "cal": m_cal, "identical": same, "top1_changed_cases": changed_cases}


def main() -> dict:
    cases, unresolved = load_cases()
    print(f">>> {len(cases)} 例拟合集(未解析相关岗: {len(unresolved)})", flush=True)

    all_scores, per_case = collect_raw_scores(cases)
    stats = distribution_stats(all_scores)
    print("\n>>> 原始 cosine 分布统计:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # 探针:逐锚点候选组验证公式排序不变性(coverage/trend 与语义分口径无关,
    # 同一批召回结果只需替换 analyze_role 的 semantic 输入)。
    print("\n>>> 排序不变性探针(公式排序 raw vs cal):")
    import numpy as np

    anchor_report: dict[str, dict] = {}
    chosen: tuple[str, float, float] | None = None
    for name, q_lo, q_hi in ANCHOR_CANDIDATES:
        p_low = round(float(np.percentile(sorted(all_scores), q_lo)), 4)
        p_high = round(float(np.percentile(sorted(all_scores), q_hi)), 4)
        probe = probe_order_invariance(cases, per_case, p_low, p_high)
        anchor_report[name] = {"p_low": p_low, "p_high": p_high, **probe}
        print(f"  {name}: p_low={p_low} p_high={p_high} "
              f"identical={probe['identical']} raw={probe['raw']} cal={probe['cal']}")
        if name == PRIMARY_ANCHOR:
            chosen = (name, p_low, p_high)

    if chosen is None:
        raise RuntimeError(f"首选锚点 {PRIMARY_ANCHOR} 不在候选列表")
    name, p_low, p_high = chosen
    payload = {
        "version": "score_calibration_v1",
        "formula": "sem_cal = clip((raw - p_low) / (p_high - p_low), 0, 1)",
        "p_low": p_low,
        "p_high": p_high,
        "anchor_choice": (
            f"{name}: 中间 90% 分对线性映射到 [0,1],头尾 5% 饱和;饱和区不改变排序"
            "(clip 为单调映射)。候选组探针排序不变性见 anchor_report。"
        ),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "n_pairs": stats["n_pairs"],
        "recall_top_n": TOP_N,
        "raw_distribution_stats": stats,
        "anchor_report": anchor_report,
    }
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] 参数已写入 {CALIBRATION_PATH}")
    return payload


if __name__ == "__main__":
    main()
