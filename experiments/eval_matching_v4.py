"""matching v4 评估:Qwen3-Embedding-4B (+DeepSeek LLM 精排) vs JobBERT-v3 基线。

背景:2026-11-05 岗位向量模型升级为 Qwen/Qwen3-Embedding-4B(2560 维,
migration 006),并在 rank_careers 增加可选的 DeepSeek 一次性全局精排层
(app/services/llm_reranker.py)。

本脚本在 eval_set_v1 + eval_set_v2(58 例)上对比三版:
  - v3_baseline :JobBERT-v3,数字直接取 reports/eval/matching_v3_eval.json
                 的最优权重 (0.15/0.70/0.15/0.00) 结果,不重新跑;
  - v4_embedding:新 embedding + v3.1 公式排序(关闭 LLM 精排);
  - v4_llm      :新 embedding + 公式排序 + DeepSeek 精排(线上默认路径)。

两个 v4 变体都走线上同一条 rank_careers 代码路径(只是开关精排),
保证评估与线上一致。指标:NDCG@5 / Hit@1 / Hit@5 / MRR。

运行:python -m experiments.eval_matching_v4
前置:postgres 已跑过 migration 006 + build_job_vectors(新模型重灌);
     .env 里 DeepSeek key 可用(精排变体需要)。
报告:reports/eval/matching_v4_eval.json
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

from app.core.config import settings  # noqa: E402

EVAL_SET_PATHS = [
    ROOT / "data" / "gold" / "eval_set_v1.json",
    ROOT / "data" / "gold" / "eval_set_v2.json",
]
V3_REPORT_PATH = ROOT / "reports" / "eval" / "matching_v3_eval.json"
REPORT_PATH = ROOT / "reports" / "eval" / "matching_v4_eval.json"
TOP_K = 5
RECALL_TOP_N = 10


def load_cases() -> tuple[list[dict], list[dict]]:
    from app.services.career_catalog import load_roles

    roles = load_roles()
    name2id = {r["role_name"]: r["role_id"] for r in roles.values()}
    cases: list[dict] = []
    unresolved: list[dict] = []
    for path in EVAL_SET_PATHS:
        for case in json.loads(path.read_text(encoding="utf-8")):
            case = dict(case, eval_set=path.stem)
            skipped = [n for n in case["relevant_role_names"] if n not in name2id]
            if skipped:
                unresolved.append({"case": case["name"], "eval_set": path.stem, "skipped": skipped})
            case["relevant_ids"] = sorted({name2id[n] for n in case["relevant_role_names"] if n in name2id})
            cases.append(case)
    return cases, unresolved


def rank_case(case: dict, llm_rerank: bool) -> list[str]:
    """走线上 rank_careers 路径,返回 job_id 排序。"""
    from app.schemas.domain import UserPreference, UserProfile
    from app.services.career_pathway_service import rank_careers

    settings.llm_rerank_enabled = llm_rerank
    profile = UserProfile(user_id="eval", skills=case["skills"], target_role=case.get("target_role"))
    rows = rank_careers(profile, UserPreference(), top_n=RECALL_TOP_N)
    return [row["job_id"] for row in rows]


def metrics(cases: list[dict], rankings: dict[str, list[str]]) -> dict:
    """rankings: case_name -> job_id 排序。relevance = 二元(在 relevant_ids 内)。"""
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
    cases, unresolved = load_cases()
    print(f">>> {len(cases)} 例评测(未解析相关岗: {len(unresolved)})", flush=True)

    v3_report = json.loads(V3_REPORT_PATH.read_text(encoding="utf-8"))
    v3_best = v3_report["best"]["metrics"]

    rankings_emb: dict[str, list[str]] = {}
    rankings_llm: dict[str, list[str]] = {}
    llm_failures = 0
    for i, case in enumerate(cases, 1):
        rankings_emb[case["name"]] = rank_case(case, llm_rerank=False)
        rankings_llm[case["name"]] = rank_case(case, llm_rerank=True)
        if rankings_llm[case["name"]] == rankings_emb[case["name"]]:
            llm_failures += 1  # 顺序没变,可能是降级(也可能 LLM 认同原序)
        print(f"[{i}/{len(cases)}] {case['name']}: emb={rankings_emb[case['name']][:3]} "
              f"llm={rankings_llm[case['name']][:3]}", flush=True)

    m_emb = metrics(cases, rankings_emb)
    m_llm = metrics(cases, rankings_llm)

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "eval_sets": [p.name for p in EVAL_SET_PATHS],
        "n_cases": len(cases),
        "recall_top_n": RECALL_TOP_N,
        "top_k": TOP_K,
        "embedding_model": "Qwen/Qwen3-Embedding-4B",
        "llm_rerank_model": settings.llm_model,
        "variants": {
            "v3_baseline": {
                "desc": "TechWolf/JobBERT-v3 + v3.1 公式排序(线上 v3 最优权重)",
                "source": "reports/eval/matching_v3_eval.json",
                "metrics": {k: v3_best[k] for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
            },
            "v4_embedding": {
                "desc": "Qwen3-Embedding-4B + v3.1 公式排序(无 LLM 精排)",
                "metrics": m_emb,
            },
            "v4_llm": {
                "desc": "Qwen3-Embedding-4B + 公式排序 + DeepSeek 全局精排(线上默认)",
                "metrics": m_llm,
            },
        },
        "deltas_vs_baseline": {
            "v4_embedding": {k: round(m_emb[k] - v3_best[k], 4)
                             for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
            "v4_llm": {k: round(m_llm[k] - v3_best[k], 4)
                       for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
        },
        "llm_unchanged_cases": llm_failures,
        "unresolved_role_names": unresolved,
        "per_case": [
            {
                "name": c["name"],
                "eval_set": c["eval_set"],
                "target_role": c.get("target_role"),
                "relevant_ids": c["relevant_ids"],
                "v4_embedding_top5": rankings_emb[c["name"]][:TOP_K],
                "v4_llm_top5": rankings_llm[c["name"]][:TOP_K],
            }
            for c in cases
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n# 三版对比(58 例)")
    print("| variant | Hit@1 | Hit@5 | MRR | NDCG@5 |")
    print("|---|---|---|---|---|")
    print(f"| v3_baseline(JobBERT) | {v3_best['hit@1']} | {v3_best['hit@5']} | "
          f"{v3_best['mrr']} | {v3_best['ndcg@5']} |")
    print(f"| v4_embedding(Qwen3-4B) | {m_emb['hit@1']} | {m_emb['hit@5']} | "
          f"{m_emb['mrr']} | {m_emb['ndcg@5']} |")
    print(f"| v4_llm(Qwen3-4B+DeepSeek) | {m_llm['hit@1']} | {m_llm['hit@5']} | "
          f"{m_llm['mrr']} | {m_llm['ndcg@5']} |")
    print(f"\n[done] 报告已写入 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    main()
