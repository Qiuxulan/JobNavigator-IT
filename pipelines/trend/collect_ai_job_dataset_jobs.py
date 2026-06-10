from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    AI_JOB_DATASET_PATH,
    ai_focused_taxonomy_rows,
    connect_db,
    date_not_before,
    fetch_role_taxonomy_from_db,
    load_role_taxonomy_local,
    normalize_timestamp,
    normalize_work_arrangement,
    safe_write_dataframe,
    sanitize_for_json,
    looks_it_related_loose,
)


def normalize_record(row: pd.Series) -> dict[str, Any]:
    title = str(row.get("job_title") or "")
    skills_text = str(row.get("required_skills") or "")
    industry = str(row.get("industry") or "")
    education = row.get("education_required")
    experience = row.get("years_experience")
    company = row.get("company_name")
    remote_ratio = pd.to_numeric(row.get("remote_ratio"), errors="coerce")
    if pd.isna(remote_ratio):
        work_arrangement = None
    elif float(remote_ratio) >= 90:
        work_arrangement = "remote"
    elif float(remote_ratio) >= 30:
        work_arrangement = "hybrid"
    else:
        work_arrangement = "onsite"
    description = " | ".join(
        part
        for part in [
            title,
            skills_text,
            industry,
            str(row.get("experience_level") or ""),
            str(row.get("employment_type") or ""),
        ]
        if part
    )
    skill_count = len([token for token in skills_text.split(",") if token.strip()])
    benefits_score = pd.to_numeric(row.get("benefits_score"), errors="coerce")
    return {
        "source": "ai_job_dataset_2024_2025",
        "source_job_id": str(row.get("job_id") or f"ai_{abs(hash(title + str(company))) % (10**12)}"),
        "query_role": None,
        "raw_job_title": title,
        "raw_jd_text": description,
        "salary_mid": pd.to_numeric(row.get("salary_usd"), errors="coerce"),
        "post_date": normalize_timestamp(row.get("posting_date")),
        "education_required": education,
        "experience_required_years": pd.to_numeric(experience, errors="coerce"),
        "company_name": company,
        "work_arrangement": normalize_work_arrangement(work_arrangement),
        "job_url": None,
        "source_skill_count": skill_count,
        "source_quality_score": round(
            0.25
            + min(skill_count / 10.0, 0.35)
            + (0.15 if industry else 0.0)
            + (0.10 if education else 0.0)
            + (0.15 if not pd.isna(remote_ratio) else 0.0),
            6,
        ),
        "job_description_length": int(pd.to_numeric(row.get("job_description_length"), errors="coerce") or 0),
        "benefits_score": None if pd.isna(benefits_score) else float(benefits_score),
        "remote_ratio_num": None if pd.isna(remote_ratio) else float(remote_ratio),
        "industry_label": industry,
        "raw_json": json.dumps(sanitize_for_json(row.to_dict()), ensure_ascii=False, default=str),
    }


def main() -> None:
    if not settings.trend_enable_ai_job_dataset:
        print(json.dumps({"status": "ok", "rows": 0, "reason": "disabled"}, ensure_ascii=False, indent=2))
        return

    try:
        taxonomy = fetch_role_taxonomy_from_db()
    except Exception:
        taxonomy = load_role_taxonomy_local()
    ai_taxonomy = ai_focused_taxonomy_rows(taxonomy)
    data_path = AI_JOB_DATASET_PATH
    if not data_path.exists():
        data_path = (Path.cwd() / settings.trend_ai_job_dataset_path).resolve()
    df = pd.read_csv(data_path, low_memory=False)
    if settings.trend_ai_job_sample_limit > 0:
        df = df.head(settings.trend_ai_job_sample_limit)

    rows = []
    for _, row in df.iterrows():
        normalized = normalize_record(row)
        if not date_not_before(normalized["post_date"], settings.trend_jd_min_date):
            continue
        if not looks_it_related_loose(normalized["raw_job_title"], normalized["raw_jd_text"], ai_taxonomy):
            continue
        rows.append(normalized)

    local_json = Path("data/gold/raw_jd_jobs_ai_job_dataset.json")
    local_parquet = Path("data/gold/raw_jd_jobs_ai_job_dataset.parquet")
    safe_write_dataframe(pd.DataFrame(rows), local_parquet, local_json)

    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM raw_jd_jobs WHERE source = 'ai_job_dataset_2024_2025'")
            cur.executemany(
                """
                INSERT INTO raw_jd_jobs (
                  source, source_job_id, query_role, raw_job_title, raw_jd_text, salary_mid, post_date,
                  education_required, experience_required_years, company_name, work_arrangement, job_url, raw_json
                ) VALUES (
                  %(source)s, %(source_job_id)s, %(query_role)s, %(raw_job_title)s, %(raw_jd_text)s, %(salary_mid)s, %(post_date)s,
                  %(education_required)s, %(experience_required_years)s, %(company_name)s, %(work_arrangement)s, %(job_url)s, %(raw_json)s::jsonb
                )
                ON CONFLICT (source, source_job_id) DO UPDATE SET
                  raw_job_title = EXCLUDED.raw_job_title,
                  raw_jd_text = EXCLUDED.raw_jd_text,
                  salary_mid = EXCLUDED.salary_mid,
                  post_date = EXCLUDED.post_date,
                  education_required = EXCLUDED.education_required,
                  experience_required_years = EXCLUDED.experience_required_years,
                  company_name = EXCLUDED.company_name,
                  work_arrangement = EXCLUDED.work_arrangement,
                  job_url = EXCLUDED.job_url,
                  raw_json = EXCLUDED.raw_json
                """,
                rows,
            )
            conn.commit()
            db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)

    print(json.dumps({"status": "ok", "rows": len(rows), "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
