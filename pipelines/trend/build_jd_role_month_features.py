from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from pipelines.trend.common import (
    PROCESSED_JD_LOCAL_JSON,
    ROLE_MONTH_FEATURES_JSON,
    connect_db,
    normalize_optional_float,
    safe_write_dataframe,
)


def median_or_none(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return None if clean.empty else float(clean.median())


def zscore(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").fillna(0.0)
    std = clean.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series([0.0] * len(clean), index=clean.index)
    return (clean - clean.mean()) / std


def sigmoid(value: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-value))


def compute_source_index(df: pd.DataFrame, columns: dict[str, float]) -> pd.Series:
    raw = pd.Series([0.0] * len(df), index=df.index)
    for column, weight in columns.items():
        if column not in df.columns:
            continue
        raw = raw + zscore(df[column]) * weight
    return raw.apply(lambda value: round(sigmoid(float(value)), 6))


def main() -> None:
    try:
        with connect_db() as conn:
            df = pd.read_sql_query(
                """
                SELECT canonical_role, month, salary_mid, experience_required_years, education_required,
                       company_name, work_arrangement, raw_jd_text, matched_skills, jd_demand_weight, source
                FROM processed_jd_jobs
                """,
                conn,
            )
        db_read_error = None
    except Exception as exc:
        db_read_error = str(exc)
        if PROCESSED_JD_LOCAL_JSON.exists():
            df = pd.read_json(PROCESSED_JD_LOCAL_JSON)
        else:
            df = pd.DataFrame()

    if df.empty:
        print(json.dumps({"status": "ok", "rows": 0, "db_read_error": db_read_error}, ensure_ascii=False, indent=2))
        return

    current_month = datetime.now(UTC).date().replace(day=1).isoformat()
    df["month"] = df["month"].astype(str)
    df = df[df["month"] < current_month].copy()
    df["salary_mid"] = pd.to_numeric(df["salary_mid"], errors="coerce")
    df["experience_required_years"] = pd.to_numeric(df["experience_required_years"], errors="coerce")
    df["education_required"] = df["education_required"].fillna("")
    df["is_remote"] = df["work_arrangement"].fillna("").str.lower().eq("remote").astype(int)
    df["is_bachelor"] = df["education_required"].str.contains("bachelor", case=False, na=False).astype(int)
    df["is_master"] = df["education_required"].str.contains("master", case=False, na=False).astype(int)
    df["matched_skill_count"] = df["matched_skills"].fillna("[]").apply(lambda value: len(json.loads(value) if isinstance(value, str) else value))
    df["jd_skill_hit_rate"] = df["matched_skill_count"] / 10.0
    for column in ["source_skill_count", "source_quality_score", "job_description_length", "benefits_score", "remote_ratio_num"]:
        if column not in df.columns:
            df[column] = None
        df[column] = pd.to_numeric(df[column], errors="coerce")

    grouped = (
        df.groupby(["canonical_role", "month"], as_index=False)
        .agg(
            unique_company_count=("company_name", lambda s: int(s.fillna("").replace("", pd.NA).dropna().nunique())),
            avg_salary_mid=("salary_mid", "mean"),
            remote_ratio=("is_remote", "mean"),
            avg_experience_required_years=("experience_required_years", "mean"),
            education_bachelor_ratio=("is_bachelor", "mean"),
            education_master_ratio=("is_master", "mean"),
            jd_skill_hit_rate=("jd_skill_hit_rate", "mean"),
            source_count=("source", lambda s: int(s.nunique())),
        )
    )
    grouped["median_salary_mid"] = (
        df.groupby(["canonical_role", "month"])["salary_mid"].apply(median_or_none).reset_index(drop=True)
    )
    grouped["avg_salary_mid"] = grouped["avg_salary_mid"].round(3)
    grouped["median_salary_mid"] = grouped["median_salary_mid"].apply(lambda x: round(x, 3) if x is not None else None)
    grouped["remote_ratio"] = grouped["remote_ratio"].round(6)
    grouped["avg_experience_required_years"] = grouped["avg_experience_required_years"].round(6)
    grouped["education_bachelor_ratio"] = grouped["education_bachelor_ratio"].round(6)
    grouped["education_master_ratio"] = grouped["education_master_ratio"].round(6)
    grouped["jd_skill_hit_rate"] = grouped["jd_skill_hit_rate"].round(6)
    # 分源独立计算 jd_demand_index，不再使用合并的 job_post_count
    def compute_source_demand_index(source_df: pd.DataFrame, post_weight: float = 0.45) -> pd.Series:
        post_z = zscore(source_df["post_count"]) * post_weight
        company_z = zscore(source_df["company_count"].fillna(0)) * 0.25
        salary_z = zscore(source_df["salary_mid"].fillna(0)) * 0.15
        skill_z = zscore(source_df["skill_density"].fillna(0)) * 0.15
        raw = post_z + company_z + salary_z + skill_z
        return raw.apply(lambda v: round(sigmoid(float(v)), 6))

    def aggregate_source(source_name: str, aggregations: dict[str, tuple[str, str]]) -> pd.DataFrame:
        source_df = df[df["source"] == source_name].copy()
        if source_df.empty:
            return pd.DataFrame(columns=["canonical_role", "month"])
        out = source_df.groupby(["canonical_role", "month"], as_index=False).agg(**aggregations)
        return out

    hf = aggregate_source(
        "hf_recruitment_2022_2023",
        {
            "post_count": ("canonical_role", "size"),
            "company_count": ("company_name", lambda s: int(s.fillna("").replace("", pd.NA).dropna().nunique())),
            "skill_density": ("source_skill_count", "mean"),
            "quality_score": ("source_quality_score", "mean"),
            "salary_mid": ("salary_mid", "mean"),
        },
    )
    if not hf.empty:
        hf = hf.rename(columns={c: f"hf_{c}" for c in ["post_count", "company_count", "skill_density", "quality_score", "salary_mid"]})
        hf["hf_source_index"] = compute_source_index(
            hf, {"hf_post_count": 0.5, "hf_company_count": 0.2, "hf_skill_density": 0.15, "hf_quality_score": 0.15}
        )

    ai = aggregate_source(
        "ai_job_dataset_2024_2025",
        {
            "post_count": ("canonical_role", "size"),
            "company_count": ("company_name", lambda s: int(s.fillna("").replace("", pd.NA).dropna().nunique())),
            "salary_mid": ("salary_mid", "median"),
            "remote_signal": ("remote_ratio_num", "mean"),
            "benefits_score": ("benefits_score", "mean"),
            "skill_density": ("source_skill_count", "mean"),
        },
    )
    if not ai.empty:
        ai = ai.rename(columns={c: f"ai_{c}" for c in ["post_count", "company_count", "salary_mid", "remote_signal", "benefits_score", "skill_density"]})
        ai["ai_source_index"] = compute_source_index(
            ai, {"ai_post_count": 0.3, "ai_salary_mid": 0.25, "ai_remote_signal": 0.15, "ai_benefits_score": 0.15, "ai_skill_density": 0.15}
        )

    for source_frame in [hf, ai]:
        if not source_frame.empty:
            grouped = grouped.merge(source_frame, on=["canonical_role", "month"], how="left")

    for col in grouped.columns:
        if any(suffix in col for suffix in ["_source_index", "_post_count", "_company_count", "_skill_density", "_quality_score", "_salary_mid", "_remote_signal", "_benefits_score"]):
            grouped[col] = pd.to_numeric(grouped[col], errors="coerce")

    # 从各源独立指数融合为统一 jd_demand_index，无合并 job_post_count
    def unify_sources(row: pd.Series) -> float:
        has_hf = pd.notna(row.get("hf_source_index")) and float(row.get("hf_source_index", 0)) > 0
        has_ai = pd.notna(row.get("ai_source_index")) and float(row.get("ai_source_index", 0)) > 0
        blended = 0.0
        w_sum = 0.0
        if has_hf:
            blended += float(row["hf_source_index"]) * 0.60
            w_sum += 0.60
        if has_ai:
            blended += float(row["ai_source_index"]) * 0.40
            w_sum += 0.40
        if w_sum == 0:
            return 0.5
        return round(blended / w_sum, 6)

    grouped["jd_demand_index"] = grouped.apply(unify_sources, axis=1)
    numeric_columns = [
        "avg_salary_mid",
        "median_salary_mid",
        "remote_ratio",
        "avg_experience_required_years",
        "education_bachelor_ratio",
        "education_master_ratio",
        "jd_skill_hit_rate",
        "jd_demand_index",
    ]
    numeric_columns.extend(
        [
            "hf_post_count", "hf_company_count", "hf_skill_density", "hf_quality_score", "hf_salary_mid", "hf_source_index",
            "ai_post_count", "ai_company_count", "ai_salary_mid", "ai_remote_signal", "ai_benefits_score", "ai_skill_density", "ai_source_index",
        ]
    )
    for column in numeric_columns:
        if column in grouped.columns:
            grouped[column] = grouped[column].apply(normalize_optional_float)
    grouped = grouped.astype(object).where(pd.notna(grouped), None)

    safe_write_dataframe(
        grouped,
        ROLE_MONTH_FEATURES_JSON.with_name("jd_role_month_features.parquet"),
        ROLE_MONTH_FEATURES_JSON.with_name("jd_role_month_features.json"),
    )

    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE jd_role_month_features")
            cur.executemany(
                """
                INSERT INTO jd_role_month_features (
                  canonical_role, month, job_post_count, unique_company_count, avg_salary_mid, median_salary_mid,
                  remote_ratio, avg_experience_required_years, education_bachelor_ratio, education_master_ratio,
                  jd_skill_hit_rate, jd_demand_index, source_count, updated_at
                ) VALUES (
                  %(canonical_role)s, %(month)s, %(job_post_count)s, %(unique_company_count)s, %(avg_salary_mid)s, %(median_salary_mid)s,
                  %(remote_ratio)s, %(avg_experience_required_years)s, %(education_bachelor_ratio)s, %(education_master_ratio)s,
                  %(jd_skill_hit_rate)s, %(jd_demand_index)s, %(source_count)s, NOW()
                )
                ON CONFLICT (canonical_role, month) DO UPDATE SET
                  job_post_count = EXCLUDED.job_post_count,
                  unique_company_count = EXCLUDED.unique_company_count,
                  avg_salary_mid = EXCLUDED.avg_salary_mid,
                  median_salary_mid = EXCLUDED.median_salary_mid,
                  remote_ratio = EXCLUDED.remote_ratio,
                  avg_experience_required_years = EXCLUDED.avg_experience_required_years,
                  education_bachelor_ratio = EXCLUDED.education_bachelor_ratio,
                  education_master_ratio = EXCLUDED.education_master_ratio,
                  jd_skill_hit_rate = EXCLUDED.jd_skill_hit_rate,
                  jd_demand_index = EXCLUDED.jd_demand_index,
                  source_count = EXCLUDED.source_count,
                  updated_at = NOW()
                """,
                grouped.to_dict(orient="records"),
            )
            conn.commit()
            db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)

    print(json.dumps({"status": "ok", "rows": len(grouped), "db_read_error": db_read_error, "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
