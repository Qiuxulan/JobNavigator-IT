from __future__ import annotations

import json
import math
import os
import ssl
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from app.core.config import settings
from pipelines.trend.common import connect_db, fetch_role_taxonomy_from_db, load_role_taxonomy_local, safe_write_dataframe

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
ARXIV_API_URL = "http://export.arxiv.org/api/query"
INT32_MAX = 2_147_483_647
ARXIV_QUERY_DELAY_SEC = float(os.getenv("JOBNAV_TREND_ARXIV_QUERY_DELAY_SEC", "1.5"))
ARXIV_RETRY_ATTEMPTS = int(os.getenv("JOBNAV_TREND_ARXIV_RETRY_ATTEMPTS", "3"))
ARXIV_RETRY_BACKOFF_SEC = float(os.getenv("JOBNAV_TREND_ARXIV_RETRY_BACKOFF_SEC", "20"))
ARXIV_MAX_QUERY_TERMS = int(os.getenv("JOBNAV_TREND_ARXIV_MAX_QUERY_TERMS", "10"))
ARXIV_SKILL_CANDIDATE_LIMIT = int(os.getenv("JOBNAV_TREND_ARXIV_SKILL_CANDIDATE_LIMIT", "15"))
FINE_GRAINED_ROLE_PATH = Path("data/gold/fine_grained_roles_v1.json")
GENERIC_TECH_SKILL_TERMS = {
    "python",
    "sql",
    "excel",
    "linux",
    "typescript",
    "javascript",
    "java",
    "react",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    ".net",
    "node.js",
    "node",
}
GENERIC_TECH_SKILL_SUBSTRINGS = {
    "full-stack",
    "full stack",
}
GENERIC_QUERY_STOP_TERMS = {
    "api",
    "rest api",
    "agile",
    "git",
    "jira",
    "confluence",
    "scrum",
    "aws",
    "docker",
    "kubernetes",
    "sql",
    "python",
    "java",
    "javascript",
    "linux",
    "react",
    "machine learning",
    "data science",
    "android",
    "excel",
    "css",
    "html",
    "devops",
    "ci/cd",
    "microservices",
    "blockchain",
    "computer vision",
    "matlab",
    "algorithms",
    "data structures",
    "fine-tuning",
    "express.js",
    "haskell",
    "clojure",
    "elixir",
    "oop",
    "system design",
    # 通用泛词（不特属于任何角色）
    "cybersecurity",
    "qa automation",
    "unit testing",
    "xml",
    "json",
    "shell",
    "lua",
    "cuda",
    "webgl",
    "bootstrap",
}
GENERIC_ALIAS_TERMS = {
    "other",
    "lead",
    "design",
    "qa",
    "security",
    "devops",
    "java",
    "javascript",
    "python",
    "sql",
    "android",
    "ios",
    "scala",
    "php",
    "rust",
    "unity",
    ".net",
    "node.js",
    "project manager",
    "product manager",
    "business analyst",
    "data engineer",
    "data science",
}
GENERIC_ALIAS_SUBSTRINGS = {
    "consultant",
    "coordinator",
    "specialist",
    "operator",
}
ROLE_TITLE_STOPWORDS = {
    "engineer",
    "developer",
    "architect",
    "specialist",
    "administrator",
    "manager",
    "analyst",
}
GENERIC_ROLE_PHRASES = {
    "data",
    "project",
    "product",
    "business",
    "information security",
    "information",
    "delivery",
    "manual qa",
}
LOW_SIGNAL_ALIAS_SUBSTRINGS = {
    "manager",
    "expert",
    "contracts",
    "stand-in",
    "grinder",
    "setter",
    "director",
    "translation",
    "quality control",
    "safety",
    "color expert",
    "machine tool",
}
ARXIV_QUERY_STOP_TERMS = {
    "microsoft azure",
    "oracle database",
    "sql server",
    "db2",
    "tableau",
    "power bi",
    "kanban",
    "jira",
    "confluence",
    "cloudformation",
    "prometheus",
    "grafana",
    "ansible",
    "jenkins",
    "github actions",
    "github",
    "gitlab ci",
    "nginx",
    "apache airflow",
    "databricks",
    "snowflake",
    "hadoop",
    "etl",
    "fastapi",
    "django",
    "flask",
    "laravel",
    "symfony",
    "nestjs",
    "sass",
    "webpack",
    "next.js",
    "objective-c",
    "sqlite",
    "appium",
    "jmeter",
    "postman",
    "pytest",
    "junit",
}
ARXIV_RESEARCH_KEYWORDS = {
    "ai",
    "agent",
    "llm",
    "language model",
    "machine learning",
    "deep learning",
    "computer vision",
    "multimodal",
    "transformer",
    "diffusion",
    "rag",
    "retrieval",
    "recommendation",
    "recommender",
    "nlp",
    "natural language",
    "security",
    "cyber",
    "penetration",
    "vulnerability",
    "threat",
    "detection",
    "privacy",
    "encryption",
    "game",
    "graphics",
    "rendering",
    "simulation",
    "robot",
}
ARXIV_TERM_REWRITES = {
    "rag": "retrieval augmented generation",
    "llm": "large language model",
    "ai agent": "large language model agents",
    "prompt engineering": "prompt engineering",
    "nlp": "natural language processing",
    "recommendation system": "recommender systems",
    "computer vision": "computer vision",
    "multimodal": "multimodal learning",
    "information security": "cybersecurity",
    "security operations": "security operations center",
    "penetration testing": "vulnerability assessment",
    "security software": "software security",
    "unity": "game development",
    "unreal engine": "real-time rendering",
    "game designer": "game design",
    "game technical artist": "real-time rendering",
    "pytorch": "deep learning",
    "tensorflow": "deep learning",
    "feature stores": "feature store",
    "stream processing": "stream processing",
    "query optimization": "query optimization",
    "database systems": "database systems",
    "transaction processing": "transaction processing",
    "model serving": "model serving",
    "distributed training": "distributed training",
    "cloud security": "cloud security",
    "zero trust": "zero trust",
    "computer graphics": "computer graphics",
    "shader generation": "shader generation",
    "3d scene generation": "3d scene generation",
}
ARXIV_REWRITE_VALUES = {normalized for normalized in [term.strip().lower() for term in ARXIV_TERM_REWRITES.values()]}
ARXIV_ROLE_SEED_TERMS = {
    "AI Agent Engineer": ["large language model agents", "agentic ai", "tool-using agents"],
    "AI Evaluation Engineer": ["llm evaluation", "model evaluation", "benchmarking large language models"],
    "LLM Inference Engineer": ["large language model inference", "llm serving", "inference optimization"],
    "RAG Engineer": ["retrieval augmented generation", "dense retrieval", "vector retrieval"],
    "Computer Vision Engineer": ["computer vision", "multimodal learning", "image understanding"],
    "Machine Learning Research Engineer": ["machine learning research", "recommender systems", "representation learning"],
    "AI Solutions Architect": ["large language model applications", "ai systems", "multimodal systems"],
    "Applied AI Engineer": ["applied machine learning", "foundation models", "large language model applications"],
    "AI Infrastructure Engineer": ["machine learning systems", "distributed training", "model serving"],
    "Forward Deployed AI Engineer": ["ai deployment", "enterprise ai systems", "agentic ai applications"],
    "Context Engineer": ["conversational ai", "retrieval systems", "context management for llms"],
    "MLOps Engineer": ["mlops", "machine learning systems", "model serving"],
    "Prompt Engineer": ["prompt engineering", "in-context learning", "large language model prompting"],
    "AI Data Engineer": ["data engineering for ai", "retrieval systems", "feature stores"],
    "Data Engineer": ["data engineering", "stream processing", "data integration"],
    "Database Administrator": ["database systems", "query optimization", "transaction processing", "learned database systems"],
    "Business Analyst": ["business intelligence", "decision support systems", "analytics"],
    "Information Security Analyst": ["cybersecurity", "network security", "threat detection"],
    "Cloud Security Engineer": ["cloud security", "zero trust", "security architecture"],
    "Penetration Testing Engineer": ["penetration testing", "vulnerability assessment", "security testing"],
    "Security Operations Engineer": ["intrusion detection system", "security information and event management", "log anomaly detection", "threat detection"],
    "Security Software Engineer": ["software security", "program analysis", "secure coding"],
    "Game Designer": ["procedural content generation", "player behavior modeling", "game analytics", "interactive storytelling"],
    "Game C++ Engineer": ["game engine", "real-time simulation", "physics simulation"],
    "Game Technical Artist": ["neural rendering", "differentiable rendering", "computer graphics", "shader generation", "image stylization", "3d scene generation"],
    "Unity Developer": ["game development", "real-time rendering", "interactive simulation"],
    "Unreal Engine Developer": ["real-time rendering", "game engine", "virtual production"],
    "Data Scientist": ["machine learning", "data mining", "statistical learning"],
    "Rust Blockchain Engineer": ["smart contracts", "consensus protocols", "blockchain scalability", "distributed ledger"],
}
ARXIV_FRIENDLY_CATEGORIES = {
    "Emerging AI",
    "AI & Data",
    "Security",
    "Game Development",
    "Other IT",
}
ARXIV_CATEGORY_ALLOWED_KEYWORDS = {
    "Emerging AI": {"ai", "agent", "llm", "language model", "machine learning", "deep learning", "computer vision", "multimodal", "transformer", "diffusion", "rag", "retrieval", "nlp", "natural language", "recommendation", "recommender", "inference"},
    "AI & Data": {"machine learning", "deep learning", "data mining", "statistical", "recommender", "recommendation", "nlp", "natural language", "computer vision"},
    "Security": {"security", "cyber", "penetration", "vulnerability", "threat", "detection", "privacy", "encryption", "intrusion", "anomaly", "siem", "log"},
    "Game Development": {"game", "graphics", "rendering", "simulation", "player", "procedural", "virtual production", "storytelling", "analytics", "behavior", "neural", "differentiable", "material", "3d"},
    "Other IT": {"blockchain", "distributed", "cryptography", "consensus", "web3", "ledger", "contract", "scalability"},
}
ROLE_NAME_HINTS = {
    "prompt engineer": {"prompt engineering", "llm", "rag", "vector database", "openai api", "langchain", "langgraph", "embedding", "fine-tuning"},
    "rag engineer": {"rag", "langchain", "langgraph", "vector database", "embedding", "openai api", "prompt engineering", "fastapi", "mcp"},
    "ai agent engineer": {"ai agent", "langchain", "langgraph", "openai api", "embedding", "vector database", "mcp", "fine-tuning"},
    "data engineer": {"etl", "apache spark", "data warehouse", "data pipeline", "snowflake", "apache airflow", "hadoop", "databricks", "bigquery"},
    "backend java engineer": {"spring", "spring boot", "hibernate", "apache kafka", "junit", "rabbitmq", "jenkins", "groovy"},
    "backend python engineer": {"django", "flask", "fastapi", "pytest", "apache airflow", "pandas", "dynamodb", "graphql"},
    "devops engineer": {"terraform", "ansible", "jenkins", "prometheus", "grafana", "helm", "cloudformation", "argocd", "gitlab ci", "github actions", "nginx"},
    "information security analyst": {"owasp", "penetration testing", "siem", "zero trust", "oauth", "ssl/tls", "encryption", "powershell"},
    "manual qa engineer": {"selenium", "cypress", "playwright", "appium", "jmeter", "postman", "qa automation", "manual qa", "unit testing"},
    "android engineer": {"kotlin", "jetpack compose", "react native", "flutter", "xamarin", "sqlite", "junit", "appium", "grpc"},
    "project manager": {"scrum", "kanban", "jira", "confluence", "power bi", "tableau", "a/b testing", "agile", "project planning", "stakeholder", "risk management", "budget", "sprint", "roadmap", "jira", "confluence"},
    "rust blockchain engineer": {"blockchain", "solidity", "smart contract", "web3", "cryptography", "distributed system", "solana", "ethereum", "rust"},
    "frontend react engineer": {"react", "next.js", "typescript", "tailwind css", "redux", "sass", "graphql", "jest", "webpack", "vite"},
}
CATEGORY_SKILL_HINTS = {
    "Emerging AI": {"llm", "agent", "rag", "langchain", "langgraph", "embedding", "vector database", "openai api", "fine-tuning", "multimodal", "transformer", "prompt", "pytorch", "tensorflow", "mcp"},
    "AI & Data": {"etl", "data warehouse", "data pipeline", "apache spark", "snowflake", "apache airflow", "databricks", "hadoop", "tableau", "power bi", "bigquery", "amazon redshift"},
    "Backend Development": {"spring", "spring boot", "django", "flask", "fastapi", "hibernate", "apache kafka", "graphql", "redis", "rabbitmq", "laravel", "ruby on rails", "nestjs", "groovy"},
    "Frontend Development": {"react", "angular", "vue", "typescript", "react native", "next.js", "css", "html"},
    "Mobile Development": {"kotlin", "jetpack compose", "swift", "objective-c", "flutter", "xamarin", "react native", "android", "ios"},
    "Cloud Native & DevOps": {"terraform", "ansible", "jenkins", "prometheus", "grafana", "helm", "cloudformation", "argocd", "gitlab ci", "github actions", "nginx", "amazon ec2"},
    "QA & Testing": {"selenium", "cypress", "playwright", "appium", "jmeter", "postman", "qa automation", "manual qa", "unit testing", "junit"},
    "Security": {"owasp", "penetration", "siem", "zero trust", "oauth", "ssl/tls", "encryption", "powershell", "security operations"},
    "Game Development": {"unity", "unreal", "shader", "game", "gameplay", "technical artist"},
    "Product & Business Analysis": {"scrum", "kanban", "jira", "confluence", "power bi", "tableau", "a/b testing"},
}
CATEGORY_SKILL_PENALTIES = {
    "Product & Business Analysis": {"spring", "hibernate", "angular", "apache kafka", "django", "flask", "terraform", "langchain",
        "devops", "ci/cd", "ios", "blockchain", "computer vision", "laravel", "php", "hadoop", "symfony", "microservices",
        "matlab", "rust", "express.js", "vue.js", "jetpack compose", "scala", "nestjs", "maria db", "redis", "jenkins",
        "siem", "apache spark", "apache airflow", "penetration testing", "powershell"},
    "Security": {"tensorflow", "deep learning", "flutter", "computer vision", "ruby on rails"},
    "QA & Testing": {"langchain", "vector database", "terraform", "databricks"},
    "Other IT": {"matlab", "algorithms", "data structures", "fine-tuning", "express.js", "computer vision", "blockchain",
        "haskell", "clojure", "elixir", "oop", "system design", "tailwind css", "xamarin", "cypress", "postgresql",
        "rabbitmq", "mysql", "elasticsearch", "mongodb", "powershell"},
}
TECH_HEAT_AUDIT_JSON = Path("data/gold/tech_heat_keyword_audit.json")

for _env_name in ("SSLKEYLOGFILE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    _env_value = os.environ.get(_env_name)
    if not _env_value:
        continue
    if _env_name.upper() == "SSLKEYLOGFILE" and not os.path.exists(_env_value):
        os.environ.pop(_env_name, None)
        continue
    if _env_value.strip().endswith("127.0.0.1:9") or _env_value.strip().endswith("127.0.0.1:9/"):
        os.environ.pop(_env_name, None)


@dataclass(frozen=True)
class MonthWindow:
    month: str
    start: date
    end: date


def grouped_path(name: str):
    from pipelines.trend.common import DATA_GOLD_DIR

    return DATA_GOLD_DIR / name


def load_fine_grained_roles() -> list[dict]:
    if not FINE_GRAINED_ROLE_PATH.exists():
        return []
    try:
        return json.loads(FINE_GRAINED_ROLE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def build_fine_role_lookup(rows: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for row in rows:
        role_name = str(row.get("role_name") or row.get("fine_role") or "").strip()
        if role_name:
            lookup[role_name] = row
    return lookup


def normalized_text(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("/", " ").replace("-", " ").split())


def derive_common_skill_terms(fine_rows: list[dict]) -> tuple[set[str], dict[str, dict[str, float]]]:
    role_count = max(len(fine_rows), 1)
    coverage: dict[str, int] = {}
    total_weight: dict[str, float] = {}
    for row in fine_rows:
        skill_freq = row.get("skill_freq") or {}
        if not isinstance(skill_freq, dict):
            continue
        for skill, score in skill_freq.items():
            name = str(skill).strip()
            if not name:
                continue
            coverage[name] = coverage.get(name, 0) + 1
            try:
                total_weight[name] = total_weight.get(name, 0.0) + float(score)
            except Exception:
                total_weight[name] = total_weight.get(name, 0.0)
    stats = {
        skill: {
            "coverage": float(count),
            "coverage_ratio": round(count / role_count, 6),
            "total_weight": round(total_weight.get(skill, 0.0), 6),
            "avg_weight": round(total_weight.get(skill, 0.0) / max(count, 1), 6),
        }
        for skill, count in coverage.items()
    }
    common = set()
    for skill, meta in stats.items():
        lowered = skill.lower()
        coverage = meta["coverage"]
        if coverage >= 30:
            common.add(skill)
            continue
        if coverage >= 20 and (
            lowered in GENERIC_TECH_SKILL_TERMS
            or any(part in lowered for part in GENERIC_TECH_SKILL_SUBSTRINGS)
            or len(skill) <= 4
        ):
            common.add(skill)
    return common, stats


def derive_common_alias_terms(fine_rows: list[dict]) -> tuple[set[str], dict[str, int]]:
    alias_cov: dict[str, int] = {}
    for row in fine_rows:
        seen: set[str] = set()
        for alias in row.get("search_keywords", []) or []:
            alias_text = normalized_text(alias)
            if not alias_text or alias_text in seen:
                continue
            seen.add(alias_text)
            alias_cov[alias_text] = alias_cov.get(alias_text, 0) + 1
    common: set[str] = set()
    for alias_text, coverage in alias_cov.items():
        if alias_text in GENERIC_ALIAS_TERMS:
            common.add(alias_text)
            continue
        if any(part in alias_text for part in GENERIC_ALIAS_SUBSTRINGS):
            common.add(alias_text)
            continue
        if len(alias_text.split()) == 1 and coverage >= 2:
            common.add(alias_text)
            continue
        if len(alias_text.split()) >= 2 and coverage >= 4:
            common.add(alias_text)
    return common, alias_cov


def category_skill_multiplier(record: dict, skill_name: str, coverage: float) -> float:
    coarse_role = str(record.get("coarse_role") or "").strip()
    role_name = normalized_text(record.get("canonical_role") or record.get("role_name") or "")
    lowered = normalized_text(skill_name)
    multiplier = 1.0
    role_hints = ROLE_NAME_HINTS.get(role_name, set())
    category_hints = CATEGORY_SKILL_HINTS.get(coarse_role, set())
    penalties = CATEGORY_SKILL_PENALTIES.get(coarse_role, set())
    if lowered in role_hints:
        multiplier *= 3.0
    elif any(hint in lowered or lowered in hint for hint in role_hints):
        multiplier *= 2.3
    if lowered in category_hints:
        multiplier *= 1.8
    elif any(hint in lowered or lowered in hint for hint in category_hints):
        multiplier *= 1.35
    if lowered in penalties or any(penalty in lowered for penalty in penalties):
        multiplier *= 0.22
    if coverage <= 3:
        multiplier *= 1.15
    return multiplier


def build_curated_aliases(record: dict, fine: dict, common_aliases: set[str], alias_stats: dict[str, int]) -> list[str]:
    canonical_role = str(record.get("canonical_role") or "").strip()
    canonical_norm = normalized_text(canonical_role)
    normalized_phrase = normalized_text(normalized_role_phrase(canonical_role) or "")
    candidates: list[str] = []
    candidates.extend(str(alias).strip() for alias in record.get("aliases", []) if str(alias).strip())
    candidates.extend(str(alias).strip() for alias in (fine.get("search_keywords", []) or [])[:12] if str(alias).strip())
    curated: list[str] = []
    seen: set[str] = set()
    for alias in candidates:
        alias_text = str(alias).strip()
        alias_norm = normalized_text(alias_text)
        if not alias_norm or alias_norm in seen:
            continue
        seen.add(alias_norm)
        if alias_norm in {canonical_norm, normalized_phrase}:
            continue
        if alias_norm in common_aliases:
            continue
        if alias_stats.get(alias_norm, 0) > 3:
            continue
        if len(alias_norm.split()) < 2:
            continue
        curated.append(alias_text)
    return curated[:4]


def top_specific_skills(record: dict, common_terms: set[str], global_stats: dict[str, dict[str, float]]) -> list[str]:
    coarse_role = str(record.get("coarse_role") or record.get("category") or "").strip()
    role_penalties = CATEGORY_SKILL_PENALTIES.get(coarse_role, set())
    skill_freq = record.get("skill_freq") or {}
    scored: list[tuple[float, str, float, float]] = []
    for skill, raw_score in skill_freq.items():
        name = str(skill).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in GENERIC_TECH_SKILL_TERMS:
            continue
        if lowered in GENERIC_QUERY_STOP_TERMS:
            continue
        if len(name) < 3:
            continue
        # 彻底排除被该分类标记为噪声的词
        if lowered in role_penalties or any(penalty in lowered for penalty in role_penalties):
            continue
        try:
            score = float(raw_score)
        except Exception:
            score = 0.0
        coverage = global_stats.get(name, {}).get("coverage", 1.0)
        specificity = score * math.log((len(global_stats) + 1.0) / (coverage + 1.0))
        if name in common_terms:
            specificity *= 0.28
        if any(part in lowered for part in GENERIC_TECH_SKILL_SUBSTRINGS):
            specificity *= 0.85
        specificity *= category_skill_multiplier(record, name, coverage)
        scored.append((specificity, name, score, coverage))
    scored.sort(key=lambda item: (item[0], item[2], -item[3], len(item[1])), reverse=True)
    return [name for _, name, _, _ in scored[: max(int(settings.trend_tech_skill_limit), 1)]]


def selected_role_records(records: list[dict]) -> list[dict]:
    role_limit = max(int(settings.trend_tech_role_limit), 0)
    skill_limit = max(int(settings.trend_tech_skill_limit), 0)
    fine_rows = load_fine_grained_roles()
    fine_lookup = build_fine_role_lookup(fine_rows)
    common_terms, common_stats = derive_common_skill_terms(fine_rows)
    common_aliases, alias_stats = derive_common_alias_terms(fine_rows)
    trimmed: list[dict] = []
    for record in records[:role_limit] if role_limit else records:
        canonical_role = str(record.get("canonical_role") or "").strip()
        fine = fine_lookup.get(canonical_role, {})
        dedup_aliases = build_curated_aliases(record, fine, common_aliases, alias_stats)
        top_skills = top_specific_skills(fine, common_terms, common_stats) if fine else []
        if skill_limit:
            top_skills = top_skills[:skill_limit]
        if not top_skills and record.get("top_skills"):
            top_skills = [str(skill).strip() for skill in record.get("top_skills", []) if str(skill).strip()][:skill_limit]
        if not top_skills and not dedup_aliases:
            continue
        trimmed.append(
            {
                **record,
                "coarse_role": fine.get("coarse_role") or record.get("category") or record.get("coarse_role"),
                "aliases": dedup_aliases,
                "top_skills": top_skills,
                "common_terms_excluded": sorted(term for term in common_terms if term in set((fine.get("skill_freq") or {}).keys()))[:20] if fine else [],
            }
        )
    TECH_HEAT_AUDIT_JSON.write_text(
        json.dumps(
            {
                "role_count": len(trimmed),
                "common_skill_terms": sorted(common_terms),
                "common_alias_terms": sorted(common_aliases),
                "sample_roles": [
                    {
                        "canonical_role": row.get("canonical_role"),
                        "coarse_role": row.get("coarse_role"),
                        "aliases": row.get("aliases", [])[:6],
                        "top_skills": row.get("top_skills", [])[:20],
                        "query_terms": build_role_query_terms(row)[:26],
                    }
                    for row in trimmed[:69]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return trimmed


def normalized_role_phrase(canonical_role: str) -> str | None:
    tokens = []
    for raw in canonical_role.replace("/", " ").replace("-", " ").split():
        token = raw.strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in ROLE_TITLE_STOPWORDS:
            continue
        tokens.append(token)
    phrase = " ".join(tokens).strip()
    lowered_phrase = phrase.lower()
    if len(phrase) < 4:
        return None
    if lowered_phrase in GENERIC_TECH_SKILL_TERMS:
        return None
    if lowered_phrase in GENERIC_ROLE_PHRASES:
        return None
    return phrase if phrase and phrase.lower() != canonical_role.strip().lower() else None


def build_role_query_terms(record: dict) -> list[str]:
    terms: list[str] = []
    canonical_role = str(record["canonical_role"]).strip()
    if canonical_role:
        terms.append(canonical_role)
    normalized_phrase = normalized_role_phrase(canonical_role)
    if normalized_phrase:
        terms.append(normalized_phrase)
    for alias in record.get("aliases", [])[:4]:
        alias_text = str(alias).strip()
        if alias_text:
            terms.append(alias_text)
    for skill in record.get("top_skills", [])[: max(int(settings.trend_tech_skill_limit), 1)]:
        skill_text = str(skill).strip()
        lowered = skill_text.lower()
        if not skill_text:
            continue
        if lowered in GENERIC_TECH_SKILL_TERMS:
            continue
        if lowered in GENERIC_QUERY_STOP_TERMS:
            continue
        if len(skill_text) < 3:
            continue
        if skill_text:
            terms.append(skill_text)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def build_term_role_map(records: list[dict]) -> dict[str, list[str]]:
    mapping: dict[str, set[str]] = {}
    identity_terms: set[str] = set()
    for record in records:
        canonical = str(record.get("canonical_role", "")).strip().lower()
        if canonical:
            identity_terms.add(canonical)
        normalized = normalized_role_phrase(str(record.get("canonical_role", "")).strip())
        if normalized:
            identity_terms.add(normalized.lower())
        for alias in record.get("aliases", [])[:2]:
            alias_text = str(alias).strip().lower()
            if alias_text:
                identity_terms.add(alias_text)
    for record in records:
        canonical_role = record["canonical_role"]
        for term in build_role_query_terms(record):
            normalized = str(term).strip()
            if not normalized:
                continue
            mapping.setdefault(normalized, set()).add(canonical_role)
    filtered: dict[str, list[str]] = {}
    for term, roles in mapping.items():
        lowered = term.lower()
        # broad non-title terms that hit too many roles are not useful as trend keywords
        if len(roles) > 12 and lowered not in identity_terms:
            continue
        filtered[term] = sorted(roles)
    return filtered


def search_terms_for_api(record: dict, max_terms: int) -> list[str]:
    terms = build_role_query_terms(record)
    identity_terms: list[str] = []
    skill_terms: list[str] = []
    canonical = str(record.get("canonical_role") or "").strip()
    normalized = normalized_role_phrase(canonical)
    aliases = {str(alias).strip().lower() for alias in record.get("aliases", [])}
    for term in terms:
        lowered = normalized_text(term)
        if term == canonical or (normalized and term == normalized) or lowered in aliases:
            identity_terms.append(term)
        else:
            skill_terms.append(term)
    ordered = identity_terms + skill_terms
    deduped: list[str] = []
    seen: set[str] = set()
    for term in ordered:
        key = normalized_text(term)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped[:max_terms]


def alias_is_arxiv_friendly(alias_text: str) -> bool:
    lowered = normalized_text(alias_text)
    if not lowered:
        return False
    if any(token in lowered for token in LOW_SIGNAL_ALIAS_SUBSTRINGS):
        return False
    if lowered in GENERIC_ALIAS_TERMS:
        return False
    return any(keyword_matches_text(keyword, lowered) for keyword in ARXIV_RESEARCH_KEYWORDS) or len(lowered.split()) >= 3


def keyword_matches_text(keyword: str, text: str) -> bool:
    normalized_keyword = normalized_text(keyword)
    normalized_value = normalized_text(text)
    if not normalized_keyword or not normalized_value:
        return False
    if " " in normalized_keyword:
        return normalized_keyword in normalized_value
    return normalized_keyword in set(normalized_value.split())


def is_research_term(term: str) -> bool:
    lowered = normalized_text(term)
    if not lowered:
        return False
    if lowered in ARXIV_QUERY_STOP_TERMS:
        return False
    return any(keyword_matches_text(keyword, lowered) for keyword in ARXIV_RESEARCH_KEYWORDS)


def category_term_allowed(coarse_role: str, term: str) -> bool:
    allowed = ARXIV_CATEGORY_ALLOWED_KEYWORDS.get(coarse_role)
    if not allowed:
        return False
    lowered = normalized_text(term)
    return any(keyword_matches_text(keyword, lowered) for keyword in allowed)


def arxiv_term_candidates(record: dict) -> list[str]:
    canonical_role = str(record.get("canonical_role") or "").strip()
    coarse_role = str(record.get("coarse_role") or "").strip()
    candidates: list[str] = []
    candidates.extend(ARXIV_ROLE_SEED_TERMS.get(canonical_role, []))
    normalized_phrase = normalized_role_phrase(canonical_role)
    if canonical_role and (coarse_role in ARXIV_FRIENDLY_CATEGORIES or is_research_term(canonical_role)):
        candidates.append(canonical_role)
    if normalized_phrase and (coarse_role in ARXIV_FRIENDLY_CATEGORIES or is_research_term(normalized_phrase)):
        candidates.append(normalized_phrase)
    for alias in record.get("aliases", [])[:6]:
        alias_text = str(alias).strip()
        if alias_is_arxiv_friendly(alias_text) and category_term_allowed(coarse_role, alias_text):
            candidates.append(alias_text)
    for skill in record.get("top_skills", [])[: max(ARXIV_SKILL_CANDIDATE_LIMIT, 1)]:
        skill_text = str(skill).strip()
        lowered = normalized_text(skill_text)
        if not skill_text or lowered in ARXIV_QUERY_STOP_TERMS:
            continue
        rewritten = ARXIV_TERM_REWRITES.get(lowered, skill_text)
        if is_research_term(rewritten) and category_term_allowed(coarse_role, rewritten):
            candidates.append(rewritten)
    if len(candidates) < 6:
        for skill in record.get("top_skills", [])[: max(ARXIV_SKILL_CANDIDATE_LIMIT, 1)]:
            skill_text = str(skill).strip()
            lowered = normalized_text(skill_text)
            if not skill_text or lowered in ARXIV_QUERY_STOP_TERMS:
                continue
            rewritten = ARXIV_TERM_REWRITES.get(lowered, skill_text)
            if category_term_allowed(coarse_role, rewritten):
                candidates.append(rewritten)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        key = normalized_text(term)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def arxiv_term_score(term: str) -> tuple[int, int, int, int]:
    lowered = normalized_text(term)
    research_hits = sum(1 for keyword in ARXIV_RESEARCH_KEYWORDS if keyword_matches_text(keyword, lowered))
    has_role_suffix = int(any(lowered.endswith(suffix) for suffix in ("engineer", "developer", "architect", "analyst", "manager")))
    token_count = len(lowered.split())
    rewritten_bonus = int(lowered in ARXIV_REWRITE_VALUES)
    return (research_hits, rewritten_bonus, -has_role_suffix, token_count)


def search_terms_for_arxiv(record: dict, max_terms: int) -> list[str]:
    ranked = sorted(arxiv_term_candidates(record), key=lambda term: arxiv_term_score(term), reverse=True)
    return ranked[:max_terms]


def expand_keyword_rows(keyword_rows: list[dict], keyword_role_map: dict[str, list[str]]) -> list[dict]:
    rows: list[dict] = []
    for row in keyword_rows:
        for canonical_role in keyword_role_map.get(str(row["keyword"]).strip(), []):
            rows.append({**row, "canonical_role": canonical_role})
    return rows


def month_windows(months_back: int) -> list[MonthWindow]:
    now = datetime.now(UTC).date().replace(day=1)
    windows: list[MonthWindow] = []
    current = now
    for _ in range(max(months_back, 1)):
        year = current.year + (current.month // 12)
        month = (current.month % 12) + 1
        next_month = date(year, month, 1)
        windows.append(MonthWindow(month=current.isoformat(), start=current, end=next_month))
        prev_month = current.month - 1
        prev_year = current.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        current = date(prev_year, prev_month, 1)
    windows.reverse()
    return windows


def complete_month_windows(months_back: int, today: date | None = None) -> list[MonthWindow]:
    anchor = (today or datetime.now(UTC).date()).replace(day=1)
    current = anchor
    windows: list[MonthWindow] = []
    for _ in range(max(months_back - 1, 0)):
        prev_month = current.month - 1
        prev_year = current.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        start = date(prev_year, prev_month, 1)
        windows.append(MonthWindow(month=start.isoformat(), start=start, end=current))
        current = start
    windows.reverse()
    return windows


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_json_with_headers(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[dict, dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8", errors="replace")), dict(response.info())


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    return json.loads(http_get_text(url, headers=headers, timeout=timeout))


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def clamp_int32(value: int | float | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return max(0, min(parsed, INT32_MAX))


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "JobNavigator-IT/tech-heat"}
    token = settings.trend_github_token or os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def collect_google_trends(records: list[dict]) -> list[dict]:
    if not settings.trend_enable_google_trends:
        return []
    try:
        from pytrends.request import TrendReq
    except Exception:
        return []

    pytrends = TrendReq(hl="en-US", tz=0)
    allowed_months = {window.month for window in complete_month_windows(12)}
    rows: list[dict] = []
    for record in records:
        keywords = record["top_skills"]
        if not keywords:
            continue
        try:
            pytrends.build_payload(keywords, timeframe="today 12-m", geo=settings.trend_google_trends_geo or "")
            interest = pytrends.interest_over_time()
        except Exception:
            continue
        if interest.empty:
            continue
        if "isPartial" in interest.columns:
            interest = interest.drop(columns=["isPartial"])
        monthly = interest.resample("MS").mean()
        for month, row in monthly.iterrows():
            month_text = month.date().isoformat()
            if month_text not in allowed_months:
                continue
            for keyword in keywords:
                rows.append(
                    {
                        "canonical_role": record["canonical_role"],
                        "keyword": keyword,
                        "month": month_text,
                        "google_trend_index": float(row.get(keyword, 0.0)),
                        "github_repo_count": None,
                        "github_repo_stars": None,
                        "arxiv_paper_count": None,
                    }
                )
        time.sleep(1.0)
    return rows


def collect_github(records: list[dict]) -> list[dict]:
    if not settings.trend_enable_github:
        return []
    headers = github_headers()
    windows = complete_month_windows(settings.trend_github_months)
    rows: list[dict] = []
    cache: dict[tuple[str, str], tuple[int | None, float]] = {}
    for record in records:
        query_terms = search_terms_for_api(record, max_terms=6)
        if not query_terms:
            continue
        role = str(record["canonical_role"])
        for term in query_terms:
            for window in windows:
                key = (term, window.month)
                if key not in cache:
                    q = f"\"{term}\" in:name,description,readme pushed:{window.start.isoformat()}..{(window.end - timedelta(days=1)).isoformat()} archived:false"
                    url = f"{GITHUB_SEARCH_URL}?{urllib.parse.urlencode({'q': q, 'per_page': settings.trend_github_top_items, 'sort': 'updated', 'order': 'desc'})}"
                    payload = None
                    for attempt in range(3):
                        try:
                            payload, response_headers = http_get_json_with_headers(url, headers=headers, timeout=30)
                            remaining = response_headers.get("X-RateLimit-Remaining")
                            if remaining == "0":
                                reset = response_headers.get("X-RateLimit-Reset")
                                if reset:
                                    sleep_for = max(int(reset) - int(time.time()) + 1, 1)
                                    time.sleep(min(sleep_for, 20))
                            break
                        except urllib.error.HTTPError as exc:
                            if exc.code in {403, 429} and attempt < 2:
                                reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
                                if reset:
                                    sleep_for = max(int(reset) - int(time.time()) + 1, 2)
                                else:
                                    sleep_for = 4 * (attempt + 1)
                                time.sleep(min(sleep_for, 20))
                                continue
                            break
                        except Exception:
                            break
                    if payload is None:
                        cache[key] = (None, 0.0)
                    else:
                        cache[key] = (
                            clamp_int32(payload.get("total_count") or 0),
                            float(sum(item.get("stargazers_count", 0) for item in payload.get("items", []))),
                        )
                    time.sleep(0.2)
                repo_count, repo_stars = cache[key]
                rows.append(
                    {
                        "canonical_role": role,
                        "keyword": term,
                        "month": window.month,
                        "google_trend_index": None,
                        "github_repo_count": repo_count,
                        "github_repo_stars": repo_stars,
                        "arxiv_paper_count": None,
                    }
                )
    return rows


def collect_arxiv(records: list[dict]) -> list[dict]:
    if not settings.trend_enable_arxiv:
        return []
    windows = {window.month for window in complete_month_windows(settings.trend_arxiv_months)}
    rows: list[dict] = []
    cache: dict[str, dict[str, int]] = {}
    for record in records:
        query_terms = search_terms_for_arxiv(record, max_terms=max(ARXIV_MAX_QUERY_TERMS, 1))
        if not query_terms:
            continue
        for term in query_terms:
            if term not in cache:
                params = {
                    "search_query": f'all:"{term}"',
                    "start": 0,
                    "max_results": settings.trend_arxiv_max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"
                counts: dict[str, int] = {}
                for attempt in range(max(ARXIV_RETRY_ATTEMPTS, 1)):
                    try:
                        xml_text = http_get_text(url, headers={"User-Agent": "JobNavigator-IT/tech-heat"}, timeout=30)
                        root = ET.fromstring(xml_text)
                        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                            published = entry.findtext("{http://www.w3.org/2005/Atom}published")
                            published_date = parse_iso_date(published)
                            if published_date is None:
                                continue
                            month = published_date.replace(day=1).isoformat()
                            if month not in windows:
                                continue
                            counts[month] = counts.get(month, 0) + 1
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code == 429 and attempt < max(ARXIV_RETRY_ATTEMPTS, 1) - 1:
                            time.sleep(ARXIV_RETRY_BACKOFF_SEC * (attempt + 1))
                            continue
                        counts = {}
                        break
                    except Exception:
                        counts = {}
                        break
                cache[term] = counts
                time.sleep(ARXIV_QUERY_DELAY_SEC)
            for month, count in cache[term].items():
                rows.append(
                    {
                        "canonical_role": record["canonical_role"],
                        "keyword": term,
                        "month": month,
                        "google_trend_index": None,
                        "github_repo_count": None,
                        "github_repo_stars": None,
                        "arxiv_paper_count": clamp_int32(count),
                    }
                )
    return rows


def consolidate_rows(rows: list[dict]) -> pd.DataFrame:
    if not rows:
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
    df = pd.DataFrame(rows)
    df["month"] = df["month"].astype(str)
    return (
        df.groupby(["canonical_role", "keyword", "month"], as_index=False)
        .agg(
            google_trend_index=("google_trend_index", "max"),
            github_repo_count=("github_repo_count", "max"),
            github_repo_stars=("github_repo_stars", "max"),
            arxiv_paper_count=("arxiv_paper_count", "max"),
        )
    )


def db_ready_records(grouped: pd.DataFrame) -> list[dict]:
    if grouped.empty:
        return []
    records: list[dict] = []
    data = grouped.copy()
    for _, row in data.iterrows():
        google_trend_index = pd.to_numeric(row.get("google_trend_index"), errors="coerce")
        github_repo_stars = pd.to_numeric(row.get("github_repo_stars"), errors="coerce")
        records.append(
            {
                "canonical_role": str(row["canonical_role"]),
                "keyword": str(row["keyword"]),
                "month": str(row["month"]),
                "google_trend_index": None if pd.isna(google_trend_index) else float(google_trend_index),
                "github_repo_count": None if pd.isna(row.get("github_repo_count")) else int(clamp_int32(row.get("github_repo_count")) or 0),
                "github_repo_stars": None if pd.isna(github_repo_stars) else float(github_repo_stars),
                "arxiv_paper_count": None if pd.isna(row.get("arxiv_paper_count")) else int(clamp_int32(row.get("arxiv_paper_count")) or 0),
            }
        )
    return records


def main() -> None:
    try:
        taxonomy = selected_role_records(fetch_role_taxonomy_from_db())
    except Exception:
        taxonomy = selected_role_records(load_role_taxonomy_local())
    rows = [*collect_google_trends(taxonomy), *collect_github(taxonomy), *collect_arxiv(taxonomy)]
    grouped = consolidate_rows(rows)
    safe_write_dataframe(
        grouped,
        grouped_path("tech_keyword_month_features.parquet"),
        grouped_path("tech_keyword_month_features.json"),
    )
    db_write = {"attempted": True, "success": False, "error": None}
    try:
        with connect_db() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE tech_keyword_month_features")
            records = db_ready_records(grouped)
            if records:
                cur.executemany(
                    """
                    INSERT INTO tech_keyword_month_features (
                      canonical_role, keyword, month, google_trend_index, github_repo_count, github_repo_stars, arxiv_paper_count, updated_at
                    ) VALUES (
                      %(canonical_role)s, %(keyword)s, %(month)s, %(google_trend_index)s, %(github_repo_count)s, %(github_repo_stars)s, %(arxiv_paper_count)s, NOW()
                    )
                    ON CONFLICT (canonical_role, keyword, month) DO UPDATE SET
                      google_trend_index = COALESCE(EXCLUDED.google_trend_index, tech_keyword_month_features.google_trend_index),
                      github_repo_count = COALESCE(EXCLUDED.github_repo_count, tech_keyword_month_features.github_repo_count),
                      github_repo_stars = COALESCE(EXCLUDED.github_repo_stars, tech_keyword_month_features.github_repo_stars),
                      arxiv_paper_count = COALESCE(EXCLUDED.arxiv_paper_count, tech_keyword_month_features.arxiv_paper_count),
                      updated_at = NOW()
                    """,
                    records,
                )
            conn.commit()
        db_write["success"] = True
    except Exception as exc:
        db_write["error"] = str(exc)
    print(json.dumps({"status": "ok", "rows": len(grouped), "db_write": db_write}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
