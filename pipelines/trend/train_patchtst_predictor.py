from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from pipelines.trend.patchtst_predictor import (
    METRICS_PATH,
    MODEL_PATH,
    PatchTSTConfig,
    Standardizer,
    build_supervised_windows,
    load_patchtst_panel,
    predict_scaled,
    save_model_bundle,
    set_seed,
    split_train_validation,
    train_patchtst_model,
    validation_metrics,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train PatchTST trend predictor for role-month demand.")
    parser.add_argument("--context-length", type=int, default=24)
    parser.add_argument("--horizon", type=int, default=36)
    parser.add_argument("--patch-len", type=int, default=6)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-forecast-start-min", type=int, default=36)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PatchTSTConfig(
        context_length=args.context_length,
        horizon=args.horizon,
        patch_len=args.patch_len,
        stride=args.stride,
        d_model=args.d_model,
        n_heads=args.n_heads,
        num_layers=args.num_layers,
        dropout=args.dropout,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        seed=args.seed,
        validation_forecast_start_min=args.validation_forecast_start_min,
    )
    set_seed(config.seed)
    panel = load_patchtst_panel()
    x, y, meta = build_supervised_windows(panel, config)
    train_x, train_y, val_x, val_y, val_meta = split_train_validation(x, y, meta, config)

    validation_standardizer = Standardizer.fit(train_x, train_y)
    validation_model = train_patchtst_model(train_x, train_y, config, validation_standardizer)
    val_pred = predict_scaled(validation_model, val_x, validation_standardizer)
    metrics = validation_metrics(val_y, val_pred)

    final_standardizer = Standardizer.fit(x, y)
    final_model = train_patchtst_model(x, y, config, final_standardizer)
    metrics.update(
        {
            "status": "ok",
            "input_dataset": "data/gold/patchtst_role_month_features.json",
            "roles": int(panel["canonical_role"].nunique()),
            "months": int(panel["month"].nunique()),
            "rows": int(len(panel)),
            "samples": int(len(x)),
            "train_samples": int(len(train_x)),
            "validation_samples": int(len(val_x)),
            "validation_forecast_start_months": sorted({m["forecast_start_month"] for m in val_meta}),
            "model_path": str(MODEL_PATH),
            "config": asdict(config),
        }
    )
    save_model_bundle(final_model, config, final_standardizer, metrics)
    write_json(METRICS_PATH, metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
