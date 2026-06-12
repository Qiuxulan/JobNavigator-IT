from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipelines.trend.common import DATA_GOLD_DIR, ROLE_MONTH_FEATURES_JSON, connect_db, fetch_role_taxonomy_from_db, safe_write_dataframe

LOCAL_JD_JSON = DATA_GOLD_DIR / "jd_role_month_features.json"
LOCAL_GDELT_DOC_JSON = DATA_GOLD_DIR / "gdelt_role_month_features.json"
LOCAL_GDELT_GKG_JSON = DATA_GOLD_DIR / "gdelt_gkg_role_month_features.json"
LOCAL_GDELT_IMPACT_JSON = DATA_GOLD_DIR / "gdelt_impact_role_month_features.json"
LOCAL_TECH_JSON = DATA_GOLD_DIR / "tech_keyword_month_features.json"
LOCAL_TECH_ROLE_JSON = DATA_GOLD_DIR / "tech_role_month_features.json"
JD_COLUMNS = [
    "canonical_role",
    "month",
    "jd_demand_index",
    "job_post_count",
    "unique_company_count",
    "avg_salary_mid",
    "median_salary_mid",
    "remote_ratio",
    "avg_experience_required_years",
    "education_bachelor_ratio",
    "education_master_ratio",
    "jd_skill_hit_rate",
    "source_count",
    "hf_post_count",
    "hf_company_count",
    "hf_skill_density",
    "hf_quality_score",
    "hf_source_index",
    "ai_post_count",
    "ai_company_count",
    "ai_salary_mid",
    "ai_remote_signal",
    "ai_benefits_score",
    "ai_skill_density",
    "ai_source_index",
]
GDELT_DOC_COLUMNS = [
    "canonical_role",
    "month",
    "gdelt_article_count",
    "gdelt_sentiment_mean",
    "gdelt_positive_ratio",
    "gdelt_negative_ratio",
    "gdelt_opportunity_index",
    "gdelt_risk_index",
]
GDELT_GKG_COLUMNS = [
    "canonical_role",
    "month",
    "article_count",
    "source_count",
    "avg_tone",
    "positive_score",
    "negative_score",
    "net_positive_score",
    "sentiment_index",
    "risk_index",
    "opportunity_index",
]
GDELT_IMPACT_COLUMNS = ["canonical_role", "month", "impact_score"]
TECH_COLUMNS = ["canonical_role", "keyword", "month", "google_trend_index", "github_repo_count", "github_repo_stars", "arxiv_paper_count"]
TECH_ROLE_COLUMNS = ["canonical_role", "month", "google_trend_index", "github_repo_count", "github_repo_stars", "arxiv_paper_count"]


def normalized_role_phrase(canonical_role: str) -> str | None:
    tokens = []
    for raw in canonical_role.replace("/", " ").replace("-", " ").split():
        token = raw.strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in {"engineer", "developer", "architect", "specialist", "administrator", "manager"}:
            continue
        tokens.append(token)
    phrase = " ".join(tokens).strip()
    return phrase if phrase and phrase.lower() != canonical_role.strip().lower() else None


def build_term_weights(taxonomy_rows: list[dict]) -> dict[tuple[str, str], float]:
    weights: dict[tuple[str, str], float] = {}
    for row in taxonomy_rows:
        skills = [str(skill).strip() for skill in row.get("top_skills", []) if str(skill).strip()]
        role = row["canonical_role"]
        aliases = [str(alias).strip() for alias in row.get("aliases", [])[:2] if str(alias).strip()]
        canonical = str(role).strip()
        title_phrase = normalized_role_phrase(canonical)

        total_budget = 1.0
        title_budget = 0.15 if canonical else 0.0
        phrase_budget = 0.05 if title_phrase else 0.0
        alias_budget = 0.10 if aliases else 0.0
        skill_budget = max(total_budget - title_budget - phrase_budget - alias_budget, 0.0)

        if canonical:
            weights[(role, canonical.lower())] = title_budget
        if title_phrase:
            weights[(role, title_phrase.lower())] = phrase_budget
        if aliases:
            per_alias = alias_budget / len(aliases)
            for alias in aliases:
                weights[(role, alias.lower())] = per_alias
        if skills:
            raw = [1.0 / (idx + 1) for idx in range(len(skills))]
            denom = sum(raw) or 1.0
            for idx, skill in enumerate(skills):
                weights[(role, skill.lower())] = skill_budget * (raw[idx] / denom)
    return weights


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid = (~values.isna()) & (~weights.isna()) & (weights > 0)
    if not valid.any():
        return 0.0
    v = values[valid].astype(float)
    w = weights[valid].astype(float)
    return float((v * w).sum() / w.sum())


def load_local_table(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    try:
        return pd.read_json(path)
    except Exception:
        return pd.DataFrame(columns=columns or [])


def aggregate_tech(df: pd.DataFrame, taxonomy_rows: list[dict]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["canonical_role", "month", "google_trend_index", "github_repo_count", "github_repo_stars", "arxiv_paper_count"])
    weight_map = build_term_weights(taxonomy_rows)
    data = df.copy()
    data["keyword_norm"] = data["keyword"].astype(str).str.lower()
    data["skill_weight"] = data.apply(
        lambda row: weight_map.get((row["canonical_role"], row["keyword_norm"]), 0.0),
        axis=1,
    )
    rows: list[dict] = []
    for (canonical_role, month), chunk in data.groupby(["canonical_role", "month"], as_index=False):
        if float(chunk["skill_weight"].sum()) <= 0:
            chunk = chunk.copy()
            chunk["skill_weight"] = 1.0 / max(len(chunk), 1)
        rows.append(
            {
                "canonical_role": canonical_role,
                "month": month,
                "google_trend_index": weighted_average(chunk["google_trend_index"], chunk["skill_weight"]),
                "github_repo_count": weighted_average(chunk["github_repo_count"], chunk["skill_weight"]),
                "github_repo_stars": weighted_average(chunk["github_repo_stars"], chunk["skill_weight"]),
                "arxiv_paper_count": weighted_average(chunk["arxiv_paper_count"], chunk["skill_weight"]),
            }
        )
    return pd.DataFrame(rows).fillna(0.0)


def read_optional_table(conn, table_name: str, columns: list[str] | None = None) -> pd.DataFrame:
    query = f"SELECT {', '.join(columns) if columns else '*'} FROM {table_name}"
    try:
        with connect_db() as optional_conn:
            return pd.read_sql_query(query, optional_conn)
    except Exception:
        selected = columns or []
        return pd.DataFrame(columns=selected)


def main() -> None:
    db_read_error = None
    try:
        with connect_db() as conn:
            jd = pd.read_sql_query("SELECT * FROM jd_role_month_features", conn)
            gdelt_doc = pd.read_sql_query("SELECT * FROM gdelt_role_month_features", conn)
            gdelt_gkg = read_optional_table(conn, "gdelt_gkg_role_month_features")
            gdelt_events = read_optional_table(conn, "gdelt_event_role_month_features")
            tech = pd.read_sql_query("SELECT * FROM tech_keyword_month_features", conn)
        taxonomy_rows = fetch_role_taxonomy_from_db()
    except Exception as exc:
        db_read_error = str(exc)
        jd = load_local_table(LOCAL_JD_JSON, JD_COLUMNS)
        gdelt_doc = load_local_table(LOCAL_GDELT_DOC_JSON, GDELT_DOC_COLUMNS)
        gdelt_gkg = load_local_table(LOCAL_GDELT_GKG_JSON, GDELT_GKG_COLUMNS)
        gdelt_events = load_local_table(LOCAL_GDELT_IMPACT_JSON, GDELT_IMPACT_COLUMNS)
        tech = load_local_table(LOCAL_TECH_JSON, TECH_COLUMNS)
        from pipelines.trend.common import load_role_taxonomy_local

        taxonomy_rows = load_role_taxonomy_local()

    tech_role = load_local_table(LOCAL_TECH_ROLE_JSON, TECH_ROLE_COLUMNS)
    if tech_role.empty:
        tech_role = aggregate_tech(tech, taxonomy_rows)
    if gdelt_gkg.empty:
        gdelt = gdelt_doc.copy()
        gdelt["gdelt_source_count"] = 0.0
        gdelt["gdelt_sentiment_index"] = gdelt["gdelt_sentiment_mean"].fillna(0.0)
    else:
        gdelt = gdelt_gkg.rename(
            columns={
                "article_count": "gdelt_article_count",
                "source_count": "gdelt_source_count",
                "avg_tone": "gdelt_sentiment_mean",
                "sentiment_index": "gdelt_sentiment_index",
                "opportunity_index": "gdelt_opportunity_index",
                "risk_index": "gdelt_risk_index",
            }
        )
        for col in ("positive_score", "negative_score"):
            if col in gdelt.columns:
                gdelt = gdelt.rename(columns={col: f"gdelt_{col}"})
        if "gdelt_positive_score" in gdelt.columns and "gdelt_positive_ratio" not in gdelt.columns:
            gdelt["gdelt_positive_ratio"] = gdelt["gdelt_positive_score"]
        if "gdelt_negative_score" in gdelt.columns and "gdelt_negative_ratio" not in gdelt.columns:
            gdelt["gdelt_negative_ratio"] = gdelt["gdelt_negative_score"]
    if gdelt_events.empty:
        gdelt_events = pd.DataFrame(columns=["canonical_role", "month", "gdelt_event_impact_score"])
    else:
        gdelt_events = gdelt_events.rename(
            columns={
                "event_impact_score": "gdelt_event_impact_score",
                "impact_score": "gdelt_event_impact_score",
            }
        )
        if "gdelt_event_impact_score" not in gdelt_events.columns:
            gdelt_events["gdelt_event_impact_score"] = 0.0

    merged = jd.merge(gdelt, on=["canonical_role", "month"], how="outer").merge(
        gdelt_events[["canonical_role", "month", "gdelt_event_impact_score"]],
        on=["canonical_role", "month"],
        how="outer",
    ).merge(
        tech_role, on=["canonical_role", "month"], how="outer"
    )
    numeric_cols = [col for col in merged.columns if col not in {"canonical_role", "month", "updated_at"}]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged[numeric_cols] = merged[numeric_cols].fillna(0.0)
    merged["available_source_count"] = (
        ((merged["hf_post_count"].fillna(0) + merged["ai_post_count"].fillna(0)) > 0).astype(int)
        + (merged["gdelt_article_count"].fillna(0) > 0).astype(int)
        + (
            (merged["google_trend_index"].fillna(0) > 0)
            | (merged["github_repo_count"].fillna(0) > 0)
            | (merged["arxiv_paper_count"].fillna(0) > 0)
        ).astype(int)
    )
    merged["job_post_count"] = merged["hf_post_count"].fillna(0) + merged["ai_post_count"].fillna(0)

    preferred_columns = [
        "canonical_role",
        "month",
        "jd_demand_index",
        "job_post_count",
        "unique_company_count",
        "avg_salary_mid",
        "median_salary_mid",
        "remote_ratio",
        "avg_experience_required_years",
        "education_bachelor_ratio",
        "education_master_ratio",
        "jd_skill_hit_rate",
        "source_count",
        "hf_post_count",
        "hf_company_count",
        "hf_skill_density",
        "hf_quality_score",
        "hf_source_index",
        "linkedin_post_count",
        "linkedin_company_count",
        "linkedin_skill_density",
        "linkedin_quality_score",
        "linkedin_experience_signal",
        "linkedin_source_index",
        "ai_post_count",
        "ai_company_count",
        "ai_salary_mid",
        "ai_remote_signal",
        "ai_benefits_score",
        "ai_skill_density",
        "ai_source_index",
        "gdelt_article_count",
        "gdelt_sentiment_mean",
        "gdelt_positive_ratio",
        "gdelt_negative_ratio",
        "gdelt_opportunity_index",
        "gdelt_risk_index",
        "gdelt_source_count",
        "gdelt_sentiment_index",
        "gdelt_event_impact_score",
        "google_trend_index",
        "github_repo_count",
        "github_repo_stars",
        "arxiv_paper_count",
        "available_source_count",
    ]
    merged = merged[[column for column in preferred_columns if column in merged.columns]]
    safe_write_dataframe(merged, ROLE_MONTH_FEATURES_JSON.with_suffix(".parquet"), ROLE_MONTH_FEATURES_JSON)
    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE role_month_features")
            cur.executemany(
                """
                INSERT INTO role_month_features (
                  canonical_role, month, jd_demand_index, job_post_count, unique_company_count, avg_salary_mid, median_salary_mid,
                  remote_ratio, avg_experience_required_years, education_bachelor_ratio, education_master_ratio, jd_skill_hit_rate,
                  gdelt_article_count, gdelt_sentiment_mean, gdelt_positive_ratio, gdelt_negative_ratio, gdelt_opportunity_index, gdelt_risk_index,
                  gdelt_source_count, gdelt_sentiment_index, gdelt_event_impact_score,
                  google_trend_index, github_repo_count, github_repo_stars, arxiv_paper_count, available_source_count, updated_at
                ) VALUES (
                  %(canonical_role)s, %(month)s, %(jd_demand_index)s, %(job_post_count)s, %(unique_company_count)s, %(avg_salary_mid)s, %(median_salary_mid)s,
                  %(remote_ratio)s, %(avg_experience_required_years)s, %(education_bachelor_ratio)s, %(education_master_ratio)s, %(jd_skill_hit_rate)s,
                  %(gdelt_article_count)s, %(gdelt_sentiment_mean)s, %(gdelt_positive_ratio)s, %(gdelt_negative_ratio)s, %(gdelt_opportunity_index)s, %(gdelt_risk_index)s,
                  %(gdelt_source_count)s, %(gdelt_sentiment_index)s, %(gdelt_event_impact_score)s,
                  %(google_trend_index)s, %(github_repo_count)s, %(github_repo_stars)s, %(arxiv_paper_count)s, %(available_source_count)s, NOW()
                )
                ON CONFLICT (canonical_role, month) DO UPDATE SET
                  jd_demand_index = EXCLUDED.jd_demand_index,
                  job_post_count = EXCLUDED.job_post_count,
                  unique_company_count = EXCLUDED.unique_company_count,
                  avg_salary_mid = EXCLUDED.avg_salary_mid,
                  median_salary_mid = EXCLUDED.median_salary_mid,
                  remote_ratio = EXCLUDED.remote_ratio,
                  avg_experience_required_years = EXCLUDED.avg_experience_required_years,
                  education_bachelor_ratio = EXCLUDED.education_bachelor_ratio,
                  education_master_ratio = EXCLUDED.education_master_ratio,
                  jd_skill_hit_rate = EXCLUDED.jd_skill_hit_rate,
                  gdelt_article_count = EXCLUDED.gdelt_article_count,
                  gdelt_sentiment_mean = EXCLUDED.gdelt_sentiment_mean,
                  gdelt_positive_ratio = EXCLUDED.gdelt_positive_ratio,
                  gdelt_negative_ratio = EXCLUDED.gdelt_negative_ratio,
                  gdelt_opportunity_index = EXCLUDED.gdelt_opportunity_index,
                  gdelt_risk_index = EXCLUDED.gdelt_risk_index,
                  gdelt_source_count = EXCLUDED.gdelt_source_count,
                  gdelt_sentiment_index = EXCLUDED.gdelt_sentiment_index,
                  gdelt_event_impact_score = EXCLUDED.gdelt_event_impact_score,
                  google_trend_index = EXCLUDED.google_trend_index,
                  github_repo_count = EXCLUDED.github_repo_count,
                  github_repo_stars = EXCLUDED.github_repo_stars,
                  arxiv_paper_count = EXCLUDED.arxiv_paper_count,
                  available_source_count = EXCLUDED.available_source_count,
                  updated_at = NOW()
                """,
                merged.to_dict(orient="records"),
            )
            conn.commit()
        db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)

    print(json.dumps({"status": "ok", "rows": len(merged), "db_read_error": db_read_error, "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
