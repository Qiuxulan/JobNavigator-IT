"""
职业推荐服务 - 真实实现(双阶段:pgvector ANN 召回 + 多维精排)

============================================================
本文件当前包含若干【临时占位】,集成时为打通链路而设,后续需替换。
全局搜索 "TODO" 可一次性定位所有待补项:

  TODO-1 path_cost_score:暂用"缺口技能惩罚"近似路径成本。
         真实的学习路径长度由 C 模块(path_planner)产出,接入后替换。
  TODO-2 constraint_score:暂固定 0.8。岗位库尚无 city/salary/degree
         字段,硬约束无法真算,岗位库补字段后替换。
  TODO-3 trend_reward_score:暂用关键词占位表。真实趋势热度来自
         行业/D 模块,接入后替换。
  TODO-4 JobRole.city/salary:岗位库暂无,填 None。
  TODO-5 打分权重 ALPHA/BETA/GAMMA/DELTA 为初始经验值,
         待评估集(reports/recommend_eval_v1.md)校准。

数据依赖:postgres job_roles 表(由 pipelines.taxonomy.build_job_vectors 写入)
  注:该岗位库当前基于 6000 条抽样、且 Djinni 部分技能尚未抽取。
      定稿时需用全量数据重跑 cluster_roles.py + build_job_vectors.py。
============================================================
"""

import json
import os
from functools import lru_cache

from app.schemas.domain import JobRole, RecommendationItem, SkillGap, UserPreference, UserProfile

MODEL_NAME = "TechWolf/JobBERT-v3"
ROLES_JSON = "data/gold/fine_grained_roles_v1.json"  # 仍读它补 core/optional/skill_freq 字段

DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)

# ---- 打分权重(TODO-5: 经验值,待评估集校准)----
ALPHA = 0.5     # 语义相似
BETA = 0.2      # 硬约束满足
GAMMA = 0.02    # 每个缺口技能的惩罚
DELTA = 0.15    # 趋势奖励
RECALL_N = 10   # 召回候选数

# TODO-3: 临时趋势奖励表,真实热度应来自行业/D模块
TREND_BONUS_KEYWORDS = {
    "machine learning": 1.0, "ml": 1.0, "ai": 1.0, "data scientist": 0.9,
    "mlops": 1.0, "data engineer": 0.8, "llm": 1.0, "devops": 0.7,
}


def _clean_skills(skills):
    return [s.replace("(方向)", "").strip() for s in skills if s and s.strip()]


@lru_cache(maxsize=1)
def _load_engine():
    """首次调用时加载模型 + 岗位库元数据(core/optional/skill_freq),之后复用缓存。
    召回不再在内存里现算岗位向量,改为查 pgvector(向量已由
    build_job_vectors.py 离线写入 job_roles.embedding)。
    放在函数内 import,避免没装 sentence-transformers 时整个模块导入失败。"""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)

    # 岗位元数据按 role_id 建索引:pgvector 只存了召回需要的字段,
    # core_skills/optional_skills/skill_freq 这些精排字段从 JSON 补。
    with open(ROLES_JSON, encoding="utf-8") as f:
        roles_list = json.load(f)
    roles_by_id = {r.get("role_id"): r for r in roles_list}

    return model, roles_by_id


def _trend_bonus(role_name: str) -> float:
    name = (role_name or "").lower()
    for kw, v in TREND_BONUS_KEYWORDS.items():
        if kw in name:
            return v
    return 0.5  # 默认中性


def _skill_gap(user_skills, role_skills):
    """大小写不敏感地算重合 / 缺口"""
    u = {s.lower() for s in user_skills}
    overlap = [rs for rs in role_skills if rs.lower() in u]
    missing = [rs for rs in role_skills if rs.lower() not in u]
    return overlap, missing


def _role_to_jobrole(role: dict) -> JobRole:
    """把岗位库的一条记录映射成仓库的 JobRole 结构"""
    skills = _clean_skills(role.get("required_skills", []))
    return JobRole(
        job_id=role.get("role_id", "unknown"),
        title=role.get("role_name", ""),
        fine_role=role.get("role_name", ""),
        coarse_role=role.get("coarse_role", ""),
        city=None,            # TODO-4: 岗位库暂无
        salary_min_k=None,    # TODO-4
        salary_max_k=None,    # TODO-4
        required_skills=skills,
    )


class RecommenderService:
    """双阶段推荐:pgvector ANN 召回 + 多维精排。对外签名与返回结构保持不变。"""

    @staticmethod
    def recommend(profile: UserProfile, preference: UserPreference, top_k: int) -> list[RecommendationItem]:
        from pipelines.taxonomy.recall import recall_topn  # 函数内 import,避免硬依赖

        model, roles_by_id = _load_engine()

        user_text = f"Target role: {profile.target_role or ''}. My skills: {', '.join(profile.skills)}"
        user_vec = model.encode(user_text, normalize_embeddings=True)

        # 阶段一:pgvector ANN 召回 Top-RECALL_N
        recalled = recall_topn(user_vec, RECALL_N, DSN)

        # 阶段二:精排
        items: list[RecommendationItem] = []
        for cand in recalled:
            # 用召回回来的 job_id 找回完整岗位元数据(core/optional/skill_freq)
            role = roles_by_id.get(cand["job_id"])
            if role is None:
                # 兜底:库里有、JSON 里没有(理论上不该发生),用召回字段拼一个
                role = {
                    "role_id": cand["job_id"],
                    "role_name": cand["title"],
                    "coarse_role": cand.get("coarse_role", ""),
                    "required_skills": cand.get("required_skills", []),
                }

            # 缺口只针对核心技能;没有 core_skills 字段时退回 required_skills(兼容)
            core = role.get("core_skills") or role.get("required_skills", [])
            role_skills = _clean_skills(core)
            overlap, missing = _skill_gap(profile.skills, role_skills)
            # 加分技能(展示用,不算缺口)
            optional = _clean_skills(role.get("optional_skills", []))

            semantic = float(cand["score"])  # pgvector 余弦相似度,口径同内存版点积
            constraint = 0.8  # TODO-2: 固定值,待接入 city/salary
            gap_penalty = GAMMA * len(missing)
            trend = _trend_bonus(role.get("role_name", ""))

            final = ALPHA * semantic + BETA * constraint - gap_penalty + DELTA * trend

            items.append(
                RecommendationItem(
                    job=_role_to_jobrole(role),
                    final_score=round(final, 4),
                    semantic_score=round(semantic, 4),
                    constraint_score=round(constraint, 4),
                    # TODO-1: path_cost_score 暂用缺口惩罚近似真实路径长度
                    path_cost_score=round(gap_penalty, 4),
                    trend_reward_score=round(trend, 4),
                    explanation=(
                        f"{role.get('role_name','')} 与你的技能重合 {len(overlap)} 项"
                        f"({', '.join(overlap) or '无'}),缺口 {len(missing)} 项;"
                        f"语义匹配 {semantic:.2f},趋势热度 {trend:.1f}。"
                    ),
                    skill_gap=SkillGap(
                        missing_skills=missing,
                        overlap_skills=overlap,
                        optional_skills=optional,
                    ),
                )
            )

        items.sort(key=lambda x: x.final_score, reverse=True)
        return items[:top_k]