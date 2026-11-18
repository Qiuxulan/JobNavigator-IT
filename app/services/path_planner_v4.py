"""PathPlannerV4 — 打分选步的学习路径规划(learning_path_method_v2.md §2.2)。

与 v3(GraphPathPlannerV3,Kahn + (level, hours) 字典序拓扑)的区别只在**排序**:
拓扑约束仍是硬约束(先修必须在前),但每次从 ready set 弹出时按用户条件化打分函数选步:

    pick = argmax_{s ∈ ready} [
        0.30 · role_importance(s)            # 岗位 JD 频率归一(v4:按用户 candidate_skills 重加权)
      + 0.25 · zpd_match(s, L)               # Vygotsky 最近发展区:难度略高于当前水平 L 时得分最高
      + 0.20 · prereq_urgency(s)             # 先修紧迫度:解锁多少路径内后续技能(加权)
      + 0.15 · trend_momentum(s)             # 技能级趋势动量(skill_trend_panel_v3, sigmoid 归一)
      + 0.10 · transfer_bonus(s, known)      # 与已知技能的 graphsage_v2 embedding 余弦相似
      - 0.10 · hours_norm(s)                 # 偏好短平快,控制总时长
    ]
    每完成一步更新 L ← 0.8·L + 0.2·difficulty(s)(ZPD 随学习推进)

数据与兼容:
- 先修图读 data/gold/skill_prerequisite_v4.json(带 confidence,DFS 闭包 depth≤4、置信 ≥0.5);
- 岗位画像 / 资源挂载 / 可迁移技能 / reason 模板与 v3 复用(本模块直接 import v3 的纯函数);
- 返回 RolePathAnalysis / LearningPath 与 v3 逐字段一致,formula_version="v4";
- 灰度:PathPlannerService 按 JOBNAV_PATH_PLANNER=v4 切换,默认仍 v3。

个性化验证:同岗位不同 profile 的路径 Jaccard 距离应显著大于 v3(见 experiments/eval_path_v4.py)。
"""

from __future__ import annotations

import json
import math
import os
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.schemas.domain import (
    LearningPath,
    LearningPathStep,
    RolePathAnalysis,
    SkillGap,
    SkillTransferableItem,
    UserProfile,
)
from app.services.graph_path_planner_v3 import (
    FEASIBILITY_HOURS_CAP,
    ROLE_SCORE_WEIGHT_COVERAGE,
    ROLE_SCORE_WEIGHT_FEASIBILITY,
    ROLE_SCORE_WEIGHT_SEMANTIC,
    ROLE_SCORE_WEIGHT_TREND,
    TARGET_TOP_N,
    TRANSFERABLE_COVERAGE_WEIGHT,
    _find_transferable,
    _freq_phrase,
    _skill_hours,
    load_resources,
    load_role_profiles,
    normalize_trend_momentum,
)

ROOT = Path(__file__).parents[2]
GOLD_DIR = ROOT / "data" / "gold"
SKILL_GRAPH_V4_PATH = Path(
    os.environ.get("JOBNAV_SKILL_GRAPH_PATH_V4", str(GOLD_DIR / "skill_prerequisite_v4.json"))
)
SKILL_TREND_PANEL_PATH = GOLD_DIR / "skill_trend_panel_v3.json"
GRAPH_SAGE_DIR = ROOT / "models" / "graphsage_v2"

FORMULA_VERSION = "v4"
CLOSURE_MAX_DEPTH = 4
CLOSURE_MIN_CONFIDENCE = 0.5
# ZPD 剪枝:先修节点难度低于学习者水平 − ZPD_SKIP_GAP 时视为"显然已会的基础",
# 不排入路径也不再展开(个性化差异度的主要来源:水平越高路径越短越聚焦)。
# 以下 ZPD/权重参数经 experiments/tune_path_v4_params.py 坐标下降调优（2026-11，
# 约束 order_distance≥0.323、coverage≥0.90）：zpd_violation 0.1734→0.1514
ZPD_SKIP_GAP = 0.25

# ---------------------------------------------------------------------------
# 排序打分权重(learning_path_method_v2.md §2.2-3,做成顶部常量便于调参)
# ---------------------------------------------------------------------------
W_ROLE_IMPORTANCE = 0.30
W_ZPD = 0.35
W_PREREQ_URGENCY = 0.20
W_TREND = 0.15
W_TRANSFER = 0.10
W_HOURS = 0.10

ZPD_SIGMA = 0.08            # zpd_match 高斯宽度
ZPD_OFFSET = 0.20           # 最优难度 = 当前水平 + 0.20(略高难度)
ZPD_LEVEL_EMA = 0.3         # 每步后学习者水平向该步难度靠拢的比例
BASE_LEVEL_BY_YEARS = 10.0  # years_experience / 10 映射为起始难度水平,上限 0.8
TRANSFER_BASE_SAME_CATEGORY = 0.5   # 无 embedding 时同 category 已知技能的迁移保底分
TRANSFER_BASE_DEFAULT = 0.2
NON_TARGET_ROLE_IMPORTANCE = 0.15   # 非岗位目标的纯先修节点的岗位重要性保底


# ---------------------------------------------------------------------------
# v4 先修图(带 confidence)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_skill_graph_v4() -> dict[str, dict[str, Any]]:
    with SKILL_GRAPH_V4_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return {skill["skill_id"]: skill for skill in payload.get("skills", [])}


@lru_cache(maxsize=1)
def _edge_confidence_v4() -> dict[tuple[str, str], float]:
    """(prereq, skill) → confidence;无 prereq_detail 的旧格式边回退 0.6。"""
    conf: dict[tuple[str, str], float] = {}
    for sid, node in load_skill_graph_v4().items():
        detail = node.get("prereq_detail") or []
        if detail:
            for row in detail:
                conf[(row["skill_id"], sid)] = float(row.get("confidence", 0.6))
        else:
            for pre in node.get("prerequisites", []):
                conf[(pre, sid)] = 0.6
    return conf


@lru_cache(maxsize=1)
def _alias_to_id_v4() -> dict[str, str]:
    """v4 图节点别名表(295 节点,含 vocab 别名;覆盖 v3 缺失的 19 个新技能)。"""
    mapping: dict[str, str] = {}
    for skill_id, node in load_skill_graph_v4().items():
        mapping[skill_id] = skill_id
        mapping[str(node.get("skill_name", "")).strip().lower()] = skill_id
        for alias in node.get("aliases", []):
            mapping[str(alias).strip().lower()] = skill_id
    return mapping


@lru_cache(maxsize=1)
def _id_to_name_v4() -> dict[str, str]:
    return {sid: node.get("skill_name", sid) for sid, node in load_skill_graph_v4().items()}


def _normalize_v4(skills: Optional[list[str]]) -> set[str]:
    alias = _alias_to_id_v4()
    normalized: set[str] = set()
    for raw in skills or []:
        key = " ".join(str(raw).strip().lower().split())
        skill_id = alias.get(key) or alias.get(key.replace(" ", "-"))
        if skill_id:
            normalized.add(skill_id)
    return normalized


def _role_freq_v4(role: dict[str, Any]) -> dict[str, float]:
    alias = _alias_to_id_v4()
    freq: dict[str, float] = {}
    for raw_key, value in (role.get("skill_freq") or {}).items():
        key = str(raw_key).strip().lower()
        skill_id = alias.get(key) or alias.get(key.replace(" ", "-"))
        if skill_id:
            freq[skill_id] = max(freq.get(skill_id, 0.0), float(value))
    return freq


def skill_display_name_v4(skill_id: str) -> str:
    return _id_to_name_v4().get(skill_id, skill_id)


# ---------------------------------------------------------------------------
# 信号:技能级趋势 / embedding 迁移
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _skill_trend_norm() -> dict[str, float]:
    """技能级 trend_momentum(近 3 月份额均值 / 之前 3 月 − 1)→ sigmoid 归一 [0,1]。"""
    if not SKILL_TREND_PANEL_PATH.exists():
        return {}
    payload = json.loads(SKILL_TREND_PANEL_PATH.read_text(encoding="utf-8"))
    skills = payload.get("skills") or {}
    months = payload.get("months") or []
    if len(months) < 7:
        return {}
    out: dict[str, float] = {}
    for sid, entry in skills.items():
        monthly = {m["month"]: m for m in (entry.get("monthly") or [])}
        recent = [monthly.get(m, {}).get("share", 0.0) for m in months[-3:]]
        prior = [monthly.get(m, {}).get("share", 0.0) for m in months[-7:-3]]
        if sum(recent) <= 0 or sum(prior) <= 0:
            continue
        momentum = (sum(recent) / 3.0) / (sum(prior) / 3.0) - 1.0
        out[sid] = normalize_trend_momentum(momentum)
    return out


@lru_cache(maxsize=1)
def _skill_embeddings() -> dict[str, list[float]]:
    """graphsage_v2 技能 embedding(余弦相似度算迁移分);缺失时返回 {}。"""
    node_index_path = GRAPH_SAGE_DIR / "node_index.json"
    emb_path = GRAPH_SAGE_DIR / "embeddings.npy"
    if not node_index_path.exists() or not emb_path.exists():
        return {}
    try:
        import numpy as np

        node_index = json.loads(node_index_path.read_text(encoding="utf-8"))
        matrix = np.load(emb_path)
    except Exception:
        return {}
    out: dict[str, list[float]] = {}
    for key, idx in node_index.items():
        if key.startswith("skill:") and isinstance(idx, int) and 0 <= idx < len(matrix):
            out[key[len("skill:"):]] = matrix[idx].astype(float).tolist()
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _transfer_bonus(
    skill_id: str,
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
) -> float:
    """与已知技能的迁移分:embedding 余弦最大者映射到 [0,1];无 embedding 回退同 category 保底。"""
    embeddings = _skill_embeddings()
    if embeddings and skill_id in embeddings:
        best = 0.0
        for known in known_ids:
            vec = embeddings.get(known)
            if vec:
                best = max(best, _cosine(embeddings[skill_id], vec))
        if best > 0:
            return (best + 1.0) / 2.0
    node = skill_graph.get(skill_id, {})
    for known in known_ids:
        if skill_graph.get(known, {}).get("category") == node.get("category"):
            return TRANSFER_BASE_SAME_CATEGORY
    return TRANSFER_BASE_DEFAULT


# ---------------------------------------------------------------------------
# 先修闭包(带 confidence 与深度限制)
# ---------------------------------------------------------------------------

def _prereq_closure_v4(
    missing_ids: set[str],
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
    transferable_ids: Optional[set[str]] = None,
    learner_level: float = 0.0,
) -> tuple[set[str], set[str]]:
    """v3 闭包的 confidence/depth/ZPD 版。

    - 只沿 confidence ≥ CLOSURE_MIN_CONFIDENCE 的边走,深度 ≤ CLOSURE_MAX_DEPTH;
    - 已知技能:不加入,也不再展开;
    - 可迁移技能:不再向下展开先修(相近已知技能已提供基础);
    - ZPD 剪枝:先修节点(非目标)难度 < learner_level − ZPD_SKIP_GAP 时视为已会基础,
      加入 assumed_known(不排入路径)。返回 (closure, assumed_known)。
    """
    transferable_ids = transferable_ids or set()
    conf = _edge_confidence_v4()
    pct = _difficulty_percentiles()
    closure: set[str] = set()
    assumed_known: set[str] = set()
    stack: list[tuple[str, int]] = [(sid, 0) for sid in missing_ids]
    while stack:
        skill_id, depth = stack.pop()
        if skill_id in known_ids:
            continue
        if skill_id in transferable_ids and skill_id not in missing_ids:
            continue
        if skill_id in closure or skill_id in assumed_known:
            continue
        # ZPD 剪枝只对先修节点(深度 ≥1)生效;岗位目标技能必须保留。
        # learner_level 为难度百分位,剪掉百分位低于 水平−ZPD_SKIP_GAP 的显然基础。
        if (depth > 0 and learner_level > 0
                and pct.get(skill_id, 0.0) < learner_level - ZPD_SKIP_GAP):
            assumed_known.add(skill_id)
            continue
        closure.add(skill_id)
        if skill_id in transferable_ids or depth >= CLOSURE_MAX_DEPTH:
            continue
        node = skill_graph.get(skill_id)
        if node is None:
            continue
        for pre in node.get("prerequisites", []):
            if conf.get((pre, skill_id), 0.0) >= CLOSURE_MIN_CONFIDENCE:
                stack.append((pre, depth + 1))
            elif (pre, skill_id) not in conf:
                stack.append((pre, depth + 1))  # 无 confidence 信息(v3 兼容格式)默认放行
    return closure, assumed_known


# ---------------------------------------------------------------------------
# 打分拓扑排序(ZPD 条件化选步)
# ---------------------------------------------------------------------------

def _difficulty_of(skill_id: str, skill_graph: dict[str, dict[str, Any]]) -> float:
    node = skill_graph.get(skill_id, {})
    score = node.get("difficulty_score")
    if score is not None:
        return max(0.0, min(1.0, float(score)))
    return max(0.0, min(1.0, (float(node.get("level", 1)) - 1.0) / 3.0))


@lru_cache(maxsize=1)
def _difficulty_percentiles() -> dict[str, float]:
    """全部技能 difficulty 的百分位(0-1,均匀展开;难度打分本身压缩在低档,百分位让
    ZPD 匹配与基础剪枝在尺度上有区分度)。"""
    graph = load_skill_graph_v4()
    raw = {sid: _difficulty_of(sid, graph) for sid in graph}
    sorted_vals = sorted(raw.values())
    import bisect

    n = len(sorted_vals)
    return {sid: bisect.bisect_left(sorted_vals, v) / max(1, n - 1) for sid, v in raw.items()}


def _initial_learner_level(
    profile: UserProfile,
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
) -> float:
    """学习者初始水平(难度百分位):工作年限映射与已会技能百分位均值取大者(上限 0.85)。"""
    by_years = max(0.0, min(0.8, float(profile.years_experience or 0.0) / BASE_LEVEL_BY_YEARS))
    pct = _difficulty_percentiles()
    known_pcts = [pct.get(sid, 0.0) for sid in known_ids]
    by_skills = statistics.fmean(known_pcts) if known_pcts else 0.0
    return max(by_years, min(0.85, by_skills))


def _scored_topo_order(
    selected_ids: set[str],
    target_ids: list[str],
    freq: dict[str, float],
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
    profile: UserProfile,
) -> tuple[list[str], dict[str, dict[str, float]]]:
    """拓扑硬约束 + ready-set 打分选步。返回 (有序列表, 每步打分明细)。"""
    selected = set(selected_ids)
    target_set = set(target_ids)
    conf = _edge_confidence_v4()
    trend = _skill_trend_norm()

    indegree = {sid: 0 for sid in selected}
    children: dict[str, list[str]] = {sid: [] for sid in selected}
    prereqs_in_path: dict[str, list[str]] = {sid: [] for sid in selected}
    for sid in selected:
        for pre in skill_graph.get(sid, {}).get("prerequisites", []):
            if pre in selected:
                indegree[sid] += 1
                children[pre].append(sid)
                prereqs_in_path[sid].append(pre)

    # 紧迫度:s 的紧迫度 = 路径内依赖 s 的(目标加权的)后代数量,随深度衰减
    urgency: dict[str, float] = {sid: 0.0 for sid in selected}

    max_freq = max((freq.get(sid, 0.0) for sid in target_set), default=1.0) or 1e-8
    max_hours = max(
        (float(skill_graph.get(sid, {}).get("hours_estimate", 0) or 0) for sid in selected),
        default=1.0,
    ) or 1e-8
    diff_pct = _difficulty_percentiles()

    learner_level = _initial_learner_level(profile, known_ids, skill_graph)

    def score(sid: str) -> tuple[float, dict[str, float]]:
        node = skill_graph.get(sid, {})
        role_importance = (freq.get(sid, 0.0) / max_freq) if sid in target_set \
            else NON_TARGET_ROLE_IMPORTANCE
        difficulty = diff_pct.get(sid, _difficulty_of(sid, skill_graph))
        zpd = math.exp(-((difficulty - (learner_level + ZPD_OFFSET)) ** 2)
                       / (2 * ZPD_SIGMA ** 2))
        prereq_urgency = min(1.0, urgency.get(sid, 0.0) / 3.0)
        trend_score = trend.get(sid, 0.5)
        transfer = _transfer_bonus(sid, known_ids, skill_graph)
        hours_norm = float(node.get("hours_estimate", 0) or 0) / max_hours
        total = (W_ROLE_IMPORTANCE * role_importance
                 + W_ZPD * zpd
                 + W_PREREQ_URGENCY * prereq_urgency
                 + W_TREND * trend_score
                 + W_TRANSFER * transfer
                 - W_HOURS * hours_norm)
        return total, {
            "role_importance": round(role_importance, 4),
            "zpd": round(zpd, 4),
            "prereq_urgency": round(prereq_urgency, 4),
            "trend": round(trend_score, 4),
            "transfer": round(transfer, 4),
            "hours_norm": round(hours_norm, 4),
            "total": round(total, 4),
        }

    ready = [sid for sid, degree in indegree.items() if degree == 0]
    ordered: list[str] = []
    breakdown: dict[str, dict[str, float]] = {}
    while ready:
        scored = [(score(sid)[0], sid) for sid in ready]
        best_total, current = max(scored, key=lambda x: (x[0], -ready.index(x[1])))
        breakdown[current] = score(current)[1]
        ready.remove(current)
        ordered.append(current)
        # ZPD:完成一步后水平向该步难度靠拢
        breakdown[current]["learner_level_before"] = round(learner_level, 4)
        learner_level = ((1 - ZPD_LEVEL_EMA) * learner_level
                         + ZPD_LEVEL_EMA * _difficulty_of(current, skill_graph))
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return ordered, breakdown


# ---------------------------------------------------------------------------
# reason 生成(数据驱动,含 confidence)
# ---------------------------------------------------------------------------

def _build_reason_v4(
    skill_id: str,
    *,
    is_target: bool,
    transferable_from: Optional[str],
    prereqs_in_path: list[str],
    dependents: list[str],
    freq: dict[str, float],
    hours: int,
    zpd: Optional[float],
    skill_graph: dict[str, dict[str, Any]],
) -> str:
    name = skill_display_name_v4(skill_id)
    parts: list[str] = []
    if is_target:
        freq_phrase = _freq_phrase(skill_id, freq)
        if freq_phrase:
            parts.append(freq_phrase)
        if prereqs_in_path:
            conf = _edge_confidence_v4()
            items = []
            for p in prereqs_in_path[:3]:
                c = conf.get((p, skill_id))
                items.append(f"「{skill_display_name_v4(p)}」"
                             + (f"(置信度{c:.2f})" if c is not None else ""))
            parts.append(f"需要先掌握直接先修 {'、'.join(items)}")
        if transferable_from:
            parts.append(
                f"已掌握「{skill_display_name_v4(transferable_from)}」,同属 "
                f"「{skill_graph.get(skill_id, {}).get('category', '')}」方向,可迁移学习"
            )
    else:
        if dependents:
            dep_names = "、".join(f"「{skill_display_name_v4(d)}」" for d in dependents[:3])
            parts.append(f"是 {dep_names} 的直接先修,优先解锁后续技能")
        freq_phrase = _freq_phrase(skill_id, freq)
        if freq_phrase:
            parts.append(freq_phrase)
    if zpd is not None:
        if zpd >= 0.7:
            parts.append("难度略高于你当前水平,正处最近发展区,学习收益最大")
        elif zpd >= 0.4:
            parts.append("难度与你的当前水平基本匹配")
    if hours > 0:
        parts.append(f"预计 {hours} 小时")
    if not parts:
        parts.append("补齐岗位所需的基础技能")
    return ";".join(parts) + "。"


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class PathPlannerV4:
    @staticmethod
    def is_available() -> bool:
        return (bool(load_role_profiles()) and bool(load_skill_graph_v4())
                and SKILL_GRAPH_V4_PATH.exists())

    @staticmethod
    def analyze_role(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: Optional[list[str]] = None,
        semantic_score: float = 0.0,
    ) -> RolePathAnalysis:
        roles = load_role_profiles()
        role = roles.get(target_job_id)
        skill_graph = load_skill_graph_v4()
        resources = load_resources()
        if role is None:
            candidate_ids = _normalize_v4(candidate_skills or [])
            if not candidate_ids:
                raise ValueError(f"未知岗位 {target_job_id},且未提供可构造画像的 candidate_skills")
            role = {
                "role_id": target_job_id,
                "role_name": target_job_id,
                "fine_role": target_job_id,
                "coarse_role": "custom",
                "skill_freq": {sid: 1.0 for sid in candidate_ids},
                "core_skill_ids": list(candidate_ids),
                "required_skill_ids": list(candidate_ids),
                "optional_skill_ids": [],
                "required_skills": [skill_display_name_v4(sid) for sid in candidate_ids],
            }

        freq = _role_freq_v4(role)
        # v4:目标集按用户 candidate_skills 重加权(个性化入口,与 v3 的差异点之一)
        if candidate_skills:
            candidate_ids = _normalize_v4(candidate_skills)
            if candidate_ids:
                freq = {sid: v * (1.5 if sid in candidate_ids else 1.0)
                        for sid, v in freq.items()}
        # 复用 v3 的 _resolve_targets 需要 v3 的 alias 映射,这里用 v4 版重写
        targets = _resolve_targets_v4(role, candidate_skills, skill_graph)
        if not targets:
            raise ValueError(f"岗位 {target_job_id} 没有可映射到技能图的目标技能")

        required_ids = set(role.get("required_skill_ids") or [])
        optional_ids = set(role.get("optional_skill_ids") or [])
        core_ids = set(role.get("core_skill_ids") or [])
        known_ids = _normalize_v4(profile.skills or [])

        transferable = _find_transferable(known_ids, targets, skill_graph)
        transferable_ids = set(transferable.keys())

        covered_ids = {sid for sid in targets if sid in known_ids}
        missing_ids = {sid for sid in targets if sid not in known_ids}
        missing_required = sorted(
            (sid for sid in missing_ids if sid in required_ids or sid in core_ids),
            key=lambda sid: (-freq.get(sid, 0.0), sid),
        )
        missing_optional = sorted(
            (sid for sid in optional_ids
             if sid not in known_ids and sid not in required_ids and sid not in core_ids
             and sid in skill_graph),
            key=lambda sid: (-freq.get(sid, 0.0), sid),
        )[:10]

        learner_level = _initial_learner_level(profile, known_ids, skill_graph)
        closure, assumed_known = _prereq_closure_v4(
            missing_ids, known_ids, skill_graph, transferable_ids, learner_level
        )
        ordered_ids, breakdown = _scored_topo_order(
            closure, targets, freq, known_ids, skill_graph, profile
        )
        hours_by_skill = {
            sid: _skill_hours(sid, skill_graph, transferable_ids) for sid in ordered_ids
        }
        total_hours = sum(hours_by_skill.values())

        dependents_of: dict[str, list[str]] = {sid: [] for sid in ordered_ids}
        prereq_map: dict[str, list[str]] = {sid: [] for sid in ordered_ids}
        for sid in ordered_ids:
            for pre in skill_graph.get(sid, {}).get("prerequisites", []):
                if pre in closure:
                    prereq_map.setdefault(sid, []).append(pre)
                    dependents_of.setdefault(pre, []).append(sid)

        steps: list[LearningPathStep] = []
        for index, skill_id in enumerate(ordered_ids, start=1):
            reason = _build_reason_v4(
                skill_id,
                is_target=skill_id in missing_ids,
                transferable_from=transferable.get(skill_id),
                prereqs_in_path=prereq_map.get(skill_id, []),
                dependents=dependents_of.get(skill_id, []),
                freq=freq,
                hours=hours_by_skill[skill_id],
                zpd=breakdown.get(skill_id, {}).get("zpd"),
                skill_graph=skill_graph,
            )
            steps.append(
                LearningPathStep(
                    step_no=index,
                    skill=skill_display_name_v4(skill_id),
                    reason=reason,
                    resources=resources.get(skill_id, []),
                )
            )

        # 评分公式与 v3 一致(保证 v3/v4 可比),formula_version 标 v4
        target_weight = {sid: freq.get(sid, 1.0) for sid in targets}
        total_weight = sum(target_weight.values()) or 1e-8
        covered_weight = sum(target_weight[sid] for sid in covered_ids)
        covered_weight += TRANSFERABLE_COVERAGE_WEIGHT * sum(
            target_weight[sid] for sid in transferable_ids
        )
        coverage_weighted = covered_weight / total_weight
        learning_feasibility = 1.0 - min(1.0, total_hours / FEASIBILITY_HOURS_CAP)
        trend_momentum = role.get("trend_momentum")
        trend_norm = normalize_trend_momentum(trend_momentum)
        role_score = (
            ROLE_SCORE_WEIGHT_COVERAGE * coverage_weighted
            + ROLE_SCORE_WEIGHT_SEMANTIC * semantic_score
            + ROLE_SCORE_WEIGHT_TREND * trend_norm
            + ROLE_SCORE_WEIGHT_FEASIBILITY * learning_feasibility
        )
        role_score = max(0.0, min(1.0, round(role_score, 4)))
        path_score = max(0.0, min(1.0, round(learning_feasibility, 4)))

        path = LearningPath(
            target_job_id=target_job_id,
            total_steps=len(steps),
            total_estimated_hours=total_hours,
            score=path_score,
            steps=steps,
        )
        return RolePathAnalysis(
            role=role,
            semantic_score=round(semantic_score, 4),
            role_score=role_score,
            score_breakdown={
                "coverage_weighted": round(coverage_weighted, 4),
                "semantic": round(semantic_score, 4),
                **({"trend_momentum": round(float(trend_momentum), 4)}
                   if trend_momentum is not None else {}),
                "trend_momentum_norm": round(trend_norm, 4),
                "learning_feasibility": round(learning_feasibility, 4),
                "role_score": role_score,
                "total_hours": float(total_hours),
                "w_role_importance": W_ROLE_IMPORTANCE,
                "w_zpd": W_ZPD,
                "w_prereq_urgency": W_PREREQ_URGENCY,
                "w_trend": W_TREND,
                "w_transfer": W_TRANSFER,
                "w_hours": W_HOURS,
                "assumed_known_count": float(len(assumed_known)),
            },
            skill_gap=SkillGap(
                missing_skills=[skill_display_name_v4(sid) for sid in missing_required],
                overlap_skills=[skill_display_name_v4(sid) for sid in covered_ids],
                optional_skills=[skill_display_name_v4(sid) for sid in missing_optional],
                transferable=[
                    SkillTransferableItem(
                        known_skill=skill_display_name_v4(known_id),
                        target_skill=skill_display_name_v4(target_id),
                        category=skill_graph.get(target_id, {}).get("category"),
                    )
                    for target_id, known_id in sorted(transferable.items())
                ],
            ),
            path=path,
            formula_version=FORMULA_VERSION,
        )

    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: Optional[list[str]] = None,
    ) -> LearningPath:
        return PathPlannerV4.analyze_role(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
            semantic_score=0.0,
        ).path


# ---------------------------------------------------------------------------
# 目标集解析(v4 alias 版,逻辑同 v3._resolve_targets)
# ---------------------------------------------------------------------------

def _role_target_ids_v4(role: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for key in ("required_skill_ids", "core_skill_ids"):
        for skill_id in role.get(key) or []:
            if skill_id not in seen:
                seen.add(skill_id)
                ordered.append(skill_id)
    return ordered


def _resolve_targets_v4(
    role: dict[str, Any],
    candidate_skills: Optional[list[str]],
    skill_graph: dict[str, dict[str, Any]],
) -> list[str]:
    freq = _role_freq_v4(role)
    targets = [sid for sid in _role_target_ids_v4(role) if sid in skill_graph]
    if not targets and freq:
        targets = [sid for sid in freq if sid in skill_graph]
    targets.sort(key=lambda sid: (-freq.get(sid, 0.0), sid))
    targets = targets[:TARGET_TOP_N]
    if candidate_skills:
        candidate_ids = _normalize_v4(candidate_skills)
        filtered = [sid for sid in targets if sid in candidate_ids]
        if filtered:
            targets = filtered
    return targets
