from __future__ import annotations

import json
import os
import re
import ssl
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import settings
from pipelines.trend.common import month_start


class BigQuerySetupError(RuntimeError):
    pass


@dataclass
class BigQueryEnvStatus:
    project_id: str
    credentials_path: Path
    removed_proxy_vars: list[str]
    removed_tls_vars: list[str]


def sanitize_bigquery_runtime_env() -> BigQueryEnvStatus:
    removed_proxy_vars: list[str] = []
    removed_tls_vars: list[str] = []
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        value = os.environ.get(name)
        if value:
            os.environ.pop(name, None)
            removed_proxy_vars.append(name)
    for name in ("SSLKEYLOGFILE",):
        value = os.environ.get(name)
        if value:
            os.environ.pop(name, None)
            removed_tls_vars.append(name)

    credentials_path = Path(settings.trend_gdelt_bigquery_credentials_path)
    if not credentials_path.is_absolute():
        credentials_path = Path.cwd() / credentials_path
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.trend_gdelt_bigquery_project
    return BigQueryEnvStatus(
        project_id=settings.trend_gdelt_bigquery_project,
        credentials_path=credentials_path,
        removed_proxy_vars=removed_proxy_vars,
        removed_tls_vars=removed_tls_vars,
    )


def validate_bigquery_env(status: BigQueryEnvStatus) -> None:
    if not status.project_id:
        raise BigQuerySetupError("missing GOOGLE_CLOUD_PROJECT")
    if not status.credentials_path.exists():
        raise BigQuerySetupError(f"credentials file not found: {status.credentials_path}")


def import_bigquery_client():
    try:
        from google.cloud import bigquery
        return bigquery
    except Exception as exc:  # pragma: no cover - dependency dependent
        raise BigQuerySetupError(f"google-cloud-bigquery import failed: {exc}") from exc


def create_bigquery_client():
    status = sanitize_bigquery_runtime_env()
    validate_bigquery_env(status)
    bigquery = import_bigquery_client()
    try:
        client = bigquery.Client(project=status.project_id)
        return client, status
    except Exception as exc:  # pragma: no cover - network/auth dependent
        if isinstance(exc, ssl.SSLError):
            raise BigQuerySetupError(f"bigquery ssl failure: {exc}") from exc
        raise BigQuerySetupError(f"bigquery client creation failed: {exc}") from exc


def role_query_terms(role: dict[str, Any], top_skill_limit: int | None = None) -> list[str]:
    terms = [role["canonical_role"], *(role.get("aliases") or [])]
    skill_limit = int(top_skill_limit or settings.trend_gdelt_bigquery_top_skills)
    terms.extend((role.get("top_skills") or [])[:skill_limit])
    cleaned = []
    seen = set()
    for term in terms:
        text = str(term).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
    return cleaned


GKG_THEME_BUCKETS: dict[str, list[str]] = {
    "ai_llm": [
        "TECH_AUTOMATION",
        "SOC_TECHNOLOGYSECTOR",
        "BUSINESS_INTELLIGENCE",
        "SOFTWARE_INFRASTRUCTURE",
        "ICT_INFRASTRUCTURE",
        "NETWORK_MANAGEMENT",
        "CLOUD_COMPUTING",
        "INNOVATION_TECHNOLOGY",
        "ICT_INNOVATION",
    ],
    "data_platform": [
        "DATA",
        "DATABASE",
        "DATA_ENGINEERING",
        "DATA_WAREHOUSE",
        "BIGQUERY",
        "ETL",
        "ANALYTICS",
    ],
    "cloud_devops": [
        "CLOUD",
        "DEVOPS",
        "KUBERNETES",
        "DOCKER",
        "INFRASTRUCTURE",
        "SRE",
        "CI_CD",
    ],
    "security": [
        "CYBERSECURITY",
        "SECURITY",
        "DATA_BREACH",
        "RANSOMWARE",
        "ZERO_TRUST",
        "IDENTITY",
    ],
    "backend_platform": [
        "API",
        "MICROSERVICES",
        "BACKEND",
        "SOFTWARE_ENGINEERING",
        "APPLICATIONS",
        "PLATFORM",
    ],
}

ROLE_BUCKET_HINTS: dict[str, set[str]] = {
    "ai_llm": {"ai", "llm", "machine learning", "deep learning", "nlp", "rag", "langchain", "prompt", "agent"},
    "data_platform": {"data", "analytics", "sql", "warehouse", "etl", "spark", "bigquery", "airflow", "database"},
    "cloud_devops": {"cloud", "devops", "docker", "kubernetes", "terraform", "platform", "sre", "infra", "aws", "azure", "gcp"},
    "security": {"security", "cyber", "soc", "iam", "siem", "vulnerability", "zero trust"},
    "backend_platform": {"backend", "api", "microservices", "java", "spring", "node", "python", "go", ".net"},
}


def bucket_regex(bucket_name: str) -> str:
    terms = GKG_THEME_BUCKETS[bucket_name]
    return "|".join(_regex_escape(term.lower()) for term in terms)


def assign_role_buckets(role: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(role.get("canonical_role", "")),
            *[str(item) for item in role.get("aliases", [])],
            *[str(item) for item in role.get("top_skills", [])],
        ]
    ).lower()
    matched = [bucket for bucket, hints in ROLE_BUCKET_HINTS.items() if any(hint in text for hint in hints)]
    return matched or ["backend_platform"]


def build_bucket_gkg_sql(bucket_name: str, months: int | None = None, max_docs: int | None = None) -> tuple[str, list[Any]]:
    regex_terms = bucket_regex(bucket_name)
    months_back = int(months or settings.trend_gdelt_bigquery_months)
    doc_limit = int(max_docs or settings.trend_gdelt_bigquery_max_docs_per_role)
    sql = f"""
    SELECT
      DATE,
      DocumentIdentifier,
      SourceCommonName,
      V2Themes,
      V2Tone
    FROM `gdelt-bq.gdeltv2.gkg_partitioned`
    WHERE DATE(_PARTITIONTIME) >= DATE_SUB(CURRENT_DATE(), INTERVAL @months_back MONTH)
      AND DATE(_PARTITIONTIME) < CURRENT_DATE()
      AND REGEXP_CONTAINS(LOWER(IFNULL(V2Themes, '')), @regex_terms)
    ORDER BY DATE DESC
    LIMIT @doc_limit
    """
    return sql, [months_back, regex_terms, doc_limit]


def _regex_escape(text: str) -> str:
    import re

    return re.escape(text)


def parse_gkg_tone(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    text = str(value)
    token = text.split(",")[0].strip()
    try:
        return float(token)
    except Exception:
        return 0.0


RISK_THEME_HINTS = {
    "CYBER_ATTACK",
    "CYBERSECURITY",
    "DATA_BREACH",
    "REGULATION",
    "LAYOFF",
    "BANKRUPTCY",
    "SUPPLY_CHAIN",
    "OUTAGE",
    "SANCTIONS",
}

OPPORTUNITY_THEME_HINTS = {
    "INVESTMENT",
    "FUNDING",
    "EXPANSION",
    "AI",
    "CLOUD",
    "AUTOMATION",
    "PRODUCT_LAUNCH",
    "PARTNERSHIP",
    "HIRING",
}


def classify_theme_scores(themes_value: Any) -> tuple[float, float]:
    if not themes_value:
        return 0.0, 0.0
    themes = [part.split("#", 1)[0].strip().upper() for part in str(themes_value).split(";") if part.strip()]
    if not themes:
        return 0.0, 0.0
    risk_hits = sum(1 for theme in themes if any(hint in theme for hint in RISK_THEME_HINTS))
    opp_hits = sum(1 for theme in themes if any(hint in theme for hint in OPPORTUNITY_THEME_HINTS))
    total = max(len(themes), 1)
    return round(risk_hits / total, 6), round(opp_hits / total, 6)


def map_document_to_roles(document: dict[str, Any], taxonomy: list[dict[str, Any]]) -> list[str]:
    bucket_name = str(document.get("bucket_name") or "")
    document_text = " ".join(
        [
            str(document.get("themes") or document.get("V2Themes") or ""),
            str(document.get("url") or document.get("DocumentIdentifier") or ""),
            str(document.get("source_domain") or document.get("SourceCommonName") or ""),
        ]
    ).lower()
    matched_roles: list[str] = []
    for role in taxonomy:
        role_buckets = assign_role_buckets(role)
        if bucket_name and bucket_name not in role_buckets:
            continue
        terms = role_query_terms(role, top_skill_limit=5)
        strong_terms = [term for term in terms if len(term.strip()) >= 4]
        score = 0
        for term in strong_terms:
            lowered = term.lower()
            if re.search(r"(?<![a-z0-9])" + re.escape(lowered) + r"(?![a-z0-9])", document_text):
                score += 1
        if score >= 1:
            matched_roles.append(role["canonical_role"])
    if matched_roles:
        return matched_roles
    # fallback: map bucket document to all roles in same bucket, but cap to close roles only
    fallback = [role["canonical_role"] for role in taxonomy if bucket_name in assign_role_buckets(role)]
    return fallback[:5]


def aggregate_gkg_month_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    grouped: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        month = month_start(row.get("publish_date") or row.get("DATE"))
        if month is None:
            continue
        key = (row["canonical_role"], month)
        bucket = grouped.setdefault(
            key,
            {
                "canonical_role": row["canonical_role"],
                "month": month.isoformat(),
                "article_count": 0,
                "source_domains": set(),
                "tone_sum": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "risk_sum": 0.0,
                "opportunity_sum": 0.0,
            },
        )
        tone = parse_gkg_tone(row.get("tone") or row.get("V2Tone"))
        risk_score, opportunity_score = classify_theme_scores(row.get("themes") or row.get("V2Themes"))
        bucket["article_count"] += 1
        if row.get("source_domain") or row.get("SourceCommonName"):
            bucket["source_domains"].add(str(row.get("source_domain") or row.get("SourceCommonName")).strip().lower())
        bucket["tone_sum"] += tone
        bucket["positive_count"] += 1 if tone > 0 else 0
        bucket["negative_count"] += 1 if tone < 0 else 0
        bucket["risk_sum"] += risk_score
        bucket["opportunity_sum"] += opportunity_score

    out: list[dict[str, Any]] = []
    for bucket in grouped.values():
        article_count = max(int(bucket["article_count"]), 1)
        avg_tone = bucket["tone_sum"] / article_count
        positive_score = bucket["positive_count"] / article_count
        negative_score = bucket["negative_count"] / article_count
        net_positive_score = positive_score - negative_score
        sentiment_index = max(min((avg_tone / 10.0) + net_positive_score, 1.0), -1.0)
        risk_index = bucket["risk_sum"] / article_count
        opportunity_index = bucket["opportunity_sum"] / article_count
        out.append(
            {
                "canonical_role": bucket["canonical_role"],
                "month": bucket["month"],
                "article_count": article_count,
                "source_count": len(bucket["source_domains"]),
                "avg_tone": round(avg_tone, 6),
                "positive_score": round(positive_score, 6),
                "negative_score": round(negative_score, 6),
                "net_positive_score": round(net_positive_score, 6),
                "sentiment_index": round(sentiment_index, 6),
                "risk_index": round(risk_index, 6),
                "opportunity_index": round(opportunity_index, 6),
            }
        )
    out.sort(key=lambda row: (row["canonical_role"], row["month"]))
    return out


def dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
