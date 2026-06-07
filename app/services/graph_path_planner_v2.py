from __future__ import annotations

import heapq
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
try:
    import psycopg
except ImportError:  # pragma: no cover - optional local dependency for DB-backed graph.
    psycopg = None

from app.schemas.domain import LearningPath, LearningPathStep, SkillGap, UserProfile
from app.services.career_catalog import (
    ROOT,
    jobrole_from_role,
    load_resources,
    load_roles,
    load_skill_graph,
    normalize_known_skill_ids,
    role_top_skills,
    skill_name,
)

MODEL_DIR = ROOT / "models" / "graphsage_v2"
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)
MODEL_VERSION = os.environ.get("JOBNAV_GRAPH_MODEL_VERSION", "graphsage-v2")
ROLE_SCORE_WEIGHTS = {
    "semantic": 0.42,
    "coverage": 0.23,
    "resource": 0.10,
    "graph": 0.08,
    "missing": 0.19,
    "prereq": 0.15,
    "hours": 0.09,
}
DIFFICULTY_VALUE = {"beginner": 1.0, "intermediate": 2.0, "advanced": 3.0}


@dataclass
class RolePathAnalysis:
    role: dict[str, Any]
    semantic_score: float
    role_score: float
    score_breakdown: dict[str, float]
    skill_gap: SkillGap
    path: LearningPath


@lru_cache(maxsize=1)
def _load_local_embeddings() -> tuple[dict[str, int], np.ndarray] | None:
    index_path = MODEL_DIR / "node_index.json"
    embeddings_path = MODEL_DIR / "embeddings.npy"
    if not index_path.exists() or not embeddings_path.exists():
        return None
    return json.loads(index_path.read_text(encoding="utf-8")), np.load(embeddings_path)


def _graph_ready() -> bool:
    if psycopg is None:
        return False
    try:
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM graph_edges WHERE relation = 'SKILL_PREREQ'")
                return bool(cur.fetchone()[0])
    except Exception:
        return False


def _prereq_cost(skill: dict[str, Any]) -> float:
    difficulty = DIFFICULTY_VALUE.get(str(skill.get("difficulty", "intermediate")).lower(), 2.0)
    level = float(skill.get("level", 1))
    hours = float(skill.get("hours_estimate", 0))
    return 0.30 + 0.08 * level + 0.10 * difficulty + min(hours / 160.0, 0.8)


def _teaches_quality(skill_id: str) -> float:
    resources = load_resources().get(skill_id, [])
    if not resources:
        return 0.0
    provider_score = {
        "coursera": 1.0,
        "github": 0.75,
        "bilibili": 0.7,
        "youtube": 0.6,
    }
    total = 0.0
    for resource in resources[:3]:
        total += provider_score.get(resource.provider.lower(), 0.55)
    return min(1.0, round(total / max(len(resources[:3]), 1), 4))


def _embedding_for_skill(skill_id: str) -> np.ndarray | None:
    if psycopg is not None:
        try:
            with psycopg.connect(DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT embedding
                        FROM graphsage_embeddings
                        WHERE node_type = 'skill' AND node_id = %s AND model_version = %s
                        """,
                        (skill_id, MODEL_VERSION),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return np.asarray(row[0], dtype=np.float32)
        except Exception:
            pass

    local = _load_local_embeddings()
    if local is None:
        return None
    index_map, embeddings = local
    key = f"skill:{skill_id}"
    if key not in index_map:
        return None
    return np.asarray(embeddings[index_map[key]], dtype=np.float32)


def _graph_reward(skill_id: str, target_ids: set[str]) -> float:
    source = _embedding_for_skill(skill_id)
    if source is None:
        return 0.45
    scores = []
    for target_id in target_ids:
        target = _embedding_for_skill(target_id)
        if target is None:
            continue
        similarity = float(np.dot(source, target) / (np.linalg.norm(source) * np.linalg.norm(target) + 1e-8))
        scores.append((similarity + 1.0) / 2.0)
    if not scores:
        return 0.45
    return max(0.0, min(1.0, max(scores)))


def _heuristic(skill_id: str, target_id: str, skill_graph: dict[str, dict[str, Any]]) -> float:
    target_skill = skill_graph[target_id]
    node_skill = skill_graph[skill_id]
    level_gap = max(float(target_skill.get("level", 1)) - float(node_skill.get("level", 1)), 0.0) / 5.0
    graph_bonus = 1.0 - _graph_reward(skill_id, {target_id})
    return round(max(0.05, 0.5 * level_gap + 0.5 * graph_bonus), 4)


def _build_skill_adjacency(skill_graph: dict[str, dict[str, Any]]) -> tuple[dict[str, list[tuple[str, float]]], dict[str, list[str]]]:
    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    prereq_map: dict[str, list[str]] = defaultdict(list)
    for skill_id, skill in skill_graph.items():
        for prereq_id in skill.get("prerequisites", []):
            if prereq_id not in skill_graph:
                continue
            adjacency[prereq_id].append((skill_id, _prereq_cost(skill)))
            prereq_map[skill_id].append(prereq_id)
    return adjacency, prereq_map


def _astar_prereq_path(
    target_id: str,
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
    adjacency: dict[str, list[tuple[str, float]]],
) -> list[str]:
    roots = [skill_id for skill_id, skill in skill_graph.items() if not skill.get("prerequisites")]
    open_heap: list[tuple[float, float, str]] = []
    g_score: dict[str, float] = {}
    previous: dict[str, str] = {}

    for known_id in known_ids:
        g_score[known_id] = 0.0
        heapq.heappush(open_heap, (_heuristic(known_id, target_id, skill_graph), 0.0, known_id))

    for root_id in roots:
        if root_id in g_score:
            continue
        root_cost = _prereq_cost(skill_graph[root_id]) * 0.4
        g_score[root_id] = root_cost
        heapq.heappush(open_heap, (root_cost + _heuristic(root_id, target_id, skill_graph), root_cost, root_id))

    visited: set[str] = set()
    while open_heap:
        _, current_cost, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)
        if current == target_id:
            path = [current]
            while current in previous:
                current = previous[current]
                path.append(current)
            return list(reversed(path))

        for neighbor, edge_cost in adjacency.get(current, []):
            tentative = current_cost + edge_cost
            if tentative >= g_score.get(neighbor, float("inf")):
                continue
            previous[neighbor] = current
            g_score[neighbor] = tentative
            priority = tentative + _heuristic(neighbor, target_id, skill_graph)
            heapq.heappush(open_heap, (priority, tentative, neighbor))
    return []


def _ordered_learning_steps(selected_ids: set[str], prereq_map: dict[str, list[str]], skill_graph: dict[str, dict[str, Any]]) -> list[str]:
    indegree = {skill_id: 0 for skill_id in selected_ids}
    children: dict[str, list[str]] = defaultdict(list)
    for skill_id in selected_ids:
        for prereq_id in prereq_map.get(skill_id, []):
            if prereq_id in selected_ids:
                indegree[skill_id] += 1
                children[prereq_id].append(skill_id)

    ready = [
        skill_id
        for skill_id, degree in indegree.items()
        if degree == 0
    ]
    ready.sort(key=lambda skill_id: (skill_graph[skill_id].get("level", 1), skill_graph[skill_id].get("hours_estimate", 0), skill_id))
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in children.get(current, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=lambda skill_id: (skill_graph[skill_id].get("level", 1), skill_graph[skill_id].get("hours_estimate", 0), skill_id))
    return ordered


def _resolve_target_skills(role: dict[str, Any], candidate_skills: list[str] | None = None) -> list[dict[str, Any]]:
    top_skills = role_top_skills(role, top_n=30)
    if not candidate_skills:
        return top_skills
    candidate_ids = normalize_known_skill_ids(candidate_skills)
    filtered = [row for row in top_skills if row["skill_id"] in candidate_ids]
    return filtered or top_skills


class GraphPathPlannerV2:
    @staticmethod
    def is_available() -> bool:
        return bool(load_roles()) and bool(load_skill_graph())

    @staticmethod
    def analyze_role(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str] | None = None,
        semantic_score: float = 0.0,
    ) -> RolePathAnalysis:
        roles = load_roles()
        role = roles.get(target_job_id)
        if role is None:
            normalized_candidates = normalize_known_skill_ids(candidate_skills or [])
            role = {
                "role_id": target_job_id,
                "role_name": target_job_id,
                "fine_role": target_job_id,
                "coarse_role": "custom",
                "skill_freq": {skill_name(skill_id): 1.0 for skill_id in normalized_candidates},
                "core_skill_ids": list(normalized_candidates),
                "required_skill_ids": list(normalized_candidates),
                "optional_skill_ids": [],
                "required_skills": [skill_name(skill_id) for skill_id in normalized_candidates],
            }

        skill_graph = load_skill_graph()
        resources = load_resources()
        adjacency, prereq_map = _build_skill_adjacency(skill_graph)
        target_skills = _resolve_target_skills(role, candidate_skills)
        target_ids = {row["skill_id"] for row in target_skills}
        known_ids = normalize_known_skill_ids(profile.skills or [])

        total_importance = max(sum(row["importance_score"] for row in target_skills), 1e-8)
        covered_rows = [row for row in target_skills if row["skill_id"] in known_ids]
        missing_rows = [row for row in target_skills if row["skill_id"] not in known_ids]

        selected_ids: set[str] = set()
        path_depths: list[int] = []
        for row in missing_rows:
            path = _astar_prereq_path(row["skill_id"], known_ids, skill_graph, adjacency)
            if not path:
                selected_ids.add(row["skill_id"])
                path_depths.append(1)
                continue
            selected_ids.update(skill_id for skill_id in path if skill_id not in known_ids)
            path_depths.append(max(1, len(path) - 1))

        ordered_ids = _ordered_learning_steps(selected_ids, prereq_map, skill_graph)
        total_hours = sum(int(skill_graph[skill_id].get("hours_estimate", 0)) for skill_id in ordered_ids)
        resource_reward = 0.0
        graph_reward = 0.0
        prereq_penalty_raw = 0.0
        for row, depth in zip(missing_rows, path_depths):
            skill = skill_graph[row["skill_id"]]
            importance = row["importance_score"] / total_importance
            difficulty = DIFFICULTY_VALUE.get(str(skill.get("difficulty", "intermediate")).lower(), 2.0) / 3.0
            level = float(skill.get("level", 1)) / 5.0
            prereq_penalty_raw += importance * min(1.0, 0.45 * difficulty + 0.35 * level + 0.20 * min(depth / 6.0, 1.0))
            resource_reward += importance * _teaches_quality(row["skill_id"])
            graph_reward += importance * _graph_reward(row["skill_id"], target_ids)

        coverage_score = sum(row["importance_score"] for row in covered_rows) / total_importance
        missing_penalty = sum(row["importance_score"] for row in missing_rows) / total_importance
        prereq_penalty = min(1.0, prereq_penalty_raw)
        hours_penalty = min(1.0, total_hours / 320.0)
        resource_reward = max(0.0, min(1.0, resource_reward))
        graph_reward = max(0.0, min(1.0, graph_reward if missing_rows else 1.0))

        role_score = (
            ROLE_SCORE_WEIGHTS["semantic"] * semantic_score
            + ROLE_SCORE_WEIGHTS["coverage"] * coverage_score
            + ROLE_SCORE_WEIGHTS["resource"] * resource_reward
            + ROLE_SCORE_WEIGHTS["graph"] * graph_reward
            - ROLE_SCORE_WEIGHTS["missing"] * missing_penalty
            - ROLE_SCORE_WEIGHTS["prereq"] * prereq_penalty
            - ROLE_SCORE_WEIGHTS["hours"] * hours_penalty
        )
        role_score = max(0.0, min(1.0, round(role_score, 4)))

        steps: list[LearningPathStep] = []
        for index, skill_id in enumerate(ordered_ids, start=1):
            skill = skill_graph[skill_id]
            reason = (
                f"importance={next((row['importance_score'] for row in target_skills if row['skill_id'] == skill_id), 0.0):.3f} "
                f"level={skill.get('level', 1)} "
                f"difficulty={skill.get('difficulty', 'intermediate')} "
                f"hours={skill.get('hours_estimate', 0)}"
            )
            steps.append(
                LearningPathStep(
                    step_no=index,
                    skill=skill["skill_name"],
                    reason=reason,
                    resources=resources.get(skill_id, []),
                )
            )

        path = LearningPath(
            target_job_id=target_job_id,
            total_steps=len(steps),
            total_estimated_hours=total_hours,
            score=max(0.0, min(1.0, round(0.45 * coverage_score + 0.30 * resource_reward + 0.25 * graph_reward - 0.20 * prereq_penalty - 0.15 * hours_penalty, 4))),
            steps=steps,
        )
        return RolePathAnalysis(
            role=role,
            semantic_score=round(semantic_score, 4),
            role_score=role_score,
            score_breakdown={
                "semantic": round(semantic_score, 4),
                "coverage": round(coverage_score, 4),
                "resource_reward": round(resource_reward, 4),
                "graph_reward": round(graph_reward, 4),
                "missing_penalty": round(missing_penalty, 4),
                "prereq_penalty": round(prereq_penalty, 4),
                "hours_penalty": round(hours_penalty, 4),
            },
            skill_gap=SkillGap(
                missing_skills=[skill_name(row["skill_id"]) for row in missing_rows],
                overlap_skills=[skill_name(row["skill_id"]) for row in covered_rows],
                optional_skills=[],
            ),
            path=path,
        )

    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
        strategy: str = "shortest",
    ) -> LearningPath:
        analysis = GraphPathPlannerV2.analyze_role(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
            semantic_score=0.0,
        )
        return analysis.path
