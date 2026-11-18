"""GraphPathPlannerV3 单元测试:闭包正确性、拓扑序、边界场景与真实数据冒烟。"""

from __future__ import annotations

import re

from app.schemas.domain import UserProfile
from app.services.graph_path_planner_v3 import (
    _prereq_closure,
    _topo_order,
    GraphPathPlannerV3,
    load_role_profiles,
    load_skill_graph,
    normalize_trend_momentum,
    ROLE_SCORE_WEIGHT_COVERAGE,
    ROLE_SCORE_WEIGHT_FEASIBILITY,
    ROLE_SCORE_WEIGHT_SEMANTIC,
    ROLE_SCORE_WEIGHT_TREND,
)


def _node(skill_id: str, prerequisites: list[str] | None = None, level: int = 1, hours: int = 10):
    return {
        "skill_id": skill_id,
        "skill_name": skill_id.upper(),
        "category": "test",
        "level": level,
        "hours_estimate": hours,
        "prerequisites": prerequisites or [],
    }


def test_prereq_closure_skips_known():
    graph = {
        "a": _node("a"),
        "b": _node("b", ["a"]),
        "c": _node("c", ["b"]),
    }
    closure = _prereq_closure({"c"}, {"b"}, graph)
    assert closure == {"c"}


def test_prereq_closure_shared_prereq_once():
    graph = {
        "a": _node("a"),
        "b": _node("b"),
        "c": _node("c", ["b"]),
        "d": _node("d", ["b"]),
    }
    closure = _prereq_closure({"c", "d"}, set(), graph)
    assert closure == {"b", "c", "d"}
    ordered = _topo_order(closure, graph)
    assert ordered.count("b") == 1
    assert "a" not in closure  # 无关根节点不进入闭包


def test_topo_order_prereqs_first():
    graph = {
        "linux": _node("linux", level=1, hours=20),
        "docker": _node("docker", ["linux"], level=2, hours=40),
        "kubernetes": _node("kubernetes", ["docker"], level=3, hours=60),
        "python": _node("python", level=1, hours=30),
        "ml": _node("ml", ["python"], level=4, hours=80),
    }
    selected = {"linux", "docker", "kubernetes", "python", "ml"}
    ordered = _topo_order(selected, graph)
    assert set(ordered) == selected
    position = {skill_id: index for index, skill_id in enumerate(ordered)}
    for skill_id, node in graph.items():
        for prereq_id in node["prerequisites"]:
            assert position[prereq_id] < position[skill_id]


def test_known_all_skills_empty_path():
    role = load_role_profiles()["role_011"]
    all_skill_names = (
        list(role.get("required_skills") or [])
        + list(role.get("core_skills") or [])
        + list(role.get("optional_skills") or [])
    )
    profile = UserProfile(user_id="u_all", skills=all_skill_names)
    analysis = GraphPathPlannerV3.analyze_role(
        profile=profile,
        target_job_id="role_011",
        semantic_score=0.9,
    )
    assert analysis.path.total_steps == 0
    assert analysis.path.steps == []
    assert analysis.path.score == 1.0
    assert analysis.skill_gap.missing_skills == []
    assert analysis.skill_gap.transferable in (None, [])


def test_real_data_smoke_rag_engineer():
    profile = UserProfile(user_id="u_smoke", skills=["Python", "SQL", "Docker"])
    analysis = GraphPathPlannerV3.analyze_role(
        profile=profile,
        target_job_id="role_011",
        semantic_score=0.8,
    )

    path = analysis.path
    assert path.total_steps > 0
    assert len(path.steps) == path.total_steps

    # 首步应是基础技能(v3 画像的 required/core 由加权频率导出,基础技能本身
    # 可能就是目标技能;断言降级为"首步属于低 level 基础",不再要求必是先修)
    graph = load_skill_graph()
    name_to_id = {node["skill_name"]: sid for sid, node in graph.items()}
    first_skill_id = name_to_id[path.steps[0].skill]
    assert float(graph.get(first_skill_id, {}).get("level", 1)) <= 2.0

    # 拓扑序:所有先修都排在自己前面
    position = {name_to_id[step.skill]: step.step_no for step in path.steps}
    for sid in position:
        for prereq_id in graph.get(sid, {}).get("prerequisites", []):
            if prereq_id in position:
                assert position[prereq_id] < position[sid]

    # reason 为中文自然语言,含 CJK 字符与数据(频率百分比/小时)
    cjk = re.compile(r"[\u4e00-\u9fff]")
    for step in path.steps:
        assert cjk.search(step.reason), step.reason

    assert analysis.formula_version == "v3"
    assert 0.0 <= analysis.role_score <= 1.0
    assert 0.0 <= path.score <= 1.0
    breakdown = analysis.score_breakdown
    assert set(breakdown) >= {"coverage_weighted", "semantic", "trend_momentum_norm",
                              "learning_feasibility"}
    expected = round(
        ROLE_SCORE_WEIGHT_COVERAGE * breakdown["coverage_weighted"]
        + ROLE_SCORE_WEIGHT_SEMANTIC * breakdown["semantic"]
        + ROLE_SCORE_WEIGHT_TREND * breakdown["trend_momentum_norm"]
        + ROLE_SCORE_WEIGHT_FEASIBILITY * breakdown["learning_feasibility"],
        4,
    )
    assert abs(analysis.role_score - expected) < 1e-3

    # trend_reward_score 的真趋势分归一化:0.5=持平,数据缺失也按 0.5;
    # 强动量岗(RAG Engineer momentum≈40)sigmoid 饱和到 1.0 是预期行为
    assert 0.0 < breakdown["trend_momentum_norm"] <= 1.0
    assert normalize_trend_momentum(None) == 0.5
    assert abs(normalize_trend_momentum(0.0) - 0.5) < 1e-6

    # SkillGap 增强:缺口/重叠/可选/可迁移都真实填充
    gap = analysis.skill_gap
    assert "Python" in gap.overlap_skills
    assert gap.missing_skills  # required 中缺失非空
    assert gap.optional_skills  # optional 中缺失非空(v2 恒为空)
    assert gap.transferable  # Docker→Kubernetes 等同 category 迁移对
