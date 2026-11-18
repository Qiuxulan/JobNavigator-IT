"""matching v5 评估:分数校准(单调映射)回归验证。

背景:2026-11-06 引入分数校准(app/services/score_calibration.py,
experiments/fit_score_calibration.py → data/gold/score_calibration_v1.json),
把挤在 0.5~0.65 窄带的原始 cosine 单调映射到 [0,1],并给推荐项打
置信度标签(high/medium/low)。

校准对粗召回是单调变换,列表内部排序不变;但 rank_careers 的
role_score = 0.15*cov + 0.70*sem + 0.15*trend 中 sem 与 cov/trend 是
加法关系,非仿射映射理论上可能改变跨岗公式排序;DeepSeek 精排消费
prompt 里的 match_scores,分数口径变化也可能影响 LLM 重排。因此本
脚本做两件事:
  1. 回归:重跑 58 例,与基线 reports/eval/matching_v4_eval.json 逐例
     对比 v4_embedding / v4_llm 两个变体的排序与 Hit@1/NDCG@5;
  2. 分散度:对公式排序变体,分别在校准关闭(恒等)/开启下收集
     final_score,报告 std/min/max,证明分数分布拉开。

运行:python -m experiments.eval_matching_v5_calibration
前置:同 experiments/eval_matching_v4(pgres + 向量已灌;.env 里 LLM key)。
报告:reports/eval/matching_v5_calibration_eval.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"

os.chdir(ROOT)

import statistics  # noqa: E402

from experiments import eval_matching_v4 as m4  # noqa: E402

REPORT_PATH = ROOT / "reports" / "eval" / "matching_v5_calibration_eval.json"


def collect_final_scores(cases: list[dict]) -> dict[str, list[float]]:
    """公式排序(关 LLM 精排)下每例 top_k 的 final_score 列表。"""
    from app.core.config import settings
    from app.schemas.domain import UserPreference, UserProfile
    from app.services.career_pathway_service import rank_careers

    settings.llm_rerank_enabled = False
    out: dict[str, list[float]] = {}
    for case in cases:
        profile = UserProfile(user_id="eval", skills=case["skills"], target_role=case.get("target_role"))
        rows = rank_careers(profile, UserPreference(), top_n=m4.RECALL_TOP_N)
        out[case["name"]] = [row["role_score"] for row in rows[: m4.TOP_K]]
    return out


def dispersion(scores_by_case: dict[str, list[float]]) -> dict:
    flat = [s for scores in scores_by_case.values() for s in scores]
    return {
        "n_scores": len(flat),
        "std": round(statistics.pstdev(flat), 4) if len(flat) > 1 else 0.0,
        "min": round(min(flat), 4) if flat else None,
        "max": round(max(flat), 4) if flat else None,
        "mean": round(statistics.fmean(flat), 4) if flat else None,
    }


def main() -> dict:
    cases, unresolved = m4.load_cases()
    print(f">>> {len(cases)} 例评测(未解析相关岗: {len(unresolved)})", flush=True)

    v4_report = json.loads(m4.REPORT_PATH.read_text(encoding="utf-8"))
    base_per_case = {c["name"]: c for c in v4_report["per_case"]}

    def invariance(base_top5: dict[str, list[str]], new: dict[str, list[str]]) -> dict:
        changed = [
            c["name"]
            for c in cases
            if base_top5.get(c["name"], [])[: m4.TOP_K] != new.get(c["name"], [])[: m4.TOP_K]
        ]
        return {"identical": not changed, "n_changed": len(changed), "changed_cases": changed}

    # ---- 1a. 线上口径:校准开启 ----
    rankings_emb: dict[str, list[str]] = {}
    rankings_llm: dict[str, list[str]] = {}
    llm_failures = 0
    for i, case in enumerate(cases, 1):
        rankings_emb[case["name"]] = m4.rank_case(case, llm_rerank=False)
        rankings_llm[case["name"]] = m4.rank_case(case, llm_rerank=True)
        if rankings_llm[case["name"]] == rankings_emb[case["name"]]:
            llm_failures += 1
        print(f"[{i}/{len(cases)}] cal {case['name']}: emb={rankings_emb[case['name']][:3]} "
              f"llm={rankings_llm[case['name']][:3]}", flush=True)

    # ---- 1b. 同会话对照:恒等校准(等价校准前),隔离 LLM 服务 run 间差异 ----
    from app.services import score_calibration

    real_calibrate = score_calibration.calibrate_semantic
    rankings_emb_id: dict[str, list[str]] = {}
    rankings_llm_id: dict[str, list[str]] = {}
    try:
        score_calibration.calibrate_semantic = lambda raw: raw
        for i, case in enumerate(cases, 1):
            rankings_emb_id[case["name"]] = m4.rank_case(case, llm_rerank=False)
            rankings_llm_id[case["name"]] = m4.rank_case(case, llm_rerank=True)
            print(f"[{i}/{len(cases)}] id  {case['name']}: emb={rankings_emb_id[case['name']][:3]} "
                  f"llm={rankings_llm_id[case['name']][:3]}", flush=True)
    finally:
        score_calibration.calibrate_semantic = real_calibrate

    m_emb = m4.metrics(cases, rankings_emb)
    m_llm = m4.metrics(cases, rankings_llm)
    m_emb_id = m4.metrics(cases, rankings_emb_id)
    m_llm_id = m4.metrics(cases, rankings_llm_id)

    inv_emb_vs_v4 = invariance(
        {n: base_per_case[n]["v4_embedding_top5"] for n in rankings_emb}, rankings_emb
    )
    inv_llm_vs_v4 = invariance(
        {n: base_per_case[n]["v4_llm_top5"] for n in rankings_llm}, rankings_llm
    )
    # 校准的因果效应(同会话内对比,排除 LLM 服务 run 间差异)
    inv_emb_cal_vs_id = invariance(rankings_emb_id, rankings_emb)
    inv_llm_cal_vs_id = invariance(rankings_llm_id, rankings_llm)
    # 恒等对照能否复现 v4 基线(检验确定性路径的可复现性)
    inv_emb_id_vs_v4 = invariance(
        {n: base_per_case[n]["v4_embedding_top5"] for n in rankings_emb_id}, rankings_emb_id
    )
    inv_llm_id_vs_v4 = invariance(
        {n: base_per_case[n]["v4_llm_top5"] for n in rankings_llm_id}, rankings_llm_id
    )

    # ---- 2. 分散度:校准关(恒等 monkeypatch)/开,各收集一遍 final_score ----
    try:
        score_calibration.calibrate_semantic = lambda raw: raw  # 恒等:等价校准前
        scores_before = collect_final_scores(cases)
    finally:
        score_calibration.calibrate_semantic = real_calibrate
    scores_after = collect_final_scores(cases)
    d_before = dispersion(scores_before)
    d_after = dispersion(scores_after)

    calibration_params = score_calibration._load_params()

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "eval_sets": [p.name for p in m4.EVAL_SET_PATHS],
        "n_cases": len(cases),
        "recall_top_n": m4.RECALL_TOP_N,
        "top_k": m4.TOP_K,
        "embedding_model": "Qwen/Qwen3-Embedding-4B",
        "calibration": {
            "version": (calibration_params or {}).get("version"),
            "formula": (calibration_params or {}).get("formula"),
            "p_low": (calibration_params or {}).get("p_low"),
            "p_high": (calibration_params or {}).get("p_high"),
            "raw_distribution_stats": (calibration_params or {}).get("raw_distribution_stats"),
            "sort_key_note": (
                "rank_careers 展示分(semantic/final_score/breakdown/confidence)走校准口径,"
                "排序键用原始分按同公式重算(app/services/career_pathway_service._raw_role_score),"
                "因为非仿射单调变换会改变 0.15*cov+0.70*sem+0.15*trend 的加法排序"
                "(探针证据见 data/gold/score_calibration_v1.json anchor_report)。"
            ),
        },
        "variants": {
            "v4_baseline_embedding": {
                "desc": "校准前基线(Qwen3-4B + 公式排序,取自 matching_v4_eval.json)",
                "metrics": v4_report["variants"]["v4_embedding"]["metrics"],
            },
            "v4_baseline_llm": {
                "desc": "校准前基线(Qwen3-4B + DeepSeek 精排,线上默认,取自 matching_v4_eval.json)",
                "metrics": v4_report["variants"]["v4_llm"]["metrics"],
            },
            "v5_embedding": {
                "desc": "分数校准后(Qwen3-4B + 公式排序,无 LLM 精排)",
                "metrics": m_emb,
                "order_invariance_vs_v4": inv_emb_vs_v4,
                "order_invariance_vs_identity_same_session": inv_emb_cal_vs_id,
            },
            "v5_identity_embedding": {
                "desc": "同会话对照:校准恒等(等价校准前),检验确定性路径可复现性",
                "metrics": m_emb_id,
                "order_invariance_vs_v4": inv_emb_id_vs_v4,
            },
            "v5_llm": {
                "desc": "分数校准后(Qwen3-4B + 公式排序 + DeepSeek 全局精排,线上默认)",
                "metrics": m_llm,
                "order_invariance_vs_v4": inv_llm_vs_v4,
                "order_invariance_vs_identity_same_session": inv_llm_cal_vs_id,
            },
            "v5_identity_llm": {
                "desc": "同会话对照:校准恒等 + DeepSeek 精排,隔离 LLM 服务 run 间差异",
                "metrics": m_llm_id,
                "order_invariance_vs_v4": inv_llm_id_vs_v4,
            },
        },
        "final_score_dispersion": {
            "before_calibration": d_before,
            "after_calibration": d_after,
        },
        "llm_unchanged_cases": llm_failures,
        "unresolved_role_names": unresolved,
        "per_case": [
            {
                "name": c["name"],
                "eval_set": c["eval_set"],
                "target_role": c.get("target_role"),
                "relevant_ids": c["relevant_ids"],
                "v5_embedding_top5": rankings_emb[c["name"]][: m4.TOP_K],
                "v5_llm_top5": rankings_llm[c["name"]][: m4.TOP_K],
                "v5_identity_embedding_top5": rankings_emb_id[c["name"]][: m4.TOP_K],
                "v5_identity_llm_top5": rankings_llm_id[c["name"]][: m4.TOP_K],
            }
            for c in cases
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    v4e = v4_report["variants"]["v4_embedding"]["metrics"]
    v4l = v4_report["variants"]["v4_llm"]["metrics"]
    print("\n# 校准前后对比(58 例)")
    print("| variant | Hit@1 | Hit@5 | MRR | NDCG@5 | 排序 vs v4基线 | 排序 vs 同会话恒等 |")
    print("|---|---|---|---|---|---|---|")
    print(f"| v4_embedding(基线) | {v4e['hit@1']} | {v4e['hit@5']} | {v4e['mrr']} | {v4e['ndcg@5']} | - | - |")
    print(f"| v5_embedding(校准后) | {m_emb['hit@1']} | {m_emb['hit@5']} | {m_emb['mrr']} | {m_emb['ndcg@5']} | "
          f"{inv_emb_vs_v4['identical']}({inv_emb_vs_v4['n_changed']}) | {inv_emb_cal_vs_id['identical']} |")
    print(f"| v5_identity_embedding(对照) | {m_emb_id['hit@1']} | {m_emb_id['hit@5']} | {m_emb_id['mrr']} | {m_emb_id['ndcg@5']} | "
          f"{inv_emb_id_vs_v4['identical']}({inv_emb_id_vs_v4['n_changed']}) | - |")
    print(f"| v4_llm(基线,线上) | {v4l['hit@1']} | {v4l['hit@5']} | {v4l['mrr']} | {v4l['ndcg@5']} | - | - |")
    print(f"| v5_llm(校准后,线上) | {m_llm['hit@1']} | {m_llm['hit@5']} | {m_llm['mrr']} | {m_llm['ndcg@5']} | "
          f"{inv_llm_vs_v4['identical']}({inv_llm_vs_v4['n_changed']}) | {inv_llm_cal_vs_id['identical']}({inv_llm_cal_vs_id['n_changed']}) |")
    print(f"| v5_identity_llm(对照) | {m_llm_id['hit@1']} | {m_llm_id['hit@5']} | {m_llm_id['mrr']} | {m_llm_id['ndcg@5']} | "
          f"{inv_llm_id_vs_v4['identical']}({inv_llm_id_vs_v4['n_changed']}) | - |")
    print(f"\n# final_score 分散度(top-{m4.TOP_K} x {len(cases)} 例)")
    print(f"  校准前: std={d_before['std']} min={d_before['min']} max={d_before['max']} mean={d_before['mean']}")
    print(f"  校准后: std={d_after['std']} min={d_after['min']} max={d_after['max']} mean={d_after['mean']}")
    print(f"\n[done] 报告已写入 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    main()
