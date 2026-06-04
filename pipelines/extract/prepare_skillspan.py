from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DATASET_NAME = "jjzha/skillspan"


def spans_from_bio(tokens: list[str], tags: list[str]) -> list[str]:
    spans: list[str] = []
    current: list[str] = []
    for token, tag in zip(tokens, tags):
        tag_name = str(tag)
        if tag_name.startswith("B"):
            if current:
                spans.append(clean_span(current))
            current = [token]
        elif tag_name.startswith("I") and current:
            current.append(token)
        else:
            if current:
                spans.append(clean_span(current))
                current = []
    if current:
        spans.append(clean_span(current))
    return [span for span in spans if span]


def clean_span(tokens: list[str]) -> str:
    text = " ".join(tokens)
    text = text.replace(" ##", "").replace("##", "")
    text = text.replace(" / ", "/").replace(" - ", "-")
    for punct in [",", ".", ";", ":", ")", "]", "}"]:
        text = text.replace(f" {punct}", punct)
    for punct in ["(", "[", "{"]:
        text = text.replace(f"{punct} ", punct)
    return " ".join(text.split()).strip(" ,.;:")


def iter_skillspan_rows(split: str) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets is not installed. Install optional dependencies before preparing SkillSpan.") from exc
    dataset = load_dataset(DATASET_NAME, split=split)
    return list(dataset)


def build_outputs(rows: list[dict[str, Any]], limit: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    counter: Counter[str] = Counter()
    eval_rows: list[dict[str, Any]] = []
    selected = rows[:limit] if limit else rows
    for idx, row in enumerate(selected):
        tokens = list(row["tokens"])
        tags = list(row["tags_skill"])
        spans = spans_from_bio(tokens, tags)
        counter.update(span.lower() for span in spans)
        if spans:
            eval_rows.append(
                {
                    "id": f"skillspan_{idx:05d}",
                    "source": row.get("source"),
                    "text": " ".join(tokens),
                    "gold_skills": sorted(set(spans), key=lambda x: x.lower()),
                }
            )
    summary = {
        "dataset": DATASET_NAME,
        "rows_read": len(selected),
        "rows_with_skills": len(eval_rows),
        "unique_skills": len(counter),
        "top_skills": [{"skill": skill, "count": count} for skill, count in counter.most_common(200)],
    }
    return summary, eval_rows


def write_outputs(summary: dict[str, Any], eval_rows: list[dict[str, Any]], out: Path, eval_out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    eval_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with eval_out.open("w", encoding="utf-8") as f:
        for row in eval_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare SkillSpan skill candidates and JSONL eval rows.")
    parser.add_argument("--split", default="train", help="SkillSpan split to read, e.g. train/validation/test.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for quick smoke runs.")
    parser.add_argument("--out", type=Path, default=Path("data/processed/skillspan_skills.json"))
    parser.add_argument("--eval-out", type=Path, default=Path("data/silver/skillspan_skill_eval.jsonl"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = iter_skillspan_rows(args.split)
    summary, eval_rows = build_outputs(rows, limit=args.limit)
    write_outputs(summary, eval_rows, args.out, args.eval_out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved summary to: {args.out}")
    print(f"Saved eval rows to: {args.eval_out}")


if __name__ == "__main__":
    main()
