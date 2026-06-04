from __future__ import annotations

import argparse
import ast
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import requests


DATASET_ID = "batuhanmtl/job_resume_fit"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
PARQUET_URL = (
    "https://huggingface.co/datasets/"
    f"{DATASET_ID}/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet"
)
IT_CATEGORY = "INFORMATION-TECHNOLOGY"


def download_parquet(path: Path, retries: int = 3) -> None:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with requests.get(PARQUET_URL, timeout=120, stream=True) as response:
                response.raise_for_status()
                with path.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            return
        except requests.RequestException as exc:
            last_error = exc
    raise RuntimeError(f"Failed to download {PARQUET_URL}") from last_error


def normalize_skill_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = ast.literal_eval(text)
            raw_items = parsed if isinstance(parsed, list) else re.split(r"[,;|]", text)
        except (SyntaxError, ValueError):
            raw_items = re.split(r"[,;|]", text)

    skills: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        skill = re.sub(r"\s+", " ", str(item)).strip(" \t\r\n,.;:-")
        key = skill.casefold()
        if skill and key not in seen:
            seen.add(key)
            skills.append(skill)
    return skills


def redact_resume(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    text = re.sub(r"https?://\S+|www\.\S+|linkedin\.com/\S+", "[REDACTED_URL]", text, flags=re.I)
    text = re.sub(r"(?:\+?\d[\d().\s-]{7,}\d)", "[REDACTED_PHONE]", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def build_rows(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    it_rows = frame[frame["category"].astype(str).str.upper() == IT_CATEGORY].copy()
    it_rows = it_rows.sort_values("ID").head(limit)

    rows: list[dict[str, Any]] = []
    for _, row in it_rows.iterrows():
        rows.append(
            {
                "id": f"profile_it_{int(row['ID'])}",
                "dataset": DATASET_ID,
                "source_url": DATASET_URL,
                "category": IT_CATEGORY,
                "text": redact_resume(str(row["resume_text"])),
                "gold_skills": normalize_skill_list(row["resume_skill_list"]),
                "gold_education": None,
                "gold_experience_years": None,
                "annotation_method": "dataset_resume_skill_list_weak_label",
                "pii_redacted": True,
            }
        )
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare anonymized English IT profile weak labels.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/silver/profile_labeled_v1.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=50)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with tempfile.TemporaryDirectory(prefix="a_module_profile_labels_") as temp_dir:
        parquet_path = Path(temp_dir) / "job_resume_fit.parquet"
        download_parquet(parquet_path)
        rows = build_rows(pd.read_parquet(parquet_path), args.limit)

    if len(rows) < args.limit:
        raise RuntimeError(f"Only found {len(rows)} {IT_CATEGORY} rows, expected {args.limit}.")
    write_jsonl(args.out, rows)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "rows": len(rows),
                "category": IT_CATEGORY,
                "dataset": DATASET_ID,
                "pii_redacted": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
