from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
GOLD_DIR = ROOT / "data" / "gold"
REPORT_PATH = ROOT / "reports" / "graph_build_summary_v2.json"
ROLE_PATH = GOLD_DIR / "fine_grained_roles_v1.json"
SKILL_GRAPH_PATH = GOLD_DIR / "skill_prerequisite_v2.json"
RESOURCE_PATH = GOLD_DIR / "learning_resources_v1.json"
VOCAB_PATH = GOLD_DIR / "skill_vocab.json"

DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)
RELATIONS = ("JOB_REQUIRES", "SKILL_PREREQ", "SKILL_HAS_RESOURCE")
PROVIDER_SCORE = {"coursera": 1.0, "github": 0.75, "bilibili": 0.70}
DIFFICULTY_SCORE = {"beginner": 1.0, "intermediate": 2.0, "advanced": 3.0}


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _normalize_array(values: list[float]) -> list[float]:
    if not values:
        return []
    norm = math.sqrt(sum(v * v for v in values))
    if norm <= 1e-8:
        return values
    return [round(v / norm, 6) for v in values]


def _normalize_skill_id(raw: str, alias_to_id: dict[str, str]) -> str | None:
    key = str(raw).strip().lower()
    return alias_to_id.get(key) or alias_to_id.get(key.replace(" ", "-"))


def _role_top_skills(role: dict[str, Any], alias_to_id: dict[str, str], id_to_name: dict[str, str], skill_by_id: dict[str, Any], top_n: int = 30) -> list[dict[str, Any]]:
    weighted: dict[str, float] = {}
    for name, score in (role.get("skill_freq") or {}).items():
        skill_id = _normalize_skill_id(name, alias_to_id)
        if not skill_id:
            continue
        weighted[skill_id] = max(weighted.get(skill_id, 0.0), float(score))

    if not weighted:
        for skill_id in role.get("required_skill_ids") or []:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 1.0)
        for skill_id in role.get("core_skill_ids") or []:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 1.05)
        for skill_id in role.get("optional_skill_ids") or []:
            weighted[skill_id] = max(weighted.get(skill_id, 0.0), 0.65)

    ranked = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    core_ids = set(role.get("core_skill_ids") or [])
    return [
        {
            "skill_id": skill_id,
            "skill_name": skill_by_id.get(skill_id, {}).get("skill_name", id_to_name.get(skill_id, skill_id)),
            "importance_score": round(float(score), 6),
            "rank": idx,
            "is_core": skill_id in core_ids,
        }
        for idx, (skill_id, score) in enumerate(ranked, start=1)
    ]


def _build_skill_feature(skill: dict[str, Any]) -> list[float]:
    difficulty = DIFFICULTY_SCORE.get(str(skill.get("difficulty", "intermediate")).lower(), 2.0)
    return _normalize_array(
        [
            float(skill.get("level", 1)) / 5.0,
            difficulty / 3.0,
            min(float(skill.get("hours_estimate", 0)) / 200.0, 1.0),
            1.0 if skill.get("hot") else 0.0,
        ]
    )


def _build_job_feature(role_skills: list[dict[str, Any]], skill_by_id: dict[str, Any]) -> list[float]:
    if not role_skills:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    weights = [row["importance_score"] for row in role_skills]
    avg_weight = sum(weights) / len(weights)
    max_weight = max(weights)
    core_ratio = sum(1 for row in role_skills if row["is_core"]) / len(role_skills)
    avg_level = sum(float(skill_by_id.get(row["skill_id"], {}).get("level", 1)) for row in role_skills) / len(role_skills)
    avg_hours = sum(float(skill_by_id.get(row["skill_id"], {}).get("hours_estimate", 0)) for row in role_skills) / len(role_skills)
    return _normalize_array([avg_weight, max_weight, core_ratio, avg_level / 5.0, min(avg_hours / 200.0, 1.0)])


def _build_resource_feature(resource: dict[str, Any]) -> list[float]:
    provider = str(resource.get("provider", "")).lower()
    difficulty = DIFFICULTY_SCORE.get(str(resource.get("level", "beginner")).lower(), 1.0)
    return _normalize_array(
        [
            PROVIDER_SCORE.get(provider, 0.5),
            difficulty / 3.0,
            min(float(resource.get("hours_estimate", 0)) / 100.0, 1.0),
            min(float(resource.get("coverage_count", 1)) / 5.0, 1.0),
        ]
    )


def build_graph_payload() -> dict[str, Any]:
    roles = _load_json(ROLE_PATH)
    skill_graph = _load_json(SKILL_GRAPH_PATH)
    resources_json = _load_json(RESOURCE_PATH)
    vocab = _load_json(VOCAB_PATH)

    alias_to_id = vocab.get("alias_to_id", {})
    id_to_name = vocab.get("id_to_name", {})
    skills = skill_graph.get("skills", [])
    skill_by_id = {skill["skill_id"]: skill for skill in skills}

    skill_nodes = []
    skill_edges = []
    for skill in skills:
        skill_nodes.append(
            {
                "node_type": "skill",
                "node_id": skill["skill_id"],
                "payload_json": skill,
                "feature_vector": _build_skill_feature(skill),
            }
        )
        for prereq_id in skill.get("prerequisites", []):
            if prereq_id not in skill_by_id:
                continue
            prereq_skill = skill_by_id[prereq_id]
            prerequisite_cost = round(
                0.30
                + 0.08 * float(skill.get("level", 1))
                + 0.10 * DIFFICULTY_SCORE.get(str(skill.get("difficulty", "intermediate")).lower(), 2.0)
                + min(float(skill.get("hours_estimate", 0)) / 160.0, 0.8),
                4,
            )
            skill_edges.append(
                {
                    "src_type": "skill",
                    "src_id": prereq_id,
                    "dst_type": "skill",
                    "dst_id": skill["skill_id"],
                    "relation": "SKILL_PREREQ",
                    "weight": prerequisite_cost,
                    "confidence": 0.95,
                    "meta_json": {
                        "level": skill.get("level", 1),
                        "difficulty": skill.get("difficulty", "intermediate"),
                        "hours_estimate": skill.get("hours_estimate", 0),
                    },
                }
            )

    job_nodes = []
    job_edges = []
    role_skill_counts: dict[str, int] = {}
    for role in roles:
        top_skills = _role_top_skills(role, alias_to_id, id_to_name, skill_by_id, top_n=30)
        role_skill_counts[role["role_id"]] = len(top_skills)
        job_nodes.append(
            {
                "node_type": "job",
                "node_id": role["role_id"],
                "payload_json": {**role, "top_skills_v2": top_skills},
                "feature_vector": _build_job_feature(top_skills, skill_by_id),
            }
        )
        for row in top_skills:
            job_edges.append(
                {
                    "src_type": "job",
                    "src_id": role["role_id"],
                    "dst_type": "skill",
                    "dst_id": row["skill_id"],
                    "relation": "JOB_REQUIRES",
                    "weight": row["importance_score"],
                    "confidence": 0.92,
                    "meta_json": {
                        "importance_score": row["importance_score"],
                        "rank": row["rank"],
                        "is_core": row["is_core"],
                    },
                }
            )

    resource_map: dict[str, dict[str, Any]] = {}
    resource_edges = []
    for skill_id, payload in resources_json.get("skills", {}).items():
        for resource in payload.get("resources", []):
            row = resource_map.setdefault(
                resource["resource_id"],
                {
                    "resource_id": resource["resource_id"],
                    "title": resource["title"],
                    "url": resource["url"],
                    "provider": resource.get("source", ""),
                    "level": resource.get("difficulty", "beginner"),
                    "hours_estimate": float(resource.get("hours_estimate", 0.0)),
                    "coverage_count": 0,
                },
            )
            row["coverage_count"] += 1
            resource_quality = round(
                0.55 * PROVIDER_SCORE.get(str(row["provider"]).lower(), 0.5)
                + 0.25 * (1.0 if str(row["level"]).lower() in {"beginner", "intermediate", "advanced"} else 0.6)
                + 0.20 * min(1.0, 1.0 / max(row["coverage_count"], 1)),
                4,
            )
            resource_edges.append(
                {
                    "src_type": "skill",
                    "src_id": skill_id,
                    "dst_type": "resource",
                    "dst_id": resource["resource_id"],
                    "relation": "SKILL_HAS_RESOURCE",
                    "weight": resource_quality,
                    "confidence": 0.85,
                    "meta_json": {
                        "provider": row["provider"],
                        "difficulty": row["level"],
                        "hours_estimate": row["hours_estimate"],
                    },
                }
            )

    resource_nodes = [
        {
            "node_type": "resource",
            "node_id": resource["resource_id"],
            "payload_json": resource,
            "feature_vector": _build_resource_feature(resource),
        }
        for resource in resource_map.values()
    ]

    return {
        "nodes": [*skill_nodes, *job_nodes, *resource_nodes],
        "edges": [*skill_edges, *job_edges, *resource_edges],
        "role_skill_counts": role_skill_counts,
        "input_files": {
            "roles": str(ROLE_PATH.relative_to(ROOT)),
            "skill_graph": str(SKILL_GRAPH_PATH.relative_to(ROOT)),
            "resources": str(RESOURCE_PATH.relative_to(ROOT)),
            "skill_vocab": str(VOCAB_PATH.relative_to(ROOT)),
        },
    }


def ensure_schema(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE graph_edges
        ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
          node_type TEXT NOT NULL,
          node_id TEXT NOT NULL,
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          feature_vector DOUBLE PRECISION[] DEFAULT '{}'::double precision[],
          embedding_vector DOUBLE PRECISION[] DEFAULT '{}'::double precision[],
          updated_at TIMESTAMP DEFAULT NOW(),
          PRIMARY KEY (node_type, node_id)
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graphsage_embeddings (
          node_type TEXT NOT NULL,
          node_id TEXT NOT NULL,
          embedding DOUBLE PRECISION[] NOT NULL DEFAULT '{}'::double precision[],
          model_version TEXT NOT NULL,
          updated_at TIMESTAMP DEFAULT NOW(),
          PRIMARY KEY (node_type, node_id, model_version)
        );
        """
    )


def persist_graph(payload: dict[str, Any]) -> dict[str, int]:
    import psycopg

    counts = {"nodes": 0, "edges": 0}
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute("DELETE FROM graph_edges WHERE relation = ANY(%s)", (list(RELATIONS),))
            for node in payload["nodes"]:
                cur.execute(
                    """
                    INSERT INTO graph_nodes (node_type, node_id, payload_json, feature_vector, embedding_vector, updated_at)
                    VALUES (%s, %s, %s::jsonb, %s, %s, NOW())
                    ON CONFLICT (node_type, node_id) DO UPDATE SET
                      payload_json = EXCLUDED.payload_json,
                      feature_vector = EXCLUDED.feature_vector,
                      updated_at = NOW();
                    """,
                    (
                        node["node_type"],
                        node["node_id"],
                        json.dumps(node["payload_json"], ensure_ascii=False),
                        node["feature_vector"],
                        [],
                    ),
                )
                counts["nodes"] += 1
            for edge in payload["edges"]:
                cur.execute(
                    """
                    INSERT INTO graph_edges (src_type, src_id, dst_type, dst_id, relation, weight, confidence, meta_json, source_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    """,
                    (
                        edge["src_type"],
                        edge["src_id"],
                        edge["dst_type"],
                        edge["dst_id"],
                        edge["relation"],
                        edge["weight"],
                        edge["confidence"],
                        json.dumps(edge.get("meta_json", {}), ensure_ascii=False),
                    ),
                )
                counts["edges"] += 1
        conn.commit()
    return counts


def write_summary(payload: dict[str, Any], counts: dict[str, int]) -> None:
    relation_counter = Counter(edge["relation"] for edge in payload["edges"])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "dsn": DSN,
                "input_files": payload["input_files"],
                "counts": counts,
                "relations": dict(relation_counter),
                "role_skill_counts": payload["role_skill_counts"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    payload = build_graph_payload()
    counts = persist_graph(payload)
    write_summary(payload, counts)
    print(json.dumps({"status": "ok", "counts": counts, "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
