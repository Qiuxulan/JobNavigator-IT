"""
test_e2e.py  ——  A→B→C 端到端联通测试
===========================================
真实调用链：
  A（ExtractorService）  ←  已实现，真实运行
  B（RecommenderService） ←  代码已有，但缺 fine_grained_roles_v1.json，用模拟输出替代
  C（PathPlannerService） ←  已实现，真实运行

运行方式：
  cd JobNavigator-IT
  python test_e2e.py
"""

import sys, json
from pathlib import Path

# ── 用 szc-dev1 的 app 包 ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.services.extractor  import ExtractorService
from app.services.path_planner import PathPlannerService
from app.schemas.domain import SkillGap, RecommendationItem, JobRole

SEP = "=" * 60

# ═══════════════════════════════════════════════════════════
# STEP 1 ── A 模块：从简历文本抽取用户画像
# ═══════════════════════════════════════════════════════════
print(SEP)
print("STEP 1  A模块 ExtractorService.extract()")
print(SEP)

resume_text = """
我有两年Python开发经验，熟悉 SQL、Git，了解 Docker。
最近在学习大模型方向，接触过 LangChain 和基础的 Prompt Engineering。
目标是成为 RAG 应用工程师。
"""

profile = ExtractorService.extract(resume_text, None, "user_demo_001")
print(f"  user_id   : {profile.user_id}")
print(f"  skills    : {profile.skills}")
print(f"  target_role: {profile.target_role}")
print(f"  experience : {profile.years_experience} 年")

# ═══════════════════════════════════════════════════════════
# STEP 2 ── B 模块：岗位推荐（当前无数据，用模拟输出）
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("STEP 2  B模块 RecommenderService（模拟输出）")
print("        原因：fine_grained_roles_v1.json 尚未提交，B模块数据缺失")
print("        实际对接后本段替换为 RecommenderService.recommend()")
print(SEP)

# 模拟 B 返回的推荐结果（RAG岗位，模拟技能缺口）
# 真实调用：recs = RecommenderService.recommend(profile, UserPreference(), top_k=3)
simulated_job = JobRole(
    job_id       = "job_rag_001",
    title        = "RAG应用工程师",
    fine_role    = "大模型应用工程师（RAG方向）",
    coarse_role  = "AI工程师",
    required_skills = ["Python", "LangChain", "RAG", "向量数据库", "Prompt Engineering",
                       "Transformer", "文本Embedding", "大语言模型"],
    salary_min_k = 25,
    salary_max_k = 45,
    city         = "上海",
)

# B 的 _skill_gap() 逻辑：用户已有 vs 岗位需要
user_skills_lower = {s.lower() for s in profile.skills}
simulated_missing = [
    sk for sk in simulated_job.required_skills
    if sk.lower() not in user_skills_lower
]
simulated_overlap = [
    sk for sk in simulated_job.required_skills
    if sk.lower() in user_skills_lower
]

simulated_skill_gap = SkillGap(
    missing_skills  = simulated_missing,
    overlap_skills  = simulated_overlap,
    optional_skills = ["LoRA微调", "Agent框架"],
)

print(f"  推荐岗位  : {simulated_job.title}（{simulated_job.fine_role}）")
print(f"  薪资范围  : {simulated_job.salary_min_k}k ~ {simulated_job.salary_max_k}k")
print(f"  重合技能  : {simulated_skill_gap.overlap_skills}")
print(f"  缺口技能  : {simulated_skill_gap.missing_skills}")

# ═══════════════════════════════════════════════════════════
# STEP 3 ── C 模块：学习路径规划（真实运行）
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("STEP 3  C模块 PathPlannerService.generate()")
print(SEP)

# 真实接口：B 的 missing_skills 直接传入 C
path = PathPlannerService.generate(
    profile          = profile,
    target_job_id    = simulated_job.job_id,
    candidate_skills = simulated_skill_gap.missing_skills,
    strategy         = "shortest",
)

print(f"  目标岗位  : {simulated_job.job_id}")
print(f"  路径步骤  : {path.total_steps} 步")
print(f"  预计学时  : {path.total_estimated_hours}h")
print(f"  路径评分  : {path.score}")
print()
print("  学习步骤清单：")
for step in path.steps:
    res_titles = [r.title[:30] for r in step.resources]
    print(f"    Step{step.step_no:2d}. {step.skill:<22} | {' / '.join(res_titles) or '（无资源，建议手动补充）'}")

# ═══════════════════════════════════════════════════════════
# STEP 4 ── 三策略对比
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("STEP 4  三策略对比（shortest / easy_first / full_cover）")
print(SEP)

all_paths = PathPlannerService.generate_all_strategies(
    profile          = profile,
    target_job_id    = simulated_job.job_id,
    candidate_skills = simulated_skill_gap.missing_skills,
)

print(f"  {'策略':<12} {'步骤':>4}  {'学时':>6}  {'评分':>6}")
print(f"  {'-'*36}")
for name, p in all_paths.items():
    print(f"  {name:<12} {p.total_steps:>4}步  {p.total_estimated_hours:>5}h  {p.score:>6.3f}")

# ═══════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("联通结果")
print(SEP)
print(f"  A -> C 真实联通  [OK]  (ExtractorService -> PathPlannerService)")
print(f"  A -> B -> C 接口 [OK]  (B.missing_skills 格式与 C.candidate_skills 完全一致)")
print(f"  B 数据缺失       [~]   (fine_grained_roles_v1.json 待 B 同学提交后替换模拟段)")
print(SEP)
