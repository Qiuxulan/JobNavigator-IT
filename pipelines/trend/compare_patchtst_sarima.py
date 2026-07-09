from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).parents[2]
DEFAULT_DATASET = ROOT / "data" / "gold" / "patchtst_role_month_features.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "trend" / "patchtst_sarima_experiment"
TARGET_COL = "jd_demand_index"
OBSERVED_COL = "jd_demand_observed"
IDENTITY_COLS = ["canonical_role", "month", "time_idx"]
DIRECTION_THRESHOLD = 0.03
EPSILON = 1e-6


@dataclass(frozen=True)
class ExperimentConfig:
    dataset_path: str = str(DEFAULT_DATASET)
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    context_length: int = 24
    horizon: int = 12
    seeds: tuple[int, ...] = (11, 22, 33, 44, 55)
    epochs: int = 80
    bootstrap_iterations: int = 5000
    bootstrap_seed: int = 2026
    sarima_maxiter: int = 75
    seasonal_period: int = 12
    patch_len: int = 6
    stride: int = 3
    d_model: int = 64
    n_heads: int = 4
    num_layers: int = 2
    dropout: float = 0.10
    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4


@dataclass
class WindowSet:
    x: np.ndarray
    y: np.ndarray
    meta: list[dict[str, Any]]


@dataclass(frozen=True)
class TemporalSplit:
    train_max_origin: int
    validation_origin: int
    test_origin: int


@dataclass
class ForecastResult:
    prediction: np.ndarray | None
    fit_seconds: float
    predict_seconds: float
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the 12-month PatchTST experiment with SARIMA and Seasonal Naive."
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seeds", default="11,22,33,44,55")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--bootstrap-iterations", type=int, default=5000)
    parser.add_argument("--sarima-maxiter", type=int, default=75)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use one PatchTST seed, five epochs, a reduced SARIMA grid, and 200 bootstrap samples.",
    )
    return parser.parse_args()


def load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_json(path)
    required = [*IDENTITY_COLS, TARGET_COL, OBSERVED_COL]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise ValueError(f"experiment dataset is missing columns: {missing}")
    panel = panel[required].copy()
    panel["month"] = pd.to_datetime(panel["month"], errors="coerce")
    panel[TARGET_COL] = pd.to_numeric(panel[TARGET_COL], errors="coerce")
    panel["time_idx"] = pd.to_numeric(panel["time_idx"], errors="coerce")
    panel[OBSERVED_COL] = panel[OBSERVED_COL].fillna(False).astype(bool)
    panel = panel.dropna(subset=["canonical_role", "month", "time_idx", TARGET_COL])
    panel["time_idx"] = panel["time_idx"].astype(int)
    return panel.sort_values(["canonical_role", "time_idx"]).reset_index(drop=True)


def build_observed_windows(
    panel: pd.DataFrame,
    context_length: int = 24,
    horizon: int = 12,
) -> WindowSet:
    windows_x: list[np.ndarray] = []
    windows_y: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    for role, group in panel.groupby("canonical_role", sort=True):
        group = group.sort_values("time_idx").reset_index(drop=True)
        values = group[TARGET_COL].to_numpy(dtype=np.float32)
        observed = group[OBSERVED_COL].to_numpy(dtype=bool)
        max_start = len(group) - context_length - horizon + 1
        for start in range(max(0, max_start)):
            context_end = start + context_length
            forecast_end = context_end + horizon
            if not observed[start:forecast_end].all():
                continue
            windows_x.append(values[start:context_end, None])
            windows_y.append(values[context_end:forecast_end])
            meta.append(
                {
                    "canonical_role": str(role),
                    "context_start_time_idx": int(group.loc[start, "time_idx"]),
                    "context_end_time_idx": int(group.loc[context_end - 1, "time_idx"]),
                    "forecast_start_time_idx": int(group.loc[context_end, "time_idx"]),
                    "forecast_end_time_idx": int(group.loc[forecast_end - 1, "time_idx"]),
                    "forecast_start_month": group.loc[context_end, "month"].strftime("%Y-%m-%d"),
                    "forecast_end_month": group.loc[forecast_end - 1, "month"].strftime("%Y-%m-%d"),
                }
            )
    if not windows_x:
        raise ValueError("no fully observed windows are available for the experiment")
    return WindowSet(np.stack(windows_x), np.stack(windows_y), meta)


def choose_temporal_split(windows: WindowSet, horizon: int = 12) -> TemporalSplit:
    origins = sorted({int(item["forecast_start_time_idx"]) for item in windows.meta})
    origin_set = set(origins)
    for test_origin in reversed(origins):
        validation_origin = test_origin - horizon
        train_max_origin = validation_origin - horizon
        if validation_origin in origin_set and any(origin <= train_max_origin for origin in origins):
            return TemporalSplit(train_max_origin, validation_origin, test_origin)
    raise ValueError("not enough history for non-overlapping train, validation, and test targets")


def split_windows(windows: WindowSet, split: TemporalSplit) -> tuple[WindowSet, WindowSet, WindowSet]:
    origins = np.asarray([item["forecast_start_time_idx"] for item in windows.meta])
    train_mask = origins <= split.train_max_origin
    validation_mask = origins == split.validation_origin
    test_mask = origins == split.test_origin

    def select(mask: np.ndarray) -> WindowSet:
        return WindowSet(
            x=windows.x[mask],
            y=windows.y[mask],
            meta=[item for item, keep in zip(windows.meta, mask) if keep],
        )

    train, validation, test = select(train_mask), select(validation_mask), select(test_mask)
    if not len(train.x) or not len(validation.x) or not len(test.x):
        raise ValueError("temporal split produced an empty partition")
    assert_non_overlapping_targets(train, validation, test)
    return train, validation, test


def assert_non_overlapping_targets(train: WindowSet, validation: WindowSet, test: WindowSet) -> None:
    train_end = max(item["forecast_end_time_idx"] for item in train.meta)
    validation_start = min(item["forecast_start_time_idx"] for item in validation.meta)
    validation_end = max(item["forecast_end_time_idx"] for item in validation.meta)
    test_start = min(item["forecast_start_time_idx"] for item in test.meta)
    if train_end >= validation_start or validation_end >= test_start:
        raise ValueError("forecast target intervals overlap across temporal partitions")


def direction_labels(values: np.ndarray, baselines: np.ndarray) -> np.ndarray:
    changes = values - baselines[:, None]
    return np.where(changes >= DIRECTION_THRESHOLD, 1, np.where(changes <= -DIRECTION_THRESHOLD, -1, 0))


def metric_values(y_true: np.ndarray, y_pred: np.ndarray, baselines: np.ndarray) -> dict[str, float]:
    errors = np.asarray(y_pred, dtype=float) - np.asarray(y_true, dtype=float)
    denominator = np.abs(y_true) + np.abs(y_pred) + EPSILON
    true_direction = direction_labels(y_true, baselines)
    pred_direction = direction_labels(y_pred, baselines)
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "smape": float(np.mean(2.0 * np.abs(errors) / denominator)),
        "direction_accuracy": float(np.mean(true_direction == pred_direction)),
    }


def metrics_by_horizon(
    model: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    baselines: np.ndarray,
    horizons: Iterable[int] = (3, 6, 12),
) -> list[dict[str, Any]]:
    rows = []
    for horizon in horizons:
        if horizon <= y_true.shape[1]:
            rows.append({"model": model, "horizon": horizon, **metric_values(
                y_true[:, :horizon], y_pred[:, :horizon], baselines
            )})
    return rows


def seasonal_naive_forecast(history: np.ndarray, horizon: int, period: int = 12) -> np.ndarray:
    history = np.asarray(history, dtype=float)
    if history.size < period:
        raise ValueError("seasonal naive requires at least one full seasonal period")
    return np.resize(history[-period:], horizon).astype(np.float32)


def sarima_candidates(quick: bool = False) -> list[tuple[tuple[int, int, int], tuple[int, int, int, int]]]:
    if quick:
        orders = [(0, 1, 0), (1, 0, 0), (1, 1, 0), (0, 1, 1)]
        seasonal = [(0, 0, 0, 12), (1, 0, 0, 12), (0, 1, 1, 12)]
    else:
        orders = list(itertools.product(range(3), repeat=3))
        seasonal = [(*values, 12) for values in itertools.product(range(2), repeat=3)]
    return [(tuple(order), tuple(seasonal_order)) for order in orders for seasonal_order in seasonal]


def safe_sarima_forecast(
    history: np.ndarray,
    horizon: int,
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int],
    maxiter: int = 75,
    model_factory: Callable[..., Any] | None = None,
) -> ForecastResult:
    started = time.perf_counter()
    try:
        if model_factory is None:
            from statsmodels.tsa.statespace.sarimax import SARIMAX

            model_factory = SARIMAX
        trend = "n" if order[1] or seasonal_order[1] else "c"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = model_factory(
                np.asarray(history, dtype=float),
                order=order,
                seasonal_order=seasonal_order,
                trend=trend,
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            fitted = model.fit(disp=False, maxiter=maxiter)
        fit_seconds = time.perf_counter() - started
        prediction_started = time.perf_counter()
        prediction = np.asarray(fitted.forecast(horizon), dtype=np.float32)
        predict_seconds = time.perf_counter() - prediction_started
        if prediction.shape != (horizon,) or not np.isfinite(prediction).all():
            raise ValueError("SARIMA produced invalid predictions")
        return ForecastResult(np.clip(prediction, 0.0, 1.0), fit_seconds, predict_seconds)
    except Exception as exc:  # A failed order must not abort the complete grid search.
        return ForecastResult(None, time.perf_counter() - started, 0.0, f"{type(exc).__name__}: {exc}")


def tune_sarima(
    validation: WindowSet,
    candidates: list[tuple[tuple[int, int, int], tuple[int, int, int, int]]],
    maxiter: int,
) -> tuple[tuple[int, int, int], tuple[int, int, int, int], list[dict[str, Any]]]:
    search_rows: list[dict[str, Any]] = []
    best: tuple[float, tuple[int, int, int], tuple[int, int, int, int]] | None = None
    for order, seasonal_order in candidates:
        predictions: list[np.ndarray] = []
        truths: list[np.ndarray] = []
        failures: list[str] = []
        elapsed = 0.0
        for history, target, meta in zip(validation.x[:, :, 0], validation.y, validation.meta):
            result = safe_sarima_forecast(history, target.size, order, seasonal_order, maxiter)
            elapsed += result.fit_seconds + result.predict_seconds
            if result.prediction is None:
                failures.append(f"{meta['canonical_role']}: {result.error}")
            else:
                predictions.append(result.prediction)
                truths.append(target)
        coverage = len(predictions) / len(validation.y)
        mae = float("inf") if coverage < 1.0 else float(np.mean(np.abs(np.stack(predictions) - np.stack(truths))))
        row = {
            "order": str(order),
            "seasonal_order": str(seasonal_order),
            "validation_mae": None if not math.isfinite(mae) else mae,
            "coverage": coverage,
            "failures": len(failures),
            "failure_examples": " | ".join(failures[:3]),
            "elapsed_seconds": elapsed,
        }
        search_rows.append(row)
        if coverage == 1.0 and (best is None or mae < best[0]):
            best = (mae, order, seasonal_order)
    if best is None:
        raise RuntimeError("all SARIMA candidates failed on at least one validation role")
    return best[1], best[2], search_rows


def evaluate_sarima(
    test: WindowSet,
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int],
    maxiter: int,
) -> tuple[np.ndarray, list[dict[str, Any]], float, float]:
    predictions: list[np.ndarray] = []
    failures: list[dict[str, Any]] = []
    fit_seconds = 0.0
    predict_seconds = 0.0
    for history, target, meta in zip(test.x[:, :, 0], test.y, test.meta):
        result = safe_sarima_forecast(history, target.size, order, seasonal_order, maxiter)
        fit_seconds += result.fit_seconds
        predict_seconds += result.predict_seconds
        if result.prediction is None:
            failures.append({"canonical_role": meta["canonical_role"], "error": result.error})
            predictions.append(np.full(target.shape, np.nan, dtype=np.float32))
        else:
            predictions.append(result.prediction)
    prediction_array = np.stack(predictions)
    if failures:
        raise RuntimeError(f"selected SARIMA order failed on test data: {failures}")
    return prediction_array, failures, fit_seconds, predict_seconds


def evaluate_patchtst(
    train: WindowSet,
    validation: WindowSet,
    test: WindowSet,
    config: ExperimentConfig,
) -> tuple[np.ndarray, list[dict[str, Any]], float, float]:
    try:
        from pipelines.trend.patchtst_predictor import (
            PatchTSTConfig,
            Standardizer,
            predict_scaled,
            set_seed,
            train_patchtst_model,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("PatchTST experiment requires torch>=2.2.0") from exc

    patch_config = PatchTSTConfig(
        context_length=config.context_length,
        horizon=config.horizon,
        patch_len=config.patch_len,
        stride=config.stride,
        d_model=config.d_model,
        n_heads=config.n_heads,
        num_layers=config.num_layers,
        dropout=config.dropout,
        batch_size=config.batch_size,
        epochs=config.epochs,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    combined_x = np.concatenate([train.x, validation.x])
    combined_y = np.concatenate([train.y, validation.y])
    seed_predictions: list[np.ndarray] = []
    seed_rows: list[dict[str, Any]] = []
    total_train_seconds = 0.0
    total_predict_seconds = 0.0
    validation_baselines = validation.x[:, -1, 0]
    test_baselines = test.x[:, -1, 0]
    for seed in config.seeds:
        patch_config.seed = seed
        set_seed(seed)
        validation_standardizer = Standardizer.fit(train.x, train.y)
        started = time.perf_counter()
        validation_model = train_patchtst_model(train.x, train.y, patch_config, validation_standardizer)
        validation_train_seconds = time.perf_counter() - started
        started = time.perf_counter()
        validation_prediction = predict_scaled(validation_model, validation.x, validation_standardizer)
        validation_predict_seconds = time.perf_counter() - started

        final_standardizer = Standardizer.fit(combined_x, combined_y)
        started = time.perf_counter()
        final_model = train_patchtst_model(combined_x, combined_y, patch_config, final_standardizer)
        final_train_seconds = time.perf_counter() - started
        started = time.perf_counter()
        test_prediction = predict_scaled(final_model, test.x, final_standardizer)
        test_predict_seconds = time.perf_counter() - started

        total_train_seconds += validation_train_seconds + final_train_seconds
        total_predict_seconds += validation_predict_seconds + test_predict_seconds
        seed_predictions.append(test_prediction)
        seed_rows.append(
            {
                "seed": seed,
                "validation": metric_values(validation.y, validation_prediction, validation_baselines),
                "test": metric_values(test.y, test_prediction, test_baselines),
                "train_seconds": validation_train_seconds + final_train_seconds,
                "test_predict_seconds": test_predict_seconds,
            }
        )
    return np.mean(np.stack(seed_predictions), axis=0), seed_rows, total_train_seconds, total_predict_seconds


def paired_bootstrap_mae(
    y_true: np.ndarray,
    patch_prediction: np.ndarray,
    sarima_prediction: np.ndarray,
    iterations: int,
    seed: int,
) -> dict[str, float]:
    patch_role_mae = np.mean(np.abs(patch_prediction - y_true), axis=1)
    sarima_role_mae = np.mean(np.abs(sarima_prediction - y_true), axis=1)
    differences = sarima_role_mae - patch_role_mae
    rng = np.random.default_rng(seed)
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        selected = rng.integers(0, len(differences), len(differences))
        samples[index] = float(np.mean(differences[selected]))
    low, high = np.quantile(samples, [0.025, 0.975])
    return {
        "mean_difference": float(np.mean(differences)),
        "ci_95_lower": float(low),
        "ci_95_upper": float(high),
    }


def prediction_rows(
    test: WindowSet,
    predictions: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample_index, meta in enumerate(test.meta):
        start = pd.Timestamp(meta["forecast_start_month"])
        for step in range(test.y.shape[1]):
            row = {
                "canonical_role": meta["canonical_role"],
                "month": (start + pd.DateOffset(months=step)).strftime("%Y-%m-%d"),
                "step": step + 1,
                "actual": float(test.y[sample_index, step]),
            }
            for model, values in predictions.items():
                row[model] = float(values[sample_index, step])
            rows.append(row)
    return rows


def role_metric_rows(
    test: WindowSet,
    predictions: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baselines = test.x[:, -1, 0]
    for index, meta in enumerate(test.meta):
        for model, values in predictions.items():
            rows.append(
                {
                    "canonical_role": meta["canonical_role"],
                    "model": model,
                    **metric_values(test.y[index:index + 1], values[index:index + 1], baselines[index:index + 1]),
                }
            )
    return rows


def build_conclusion(
    overall: dict[str, dict[str, float]],
    horizon_rows: list[dict[str, Any]],
    bootstrap: dict[str, float],
    patch_win_ratio: float,
) -> tuple[bool, dict[str, bool], str]:
    patch = overall["patchtst"]
    sarima = overall["sarima"]
    horizon_ok = True
    for horizon in (3, 6, 12):
        patch_row = next(row for row in horizon_rows if row["model"] == "patchtst" and row["horizon"] == horizon)
        sarima_row = next(row for row in horizon_rows if row["model"] == "sarima" and row["horizon"] == horizon)
        horizon_ok = horizon_ok and patch_row["mae"] <= sarima_row["mae"] * 1.05
    conditions = {
        "lower_mae_and_rmse": patch["mae"] < sarima["mae"] and patch["rmse"] < sarima["rmse"],
        "bootstrap_ci_above_zero": bootstrap["ci_95_lower"] > 0.0,
        "wins_majority_of_roles": patch_win_ratio > 0.5,
        "no_horizon_degradation_over_5_percent": horizon_ok,
    }
    superior = all(conditions.values())
    conclusion = (
        "PatchTST 在本数据集的严格时间切分测试中显著优于 SARIMA。"
        if superior
        else "本实验未证明 PatchTST 显著优于 SARIMA。"
    )
    return superior, conditions, conclusion


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_plots(predictions_df: pd.DataFrame, output_dir: Path) -> list[str]:
    matplotlib_config_dir = ROOT / ".pytest_cache" / "matplotlib"
    matplotlib_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config_dir))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    error_rows = []
    for step, group in predictions_df.groupby("step"):
        for model in ("patchtst", "sarima", "seasonal_naive"):
            error_rows.append({"step": step, "model": model, "mae": np.mean(np.abs(group[model] - group["actual"]))})
    error_df = pd.DataFrame(error_rows)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for model, group in error_df.groupby("model"):
        ax.plot(group["step"], group["mae"], marker="o", label=model)
    ax.set(xlabel="Forecast month", ylabel="MAE", title="Error by forecast month")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    error_path = plot_dir / "error_by_horizon.png"
    fig.savefig(error_path, dpi=160)
    plt.close(fig)
    generated.append(str(error_path))

    roles = sorted(predictions_df["canonical_role"].unique())[:4]
    fig, axes = plt.subplots(len(roles), 1, figsize=(9, max(3, 2.8 * len(roles))), squeeze=False)
    for axis, role in zip(axes[:, 0], roles):
        group = predictions_df[predictions_df["canonical_role"] == role]
        axis.plot(group["step"], group["actual"], marker="o", linewidth=2, label="actual")
        for model in ("patchtst", "sarima", "seasonal_naive"):
            axis.plot(group["step"], group[model], marker=".", label=model)
        axis.set_title(role)
        axis.grid(alpha=0.2)
    axes[0, 0].legend(ncol=4, fontsize=8)
    axes[-1, 0].set_xlabel("Forecast month")
    fig.tight_layout()
    example_path = plot_dir / "forecast_examples.png"
    fig.savefig(example_path, dpi=160)
    plt.close(fig)
    generated.append(str(example_path))
    return generated


def write_report(
    output_dir: Path,
    config: ExperimentConfig,
    panel: pd.DataFrame,
    windows: WindowSet,
    train: WindowSet,
    validation: WindowSet,
    test: WindowSet,
    split: TemporalSplit,
    overall: dict[str, dict[str, float]],
    horizon_rows: list[dict[str, Any]],
    bootstrap: dict[str, float],
    patch_win_ratio: float,
    patch_seed_rows: list[dict[str, Any]],
    sarima_order: tuple[int, int, int],
    sarima_seasonal_order: tuple[int, int, int, int],
    conditions: dict[str, bool],
    conclusion: str,
    timing: dict[str, float],
) -> None:
    seed_maes = np.asarray([row["test"]["mae"] for row in patch_seed_rows])
    lines = [
        "# PatchTST 与 SARIMA 时序预测对比实验报告",
        "",
        "## 实验结论",
        "",
        f"**{conclusion}**",
        "",
        "该结论只适用于当前岗位需求月度数据及本实验设置，不能推广为 PatchTST 在所有时序任务上均优于传统模型。",
        "",
        "## 数据与切分",
        "",
        f"- 原始面板：{panel['canonical_role'].nunique()} 个岗位，{panel['month'].nunique()} 个月，{len(panel)} 行。",
        f"- 完整可观测窗口：{len(windows.x)} 个，覆盖 {len({m['canonical_role'] for m in windows.meta})} 个岗位。",
        f"- 训练/验证/测试样本：{len(train.x)}/{len(validation.x)}/{len(test.x)}。",
        f"- 严格测试岗位数：{len({m['canonical_role'] for m in test.meta})}。数据连续观测不足是未覆盖全部 69 个岗位的原因。",
        f"- 预测起点 time_idx：训练不晚于 {split.train_max_origin}，验证 {split.validation_origin}，测试 {split.test_origin}。",
        f"- 历史窗口 {config.context_length} 个月，预测窗口 {config.horizon} 个月；三个分区的预测目标月份完全不重叠。",
        "",
        "## 模型设置",
        "",
        f"- PatchTST：{len(config.seeds)} 个随机种子 {list(config.seeds)}，每次 {config.epochs} epochs；测试预测取各次结果均值。",
        f"- PatchTST 单次运行测试 MAE：均值 {seed_maes.mean():.4f}，标准差 {seed_maes.std(ddof=0):.4f}。",
        f"- SARIMA：验证集选得 order={sarima_order}，seasonal_order={sarima_seasonal_order}。",
        "- Seasonal Naive：重复最近 12 个月，作为结果合理性检查。",
        "",
        "## 总体结果",
        "",
        "| 模型 | MAE | RMSE | sMAPE | 方向准确率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in ("patchtst", "sarima", "seasonal_naive"):
        metric = overall[model]
        lines.append(
            f"| {model} | {metric['mae']:.4f} | {metric['rmse']:.4f} | "
            f"{metric['smape']:.4f} | {metric['direction_accuracy']:.4f} |"
        )
    lines.extend(["", "## 分预测长度结果", "", "| 模型 | 月数 | MAE | RMSE | sMAPE | 方向准确率 |", "|---|---:|---:|---:|---:|---:|"])
    for row in horizon_rows:
        lines.append(
            f"| {row['model']} | {row['horizon']} | {row['mae']:.4f} | {row['rmse']:.4f} | "
            f"{row['smape']:.4f} | {row['direction_accuracy']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 显著性与判定",
            "",
            f"- 岗位级 PatchTST 胜出比例：{patch_win_ratio:.2%}。",
            f"- 配对 bootstrap 的 `SARIMA MAE - PatchTST MAE`：均值 {bootstrap['mean_difference']:.4f}，"
            f"95% CI [{bootstrap['ci_95_lower']:.4f}, {bootstrap['ci_95_upper']:.4f}]。",
        ]
    )
    for name, passed in conditions.items():
        lines.append(f"- {'通过' if passed else '未通过'}：`{name}`。")
    lines.extend(
        [
            "",
            "## 运行效率",
            "",
            f"- PatchTST {len(config.seeds)} 种子训练总时间：{timing['patchtst_total_train_seconds']:.2f} 秒；"
            f"单岗位单次测试预测平均 {timing['patchtst_mean_test_prediction_seconds']:.6f} 秒。",
            f"- SARIMA 参数搜索时间：{timing['sarima_grid_search_seconds']:.2f} 秒；"
            f"测试集拟合总时间 {timing['sarima_test_fit_seconds']:.2f} 秒；"
            f"单岗位预测平均 {timing['sarima_mean_test_prediction_seconds']:.6f} 秒。",
            "- 时间结果与本机硬件、线程配置和软件版本有关，只用于本实验内的量级比较。",
            "",
            "## 模型优缺点",
            "",
            "- PatchTST 可跨岗位共享模式并学习较复杂的长期关系，但依赖更多训练数据、算力与随机初始化，解释性较弱。",
            "- SARIMA 参数含义清晰、适合小样本和稳定季节模式，但每个岗位需单独拟合，对非线性和跨岗位共性利用有限。",
            "- 当前严格测试仅包含连续观测足够的岗位，样本规模较小；应结合置信区间和岗位级结果解读，避免只看单个总体指标。",
            "",
            "## 产物",
            "",
            "- `experiment_config.json`：完整实验配置与切分。",
            "- `overall_metrics.json`、`horizon_metrics.csv`、`role_metrics.csv`：总体、分长度和岗位级指标。",
            "- `predictions.csv`：逐岗位逐月份真实值与预测值。",
            "- `sarima_search.csv`：SARIMA 验证集网格搜索记录及失败信息。",
            "- `plots/error_by_horizon.png`、`plots/forecast_examples.png`：误差与预测曲线。",
        ]
    )
    (output_dir / "实验报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment(config: ExperimentConfig, quick: bool = False) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_panel(Path(config.dataset_path))
    windows = build_observed_windows(panel, config.context_length, config.horizon)
    split = choose_temporal_split(windows, config.horizon)
    train, validation, test = split_windows(windows, split)

    selected_order, selected_seasonal_order, search_rows = tune_sarima(
        validation, sarima_candidates(quick), config.sarima_maxiter
    )
    sarima_prediction, sarima_failures, sarima_fit_seconds, sarima_predict_seconds = evaluate_sarima(
        test, selected_order, selected_seasonal_order, config.sarima_maxiter
    )
    patch_prediction, patch_seed_rows, patch_train_seconds, patch_predict_seconds = evaluate_patchtst(
        train, validation, test, config
    )
    naive_prediction = np.stack(
        [seasonal_naive_forecast(history[:, 0], config.horizon, config.seasonal_period) for history in test.x]
    )
    predictions = {
        "patchtst": patch_prediction,
        "sarima": sarima_prediction,
        "seasonal_naive": naive_prediction,
    }
    baselines = test.x[:, -1, 0]
    overall = {model: metric_values(test.y, values, baselines) for model, values in predictions.items()}
    horizon_rows = [
        row
        for model, values in predictions.items()
        for row in metrics_by_horizon(model, test.y, values, baselines)
    ]
    role_rows = role_metric_rows(test, predictions)
    role_df = pd.DataFrame(role_rows)
    role_pivot = role_df.pivot(index="canonical_role", columns="model", values="mae")
    patch_win_ratio = float((role_pivot["patchtst"] < role_pivot["sarima"]).mean())
    bootstrap = paired_bootstrap_mae(
        test.y, patch_prediction, sarima_prediction, config.bootstrap_iterations, config.bootstrap_seed
    )
    superior, conditions, conclusion = build_conclusion(
        overall, horizon_rows, bootstrap, patch_win_ratio
    )

    predictions_df = pd.DataFrame(prediction_rows(test, predictions))
    predictions_df.to_csv(output_dir / "predictions.csv", index=False, encoding="utf-8-sig")
    role_df.to_csv(output_dir / "role_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(horizon_rows).to_csv(output_dir / "horizon_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(search_rows).to_csv(output_dir / "sarima_search.csv", index=False, encoding="utf-8-sig")
    plot_paths = create_plots(predictions_df, output_dir)

    timing = {
        "patchtst_total_train_seconds": patch_train_seconds,
        "patchtst_mean_test_prediction_seconds": patch_predict_seconds / (len(config.seeds) * len(test.y)),
        "sarima_grid_search_seconds": float(sum(row["elapsed_seconds"] for row in search_rows)),
        "sarima_test_fit_seconds": sarima_fit_seconds,
        "sarima_mean_test_prediction_seconds": sarima_predict_seconds / len(test.y),
    }
    summary = {
        "status": "ok",
        "conclusion": conclusion,
        "patchtst_superior": superior,
        "conditions": conditions,
        "overall_metrics": overall,
        "bootstrap": bootstrap,
        "patchtst_role_win_ratio": patch_win_ratio,
        "patchtst_seed_metrics": patch_seed_rows,
        "sarima": {
            "order": selected_order,
            "seasonal_order": selected_seasonal_order,
            "test_failures": sarima_failures,
        },
        "timing": timing,
        "plots": plot_paths,
    }
    config_payload = {
        **asdict(config),
        "seeds": list(config.seeds),
        "split": asdict(split),
        "dataset_rows": len(panel),
        "dataset_roles": int(panel["canonical_role"].nunique()),
        "eligible_windows": len(windows.x),
        "train_samples": len(train.x),
        "validation_samples": len(validation.x),
        "test_samples": len(test.x),
        "test_roles": sorted({item["canonical_role"] for item in test.meta}),
    }
    write_json(output_dir / "experiment_config.json", config_payload)
    write_json(output_dir / "overall_metrics.json", summary)
    write_report(
        output_dir, config, panel, windows, train, validation, test, split, overall, horizon_rows,
        bootstrap, patch_win_ratio, patch_seed_rows, selected_order, selected_seasonal_order,
        conditions, conclusion, timing,
    )
    return summary


def main() -> None:
    args = parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    config = ExperimentConfig(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        seeds=(seeds[0],) if args.quick else seeds,
        epochs=5 if args.quick else args.epochs,
        bootstrap_iterations=200 if args.quick else args.bootstrap_iterations,
        sarima_maxiter=min(args.sarima_maxiter, 25) if args.quick else args.sarima_maxiter,
    )
    summary = run_experiment(config, quick=args.quick)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
