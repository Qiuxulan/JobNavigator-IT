from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import DATA_GOLD_DIR, REPORTS_DIR, connect_db, export_json_report, sigmoid, zscore

WEIGHTS = {
    "jd_demand_index": 0.46,
    "gdelt_opportunity_index": 0.16,
    "gdelt_risk_index": -0.16,
    "gdelt_sentiment_index": 0.08,
    "gdelt_event_impact_score": 0.05,
    "google_trend_index": 0.06,
    "github_repo_count": 0.05,
    "github_repo_stars": 0.04,
    "arxiv_paper_count": 0.03,
    "remote_ratio": 0.02,
    "gdelt_source_count": 0.01,
}

LABELS = {
    "jd_demand_index": "JD需求指数上升",
    "gdelt_opportunity_index": "行业机会类新闻增强",
    "gdelt_risk_index": "行业风险类新闻增强",
    "gdelt_sentiment_index": "行业新闻整体情绪改善",
    "gdelt_event_impact_score": "重大事件冲击提升岗位关注度",
    "google_trend_index": "Google Trends 搜索热度上升",
    "github_repo_count": "GitHub 相关仓库数量增加",
    "github_repo_stars": "GitHub 头部仓库关注度提升",
    "arxiv_paper_count": "arXiv 相关论文关注度提升",
    "remote_ratio": "远程岗位占比提升",
    "gdelt_source_count": "新闻来源覆盖增加",
}
LOCAL_ROLE_MONTH_JSON = DATA_GOLD_DIR / "role_month_features.json"
LOCAL_GDELT_RAW_JSON = DATA_GOLD_DIR / "raw_gdelt_articles.json"
LOCAL_PROCESSED_JD_JSON = DATA_GOLD_DIR / "processed_jd_jobs.json"


def score_direction(value: float) -> str:
    if value >= 0.58:
        return "up"
    if value <= 0.42:
        return "down"
    return "flat"


def compute_confidence(row: pd.Series) -> float:
    def num(name: str) -> float:
        value = row.get(name, 0)
        if value is None or pd.isna(value):
            return 0.0
        return float(value)

    source_component = min(max(num("available_source_count") / 3.0, 0.0), 1.0)
    demand_component = 1.0 if num("job_post_count") > 0 else 0.0
    article_component = 1.0 if num("gdelt_article_count") > 0 else 0.0
    event_component = 1.0 if num("gdelt_event_impact_score") > 0 else 0.0
    tech_component = 1.0 if (
        num("google_trend_index") > 0
        or num("github_repo_count") > 0
        or num("arxiv_paper_count") > 0
    ) else 0.0
    confidence = 0.22 + 0.30 * source_component + 0.15 * demand_component + 0.13 * article_component + 0.10 * tech_component + 0.10 * event_component
    return round(min(confidence, 0.98), 6)


def load_local_json(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_json(path)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df
    except Exception:
        return pd.DataFrame(columns=columns)


def main() -> None:
    db_read_error = None
    try:
        with connect_db() as conn:
            df = pd.read_sql_query("SELECT * FROM role_month_features", conn)
            evidence_df = pd.read_sql_query(
                """
                SELECT canonical_role, url, publish_date
                FROM raw_gdelt_articles
                WHERE url IS NOT NULL AND url <> ''
                """,
                conn,
            )
            jd_urls_df = pd.read_sql_query(
                """
                SELECT canonical_role, job_url, post_date
                FROM processed_jd_jobs
                WHERE job_url IS NOT NULL AND job_url <> ''
                """,
                conn,
            )
    except Exception as exc:
        db_read_error = str(exc)
        df = load_local_json(LOCAL_ROLE_MONTH_JSON, ["canonical_role", "month", *WEIGHTS.keys(), "job_post_count", "gdelt_article_count", "available_source_count"])
        evidence_df = load_local_json(LOCAL_GDELT_RAW_JSON, ["canonical_role", "url", "publish_date"])
        jd_urls_df = load_local_json(LOCAL_PROCESSED_JD_JSON, ["canonical_role", "job_url", "post_date"])

    if df.empty:
        print(json.dumps({"status": "ok", "rows": 0}, ensure_ascii=False, indent=2))
        return

    scaled = df.copy()
    for feature in WEIGHTS:
        if feature not in scaled.columns:
            scaled[feature] = 0.0
        scaled[f"z_{feature}"] = zscore(scaled[feature].fillna(0.0))

    score_breakdowns = []
    outputs = []
    for _, row in scaled.iterrows():
        contributions = {
            feature: round(float(row[f"z_{feature}"]) * weight, 6)
            for feature, weight in WEIGHTS.items()
        }
        raw_score = sum(contributions.values())
        predicted_demand_index = round(sigmoid(raw_score), 6)
        trend_direction = score_direction(predicted_demand_index)
        confidence = compute_confidence(row)
        factors = [
            LABELS[feature]
            for feature, _ in sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)
            if abs(contributions[feature]) > 0.03
        ][:3]

        role = row["canonical_role"]
        gdelt_urls = (
            evidence_df[evidence_df["canonical_role"] == role]
            .sort_values("publish_date", ascending=False)["url"]
            .dropna()
            .tolist()
        )[:3]
        jd_urls = (
            jd_urls_df[jd_urls_df["canonical_role"] == role]
            .sort_values("post_date", ascending=False)["job_url"]
            .dropna()
            .tolist()
        )[:2]
        evidence_urls = list(dict.fromkeys([*gdelt_urls, *jd_urls]))

        outputs.append(
            {
                "canonical_role": role,
                "month": row["month"],
                "horizon_months": settings.trend_horizon_months,
                "trend_direction": trend_direction,
                "predicted_demand_index": predicted_demand_index,
                "confidence": confidence,
                "main_factors_json": json.dumps(factors, ensure_ascii=False),
                "evidence_urls_json": json.dumps(evidence_urls, ensure_ascii=False),
                "score_breakdown_json": json.dumps(contributions, ensure_ascii=False),
                "model_version": "trend-score-v2",
            }
        )
        score_breakdowns.append(
            {
                "canonical_role": role,
                "month": str(row["month"]),
                "predicted_demand_index": predicted_demand_index,
                "trend_direction": trend_direction,
                "confidence": confidence,
                "contributions": contributions,
            }
        )

    out_df = pd.DataFrame(outputs)
    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO role_trend_scores (
                  canonical_role, month, horizon_months, trend_direction, predicted_demand_index,
                  confidence, main_factors_json, evidence_urls_json, score_breakdown_json, model_version, created_at, updated_at
                ) VALUES (
                  %(canonical_role)s, %(month)s, %(horizon_months)s, %(trend_direction)s, %(predicted_demand_index)s,
                  %(confidence)s, %(main_factors_json)s::jsonb, %(evidence_urls_json)s::jsonb, %(score_breakdown_json)s::jsonb, %(model_version)s, NOW(), NOW()
                )
                ON CONFLICT (canonical_role, month, horizon_months) DO UPDATE SET
                  trend_direction = EXCLUDED.trend_direction,
                  predicted_demand_index = EXCLUDED.predicted_demand_index,
                  confidence = EXCLUDED.confidence,
                  main_factors_json = EXCLUDED.main_factors_json,
                  evidence_urls_json = EXCLUDED.evidence_urls_json,
                  score_breakdown_json = EXCLUDED.score_breakdown_json,
                  model_version = EXCLUDED.model_version,
                  updated_at = NOW()
                """,
                out_df.to_dict(orient="records"),
            )
            conn.commit()
        db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)

    export_json_report(score_breakdowns, report_path())
    out_df.to_json(DATA_GOLD_DIR / "role_trend_scores.json", orient="records", force_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "rows": len(out_df), "db_read_error": db_read_error, "db_write": db_write}, ensure_ascii=False, indent=2))


def report_path():
    return REPORTS_DIR / "trend_score_breakdown_v1.json"


if __name__ == "__main__":
    main()
