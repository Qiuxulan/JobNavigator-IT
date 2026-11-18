"""语义兜底校准：对当前规则兜底(role_071)的全部唯一标题跑 Qwen3 语义近邻，输出相似度分布与样例。

    /var/lib/jobnav-env/bin/python experiments/calibrate_role_semantic.py

结果写 reports/eval/role_semantic_fallback_eval.json，用于选定 SIM_THRESHOLD。
"""
import gzip
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.cn_jobs import build_market as B
from pipelines.cn_jobs import collect as C
from pipelines.cn_jobs.role_semantic import SemanticRoleAssigner, job_key_text


def main():
    ledger = [json.loads(l) for l in gzip.open("data/cn_jobs/jobs_ledger.jsonl.gz", "rt", encoding="utf-8") if l.strip()]
    ledger = [j for j in ledger if C.is_it_job(j["title"], j.get("category", ""))]
    for j in ledger:
        j["cities"] = [c for c in j["cities"] if C.is_domestic([c])] or j["cities"]
    ledger = [j for j in ledger if C.is_domestic(j["cities"])]
    active = [j for j in ledger if j.get("active")]
    fb = [j["title"] for j in active if B.assign_role(j["title"], j.get("category", "")) == "role_071"]
    uniq = sorted(set(fb))
    print(f"fallback jobs: {len(fb)}, unique titles: {len(uniq)}")

    roles_doc = json.load(open("data/gold/role_profiles_v3.json"))
    roles = roles_doc["roles"] if isinstance(roles_doc["roles"], list) else list(roles_doc["roles"].values())
    role_by_id = {r["role_id"]: r for r in roles}

    asn = SemanticRoleAssigner(role_by_id)
    # 用 标题+职能+JD 前 200 字 编码，与 build_market 在线路径一致
    items = {}
    for j in active:
        if B.assign_role(j["title"], j.get("category", "")) != "role_071":
            continue
        k, t = job_key_text(j)
        items[k] = t
    asn.assign(items)
    uniq = list(items)
    fb = uniq  # 校准以“唯一岗位文本”为单位
    sims = np.array([asn.cache[k]["sim"] for k in uniq])
    quantiles = {str(q): round(float(np.quantile(sims, q)), 3) for q in [0.1, 0.25, 0.5, 0.75, 0.9]}
    print("sim quantiles:", quantiles)
    for th in [0.40, 0.45, 0.50, 0.55, 0.60]:
        n_titles = int((sims >= th).sum())
        n_jobs = sum(1 for t in fb if asn.cache[t]["sim"] >= th)
        print(f"  th={th}: titles {n_titles}/{len(uniq)} ({n_titles/len(uniq):.1%}), jobs {n_jobs}/{len(fb)} ({n_jobs/len(fb):.1%})")

    random.seed(0)
    key_to_job = {}
    for j in active:
        if j.get("title") and B.assign_role(j["title"], j.get("category", "")) == "role_071":
            k, _ = job_key_text(j)
            key_to_job[k] = j["title"]
    samples = []
    for k in random.sample(uniq, min(40, len(uniq))):
        h = asn.cache[k]
        t = key_to_job.get(k, k)
        samples.append({"title": t, "sim": h["sim"], "role_id": h["role_id"], "role_name": role_by_id[h["role_id"]]["role_name"]})
        print(f"  {h['sim']:.3f}  {t[:36]:38s} -> {h['role_id']} {role_by_id[h['role_id']]['role_name'][:35]}")

    out = {
        "n_fallback_jobs": len(fb), "n_unique_titles": len(uniq),
        "sim_quantiles": quantiles,
        "threshold_sweep": {str(th): {"titles": int((sims >= th).sum()),
                                      "jobs": sum(1 for t in fb if asn.cache[t]["sim"] >= th)}
                            for th in [0.40, 0.45, 0.50, 0.55, 0.60]},
        "samples": samples,
    }
    Path("reports/eval/role_semantic_fallback_eval.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> reports/eval/role_semantic_fallback_eval.json")


if __name__ == "__main__":
    main()
