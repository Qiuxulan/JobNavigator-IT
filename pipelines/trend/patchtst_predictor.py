from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


ROOT = Path(__file__).parents[2]
DATA_GOLD_DIR = ROOT / "data" / "gold"
MODEL_DIR = ROOT / "models" / "patchtst_trend"

PATCHTST_DATASET_PATH = DATA_GOLD_DIR / "patchtst_role_month_features.json"
ROLE_TAXONOMY_PATH = DATA_GOLD_DIR / "role_taxonomy.json"
ROLE_MONTH_FEATURES_PATH = DATA_GOLD_DIR / "role_month_features.json"
MODEL_PATH = MODEL_DIR / "patchtst_trend_model.pt"
METRICS_PATH = MODEL_DIR / "patchtst_metrics.json"
PREDICTIONS_PATH = DATA_GOLD_DIR / "patchtst_predictions_36m.json"
MILESTONES_PATH = DATA_GOLD_DIR / "patchtst_prediction_milestones.json"

TARGET_COL = "jd_demand_index"
FEATURE_COLS = [TARGET_COL]
CALIBRATION_COLS = [
    "gdelt_sentiment_index",
    "gdelt_article_count",
    "gdelt_opportunity_index",
    "gdelt_risk_index",
    "gdelt_event_impact_score",
    "github_repo_count",
    "github_repo_stars",
    "arxiv_paper_count",
]
IDENTITY_COLS = ["role_id", "canonical_role", "month", "time_idx"]
TARGET_OBSERVED_COL = "jd_demand_observed"
SOURCE_OBSERVED_COLS = ["gdelt_observed", "github_observed", "arxiv_observed"]
MILESTONE_STEPS = [3, 6, 12, 24, 36]
SOURCE_CAPS = {"gdelt": 0.03, "github": 0.015, "arxiv": 0.01}
MAX_SUPPLEMENTAL_ADJUSTMENT = 0.05
MAX_SIGNAL_AGE_MONTHS = 6
TREND_CHANGE_THRESHOLD = 0.03


@dataclass
class PatchTSTConfig:
    context_length: int = 24
    horizon: int = 36
    patch_len: int = 6
    stride: int = 3
    d_model: int = 64
    n_heads: int = 4
    num_layers: int = 2
    dropout: float = 0.10
    batch_size: int = 64
    epochs: int = 80
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    seed: int = 42
    validation_forecast_start_min: int = 36


@dataclass
class Standardizer:
    mean: list[float]
    std: list[float]
    target_mean: float
    target_std: float

    @classmethod
    def fit(cls, features: np.ndarray, targets: np.ndarray) -> "Standardizer":
        flat = features.reshape(-1, features.shape[-1])
        mean = flat.mean(axis=0)
        std = flat.std(axis=0)
        std = np.where(std < 1e-6, 1.0, std)
        target_baseline = features[:, -1, FEATURE_COLS.index(TARGET_COL)][:, None]
        target_deltas = targets - target_baseline
        target_mean = float(target_deltas.mean())
        target_std = float(target_deltas.std())
        if target_std < 1e-6:
            target_std = 1.0
        return cls(
            mean=[float(x) for x in mean],
            std=[float(x) for x in std],
            target_mean=target_mean,
            target_std=target_std,
        )

    def transform_x(self, values: np.ndarray) -> np.ndarray:
        mean = np.asarray(self.mean, dtype=np.float32)
        std = np.asarray(self.std, dtype=np.float32)
        return ((values - mean) / std).astype(np.float32)

    def transform_y(self, values: np.ndarray, baselines: np.ndarray) -> np.ndarray:
        deltas = values - baselines[:, None]
        return ((deltas - self.target_mean) / self.target_std).astype(np.float32)

    def inverse_y(self, values: np.ndarray, baselines: np.ndarray) -> np.ndarray:
        deltas = values * self.target_std + self.target_mean
        return deltas + baselines[:, None]


class PatchTST(nn.Module):
    """Small PatchTST-style model for shared role-month forecasting."""

    def __init__(self, config: PatchTSTConfig, n_features: int) -> None:
        super().__init__()
        self.config = config
        self.n_features = n_features
        if config.context_length < config.patch_len:
            raise ValueError("context_length must be >= patch_len")
        self.n_patches = ((config.context_length - config.patch_len) // config.stride) + 1
        token_dim = n_features * config.patch_len
        self.patch_projection = nn.Linear(token_dim, config.d_model)
        self.position_embedding = nn.Parameter(torch.zeros(1, self.n_patches, config.d_model))
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.n_heads,
            dim_feedforward=config.d_model * 4,
            dropout=config.dropout,
            batch_first=True,
            activation="gelu",
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=config.num_layers)
        self.head = nn.Sequential(
            nn.LayerNorm(config.d_model * self.n_patches),
            nn.Linear(config.d_model * self.n_patches, config.d_model),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.d_model, config.horizon),
        )
        nn.init.trunc_normal_(self.position_embedding, std=0.02)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [batch, context_length, n_features]
        patches = x.unfold(dimension=1, size=self.config.patch_len, step=self.config.stride)
        patches = patches.contiguous().view(x.shape[0], self.n_patches, -1)
        tokens = self.patch_projection(patches) + self.position_embedding
        encoded = self.encoder(tokens)
        return self.head(encoded.reshape(encoded.shape[0], -1))


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_patchtst_panel(path: Path = PATCHTST_DATASET_PATH) -> pd.DataFrame:
    if path.resolve() != PATCHTST_DATASET_PATH.resolve():
        raise ValueError("PatchTST training must use data/gold/patchtst_role_month_features.json")
    df = pd.read_json(path)
    required = [*IDENTITY_COLS, *FEATURE_COLS, *CALIBRATION_COLS, TARGET_OBSERVED_COL, *SOURCE_OBSERVED_COLS]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"patchtst dataset is missing columns: {missing}")
    df = df[required].copy()
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    df = df.dropna(subset=["month", "canonical_role"])
    for col in [*FEATURE_COLS, *CALIBRATION_COLS, "time_idx"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df[TARGET_OBSERVED_COL] = df[TARGET_OBSERVED_COL].fillna(False).astype(bool)
    for col in SOURCE_OBSERVED_COLS:
        df[col] = df[col].fillna(False).astype(bool)
    return df.sort_values(["canonical_role", "time_idx"]).reset_index(drop=True)


def load_role_taxonomy(path: Path = ROLE_TAXONOMY_PATH) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("role_taxonomy.json must contain a list")
    return data


def resolve_role(role: str, taxonomy: list[dict[str, Any]] | None = None) -> str:
    taxonomy = taxonomy if taxonomy is not None else load_role_taxonomy()
    query = str(role).strip().lower()
    for item in taxonomy:
        canonical = str(item.get("canonical_role", "")).strip()
        if query in {canonical.lower(), canonical.lower().replace(" ", "-")}:
            return canonical
        for alias in item.get("aliases", []):
            if query == str(alias).strip().lower():
                return canonical
    raise KeyError(f"no canonical role found for {role!r}")


def month_after(month: pd.Timestamp, offset: int) -> str:
    return (month.to_period("M") + offset).to_timestamp().strftime("%Y-%m-%d")


def build_supervised_windows(
    panel: pd.DataFrame,
    config: PatchTSTConfig,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    windows_x: list[np.ndarray] = []
    windows_y: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    for role, group in panel.groupby("canonical_role", sort=True):
        group = group.sort_values("time_idx").reset_index(drop=True)
        values = group[FEATURE_COLS].to_numpy(dtype=np.float32)
        target = group[TARGET_COL].to_numpy(dtype=np.float32)
        target_observed = group[TARGET_OBSERVED_COL].to_numpy(dtype=bool)
        max_start = len(group) - config.context_length - config.horizon + 1
        for start in range(max_start):
            context_end = start + config.context_length
            forecast_end = context_end + config.horizon
            if not target_observed[context_end:forecast_end].all():
                continue
            windows_x.append(values[start:context_end])
            windows_y.append(target[context_end:forecast_end])
            meta.append(
                {
                    "canonical_role": role,
                    "context_start_time_idx": int(group.loc[start, "time_idx"]),
                    "forecast_start_time_idx": int(group.loc[context_end, "time_idx"]),
                    "forecast_start_month": group.loc[context_end, "month"].strftime("%Y-%m-%d"),
                }
            )
    if not windows_x:
        raise ValueError("not enough data to build PatchTST windows")
    return np.stack(windows_x), np.stack(windows_y), meta


def split_train_validation(
    x: np.ndarray,
    y: np.ndarray,
    meta: list[dict[str, Any]],
    config: PatchTSTConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    val_mask = np.array(
        [m["forecast_start_time_idx"] >= config.validation_forecast_start_min for m in meta],
        dtype=bool,
    )
    if val_mask.sum() == 0 or val_mask.sum() == len(val_mask):
        val_mask[:] = False
        val_mask[-max(1, len(val_mask) // 5):] = True
    train_mask = ~val_mask
    return x[train_mask], y[train_mask], x[val_mask], y[val_mask], [m for m, keep in zip(meta, val_mask) if keep]


def train_patchtst_model(
    train_x: np.ndarray,
    train_y: np.ndarray,
    config: PatchTSTConfig,
    standardizer: Standardizer,
    device: str | None = None,
) -> PatchTST:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = PatchTST(config, len(FEATURE_COLS)).to(device)
    train_x_scaled = standardizer.transform_x(train_x)
    target_baselines = train_x[:, -1, FEATURE_COLS.index(TARGET_COL)]
    train_y_scaled = standardizer.transform_y(train_y, target_baselines)
    dataset = TensorDataset(torch.from_numpy(train_x_scaled), torch.from_numpy(train_y_scaled))
    loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    loss_fn = nn.SmoothL1Loss()
    model.train()
    for _ in range(config.epochs):
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
    return model


@torch.no_grad()
def predict_scaled(
    model: PatchTST,
    values: np.ndarray,
    standardizer: Standardizer,
    device: str | None = None,
) -> np.ndarray:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()
    batch = torch.from_numpy(standardizer.transform_x(values)).to(device)
    pred = model(batch).cpu().numpy()
    target_baselines = values[:, -1, FEATURE_COLS.index(TARGET_COL)]
    return np.clip(standardizer.inverse_y(pred, target_baselines), 0.0, 1.0)


def direction_from_score(score: float) -> str:
    if score >= 0.58:
        return "up"
    if score <= 0.42:
        return "down"
    return "flat"


def direction_from_change(change: float, threshold: float = TREND_CHANGE_THRESHOLD) -> str:
    if change >= threshold:
        return "up"
    if change <= -threshold:
        return "down"
    return "flat"


def confidence_for_step(
    step: int,
    validation_mae: float,
    signal_strength: float,
    supplemental_quality: float = 0.0,
) -> float:
    decay = math.exp(-0.035 * max(step - 1, 0))
    error_component = max(0.15, 1.0 - min(validation_mae, 0.5) * 2.0)
    confidence = 0.15 + 0.70 * decay * error_component + 0.15 * signal_strength
    confidence += 0.05 * signal_decay(step) * float(np.clip(supplemental_quality, 0.0, 1.0))
    return round(float(np.clip(confidence, 0.05, 0.95)), 4)


def validation_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    errors = y_pred - y_true
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    smape = float(np.mean(2.0 * np.abs(errors) / (np.abs(y_true) + np.abs(y_pred) + 1e-6)))
    metrics: dict[str, Any] = {"mae": mae, "rmse": rmse, "smape": smape}
    for step in [3, 6, 12]:
        idx = step - 1
        if idx < y_true.shape[1]:
            true_dir = np.where(y_true[:, idx] >= 0.58, 1, np.where(y_true[:, idx] <= 0.42, -1, 0))
            pred_dir = np.where(y_pred[:, idx] >= 0.58, 1, np.where(y_pred[:, idx] <= 0.42, -1, 0))
            metrics[f"horizon_{step}_mae"] = float(np.mean(np.abs(errors[:, idx])))
            metrics[f"horizon_{step}_direction_accuracy"] = float(np.mean(true_dir == pred_dir))
    return metrics


def jd_signal_strength(group: pd.DataFrame) -> float:
    full = group.sort_values("time_idx")
    observed = full[full[TARGET_OBSERVED_COL]]
    if observed.empty or full.empty:
        return 0.0
    jd_values = observed[TARGET_COL].to_numpy(dtype=float)
    jd_coverage = float(len(observed) / len(full))
    if len(jd_values) >= 2:
        denom = max(abs(jd_values[0]), float(np.std(jd_values)), 1e-6)
        jd_trend = float(np.tanh((jd_values[-1] - jd_values[0]) / denom))
        jd_signal = (jd_trend + 1.0) / 2.0
    else:
        jd_signal = 0.5
    combined = 0.65 * jd_coverage + 0.35 * jd_signal
    return float(np.clip(combined, 0.0, 1.0))


def signal_decay(step: int) -> float:
    if step <= 3:
        return 1.0
    if step <= 6:
        return (7.0 - step) / 4.0
    return 0.0


def _month_age(latest_month: pd.Timestamp, prediction_origin: pd.Timestamp) -> int:
    latest = latest_month.to_period("M")
    origin = prediction_origin.to_period("M")
    return max((origin.year - latest.year) * 12 + origin.month - latest.month, 0)


def _robust_trend(values: np.ndarray, *, log_scale: bool = False) -> float:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 2:
        return 0.0
    if log_scale:
        clean = np.log1p(np.clip(clean, 0.0, None))
    slopes = [
        (clean[j] - clean[i]) / (j - i)
        for i in range(len(clean) - 1)
        for j in range(i + 1, len(clean))
    ]
    total_change = float(np.median(slopes)) * (len(clean) - 1)
    scale = max(float(np.ptp(clean)), float(np.std(clean)), 0.05)
    return float(np.clip(np.tanh(total_change / scale), -1.0, 1.0))


def _source_record(
    group: pd.DataFrame,
    source: str,
    observed_col: str,
    prediction_origin: pd.Timestamp,
) -> dict[str, Any]:
    valid = group[group[observed_col]].sort_values("month")
    valid_months = [value.strftime("%Y-%m-%d") for value in valid["month"]]
    latest_month = valid["month"].max() if not valid.empty else None
    age_months = _month_age(latest_month, prediction_origin) if latest_month is not None else None
    stale = age_months is not None and age_months > MAX_SIGNAL_AGE_MONTHS
    eligible = len(valid) >= 2 and not stale
    signal: float | None = None
    if eligible and source == "gdelt":
        components = [
            _robust_trend(valid["gdelt_sentiment_index"].to_numpy(dtype=float)),
            _robust_trend(valid["gdelt_opportunity_index"].to_numpy(dtype=float)),
            -_robust_trend(valid["gdelt_risk_index"].to_numpy(dtype=float)),
        ]
        if valid["gdelt_event_impact_score"].abs().sum() > 0:
            components.append(_robust_trend(valid["gdelt_event_impact_score"].to_numpy(dtype=float)))
        signal = float(np.clip(np.mean(components), -1.0, 1.0))
    elif eligible and source == "github":
        count_signal = _robust_trend(valid["github_repo_count"].to_numpy(dtype=float), log_scale=True)
        star_signal = _robust_trend(valid["github_repo_stars"].to_numpy(dtype=float), log_scale=True)
        signal = float(np.clip(0.75 * count_signal + 0.25 * star_signal, -1.0, 1.0))
    elif eligible and source == "arxiv":
        signal = _robust_trend(valid["arxiv_paper_count"].to_numpy(dtype=float))
    base_contribution = 0.0 if signal is None else float(signal * SOURCE_CAPS[source])
    return {
        "observed": bool(len(valid)),
        "eligible": bool(eligible),
        "valid_months": valid_months,
        "latest_month": None if latest_month is None else latest_month.strftime("%Y-%m-%d"),
        "age_months": age_months,
        "stale": bool(stale),
        "signal": None if signal is None else round(signal, 6),
        "max_adjustment": SOURCE_CAPS[source],
        "base_contribution": round(base_contribution, 6),
    }


def build_supplemental_signals(group: pd.DataFrame, prediction_origin: pd.Timestamp) -> dict[str, dict[str, Any]]:
    return {
        "gdelt": _source_record(group, "gdelt", "gdelt_observed", prediction_origin),
        "github": _source_record(group, "github", "github_observed", prediction_origin),
        "arxiv": _source_record(group, "arxiv", "arxiv_observed", prediction_origin),
    }


def calibration_for_step(
    signals: dict[str, dict[str, Any]],
    step: int,
) -> tuple[float, float, dict[str, dict[str, Any]]]:
    decay = signal_decay(step)
    raw_total = sum(float(item["base_contribution"]) for item in signals.values())
    clipped_total = float(np.clip(raw_total, -MAX_SUPPLEMENTAL_ADJUSTMENT, MAX_SUPPLEMENTAL_ADJUSTMENT))
    contribution_scale = clipped_total / raw_total if abs(raw_total) > MAX_SUPPLEMENTAL_ADJUSTMENT else 1.0
    details: dict[str, dict[str, Any]] = {}
    for source, item in signals.items():
        detail = dict(item)
        detail["contribution"] = round(float(item["base_contribution"]) * contribution_scale * decay, 6)
        details[source] = detail
    adjustment = round(clipped_total * decay, 6)
    eligible_cap = sum(SOURCE_CAPS[source] for source, item in signals.items() if item["eligible"])
    quality = float(np.clip(eligible_cap / sum(SOURCE_CAPS.values()), 0.0, 1.0))
    return adjustment, quality, details


def build_prediction_records(
    panel: pd.DataFrame,
    model: PatchTST,
    config: PatchTSTConfig,
    standardizer: Standardizer,
    validation_mae: float,
    device: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    predictions: list[dict[str, Any]] = []
    milestones: list[dict[str, Any]] = []
    last_month = pd.to_datetime(panel["month"]).max().replace(day=1)
    for role, group in panel.groupby("canonical_role", sort=True):
        group = group.sort_values("time_idx").reset_index(drop=True)
        context = group[FEATURE_COLS].tail(config.context_length).to_numpy(dtype=np.float32)
        pred = predict_scaled(model, context[None, :, :], standardizer, device=device)[0]
        current = float(group[TARGET_COL].iloc[-1])
        signal_strength = jd_signal_strength(group)
        supplemental_signals = build_supplemental_signals(group, last_month)
        monthly: list[dict[str, Any]] = []
        for i, score in enumerate(pred, start=1):
            base_score = round(float(score), 6)
            adjustment, supplemental_quality, signal_details = calibration_for_step(supplemental_signals, i)
            score_float = round(float(np.clip(base_score + adjustment, 0.0, 1.0)), 6)
            change_from_latest = round(score_float - current, 6)
            record = {
                "canonical_role": role,
                "month": month_after(last_month, i),
                "step": i,
                "base_predicted_demand_index": base_score,
                "predicted_demand_index": score_float,
                "trend_direction": direction_from_change(change_from_latest),
                "trend_direction_basis": "change_from_latest",
                "trend_change_threshold": TREND_CHANGE_THRESHOLD,
                "confidence": confidence_for_step(i, validation_mae, signal_strength, supplemental_quality),
                "change_from_latest": change_from_latest,
                "supplemental_adjustment": adjustment,
                "signal_decay": round(signal_decay(i), 6),
                "supplemental_signals": signal_details,
            }
            predictions.append(record)
            monthly.append(record)
        milestone_records = [
            {
                "label": f"{step}_month",
                **monthly[step - 1],
            }
            for step in MILESTONE_STEPS
            if step <= len(monthly)
        ]
        milestones.append({"canonical_role": role, "milestones": milestone_records})
    return predictions, milestones


def save_model_bundle(
    model: PatchTST,
    config: PatchTSTConfig,
    standardizer: Standardizer,
    metrics: dict[str, Any],
    path: Path = MODEL_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.cpu().state_dict(),
            "config": asdict(config),
            "standardizer": asdict(standardizer),
            "feature_cols": FEATURE_COLS,
            "target_col": TARGET_COL,
            "metrics": metrics,
        },
        path,
    )


def load_model_bundle(path: Path = MODEL_PATH, device: str | None = None) -> tuple[PatchTST, PatchTSTConfig, Standardizer, dict[str, Any]]:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    bundle = torch.load(path, map_location=device)
    config = PatchTSTConfig(**bundle["config"])
    standardizer = Standardizer(**bundle["standardizer"])
    model = PatchTST(config, len(bundle.get("feature_cols", FEATURE_COLS)))
    model.load_state_dict(bundle["model_state_dict"])
    model.to(device)
    return model, config, standardizer, bundle.get("metrics", {})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
