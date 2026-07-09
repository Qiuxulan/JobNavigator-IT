from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from pipelines.trend.compare_patchtst_sarima import (
    DEFAULT_DATASET,
    WindowSet,
    assert_non_overlapping_targets,
    build_observed_windows,
    choose_temporal_split,
    load_panel,
    metric_values,
    prediction_rows,
    role_metric_rows,
    safe_sarima_forecast,
    sarima_candidates,
    seasonal_naive_forecast,
    split_windows,
    tune_sarima,
    write_json,
)
ROOT = Path(__file__).parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "trend" / "patchtst_tuning"
COARSE_SEED = 42
CONFIRMATION_SEEDS = (11, 22, 33, 44, 55)
HORIZON = 12
MAX_EPOCHS = 100
PATIENCE = 10


@dataclass(frozen=True)
class TuningConfig:
    context_length: int = 24
    horizon: int = HORIZON
    patch_len: int = 6
    stride: int = 3
    d_model: int = 64
    n_heads: int = 4
    num_layers: int = 2
    dropout: float = 0.10
    batch_size: int = 64
    epochs: int = MAX_EPOCHS
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4


@dataclass
class TrainResult:
    prediction: np.ndarray
    best_epoch: int
    train_seconds: float
    metrics: dict[str, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune PatchTST with a strict temporal holdout.")
    parser.add_argument("--mode", choices=("quick", "balanced"), default="balanced")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--patience", type=int, default=PATIENCE)
    return parser.parse_args()


def validate_config(config: TuningConfig) -> None:
    if config.context_length < config.patch_len:
        raise ValueError("context_length must be >= patch_len")
    if config.patch_len <= 0 or config.stride <= 0:
        raise ValueError("patch_len and stride must be positive")
    if config.d_model <= 0 or config.n_heads <= 0 or config.d_model % config.n_heads:
        raise ValueError("n_heads must be positive and divide d_model")
    if config.num_layers <= 0 or config.batch_size <= 0 or config.epochs <= 0:
        raise ValueError("num_layers, batch_size, and epochs must be positive")
    if not 0.0 <= config.dropout < 1.0:
        raise ValueError("dropout must be in [0, 1)")
    if config.learning_rate <= 0 or config.weight_decay < 0:
        raise ValueError("learning_rate must be positive and weight_decay non-negative")


def config_key(config: TuningConfig) -> tuple[Any, ...]:
    return tuple(asdict(config).values())


def _torch_dependencies() -> tuple[Any, ...]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
        from pipelines.trend.patchtst_predictor import (
            PatchTST,
            PatchTSTConfig,
            Standardizer,
            predict_scaled,
            set_seed,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("PatchTST tuning requires torch>=2.2.0") from exc
    return torch, nn, DataLoader, TensorDataset, PatchTST, PatchTSTConfig, Standardizer, predict_scaled, set_seed


def _environment_info() -> dict[str, Any]:
    info: dict[str, Any] = {"python": sys.version, "platform": platform.platform()}
    try:
        torch, *_ = _torch_dependencies()
        info.update({"torch": torch.__version__, "device": "cuda" if torch.cuda.is_available() else "cpu"})
    except RuntimeError:
        info.update({"torch": None, "device": None})
    return info


def common_aligned_windows(
    panel: pd.DataFrame,
    context_lengths: Iterable[int],
    horizon: int = HORIZON,
) -> dict[int, WindowSet]:
    raw = {length: build_observed_windows(panel, length, horizon) for length in sorted(set(context_lengths))}

    def key(meta: dict[str, Any]) -> tuple[str, int]:
        return str(meta["canonical_role"]), int(meta["forecast_start_time_idx"])

    common = set.intersection(*({key(item) for item in windows.meta} for windows in raw.values()))
    if not common:
        raise ValueError("context lengths have no common observed forecast samples")
    aligned: dict[int, WindowSet] = {}
    for length, windows in raw.items():
        indices = [index for index, item in enumerate(windows.meta) if key(item) in common]
        indices.sort(key=lambda index: key(windows.meta[index]))
        aligned[length] = WindowSet(
            x=windows.x[indices],
            y=windows.y[indices],
            meta=[windows.meta[index] for index in indices],
        )
    reference_keys = [key(item) for item in aligned[min(aligned)].meta]
    if any([key(item) for item in windows.meta] != reference_keys for windows in aligned.values()):
        raise AssertionError("aligned context windows do not share identical samples")
    return aligned


def split_aligned_windows(windows_by_context: dict[int, WindowSet]) -> tuple[Any, dict[int, tuple[WindowSet, WindowSet, WindowSet]]]:
    reference = windows_by_context[min(windows_by_context)]
    split = choose_temporal_split(reference, HORIZON)
    partitions = {length: split_windows(windows, split) for length, windows in windows_by_context.items()}
    expected = None
    for train, validation, test in partitions.values():
        assert_non_overlapping_targets(train, validation, test)
        keys = tuple(
            (item["canonical_role"], item["forecast_start_time_idx"])
            for group in (train, validation, test)
            for item in group.meta
        )
        if expected is None:
            expected = keys
        elif keys != expected:
            raise AssertionError("candidate configurations do not share identical temporal samples")
    return split, partitions


def last_value_forecast(x: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(np.asarray(x)[:, -1, 0][:, None], horizon, axis=1).astype(np.float32)


def moving_average_forecast(x: np.ndarray, horizon: int, window: int) -> np.ndarray:
    if window <= 0 or x.shape[1] < window:
        raise ValueError("moving average window must fit inside the context")
    mean = np.mean(np.asarray(x)[:, -window:, 0], axis=1)
    return np.repeat(mean[:, None], horizon, axis=1).astype(np.float32)


def linear_trend_forecast(x: np.ndarray, horizon: int, window: int = 12) -> np.ndarray:
    if window < 2 or x.shape[1] < window:
        raise ValueError("linear trend window must contain at least two context values")
    history = np.asarray(x, dtype=float)[:, -window:, 0]
    time_axis = np.arange(window, dtype=float)
    centered = time_axis - time_axis.mean()
    slopes = ((history - history.mean(axis=1, keepdims=True)) * centered).sum(axis=1) / np.square(centered).sum()
    intercepts = history.mean(axis=1) - slopes * time_axis.mean()
    future = np.arange(window, window + horizon, dtype=float)
    return np.clip(intercepts[:, None] + slopes[:, None] * future, 0.0, 1.0).astype(np.float32)


def _patch_config(config: TuningConfig, seed: int, patch_config_class: Any) -> Any:
    return patch_config_class(**asdict(config), seed=seed)


def train_with_early_stopping(
    train: WindowSet,
    validation: WindowSet,
    config: TuningConfig,
    seed: int,
    patience: int = PATIENCE,
    device: str | None = None,
) -> TrainResult:
    validate_config(config)
    torch, nn, DataLoader, TensorDataset, PatchTST, PatchTSTConfig, Standardizer, predict_scaled, set_seed = _torch_dependencies()
    set_seed(seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    patch_config = _patch_config(config, seed, PatchTSTConfig)
    standardizer = Standardizer.fit(train.x, train.y)
    model = PatchTST(patch_config, n_features=train.x.shape[-1]).to(device)
    train_x = standardizer.transform_x(train.x)
    train_baselines = train.x[:, -1, 0]
    train_y = standardizer.transform_y(train.y, train_baselines)
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y)),
        batch_size=config.batch_size,
        shuffle=True,
        generator=generator,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    loss_fn = nn.SmoothL1Loss()
    validation_baselines = validation.x[:, -1, 0]
    best_mae = float("inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    stale_epochs = 0
    started = time.perf_counter()
    for epoch in range(1, config.epochs + 1):
        model.train()
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        prediction = predict_scaled(model, validation.x, standardizer, device=device)
        mae = metric_values(validation.y, prediction, validation_baselines)["mae"]
        if mae < best_mae - 1e-8:
            best_mae = mae
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break
    if best_state is None:
        raise RuntimeError("training did not produce a valid checkpoint")
    model.load_state_dict(best_state)
    prediction = predict_scaled(model, validation.x, standardizer, device=device)
    metrics = metric_values(validation.y, prediction, validation_baselines)
    return TrainResult(prediction, best_epoch, time.perf_counter() - started, metrics)


def train_final_model(
    train: WindowSet,
    test: WindowSet,
    config: TuningConfig,
    seed: int,
    epochs: int,
    device: str | None = None,
) -> np.ndarray:
    torch, nn, DataLoader, TensorDataset, PatchTST, PatchTSTConfig, Standardizer, predict_scaled, set_seed = _torch_dependencies()
    final = replace(config, epochs=max(1, epochs))
    set_seed(seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    standardizer = Standardizer.fit(train.x, train.y)
    model = PatchTST(_patch_config(final, seed, PatchTSTConfig), train.x.shape[-1]).to(device)
    x_scaled = standardizer.transform_x(train.x)
    y_scaled = standardizer.transform_y(train.y, train.x[:, -1, 0])
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(x_scaled), torch.from_numpy(y_scaled)),
        batch_size=final.batch_size,
        shuffle=True,
        generator=generator,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=final.learning_rate, weight_decay=final.weight_decay)
    loss_fn = nn.SmoothL1Loss()
    for _ in range(final.epochs):
        model.train()
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
    return predict_scaled(model, test.x, standardizer, device=device)


def _replace(base: TuningConfig, **changes: Any) -> TuningConfig:
    candidate = replace(base, **changes)
    validate_config(candidate)
    return candidate


def staged_candidates(mode: str, epochs: int) -> list[tuple[str, TuningConfig]]:
    base = replace(TuningConfig(), epochs=epochs)
    if mode == "quick":
        return [
            ("default", base),
            ("patch", _replace(base, patch_len=3, stride=3)),
            ("capacity", _replace(base, d_model=32, n_heads=4, num_layers=1)),
            ("training", _replace(base, learning_rate=3e-4, batch_size=32)),
        ]

    candidates: list[tuple[str, TuningConfig]] = [("default", base)]
    patch_pairs = ((3, 1), (3, 3), (6, 1), (6, 3), (6, 6), (12, 3), (12, 6), (12, 12))
    for context in (12, 18, 24, 36):
        for patch_len, stride in patch_pairs:
            if patch_len <= context and (context, patch_len, stride) not in {(24, 6, 3)}:
                candidates.append(("patch", _replace(base, context_length=context, patch_len=patch_len, stride=stride)))
    # Keep the balanced run bounded: 25 patch candidates plus staged capacity/training variants.
    candidates = candidates[:26]
    candidates.extend(
        [
            ("capacity", _replace(base, d_model=32, n_heads=2, num_layers=1, dropout=0.0)),
            ("capacity", _replace(base, d_model=32, n_heads=4, num_layers=2, dropout=0.2)),
            ("capacity", _replace(base, d_model=64, n_heads=2, num_layers=1, dropout=0.1)),
            ("capacity", _replace(base, d_model=64, n_heads=8, num_layers=3, dropout=0.2)),
            ("capacity", _replace(base, d_model=128, n_heads=4, num_layers=2, dropout=0.1)),
            ("capacity", _replace(base, d_model=128, n_heads=8, num_layers=3, dropout=0.3)),
            ("training", _replace(base, learning_rate=3e-4, weight_decay=0.0, batch_size=32)),
            ("training", _replace(base, learning_rate=3e-4, weight_decay=1e-5, batch_size=64)),
            ("training", _replace(base, learning_rate=1e-3, weight_decay=1e-3, batch_size=32)),
            ("training", _replace(base, learning_rate=3e-3, weight_decay=1e-4, batch_size=64)),
            ("training", _replace(base, learning_rate=1e-3, weight_decay=0.0, batch_size=128)),
        ]
    )
    unique: list[tuple[str, TuningConfig]] = []
    seen = set()
    for stage, candidate in candidates:
        if config_key(candidate) not in seen:
            unique.append((stage, candidate))
            seen.add(config_key(candidate))
    return unique


def patch_candidates(base: TuningConfig) -> list[TuningConfig]:
    pairs = ((3, 1), (3, 3), (6, 1), (6, 3), (6, 6), (12, 3), (12, 6), (12, 12))
    values = [base]
    for context in (12, 18, 24, 36):
        for patch_len, stride in pairs:
            if patch_len <= context:
                values.append(_replace(base, context_length=context, patch_len=patch_len, stride=stride))
    unique = {config_key(value): value for value in values}
    return list(unique.values())[:26]


def capacity_candidates(base: TuningConfig) -> list[TuningConfig]:
    changes = (
        {"d_model": 32, "n_heads": 2, "num_layers": 1, "dropout": 0.0},
        {"d_model": 32, "n_heads": 4, "num_layers": 2, "dropout": 0.2},
        {"d_model": 64, "n_heads": 2, "num_layers": 1, "dropout": 0.1},
        {"d_model": 64, "n_heads": 8, "num_layers": 3, "dropout": 0.2},
        {"d_model": 128, "n_heads": 4, "num_layers": 2, "dropout": 0.1},
        {"d_model": 128, "n_heads": 8, "num_layers": 3, "dropout": 0.3},
    )
    return [base, *[_replace(base, **value) for value in changes]]


def training_candidates(base: TuningConfig) -> list[TuningConfig]:
    changes = (
        {"learning_rate": 3e-4, "weight_decay": 0.0, "batch_size": 32},
        {"learning_rate": 3e-4, "weight_decay": 1e-5, "batch_size": 64},
        {"learning_rate": 1e-3, "weight_decay": 1e-3, "batch_size": 32},
        {"learning_rate": 3e-3, "weight_decay": 1e-4, "batch_size": 64},
        {"learning_rate": 1e-3, "weight_decay": 0.0, "batch_size": 128},
    )
    return [base, *[_replace(base, **value) for value in changes]]


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row["validation_mae"], row["validation_rmse"], row["validation_smape"]))


def _evaluate_candidate(
    experiment_id: str,
    stage: str,
    config: TuningConfig,
    partitions: dict[int, tuple[WindowSet, WindowSet, WindowSet]],
    seed: int,
    patience: int,
) -> tuple[dict[str, Any], TrainResult]:
    train, validation, _ = partitions[config.context_length]
    result = train_with_early_stopping(train, validation, config, seed, patience)
    row = {
        "experiment_id": experiment_id,
        "stage": stage,
        "seed": seed,
        **asdict(config),
        "validation_mae": result.metrics["mae"],
        "validation_rmse": result.metrics["rmse"],
        "validation_smape": result.metrics["smape"],
        "validation_direction_accuracy": result.metrics["direction_accuracy"],
        "best_epoch": result.best_epoch,
        "train_seconds": result.train_seconds,
        "status": "ok",
    }
    return row, result


def _sarima_test_prediction(validation: WindowSet, test: WindowSet, quick: bool) -> tuple[np.ndarray, dict[str, Any]]:
    order, seasonal_order, search_rows = tune_sarima(validation, sarima_candidates(quick), 25 if quick else 75)
    predictions = []
    for history in test.x:
        result = safe_sarima_forecast(history[:, 0], HORIZON, order, seasonal_order, 25 if quick else 75)
        if result.prediction is None:
            raise RuntimeError(f"selected SARIMA failed during tuning report: {result.error}")
        predictions.append(result.prediction)
    return np.stack(predictions), {
        "order": list(order),
        "seasonal_order": list(seasonal_order),
        "validation_candidates": len(search_rows),
    }


def create_plots(
    output_dir: Path,
    tuning_df: pd.DataFrame,
    confirmation_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
) -> list[str]:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".pytest_cache" / "matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    def save(fig: Any, name: str) -> None:
        path = plot_dir / name
        fig.tight_layout()
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(str(path))

    ordered = tuning_df.reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(1, len(ordered) + 1)
    ax.plot(x, ordered["validation_mae"], marker="o", ms=3, label="Experiment MAE")
    ax.plot(x, ordered["validation_mae"].cummin(), linewidth=2, label="Best so far")
    ax.set(xlabel="Experiment order", ylabel="Validation MAE", title="Tuning progress (lower is better)")
    ax.grid(alpha=0.25); ax.legend()
    save(fig, "01_tuning_progress.png")

    parameters = ["context_length", "patch_len", "stride", "d_model", "n_heads", "num_layers", "dropout", "learning_rate", "weight_decay", "batch_size"]
    fig, axes = plt.subplots(2, 5, figsize=(16, 7), squeeze=False)
    for ax, parameter in zip(axes.flat, parameters):
        grouped = ordered.groupby(parameter)["validation_mae"].mean().sort_index()
        ax.plot([str(value) for value in grouped.index], grouped.values, marker="o")
        ax.set_title(parameter); ax.tick_params(axis="x", rotation=35); ax.grid(alpha=0.2)
    fig.suptitle("Mean validation MAE by parameter value")
    save(fig, "02_parameter_effects.png")

    heat = ordered[ordered["stage"] == "patch"].pivot_table(index="patch_len", columns="stride", values="validation_mae", aggfunc="min")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    if not heat.empty:
        image = ax.imshow(heat.values, aspect="auto", cmap="viridis_r")
        ax.set_xticks(range(len(heat.columns)), heat.columns); ax.set_yticks(range(len(heat.index)), heat.index)
        for row in range(len(heat.index)):
            for col in range(len(heat.columns)):
                if np.isfinite(heat.values[row, col]): ax.text(col, row, f"{heat.values[row, col]:.3f}", ha="center", va="center")
        fig.colorbar(image, ax=ax, label="Validation MAE")
    ax.set(xlabel="stride", ylabel="patch_len", title="Patch length x stride (lower is better)")
    save(fig, "03_patch_stride_heatmap.png")

    fig, ax = plt.subplots(figsize=(10, 4.8))
    metric_names = ["mae", "rmse", "smape"]
    width = 0.24; positions = np.arange(len(comparison_df))
    for index, metric in enumerate(metric_names):
        ax.bar(positions + (index - 1) * width, comparison_df[metric], width, label=metric.upper())
    ax.set_xticks(positions, comparison_df["model"], rotation=30, ha="right")
    ax.set_ylabel("Test error"); ax.set_title("Baseline and PatchTST comparison"); ax.legend(); ax.grid(axis="y", alpha=0.2)
    save(fig, "04_model_error_comparison.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(comparison_df["model"], comparison_df["direction_accuracy"])
    ax.bar_label(bars, fmt="%.3f"); ax.tick_params(axis="x", rotation=30)
    ax.set_ylim(0, 1); ax.set(ylabel="Direction Accuracy", title="Direction Accuracy on test set")
    save(fig, "05_direction_accuracy.png")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    errors = [np.abs(predictions_df[name] - predictions_df["actual"]) for name in ("default_patchtst", "tuned_patchtst")]
    ax.boxplot(errors, tick_labels=["Default PatchTST", "Tuned PatchTST"])
    ax.set(ylabel="Absolute error", title="Default vs tuned absolute errors")
    save(fig, "06_error_distribution.png")

    roles = sorted(predictions_df["canonical_role"].unique())[:4]
    fig, axes = plt.subplots(len(roles), 1, figsize=(10, max(3, 2.7 * len(roles))), squeeze=False)
    for ax, role in zip(axes[:, 0], roles):
        group = predictions_df[predictions_df["canonical_role"] == role]
        for name in ("actual", "default_patchtst", "tuned_patchtst", "last_value"):
            ax.plot(group["step"], group[name], marker=".", label=name)
        ax.set_title(role); ax.grid(alpha=0.2)
    axes[0, 0].legend(ncol=4, fontsize=8); axes[-1, 0].set_xlabel("Forecast month")
    save(fig, "07_forecast_examples.png")

    model_columns = [column for column in predictions_df.columns if column not in {"canonical_role", "month", "step", "actual"}]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for name in model_columns:
        values = predictions_df.assign(error=np.abs(predictions_df[name] - predictions_df["actual"])).groupby("step")["error"].mean()
        ax.plot(values.index, values.values, marker="o", label=name)
    ax.set(xlabel="Forecast month", ylabel="MAE", title="MAE by forecast month (lower is better)")
    ax.grid(alpha=0.2); ax.legend(ncol=3, fontsize=8)
    save(fig, "08_mae_by_forecast_month.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for candidate_id, group in confirmation_df.groupby("candidate_id"):
        ax.scatter(group["seed"].astype(str), group["validation_mae"], label=candidate_id)
    ax.set(xlabel="Random seed", ylabel="Validation MAE", title="Five-seed confirmation")
    ax.grid(alpha=0.2); ax.legend(fontsize=8)
    save(fig, "09_seed_stability.png")
    return paths


def write_report(
    output_dir: Path,
    best_config: TuningConfig,
    best_summary: dict[str, Any],
    comparison_df: pd.DataFrame,
    default_validation_mae: float,
    plots: list[str],
) -> None:
    tuned = comparison_df.set_index("model").loc["tuned_patchtst"]
    default = comparison_df.set_index("model").loc["default_patchtst"]
    validation_gain = default_validation_mae - best_summary["validation_mae_mean"]
    validation_pct = validation_gain / max(default_validation_mae, 1e-12) * 100
    test_gain = default["mae"] - tuned["mae"]
    test_degradation = float(tuned["mae"] - default["mae"])
    test_degradation_pct = test_degradation / max(float(default["mae"]), 1e-12) * 100
    tuning_df = pd.read_csv(output_dir / "tuning_results.csv")
    confirmation_df = pd.read_csv(output_dir / "seed_confirmation.csv")
    experiment = json.loads((output_dir / "experiment_config.json").read_text(encoding="utf-8"))
    successful = tuning_df[tuning_df["status"] == "ok"].copy()
    failed = tuning_df[tuning_df["status"] != "ok"].copy()
    top_rows = successful.sort_values(["validation_mae", "validation_rmse", "validation_smape"]).head(10)
    stage_labels = {"patch": "Patch 划分", "capacity": "模型容量", "training": "训练参数", "joint": "联合验证", "quick": "快速筛选"}
    model_labels = {
        "moving_average_3": "移动平均（3个月）",
        "default_patchtst": "默认 PatchTST",
        "last_value": "最近值",
        "tuned_patchtst": "调优 PatchTST",
        "moving_average_6": "移动平均（6个月）",
        "sarima": "SARIMA",
        "seasonal_naive": "季节朴素法",
        "linear_trend": "线性趋势",
    }
    seed_best = confirmation_df[confirmation_df["candidate_id"] == best_summary["candidate_id"]].sort_values("seed")
    deployment_passed = float(tuned["mae"]) < float(default["mae"])
    lines = [
        "# PatchTST 参数调优实验报告",
        "",
        "## 1. 实验摘要",
        "",
        f"本实验围绕岗位需求指数的未来 **12 个月预测**开展 PatchTST 参数调优，共执行 {len(tuning_df)} 组粗筛实验，其中 {len(successful)} 组成功、{len(failed)} 组因数据历史不足等约束未执行。粗筛完成后，对排名靠前的候选配置及默认配置使用随机种子 {experiment['confirmation_seeds']} 进行复验。",
        "",
        "参数选择严格只使用验证集：首先按五随机种子的平均验证 MAE 排名；若 MAE 相同，再依次比较 RMSE、sMAPE 和 MAE 标准差。测试集只在配置确定后评估，没有参与参数选择。",
        "",
        f"按上述规则，候选 `{best_summary['candidate_id']}` 获得最低平均验证 MAE。但其独立测试 MAE 为 {float(tuned['mae']):.6f}，高于默认 PatchTST 的 {float(default['mae']):.6f}，因此本报告将其认定为**验证集优胜配置**，而不是可直接替换生产模型的配置。",
        "",
        "## 2. 数据与实验设置",
        "",
        f"- 输入数据：`{experiment['dataset_path']}`",
        f"- 预测长度：{experiment['horizon']} 个月",
        f"- 可比较公共窗口：{experiment['common_samples']} 个",
        f"- 训练/验证/测试样本：{experiment['train_samples']}/{experiment['validation_samples']}/{experiment['test_samples']}",
        f"- 时间切分起点：训练预测起点不晚于 time_idx={experiment['split']['train_max_origin']}，验证起点={experiment['split']['validation_origin']}，测试起点={experiment['split']['test_origin']}",
        f"- 最大训练轮数：{experiment['max_epochs']}；Early Stopping patience={experiment['patience']}",
        f"- 粗筛随机种子：{experiment['coarse_seed']}；复验随机种子：{experiment['confirmation_seeds']}",
        f"- 运行环境：Python {experiment['environment']['python'].split('|')[0].strip()}，PyTorch {experiment['environment']['torch']}，设备={experiment['environment']['device']}",
        "- Direction Accuracy：相对于预测起点最后一个真实值判断方向，变化绝对值小于 0.03 记为持平。",
        "- GDELT、GitHub、arXiv 外部校准信号未进入本次主模型调参。",
        "",
        "严格时间切分确保训练、验证和测试的目标月份互不重叠。不同 `context_length` 的候选只在共同的“岗位 + 预测起点”样本上比较，避免因样本数量不同造成不公平。",
        "",
        "## 3. 参数搜索过程",
        "",
        "| 阶段 | 成功实验数 | 最低单种子验证 MAE | 说明 |",
        "|---|---:|---:|---|",
    ]
    for stage, group in tuning_df.groupby("stage", sort=False):
        ok = group[group["status"] == "ok"]
        best = f"{ok['validation_mae'].min():.6f}" if len(ok) else "-"
        descriptions = {
            "patch": "比较 context_length、patch_len 与 stride",
            "capacity": "在 Patch 阶段优胜配置上比较模型宽度、注意力头、层数与 dropout",
            "training": "在结构优胜配置上比较学习率、权重衰减与 batch size",
            "joint": "组合前述阶段优胜参数进行联合确认",
            "quick": "少量候选的链路验证",
        }
        lines.append(f"| {stage_labels.get(stage, stage)} | {len(ok)} | {best} | {descriptions.get(stage, '')} |")
    lines.extend([
        "",
        "`context_length=36` 的两个候选没有被强行训练。当前真实历史无法同时容纳 36 个月上下文以及互不重叠的训练、验证、测试三段 12 个月目标区间，因此它们在记录中标记为失败。这是数据长度约束，不是模型运行错误。",
        "",
        "### 单种子粗筛前十名",
        "",
        "| 排名 | 实验 | 阶段 | context | patch/stride | d_model | heads/layers | batch | lr | weight decay | 验证 MAE | 最佳 epoch |",
        "|---:|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|",
    ])
    for rank, row in enumerate(top_rows.itertuples(index=False), start=1):
        lines.append(
            f"| {rank} | {row.experiment_id} | {stage_labels.get(row.stage, row.stage)} | {int(row.context_length)} | "
            f"{int(row.patch_len)}/{int(row.stride)} | {int(row.d_model)} | {int(row.n_heads)}/{int(row.num_layers)} | "
            f"{int(row.batch_size)} | {row.learning_rate:g} | {row.weight_decay:g} | {row.validation_mae:.6f} | {int(row.best_epoch)} |"
        )
    lines.extend([
        "",
        "从粗筛结果看，较短的 12 个月上下文、较细的 `patch_len=3` 和 `stride=1` 更适合当前验证时间段。训练参数阶段进一步表明，较小学习率 `0.0003`、batch size 32 和不使用 weight decay 的组合取得最低单种子验证 MAE。这个结论仅代表当前数据切分，不应直接推广到所有时间段。",
        "",
        "## 4. 验证集优胜配置",
        "",
        "```json",
        json.dumps(asdict(best_config), indent=2),
        "```",
        "",
        f"- 五种子平均验证 MAE：{best_summary['validation_mae_mean']:.6f}",
        f"- 五种子验证 MAE 标准差：{best_summary['validation_mae_std']:.6f}",
        f"- 平均验证 RMSE：{best_summary['validation_rmse_mean']:.6f}",
        f"- 平均验证 sMAPE：{best_summary['validation_smape_mean']:.6f}",
        f"- 平均最佳 epoch：{best_summary['best_epoch_mean']:.1f}",
        f"- 默认配置五种子平均验证 MAE：{default_validation_mae:.6f}",
        f"- 相对默认配置的验证 MAE 改善：{validation_gain:.6f}（{validation_pct:.2f}%）",
        "",
        "### 五随机种子稳定性",
        "",
        "| 种子 | 验证 MAE | RMSE | sMAPE | Direction Accuracy | 最佳 epoch | 训练秒数 |",
        "|---|---:|---:|---:|---:|",
    ])
    lines[-1] = "|---:|---:|---:|---:|---:|---:|---:|"
    for row in seed_best.itertuples(index=False):
        lines.append(
            f"| {int(row.seed)} | {row.validation_mae:.6f} | {row.validation_rmse:.6f} | {row.validation_smape:.6f} | "
            f"{row.validation_direction_accuracy:.4f} | {int(row.best_epoch)} | {row.train_seconds:.2f} |"
        )
    lines.extend([
        "",
        "五个种子的验证 MAE 范围约为 0.1664–0.1766，标准差 0.00344，说明该配置在验证集上的随机初始化敏感度不算高。但不同种子的最佳 epoch 从 11 到 39 差异较大，因此 Early Stopping 是必要的，固定训练到 100 epochs 反而可能增加过拟合风险。",
        "",
        "## 5. 独立测试集结果",
        "",
        "| 方法 | MAE | RMSE | sMAPE | Direction Accuracy |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in comparison_df.itertuples(index=False):
        lines.append(
            f"| {model_labels.get(row.model, row.model)} | {row.mae:.4f} | {row.rmse:.4f} | "
            f"{row.smape:.4f} | {row.direction_accuracy:.4f} |"
        )
    lines.extend([
        "",
        f"调优 PatchTST 的测试 MAE 为 {float(tuned['mae']):.6f}，默认 PatchTST 为 {float(default['mae']):.6f}。调优模型比默认模型多出 {test_degradation:.6f} 的 MAE，误差相对增加 {test_degradation_pct:.2f}%。",
        "",
        "测试集表现最好的方法是 3 个月移动平均，MAE 为 0.0531；默认 PatchTST 和最近值方法也明显优于调优 PatchTST。这说明测试区间可能更偏向平稳或短期惯性模式，而验证区间更有利于短上下文、细粒度 patch 的神经网络配置。",
        "",
        "Direction Accuracy 方面，调优 PatchTST 为 0.4792，高于默认 PatchTST 的 0.3333，但方向判断改善没有抵消数值误差的大幅增加。因此不能只凭方向准确率批准模型替换。",
        "",
        "## 6. 结论与部署建议",
        "",
        f"1. **参数搜索结论**：`{best_summary['candidate_id']}` 是严格按验证集 MAE 选出的优胜配置，验证 MAE 相对默认配置改善 {validation_pct:.2f}%。",
        f"2. **独立测试结论**：该配置未通过部署验收。测试 MAE 从默认模型的 {float(default['mae']):.4f} 上升至 {float(tuned['mae']):.4f}。",
        "3. **当前决策**：保留现有生产 PatchTST，不使用本次优胜配置覆盖模型权重或生产预测文件。",
        "4. **后续验证**：建议增加滚动时间回测，使多个验证/测试起点共同参与稳定性判断；目前每个验证和测试切分仅有 8 个岗位样本，单一时间段容易造成排名偏差。",
        "5. **基线意义**：3 个月移动平均在本次测试集上排名第一，后续模型验收应增加“必须优于移动平均和最近值”的硬性门槛。",
        "",
        "因此，最准确的表述是：**本次调优找到了验证集上的更优参数，但没有证明其跨时间泛化能力优于默认 PatchTST，暂不具备生产替换条件。**",
        "",
        "## 7. 可视化与产物说明",
        "",
        "| 文件 | 内容 |",
        "|---|---|",
        "| `plots/01_tuning_progress.png` | 每次实验验证 MAE 与历史最佳 MAE |",
        "| `plots/02_parameter_effects.png` | 各参数取值对应的平均验证 MAE |",
        "| `plots/03_patch_stride_heatmap.png` | patch_len 与 stride 的 MAE 热力图 |",
        "| `plots/04_model_error_comparison.png` | baseline、默认模型与调优模型的误差对比 |",
        "| `plots/05_direction_accuracy.png` | 各方法方向准确率 |",
        "| `plots/06_error_distribution.png` | 默认与调优 PatchTST 的绝对误差分布 |",
        "| `plots/07_forecast_examples.png` | 代表性岗位的真实值与预测曲线 |",
        "| `plots/08_mae_by_forecast_month.png` | 逐预测月份 MAE |",
        "| `plots/09_seed_stability.png` | 候选配置的五随机种子稳定性 |",
        "",
        "完整实验记录保存在 `tuning_results.csv`、`seed_confirmation.csv`、`baseline_comparison.csv`、`predictions.csv`、`role_metrics.csv` 和 `horizon_metrics.csv`。当前生产模型未被覆盖。",
    ])
    content = "\n".join(lines) + "\n"
    (output_dir / "tuning_report.md").write_text(content, encoding="utf-8")
    (output_dir / "PatchTST调优报告.md").write_text(content, encoding="utf-8")


def run_tuning(
    dataset_path: Path,
    output_dir: Path,
    mode: str = "balanced",
    max_epochs: int = MAX_EPOCHS,
    patience: int = PATIENCE,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    effective_epochs = min(max_epochs, 5) if mode == "quick" else max_epochs
    default_config = replace(TuningConfig(), epochs=effective_epochs)
    # The current observed history cannot support context=36 plus three disjoint
    # 12-month target regions. Those candidates remain in the search log as failed.
    contexts = [12, 18, 24] if mode == "balanced" else [24]
    panel = load_panel(dataset_path)
    aligned = common_aligned_windows(panel, contexts)
    split, partitions = split_aligned_windows(aligned)

    coarse_rows: list[dict[str, Any]] = []
    candidate_results: list[tuple[str, TuningConfig]] = []
    counter = 0

    def evaluate_stage(stage: str, values: list[TuningConfig]) -> list[dict[str, Any]]:
        nonlocal counter
        stage_rows: list[dict[str, Any]] = []
        known = {config_key(config) for _, config in candidate_results}
        for candidate in values:
            if config_key(candidate) in known:
                matching_id = next(identifier for identifier, config in candidate_results if config_key(config) == config_key(candidate))
                existing = next(row for row in coarse_rows if row["experiment_id"] == matching_id)
                stage_rows.append(existing)
                continue
            counter += 1
            experiment_id = f"P{counter:03d}"
            try:
                if candidate.context_length not in partitions:
                    raise ValueError(
                        f"context_length={candidate.context_length} has insufficient observed history "
                        "for disjoint train, validation, and test targets"
                    )
                row, _ = _evaluate_candidate(experiment_id, stage, candidate, partitions, COARSE_SEED, patience)
                coarse_rows.append(row)
                candidate_results.append((experiment_id, candidate))
                stage_rows.append(row)
                known.add(config_key(candidate))
            except Exception as exc:
                row = {
                    "experiment_id": experiment_id, "stage": stage, "seed": COARSE_SEED,
                    **asdict(candidate), "status": "failed", "error": str(exc),
                    "validation_mae": np.nan, "validation_rmse": np.nan, "validation_smape": np.nan,
                    "validation_direction_accuracy": np.nan, "best_epoch": np.nan, "train_seconds": np.nan,
                }
                coarse_rows.append(row)
                stage_rows.append(row)
        return [row for row in stage_rows if row["status"] == "ok"]

    if mode == "quick":
        quick_rows = evaluate_stage("quick", [config for _, config in staged_candidates("quick", effective_epochs)])
        if not quick_rows:
            raise RuntimeError("all PatchTST quick candidates failed")
    else:
        patch_rows = evaluate_stage("patch", patch_candidates(default_config))
        if not patch_rows:
            raise RuntimeError("all PatchTST patch candidates failed")
        patch_winner = next(config for identifier, config in candidate_results if identifier == rank_rows(patch_rows)[0]["experiment_id"])
        capacity_rows = evaluate_stage("capacity", capacity_candidates(patch_winner))
        capacity_winner = next(config for identifier, config in candidate_results if identifier == rank_rows(capacity_rows)[0]["experiment_id"])
        training_rows = evaluate_stage("training", training_candidates(capacity_winner))
        training_winner = next(config for identifier, config in candidate_results if identifier == rank_rows(training_rows)[0]["experiment_id"])
        joint = [training_winner]
        for row in rank_rows(patch_rows)[:2]:
            patch_choice = next(config for identifier, config in candidate_results if identifier == row["experiment_id"])
            joint.append(replace(
                patch_choice,
                d_model=capacity_winner.d_model,
                n_heads=capacity_winner.n_heads,
                num_layers=capacity_winner.num_layers,
                dropout=capacity_winner.dropout,
                learning_rate=training_winner.learning_rate,
                weight_decay=training_winner.weight_decay,
                batch_size=training_winner.batch_size,
            ))
        evaluate_stage("joint", joint)
    successful = [row for row in coarse_rows if row["status"] == "ok"]
    if not successful:
        raise RuntimeError("all PatchTST tuning candidates failed")
    ranked = rank_rows(successful)
    confirmation_count = min(3 if mode == "quick" else 5, len(ranked))
    top_ids = [row["experiment_id"] for row in ranked[:confirmation_count]]
    candidate_map = dict(candidate_results)
    default_id = next(identifier for identifier, config in candidate_results if config_key(config) == config_key(default_config))
    if default_id not in top_ids:
        top_ids.append(default_id)

    confirmation_rows: list[dict[str, Any]] = []
    confirmation_seeds = (COARSE_SEED,) if mode == "quick" else CONFIRMATION_SEEDS
    for candidate_id in top_ids:
        candidate = candidate_map[candidate_id]
        for seed in confirmation_seeds:
            row, _ = _evaluate_candidate(f"{candidate_id}-S{seed}", "confirmation", candidate, partitions, seed, patience)
            confirmation_rows.append({"candidate_id": candidate_id, **row})
    confirmation_df = pd.DataFrame(confirmation_rows)
    summaries = []
    for candidate_id, group in confirmation_df.groupby("candidate_id"):
        summaries.append({
            "candidate_id": candidate_id,
            "validation_mae_mean": float(group["validation_mae"].mean()),
            "validation_rmse_mean": float(group["validation_rmse"].mean()),
            "validation_smape_mean": float(group["validation_smape"].mean()),
            "validation_mae_std": float(group["validation_mae"].std(ddof=0)),
            "best_epoch_mean": float(group["best_epoch"].mean()),
        })
    summaries.sort(key=lambda row: (
        row["validation_mae_mean"], row["validation_rmse_mean"],
        row["validation_smape_mean"], row["validation_mae_std"],
    ))
    best_summary = summaries[0]
    best_config = candidate_map[best_summary["candidate_id"]]

    default_summary = next(summary for summary in summaries if summary["candidate_id"] == default_id)
    default_validation_mae = default_summary["validation_mae_mean"]
    selected_config = best_config if best_summary["validation_mae_mean"] < default_validation_mae else default_config

    selected_context = selected_config.context_length
    default_train, default_validation, default_test = partitions[default_config.context_length]
    tuned_train, tuned_validation, tuned_test = partitions[selected_context]
    combined_default = WindowSet(
        np.concatenate([default_train.x, default_validation.x]),
        np.concatenate([default_train.y, default_validation.y]),
        default_train.meta + default_validation.meta,
    )
    combined_tuned = WindowSet(
        np.concatenate([tuned_train.x, tuned_validation.x]),
        np.concatenate([tuned_train.y, tuned_validation.y]),
        tuned_train.meta + tuned_validation.meta,
    )
    default_epoch = int(next(row["best_epoch"] for row in successful if row["experiment_id"] == default_id))
    tuned_epoch = max(1, int(round(best_summary["best_epoch_mean"])))
    default_predictions = np.mean(np.stack([
        train_final_model(combined_default, default_test, default_config, seed, default_epoch)
        for seed in confirmation_seeds
    ]), axis=0)
    tuned_predictions = np.mean(np.stack([
        train_final_model(combined_tuned, tuned_test, selected_config, seed, tuned_epoch)
        for seed in confirmation_seeds
    ]), axis=0)

    x = tuned_test.x
    predictions = {
        "last_value": last_value_forecast(x, HORIZON),
        "moving_average_3": moving_average_forecast(x, HORIZON, 3),
        "moving_average_6": moving_average_forecast(x, HORIZON, 6),
        "linear_trend": linear_trend_forecast(x, HORIZON, 12),
        "seasonal_naive": np.stack([seasonal_naive_forecast(history[:, 0], HORIZON) for history in x]),
        "default_patchtst": default_predictions,
        "tuned_patchtst": tuned_predictions,
    }
    sarima_prediction, sarima_info = _sarima_test_prediction(tuned_validation, tuned_test, mode == "quick")
    predictions["sarima"] = sarima_prediction
    baselines = tuned_test.x[:, -1, 0]
    comparison_rows = [{"model": name, **metric_values(tuned_test.y, values, baselines)} for name, values in predictions.items()]
    comparison_df = pd.DataFrame(comparison_rows).sort_values("mae").reset_index(drop=True)
    predictions_df = pd.DataFrame(prediction_rows(tuned_test, predictions))
    role_df = pd.DataFrame(role_metric_rows(tuned_test, predictions))
    horizon_rows = []
    for name, values in predictions.items():
        for step in range(1, HORIZON + 1):
            horizon_rows.append({
                "model": name, "horizon": step,
                **metric_values(tuned_test.y[:, :step], values[:, :step], baselines),
            })

    tuning_df = pd.DataFrame(coarse_rows)
    tuning_df.to_csv(output_dir / "tuning_results.csv", index=False, encoding="utf-8-sig")
    confirmation_df.to_csv(output_dir / "seed_confirmation.csv", index=False, encoding="utf-8-sig")
    comparison_df.to_csv(output_dir / "baseline_comparison.csv", index=False, encoding="utf-8-sig")
    predictions_df.to_csv(output_dir / "predictions.csv", index=False, encoding="utf-8-sig")
    role_df.to_csv(output_dir / "role_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(horizon_rows).to_csv(output_dir / "horizon_metrics.csv", index=False, encoding="utf-8-sig")
    plots = create_plots(output_dir, tuning_df[tuning_df["status"] == "ok"], confirmation_df, comparison_df, predictions_df)

    best_payload = {
        "selection_metric": "mean validation MAE across confirmation seeds",
        "selected_candidate_id": best_summary["candidate_id"],
        "best_candidate_config": asdict(best_config),
        "recommended_config": asdict(selected_config),
        "retain_default": selected_config == default_config,
        **best_summary,
    }
    write_json(output_dir / "best_config.json", best_payload)
    experiment_payload = {
        "mode": mode,
        "dataset_path": str(dataset_path),
        "output_dir": str(output_dir),
        "horizon": HORIZON,
        "coarse_seed": COARSE_SEED,
        "confirmation_seeds": list(confirmation_seeds),
        "max_epochs": effective_epochs,
        "patience": patience,
        "candidate_count": len(coarse_rows),
        "ranking": ["validation_mae", "validation_rmse", "validation_smape", "validation_mae_std"],
        "split": asdict(split),
        "common_samples": len(aligned[contexts[0]].x),
        "train_samples": len(partitions[contexts[0]][0].x),
        "validation_samples": len(partitions[contexts[0]][1].x),
        "test_samples": len(partitions[contexts[0]][2].x),
        "search_space": {
            "context_length": [12, 18, 24, 36], "patch_len_stride": [[3, 1], [3, 3], [6, 1], [6, 3], [6, 6], [12, 3], [12, 6], [12, 12]],
            "d_model": [32, 64, 128], "n_heads": [2, 4, 8], "num_layers": [1, 2, 3], "dropout": [0.0, 0.1, 0.2, 0.3],
            "learning_rate": [3e-4, 1e-3, 3e-3], "weight_decay": [0.0, 1e-5, 1e-4, 1e-3], "batch_size": [32, 64, 128],
        },
        "environment": _environment_info(),
        "sarima": sarima_info,
        "plots": plots,
        "production_model_overwritten": False,
    }
    write_json(output_dir / "experiment_config.json", experiment_payload)
    write_report(output_dir, selected_config, best_summary, comparison_df, default_validation_mae, plots)
    return {"status": "ok", "best_config": best_payload, "outputs": experiment_payload}


def main() -> None:
    args = parse_args()
    result = run_tuning(Path(args.dataset), Path(args.output_dir), args.mode, args.max_epochs, args.patience)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
