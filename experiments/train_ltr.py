"""LTR 模型训练(matching v6,2026-11-08)。

读取 data/silver/ltr_train_v1.jsonl(DeepSeek 打标的合成画像样本),
用 LightGBM LambdaRank 训练本地排序器:
  - group = 画像(同一画像的候选是一个 query);
  - 5-fold 按画像分组交叉验证(GroupKFold),held-out 上算
    graded NDCG@5(label 0-3 直接作 gain)与 binary 口径
    (label>=2 算相关)的 Hit@1/Hit@5/MRR/NDCG@5;
  - 输出特征重要性(gain),top10 打印;
  - 全量数据重训最终模型,存 models/ltr_ranker_v1.txt
    + 特征清单 models/ltr_ranker_v1_features.json(线上 ltr_ranker 按它对齐特征顺序)。

运行:python -m experiments.train_ltr
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"
os.chdir(ROOT)

from app.services.ltr_ranker import FEATURE_NAMES  # noqa: E402

DATA_PATH = ROOT / "data" / "silver" / "ltr_train_v1.jsonl"
MODEL_PATH = ROOT / "models" / "ltr_ranker_v1.txt"
FEATURES_PATH = ROOT / "models" / "ltr_ranker_v1_features.json"
REPORT_PATH = ROOT / "reports" / "eval" / "ltr_training_v1.json"

LABEL_GAIN = [0.0, 1.0, 2.0, 3.0]
RELEVANT_THRESHOLD = 2  # binary 口径:label>=2 算相关(与 58 例 eval set 口径一致)


def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """jsonl → (X, y, group, profile_ids);特征顺序与 FEATURE_NAMES 严格一致。"""
    X, y, groups, profile_ids = [], [], [], []
    with path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            cands = record["candidates"]
            for cand in cands:
                feats = cand["features"]
                missing = [name for name in FEATURE_NAMES if name not in feats]
                if missing:
                    raise ValueError(f"{record['profile_id']} 缺特征 {missing}")
                X.append([float(feats[name]) for name in FEATURE_NAMES])
                y.append(int(cand["label"]))
            groups.append(len(cands))
            profile_ids.append(record["profile_id"])
    return np.array(X, dtype=float), np.array(y, dtype=int), np.array(groups), profile_ids


def _group_slices(groups: np.ndarray) -> list[slice]:
    out, start = [], 0
    for g in groups:
        out.append(slice(start, start + int(g)))
        start += int(g)
    return out


def ranking_metrics(y_true: np.ndarray, y_score: np.ndarray, groups: np.ndarray) -> dict:
    """按画像分组计算 graded / binary 两套口径的排序指标。"""
    n = len(groups)
    graded_ndcg = binary_hit1 = binary_hit5 = binary_mrr = binary_ndcg = 0.0
    for sl in _group_slices(groups):
        labels = y_true[sl]
        scores = y_score[sl]
        order = np.argsort(-scores, kind="stable")
        ranked = labels[order][:5]
        # graded NDCG@5:gain 直接用 label
        dcg = sum((2.0 ** rel - 1.0) / math.log2(r + 2) for r, rel in enumerate(ranked))
        ideal = np.sort(labels)[::-1][:5]
        idcg = sum((2.0 ** rel - 1.0) / math.log2(r + 2) for r, rel in enumerate(ideal))
        graded_ndcg += dcg / idcg if idcg > 0 else 0.0
        # binary:label >= RELEVANT_THRESHOLD 算相关
        rel = (ranked >= RELEVANT_THRESHOLD).astype(int)
        n_rel = int((labels >= RELEVANT_THRESHOLD).sum())
        binary_hit1 += rel[0] if len(rel) else 0
        binary_hit5 += 1 if rel.sum() > 0 else 0
        for r, flag in enumerate(rel, 1):
            if flag:
                binary_mrr += 1.0 / r
                break
        dcg = sum(1.0 / math.log2(r + 1) for r, flag in enumerate(rel, 1) if flag)
        idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(n_rel, 5) + 1))
        binary_ndcg += dcg / idcg if idcg > 0 else 0.0
    return {
        "graded_ndcg@5": round(graded_ndcg / n, 4),
        "binary_hit@1": round(binary_hit1 / n, 4),
        "binary_hit@5": round(binary_hit5 / n, 4),
        "binary_mrr": round(binary_mrr / n, 4),
        "binary_ndcg@5": round(binary_ndcg / n, 4),
        "n_queries": n,
    }


def make_ranker() -> "object":
    import lightgbm as lgb

    return lgb.LGBMRanker(
        objective="lambdarank",
        label_gain=LABEL_GAIN,
        learning_rate=0.05,
        n_estimators=400,
        num_leaves=31,
        min_child_samples=10,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )


def main() -> dict:
    from sklearn.model_selection import GroupKFold

    X, y, groups, profile_ids = load_dataset(DATA_PATH)
    print(f">>> 数据集: {len(groups)} 画像 / {len(y)} 候选;label 分布 "
          f"{dict(zip(*np.unique(y, return_counts=True)))}", flush=True)

    # 样本级画像 id(每候选一行),GroupKFold 按画像整组切分
    sample_gid = np.repeat(np.arange(len(groups)), groups)
    folds = list(GroupKFold(n_splits=5).split(X, y, groups=sample_gid))
    fold_rows = []
    for fold, (tr_idx, va_idx) in enumerate(folds, 1):
        tr_groups = np.bincount(sample_gid[tr_idx], minlength=len(groups))
        va_groups = np.bincount(sample_gid[va_idx], minlength=len(groups))
        tr_groups = tr_groups[tr_groups > 0]
        va_groups = va_groups[va_groups > 0]
        ranker = make_ranker()
        ranker.fit(
            X[tr_idx], y[tr_idx], group=tr_groups,
            eval_set=[(X[va_idx], y[va_idx])], eval_group=[va_groups],
            eval_at=[5], callbacks=[__import__("lightgbm").early_stopping(30, verbose=False)],
        )
        best_iter = ranker.best_iteration_ or ranker.n_estimators
        va_pred = ranker.predict(X[va_idx])
        m = ranking_metrics(y[va_idx], va_pred, va_groups)
        m.update({"fold": fold, "n_train_queries": int(len(tr_groups)), "best_iter": best_iter})
        fold_rows.append(m)
        print(f"fold {fold}: {m}", flush=True)

    keys = ["graded_ndcg@5", "binary_hit@1", "binary_hit@5", "binary_mrr", "binary_ndcg@5"]
    cv_mean = {k: round(float(np.mean([r[k] for r in fold_rows])), 4) for k in keys}

    final = make_ranker()
    final.fit(X, y, group=groups)
    fi = final.booster_.feature_importance(importance_type="gain")
    importance = sorted(
        ({"feature": name, "gain": float(g)} for name, g in zip(FEATURE_NAMES, fi)),
        key=lambda r: -r["gain"],
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    final.booster_.save_model(str(MODEL_PATH))
    FEATURES_PATH.write_text(
        json.dumps(
            {
                "feature_names": FEATURE_NAMES,
                "label_gain": LABEL_GAIN,
                "objective": "lambdarank",
                "n_profiles": int(len(groups)),
                "n_candidates": int(len(y)),
                "trained_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc).isoformat(),
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    train_pred = final.predict(X)
    train_metrics = ranking_metrics(y, train_pred, groups)

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "data": str(DATA_PATH),
        "model": str(MODEL_PATH),
        "features": str(FEATURES_PATH),
        "n_profiles": int(len(groups)),
        "n_candidates": int(len(y)),
        "label_distribution": {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))},
        "cv_5fold": {"folds": fold_rows, "mean": cv_mean},
        "train_set_metrics": train_metrics,
        "feature_importance_top10": [
            {**row, "gain": round(row["gain"], 2)} for row in importance[:10]
        ],
        "feature_importance_full": [
            {**row, "gain": round(row["gain"], 2)} for row in importance
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n# 5-fold CV(画像分组,held-out)")
    print("| fold | graded NDCG@5 | binary Hit@1 | binary Hit@5 | binary MRR | binary NDCG@5 |")
    print("|---|---|---|---|---|---|")
    for r in fold_rows:
        print(f"| {r['fold']} | {r['graded_ndcg@5']} | {r['binary_hit@1']} | "
              f"{r['binary_hit@5']} | {r['binary_mrr']} | {r['binary_ndcg@5']} |")
    print(f"| mean | {cv_mean['graded_ndcg@5']} | {cv_mean['binary_hit@1']} | "
          f"{cv_mean['binary_hit@5']} | {cv_mean['binary_mrr']} | {cv_mean['binary_ndcg@5']} |")
    print("\n# 特征重要性 top10(gain)")
    for i, row in enumerate(importance[:10], 1):
        print(f"{i:2d}. {row['feature']:<28} {row['gain']:.1f}")
    print(f"\n[done] 模型 {MODEL_PATH} / 清单 {FEATURES_PATH} / 报告 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    main()
