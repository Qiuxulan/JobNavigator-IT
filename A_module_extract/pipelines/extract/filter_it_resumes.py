from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


IT_KEYWORDS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "golang", "go ", "rust", "scala", "sql",
    "software", "developer", "engineer", "programmer", "frontend", "backend", "full stack", "full-stack",
    "data scientist", "data science", "data analyst", "data engineer", "machine learning", "deep learning",
    "artificial intelligence", " ai ", " ml ", "nlp", "computer vision", "analytics", "business intelligence",
    "database", "mysql", "postgresql", "oracle", "mongodb", "redis", "spark", "hadoop", "hive", "etl",
    "cloud", "aws", "azure", "gcp", "docker", "kubernetes", "devops", "sre", "linux", "unix",
    "network", "cybersecurity", "security engineer", "information security", "penetration testing",
    "api", "rest", "microservice", "distributed system", "web application", "mobile application",
    "react", "angular", "vue", "node.js", "django", "flask", "spring", "fastapi", ".net",
    "tableau", "power bi", "excel vba", "git", "github", "jira", "agile",
}


EXCLUDE_HINTS = {
    "fitness director", "general manager", "sales associate", "cashier", "bartender", "server",
    "registered nurse", "medical assistant", "teacher", "accountant", "warehouse", "driver",
}


def normalize_for_match(text: str) -> str:
    return f" {re.sub(r'\\s+', ' ', text.lower())} "


def keyword_hits(text: str) -> list[str]:
    normalized = normalize_for_match(text)
    hits: list[str] = []
    for keyword in sorted(IT_KEYWORDS):
        key = keyword.lower()
        if key.startswith(" ") or key.endswith(" "):
            if key in normalized:
                hits.append(keyword.strip())
            continue
        if re.search(rf"(?<![a-z0-9+#.]){re.escape(key)}(?![a-z0-9+#.])", normalized):
            hits.append(keyword)
    return hits


def exclude_hits(text: str) -> list[str]:
    normalized = normalize_for_match(text)
    return [hint for hint in sorted(EXCLUDE_HINTS) if hint in normalized]


def is_it_resume(row: dict[str, Any], min_hits: int) -> tuple[bool, list[str], list[str]]:
    text = f"{row.get('text', '')} {row.get('summary', '')}"
    hits = keyword_hits(text)
    excludes = exclude_hits(text)
    if len(hits) >= min_hits:
        return True, hits, excludes
    return False, hits, excludes


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Filter real English resumes to IT-related profiles.")
    parser.add_argument("--input", type=Path, default=Path("A_module_extract/data/silver/resume_real_english.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("A_module_extract/data/silver/resume_it_english.jsonl"))
    parser.add_argument("--summary-out", type=Path, default=Path("A_module_extract/data/processed/resume_it_filter_summary.json"))
    parser.add_argument("--min-hits", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = read_jsonl(args.input)
    kept: list[dict[str, Any]] = []
    rejected = 0
    for row in rows:
        keep, hits, excludes = is_it_resume(row, args.min_hits)
        if keep:
            enriched = dict(row)
            enriched["it_keyword_hits"] = hits
            enriched["non_it_exclude_hints"] = excludes
            kept.append(enriched)
        else:
            rejected += 1
    write_jsonl(args.out, kept)
    summary = {
        "input": str(args.input),
        "output": str(args.out),
        "total_rows": len(rows),
        "kept_rows": len(kept),
        "rejected_rows": rejected,
        "min_hits": args.min_hits,
        "filter_type": "keyword-based IT resume filter",
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
