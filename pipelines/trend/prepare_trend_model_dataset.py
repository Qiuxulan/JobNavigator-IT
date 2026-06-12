from __future__ import annotations

import json

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    PATCHTST_DATASET_JSON,
    PATCHTST_DATASET_PARQUET,
    ROLE_MONTH_FEATURES_JSON,
    load_role_taxonomy_local,
    safe_write_dataframe,
)


SOURCE_OBSERVED_COLS = ["gdelt_observed", "github_observed", "arxiv_observed"]


def _numeric_series(data: pd.DataFrame, column: str) -> pd.Series:
    if column not in data:
        return pd.Series(0.0, index=data.index, dtype=float)
    return pd.to_numeric(data[column], errors="coerce").fillna(0.0)


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
    if "gdelt_observed" not in data:
        data["gdelt_observed"] = (
            (_numeric_series(data, "gdelt_article_count") > 0)
            | (_numeric_series(data, "gdelt_source_count") > 0)
            | (_numeric_series(data, "gdelt_event_impact_score").abs() > 0)
        )
    if "github_observed" not in data:
        data["github_observed"] = (
            (_numeric_series(data, "github_repo_count") > 0)
            | (_numeric_series(data, "github_repo_stars") > 0)
        )
    if "arxiv_observed" not in data:
        data["arxiv_observed"] = _numeric_series(data, "arxiv_paper_count") > 0
    job_posts = data["job_post_count"] if "job_post_count" in data else pd.Series(0.0, index=data.index)
    demand_index = data["jd_demand_index"] if "jd_demand_index" in data else pd.Series(0.0, index=data.index)
    if "job_post_count" in data:
        jd_signal = pd.to_numeric(job_posts, errors="coerce").fillna(0.0)
    else:
        jd_signal = pd.to_numeric(demand_index, errors="coerce").fillna(0.0).abs()
    observed_jd = data.loc[jd_signal > 0, ["canonical_role", "month"]].copy()
    latest_jd_month_by_role = observed_jd.groupby("canonical_role")["month"].max()
    merged = panel.merge(data, on=["canonical_role", "month"], how="left")
    if "role_id_x" in merged.columns:
        merged["role_id"] = merged["role_id_x"]
        for column in ["role_id_x", "role_id_y"]:
            if column in merged.columns:
                merged = merged.drop(columns=column)
    if latest_jd_month_by_role.empty:
        merged["jd_demand_observed"] = False
    else:
        merged = merged.sort_values(["canonical_role", "month"])
        role_cutoff = merged["canonical_role"].map(latest_jd_month_by_role)
        merged["jd_demand_observed"] = role_cutoff.notna() & (merged["month"] <= role_cutoff)
        future_mask = ~merged["jd_demand_observed"]
        demand_for_carry = merged["jd_demand_index"].mask(future_mask)
        carried_demand = demand_for_carry.groupby(merged["canonical_role"]).ffill()
        merged.loc[future_mask, "jd_demand_index"] = carried_demand[future_mask]

    for column in SOURCE_OBSERVED_COLS:
        merged[column] = merged[column].map(lambda value: bool(value) if pd.notna(value) else False)
    boolean_cols = {"jd_demand_observed", *SOURCE_OBSERVED_COLS}
    numeric_cols = [col for col in merged.columns if col not in {"role_id", "canonical_role", "month", "updated_at", *boolean_cols}]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["month"] = merged["month"].dt.strftime("%Y-%m-%d")
    merged = merged.sort_values(["canonical_role", "month"]).reset_index(drop=True)
    merged["time_idx"] = merged.groupby("canonical_role").cumcount()
    return merged


def main() -> None:
    if not ROLE_MONTH_FEATURES_JSON.exists():
        raise FileNotFoundError(f"corrected trend dataset not found: {ROLE_MONTH_FEATURES_JSON}")
    role_month_df = pd.read_json(ROLE_MONTH_FEATURES_JSON)
    taxonomy_rows = load_role_taxonomy_local()
    taxonomy_df = (
        pd.DataFrame(taxonomy_rows)[["role_id", "canonical_role"]]
        if taxonomy_rows
        else pd.DataFrame()
    )
    if role_month_df.empty:
        raise ValueError(f"corrected trend dataset is empty: {ROLE_MONTH_FEATURES_JSON}")

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
                "input_dataset": str(ROLE_MONTH_FEATURES_JSON),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
