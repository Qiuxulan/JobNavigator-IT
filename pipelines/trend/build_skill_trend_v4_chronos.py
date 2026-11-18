"""技能趋势面板 v4：Chronos-Bolt 技能 share 预测（v3 面板结构兼容）。

背景：experiments/eval_chronos_vs_holt.py 回测显示 amazon/chronos-bolt-small
在 v3 同款 CV 协议（尾部 24 月、horizon=3、滚动 origin、MAPE）下中位 MAPE
较 damped Holt 降 17.7%、较最优基线降 14.6%、对最优基线胜率 66.7%（≥60%），
满足上线阈值。本管线把 v3 的 Holt/naive 二选一升级为三方逐技能 CV 选模。

做法（不重算面板，只换预测引擎，其余字段原样继承 v3）：
  输入 data/gold/skill_trend_panel_v3.json 作为结构/指标/状态唯一来源；
  从 full parquet 取各技能截至 analysis_end 的 share 序列；
  对有 forecast 的技能（≥18 非零月、非 discontinued）：
    1) 同协议 CV 算 chronos / holt / naive 三方 MAPE（fold 全技能 batch 上 GPU）；
    2) 选模：先按 v3 规则定最优基线，chronos CV MAPE 严格更优才替换
       （保守：不打平换人），保证任一技能的在线 MAPE 不回退；
    3) 用选中模型在完整截断序列上预测 6 个月，forecast.method ∈
       {"chronos-bolt", "holt", "naive"}，结构与 v3 完全一致。

输出 data/gold/skill_trend_panel_v4_chronos.json（幂等覆盖，不碰 v3 文件）。
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trend"))
from build_skill_trend_v3 import (  # noqa: E402
    CV_HORIZON, CV_MIN_FOLDS, CV_MIN_ORIGIN, CV_TAIL_MONTHS, EPS,
    fit_holt, predict_holt, predict_seasonal_naive,
)

V3_GOLD_PATH = Path("data/gold/skill_trend_panel_v3.json")
FULL_PARQUET_PATH = Path("/data/shichaojian/JNIT/processed/skill_trend_panel_v3_full.parquet")
V4_GOLD_PATH = Path("data/gold/skill_trend_panel_v4_chronos.json")


def cv_origins(n_tail: int) -> list[int]:
    return list(range(CV_MIN_ORIGIN, n_tail - CV_HORIZON + 1, 2))


def baseline_cv_mape(y_tail: np.ndarray) -> dict[str, float | None]:
    """与 v3 cv_mape 同协议，返回各方法 fold 均值 MAPE（有效折 <3 → None）。"""
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
    return {k: (float(np.mean(v)) if len(v) >= CV_MIN_FOLDS else None) for k, v in errs.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="amazon/chronos-bolt-small")
    ap.add_argument("--v3-gold", type=Path, default=V3_GOLD_PATH)
    ap.add_argument("--full-parquet", type=Path, default=FULL_PARQUET_PATH)
    ap.add_argument("--out", type=Path, default=V4_GOLD_PATH)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()

    v3 = json.loads(args.v3_gold.read_text(encoding="utf-8"))
    analysis_end = v3["analysis_end"]
    months = [m for m in v3["months"] if m <= analysis_end]

    panel = pd.read_parquet(args.full_parquet)
    panel = panel[panel["month"] <= analysis_end]
    wide = (panel.pivot(index="skill", columns="month", values="share")
            .reindex(columns=months).fillna(0.0))

    # 有 v3 forecast 的技能（≥18 非零月、非 discontinued）才重算
    targets = [s for s, rec in v3["skills"].items()
               if rec.get("forecast") and s in wide.index]
    print(f"[v4] 待重算预测技能: {len(targets)}, analysis_end={analysis_end}")

    import torch
    from chronos import BaseChronosPipeline
    torch_dtype = torch.bfloat16 if args.device.startswith("cuda") else torch.float32
    pipe = BaseChronosPipeline.from_pretrained(
        args.model, device_map=args.device, torch_dtype=torch_dtype)

    # ---- 逐技能基线 CV（numpy，快）----
    t0 = time.time()
    baseline_mape: dict[str, dict[str, float | None]] = {}
    tails = {}
    for s in targets:
        y_tail = wide.loc[s, months].to_numpy(dtype=np.float64)[-CV_TAIL_MONTHS:]
        tails[s] = y_tail
        baseline_mape[s] = baseline_cv_mape(y_tail)
    t_base = time.time() - t0

    # ---- chronos CV：按 fold 全技能 batch ----
    origins = cv_origins(CV_TAIL_MONTHS)
    chronos_mape: dict[str, list[float]] = {s: [] for s in targets}
    t0 = time.time()
    for o in origins:
        ctx = torch.tensor(np.stack([tails[s][:o] for s in targets]).astype(np.float32))
        with torch.no_grad():
            q, _ = pipe.predict_quantiles(ctx, prediction_length=CV_HORIZON,
                                          quantile_levels=[0.5])
        pred = np.maximum(q[:, :, 0].cpu().to(torch.float64).numpy(), 0.0)
        for i, s in enumerate(targets):
            actual = tails[s][o:o + CV_HORIZON]
            if np.sum(actual) < EPS:
                continue
            denom = np.maximum(np.abs(actual), EPS)
            chronos_mape[s].append(float(np.mean(np.abs(actual - pred[i]) / denom)))
    t_cv = time.time() - t0
    chronos_cv = {s: (float(np.mean(v)) if len(v) >= CV_MIN_FOLDS else None)
                  for s, v in chronos_mape.items()}

    # ---- 选模 + 6 个月前瞻（chronos 胜出者 batch）----
    def pick(s: str) -> tuple[str, float | None]:
        m = baseline_mape[s]
        # v3 基线选模逻辑
        if m["holt"] is None and m["naive"] is None:
            base_method, base_mape = "naive", None
        elif m["holt"] is None:
            base_method, base_mape = "naive", m["naive"]
        elif m["naive"] is None:
            base_method, base_mape = "holt", m["holt"]
        else:
            base_method = "holt" if m["holt"] <= m["naive"] else "naive"
            base_mape = m[base_method]
        c = chronos_cv[s]
        if c is not None and (base_mape is None or c < base_mape):  # 严格更优才换
            return "chronos-bolt", c
        return base_method, base_mape

    chosen = {s: pick(s) for s in targets}

    chr_idx = [i for i, s in enumerate(targets) if chosen[s][0] == "chronos-bolt"]
    chr_pred6: dict[str, np.ndarray] = {}
    if chr_idx:
        t0 = time.time()
        ctx = torch.tensor(np.stack([wide.loc[targets[i], months].to_numpy(dtype=np.float32)
                                     for i in chr_idx]))
        with torch.no_grad():
            q, _ = pipe.predict_quantiles(ctx, prediction_length=6, quantile_levels=[0.5])
        pred = np.maximum(q[:, :, 0].cpu().to(torch.float64).numpy(), 0.0)
        chr_pred6 = {targets[i]: pred[j] for j, i in enumerate(chr_idx)}
        t_fwd = time.time() - t0
    else:
        t_fwd = 0.0
    del pipe
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()

    # ---- 组装 v4 面板：结构同 v3，仅换 forecast ----
    from collections import Counter
    old = Counter(r["forecast"]["method"] for r in v3["skills"].values() if r.get("forecast"))
    method_counts: Counter = Counter()
    for s in targets:
        method, mape = chosen[s]
        y_full = wide.loc[s, months].to_numpy(dtype=np.float64)
        if method == "chronos-bolt":
            pred = chr_pred6[s]
        elif method == "holt":
            pred = np.maximum(predict_holt(fit_holt(y_full), 6), 0.0)
        else:
            pred = np.maximum(predict_seasonal_naive(y_full, 6), 0.0)
        v3["skills"][s]["forecast"] = {
            "method": method,
            "m3": round(float(pred[2]), 6),
            "m6": round(float(pred[5]), 6),
            "mape": (None if mape is None else round(mape, 4)),
        }
        method_counts[method] += 1

    v4 = dict(v3)
    v4["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    v4["forecast_engine"] = {
        "version": "v4_chronos_bolt",
        "model": args.model,
        "selection": "逐技能 CV 选模：chronos-bolt 仅在 CV MAPE 严格优于 v3 最优基线时替换",
        "backtest": "reports/eval/chronos_vs_holt_eval.json",
        "method_counts": dict(method_counts),
        "baseline_cv_s": round(t_base, 2),
        "chronos_cv_s": round(t_cv, 2),
        "chronos_forward_s": round(t_fwd, 2),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(v4, ensure_ascii=False), encoding="utf-8")

    print(f"[v4] 选模分布: {dict(method_counts)}  (v3 原分布: {dict(old)})")
    print(f"[v4] 耗时: 基线CV {t_base:.1f}s, chronos CV {t_cv:.1f}s, chronos 前瞻 {t_fwd:.1f}s")
    print(f"[v4] 输出: {args.out}")


if __name__ == "__main__":
    main()
