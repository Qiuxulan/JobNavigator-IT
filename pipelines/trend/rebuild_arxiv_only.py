from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipelines.trend.build_role_month_features import aggregate_tech
from pipelines.trend.collect_tech_heat import (
    TECH_HEAT_AUDIT_JSON,
    collect_arxiv,
    consolidate_rows,
    grouped_path,
    selected_role_records,
)
from pipelines.trend.common import load_role_taxonomy_local, safe_write_dataframe


def load_existing_keyword_features() -> pd.DataFrame:
    path = grouped_path("tech_keyword_month_features.json")
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "canonical_role",
                "keyword",
                "month",
                "google_trend_index",
                "github_repo_count",
                "github_repo_stars",
                "arxiv_paper_count",
            ]
        )
    return pd.read_json(path)


def merge_arxiv(existing: pd.DataFrame, arxiv_grouped: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["canonical_role", "keyword", "month"]
    if existing.empty:
        return arxiv_grouped.copy()
    base = existing.copy()
    if "arxiv_paper_count" in base.columns:
        base = base.drop(columns=["arxiv_paper_count"])
    merged = base.merge(
        arxiv_grouped[key_cols + ["arxiv_paper_count"]] if not arxiv_grouped.empty else pd.DataFrame(columns=key_cols + ["arxiv_paper_count"]),
        on=key_cols,
        how="left",
    )
    merged["arxiv_paper_count"] = pd.to_numeric(merged.get("arxiv_paper_count"), errors="coerce")
    # include pure arxiv-only rows not present in current keyword table
    if not arxiv_grouped.empty:
        missing = arxiv_grouped.merge(base[key_cols], on=key_cols, how="left", indicator=True)
        missing = missing[missing["_merge"] == "left_only"].drop(columns=["_merge"])
        if not missing.empty:
            missing["google_trend_index"] = None
            missing["github_repo_count"] = None
            missing["github_repo_stars"] = None
            merged = pd.concat([merged, missing[merged.columns]], ignore_index=True)
    return merged


def main() -> None:
    taxonomy_rows = selected_role_records(load_role_taxonomy_local())
    arxiv_rows = collect_arxiv(taxonomy_rows)
    arxiv_grouped = consolidate_rows(arxiv_rows)
    existing = load_existing_keyword_features()
    merged = merge_arxiv(existing, arxiv_grouped)
    safe_write_dataframe(
        merged,
        grouped_path("tech_keyword_month_features.parquet"),
        grouped_path("tech_keyword_month_features.json"),
    )
    tech_role = aggregate_tech(merged, taxonomy_rows)
    safe_write_dataframe(
        tech_role,
        grouped_path("tech_role_month_features.parquet"),
        grouped_path("tech_role_month_features.json"),
    )
    report = {
        "status": "ok",
        "role_count": len(taxonomy_rows),
        "keyword_rows": int(len(merged)),
        "arxiv_keyword_rows": int(len(arxiv_grouped)),
        "arxiv_role_coverage": int(len({row["canonical_role"] for row in arxiv_rows})) if arxiv_rows else 0,
        "audit_file": str(TECH_HEAT_AUDIT_JSON),
    }
    report_path = Path("reports/trend/arxiv_full_rebuild_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report": str(report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
