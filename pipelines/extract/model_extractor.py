from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)
JOBBERT_SKILL_MODEL = "jjzha/jobbert_skill_extraction"
A_MODULE_ROOT = Path(__file__).resolve().parents[2]
LOCAL_EXTRACTOR_MODELS = [A_MODULE_ROOT / "models" / "extractor_v1"]


def normalize_model_skill(skill: str) -> str:
    skill = re.sub(r"\s+", " ", skill).strip(" \t\r\n,.;:()[]{}")
    if not skill:
        return ""
    upper_keep = {"sql", "nlp", "rag", "llm", "api", "etl", "aws", "gcp", "ci/cd"}
    lower = skill.lower()
    if lower in upper_keep:
        return lower.upper()
    if skill.isupper() and len(skill) <= 5:
        return skill
    return skill


@lru_cache(maxsize=1)
def _load_skill_pipeline() -> Any:
    try:
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
    except ImportError as exc:
        raise RuntimeError(
            "transformers is not installed. Install optional model dependencies before enabling JobBERT."
        ) from exc
    for local_model in LOCAL_EXTRACTOR_MODELS:
        if (local_model / "config.json").exists():
            tokenizer = AutoTokenizer.from_pretrained(str(local_model), local_files_only=True)
            model = AutoModelForTokenClassification.from_pretrained(str(local_model), local_files_only=True)
            return pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
            )
    model_path = JOBBERT_SKILL_MODEL
    return pipeline(
        "token-classification",
        model=model_path,
        tokenizer=model_path,
        aggregation_strategy="simple",
    )


def extract_model_skills(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    nlp = _load_skill_pipeline()
    outputs = nlp(text)
    skills: list[str] = []
    for item in outputs:
        entity = str(item.get("entity_group") or item.get("entity") or "").lower()
        if entity == "o":
            continue
        if entity and "skill" not in entity and entity not in {"b", "i", "label_0", "label_1", "label_2"}:
            continue
        word = str(item.get("word") or "")
        normalized = normalize_model_skill(word.replace(" ##", "").replace("##", ""))
        if normalized:
            skills.append(normalized)
    return sorted(set(skills), key=lambda x: x.lower())


def safe_extract_model_skills(text: str) -> list[str]:
    try:
        return extract_model_skills(text)
    except Exception as exc:  # pragma: no cover - depends on optional remote model/runtime.
        LOGGER.warning("JobBERT skill extraction unavailable; falling back to rules: %s", exc)
        return []
