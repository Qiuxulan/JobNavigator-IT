from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rule_extractor import parse_jd, parse_resume


@dataclass
class EvalCounts:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    education_total: int = 0
    education_correct: int = 0
    experience_total: int = 0
    experience_correct: int = 0
    rows: int = 0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSONL") from exc
    return rows


def normalize_skill_set(skills: list[str]) -> set[str]:
    return {skill.strip().lower() for skill in skills if skill and skill.strip()}


def parse_prediction(mode: str, row: dict[str, Any]):
    text = row["text"]
    row_id = str(row.get("id", "row"))
    if mode == "jd":
        return parse_jd(text, job_id=row_id)
    return parse_resume(text, user_id=row_id)


def get_predicted_skills(mode: str, prediction: Any) -> list[str]:
    if mode == "jd":
        return sorted(set(prediction.required_skills + prediction.nice_to_have_skills))
    return prediction.skills


def evaluate(rows: list[dict[str, Any]], mode: str) -> tuple[EvalCounts, list[dict[str, Any]]]:
    counts = EvalCounts(rows=len(rows))
    details: list[dict[str, Any]] = []

    for row in rows:
        prediction = parse_prediction(mode, row)
        predicted_skills = normalize_skill_set(get_predicted_skills(mode, prediction))
        gold_skills = normalize_skill_set(row.get("gold_skills", []))

        tp = len(predicted_skills & gold_skills)
        fp = len(predicted_skills - gold_skills)
        fn = len(gold_skills - predicted_skills)
        counts.true_positive += tp
        counts.false_positive += fp
        counts.false_negative += fn

        gold_education = row.get("gold_education")
        pred_education = prediction.education_required if mode == "jd" else prediction.education
        if gold_education is not None:
            counts.education_total += 1
            if pred_education == gold_education:
                counts.education_correct += 1

        gold_experience = row.get("gold_experience_years")
        pred_experience = prediction.min_experience_years if mode == "jd" else prediction.experience_years
        if gold_experience is not None:
            counts.experience_total += 1
            if abs(float(pred_experience) - float(gold_experience)) <= 0.1:
                counts.experience_correct += 1

        details.append(
            {
                "id": row.get("id"),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "missing_skills": sorted(gold_skills - predicted_skills),
                "extra_skills": sorted(predicted_skills - gold_skills),
                "pred_education": pred_education,
                "gold_education": gold_education,
                "pred_experience_years": pred_experience,
                "gold_experience_years": gold_experience,
            }
        )

    return counts, details


def safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def print_report(counts: EvalCounts, details: list[dict[str, Any]], mode: str, gold_path: Path) -> None:
    precision = safe_div(counts.true_positive, counts.true_positive + counts.false_positive)
    recall = safe_div(counts.true_positive, counts.true_positive + counts.false_negative)
    f1 = safe_div(2 * precision * recall, precision + recall) if precision + recall else 0.0
    education_acc = safe_div(counts.education_correct, counts.education_total)
    experience_acc = safe_div(counts.experience_correct, counts.experience_total)

    print(f"A Extract Evaluation Report")
    print(f"Mode: {mode}")
    print(f"Gold file: {gold_path}")
    print(f"Rows: {counts.rows}")
    print()
    print("Skill extraction")
    print(f"  TP: {counts.true_positive}")
    print(f"  FP: {counts.false_positive}")
    print(f"  FN: {counts.false_negative}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1:        {f1:.4f}")
    print()
    print("Field extraction")
    print(f"  Education accuracy:  {counts.education_correct}/{counts.education_total} = {education_acc:.4f}")
    print(f"  Experience accuracy: {counts.experience_correct}/{counts.experience_total} = {experience_acc:.4f}")

    problem_rows = [row for row in details if row["fp"] or row["fn"]]
    if problem_rows:
        print()
        print("Rows with skill differences")
        for row in problem_rows:
            print(f"  - {row['id']}: missing={row['missing_skills']} extra={row['extra_skills']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate A module rule-based extraction.")
    parser.add_argument("--gold", type=Path, required=True, help="Gold JSONL path.")
    parser.add_argument("--mode", choices=["jd", "resume"], required=True, help="Gold data type.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = read_jsonl(args.gold)
    counts, details = evaluate(rows, args.mode)
    print_report(counts, details, args.mode, args.gold)


if __name__ == "__main__":
    main()
