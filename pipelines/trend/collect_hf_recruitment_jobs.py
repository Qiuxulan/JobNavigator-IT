from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    RAW_JD_LOCAL_JSON,
    RAW_JD_LOCAL_PARQUET,
    connect_db,
    date_not_before,
    fetch_role_taxonomy_from_db,
    load_hf_recruitment_local_dataframe,
    load_role_taxonomy_local,
    looks_it_related_loose,
    normalize_timestamp,
    normalize_years,
    safe_write_dataframe,
    sanitize_for_json,
)


def normalize_record(item: dict[str, Any]) -> dict[str, Any]:
    title = (
        item.get("Position")
        or item.get("position")
        or item.get("job_title")
        or item.get("title")
        or item.get("job")
        or ""
    )
    description = (
        item.get("Long Description")
        or item.get("long_description")
        or item.get("job_description")
        or item.get("description")
        or item.get("description_text")
        or item.get("job_summary")
        or ""
    )
    post_date = (
        item.get("Published")
        or item.get("published")
        or item.get("posted_date")
        or item.get("post_date")
        or item.get("date")
        or item.get("listed_time")
        or item.get("original_listed_time")
    )
    company = item.get("Company Name") or item.get("company_name") or item.get("company") or item.get("employer_name")
    url = item.get("job_url") or item.get("url") or item.get("apply_url")
    work_arrangement = item.get("work_arrangement") or item.get("remote") or item.get("location_type")
    salary_mid = item.get("salary_mid") or item.get("salary") or item.get("salary_yearly")
    source_job_id = (
        item.get("id")
        or item.get("job_id")
        or item.get("uuid")
        or item.get("link")
        or f"hf_{abs(hash(title + str(post_date) + str(company))) % (10**12)}"
    )
    return {
        "source": "hf_recruitment_2022_2023",
        "source_job_id": str(source_job_id),
        "query_role": None,
        "raw_job_title": str(title),
        "raw_jd_text": str(description),
        "salary_mid": salary_mid,
        "post_date": normalize_timestamp(post_date),
        "education_required": item.get("education_required") or item.get("education") or item.get("English Level"),
        "experience_required_years": normalize_years(
            item.get("required_experience_years") or item.get("experience_required_years") or item.get("Exp Years")
        ),
        "company_name": company,
        "work_arrangement": work_arrangement,
        "job_url": url,
        "source_skill_count": max(int(str(description).count(",")) + 1, 0) if description else 0,
        "source_quality_score": round(
            min(len(str(description)) / 2500.0, 1.0) * 0.6
            + (0.2 if company else 0.0)
            + (0.2 if post_date else 0.0),
            6,
        ),
        "job_description_length": len(str(description)),
        "raw_json": json.dumps(sanitize_for_json(item), ensure_ascii=False),
    }


def main() -> None:
    if not settings.trend_enable_hf_recruitment:
        print(json.dumps({"status": "ok", "rows": 0, "reason": "disabled"}, ensure_ascii=False, indent=2))
        return

    local_df = load_hf_recruitment_local_dataframe()
    dataset_source = "remote"
    if local_df is not None:
        dataset_source = str(Path(settings.trend_hf_local_arrow_path))
        records = local_df.to_dict(orient="records")
    else:
        from datasets import load_dataset

        dataset = load_dataset(settings.trend_hf_recruitment_dataset)["train"]
        records = list(dataset)

    if settings.trend_hf_sample_limit > 0:
        records = records[: settings.trend_hf_sample_limit]

    try:
        taxonomy = fetch_role_taxonomy_from_db()
    except Exception:
        taxonomy = load_role_taxonomy_local()
    rows = []
    for item in records:
        normalized = normalize_record(item)
        if not date_not_before(normalized["post_date"], settings.trend_jd_min_date):
            continue
        if not looks_it_related_loose(normalized["raw_job_title"], normalized["raw_jd_text"], taxonomy):
            continue
        rows.append(normalized)
    safe_write_dataframe(
        pd.DataFrame(rows),
        RAW_JD_LOCAL_PARQUET.with_name("raw_jd_jobs_hf_recruitment.parquet"),
        RAW_JD_LOCAL_JSON.with_name("raw_jd_jobs_hf_recruitment.json"),
    )
    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM raw_jd_jobs WHERE source = 'hf_recruitment_2022_2023'")
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
    print(json.dumps({"status": "ok", "rows": len(rows), "dataset_source": dataset_source, "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
