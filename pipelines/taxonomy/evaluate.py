"""
推荐效果评估 - 第三版(加入 Hit@1 / MRR,提升小库下的区分度)

改进:
  1. 评测集用 relevant_role_names(岗位名,稳定)标注 ground truth,
     运行时自动用当前岗位库把名字解析成 role_id —— 岗位库重编号也不失效
  2. 修正 NDCG 的 IDCG:理想排序 = 所有相关岗位排最前
  3. 评测集外置到 data/gold/eval_set_v1.json
  4. 【v3】新增 Hit@1 与 MRR:
     - Hit@5 在小岗位库(69个)上区分度低(几乎恒为1.0),
       Hit@1 看"目标岗是否排第一"、MRR 看"第一个命中的排名倒数",
       二者能暴露精排排序质量(如趋势占位表把泛AI岗顶到精确岗之前)。

指标:Hit@1 / Hit@K / MRR / NDCG@K
运行:python -m pipelines.taxonomy.evaluate

说明:GAMMA 在 18 用户上的敏感性显示 0.01~0.02 区间 NDCG 最优
     (0.01=0.840, 0.02=0.836,差异在噪声内;0.06 在小样本下的"更优"已被证伪)。
     当前定 GAMMA=0.02。
"""

import json
import math
from pathlib import Path

import numpy as np

from app.schemas.domain import UserPreference, UserProfile
from app.services import recommender as R

TOP_K = 5
EVAL_SET_PATH = Path("data/gold/eval_set_v1.json")
ROLES_JSON = Path("data/gold/fine_grained_roles_v1.json")

FALLBACK_EVAL_SET = [
    {"name": "ML工程师求职者", "skills": ["Python", "SQL", "Machine Learning", "PyTorch"],
     "target_role": "Machine Learning Engineer",
     "relevant_role_names": ["Machine Learning Engineer", "Machine Learning Research Engineer", "Data Scientist"]},
    {"name": "Java后端求职者", "skills": ["Java", "Spring", "MySQL", "REST API"],
     "target_role": "Backend Java Engineer",
     "relevant_role_names": ["Backend Java Engineer", "Cloud Java Engineer"]},
    {"name": "前端React求职者", "skills": ["JavaScript", "React", "TypeScript", "CSS"],
     "target_role": "Frontend Engineer",
     "relevant_role_names": ["Frontend React Engineer", "Full-Stack JavaScript Engineer", "React Native Engineer"]},
    {"name": "DevOps求职者", "skills": ["Docker", "Kubernetes", "AWS", "CI/CD", "Terraform"],
     "target_role": "DevOps Engineer",
     "relevant_role_names": ["DevOps Engineer", "Azure DevOps Engineer", "Node.js DevOps Engineer"]},
    {"name": "数据工程求职者", "skills": ["Python", "SQL", "Spark", "ETL", "Airflow"],
     "target_role": "Data Engineer",
     "relevant_role_names": ["Data Engineer", "AI Data Engineer"]},
]


def load_name2id():
    """从当前岗位库建 岗位名 -> role_id 映射"""
    with ROLES_JSON.open(encoding="utf-8") as f:
        roles = json.load(f)
    return {r["role_name"]: r["role_id"] for r in roles}


def load_eval_set(name2id):
    """读评测集;把 relevant_role_names 解析成 relevant_role_ids。
    兼容旧格式:若直接写了 relevant_role_ids 也能用。"""
    if EVAL_SET_PATH.exists():
        with EVAL_SET_PATH.open(encoding="utf-8") as f:
            raw = json.load(f)
        src = str(EVAL_SET_PATH)
    else:
        raw = FALLBACK_EVAL_SET
        src = "内置兜底集"

    eval_set = []
    warnings = []
    for case in raw:
        if "relevant_role_ids" in case and case["relevant_role_ids"]:
            ids = case["relevant_role_ids"]
        else:
            ids = []
            for nm in case.get("relevant_role_names", []):
                rid = name2id.get(nm)
                if rid:
                    ids.append(rid)
                else:
                    warnings.append(f"  [{case['name']}] 岗位名 '{nm}' 在当前岗位库找不到,已跳过")
        eval_set.append({**case, "relevant_role_ids": ids})
    return eval_set, src, warnings


def hit_at_k(rec_items, relevant_ids, k):
    rel = set(relevant_ids)
    return 1 if any(it.job.job_id in rel for it in rec_items[:k]) else 0


def hit_at_1(rec_items, relevant_ids):
    """Top-1 是否命中任一相关岗位。比 Hit@5 区分度高得多。"""
    rel = set(relevant_ids)
    if not rec_items:
        return 0
    return 1 if rec_items[0].job.job_id in rel else 0


def mrr(rec_items, relevant_ids, k):
    """Mean Reciprocal Rank:第一个命中的相关岗位排名的倒数。
    命中在第1位=1.0,第2位=0.5,第3位=0.333...,Top-K 内没命中=0。
    单数概括'正确答案平均排多靠前',对排序质量敏感。"""
    rel = set(relevant_ids)
    for rank, it in enumerate(rec_items[:k], start=1):
        if it.job.job_id in rel:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(rec_items, relevant_ids, k):
    rel = set(relevant_ids)
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, it in enumerate(rec_items[:k], start=1)
        if it.job.job_id in rel
    )
    n_ideal = min(len(rel), k)
    idcg = sum(1.0 / math.log2(r + 1) for r in range(1, n_ideal + 1))
    return dcg / idcg if idcg else 0.0


def run_eval(eval_set, gamma=None):
    if gamma is not None:
        R.GAMMA = gamma
    hits, hits1, mrrs, ndcgs, details = [], [], [], [], []
    for case in eval_set:
        profile = UserProfile(user_id="eval", skills=case["skills"],
                              target_role=case.get("target_role", ""))
        items = R.RecommenderService.recommend(profile, UserPreference(), TOP_K)
        h = hit_at_k(items, case["relevant_role_ids"], TOP_K)
        h1 = hit_at_1(items, case["relevant_role_ids"])
        m = mrr(items, case["relevant_role_ids"], TOP_K)
        n = ndcg_at_k(items, case["relevant_role_ids"], TOP_K)
        hits.append(h)
        hits1.append(h1)
        mrrs.append(m)
        ndcgs.append(n)
        rel = set(case["relevant_role_ids"])
        hit_positions = [(rank, it.job.job_id, it.job.title)
                         for rank, it in enumerate(items[:TOP_K], 1) if it.job.job_id in rel]
        details.append({"name": case["name"], "hit": h, "hit1": h1, "mrr": m, "ndcg": n,
                        "top5": [(it.job.job_id, it.job.title) for it in items[:TOP_K]],
                        "hit_positions": hit_positions})
    return {
        "hit": float(np.mean(hits)),
        "hit1": float(np.mean(hits1)),
        "mrr": float(np.mean(mrrs)),
        "ndcg": float(np.mean(ndcgs)),
        "details": details,
    }


def main():
    name2id = load_name2id()
    eval_set, src, warnings = load_eval_set(name2id)

    print("=" * 64)
    print(f"推荐效果评估(评测集: {src},共 {len(eval_set)} 个测试用户)")
    print("=" * 64)
    if warnings:
        print("\n⚠️  评测集映射警告:")
        for w in warnings:
            print(w)

    res = run_eval(eval_set)
    print(f"\n>>> 当前权重 (ALPHA={R.ALPHA} BETA={R.BETA} GAMMA={R.GAMMA} DELTA={R.DELTA}) 逐用户结果:\n")
    for d in res["details"]:
        print(f"  [{d['name']}]  Hit@1={d['hit1']}  Hit@{TOP_K}={d['hit']}  "
              f"MRR={d['mrr']:.3f}  NDCG@{TOP_K}={d['ndcg']:.3f}")
        if d["hit_positions"]:
            for rank, rid, title in d["hit_positions"]:
                print(f"      命中: 第{rank}位 [{rid}] {title}")
        else:
            print(f"      未命中。Top5: {[t[1] for t in d['top5']]}")
    print(f"\n  平均 Hit@1   = {res['hit1']:.3f}   ← 目标岗排第一的比例(小库下主看这个)")
    print(f"  平均 Hit@{TOP_K}  = {res['hit']:.3f}   ← 召回覆盖(小库下区分度低)")
    print(f"  平均 MRR     = {res['mrr']:.3f}   ← 第一个命中的平均排名质量")
    print(f"  平均 NDCG@{TOP_K} = {res['ndcg']:.3f}")

    print("\n" + "=" * 64)
    print("GAMMA(缺口惩罚)敏感性分析")
    print("=" * 64)
    original = R.GAMMA
    print(f"\n  {'GAMMA':>8} | {'Hit@1':>7} | {'Hit@5':>7} | {'MRR':>7} | {'NDCG@5':>8}")
    print("  " + "-" * 48)
    for g in [0.0, 0.01, 0.02, 0.04, 0.06, 0.10]:
        r = run_eval(eval_set, gamma=g)
        print(f"  {g:>8} | {r['hit1']:>7.3f} | {r['hit']:>7.3f} | {r['mrr']:>7.3f} | {r['ndcg']:>8.3f}")
    R.GAMMA = original


if __name__ == "__main__":
    main()