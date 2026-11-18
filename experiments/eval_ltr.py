"""LTR 排序器评估(matching v6,2026-11-08)。

在 eval_set_v1 + eval_set_v2(58 例,与 matching v4/v5 评估同一套)上对比
三条精排路径(都走线上同一条 rank_careers 代码路径,只切 JOBNAV_RANKER):
  - formula :纯 v3.1 公式排序(无精排,基线);
  - ltr     :本地 LightGBM LambdaRank(models/ltr_ranker_v1.txt);
  - llm     :DeepSeek 全局精排(matching v4 线上原路径,教师)。

指标:Hit@1 / Hit@5 / MRR / NDCG@5(二元相关,与 v4/v5 报告同口径,可直接对比
reports/eval/matching_v5_calibration_eval.json)。
报告:reports/eval/ltr_eval.json。若 ltr 不如 formula,如实写入报告并提示不要默认启用。

运行:python -m experiments.eval_ltr
前置:postgres + 岗位向量就绪;.env DeepSeek key 可用(llm 路径需要);
     models/ltr_ranker_v1.txt 已训练(ltr 路径需要)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"
os.chdir(ROOT)

from app.core.config import settings  # noqa: E402

EVAL_SET_PATHS = [
    ROOT / "data" / "gold" / "eval_set_v1.json",
    ROOT / "data" / "gold" / "eval_set_v2.json",
]
REPORT_PATH = ROOT / "reports" / "eval" / "ltr_eval.json"
MODEL_PATH = ROOT / "models" / "ltr_ranker_v1.txt"
TOP_K = 5
RECALL_TOP_N = 10


def load_cases() -> list[dict]:
    from app.services.career_catalog import load_roles

    roles = load_roles()
    name2id = {r["role_name"]: r["role_id"] for r in roles.values()}
    cases: list[dict] = []
    for path in EVAL_SET_PATHS:
        for case in json.loads(path.read_text(encoding="utf-8")):
            case["relevant_ids"] = sorted({name2id[n] for n in case["relevant_role_names"] if n in name2id})
            cases.append(case)
    return cases


def rank_case(case: dict, mode: str) -> list[str]:
    from app.schemas.domain import UserPreference, UserProfile
    from app.services.career_pathway_service import rank_careers

    os.environ["JOBNAV_RANKER"] = mode
    settings.llm_rerank_enabled = True  # llm 路径需要;ltr/formula 路径不读它
    profile = UserProfile(user_id="eval", skills=case["skills"], target_role=case.get("target_role"))
    rows = rank_careers(profile, UserPreference(), top_n=RECALL_TOP_N)
    return [row["job_id"] for row in rows]


def metrics(cases: list[dict], rankings: dict[str, list[str]]) -> dict:
    import math

    hit1 = hit5 = mrr_sum = ndcg_sum = 0.0
    n = len(cases)
    for case in cases:
        rel = set(case["relevant_ids"])
        ranked = rankings.get(case["name"], [])
        topk = ranked[:TOP_K]
        hit1 += int(bool(ranked) and ranked[0] in rel)
        hit5 += int(any(j in rel for j in topk))
        for rank, j in enumerate(topk, start=1):
            if j in rel:
                mrr_sum += 1.0 / rank
                break
        dcg = sum(1.0 / math.log2(r + 1) for r, j in enumerate(topk, start=1) if j in rel)
        idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(rel), TOP_K) + 1))
        ndcg_sum += dcg / idcg if idcg else 0.0
    return {
        "n_cases": n,
        "hit@1": round(hit1 / n, 4),
        "hit@5": round(hit5 / n, 4),
        "mrr": round(mrr_sum / n, 4),
        "ndcg@5": round(ndcg_sum / n, 4),
    }


def main() -> dict:
    cases = load_cases()
    print(f">>> {len(cases)} 例评测;model 存在: {MODEL_PATH.exists()}", flush=True)

    rankings: dict[str, dict[str, list[str]]] = {"formula": {}, "ltr": {}, "llm": {}}
    for i, case in enumerate(cases, 1):
        for mode in ("formula", "ltr", "llm"):
            rankings[mode][case["name"]] = rank_case(case, mode)
        print(f"[{i}/{len(cases)}] {case['name']}: "
              f"formula={rankings['formula'][case['name']][:3]} "
              f"ltr={rankings['ltr'][case['name']][:3]} "
              f"llm={rankings['llm'][case['name']][:3]}", flush=True)

    m = {mode: metrics(cases, rankings[mode]) for mode in rankings}

    verdict = "enable"
    notes = []
    if not MODEL_PATH.exists():
        verdict = "model_missing"
        notes.append("模型文件缺失,ltr 路径实际回退为公式排序。")
    if m["ltr"]["ndcg@5"] < m["formula"]["ndcg@5"] or m["ltr"]["hit@1"] < m["formula"]["hit@1"]:
        verdict = "keep_disabled"
        notes.append("LTR 低于 formula 基线,不建议默认启用 JOBNAV_RANKER=ltr。")
    gap_llm = round(m["llm"]["ndcg@5"] - m["ltr"]["ndcg@5"], 4)
    notes.append(f"LTR 与 LLM 教师差距(NDCG@5): {gap_llm}。")

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "eval_sets": [p.name for p in EVAL_SET_PATHS],
        "n_cases": len(cases),
        "recall_top_n": RECALL_TOP_N,
        "top_k": TOP_K,
        "model": str(MODEL_PATH),
        "llm_rerank_model": settings.llm_model,
        "variants": {
            "formula": {"desc": "纯 v3.1 公式排序(无精排)", "metrics": m["formula"]},
            "ltr": {"desc": "本地 LightGBM LambdaRank(DeepSeek 蒸馏)", "metrics": m["ltr"]},
            "llm": {"desc": "DeepSeek 全局精排(教师,matching v4)", "metrics": m["llm"]},
        },
        "deltas": {
            "ltr_vs_formula": {k: round(m["ltr"][k] - m["formula"][k], 4)
                               for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
            "ltr_vs_llm": {k: round(m["ltr"][k] - m["llm"][k], 4)
                           for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
        },
        "verdict": verdict,
        "notes": notes,
        "per_case": [
            {
                "name": c["name"],
                "target_role": c.get("target_role"),
                "relevant_ids": c["relevant_ids"],
                "formula_top5": rankings["formula"][c["name"]][:TOP_K],
                "ltr_top5": rankings["ltr"][c["name"]][:TOP_K],
                "llm_top5": rankings["llm"][c["name"]][:TOP_K],
            }
            for c in cases
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n# 三路径对比(58 例)")
    print("| variant | Hit@1 | Hit@5 | MRR | NDCG@5 |")
    print("|---|---|---|---|---|")
    for mode in ("formula", "ltr", "llm"):
        r = m[mode]
        print(f"| {mode} | {r['hit@1']} | {r['hit@5']} | {r['mrr']} | {r['ndcg@5']} |")
    print(f"\nverdict: {verdict}; notes: {notes}")
    print(f"[done] 报告已写入 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    main()
