"""Chronos-Bolt vs damped Holt vs seasonal naive 回测对擂（技能月度 share 预测）。

协议与 pipelines/trend/build_skill_trend_v3.py 的 cv_mape 完全对齐：
  尾部 24 个月 expanding window，origin 从 12 起、步长 2、horizon=3，
  实际值全 0 的 fold 跳过，MAPE 分母 max(|actual|, EPS)，预测截断 ≥0，
  每技能有效折 ≥3 才参与汇总。

额外加第三方：amazon/chronos-bolt-small（中位数分位数作点预测），
按 fold 把全部技能 batch 进 GPU，单次推理覆盖所有 origin。

输出 reports/eval/chronos_vs_holt_eval.json：三方 MAPE 分布、两两胜率、
按技能类别（skill_vocab_v2 by_category）胜负、耗时/显存。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines" / "trend"))
from build_skill_trend_v3 import (  # noqa: E402
    CV_HORIZON, CV_MIN_FOLDS, CV_MIN_ORIGIN, CV_TAIL_MONTHS, EPS,
    fit_holt, predict_holt, predict_seasonal_naive,
)

FULL_PARQUET_PATH = Path("/data/shichaojian/JNIT/processed/skill_trend_panel_v3_full.parquet")
VOCAB_PATH = Path("data/gold/skill_vocab_v2.json")
REPORT_PATH = Path("reports/eval/chronos_vs_holt_eval.json")


def load_panel(path: Path) -> tuple[pd.DataFrame, str]:
    df = pd.read_parquet(path)
    months = sorted(df["month"].unique())
    ok = [m for m in months if not bool(df.loc[df["month"] == m, "low_coverage"].iloc[0])]
    analysis_end = ok[-1] if ok else months[-1]
    return df[df["month"] <= analysis_end], analysis_end


def skill_category_map() -> dict[str, str]:
    if not VOCAB_PATH.exists():
        return {}
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for cat, ids in vocab.get("by_category", {}).items():
        for s in ids:
            out[str(s)] = cat
    return out


def cv_origins(n_tail: int) -> list[int]:
    return list(range(CV_MIN_ORIGIN, n_tail - CV_HORIZON + 1, 2))


def eval_baselines(y_tail: np.ndarray) -> dict[str, list[float]]:
    """返回 {method: [fold MAPE,...]}，协议与 v3 cv_mape 一致。"""
    errs = {"holt": [], "naive": []}
    for o in cv_origins(len(y_tail)):
        train = y_tail[:o]
        actual = y_tail[o:o + CV_HORIZON]
        if np.sum(actual) < EPS:
            continue
        denom = np.maximum(np.abs(actual), EPS)
        p_holt = np.maximum(predict_holt(fit_holt(train), CV_HORIZON), 0.0)
        p_naive = np.maximum(predict_seasonal_naive(train, CV_HORIZON), 0.0)
        errs["holt"].append(float(np.mean(np.abs(actual - p_holt) / denom)))
        errs["naive"].append(float(np.mean(np.abs(actual - p_naive) / denom)))
    return errs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="amazon/chronos-bolt-small")
    ap.add_argument("--full-parquet", type=Path, default=FULL_PARQUET_PATH)
    ap.add_argument("--min-nonzero-months", type=int, default=24)
    ap.add_argument("--max-skills", type=int, default=0, help="0 = 不抽样，全部合格技能")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--out", type=Path, default=REPORT_PATH)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    panel, analysis_end = load_panel(args.full_parquet)
    months = sorted(panel["month"].unique())
    print(f"[data] months {months[0]}..{months[-1]} ({len(months)}), analysis_end={analysis_end}")

    wide = panel.pivot(index="skill", columns="month", values="share").reindex(columns=months)
    wide = wide.fillna(0.0).sort_index()
    nz = (wide > 0).sum(axis=1)
    eligible = wide[nz >= args.min_nonzero_months]
    if args.max_skills and len(eligible) > args.max_skills:
        eligible = eligible.sample(args.max_skills, random_state=args.seed).sort_index()
    skills = eligible.index.tolist()
    print(f"[data] 合格技能(≥{args.min_nonzero_months} 非零月): {len(skills)}")

    Y = eligible.to_numpy(dtype=np.float64)  # (n_skill, n_month)
    n_skill = len(skills)

    # ---- 基线：numpy 向量化重算（与 v3 实现等价）----
    t0 = time.time()
    Y_tail = Y[:, -CV_TAIL_MONTHS:]
    origins = cv_origins(CV_TAIL_MONTHS)
    # fold_mask[i, f]: 该 fold 实际值不全 0
    fold_mask = np.stack([Y_tail[:, o:o + CV_HORIZON].sum(axis=1) >= EPS for o in origins], axis=1)
    valid_folds = fold_mask.sum(axis=1)
    denom = np.maximum(np.abs(Y_tail), EPS)

    holt_err = np.full((n_skill, len(origins)), np.nan)
    naive_err = np.full((n_skill, len(origins)), np.nan)
    for fi, o in enumerate(origins):
        for si in range(n_skill):
            if not fold_mask[si, fi]:
                continue
            train = Y_tail[si, :o]
            actual = Y_tail[si, o:o + CV_HORIZON]
            p_h = np.maximum(predict_holt(fit_holt(train), CV_HORIZON), 0.0)
            p_n = np.maximum(predict_seasonal_naive(train, CV_HORIZON), 0.0)
            holt_err[si, fi] = np.mean(np.abs(actual - p_h) / denom[si, o:o + CV_HORIZON])
            naive_err[si, fi] = np.mean(np.abs(actual - p_n) / denom[si, o:o + CV_HORIZON])
    t_baseline = time.time() - t0

    # ---- Chronos：按 fold 全技能 batch ----
    import torch
    from chronos import BaseChronosPipeline

    torch_dtype = torch.bfloat16 if args.device.startswith("cuda") else torch.float32
    t0 = time.time()
    pipe = BaseChronosPipeline.from_pretrained(
        args.model, device_map=args.device, torch_dtype=torch_dtype)
    t_load = time.time() - t0

    chronos_err = np.full((n_skill, len(origins)), np.nan)
    t0 = time.time()
    for fi, o in enumerate(origins):
        idx = np.where(fold_mask[:, fi])[0]
        if len(idx) == 0:
            continue
        ctx = torch.tensor(Y_tail[idx, :o].astype(np.float32))
        with torch.no_grad():
            q, _ = pipe.predict_quantiles(ctx, prediction_length=CV_HORIZON,
                                          quantile_levels=[0.5])
        pred = np.maximum(q[:, :, 0].cpu().to(torch.float64).numpy(), 0.0)
        for j, si in enumerate(idx):
            chronos_err[si, fi] = np.mean(
                np.abs(Y_tail[si, o:o + CV_HORIZON] - pred[j])
                / denom[si, o:o + CV_HORIZON])
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
        vram_mb = torch.cuda.max_memory_allocated() / 2**20
    else:
        vram_mb = 0.0
    t_chronos = time.time() - t0
    del pipe
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()

    # ---- 汇总 ----
    def skill_mape(err: np.ndarray) -> np.ndarray:
        return np.array([np.nanmean(err[i]) if valid_folds[i] >= CV_MIN_FOLDS else np.nan
                         for i in range(n_skill)])

    m_holt, m_naive, m_chr = skill_mape(holt_err), skill_mape(naive_err), skill_mape(chronos_err)
    keep = ~np.isnan(m_holt) & ~np.isnan(m_naive) & ~np.isnan(m_chr)
    print(f"[eval] 有效技能(三方均 ≥{CV_MIN_FOLDS} 折): {int(keep.sum())}/{n_skill}")

    def dist(x: np.ndarray) -> dict:
        x = x[keep]
        return {"n": int(len(x)), "median": float(np.median(x)), "mean": float(np.mean(x)),
                "p25": float(np.quantile(x, 0.25)), "p75": float(np.quantile(x, 0.75))}

    base_best = np.minimum(m_holt, m_naive)
    paired = keep
    win_vs_holt = float(np.mean(m_chr[paired] < m_holt[paired]))
    win_vs_naive = float(np.mean(m_chr[paired] < m_naive[paired]))
    win_vs_best = float(np.mean(m_chr[paired] < base_best[paired]))
    med_drop_vs_holt = 1.0 - float(np.median(m_chr[paired]) / np.median(m_holt[paired]))
    med_drop_vs_best = 1.0 - float(np.median(m_chr[paired]) / np.median(base_best[paired]))

    cats = skill_category_map()
    by_cat: dict[str, dict] = {}
    for cat in sorted(set(cats.get(s, "other") for s in skills)):
        idx = [i for i, s in enumerate(skills) if cats.get(s, "other") == cat and keep[i]]
        if len(idx) < 5:
            continue
        ch, ho = m_chr[idx], m_holt[idx]
        by_cat[cat] = {
            "n": len(idx),
            "chronos_median_mape": float(np.median(ch)),
            "holt_median_mape": float(np.median(ho)),
            "naive_median_mape": float(np.median(m_naive[idx])),
            "chronos_win_rate_vs_holt": float(np.mean(ch < ho)),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": {
            "source": str(args.full_parquet),
            "analysis_end": analysis_end,
            "n_months": len(months),
            "tail_months": CV_TAIL_MONTHS, "horizon": CV_HORIZON,
            "origins": origins, "step": 2,
            "min_nonzero_months": args.min_nonzero_months,
            "min_valid_folds": CV_MIN_FOLDS,
            "mape_denom": "max(|actual|, 1e-6)，预测截断 ≥0，实际值全 0 的 fold 跳过",
            "alignment": "与 build_skill_trend_v3.cv_mape 完全一致",
        },
        "model": {"name": args.model, "point_forecast": "median quantile (0.5)",
                  "device": args.device},
        "n_skills_evaluated": int(keep.sum()),
        "mape_distribution": {"chronos": dist(m_chr), "holt": dist(m_holt),
                              "naive": dist(m_naive), "best_baseline": dist(base_best)},
        "chronos_win_rate": {"vs_holt": win_vs_holt, "vs_naive": win_vs_naive,
                             "vs_best_baseline": win_vs_best},
        "chronos_median_mape_drop": {"vs_holt": med_drop_vs_holt,
                                     "vs_best_baseline": med_drop_vs_best},
        "by_category": by_cat,
        "cost": {"baseline_total_s": round(t_baseline, 2),
                 "chronos_load_s": round(t_load, 2),
                 "chronos_infer_s": round(t_chronos, 2),
                 "chronos_peak_vram_mb": round(vram_mb, 1)},
        "verdict_thresholds": {"上线条件": "中位 MAPE 降 ≥10%（对最优基线）或胜率 ≥60%",
                               "chronos_median_drop_vs_best": med_drop_vs_best,
                               "chronos_win_rate_vs_best": win_vs_best},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== MAPE 分布（中位 / 均值）===")
    for k in ("chronos", "holt", "naive", "best_baseline"):
        d = report["mape_distribution"][k]
        print(f"  {k:<14} {d['median']:.4f} / {d['mean']:.4f}  (n={d['n']})")
    print(f"\nchronos 胜率: vs holt {win_vs_holt:.1%}, vs naive {win_vs_naive:.1%}, "
          f"vs best {win_vs_best:.1%}")
    print(f"chronos 中位 MAPE 降幅: vs holt {med_drop_vs_holt:.1%}, vs best {med_drop_vs_best:.1%}")
    print(f"\n耗时: 基线 {t_baseline:.1f}s, chronos 加载 {t_load:.1f}s 推理 {t_chronos:.1f}s, "
          f"峰值显存 {vram_mb:.0f} MB")
    print(f"报告: {args.out}")


if __name__ == "__main__":
    main()
