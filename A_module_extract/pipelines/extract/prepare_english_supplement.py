from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


RESUME_DATASET = "yashpwr/resume-ner-training-data"
JD_SKILL_DATASET = "keerthanshetty/resume-skill-extractor-dataset"


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_resume_text(messages: list[dict[str, str]]) -> tuple[str, str | None]:
    user_text = ""
    assistant_text = None
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "user":
            user_text = content
        elif role == "assistant":
            assistant_text = content
    marker = "Please summarize the following resume:"
    if marker in user_text:
        user_text = user_text.split(marker, 1)[1]
    return clean_text(user_text), clean_text(assistant_text or "") or None


def load_split(dataset_name: str, split: str):
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets is not installed. Use the my_env Python with Hugging Face dependencies.") from exc
    return load_dataset(dataset_name, split=split)


def build_resume_rows(limit: int) -> list[dict[str, Any]]:
    dataset = load_split(RESUME_DATASET, "train")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(dataset.select(range(min(limit, len(dataset))))):
        resume_text, summary = extract_resume_text(row["messages"])
        if not resume_text:
            continue
        rows.append(
            {
                "id": f"resume_real_{idx:05d}",
                "dataset": RESUME_DATASET,
                "text": resume_text,
                "summary": summary,
            }
        )
    return rows


def build_jd_skill_rows(limit: int) -> list[dict[str, Any]]:
    dataset = load_split(JD_SKILL_DATASET, "train")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(dataset.select(range(min(limit, len(dataset))))):
        skills = [clean_text(skill) for skill in row.get("required_skills", []) if clean_text(skill)]
        text = clean_text(row.get("job_description", ""))
        if not text or not skills:
            continue
        rows.append(
            {
                "id": f"jd_skill_{idx:05d}",
                "dataset": JD_SKILL_DATASET,
                "title": row.get("title"),
                "source": row.get("source"),
                "text": text,
                "summary": clean_text(row.get("summary", "")),
                "gold_skills": sorted(set(skills), key=lambda x: x.lower()),
            }
        )
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, resume_rows: list[dict[str, Any]], jd_rows: list[dict[str, Any]]) -> None:
    unique_jd_skills = sorted({skill for row in jd_rows for skill in row["gold_skills"]}, key=lambda x: x.lower())
    summary = {
        "datasets": [
            {
                "name": RESUME_DATASET,
                "use": "real English resume text for extraction demos and future weak labeling",
                "rows_written": len(resume_rows),
            },
            {
                "name": JD_SKILL_DATASET,
                "use": "real English JD text with required_skills labels for skill extraction evaluation",
                "rows_written": len(jd_rows),
                "unique_gold_skills": len(unique_jd_skills),
            },
        ],
        "total_rows_written": len(resume_rows) + len(jd_rows),
        "top_level_outputs": [
            "data/silver/resume_real_english.jsonl",
            "data/silver/jd_skill_list_eval.jsonl",
        ],
        "sample_jd_skills": unique_jd_skills[:50],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare supplemental real English datasets for A-module extraction.")
    parser.add_argument("--resume-limit", type=int, default=5000)
    parser.add_argument("--jd-limit", type=int, default=3050)
    parser.add_argument("--resume-out", type=Path, default=Path("data/silver/resume_real_english.jsonl"))
    parser.add_argument("--jd-out", type=Path, default=Path("data/silver/jd_skill_list_eval.jsonl"))
    parser.add_argument("--summary-out", type=Path, default=Path("data/processed/english_supplement_summary.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    resume_rows = build_resume_rows(args.resume_limit)
    jd_rows = build_jd_skill_rows(args.jd_limit)
    write_jsonl(args.resume_out, resume_rows)
    write_jsonl(args.jd_out, jd_rows)
    write_summary(args.summary_out, resume_rows, jd_rows)
    print(
        json.dumps(
            {
                "resume_rows": len(resume_rows),
                "jd_skill_rows": len(jd_rows),
                "summary_out": str(args.summary_out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
