"""趋势预测 v2：回测选模的诚实预测（经典方法，不用深度学习）。

为什么不用 PatchTST：可靠训练月份最多 24 个/岗位（low_confidence 规则剔除了
抓取覆盖不足的月份），全部岗位 × ≤24 点不支持深度学习；经典方法 + 时间序回测
选模更诚实。

主信号：jd_share（抗抓取量偏差，见 build_panel.py）；副信号：salary_mid。

回测协议：2020-01..2025-09（仅非 low_confidence 月）训练 → 预测 2025-10..2026-09
共 12 个月，与真实值对比；按 sMAPE 选模；方向准确率 = 回测期内 3 个月变化方向
（阈值 ±2%）的命中率。选中的模型用全部可靠月重训，外推面板最新数据月的次月起
12 个月（随月度链路滚动，见 fc_window()）。

候选模型（全部自实现，无 statsmodels 依赖）：
  naive / seasonal_naive（日历周期，需 ≥24 可靠训练点）/ 线性趋势 /
  Holt 阻尼趋势（φ=0.9，α、β 网格搜索）/ EMA 平滑外推（span 网格搜索）。

注意：Holt/EMA 在"可靠月压缩序列"上拟合（即忽略被 low_confidence 剔除的月份，
把它们当作序列中不存在的点）——这是对不规则采样的诚实简化，不使用被标记月份
的信息。

输出：
  - data/gold/trend_forecasts_v2.json      （每岗位 history + forecast）
  - data/gold/trend_forecasts_v2_eval.json （QC：选模分布、sMAPE vs naive、方向准确率）

confidence 公式（写明，供 API 侧解释）：
  base        = max(0, 1 - backtest_sMAPE)        # 回测越准越高
  data_factor = min(1, n_reliable_train / 24)      # 数据量越足越高
  confidence  = round(base * data_factor, 3)
  稀疏岗位（历史 jd_count 总和 < 50）：confidence = min(confidence, 0.35) 且 sparse=true
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

PANEL_PATH = Path("/data/shichaojian/JNIT/processed/trend_panel_v2.parquet")


def _roles_path() -> Path:
    for v in ("v3", "v2", "v1"):
        p = Path(f"data/gold/fine_grained_roles_{v}.json")
        if p.exists():
            return p
    raise FileNotFoundError("data/gold/fine_grained_roles_v3/v2/v1.json 均不存在")


ROLES_PATH = _roles_path()
OUT_PATH = Path("data/gold/trend_forecasts_v2.json")
EVAL_PATH = Path("data/gold/trend_forecasts_v2_eval.json")

BT_TRAIN_END = "2025-09"      # 回测训练截止
BT_HORIZON = ("2025-10", "2026-09")   # 回测 12 个月
# 未来预测窗口 = 面板最新数据月的次月起 12 个月（随月度链路自动滚动，
# 如面板到 2026-10 则预测 2026-11..2027-10）

DIRECTION_THRESHOLD = 0.02     # ±2% 视为 flat
Z80 = 1.2816                   # 80% 区间正态分位
HOLT_PHI = 0.9                 # Holt 阻尼系数（固定）
SPARSE_JD_TOTAL = 50
MIN_TRAIN = {"linear": 6, "holt": 8, "ema": 4, "seasonal_naive": 24, "naive": 1}


def months_between(start: str, end: str) -> list[str]:
    return [str(m) for m in pd.period_range(start=start, end=end, freq="M")]


def fc_window(panel_end: str) -> tuple[str, str]:
    """未来 12 个月预测窗口：面板最新数据月的次月起。"""
    start = str(pd.Period(panel_end, freq="M") + 1)
    end = str(pd.Period(start, freq="M") + 11)
    return start, end


# ---------- 模型（自实现） ----------

def fit_naive(y: np.ndarray) -> dict:
    return {"kind": "naive", "last": float(y[-1])}


def predict_naive(m, h: int) -> np.ndarray:
    return np.full(h, m["last"])


def fit_seasonal_naive(panel_g: pd.DataFrame, train_mask: np.ndarray) -> dict:
    """日历周期：预测 y[m] = y[m-12]，取面板中对应月（jd_share 全部有观测）。"""
    return {"kind": "seasonal_naive"}


def predict_seasonal_naive(m, months: list[str], lookup: dict[str, float]) -> np.ndarray:
    out = []
    for mo in months:
        prev = lookup.get(_shift_month(mo, -12))
        out.append(prev if prev is not None else m["fallback"])
    return np.array(out)


def _shift_month(mo: str, delta: int) -> str:
    p = pd.Period(mo, freq="M") + delta
    return str(p)


def fit_linear(y: np.ndarray, t: np.ndarray) -> dict:
    slope, intercept = np.polyfit(t, y, 1)
    return {"kind": "linear", "slope": float(slope), "intercept": float(intercept),
            "t_last": float(t[-1])}


def predict_linear(m, h: int) -> np.ndarray:
    return np.array([m["intercept"] + m["slope"] * (m["t_last"] + i)
                     for i in range(1, h + 1)])


def _holt_sse(y, alpha, beta, phi):
    n = len(y)
    l, b = y[0], (y[1] - y[0]) if n > 1 else 0.0
    sse = 0.0
    for t in range(1, n):
        fit = l + phi * b
        sse += (y[t] - fit) ** 2
        l_prev = l
        l = alpha * y[t] + (1 - alpha) * fit
        b = beta * (l - l_prev) + (1 - beta) * phi * b
    return sse


def fit_holt(y: np.ndarray) -> dict:
    grid = np.arange(0.05, 0.901, 0.05)
    best = min(((a, b) for a in grid for b in grid),
               key=lambda ab: _holt_sse(y, ab[0], ab[1], HOLT_PHI))
    a, b = best
    l, bb = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
    for t in range(1, len(y)):
        l_prev = l
        l = a * y[t] + (1 - a) * (l + HOLT_PHI * bb)
        bb = b * (l - l_prev) + (1 - b) * HOLT_PHI * bb
    return {"kind": "holt", "alpha": float(a), "beta": float(b),
            "level": float(l), "trend": float(bb)}


def predict_holt(m, h: int) -> np.ndarray:
    phi_sum = np.cumsum(np.full(h, HOLT_PHI) ** np.arange(1, h + 1))
    return m["level"] + phi_sum * m["trend"]


def fit_ema(y: np.ndarray) -> dict:
    """EMA 平滑外推：s_t = α y_t + (1-α) s_{t-1}，向前平推 s_last；α 用
    一步向前预测误差（y_{t+1} vs s_t）网格搜索。"""
    n = len(y)
    best_a, best_sse = 0.5, math.inf
    for a in np.arange(0.05, 0.951, 0.05):
        s = y[0]
        sse = 0.0
        for t in range(n - 1):
            sse += (y[t + 1] - s) ** 2
            s = a * y[t + 1] + (1 - a) * s  # 先更新到 t+1，再预测 t+2
        if sse < best_sse:
            best_sse, best_a = sse, a
    s = y[0]
    for t in range(1, n):
        s = best_a * y[t] + (1 - best_a) * s
    return {"kind": "ema", "alpha": float(best_a), "level": float(s)}


def predict_ema(m, h: int) -> np.ndarray:
    return np.full(h, m["level"])


FIT_FUNCS = {
    "naive": lambda y, t, ctx: fit_naive(y),
    "seasonal_naive": lambda y, t, ctx: fit_seasonal_naive(ctx["g"], ctx["mask"]),
    "linear": lambda y, t, ctx: fit_linear(y, t),
    "holt": lambda y, t, ctx: fit_holt(y),
    "ema": lambda y, t, ctx: fit_ema(y),
}


def smape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = np.abs(actual) + np.abs(pred)
    diff = 2.0 * np.abs(actual - pred)
    terms = np.where(denom == 0, 0.0, np.where(denom > 0, diff / np.maximum(denom, 1e-12), 0.0))
    # a=p=0 → 0 误差；a=0,p>0 → 误差 2
    terms = np.where((actual == 0) & (pred != 0), 2.0, terms)
    return float(np.mean(terms))


def direction(series_now: np.ndarray, series_base: np.ndarray) -> list[str]:
    """相对 3 个月前的变化方向，阈值 ±2%。"""
    out = []
    for now, base in zip(series_now, series_base):
        if base == 0:
            out.append("flat" if now == 0 else "up")
            continue
        chg = now / base - 1.0
        out.append("up" if chg > DIRECTION_THRESHOLD else
                   "down" if chg < -DIRECTION_THRESHOLD else "flat")
    return out


def _fallback_level(share: np.ndarray, full_mask: np.ndarray) -> float:
    """insufficient_data 岗位的兜底预测水平：最近 6 个可靠月均值（最贴近当下），
    无可靠月则退全部月份中位数（jd_share 全月有观测，不会 NaN）。"""
    rel = share[full_mask]
    if len(rel) >= 3:
        return float(np.mean(rel[-6:]))
    if len(rel) >= 1:
        return float(np.mean(rel))
    return float(np.median(share))


# ---------- 每岗位流程 ----------

def forecast_role(g: pd.DataFrame, sparse: bool) -> dict:
    g = g.sort_values("month").reset_index(drop=True)
    months = g["month"].tolist()
    share = g["jd_share"].astype(float).to_numpy()
    low = g["low_confidence"].astype(bool).to_numpy()
    salary = g["salary_mid"].astype(float).to_numpy()
    di = g["demand_index"].astype(float).to_numpy()
    t_cal = np.arange(len(months), dtype=float)

    month_idx = {m: i for i, m in enumerate(months)}
    lookup_share = {m: float(share[i]) for i, m in enumerate(months)}

    train_mask = np.array([m <= BT_TRAIN_END for m in months]) & ~low
    n_train = int(train_mask.sum())
    bt_months = months_between(*BT_HORIZON)
    bt_idx = np.array([month_idx[m] for m in bt_months if m in month_idx])
    actual_bt = share[bt_idx]

    y_tr, t_tr = share[train_mask], t_cal[train_mask]
    ctx = {"g": g, "mask": train_mask}

    def fit_by_name(name: str, yy=y_tr, tt=t_tr):
        if len(yy) < MIN_TRAIN[name]:
            return None
        try:
            return FIT_FUNCS[name](yy, tt, ctx)
        except (np.linalg.LinAlgError, ValueError, IndexError, FloatingPointError):
            return None

    def predict_by_name(name, model, h, target_months):
        if model is None:
            return None
        if name == "seasonal_naive":
            model["fallback"] = float(y_tr[-1]) if len(y_tr) else 0.0
            return predict_seasonal_naive(model, target_months, lookup_share)
        return {"naive": predict_naive, "linear": predict_linear,
                "holt": predict_holt, "ema": predict_ema}[name](model, h)

    # ---- 回测 ----
    results, naive_smape = {}, math.inf
    for name in FIT_FUNCS:
        model = fit_by_name(name)
        pred = predict_by_name(name, model, len(bt_months), bt_months)
        if pred is None or np.any(~np.isfinite(pred)):
            results[name] = {"model": model, "smape": math.inf, "pred": None}
            continue
        pred = np.maximum(pred, 0.0)  # 份额不为负
        results[name] = {"model": model, "smape": smape(actual_bt, pred), "pred": pred}
    naive_smape = results["naive"]["smape"] if results["naive"]["pred"] is not None else math.inf

    valid = {k: v for k, v in results.items() if v["pred"] is not None}
    if valid:
        best_name = min(valid, key=lambda k: valid[k]["smape"])
        best_smape = valid[best_name]["smape"]
    else:  # 完全没有可靠训练数据：兜底为近 6 可靠月均值（见 _fallback_level）
        best_name, best_smape = "insufficient_data", math.inf
        valid["insufficient_data"] = {"model": None, "smape": math.inf, "pred": None}

    # 方向准确率（回测期，3 个月变化，±2% 阈值）
    base_idx = bt_idx - 3
    best_pred = valid[best_name]["pred"]
    if best_name != "insufficient_data" and best_pred is not None:
        actual_dirs = direction(actual_bt, share[base_idx])
        pred_dirs = direction(best_pred, share[base_idx])
        dir_acc = float(np.mean([a == p for a, p in zip(actual_dirs, pred_dirs)]))
    else:
        dir_acc = None

    # ---- 全量重训 + 未来预测 ----
    full_mask = ~low
    y_full, t_full = share[full_mask], t_cal[full_mask]
    fc_months = months_between(*fc_window(months[-1]))
    if best_name != "insufficient_data":
        model_full = fit_by_name(best_name, yy=y_full, tt=t_full) \
            if len(y_full) >= MIN_TRAIN[best_name] else None
        if model_full is None:
            model_full = fit_naive(y_full) if len(y_full) else None
            best_name = "naive" if model_full is not None else best_name
        if model_full is None:
            fc_pred = np.full(12, _fallback_level(share, full_mask))
            best_name = "insufficient_data"
        else:
            ctx = {"g": g, "mask": full_mask}
            if best_name == "seasonal_naive":
                model_full["fallback"] = float(y_full[-1])
                fc_pred = predict_seasonal_naive(model_full, fc_months, lookup_share)
            else:
                fc_pred = predict_by_name(best_name, model_full, 12, fc_months)
            fc_pred = np.asarray(fc_pred, dtype=float)
    else:
        fc_pred = np.full(12, _fallback_level(share, full_mask))

    # 80% 区间：回测残差 std；残差不足时用预测值的 15% 兜底（如实记录）
    resid = (valid[best_name]["pred"] - actual_bt) if valid.get(best_name, {}).get("pred") is not None else None
    if resid is not None and len(resid) >= 2 and np.std(resid, ddof=1) > 0:
        sigma = float(np.std(resid, ddof=1))
        sigma_source = "backtest_residual_std"
    else:
        sigma = None
        sigma_source = "fallback_15pct_of_pred"

    fc_pred = np.where(np.isfinite(fc_pred), fc_pred, float(np.nanmedian(share)))
    fc_pred = np.maximum(fc_pred, 0.0)
    lower = np.array([max(0.0, p - Z80 * (sigma if sigma is not None else 0.15 * p)) for p in fc_pred])
    upper = np.array([p + Z80 * (sigma if sigma is not None else 0.15 * p) for p in fc_pred])

    # demand_index 映射（岗位内 min-max，同 build_panel 口径），clip [0,1]
    s_min, s_max = float(np.nanmin(share)), float(np.nanmax(share))
    span = (s_max - s_min) or np.nan

    def to_di(x):
        if not np.isfinite(span):
            # 份额恒定（含全 0）的岗位无 trend 信息，min-max 归一化无定义，
            # 取 0.5 中性占位（如实记录，不做修形）
            return 0.5
        return float(np.clip((x - s_min) / span, 0.0, 1.0))

    di_pred = [to_di(p) for p in fc_pred]

    # ---- 副目标 salary_mid ----
    sal_pred, sal_smape, sal_model = _forecast_salary(g, months, salary, low, month_idx)

    # ---- confidence ----
    if best_smape is math.inf:
        confidence = 0.1 if best_name == "insufficient_data" else 0.2
    else:
        base = max(0.0, 1.0 - best_smape)
        data_factor = min(1.0, n_train / 24.0)
        confidence = round(base * data_factor, 3)
    if sparse:
        confidence = min(confidence, 0.35)

    # ---- trend_direction：末 3 月预测均值 vs 末 3 个可靠历史月均值 ----
    tail_fc = fc_pred[-3:]
    hist_reliable = share[full_mask][-3:]
    if len(hist_reliable) and np.mean(hist_reliable) > 0:
        chg = np.mean(tail_fc) / np.mean(hist_reliable) - 1.0
        trend = "up" if chg > DIRECTION_THRESHOLD else \
                "down" if chg < -DIRECTION_THRESHOLD else "flat"
    else:
        trend = "flat"

    history = [{
        "month": m, "jd_share": round(float(share[i]), 6),
        "demand_index": None if np.isnan(di[i]) else round(float(di[i]), 4),
        "salary_mid": None if np.isnan(salary[i]) else round(float(salary[i]), 0),
        "low_confidence": bool(low[i]),
    } for i, m in enumerate(months)]

    forecast = [{
        "month": m, "jd_share_pred": round(float(p), 6),
        "lower80": round(float(l), 6), "upper80": round(float(u), 6),
        "demand_index_pred": (None if d is None else round(d, 4)),
        "salary_mid_pred": (None if s is None else round(float(s), 0)),
    } for m, p, l, u, d, s in zip(fc_months, fc_pred, lower, upper, di_pred, sal_pred)]

    return {
        "role_id": g["role_id"].iloc[0],
        "model_used": best_name,
        "backtest_smape": (None if best_smape is math.inf else round(best_smape, 4)),
        "naive_backtest_smape": (None if naive_smape is math.inf else round(naive_smape, 4)),
        "direction_accuracy": (None if dir_acc is None else round(dir_acc, 4)),
        "n_reliable_train_months": n_train,
        "interval_sigma_source": sigma_source,
        "salary_model": sal_model,
        "salary_backtest_smape": sal_smape,
        "sparse": bool(sparse),
        "confidence": confidence,
        "trend_direction": trend,
        "history": history,
        "forecast": forecast,
        "_all_backtest_smapes": {k: (None if v["smape"] is math.inf else round(v["smape"], 4))
                                 for k, v in results.items()},
    }


def _forecast_salary(g, months, salary, low, month_idx):
    """副目标 salary_mid：候选 naive / 线性，同样回测选模；数据不足返回 None。"""
    sal_mask = ~np.isnan(salary)
    tr_idx = np.array([i for i, m in enumerate(months)
                       if m <= BT_TRAIN_END and sal_mask[i]])
    bt_months = [m for m in months_between(*BT_HORIZON) if m in month_idx]
    bt_idx = [month_idx[m] for m in bt_months]
    actual_bt = salary[bt_idx]
    obs_bt = ~np.isnan(actual_bt)
    if len(tr_idx) < 3 or obs_bt.sum() < 3:
        return [None] * 12, None, "insufficient_data"

    y_tr, t_tr = salary[tr_idx], tr_idx.astype(float)

    def lin_forecast(yy, tt, h, t_last):
        slope, intercept = np.polyfit(tt, yy, 1)
        return np.array([intercept + slope * (t_last + i) for i in range(1, h + 1)])

    cands = {"naive": np.full(len(bt_months), y_tr[-1])}
    if len(tr_idx) >= 6:
        cands["linear"] = lin_forecast(y_tr, t_tr, len(bt_months), t_tr[-1])
    scores = {k: smape(actual_bt[obs_bt], v[obs_bt]) for k, v in cands.items()}
    best = min(scores, key=scores.get)

    full_idx = np.array([i for i in range(len(months)) if sal_mask[i]])
    y_f, t_f = salary[full_idx], full_idx.astype(float)
    if best == "linear" and len(full_idx) >= 6:
        fc = lin_forecast(y_f, t_f, 12, t_f[-1])
    else:
        fc = np.full(12, y_f[-1])
    resid = cands[best][obs_bt] - actual_bt[obs_bt]
    sig = float(np.std(resid, ddof=1)) if len(resid) >= 2 and np.std(resid, ddof=1) > 0 else None
    fc = list(np.maximum(fc, 0.0))
    return [round(float(x), 0) for x in fc], round(scores[best], 4), best


# ---------- 主流程 ----------

def main() -> None:
    panel = pd.read_parquet(PANEL_PATH)
    roles = json.loads(ROLES_PATH.read_text(encoding="utf-8"))
    name_of = {r["role_id"]: r["role_name"] for r in roles}
    jd_total = panel.groupby("role_id")["jd_count"].sum().to_dict()
    sparse_ids = {r for r, c in jd_total.items() if c < SPARSE_JD_TOTAL}

    forecasts, eval_rows = {}, []
    for role_id, g in panel.groupby("role_id"):
        rec = forecast_role(g, sparse=role_id in sparse_ids)
        rec["role_name"] = name_of[role_id]
        # 内部字段不进入对外 JSON
        all_smape = rec.pop("_all_backtest_smapes")
        forecasts[role_id] = rec
        eval_rows.append({
            "role_id": role_id, "model": rec["model_used"],
            "smape": rec["backtest_smape"], "naive_smape": rec["naive_backtest_smape"],
            "dir_acc": rec["direction_accuracy"],
            "n_train": rec["n_reliable_train_months"], "sparse": rec["sparse"],
            "all_smapes": all_smape,
        })

    # ---- 校验断言（红线） ----
    expected_fc_months = months_between(*fc_window(str(panel["month"].max())))
    for role_id, rec in forecasts.items():
        fc = rec["forecast"]
        assert [f["month"] for f in fc] == expected_fc_months, f"{role_id}: 预测月份不连续"
        for f in fc:
            assert f["jd_share_pred"] is not None and math.isfinite(f["jd_share_pred"]), f"{role_id}: NaN 预测"
            assert f["lower80"] <= f["jd_share_pred"] <= f["upper80"], f"{role_id}: 区间不包含点预测"
            assert f["lower80"] >= 0, f"{role_id}: 区间下界为负"
            assert f["demand_index_pred"] is not None, f"{role_id}: demand_index_pred 缺失"
            assert 0.0 <= f["demand_index_pred"] <= 1.0, f"{role_id}: demand_index_pred 越界"

    # ---- QC / eval ----
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(float(np.mean(xs)), 4) if xs else None

    model_counts = {}
    for r in eval_rows:
        model_counts[r["model"]] = model_counts.get(r["model"], 0) + 1
    wins = sum(1 for r in eval_rows
               if r["smape"] is not None and r["naive_smape"] is not None
               and r["smape"] < r["naive_smape"])
    ties = sum(1 for r in eval_rows
               if r["smape"] is not None and r["naive_smape"] is not None
               and r["smape"] == r["naive_smape"])
    losses = sum(1 for r in eval_rows
                 if r["smape"] is not None and r["naive_smape"] is not None
                 and r["smape"] > r["naive_smape"])

    eval_json = {
        "protocol": {
            "signal": "jd_share（岗位份额，抗抓取量偏差）",
            "backtest": f"train 2020-01..{BT_TRAIN_END}（仅非 low_confidence） → "
                        f"predict {BT_HORIZON[0]}..{BT_HORIZON[1]} (12 个月)",
            "selection": "每岗位按 sMAPE 选最优；方向准确率阈值 ±2%（3 个月变化）",
            "confidence_formula": "confidence = max(0, 1 - sMAPE) * min(1, n_reliable_train/24)；"
                                  "稀疏岗位(总 jd_count<50) 截断至 ≤0.35",
            "candidates": list(FIT_FUNCS.keys()),
            "note": "Holt/EMA 在可靠月压缩序列上拟合；PatchTST 弃用（≤24 可靠月不支持深度学习）",
        },
        "model_selection_counts": dict(sorted(model_counts.items(), key=lambda kv: -kv[1])),
        "overall_mean_smape": mean([r["smape"] for r in eval_rows]),
        "naive_mean_smape": mean([r["naive_smape"] for r in eval_rows]),
        "overall_direction_accuracy": mean([r["dir_acc"] for r in eval_rows]),
        "vs_naive": {"win": wins, "tie": ties, "loss": losses,
                     "win_rate": round(wins / max(1, wins + ties + losses), 4)},
        "roles": eval_rows,
    }

    OUT_PATH.write_text(json.dumps(forecasts, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    EVAL_PATH.write_text(json.dumps(eval_json, ensure_ascii=False, indent=1),
                         encoding="utf-8")

    # ---- 抽查打印 ----
    sample_ids = [rid for rid, nm in name_of.items()
                  if nm in ("AI Engineer", "Data Scientist", "Backend Java Engineer")]
    for rid in sample_ids:
        rec = forecasts[rid]
        print(f"\n=== {rec['role_name']} ({rid}) | model={rec['model_used']} "
              f"sMAPE={rec['backtest_smape']} dir_acc={rec['direction_accuracy']} "
              f"conf={rec['confidence']} trend={rec['trend_direction']} sparse={rec['sparse']}")
        print(" history 尾部 6 个月:")
        for h in rec["history"][-6:]:
            print(f"  {h['month']} share={h['jd_share']} di={h['demand_index']} "
                  f"salary={h['salary_mid']} low_conf={h['low_confidence']}")
        print(" forecast 前 6 个月:")
        for f in rec["forecast"][:6]:
            print(f"  {f['month']} pred={f['jd_share_pred']} "
                  f"[{f['lower80']}, {f['upper80']}] di_pred={f['demand_index_pred']} "
                  f"salary={f['salary_mid_pred']}")

    print(f"\n=== 汇总 ===")
    print(f"模型选中分布: {eval_json['model_selection_counts']}")
    print(f"平均 sMAPE: {eval_json['overall_mean_smape']} vs naive "
          f"{eval_json['naive_mean_smape']}")
    print(f"方向准确率: {eval_json['overall_direction_accuracy']}")
    print(f"vs naive: {eval_json['vs_naive']}")


if __name__ == "__main__":
    main()
