from __future__ import annotations

import json

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    PATCHTST_DATASET_JSON,
    PATCHTST_DATASET_PARQUET,
    ROLE_MONTH_FEATURES_JSON,
    connect_db,
    load_role_taxonomy_local,
    safe_write_dataframe,
)


def build_patchtst_panel(role_month_df: pd.DataFrame, taxonomy_df: pd.DataFrame) -> pd.DataFrame:
    if role_month_df.empty:
        return role_month_df.copy()
    months = pd.to_datetime(role_month_df["month"], errors="coerce").dropna()
    if months.empty:
        return pd.DataFrame()
    max_month = months.max().replace(day=1)
    lookback = max(int(settings.trend_patchtst_lookback_months), 1)
    start_period = (max_month.to_period("M") - (lookback - 1))
    start_month = start_period.to_timestamp()
    roles = taxonomy_df[["role_id", "canonical_role"]].drop_duplicates().copy()
    if roles.empty:
        roles = pd.DataFrame({"role_id": sorted(role_month_df["canonical_role"].astype(str).unique()), "canonical_role": sorted(role_month_df["canonical_role"].astype(str).unique())})
    month_index = pd.date_range(start_month, max_month, freq="MS")
    panel = (
        roles.assign(_key=1)
        .merge(pd.DataFrame({"month": month_index, "_key": 1}), on="_key", how="inner")
        .drop(columns="_key")
    )
    data = role_month_df.copy()
    data["month"] = pd.to_datetime(data["month"], errors="coerce")
    data = data[data["month"] >= start_month]
    merged = panel.merge(data, on=["canonical_role", "month"], how="left")
    if "role_id_x" in merged.columns:
        merged["role_id"] = merged["role_id_x"]
        for column in ["role_id_x", "role_id_y"]:
            if column in merged.columns:
                merged = merged.drop(columns=column)
    numeric_cols = [col for col in merged.columns if col not in {"role_id", "canonical_role", "month", "updated_at"}]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["month"] = merged["month"].dt.strftime("%Y-%m-%d")
    merged = merged.sort_values(["canonical_role", "month"]).reset_index(drop=True)
    merged["time_idx"] = merged.groupby("canonical_role").cumcount()
    return merged


def main() -> None:
    db_read_error = None
    try:
        with connect_db() as conn:
            role_month_df = pd.read_sql_query("SELECT * FROM role_month_features ORDER BY canonical_role, month", conn)
            taxonomy_df = pd.read_sql_query("SELECT role_id, canonical_role FROM role_taxonomy ORDER BY canonical_role", conn)
    except Exception as exc:
        db_read_error = str(exc)
        role_month_df = pd.read_json(ROLE_MONTH_FEATURES_JSON) if ROLE_MONTH_FEATURES_JSON.exists() else pd.DataFrame()
        taxonomy_df = pd.DataFrame(load_role_taxonomy_local())[["role_id", "canonical_role"]] if load_role_taxonomy_local() else pd.DataFrame()

    if role_month_df.empty:
        print(json.dumps({"status": "ok", "rows": 0, "db_read_error": db_read_error}, ensure_ascii=False, indent=2))
        return

    panel = build_patchtst_panel(role_month_df, taxonomy_df)
    safe_write_dataframe(panel, PATCHTST_DATASET_PARQUET, PATCHTST_DATASET_JSON)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(panel),
                "roles": int(panel["canonical_role"].nunique()) if not panel.empty else 0,
                "months": int(panel["month"].nunique()) if not panel.empty else 0,
                "parquet": str(PATCHTST_DATASET_PARQUET),
                "json": str(PATCHTST_DATASET_JSON),
                "db_read_error": db_read_error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
