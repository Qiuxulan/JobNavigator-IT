from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.services.career_catalog import load_roles, role_top_skills

ROOT = Path(__file__).parents[2]
RAW_DATA_DIR = ROOT / "data" / "raw"
DATA_GOLD_DIR = ROOT / "data" / "gold"
REPORTS_DIR = ROOT / "reports"
KAGGLE_DATA_DIR = ROOT / settings.trend_kaggle_data_dir
HF_LOCAL_ARROW_PATH = ROOT / settings.trend_hf_local_arrow_path
HF_LOCAL_CSV_PATH = ROOT / settings.trend_hf_local_csv_path
HF_LOCAL_INFO_PATH = ROOT / settings.trend_hf_local_info_path
LINKEDIN_POSTINGS_PATH = ROOT / settings.trend_linkedin_postings_path
LINKEDIN_SKILLS_PATH = ROOT / settings.trend_linkedin_skills_path
AI_JOB_DATASET_PATH = ROOT / settings.trend_ai_job_dataset_path

ROLE_TAXONOMY_JSON = DATA_GOLD_DIR / "role_taxonomy.json"
ROLE_TAXONOMY_PARQUET = DATA_GOLD_DIR / "role_taxonomy.parquet"
ROLE_MONTH_FEATURES_PARQUET = DATA_GOLD_DIR / "role_month_features.parquet"
ROLE_MONTH_FEATURES_JSON = DATA_GOLD_DIR / "role_month_features.json"
PATCHTST_DATASET_PARQUET = DATA_GOLD_DIR / "patchtst_role_month_features.parquet"
PATCHTST_DATASET_JSON = DATA_GOLD_DIR / "patchtst_role_month_features.json"
RAW_JD_LOCAL_JSON = DATA_GOLD_DIR / "raw_jd_jobs.json"
RAW_JD_LOCAL_PARQUET = DATA_GOLD_DIR / "raw_jd_jobs.parquet"
PROCESSED_JD_LOCAL_JSON = DATA_GOLD_DIR / "processed_jd_jobs.json"
PROCESSED_JD_LOCAL_PARQUET = DATA_GOLD_DIR / "processed_jd_jobs.parquet"

POSITIVE_HINTS = {
    "launch",
    "funding",
    "growth",
    "adoption",
    "hiring",
    "expansion",
    "release",
    "partnership",
    "investment",
    "breakthrough",
}
NEGATIVE_HINTS = {
    "layoff",
    "lawsuit",
    "risk",
    "breach",
    "decline",
    "slowdown",
    "cut",
    "ban",
    "regulation",
    "outage",
}

TITLE_COLUMN_CANDIDATES = ["title", "job_title", "job_title_short", "position"]
DESC_COLUMN_CANDIDATES = ["description", "job_description", "description_text", "job_summary", "job_details"]
DATE_COLUMN_CANDIDATES = ["posted_date", "post_date", "listed_time", "original_listed_time", "job_posted_date", "date"]
SALARY_COLUMN_CANDIDATES = ["salary", "salary_yearly", "salary_mid", "pay", "max_salary", "min_salary"]
COMPANY_COLUMN_CANDIDATES = ["company", "company_name", "employer_name"]
URL_COLUMN_CANDIDATES = ["job_url", "url", "apply_url", "job_link"]
WORK_ARRANGEMENT_CANDIDATES = ["work_arrangement", "remote", "location_type", "job_is_remote"]
ROLE_STOPWORDS = {
    "engineer", "developer", "architect", "specialist", "administrator", "admin", "consultant",
    "manager", "lead", "senior", "junior", "middle", "staff", "principal", "sr", "jr",
}
AMBIGUOUS_SKILL_TOKENS = {"r", "c", "go", "ai", "ml", "qa"}
GENERIC_IT_ROLES = {"Project Manager", "Product Manager", "Delivery Manager", "Business Analyst"}
GENERIC_IT_SUPPORT_KEYWORDS = {
    "software", "platform", "application", "applications", "cloud", "data", "analytics", "engineer",
    "developer", "devops", "security", "ai", "ml", "machine learning", "llm", "rag", "infrastructure",
    "system", "systems", "it ", " it", "technical", "technology", "digital", "api", "backend", "frontend",
}
AI_ROLE_HINTS = {
    "ai",
    "ml",
    "machine learning",
    "llm",
    "rag",
    "prompt",
    "nlp",
    "computer vision",
    "deep learning",
    "generative",
    "inference",
    "mlops",
}


def connect_db():
    import psycopg

    return psycopg.connect(settings.postgres_dsn)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def safe_write_dataframe(df: pd.DataFrame, parquet_path: Path, json_path: Path) -> None:
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", force_ascii=False, indent=2, date_format="iso")
    ensure_parent(parquet_path)
    try:
        df.to_parquet(parquet_path, index=False)
    except Exception:
        pass


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")


def hash_id(*parts: Any) -> str:
    payload = "||".join("" if part is None else str(part) for part in parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def month_start(value: Any) -> date | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").date().replace(day=1)
        except Exception:
            pass
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").date().replace(day=1)
        except Exception:
            pass
    try:
        if not isinstance(value, (date, datetime, str)):
            numeric = float(value)
            if numeric > 10**12:
                return datetime.utcfromtimestamp(numeric / 1000.0).date().replace(day=1)
            if numeric > 10**9:
                return datetime.utcfromtimestamp(numeric).date().replace(day=1)
    except Exception:
        pass
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.replace(day=1)
    if isinstance(value, datetime):
        return value.date().replace(day=1)
    text = str(value).strip()
    for parser in (
        lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")),
        lambda x: datetime.strptime(x[:10], "%Y-%m-%d"),
    ):
        try:
            return parser(text).date().replace(day=1)
        except Exception:
            continue
    return None


def normalize_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").isoformat()
        except Exception:
            pass
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").isoformat()
        except Exception:
            pass
    try:
        if not isinstance(value, (date, datetime, str)):
            numeric = float(value)
            if numeric > 10**12:
                return datetime.utcfromtimestamp(numeric / 1000.0).isoformat()
            if numeric > 10**9:
                return datetime.utcfromtimestamp(numeric).isoformat()
    except Exception:
        pass
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except Exception:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").isoformat()
    except Exception:
        return None


def date_not_before(value: Any, min_date: str | date | datetime | None) -> bool:
    if min_date in (None, ""):
        return True
    current = month_start(value)
    threshold = month_start(min_date)
    if current is None or threshold is None:
        return False
    return current >= threshold


def normalize_years(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None
    text = str(value).strip().lower()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def normalize_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [part.strip() for part in value.split(";") if part.strip()]
    return [str(value).strip()]


def normalize_work_arrangement(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if "onsite" in text or "on-site" in text or "office" in text:
        return "onsite"
    return text


def load_role_taxonomy_rows() -> list[dict[str, Any]]:
    roles = load_roles()
    rows: list[dict[str, Any]] = []
    for role_id, role in sorted(roles.items()):
        aliases = sorted(
            {
                str(alias).strip()
                for alias in (
                    role.get("aliases")
                    or role.get("role_aliases")
                    or role.get("search_aliases")
                    or []
                )
                if str(alias).strip()
            }
        )
        aliases = sorted({*aliases, *generated_role_aliases(role.get("role_name", role_id))})
        top_skills = [row["skill_name"] for row in role_top_skills(role, top_n=10)]
        rows.append(
            {
                "role_id": role_id,
                "category": role.get("coarse_role", "unknown"),
                "canonical_role": role.get("role_name", role_id),
                "aliases": aliases,
                "top_skills": top_skills,
                "existing_jd_count": int(role.get("job_count") or role.get("sample_count") or 0),
            }
        )
    return rows


def read_any_table(path: Path) -> pd.DataFrame | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path, low_memory=False)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(path)
    except Exception:
        return None
    return None


def load_hf_recruitment_local_dataframe() -> pd.DataFrame | None:
    if not HF_LOCAL_ARROW_PATH.exists():
        if HF_LOCAL_CSV_PATH.exists():
            return pd.read_csv(HF_LOCAL_CSV_PATH, low_memory=False)
        return None
    try:
        from datasets import Dataset

        dataset = Dataset.from_file(str(HF_LOCAL_ARROW_PATH))
        return dataset.to_pandas()
    except Exception:
        if HF_LOCAL_CSV_PATH.exists():
            return pd.read_csv(HF_LOCAL_CSV_PATH, low_memory=False)
        csv_fallback = HF_LOCAL_ARROW_PATH.with_suffix(".csv")
        parquet_fallback = HF_LOCAL_ARROW_PATH.with_suffix(".parquet")
        if csv_fallback.exists():
            return pd.read_csv(csv_fallback, low_memory=False)
        if parquet_fallback.exists():
            return pd.read_parquet(parquet_fallback)
        raise


def pick_first_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    lower_map = {str(col).lower(): str(col) for col in columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def find_candidate_jd_tables(data_dir: Path | None = None) -> list[tuple[Path, pd.DataFrame, dict[str, str | None]]]:
    root = data_dir or KAGGLE_DATA_DIR
    if not root.exists() and root != RAW_DATA_DIR:
        root = RAW_DATA_DIR
    if not root.exists():
        return []
    matches: list[tuple[Path, pd.DataFrame, dict[str, str | None]]] = []
    for file in root.glob("*"):
        df = read_any_table(file)
        if df is None or df.empty:
            continue
        column_map = {
            "title": pick_first_column(df.columns, TITLE_COLUMN_CANDIDATES),
            "desc": pick_first_column(df.columns, DESC_COLUMN_CANDIDATES),
            "date": pick_first_column(df.columns, DATE_COLUMN_CANDIDATES),
            "salary": pick_first_column(df.columns, SALARY_COLUMN_CANDIDATES),
            "company": pick_first_column(df.columns, COMPANY_COLUMN_CANDIDATES),
            "url": pick_first_column(df.columns, URL_COLUMN_CANDIDATES),
            "work_arrangement": pick_first_column(df.columns, WORK_ARRANGEMENT_CANDIDATES),
        }
        has_title = bool(column_map["title"])
        has_desc = bool(column_map["desc"])
        has_date = bool(column_map["date"])
        has_company = bool(column_map["company"])
        has_salary = bool(column_map["salary"])
        if has_title and (has_desc or has_date) and (has_date or has_company or has_salary):
            matches.append((file, df, column_map))
    return matches


def looks_it_related_loose(title: str, text: str, taxonomy_rows: list[dict[str, Any]]) -> bool:
    joined = f"{title}\n{text}".lower()
    soft_keywords = {
        "engineer", "developer", "software", "backend", "frontend", "full stack", "data", "machine learning",
        "ai", "devops", "cloud", "python", "java", "javascript", "react", "node", "sql", "llm", "rag",
        "security", "sre", "platform", "qa", "product", "analytics", "kubernetes", "docker",
    }
    taxonomy_hits = 0
    for role in taxonomy_rows:
        if role["canonical_role"].lower() in joined:
            taxonomy_hits += 1
            break
        if any(alias.lower() in joined for alias in role.get("aliases", [])[:5]):
            taxonomy_hits += 1
            break
        if any(skill.lower() in joined for skill in role.get("top_skills", [])[:6]):
            taxonomy_hits += 1
            break
    soft_hits = sum(1 for keyword in soft_keywords if keyword in joined)
    return taxonomy_hits > 0 or soft_hits >= 2


def export_role_taxonomy(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    safe_write_dataframe(df, ROLE_TAXONOMY_PARQUET, ROLE_TAXONOMY_JSON)
    return df


def upsert_role_taxonomy(rows: list[dict[str, Any]]) -> None:
    with connect_db() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO role_taxonomy (role_id, category, canonical_role, aliases, top_skills, existing_jd_count, updated_at)
            VALUES (%(role_id)s, %(category)s, %(canonical_role)s, %(aliases)s::jsonb, %(top_skills)s::jsonb, %(existing_jd_count)s, NOW())
            ON CONFLICT (role_id) DO UPDATE SET
              category = EXCLUDED.category,
              canonical_role = EXCLUDED.canonical_role,
              aliases = EXCLUDED.aliases,
              top_skills = EXCLUDED.top_skills,
              existing_jd_count = EXCLUDED.existing_jd_count,
              updated_at = NOW()
            """,
            [
                {
                    **row,
                    "aliases": json.dumps(row["aliases"], ensure_ascii=False),
                    "top_skills": json.dumps(row["top_skills"], ensure_ascii=False),
                }
                for row in rows
            ],
        )
        conn.commit()


def fetch_role_taxonomy_from_db() -> list[dict[str, Any]]:
    with connect_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT role_id, category, canonical_role, aliases, top_skills, existing_jd_count
            FROM role_taxonomy
            ORDER BY canonical_role
            """
        )
        rows = []
        for role_id, category, canonical_role, aliases, top_skills, existing_jd_count in cur.fetchall():
            rows.append(
                {
                    "role_id": role_id,
                    "category": category,
                    "canonical_role": canonical_role,
                    "aliases": listify(aliases),
                    "top_skills": listify(top_skills),
                    "existing_jd_count": existing_jd_count,
                }
            )
    return rows


def load_role_taxonomy_local() -> list[dict[str, Any]]:
    if not ROLE_TAXONOMY_JSON.exists():
        return []
    try:
        data = json.loads(ROLE_TAXONOMY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for row in data:
        rows.append(
            {
                "role_id": row.get("role_id"),
                "category": row.get("category"),
                "canonical_role": row.get("canonical_role"),
                "aliases": listify(row.get("aliases")),
                "top_skills": listify(row.get("top_skills")),
                "existing_jd_count": int(row.get("existing_jd_count") or 0),
            }
        )
    return rows


def is_ai_focused_role(row: dict[str, Any]) -> bool:
    role_text = " | ".join(
        [
            str(row.get("canonical_role") or ""),
            " | ".join(str(alias) for alias in row.get("aliases", []) if str(alias).strip()),
        ]
    ).lower()
    if any(hint in role_text for hint in AI_ROLE_HINTS):
        return True
    skill_hits = 0
    for skill in row.get("top_skills", []):
        skill_text = str(skill).strip().lower()
        if skill_text and any(hint in skill_text for hint in AI_ROLE_HINTS):
            skill_hits += 1
    return skill_hits >= 2


def ai_focused_taxonomy_rows(taxonomy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in taxonomy_rows if is_ai_focused_role(row)]
    return rows or taxonomy_rows


def processed_jd_dedup_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("source") or "").strip().lower(),
        str(row.get("canonical_role") or "").strip().lower(),
        str(row.get("raw_job_title") or "").strip().lower(),
        str(row.get("company_name") or "").strip().lower(),
        str(row.get("month") or "").strip(),
        str(row.get("work_arrangement") or "").strip().lower(),
        normalize_optional_float(row.get("salary_mid")),
    )


def title_tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9+#.]+", str(text).lower()) if token}


def role_title_tokens(text: str) -> set[str]:
    return {token for token in title_tokens(text) if token not in ROLE_STOPWORDS}


def compile_term_pattern(value: str) -> re.Pattern[str] | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])")


def generated_role_aliases(canonical_role: str) -> list[str]:
    tokens = list(role_title_tokens(canonical_role))
    if not tokens:
        return []
    aliases = set()
    if len(tokens) >= 2:
        aliases.add(" ".join(tokens))
    joined = " ".join(tokens)
    if "backend" in tokens:
        aliases.add(f"{joined} engineer")
        aliases.add(f"{joined} developer")
    if "frontend" in tokens:
        aliases.add(f"{joined} developer")
    if "devops" in tokens:
        aliases.add("cloud infrastructure engineer")
        aliases.add("platform engineer")
    if "qa" in tokens:
        aliases.add("test engineer")
        aliases.add("quality assurance engineer")
    if "system" in tokens and "administrator" in canonical_role.lower():
        aliases.add("sysadmin")
        aliases.add("systems administrator")
    if "rag" in tokens:
        aliases.add("retrieval augmented generation engineer")
    if "llm" in tokens:
        aliases.add("large language model engineer")
    return sorted(alias for alias in aliases if alias.strip())


def skill_hit_fraction(text: str, skills: Iterable[str]) -> tuple[list[str], float]:
    haystack = str(text).lower()
    source_skills = list(skills) if not isinstance(skills, list) else skills
    matched: list[str] = []
    filtered_total = 0
    for skill in source_skills:
        skill_text = str(skill).strip()
        if not skill_text:
            continue
        normalized = skill_text.lower()
        if normalized in AMBIGUOUS_SKILL_TOKENS:
            continue
        if len(normalized) < 3 and normalized not in {"c++", "c#", ".net", "aws", "sql"}:
            continue
        filtered_total += 1
        pattern = r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])"
        if re.search(pattern, haystack):
            matched.append(skill_text)
    total = filtered_total
    fraction = len(matched) / total if total else 0.0
    return matched, round(fraction, 6)


def prepare_skill_patterns(skills: Iterable[str]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    source_skills = list(skills) if not isinstance(skills, list) else skills
    for skill in source_skills:
        skill_text = str(skill).strip()
        if not skill_text:
            continue
        normalized = skill_text.lower()
        if normalized in AMBIGUOUS_SKILL_TOKENS:
            continue
        if len(normalized) < 3 and normalized not in {"c++", "c#", ".net", "aws", "sql"}:
            continue
        pattern = compile_term_pattern(normalized)
        if pattern is None:
            continue
        prepared.append({"skill": skill_text, "pattern": pattern})
    return prepared


def skill_hit_fraction_prepared(text: str, prepared_skills: list[dict[str, Any]]) -> tuple[list[str], float]:
    haystack = str(text).lower()
    matched: list[str] = []
    for item in prepared_skills:
        if item["pattern"].search(haystack):
            matched.append(item["skill"])
    total = len(prepared_skills)
    fraction = len(matched) / total if total else 0.0
    return matched, round(fraction, 6)


def prepare_taxonomy_rows(taxonomy_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    prepared_rows: list[dict[str, Any]] = []
    token_index: dict[str, list[dict[str, Any]]] = {}
    for row in taxonomy_rows:
        canonical = row["canonical_role"]
        canonical_tokens = role_title_tokens(canonical)
        alias_patterns = []
        alias_tokens: set[str] = set()
        for alias in row.get("aliases", []):
            pattern = compile_term_pattern(alias)
            if pattern is not None:
                alias_patterns.append((alias, pattern))
            alias_tokens |= role_title_tokens(alias)
        prepared = {
            **row,
            "canonical_lower": canonical.lower(),
            "canonical_tokens": canonical_tokens,
            "alias_patterns": alias_patterns,
            "prepared_skills": prepare_skill_patterns(row.get("top_skills", [])[:10]),
            "all_role_tokens": canonical_tokens | alias_tokens,
            "is_generic_it_role": canonical in GENERIC_IT_ROLES,
        }
        prepared_rows.append(prepared)
        for token in prepared["all_role_tokens"]:
            token_index.setdefault(token, []).append(prepared)
    return prepared_rows, token_index


def candidate_taxonomy_rows(
    raw_job_title: str,
    prepared_rows: list[dict[str, Any]],
    token_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    title_l = str(raw_job_title or "").lower()
    title_role_token_set = role_title_tokens(raw_job_title)
    candidates: dict[str, dict[str, Any]] = {}
    for token in title_role_token_set:
        for row in token_index.get(token, []):
            candidates[row["role_id"]] = row
    for row in prepared_rows:
        if row["canonical_lower"] in title_l:
            candidates[row["role_id"]] = row
            continue
        for _, alias_pattern in row["alias_patterns"]:
            if alias_pattern.search(title_l):
                candidates[row["role_id"]] = row
                break
    return list(candidates.values()) or prepared_rows


def score_role_match(raw_job_title: str, raw_jd_text: str, taxonomy_row: dict[str, Any]) -> dict[str, Any]:
    title = str(raw_job_title or "")
    jd_text = str(raw_jd_text or "")[:4000]
    title_l = title.lower()
    text_l = jd_text.lower()
    canonical = taxonomy_row["canonical_role"]
    aliases = taxonomy_row.get("aliases", [])
    top_skills = taxonomy_row.get("top_skills", [])

    score = 0.0
    matched_by = None
    matched_alias = None
    canonical_lower = taxonomy_row.get("canonical_lower", canonical.lower())
    canonical_tokens = taxonomy_row.get("canonical_tokens", role_title_tokens(canonical))
    title_role_tokens = role_title_tokens(title)

    if canonical_lower in title_l:
        score += 1.0
        matched_by = "title"
    elif len(canonical_tokens) >= 2:
        matched_token_count = len(canonical_tokens & title_role_tokens)
        overlap = matched_token_count / max(len(canonical_tokens), 1)
        if matched_token_count >= 2 and overlap >= 0.5:
            score = max(score, round(0.55 + 0.35 * overlap, 6))
            matched_by = "title"
    elif len(canonical_tokens) == 1 and title_role_tokens and canonical_tokens.issubset(title_role_tokens):
        matched_token_count = 1
        overlap = 1.0
        score = max(score, 0.65)
        matched_by = "title"

    alias_patterns = taxonomy_row.get("alias_patterns")
    if alias_patterns is None:
        alias_patterns = [(alias, compile_term_pattern(alias)) for alias in aliases]
    for alias, alias_pattern in alias_patterns:
        if alias_pattern and alias_pattern.search(title_l):
            score = max(score, 0.92)
            matched_by = "alias" if matched_by is None else "mixed"
            matched_alias = alias
            break

    prepared_skills = taxonomy_row.get("prepared_skills")
    if prepared_skills is None:
        prepared_skills = prepare_skill_patterns(top_skills[:10])
    matched_skills, hit_fraction = skill_hit_fraction_prepared(f"{title_l}\n{text_l}", prepared_skills)
    matched_skills_title, title_hit_fraction = skill_hit_fraction_prepared(title_l, prepared_skills)
    if hit_fraction > 0:
        skill_score = min(0.78, 0.2 + 0.58 * hit_fraction)
        has_title_skill_evidence = len(matched_skills_title) >= 1 and title_hit_fraction >= 0.1
        strong_title_skill_evidence = len(matched_skills_title) >= 2 or title_hit_fraction >= 0.2
        if matched_by is None and (
            (strong_title_skill_evidence and len(matched_skills) >= 2 and hit_fraction >= 0.2)
            or (has_title_skill_evidence and len(matched_skills) >= 3 and hit_fraction >= 0.35)
        ):
            matched_by = "skill"
            score = max(score, skill_score + (0.08 if strong_title_skill_evidence else 0.04))
        elif matched_by is not None:
            matched_by = "mixed"
            score = max(score, min(1.2, score + 0.15 + 0.35 * hit_fraction))

    if taxonomy_row.get("is_generic_it_role", canonical in GENERIC_IT_ROLES) and matched_by in {"title", "alias"}:
        joined = f"{title_l}\n{text_l}"
        has_it_support = bool(matched_skills) or any(keyword in joined for keyword in GENERIC_IT_SUPPORT_KEYWORDS)
        if not has_it_support:
            matched_by = "none"
            score = 0.0
    if taxonomy_row.get("is_generic_it_role", canonical in GENERIC_IT_ROLES) and matched_by == "skill":
        has_role_family_title_evidence = bool(canonical_tokens & title_role_tokens)
        if not has_role_family_title_evidence:
            matched_by = "none"
            score = 0.0

    return {
        "canonical_role": canonical,
        "role_id": taxonomy_row["role_id"],
        "matched_by": matched_by or "none",
        "matched_alias": matched_alias,
        "matched_skills": matched_skills,
        "role_match_score": round(score, 6),
        "skill_hit_fraction": hit_fraction,
    }


def choose_best_role(raw_job_title: str, raw_jd_text: str, taxonomy_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [score_role_match(raw_job_title, raw_jd_text, row) for row in taxonomy_rows]
    scored = [row for row in scored if row["role_match_score"] > 0]
    if not scored:
        return None
    scored.sort(
        key=lambda row: (
            -row["role_match_score"],
            row["matched_by"] != "title",
            row["canonical_role"],
        )
    )
    return scored[0]


def build_processed_jd_rows(raw_rows: list[dict[str, Any]], taxonomy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    prepared_rows, token_index = prepare_taxonomy_rows(taxonomy_rows)
    seen_processed_keys: set[tuple[Any, ...]] = set()
    for raw in raw_rows:
        raw_title = raw.get("raw_job_title", "")
        candidate_rows = candidate_taxonomy_rows(raw_title, prepared_rows, token_index)
        best = choose_best_role(raw_title, raw.get("raw_jd_text", ""), candidate_rows)
        if not best:
            continue
        if best["role_match_score"] < 0.45:
            continue
        if best["matched_by"] == "skill" and best["role_match_score"] < 0.6:
            continue
        month = month_start(raw.get("post_date"))
        if month is None:
            continue
        processed_row = {
            "source": raw["source"],
            "source_job_id": raw["source_job_id"],
            "canonical_role": best["canonical_role"],
            "role_id": best["role_id"],
            "raw_job_title": raw.get("raw_job_title"),
            "raw_jd_text": raw.get("raw_jd_text"),
            "salary_mid": normalize_optional_float(raw.get("salary_mid")),
            "post_date": raw.get("post_date"),
            "month": month.isoformat(),
            "education_required": raw.get("education_required"),
            "experience_required_years": raw.get("experience_required_years"),
            "company_name": raw.get("company_name"),
            "work_arrangement": normalize_work_arrangement(raw.get("work_arrangement")),
            "job_url": raw.get("job_url"),
            "role_match_score": best["role_match_score"],
            "matched_by": best["matched_by"],
            "matched_alias": best["matched_alias"],
            "matched_skills": best["matched_skills"],
            "jd_demand_weight": jd_demand_weight(best["role_match_score"], raw.get("salary_mid")),
            "source_skill_count": raw.get("source_skill_count"),
            "source_quality_score": raw.get("source_quality_score"),
            "job_description_length": raw.get("job_description_length"),
            "benefits_score": raw.get("benefits_score"),
            "remote_ratio_num": raw.get("remote_ratio_num"),
            "industry_label": raw.get("industry_label"),
            "job_level": raw.get("job_level"),
            "job_type_label": raw.get("job_type_label"),
        }
        dedup_key = processed_jd_dedup_key(processed_row)
        if dedup_key in seen_processed_keys:
            continue
        seen_processed_keys.add(dedup_key)
        processed.append(processed_row)
    return processed


def jd_demand_weight(role_match_score: float, salary_mid: Any) -> float:
    salary_bonus = 0.0
    try:
        if salary_mid is not None:
            salary_bonus = min(float(salary_mid) / 500_000.0, 0.2)
    except Exception:
        salary_bonus = 0.0
    return round(0.8 + min(role_match_score, 1.0) * 0.4 + salary_bonus, 6)


def zscore(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    std = clean.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series([0.0] * len(clean), index=clean.index)
    mean = clean.mean()
    return (clean - mean) / std


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def compute_jd_demand_index(df: pd.DataFrame) -> pd.Series:
    post_z = zscore(df["job_post_count"]) * 0.45
    company_z = zscore(df["unique_company_count"]) * 0.25
    salary_z = zscore(df["median_salary_mid"].fillna(df["avg_salary_mid"]).fillna(0.0)) * 0.15
    skill_z = zscore(df["jd_skill_hit_rate"]) * 0.15
    raw = post_z + company_z + salary_z + skill_z
    return raw.apply(lambda value: round(sigmoid(float(value)), 6))


def estimate_sentiment(text: str) -> float:
    lower = str(text).lower()
    pos = sum(1 for hint in POSITIVE_HINTS if hint in lower)
    neg = sum(1 for hint in NEGATIVE_HINTS if hint in lower)
    score = (pos - neg) / max(pos + neg, 1)
    return round(max(-1.0, min(1.0, score)), 6)


def export_json_report(payload: Any, path: Path) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_local_table_rows(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value
