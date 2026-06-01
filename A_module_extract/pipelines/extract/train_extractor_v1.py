from __future__ import annotations

import argparse
import inspect
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SKILLSPAN_DATASET = "jjzha/skillspan"
BASE_MODEL = "jjzha/jobbert_skill_extraction"
LABEL_LIST = ["B", "I", "O"]
LABEL_TO_ID = {label: idx for idx, label in enumerate(LABEL_LIST)}
ID_TO_LABEL = {idx: label for idx, label in enumerate(LABEL_LIST)}


def simple_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9+#.]+(?:[-/][A-Za-z0-9+#.]+)*|[^\s]", text)


def normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", "", token.lower())


def apply_skill_labels(tokens: list[str], skills: list[str]) -> list[str]:
    labels = ["O"] * len(tokens)
    normalized_tokens = [normalize_token(token) for token in tokens]
    for skill in sorted(set(skills), key=lambda x: len(x), reverse=True):
        skill_tokens = [normalize_token(token) for token in simple_words(skill) if normalize_token(token)]
        if not skill_tokens:
            continue
        width = len(skill_tokens)
        for start in range(0, len(tokens) - width + 1):
            if labels[start] != "O":
                continue
            if normalized_tokens[start : start + width] == skill_tokens:
                labels[start] = "B"
                for offset in range(1, width):
                    labels[start + offset] = "I"
    return labels


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_jd_weak_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(path)[:limit]:
        tokens = simple_words(row["text"])
        labels = apply_skill_labels(tokens, row.get("gold_skills", []))
        if "B" not in labels:
            continue
        rows.append({"tokens": tokens, "tags_skill": labels, "source": "jd_skill_weak"})
    return rows


def read_skillspan_arrow(path: Path, limit: int) -> list[dict[str, Any]]:
    import pyarrow as pa
    import pyarrow.ipc as ipc

    with pa.memory_map(str(path), "r") as source:
        rows = ipc.open_stream(source).read_all().slice(0, limit).to_pylist()
    return [
        {"tokens": list(row["tokens"]), "tags_skill": [str(x) for x in row["tags_skill"]], "source": row["source"]}
        for row in rows
    ]


def build_skillspan_rows(cache_dir: Path, max_train_samples: int, max_eval_samples: int):
    train_rows = read_skillspan_arrow(cache_dir / "skillspan-train.arrow", max_train_samples)
    eval_rows = read_skillspan_arrow(cache_dir / "skillspan-validation.arrow", max_eval_samples)
    return train_rows, eval_rows


def tokenize_and_align_labels(examples: dict[str, Any], tokenizer: Any, max_length: int):
    tokenized = tokenizer(
        examples["tokens"],
        is_split_into_words=True,
        truncation=True,
        max_length=max_length,
    )
    all_labels: list[list[int]] = []
    for batch_idx, tags in enumerate(examples["tags_skill"]):
        word_ids = tokenized.word_ids(batch_index=batch_idx)
        tags_as_ids = [LABEL_TO_ID[str(tag)] for tag in tags]
        previous_word_id = None
        labels: list[int] = []
        for word_id in word_ids:
            if word_id is None:
                labels.append(-100)
            elif word_id != previous_word_id:
                labels.append(tags_as_ids[word_id])
            else:
                labels.append(-100)
            previous_word_id = word_id
        all_labels.append(labels)
    tokenized["labels"] = all_labels
    return tokenized


def simple_token_metrics(eval_pred: Any) -> dict[str, float]:
    import numpy as np

    logits, labels = eval_pred
    if isinstance(logits, tuple):
        logits = logits[0]
    predictions = np.argmax(logits, axis=-1)
    total = correct = skill_total = skill_correct = 0
    for pred_row, label_row in zip(predictions, labels):
        for pred, label in zip(pred_row, label_row):
            if label == -100:
                continue
            total += 1
            if int(pred) == int(label):
                correct += 1
            if int(label) != LABEL_TO_ID["O"]:
                skill_total += 1
                if int(pred) == int(label):
                    skill_correct += 1
    return {
        "token_accuracy": correct / total if total else 0.0,
        "skill_token_accuracy": skill_correct / skill_total if skill_total else 0.0,
    }


def training_args_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    from transformers import TrainingArguments

    kwargs: dict[str, Any] = {
        "output_dir": str(args.output_dir),
        "learning_rate": args.learning_rate,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "per_device_eval_batch_size": args.per_device_eval_batch_size,
        "num_train_epochs": args.num_train_epochs,
        "weight_decay": args.weight_decay,
        "logging_steps": args.logging_steps,
        "save_strategy": "no",
        "report_to": "none",
    }
    signature = inspect.signature(TrainingArguments.__init__)
    kwargs["use_cpu" if "use_cpu" in signature.parameters else "no_cuda"] = True
    kwargs["eval_strategy" if "eval_strategy" in signature.parameters else "evaluation_strategy"] = "epoch"
    if "save_safetensors" in signature.parameters:
        kwargs["save_safetensors"] = True
    return kwargs


def write_model_readme(args: argparse.Namespace, train_count: int, jd_count: int, metrics: dict[str, Any]) -> None:
    readme = f"""# extractor_v1

本目录是 A 模块技能抽取模型的 v2 本地版本。

## 训练信息

- base model: `{BASE_MODEL}`
- supervised dataset: `{SKILLSPAN_DATASET}`
- weak-labeled JD dataset: `{args.jd_skill_file}`
- output dir: `{args.output_dir}`
- SkillSpan train samples: `{args.max_skillspan_train_samples}`
- weak JD train samples: `{jd_count}`
- total train samples: `{train_count}`
- eval samples: `{args.max_eval_samples}`
- epochs: `{args.num_train_epochs}`
- batch size: `{args.per_device_train_batch_size}`
- created at: `{datetime.now().isoformat(timespec="seconds")}`

## 评估结果

```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

v2 使用新增 JD `required_skills` 数据做弱标注增强；英文简历数据仍主要用于真实抽取演示和后续弱标注扩展。
"""
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train extractor_v1 with SkillSpan plus weak-labeled JD skill data.")
    parser.add_argument("--output-dir", type=Path, default=Path("A_module_extract/models/extractor_v1"))
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument(
        "--skillspan-cache-dir",
        type=Path,
        default=Path.home()
        / ".cache/huggingface/datasets/jjzha___skillspan/default/0.0.0/33062e6bd0e03a5e01ae299ce0518f4613ef4298",
    )
    parser.add_argument("--jd-skill-file", type=Path, default=Path("A_module_extract/data/silver/jd_skill_list_eval.jsonl"))
    parser.add_argument("--max-skillspan-train-samples", type=int, default=1000)
    parser.add_argument("--max-jd-train-samples", type=int, default=1000)
    parser.add_argument("--max-eval-samples", type=int, default=200)
    parser.add_argument("--num-train-epochs", type=float, default=1.0)
    parser.add_argument("--per-device-train-batch-size", type=int, default=4)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--logging-steps", type=int, default=25)
    return parser


def write_model_readme_cn(args: argparse.Namespace, train_count: int, jd_count: int, metrics: dict[str, Any]) -> None:
    readme = f"""# extractor_v1

本目录是 A 模块英文技能抽取模型的 v2 本地版本。

## 训练信息

- 初始模型：`{args.base_model}`
- 人工标注数据：`{SKILLSPAN_DATASET}`
- JD 弱标注数据：`{args.jd_skill_file}`
- SkillSpan 训练样本：`{args.max_skillspan_train_samples}`
- JD 弱标注训练样本：`{jd_count}`
- 总训练样本：`{train_count}`
- 评估样本：`{args.max_eval_samples}`
- epoch：`{args.num_train_epochs}`
- batch size：`{args.per_device_train_batch_size}`
- 生成时间：`{datetime.now().isoformat(timespec="seconds")}`

## 评估结果

```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

v2 使用新增 JD `required_skills` 数据做弱标注增强。英文简历数据仍用于真实抽取演示和后续标注扩展。
"""
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    from datasets import Dataset
    from transformers import AutoModelForTokenClassification, AutoTokenizer, DataCollatorForTokenClassification, Trainer

    skillspan_train, eval_rows = build_skillspan_rows(
        args.skillspan_cache_dir,
        args.max_skillspan_train_samples,
        args.max_eval_samples,
    )
    jd_rows = build_jd_weak_rows(args.jd_skill_file, args.max_jd_train_samples)
    train_rows = skillspan_train + jd_rows

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForTokenClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABEL_LIST),
        id2label=ID_TO_LABEL,
        label2id=LABEL_TO_ID,
        ignore_mismatched_sizes=True,
    )

    train_dataset = Dataset.from_list(train_rows)
    eval_dataset = Dataset.from_list(eval_rows)
    tokenized_train = train_dataset.map(
        lambda examples: tokenize_and_align_labels(examples, tokenizer, args.max_length),
        batched=True,
        remove_columns=train_dataset.column_names,
    )
    tokenized_eval = eval_dataset.map(
        lambda examples: tokenize_and_align_labels(examples, tokenizer, args.max_length),
        batched=True,
        remove_columns=eval_dataset.column_names,
    )

    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": __import__("transformers").TrainingArguments(**training_args_kwargs(args)),
        "train_dataset": tokenized_train,
        "eval_dataset": tokenized_eval,
        "data_collator": DataCollatorForTokenClassification(tokenizer=tokenizer),
        "compute_metrics": simple_token_metrics,
    }
    trainer_signature = inspect.signature(Trainer.__init__)
    trainer_kwargs["processing_class" if "processing_class" in trainer_signature.parameters else "tokenizer"] = tokenizer
    trainer = Trainer(**trainer_kwargs)
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    (args.output_dir / "label_map.json").write_text(
        json.dumps({"label_list": LABEL_LIST, "label_to_id": LABEL_TO_ID, "id_to_label": ID_TO_LABEL}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "training_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_model_readme_cn(args, len(train_rows), len(jd_rows), metrics)
    print(json.dumps({"output_dir": str(args.output_dir), "train_rows": len(train_rows), "jd_weak_rows": len(jd_rows), "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
