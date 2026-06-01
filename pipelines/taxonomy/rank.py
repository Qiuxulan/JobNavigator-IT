"""
精排 - 第一版(召回候选 -> 多维打分 + 缺口分析 + 可解释输出)

打分:Final = α·语义相似 + β·约束满足 - γ·缺口惩罚 + δ·趋势奖励
重点:除了分数,额外输出"重合技能/缺口技能/推荐理由",这才是可解释性主体
运行:python pipelines/taxonomy/rank.py
"""

import json
import numpy as np
from sentence_transformers import SentenceTransformer

ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
MODEL_NAME = "TechWolf/JobBERT-v3"
RECALL_N = 10   # 召回阶段取多少候选
TOP_K = 5       # 精排后输出多少

# ---- 打分权重(初始经验值,后续用评估集校准)----
ALPHA = 0.5     # 语义相似
BETA = 0.2      # 硬约束满足
GAMMA = 0.02   # 每个缺口技能的惩罚
DELTA = 0.15    # 趋势奖励
# --------------------------------------------------

# 临时的"趋势奖励"表(本应来自行业/D模块,这里先用占位)
TREND_BONUS_KEYWORDS = {
    "machine learning": 1.0, "ml": 1.0, "ai": 1.0, "data scientist": 0.9,
    "mlops": 1.0, "data engineer": 0.8, "llm": 1.0, "devops": 0.7,
}


def clean_skills(skills):
    return [s.replace("(方向)", "").strip() for s in skills if s.strip()]


def role_to_text(role):
    skills = clean_skills(role.get("required_skills", []))
    return f"{role.get('role_name','')}. Required skills: {', '.join(skills)}"


def profile_to_text(p):
    return f"Target role: {p.get('target_role','')}. My skills: {', '.join(p.get('skills', []))}"


def trend_bonus(role_name):
    name = role_name.lower()
    for kw, v in TREND_BONUS_KEYWORDS.items():
        if kw in name:
            return v
    return 0.5  # 默认中性


def skill_gap(user_skills, role_skills):
    """返回 (重合, 缺口),大小写不敏感匹配"""
    u = {s.lower(): s for s in user_skills}
    overlap, missing = [], []
    for rs in role_skills:
        if rs.lower() in u:
            overlap.append(rs)
        else:
            missing.append(rs)
    return overlap, missing


def constraint_score(profile, role):
    """硬约束:城市/薪资是否满足。岗位库目前没这些字段,先返回中性 0.8,接真实数据后再算"""
    # TODO: 接入岗位的 city / salary 后,做真实匹配
    return 0.8


def main():
    print(">>> 加载岗位库 + 向量化 ...")
    with open(ROLES_JSON, encoding="utf-8") as f:
        roles = json.load(f)
    model = SentenceTransformer(MODEL_NAME)
    job_vecs = model.encode([role_to_text(r) for r in roles], normalize_embeddings=True)

    # ---- mock 用户 ----
    user = {
        "skills": ["Python", "SQL", "Machine Learning"],
        "target_role": "AI / Machine Learning Engineer",
        "preferred_city": None,
    }
    print(f">>> 用户: {user}\n")

    user_vec = model.encode(profile_to_text(user), normalize_embeddings=True)
    sims = job_vecs @ user_vec

    # 阶段一:召回 Top-RECALL_N
    recall_idx = np.argsort(-sims)[:RECALL_N]

    # 阶段二:精排
    items = []
    for i in recall_idx:
        role = roles[int(i)]
        # 缺口只针对核心技能;没有 core_skills 字段时退回 required_skills
        core = role.get("core_skills") or role.get("required_skills", [])
        role_skills = clean_skills(core)
        overlap, missing = skill_gap(user["skills"], role_skills)

        sem = float(sims[i])
        con = constraint_score(user, role)
        gap_penalty = GAMMA * len(missing)
        trend = trend_bonus(role["role_name"])

        final = ALPHA * sem + BETA * con - gap_penalty + DELTA * trend

        explanation = (
            f"与你的技能重合 {len(overlap)} 项({', '.join(overlap) or '无'}),"
            f"缺口 {len(missing)} 项;语义匹配 {sem:.2f},趋势热度 {trend:.1f}。"
        )

        items.append({
            "role_id": role["role_id"],
            "role_name": role["role_name"],
            "final_score": round(final, 4),
            "score_breakdown": {
                "semantic": round(ALPHA * sem, 4),
                "constraint": round(BETA * con, 4),
                "gap_penalty": round(-gap_penalty, 4),
                "trend_reward": round(DELTA * trend, 4),
            },
            "overlap_skills": overlap,
            "missing_skills": missing,   # <-- 交给 C 做学习路径的关键产物
            "explanation": explanation,
        })

    items.sort(key=lambda x: x["final_score"], reverse=True)
    items = items[:TOP_K]

    print(f">>> 精排 Top-{TOP_K} 推荐:\n")
    for rank, it in enumerate(items, 1):
        print(f"#{rank} [{it['role_id']}] {it['role_name']}  总分={it['final_score']}")
        print(f"     分解: {it['score_breakdown']}")
        print(f"     缺口技能(给C): {', '.join(it['missing_skills'][:6])}")
        print(f"     解释: {it['explanation']}")
        print()


if __name__ == "__main__":
    main()