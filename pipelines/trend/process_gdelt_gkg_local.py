from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import (
    DATA_GOLD_DIR,
    connect_db,
    export_json_report,
    fetch_role_taxonomy_from_db,
    load_role_taxonomy_local,
    month_start,
    safe_write_dataframe,
)
from pipelines.trend.gdelt_bigquery import assign_role_buckets, classify_theme_scores, parse_gkg_tone, role_query_terms

LOCAL_GDELT_DIR = Path(settings.trend_gdelt_local_dir)
PROCESSED_DIR = Path(settings.trend_gdelt_local_processed_dir)
ROLE_DOCS_JSONL = DATA_GOLD_DIR / "gdelt_gkg_role_documents.jsonl"
ROLE_DOCS_SAMPLE_JSON = DATA_GOLD_DIR / "gdelt_gkg_role_documents_sample.json"
ROLE_DOCS_SAMPLE_PARQUET = DATA_GOLD_DIR / "gdelt_gkg_role_documents_sample.parquet"
BUCKET_EXPORT_JSON = DATA_GOLD_DIR / "gdelt_gkg_bucket_month_features.json"
BUCKET_EXPORT_PARQUET = DATA_GOLD_DIR / "gdelt_gkg_bucket_month_features.parquet"
FEATURE_EXPORT_JSON = DATA_GOLD_DIR / "gdelt_gkg_role_month_features.json"
FEATURE_EXPORT_PARQUET = DATA_GOLD_DIR / "gdelt_gkg_role_month_features.parquet"
IMPACT_EXPORT_JSON = DATA_GOLD_DIR / "gdelt_impact_role_month_features.json"
IMPACT_EXPORT_PARQUET = DATA_GOLD_DIR / "gdelt_impact_role_month_features.parquet"
REPORT_JSON = DATA_GOLD_DIR / "gdelt_gkg_local_processing_report.json"


def current_month_iso() -> str:
    today = date.today()
    return today.replace(day=1).isoformat()


def load_taxonomy() -> tuple[list[dict], str]:
    try:
        rows = fetch_role_taxonomy_from_db()
        if rows:
            return rows, "database"
    except Exception:
        pass
    rows = load_role_taxonomy_local()
    return rows, "local_json"


def iter_zip_files(root: Path) -> list[Path]:
    files = sorted(root.rglob("*.gkg.csv.zip"))
    max_files = max(int(settings.trend_gdelt_local_max_files), 0)
    return files[:max_files] if max_files else files


def batch_iter(items: list[Path], batch_size: int) -> Iterable[list[Path]]:
    size = max(int(batch_size), 1)
    for index in range(0, len(items), size):
        yield items[index : index + size]


def iter_rows_from_zip(zip_path: Path) -> Iterable[dict[str, str]]:
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"no csv found inside {zip_path}")
        with zf.open(names[0]) as src:
            text_stream = io.TextIOWrapper(src, encoding="utf-8", errors="replace", newline="")
            reader = csv.DictReader(text_stream, delimiter="\t")
            for row in reader:
                yield row


def matched_buckets_from_themes(themes_value: str) -> list[str]:
    text = str(themes_value or "").upper()
    matched: list[str] = []
    # ai_llm: GKG theme codes related to AI/ML/automation/tech innovation
    if any(kw in text for kw in [
        "TECH_AUTOMATION",
        "SOC_TECHNOLOGYSECTOR",
        "WB_660_BUSINESS_INTELLIGENCE",
        "WB_669_SOFTWARE_INFRASTRUCTURE",
        "WB_667_ICT_INFRASTRUCTURE",
        "WB_672_NETWORK_MANAGEMENT",
        "WB_676_CLOUD_COMPUTING",
        "WB_376_INNOVATION_TECHNOLOGY_AND_ENTREPRENEURSHIP",
        "WB_2350_ICT_INNOVATION_POLICY",
        "WB_2399_ICT_INNOVATION_AND_TRANSFORMATION",
    ]):
        matched.append("ai_llm")
    if "DATABASE" in text or "ANALYTICS" in text or "BIGQUERY" in text or "DATA_WAREHOUSE" in text or "ETL" in text:
        matched.append("data_platform")
    if "CLOUD" in text or "DEVOPS" in text or "KUBERNETES" in text or "DOCKER" in text or "INFRASTRUCTURE" in text:
        matched.append("cloud_devops")
    if "CYBERSECURITY" in text or "DATA_BREACH" in text or "RANSOMWARE" in text or "SECURITY" in text:
        matched.append("security")
    if "API" in text or "MICROSERVICES" in text or "SOFTWARE_ENGINEERING" in text or "APPLICATIONS" in text or "PLATFORM" in text:
        matched.append("backend_platform")
    return sorted(set(matched))


def first_source_url(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for part in text.split("<UDIV>"):
        url = part.strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
    return None


def source_domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower() or None
    except Exception:
        return None


def build_bucket_role_terms(taxonomy: list[dict[str, object]]) -> dict[str, list[tuple[str, list[str]]]]:
    bucket_terms: dict[str, list[tuple[str, list[str]]]] = {}
    for row in taxonomy:
        canonical_role = str(row["canonical_role"])
        terms = []
        for term in role_query_terms(row, top_skill_limit=5):
            text = str(term).strip().lower()
            if len(text) < 4:
                continue
            terms.append(text)
        for bucket_name in assign_role_buckets(row):
            bucket_terms.setdefault(bucket_name, []).append((canonical_role, sorted(set(terms), key=len, reverse=True)))
    return bucket_terms


def raw_export_limit() -> int:
    return max(int(settings.trend_gdelt_raw_export_limit), 0)


def update_aggregate(
    aggregates: dict[tuple[str, str], dict[str, object]],
    key: tuple[str, str],
    weight: float,
    tone: float,
    risk_score: float,
    opportunity_score: float,
    source_domain: str | None,
) -> None:
    agg = aggregates.setdefault(
        key,
        {
            "article_count": 0.0,
            "source_domains": set(),
            "tone_sum": 0.0,
            "positive_count": 0.0,
            "negative_count": 0.0,
            "risk_sum": 0.0,
            "opportunity_sum": 0.0,
        },
    )
    agg["article_count"] += weight
    if source_domain:
        agg["source_domains"].add(source_domain)
    agg["tone_sum"] += tone * weight
    agg["positive_count"] += (1.0 if tone > 0 else 0.0) * weight
    agg["negative_count"] += (1.0 if tone < 0 else 0.0) * weight
    agg["risk_sum"] += risk_score * weight
    agg["opportunity_sum"] += opportunity_score * weight


def build_feature_rows(
    aggregates: dict[tuple[str, str], dict[str, object]],
    first_key_name: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    excluded_month = current_month_iso()
    for (name, month), agg in aggregates.items():
        if month == excluded_month:
            continue
        article_count = max(float(agg["article_count"]), 1.0)
        avg_tone = float(agg["tone_sum"]) / article_count
        positive_score = float(agg["positive_count"]) / article_count
        negative_score = float(agg["negative_count"]) / article_count
        net_positive_score = positive_score - negative_score
        sentiment_index = max(min((avg_tone / 10.0) + net_positive_score, 1.0), -1.0)
        risk_index = float(agg["risk_sum"]) / article_count
        opportunity_index = float(agg["opportunity_sum"]) / article_count
        rows.append(
            {
                first_key_name: name,
                "month": month,
                "article_count": article_count,
                "source_count": len(agg["source_domains"]),
                "avg_tone": round(avg_tone, 6),
                "positive_score": round(positive_score, 6),
                "negative_score": round(negative_score, 6),
                "net_positive_score": round(net_positive_score, 6),
                "sentiment_index": round(sentiment_index, 6),
                "risk_index": round(risk_index, 6),
                "opportunity_index": round(opportunity_index, 6),
            }
        )
    return pd.DataFrame(rows).sort_values([first_key_name, "month"]) if rows else pd.DataFrame(
        columns=[first_key_name, "month", "article_count", "source_count", "avg_tone", "positive_score", "negative_score", "net_positive_score", "sentiment_index", "risk_index", "opportunity_index"]
    )


def build_impact_features(doc_df: pd.DataFrame, gkg_df: pd.DataFrame) -> pd.DataFrame:
    if gkg_df.empty:
        return pd.DataFrame(columns=["canonical_role", "month", "impact_direction", "impact_score"])
    doc_grouped = pd.DataFrame(columns=["canonical_role", "month", "doc_article_count", "doc_sentiment_mean", "doc_opportunity_index", "doc_risk_index"])
    if not doc_df.empty:
        temp = doc_df.copy()
        temp["month"] = temp["publish_date"].apply(month_start)
        temp = temp[temp["month"].notna()].copy()
        temp["tone_num"] = temp["tone"].apply(parse_gkg_tone)
        scores = temp["themes"].apply(classify_theme_scores)
        temp["risk_component"] = [item[0] for item in scores]
        temp["opportunity_component"] = [item[1] for item in scores]
        doc_grouped = (
            temp.groupby(["canonical_role", "month"], as_index=False)
            .agg(
                doc_article_count=("themes", "size"),
                doc_sentiment_mean=("tone_num", "mean"),
                doc_opportunity_index=("opportunity_component", "mean"),
                doc_risk_index=("risk_component", "mean"),
            )
        )
        doc_grouped["month"] = doc_grouped["month"].astype(str)

    merged = gkg_df.merge(doc_grouped, on=["canonical_role", "month"], how="left").fillna(0.0)
    merged["impact_score"] = (
        0.5 * merged["sentiment_index"]
        + 0.3 * ((merged["opportunity_index"] + merged["doc_opportunity_index"]) / 2.0)
        - 0.2 * ((merged["risk_index"] + merged["doc_risk_index"]) / 2.0)
    ).round(6)
    merged["impact_direction"] = merged["impact_score"].apply(lambda value: "positive" if value > 0.08 else "negative" if value < -0.08 else "neutral")
    return merged[[
        "canonical_role", "month", "article_count", "source_count", "avg_tone", "positive_score", "negative_score", "net_positive_score",
        "sentiment_index", "risk_index", "opportunity_index", "doc_article_count", "doc_sentiment_mean", "doc_opportunity_index", "doc_risk_index",
        "impact_direction", "impact_score",
    ]].sort_values(["canonical_role", "month"])


def main() -> None:
    taxonomy, taxonomy_source = load_taxonomy()
    bucket_role_terms = build_bucket_role_terms(taxonomy)
    zip_files = iter_zip_files(LOCAL_GDELT_DIR)
    if not zip_files:
        raise RuntimeError(f"no GDELT zip files found under {LOCAL_GDELT_DIR}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    sample_documents: list[dict[str, object]] = []
    bucket_aggregates: dict[tuple[str, str], dict[str, object]] = {}
    role_aggregates: dict[tuple[str, str], dict[str, object]] = {}
    batch_reports: list[dict[str, object]] = []
    total_bucket_records = 0
    total_role_matches = 0
    sample_limit = raw_export_limit()

    with ROLE_DOCS_JSONL.open("w", encoding="utf-8") as role_sink:
        for batch_index, batch in enumerate(batch_iter(zip_files, settings.trend_gdelt_local_batch_size), start=1):
            batch_report = {"batch_index": batch_index, "file_count": len(batch), "files": []}
            for zip_path in batch:
                processed_jsonl = PROCESSED_DIR / f"{zip_path.stem}.filtered.jsonl"
                matched_rows = 0
                with processed_jsonl.open("w", encoding="utf-8") as sink:
                    for row in iter_rows_from_zip(zip_path):
                        publish_month = month_start(row.get("DATE") or "")
                        if publish_month is None:
                            continue
                        month = publish_month.isoformat()
                        themes = row.get("THEMES") or ""
                        buckets = matched_buckets_from_themes(themes)
                        if not buckets:
                            continue
                        tone = parse_gkg_tone(row.get("TONE") or "")
                        risk_score, opportunity_score = classify_theme_scores(themes)
                        url = first_source_url(row.get("SOURCEURLS") or "")
                        source_domain = source_domain_from_url(url)
                        base_record = {
                            "DATE": row.get("DATE") or "",
                            "month": month,
                            "url": url,
                            "source_domain": source_domain,
                            "themes": themes,
                            "tone": row.get("TONE") or "",
                        }
                        for bucket_name in buckets:
                            update_aggregate(bucket_aggregates, (bucket_name, month), 1.0, tone, risk_score, opportunity_score, source_domain)
                            matched_rows += 1
                            total_bucket_records += 1
                            compact_record = {**base_record, "bucket_name": bucket_name}
                            sink.write(json.dumps(compact_record, ensure_ascii=False) + "\n")
                            document_text = " ".join([themes, str(url or ""), str(source_domain or "")]).lower()
                            role_hits: list[tuple[str, int, list[str]]] = []
                            for canonical_role, terms in bucket_role_terms.get(bucket_name, []):
                                matched_terms = [term for term in terms if term in document_text]
                                hit_count = len(matched_terms)
                                if hit_count > 0:
                                    role_hits.append((canonical_role, hit_count, matched_terms[:10]))
                            if role_hits:
                                total_hits = sum(hit for _, hit, _ in role_hits)
                                for canonical_role, hit_count, matched_terms in role_hits:
                                    weight = hit_count / total_hits
                                    role_record = {
                                        **compact_record,
                                        "canonical_role": canonical_role,
                                        "match_weight": round(weight, 6),
                                        "matched_term_count": hit_count,
                                        "matched_terms": matched_terms,
                                    }
                                    role_sink.write(json.dumps(role_record, ensure_ascii=False) + "\n")
                                    if sample_limit > 0 and len(sample_documents) < sample_limit:
                                        sample_documents.append(role_record)
                                    update_aggregate(role_aggregates, (canonical_role, month), weight, tone, risk_score, opportunity_score, source_domain)
                                    total_role_matches += 1
                batch_report["files"].append({
                    "zip_file": str(zip_path),
                    "processed_jsonl": str(processed_jsonl),
                    "matched_bucket_rows": matched_rows,
                })
            batch_reports.append(batch_report)

    if sample_limit > 0 and sample_documents:
        raw_df = pd.DataFrame(sample_documents)
        safe_write_dataframe(raw_df, ROLE_DOCS_SAMPLE_PARQUET, ROLE_DOCS_SAMPLE_JSON)

    bucket_df = build_feature_rows(bucket_aggregates, "bucket_name")
    safe_write_dataframe(bucket_df, BUCKET_EXPORT_PARQUET, BUCKET_EXPORT_JSON)

    role_features = build_feature_rows(role_aggregates, "canonical_role")
    safe_write_dataframe(role_features, FEATURE_EXPORT_PARQUET, FEATURE_EXPORT_JSON)

    doc_df = pd.DataFrame(columns=["canonical_role", "publish_date", "tone", "themes"])
    try:
        with connect_db() as conn:
            doc_df = pd.read_sql_query(
                "SELECT canonical_role, publish_date, tone, snippet AS themes FROM raw_gdelt_articles",
                conn,
            )
    except Exception:
        pass

    impact_df = build_impact_features(doc_df, role_features)
    safe_write_dataframe(impact_df, IMPACT_EXPORT_PARQUET, IMPACT_EXPORT_JSON)

    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE gdelt_gkg_role_month_features")
            cur.execute("TRUNCATE TABLE gdelt_event_role_month_features")
            if not role_features.empty:
                cur.executemany(
                    """
                    INSERT INTO gdelt_gkg_role_month_features (
                      canonical_role, month, article_count, source_count, avg_tone,
                      positive_score, negative_score, net_positive_score, sentiment_index,
                      risk_index, opportunity_index, updated_at
                    ) VALUES (
                      %(canonical_role)s, %(month)s, %(article_count)s, %(source_count)s, %(avg_tone)s,
                      %(positive_score)s, %(negative_score)s, %(net_positive_score)s, %(sentiment_index)s,
                      %(risk_index)s, %(opportunity_index)s, NOW()
                    )
                    ON CONFLICT (canonical_role, month) DO UPDATE SET
                      article_count = EXCLUDED.article_count,
                      source_count = EXCLUDED.source_count,
                      avg_tone = EXCLUDED.avg_tone,
                      positive_score = EXCLUDED.positive_score,
                      negative_score = EXCLUDED.negative_score,
                      net_positive_score = EXCLUDED.net_positive_score,
                      sentiment_index = EXCLUDED.sentiment_index,
                      risk_index = EXCLUDED.risk_index,
                      opportunity_index = EXCLUDED.opportunity_index,
                      updated_at = NOW()
                    """,
                    role_features.to_dict(orient="records"),
                )
            if not impact_df.empty:
                cur.executemany(
                    """
                    INSERT INTO gdelt_event_role_month_features (
                      canonical_role, month, event_impact_score, updated_at
                    ) VALUES (
                      %(canonical_role)s, %(month)s, %(impact_score)s, NOW()
                    )
                    ON CONFLICT (canonical_role, month) DO UPDATE SET
                      event_impact_score = EXCLUDED.event_impact_score,
                      updated_at = NOW()
                    """,
                    impact_df.to_dict(orient="records"),
                )
            conn.commit()
        db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)

    export_json_report(
        {
            "status": "ok",
            "taxonomy_source": taxonomy_source,
            "zip_file_count": len(zip_files),
            "batch_size": settings.trend_gdelt_local_batch_size,
            "role_documents_jsonl": str(ROLE_DOCS_JSONL),
            "raw_export_limit": sample_limit,
            "sample_export_rows": len(sample_documents),
            "total_bucket_records": total_bucket_records,
            "total_role_matches": total_role_matches,
            "bucket_feature_rows": int(len(bucket_df)),
            "gkg_feature_rows": int(len(role_features)),
            "impact_rows": int(len(impact_df)),
            "db_write": db_write,
            "batches": batch_reports,
        },
        REPORT_JSON,
    )
    print(json.dumps({
        "status": "ok",
        "taxonomy_source": taxonomy_source,
        "zip_file_count": len(zip_files),
        "role_documents_jsonl": str(ROLE_DOCS_JSONL),
        "raw_export_limit": sample_limit,
        "sample_export_rows": len(sample_documents),
        "total_bucket_records": total_bucket_records,
        "total_role_matches": total_role_matches,
        "bucket_feature_rows": int(len(bucket_df)),
        "gkg_feature_rows": int(len(role_features)),
        "impact_rows": int(len(impact_df)),
        "db_write": db_write,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
