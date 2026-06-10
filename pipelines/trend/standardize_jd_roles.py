from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    PROCESSED_JD_LOCAL_JSON,
    PROCESSED_JD_LOCAL_PARQUET,
    RAW_JD_LOCAL_JSON,
    build_processed_jd_rows,
    connect_db,
    fetch_role_taxonomy_from_db,
    load_local_table_rows,
    load_role_taxonomy_local,
    safe_write_dataframe,
)

BATCH_SIZE = 5000


def main() -> None:
    try:
        taxonomy = fetch_role_taxonomy_from_db()
    except Exception:
        taxonomy = load_role_taxonomy_local()
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source, source_job_id, raw_job_title, raw_jd_text, salary_mid, post_date,
                       education_required, experience_required_years, company_name, work_arrangement, job_url
                FROM raw_jd_jobs
                WHERE post_date >= %(min_date)s
                ORDER BY post_date NULLS LAST, source, source_job_id
                """,
                {"min_date": settings.trend_jd_min_date},
            )
            raw_rows = [
                {
                    "source": row[0],
                    "source_job_id": row[1],
                    "raw_job_title": row[2],
                    "raw_jd_text": row[3],
                    "salary_mid": row[4],
                    "post_date": row[5],
                    "education_required": row[6],
                    "experience_required_years": row[7],
                    "company_name": row[8],
                    "work_arrangement": row[9],
                    "job_url": row[10],
                }
                for row in cur.fetchall()
            ]
        db_read_error = None
    except Exception as exc:
        db_read_error = str(exc)
        raw_rows = []
        for name in [
            "raw_jd_jobs_hf_recruitment.json",
            "raw_jd_jobs_linkedin_postings.json",
            "raw_jd_jobs_ai_job_dataset.json",
        ]:
            raw_rows.extend(load_local_table_rows(Path("data/gold") / name))
    if settings.trend_standardize_max_rows > 0:
        raw_rows = raw_rows[: settings.trend_standardize_max_rows]

    total = 0
    all_processed = []
    db_write = {"attempted": True, "success": False, "error": None}
    db_conn = None
    db_cur = None
    try:
        db_conn = connect_db()
        db_cur = db_conn.cursor()
        db_cur.execute("TRUNCATE TABLE processed_jd_jobs")
        db_conn.commit()
    except Exception as exc:
        db_write["error"] = str(exc)
    for start in range(0, len(raw_rows), BATCH_SIZE):
        batch = raw_rows[start : start + BATCH_SIZE]
        processed = build_processed_jd_rows(batch, taxonomy)
        if not processed:
            continue
        all_processed.extend(processed)
        if db_cur is not None:
            db_cur.executemany(
                """
                INSERT INTO processed_jd_jobs (
                  source, source_job_id, canonical_role, role_id, raw_job_title, raw_jd_text, salary_mid, post_date, month,
                  education_required, experience_required_years, company_name, work_arrangement, job_url,
                  role_match_score, matched_by, matched_alias, matched_skills, jd_demand_weight
                ) VALUES (
                  %(source)s, %(source_job_id)s, %(canonical_role)s, %(role_id)s, %(raw_job_title)s, %(raw_jd_text)s, %(salary_mid)s, %(post_date)s, %(month)s,
                  %(education_required)s, %(experience_required_years)s, %(company_name)s, %(work_arrangement)s, %(job_url)s,
                  %(role_match_score)s, %(matched_by)s, %(matched_alias)s, %(matched_skills)s::jsonb, %(jd_demand_weight)s
                )
                ON CONFLICT (source, source_job_id) DO UPDATE SET
                  canonical_role = EXCLUDED.canonical_role,
                  role_id = EXCLUDED.role_id,
                  raw_job_title = EXCLUDED.raw_job_title,
                  raw_jd_text = EXCLUDED.raw_jd_text,
                  salary_mid = EXCLUDED.salary_mid,
                  post_date = EXCLUDED.post_date,
                  month = EXCLUDED.month,
                  education_required = EXCLUDED.education_required,
                  experience_required_years = EXCLUDED.experience_required_years,
                  company_name = EXCLUDED.company_name,
                  work_arrangement = EXCLUDED.work_arrangement,
                  job_url = EXCLUDED.job_url,
                  role_match_score = EXCLUDED.role_match_score,
                  matched_by = EXCLUDED.matched_by,
                  matched_alias = EXCLUDED.matched_alias,
                  matched_skills = EXCLUDED.matched_skills,
                  jd_demand_weight = EXCLUDED.jd_demand_weight
                """,
                [{**row, "matched_skills": json.dumps(row["matched_skills"], ensure_ascii=False)} for row in processed],
            )
            db_conn.commit()
        total += len(processed)
        print(json.dumps({"batch_start": start, "processed_rows": total}, ensure_ascii=False))
    if db_conn is not None:
        db_write["success"] = True
        db_conn.close()
    safe_write_dataframe(pd.DataFrame(all_processed), PROCESSED_JD_LOCAL_PARQUET, PROCESSED_JD_LOCAL_JSON)
    print(json.dumps({"status": "ok", "rows": total, "db_read_error": db_read_error, "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
