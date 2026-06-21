from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.domain import JobRole, LearningResource
from app.services.skill_norm import normalize_skill_id

ROOT = Path(__file__).parents[2]
GOLD_DIR = ROOT / "data" / "gold"
ROLE_PATH = GOLD_DIR / "fine_grained_roles_v1.json"
SKILL_GRAPH_PATH = GOLD_DIR / "skill_prerequisite_v2.json"
RESOURCE_PATH = GOLD_DIR / "learning_resources_v1.json"
RESOURCE_V2_PATH = GOLD_DIR / "learning_resources_v2.json"
VOCAB_PATH = GOLD_DIR / "skill_vocab.json"


@lru_cache(maxsize=1)
def load_roles() -> dict[str, dict[str, Any]]:
    with ROLE_PATH.open(encoding="utf-8") as f:
        roles = json.load(f)
    return {role["role_id"]: role for role in roles}


@lru_cache(maxsize=1)
def load_skill_graph() -> dict[str, dict[str, Any]]:
    with SKILL_GRAPH_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return {skill["skill_id"]: skill for skill in payload.get("skills", [])}


@lru_cache(maxsize=1)
def load_vocab() -> dict[str, Any]:
    with VOCAB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _parse_resource_payload(payload: dict, resource_map: dict[str, list[LearningResource]]) -> None:
    for skill_id, item in payload.get("skills", {}).items():
        if resource_map.get(skill_id):
            continue
        resources = []
        for resource in item.get("resources", [])[:3]:
            level = (resource.get("difficulty") or "beginner").lower()
            if level not in {"beginner", "intermediate", "advanced"}:
                level = "beginner"
            resources.append(
                LearningResource(
                    resource_id=resource["resource_id"],
                    title=resource["title"],
                    url=resource["url"],
                    provider=resource.get("source", ""),
                    level=level,
                )
            )
        resource_map[skill_id] = resources


@lru_cache(maxsize=1)
def load_resources() -> dict[str, list[LearningResource]]:
    resource_map: dict[str, list[LearningResource]] = {}
    with RESOURCE_PATH.open(encoding="utf-8") as f:
        _parse_resource_payload(json.load(f), resource_map)
    if RESOURCE_V2_PATH.exists():
        with RESOURCE_V2_PATH.open(encoding="utf-8") as f:
            _parse_resource_payload(json.load(f), resource_map)
    return resource_map


def jobrole_from_role(role: dict[str, Any]) -> JobRole:
    return JobRole(
        job_id=role.get("role_id", "unknown"),
        title=role.get("role_name", ""),
        fine_role=role.get("fine_role", role.get("role_name", "")),
        coarse_role=role.get("coarse_role", ""),
        city=None,
        salary_min_k=None,
        salary_max_k=None,
        required_skills=list(role.get("required_skills") or []),
    )


def normalize_known_skill_ids(skills: list[str]) -> set[str]:
    graph = load_skill_graph()
    valid_ids = set(graph.keys())
    normalized: set[str] = set()
    for raw in skills:
        skill_id = normalize_skill_id(raw) or str(raw).strip().lower().replace(" ", "-")
        if skill_id in valid_ids:
            normalized.add(skill_id)
    return normalized


def skill_name(skill_id: str) -> str:
    graph = load_skill_graph()
    if skill_id in graph:
        return graph[skill_id]["skill_name"]
    vocab = load_vocab()
    return vocab.get("id_to_name", {}).get(skill_id, skill_id)


def role_top_skills(role: dict[str, Any], top_n: int = 30) -> list[dict[str, Any]]:
    vocab = load_vocab()
    alias_to_id = vocab.get("alias_to_id", {})
    id_to_name = vocab.get("id_to_name", {})
    skill_graph = load_skill_graph()
    core_ids = set(role.get("core_skill_ids") or [])
    required_ids = set(role.get("required_skill_ids") or [])
    optional_ids = set(role.get("optional_skill_ids") or [])

    weighted: dict[str, float] = {}
    for raw_name, score in (role.get("skill_freq") or {}).items():
        key = str(raw_name).strip().lower()
        skill_id = (
            alias_to_id.get(key)
            or alias_to_id.get(key.replace(" ", "-"))
            or normalize_skill_id(raw_name)
        )
        if not skill_id:
            continue
        weighted[skill_id] = max(weighted.get(skill_id, 0.0), float(score))

    if not weighted:
        for skill_id in required_ids:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 1.0)
        for skill_id in core_ids:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 1.05)
        for skill_id in optional_ids:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 0.65)

    ranked = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    rows: list[dict[str, Any]] = []
    for index, (skill_id, importance) in enumerate(ranked, start=1):
        rows.append(
            {
                "skill_id": skill_id,
                "skill_name": skill_graph.get(skill_id, {}).get(
                    "skill_name",
                    id_to_name.get(skill_id, skill_id),
                ),
                "importance_score": round(float(importance), 6),
                "rank": index,
                "is_core": skill_id in core_ids,
                "is_required": skill_id in required_ids,
                "is_optional": skill_id in optional_ids,
            }
        )
    return rows
