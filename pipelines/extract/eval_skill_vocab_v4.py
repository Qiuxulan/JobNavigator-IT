"""skill_vocab_v4 效果量化：v3 vs v4 enriched JD 数据集对比 + 审核结果统计。

输入：
  data/gold/skill_vocab_review_v1.json     审核结果
  data/gold/skill_vocab_v4.json            v4 增量词典
  /data/shichaojian/JNIT/processed/jd_unified_v3_enriched/
  /data/shichaojian/JNIT/processed/jd_unified_v4_enriched/
输出：
  reports/eval/skill_vocab_v4_report.json
  控制台打印摘要。

指标：
  - 审核统计：keep/drop、category 分布、keep/drop 各 20 条抽样
  - 覆盖率：skills 非空率、平均每 JD 技能数、技能总命中、独立技能数（v3 vs v4）
  - v4 新增技能频次 top 50（v3 词表中不存在、由 v4 增量词典引入的 canonical）
  - 回归抽查：1000 行（固定随机种子）v3 skills 是否为 v4 skills 子集

用法：
  /var/lib/jobnav-env/bin/python pipelines/extract/eval_skill_vocab_v4.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/mnt/afs/JobNavigator-IT")
sys.path.insert(0, str(ROOT))

REVIEW_PATH = ROOT / "data/gold/skill_vocab_review_v1.json"
V4_PATH = ROOT / "data/gold/skill_vocab_v4.json"
V3_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3_enriched")
V4_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v4_enriched")
REPORT_PATH = ROOT / "reports/eval/skill_vocab_v4_report.json"

REGRESSION_SAMPLE = 1000


def load_skills(dir_path: Path) -> pd.DataFrame:
    frames = []
    for part in sorted(dir_path.glob("posted_month=*/part-0.parquet")):
        df = pd.read_parquet(part, columns=["skills", "skills_enriched"])
        df["skills"] = df["skills"].apply(
            lambda s: list(s) if isinstance(s, (list, tuple, np.ndarray)) else [])
        df["month"] = part.parent.name.split("=", 1)[1]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    review = json.load(open(REVIEW_PATH, encoding="utf-8"))
    reviews = review["reviews"]
    v4_vocab = json.load(open(V4_PATH, encoding="utf-8"))
    v4_canonicals = set(v4_vocab["skills"].keys())

    # ---- 审核统计 ----
    n_keep = sum(1 for r in reviews if r["keep"])
    cat_counter: Counter = Counter(rec["category"] if rec["keep"] else "dropped"
                                   for rec in reviews)
    keep_cat: Counter = Counter(r["category"] for r in reviews if r["keep"])
    keep_samples = [{"name": r["name"], "canonical": r["canonical"],
                     "category": r["category"], "reason": r["reason"]}
                    for r in reviews if r["keep"]][:20]
    drop_samples = [{"name": r["name"], "reason": r["reason"]}
                    for r in reviews if not r["keep"]][:20]

    # ---- 数据集对比 ----
    df3 = load_skills(V3_DIR)
    df4 = load_skills(V4_DIR)
    assert len(df3) == len(df4), f"行数不一致: {len(df3)} vs {len(df4)}"

    def coverage(df: pd.DataFrame) -> dict:
        n = len(df)
        nonempty = df["skills"].apply(len).gt(0)
        all_skills = [s for skills in df["skills"] for s in skills]
        return {
            "rows": int(n),
            "skills_nonempty_ratio": round(float(nonempty.mean()), 4),
            "avg_skills_per_jd": round(len(all_skills) / n, 4),
            "total_skill_hits": len(all_skills),
            "unique_skills": len(set(all_skills)),
        }

    cov3, cov4 = coverage(df3), coverage(df4)

    # v4 新增技能频次（来自 v4 增量词典的 canonical）
    new_counter: Counter = Counter()
    enriched_new_rows = 0
    for s3, s4, flag in zip(df3["skills"], df4["skills"], df4["skills_enriched"]):
        added = [s for s in s4 if s in v4_canonicals and s not in set(s3)]
        if added and flag:
            enriched_new_rows += 1
        new_counter.update(added)
    new_top50 = new_counter.most_common(50)

    # ---- 回归抽查 ----
    rng = random.Random(42)
    idx = rng.sample(range(len(df3)), min(REGRESSION_SAMPLE, len(df3)))
    lost_rows, lost_skills = 0, Counter()
    for i in idx:
        s3, s4 = set(df3["skills"].iloc[i]), set(df4["skills"].iloc[i])
        missing = s3 - s4
        if missing:
            lost_rows += 1
            lost_skills.update(missing)
    regression = {
        "sample_size": len(idx),
        "rows_with_loss": lost_rows,
        "loss_ratio": round(lost_rows / len(idx), 4),
        "lost_skills_top20": lost_skills.most_common(20),
    }

    report = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "inputs": {"review": str(REVIEW_PATH), "vocab_v4": str(V4_PATH),
                   "v3_dir": str(V3_DIR), "v4_dir": str(V4_DIR)},
        "review_stats": {
            "n_candidates": len(reviews),
            "n_keep": n_keep,
            "n_drop": len(reviews) - n_keep,
            "keep_ratio": round(n_keep / len(reviews), 4),
            "category_distribution_all": dict(cat_counter.most_common()),
            "category_distribution_keep": dict(keep_cat.most_common()),
            "keep_samples_20": keep_samples,
            "drop_samples_20": drop_samples,
        },
        "vocab_v4_stats": {"num_skills": v4_vocab["num_skills"],
                           "num_aliases": v4_vocab["num_aliases"],
                           "build_stats": v4_vocab.get("stats")},
        "coverage": {"v3": cov3, "v4": cov4,
                     "delta_nonempty_ratio": round(cov4["skills_nonempty_ratio"] - cov3["skills_nonempty_ratio"], 4)},
        "new_skills_top50": new_top50,
        "rows_gaining_v4_skills": enriched_new_rows,
        "regression_check": regression,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({"review": {"keep": n_keep, "drop": len(reviews) - n_keep},
                      "vocab_v4": report["vocab_v4_stats"],
                      "coverage": report["coverage"],
                      "regression": {"sample": regression["sample_size"],
                                     "rows_with_loss": lost_rows,
                                     "loss_ratio": regression["loss_ratio"]},
                      "top10_new_skills": new_top50[:10]},
                     ensure_ascii=False, indent=2))
    print(f"\n报告已写入 {REPORT_PATH}")


if __name__ == "__main__":
    main()
