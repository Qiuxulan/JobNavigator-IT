"""GraphPathPlannerV3 — 基于真实岗位画像与 v3 先修 DAG 的学习路径规划。

相比 v2 的修复点(病灶 → 对策):

1. 误用 A* → 先修闭包 + Kahn 拓扑排序。
   先修图是 DAG 且先修关系是合取(所有先修都必须学),不存在"选路"问题:
   对缺失技能沿 prerequisites 递归展开(共享先修只学一次,已知/可迁移技能剔除),
   再对 induced 子图做 Kahn 拓扑排序,ready 队列按 (level, hours_estimate) 出队。
   这是完整正确的算法,不需要启发式搜索。

2. 双重计分 → 单一公式(v3.1,2026-10-19 引入真实趋势动量):
       role_score = w_cov * coverage_weighted
                  + w_sem * semantic
                  + w_trend * trend_momentum_norm
                  + w_feas * learning_feasibility
       (权重:experiments/tune_ranking_weights.py 在 eval_set_v1+v2 合并 58 例上
        做四维网格扫描(步长 0.05,和=1,w_sem∈[0.3,0.7])按 NDCG@5 选优;
        对照基线为旧线上权重 0.15/0.80/0/0.05,详见 reports/eval/matching_v3_eval.json)
   - coverage_weighted = Σ covered skill_freq / Σ target skill_freq
     (目标岗位 JD 频率加权;可迁移技能算"半个已知",按 0.5 权重计入 covered)
   - semantic            : 外部传入的向量召回分
   - trend_momentum_norm : 岗位 trend_momentum(近 3 月 JD 份额均值 / 之前 3 月 - 1,
     来自 role_profiles_v3)经 sigmoid(k=1.5)归一化到 (0,1),0.5=持平;
     momentum 缺失按 0.5(持平)处理,不奖不罚
   - learning_feasibility = 1 - min(1, total_hours / 600)
     (600h ≈ 6 个月业余学习,是可行性拐点;可迁移技能按 ×0.6 成本计入 total_hours)
   path.score = 1 - min(1, total_hours / 600),是路径本身的可行性分,
   与 role_score(岗位匹配分)职责分开,不再混用两套公式。
   score_breakdown 附带 formula_version="v3"。

3. reason 字段输出中文自然语言解释,数据驱动:
   先修关系来自 v3 图,岗位出现频率来自 role_profiles_v3(近期加权),
   时长来自图节点。

4. SkillGap.optional_skills 真实填充(optional 中缺失),transferable 记录
   已知技能 → 可迁移目标技能(同 category 且 level 差 ≤ 1)。
   strategy 参数为 v2 死代码,v3 的 generate 不再接受。

5. 数据源切换为重建后的真实画像:
   role_profiles_v3.json(99 岗,skill_freq 基于 12.6 万 v3 JD 近期加权,
   附 trend_momentum/薪资/remote/seniority/月度序列;零 JD 岗回退岗位目录)、
   skill_prerequisite_v3.json(276 节点 347 边)、learning_resources_v5.json（2006 条，含章节结构与死链清洗）
   (1576 条,平铺格式,加载时按 skill_ids 分组取 quality_score top3)。
   GraphSAGE/数据库 embedding 整套逻辑删除 —— v3 评分不再需要。
"""

from __future__ import annotations

import heapq
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.schemas.domain import (
    LearningPath,
    LearningPathStep,
    LearningResource,
    RolePathAnalysis,
    SkillGap,
    SkillTransferableItem,
    UserProfile,
)

ROOT = Path(__file__).parents[2]
GOLD_DIR = ROOT / "data" / "gold"

ROLE_PROFILES_PATH = Path(
    os.environ.get("JOBNAV_ROLE_PROFILES_PATH", str(GOLD_DIR / "role_profiles_v3.json"))
)
ROLE_PROFILES_FALLBACK_PATHS = [
    GOLD_DIR / "role_profiles_v2.json",
    GOLD_DIR / "fine_grained_roles_v1.json",
]
SKILL_GRAPH_PATH = Path(
    os.environ.get("JOBNAV_SKILL_GRAPH_PATH", str(GOLD_DIR / "skill_prerequisite_v3.json"))
)
RESOURCES_PATH = Path(
    os.environ.get("JOBNAV_RESOURCES_PATH", str(GOLD_DIR / "learning_resources_v5.json"))
)
SKILL_VOCAB_V2_PATH = GOLD_DIR / "skill_vocab_v2.json"

FORMULA_VERSION = "v3"
TARGET_TOP_N = 30
FEASIBILITY_HOURS_CAP = 600.0  # ≈ 6 个月业余学习
TRANSFERABLE_LEVEL_GAP = 1
TRANSFERABLE_COST_FACTOR = 0.6
TRANSFERABLE_COVERAGE_WEIGHT = 0.5

# 2026-10-19 四维调参来源见模块 docstring 第 2 节(experiments/tune_ranking_weights.py,
# eval_set_v1+v2 合并 58 例网格扫描,步长 0.05,和=1,w_sem∈[0.3,0.7];
# 最优 NDCG@5=0.7026 / Hit@1=0.8103,基线(0.15/0.80/0/0.05)0.6654/0.7241,
# 报告 reports/eval/matching_v3_eval.json。注意:该网格下 w_feas 最优为 0,
# 可行性不再参与排名,但仍计算并展示(path_cost_score / LearningPath.score)。
ROLE_SCORE_WEIGHT_COVERAGE = 0.15
ROLE_SCORE_WEIGHT_SEMANTIC = 0.70
ROLE_SCORE_WEIGHT_TREND = 0.15
ROLE_SCORE_WEIGHT_FEASIBILITY = 0.0

TREND_SIGMOID_K = 1.5  # momentum → [0,1] 的 sigmoid 斜率;m=0(持平)→0.5


def normalize_trend_momentum(momentum: Optional[float]) -> float:
    """岗位趋势动量 → [0,1] 奖励分:0.5=持平,>0.5 上升,<0.5 下降。

    momentum = 近 3 月 JD 份额均值 / 之前 3 月 - 1(role_profiles_v3.trend_momentum),
    范围无界(RAG Engineer 可到 40),用 sigmoid 压到 (0,1);
    数据不足(momentum=None)按持平 0.5 处理。
    """
    if momentum is None:
        return 0.5
    try:
        m = float(momentum)
    except (TypeError, ValueError):
        return 0.5
    return 1.0 / (1.0 + math.exp(-TREND_SIGMOID_K * m))

_DIFFICULTY_LEVELS = {"beginner", "intermediate", "advanced"}


@lru_cache(maxsize=1)
def _load_roles_catalog() -> dict[str, dict[str, Any]]:
    """岗位目录(fine_grained_roles v3→v2→v1):给零/低 JD 画像岗补技能清单。"""
    for name in ("fine_grained_roles_v3.json", "fine_grained_roles_v2.json",
                 "fine_grained_roles_v1.json"):
        path = GOLD_DIR / name
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            roles = payload if isinstance(payload, list) else payload.get("roles", [])
            return {r["role_id"]: r for r in roles}
    return {}


@lru_cache(maxsize=1)
def load_role_profiles() -> dict[str, dict[str, Any]]:
    """岗位画像:默认 v3(99 岗真实画像);缺文件按 v2 -> v1 回退。

    v3 中零映射 JD 的岗(如 role_014)画像技能为空,回退用岗位目录的
    required/core/optional 清单 + 合成频率(required=1.0/core=1.05),
    保证规划器对全岗可用;有真实画像的岗不受影响。
    """
    profiles: dict[str, dict[str, Any]] = {}
    for path in [ROLE_PROFILES_PATH, *ROLE_PROFILES_FALLBACK_PATHS]:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                roles = payload.get("roles", list(payload.values()))
            else:
                roles = payload
            profiles = {role["role_id"]: role for role in roles}
            break

    catalog = _load_roles_catalog()
    for rid, role in profiles.items():
        cat = catalog.get(rid)
        if not cat:
            continue
        if not role.get("required_skill_ids") and not role.get("core_skill_ids"):
            for key in ("required_skill_ids", "core_skill_ids", "optional_skill_ids",
                        "required_skills", "core_skills", "optional_skills"):
                role[key] = cat.get(key) or []
            if not role.get("skill_freq"):
                freq: dict[str, float] = {}
                for sid in role.get("required_skill_ids") or []:
                    freq[sid] = max(freq.get(sid, 0.0), 1.0)
                for sid in role.get("core_skill_ids") or []:
                    freq[sid] = max(freq.get(sid, 0.0), 1.05)
                for sid in role.get("optional_skill_ids") or []:
                    freq[sid] = max(freq.get(sid, 0.0), 0.65)
                role["skill_freq"] = freq
    return profiles


@lru_cache(maxsize=1)
def load_skill_graph() -> dict[str, dict[str, Any]]:
    with SKILL_GRAPH_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return {skill["skill_id"]: skill for skill in payload.get("skills", [])}


@lru_cache(maxsize=1)
def _load_vocab_names() -> dict[str, str]:
    if SKILL_VOCAB_V2_PATH.exists():
        vocab = json.loads(SKILL_VOCAB_V2_PATH.read_text(encoding="utf-8"))
        return dict(vocab.get("id_to_name", {}))
    return {}


@lru_cache(maxsize=1)
def _alias_to_id() -> dict[str, str]:
    """v3 图节点自身的别名表(skill_name + aliases + skill_id)。"""
    mapping: dict[str, str] = {}
    for skill_id, node in load_skill_graph().items():
        mapping[skill_id] = skill_id
        mapping[str(node.get("skill_name", "")).strip().lower()] = skill_id
        for alias in node.get("aliases", []):
            mapping[str(alias).strip().lower()] = skill_id
    return mapping


@lru_cache(maxsize=1)
def _id_to_name() -> dict[str, str]:
    names = {sid: node.get("skill_name", sid) for sid, node in load_skill_graph().items()}
    for sid, name in _load_vocab_names().items():
        names.setdefault(sid, name)
    return names


def normalize_skill_ids(skills: Optional[list[str]]) -> set[str]:
    """profile/candidate 技能写法 → v3 图 skill_id 集合。"""
    alias = _alias_to_id()
    normalized: set[str] = set()
    for raw in skills or []:
        key = " ".join(str(raw).strip().lower().split())
        skill_id = alias.get(key) or alias.get(key.replace(" ", "-"))
        if skill_id:
            normalized.add(skill_id)
    return normalized


def skill_display_name(skill_id: str) -> str:
    return _id_to_name().get(skill_id, skill_id)


# ---------------------------------------------------------------------------
# 路径算法:先修闭包 + Kahn 拓扑排序
# ---------------------------------------------------------------------------

def _prereq_closure(
    missing_ids: set[str],
    known_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
    transferable_ids: Optional[set[str]] = None,
) -> set[str]:
    """缺失技能的先修闭包(合取展开)。

    - 已知技能:不加入,也不再展开(已经会了)。
    - 可迁移技能:若是缺失目标本身则保留在闭包中(由调用方按 ×0.6 成本学习);
      若只是先修节点则剔除 —— 同 category 且 level 相近的已知技能已提供基础。
    - 共享先修只出现一次(集合语义)。
    """
    transferable_ids = transferable_ids or set()
    closure: set[str] = set()
    stack = list(missing_ids)
    while stack:
        skill_id = stack.pop()
        if skill_id in known_ids:
            continue
        if skill_id in transferable_ids and skill_id not in missing_ids:
            continue
        if skill_id in closure:
            continue
        closure.add(skill_id)
        node = skill_graph.get(skill_id)
        if node is None:
            continue
        if skill_id in transferable_ids:
            # 可迁移目标:相近已知技能提供基础,不再向下展开先修。
            continue
        stack.extend(node.get("prerequisites", []))
    return closure


def _topo_order(
    selected_ids: set[str],
    skill_graph: dict[str, dict[str, Any]],
) -> list[str]:
    """Kahn 拓扑排序;ready 队列按 (level, hours_estimate, skill_id) 出队。"""
    def sort_key(skill_id: str) -> tuple[float, float, str]:
        node = skill_graph.get(skill_id, {})
        return (
            float(node.get("level", 1)),
            float(node.get("hours_estimate", 0)),
            skill_id,
        )

    selected = set(selected_ids)
    indegree = {skill_id: 0 for skill_id in selected}
    children: dict[str, list[str]] = {skill_id: [] for skill_id in selected}
    for skill_id in selected:
        for prereq_id in skill_graph.get(skill_id, {}).get("prerequisites", []):
            if prereq_id in selected:
                indegree[skill_id] += 1
                children[prereq_id].append(skill_id)

    ready = [(sort_key(skill_id), skill_id) for skill_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        _, current = heapq.heappop(ready)
        ordered.append(current)
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (sort_key(child), child))
    return ordered


def _skill_hours(skill_id: str, skill_graph: dict[str, dict[str, Any]], transferable_ids: set[str]) -> int:
    hours = float(skill_graph.get(skill_id, {}).get("hours_estimate", 0) or 0)
    if skill_id in transferable_ids:
        hours *= TRANSFERABLE_COST_FACTOR
    return int(round(hours))


# ---------------------------------------------------------------------------
# 资源
# ---------------------------------------------------------------------------

def _to_learning_resource(raw: dict[str, Any]) -> LearningResource:
    difficulty = raw.get("difficulty")
    difficulty = difficulty.lower() if isinstance(difficulty, str) else None
    raw_level = raw.get("level")
    raw_level = raw_level.lower() if isinstance(raw_level, str) else None
    level_value = difficulty or raw_level
    level = level_value if level_value in _DIFFICULTY_LEVELS else "beginner"
    return LearningResource(
        resource_id=str(raw.get("resource_id") or raw.get("url") or ""),
        title=str(raw.get("title", "")),
        url=str(raw.get("url", "")),
        provider=str(raw.get("provider") or raw.get("source") or ""),
        level=level,
        difficulty=difficulty or raw_level,
        hours_estimate=raw.get("hours_estimate") or raw.get("duration_hours"),
        language=raw.get("language"),
        quality_score=raw.get("quality_score"),
        source=raw.get("source"),
    )


@lru_cache(maxsize=1)
def load_resources() -> dict[str, list[LearningResource]]:
    """载入学习资源。兼容 v3（{resources: {skill_id: [..]}}）与
    v4（{resources: [..]} 平铺，每条带 skill_ids）两种格式。"""
    if not RESOURCES_PATH.exists():
        return {}
    payload = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    raw_resources = payload.get("resources") or {}
    resource_map: dict[str, list[LearningResource]] = {}
    if isinstance(raw_resources, dict):
        for skill_id, items in raw_resources.items():
            resources = [_to_learning_resource(item) for item in items]
            resources.sort(key=lambda r: (r.quality_score or 0.0), reverse=True)
            resource_map[skill_id] = resources[:3]
    else:
        grouped: dict[str, list[LearningResource]] = {}
        for item in raw_resources:
            resource = _to_learning_resource(item)
            for skill_id in item.get("skill_ids") or []:
                grouped.setdefault(skill_id, []).append(resource)
        for skill_id, resources in grouped.items():
            resources.sort(key=lambda r: (r.quality_score or 0.0), reverse=True)
            resource_map[skill_id] = resources[:3]
    return resource_map


# ---------------------------------------------------------------------------
# 岗位目标集
# ---------------------------------------------------------------------------

def _role_freq(role: dict[str, Any]) -> dict[str, float]:
    """岗位 skill_freq(键归一化到 v3 skill_id)。v1 回退时键可能是技能名。"""
    alias = _alias_to_id()
    freq: dict[str, float] = {}
    for raw_key, value in (role.get("skill_freq") or {}).items():
        key = str(raw_key).strip().lower()
        skill_id = alias.get(key) or alias.get(key.replace(" ", "-"))
        if skill_id:
            freq[skill_id] = max(freq.get(skill_id, 0.0), float(value))
    return freq


def _role_target_ids(role: dict[str, Any]) -> list[str]:
    """目标技能集 = required + core,保持岗位给出的优先级顺序,去重。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for key in ("required_skill_ids", "core_skill_ids"):
        for skill_id in role.get(key) or []:
            if skill_id not in seen:
                seen.add(skill_id)
                ordered.append(skill_id)
    return ordered


def _resolve_targets(
    role: dict[str, Any],
    candidate_skills: Optional[list[str]],
    skill_graph: dict[str, dict[str, Any]],
) -> list[str]:
    freq = _role_freq(role)
    targets = [sid for sid in _role_target_ids(role) if sid in skill_graph]
    if not targets and freq:
        # required/core 都映射不进技能图(如部分设计岗)时,回退用画像高频技能
        targets = [sid for sid in freq if sid in skill_graph]
    targets.sort(key=lambda sid: (-freq.get(sid, 0.0), sid))
    targets = targets[:TARGET_TOP_N]
    if candidate_skills:
        candidate_ids = normalize_skill_ids(candidate_skills)
        filtered = [sid for sid in targets if sid in candidate_ids]
        if filtered:
            targets = filtered
    return targets


# ---------------------------------------------------------------------------
# 可迁移技能
# ---------------------------------------------------------------------------

def _find_transferable(
    known_ids: set[str],
    target_ids: list[str],
    skill_graph: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """已知技能 → 可迁移目标技能(同 category 且 level 差 ≤ 1)。"""
    transferable: dict[str, str] = {}
    missing_targets = [sid for sid in target_ids if sid not in known_ids]
    for target_id in missing_targets:
        target = skill_graph.get(target_id)
        if not target:
            continue
        for known_id in known_ids:
            known = skill_graph.get(known_id)
            if not known:
                continue
            if known.get("category") != target.get("category"):
                continue
            if abs(float(known.get("level", 1)) - float(target.get("level", 1))) > TRANSFERABLE_LEVEL_GAP:
                continue
            transferable[target_id] = known_id
            break
    return transferable


# ---------------------------------------------------------------------------
# reason 生成(中文自然语言,数据驱动)
# ---------------------------------------------------------------------------

def _freq_phrase(skill_id: str, freq: dict[str, float]) -> str:
    value = freq.get(skill_id)
    if value is None:
        return ""
    return f"在目标岗位 {value * 100:.0f}% 的 JD 中出现"


def _build_reason(
    skill_id: str,
    *,
    is_target: bool,
    transferable_from: Optional[str],
    prereqs_in_path: list[str],
    dependents: list[str],
    freq: dict[str, float],
    hours: int,
    skill_graph: dict[str, dict[str, Any]],
) -> str:
    name = skill_display_name(skill_id)
    parts: list[str] = []

    if is_target:
        freq_phrase = _freq_phrase(skill_id, freq)
        if freq_phrase:
            parts.append(freq_phrase)
        if prereqs_in_path:
            prereq_names = "、".join(f"「{skill_display_name(p)}」" for p in prereqs_in_path)
            parts.append(f"需要先掌握直接先修 {prereq_names}")
        if transferable_from:
            parts.append(
                f"已掌握「{skill_display_name(transferable_from)}」,同属 "
                f"「{skill_graph.get(skill_id, {}).get('category', '')}」方向,可迁移学习"
            )
    else:
        if dependents:
            dep_names = "、".join(f"「{skill_display_name(d)}」" for d in dependents[:3])
            parts.append(f"是 {dep_names} 的直接先修")
        freq_phrase = _freq_phrase(skill_id, freq)
        if freq_phrase:
            parts.append(freq_phrase)

    if hours > 0:
        parts.append(f"预计 {hours} 小时")
    if not parts:
        parts.append("补齐岗位所需的基础技能")
    return ";".join(parts) + "。"


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class GraphPathPlannerV3:
    @staticmethod
    def is_available() -> bool:
        return bool(load_role_profiles()) and bool(load_skill_graph())

    @staticmethod
    def analyze_role(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: Optional[list[str]] = None,
        semantic_score: float = 0.0,
    ) -> RolePathAnalysis:
        roles = load_role_profiles()
        role = roles.get(target_job_id)
        if role is None:
            candidate_ids = normalize_skill_ids(candidate_skills or [])
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
                "required_skills": [skill_display_name(sid) for sid in candidate_ids],
            }

        skill_graph = load_skill_graph()
        resources = load_resources()
        freq = _role_freq(role)
        target_ids = _resolve_targets(role, candidate_skills, skill_graph)
        if not target_ids:
            raise ValueError(f"岗位 {target_job_id} 没有可映射到技能图的目标技能")

        required_ids = set(role.get("required_skill_ids") or [])
        optional_ids = set(role.get("optional_skill_ids") or [])
        core_ids = set(role.get("core_skill_ids") or [])
        known_ids = normalize_skill_ids(profile.skills or [])

        transferable = _find_transferable(known_ids, target_ids, skill_graph)
        transferable_ids = set(transferable.keys())

        covered_ids = {sid for sid in target_ids if sid in known_ids}
        missing_ids = {sid for sid in target_ids if sid not in known_ids}
        missing_required = sorted(
            (sid for sid in missing_ids if sid in required_ids or sid in core_ids),
            key=lambda sid: (-freq.get(sid, 0.0), sid),
        )
        missing_optional = sorted(
            (
                sid
                for sid in optional_ids
                if sid not in known_ids
                and sid not in required_ids
                and sid not in core_ids
                and sid in skill_graph
            ),
            key=lambda sid: (-freq.get(sid, 0.0), sid),
        )[:10]

        # 先修闭包(共享先修只学一次;已知/可迁移先修剔除)+ Kahn 拓扑排序
        closure = _prereq_closure(missing_ids, known_ids, skill_graph, transferable_ids)
        ordered_ids = _topo_order(closure, skill_graph)
        hours_by_skill = {
            sid: _skill_hours(sid, skill_graph, transferable_ids) for sid in ordered_ids
        }
        total_hours = sum(hours_by_skill.values())

        # 排序依据:每个非目标先修技能,哪些路径内技能直接依赖它
        dependents_of: dict[str, list[str]] = {sid: [] for sid in ordered_ids}
        prereqs_in_path: dict[str, list[str]] = {sid: [] for sid in ordered_ids}
        for sid in ordered_ids:
            for prereq_id in skill_graph.get(sid, {}).get("prerequisites", []):
                if prereq_id in closure:
                    prereqs_in_path.setdefault(sid, []).append(prereq_id)
                    dependents_of.setdefault(prereq_id, []).append(sid)

        steps: list[LearningPathStep] = []
        for index, skill_id in enumerate(ordered_ids, start=1):
            reason = _build_reason(
                skill_id,
                is_target=skill_id in missing_ids,
                transferable_from=transferable.get(skill_id),
                prereqs_in_path=prereqs_in_path.get(skill_id, []),
                dependents=dependents_of.get(skill_id, []),
                freq=freq,
                hours=hours_by_skill[skill_id],
                skill_graph=skill_graph,
            )
            steps.append(
                LearningPathStep(
                    step_no=index,
                    skill=skill_display_name(skill_id),
                    reason=reason,
                    resources=resources.get(skill_id, []),
                )
            )

        # 评分:单一公式(见模块 docstring)
        target_weight = {sid: freq.get(sid, 1.0) for sid in target_ids}
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
            },
            skill_gap=SkillGap(
                missing_skills=[skill_display_name(sid) for sid in missing_required],
                overlap_skills=[skill_display_name(sid) for sid in covered_ids],
                optional_skills=[skill_display_name(sid) for sid in missing_optional],
                transferable=[
                    SkillTransferableItem(
                        known_skill=skill_display_name(known_id),
                        target_skill=skill_display_name(target_id),
                        category=skill_graph.get(target_id, {}).get("category"),
                    )
                    for target_id, known_id in sorted(transferable.items())
                ],
            ),
            path=path,
        )

    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: Optional[list[str]] = None,
    ) -> LearningPath:
        return GraphPathPlannerV3.analyze_role(
            profile=profile,
            target_job_id=target_job_id,
            candidate_skills=candidate_skills,
            semantic_score=0.0,
        ).path
