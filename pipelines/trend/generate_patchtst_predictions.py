from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipelines.trend.patchtst_predictor import (
    MILESTONES_PATH,
    MODEL_PATH,
    PREDICTIONS_PATH,
    build_prediction_records,
    load_model_bundle,
    load_patchtst_panel,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 36-month PatchTST trend predictions.")
    parser.add_argument("--model-path", default=str(MODEL_PATH))
    parser.add_argument("--predictions-path", default=str(PREDICTIONS_PATH))
    parser.add_argument("--milestones-path", default=str(MILESTONES_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel = load_patchtst_panel()
    model_path = Path(args.model_path)
    predictions_path = Path(args.predictions_path)
    milestones_path = Path(args.milestones_path)
    model, config, standardizer, metrics = load_model_bundle(model_path)
    if config.horizon != 36:
        raise ValueError("deliverable predictions require horizon=36")
    validation_mae = float(metrics.get("mae", 0.15))
    predictions, milestones = build_prediction_records(
        panel=panel,
        model=model,
        config=config,
        standardizer=standardizer,
        validation_mae=validation_mae,
    )
    write_json(predictions_path, predictions)
    write_json(milestones_path, milestones)
    summary = {
        "status": "ok",
        "model_path": str(model_path),
        "predictions_path": str(predictions_path),
        "milestones_path": str(milestones_path),
        "roles": len({row["canonical_role"] for row in predictions}),
        "prediction_rows": len(predictions),
        "milestone_roles": len(milestones),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
