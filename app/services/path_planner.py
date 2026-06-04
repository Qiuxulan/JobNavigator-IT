"""
app/services/path_planner.py  —  C部分对接层  v4.0
====================================================
对外接口与团队 schema (app/schemas/domain.py) 完全对齐。

技能 ID 双轨对接说明：
  B 模块使用 kebab-case 英文 ID（如 machine-learning, vector-database）
  C 内部图谱使用 sk_ 前缀格式（如 sk_ml_basic, sk_vector_db）

  转换流程：
    B 输出字符串 → skill_norm.normalize_skill_id() → B 的 ID
                 → B_TO_C_ID 映射                  → C 内部 ID
    若 skill_norm 返回 None → 尝试直接字符串模糊匹配
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "services"))

from app.schemas.domain import (
    LearningPath, LearningPathStep, LearningResource, UserProfile,
)

# skill_norm 可能因 vocab 未生成而加载失败，做降级处理
try:
    from app.services.skill_norm import normalize_skill_id as _b_normalize
    _SKILL_NORM_OK = True
except Exception:
    _SKILL_NORM_OK = False
    def _b_normalize(s): return None

# ════════════════════════════════════════════════════════════
# B 模块 skill_id (kebab-case) → C 内部 skill_id (sk_前缀)
# 依据 B 的 build_skill_vocab.py 中的技能 ID 整理
# ════════════════════════════════════════════════════════════
B_TO_C_ID: dict[str, str] = {
    # ── 编程语言 ──────────────────────────────────────────
    "python":                "sk_python_basic",
    "sql":                   "sk_sql_basic",
    "sql-lang":              "sk_sql_basic",
    "mysql":                 "sk_sql_basic",
    "postgresql":            "sk_sql_basic",
    # ── 工程工具 ──────────────────────────────────────────
    "git":                   "sk_git",
    "linux":                 "sk_linux_basic",
    "unix":                  "sk_linux_basic",
    "shell":                 "sk_linux_basic",
    # ── 数据分析 ──────────────────────────────────────────
    "pandas":                "sk_pandas",
    "numpy":                 "sk_numpy",
    "tableau":               "sk_tableau",
    "powerbi":               "sk_tableau",
    "data-analysis":         "sk_pandas",
    "data-visualization":    "sk_matplotlib",
    "statistics":            "sk_stats",
    "ab-testing":            "sk_ab_test",
    # ── 机器学习 / 深度学习 ───────────────────────────────
    "machine-learning":      "sk_ml_basic",
    "scikit-learn":          "sk_ml_basic",
    "deep-learning":         "sk_dl_basic",
    "tensorflow":            "sk_dl_basic",
    "keras":                 "sk_dl_basic",
    "pytorch":               "sk_pytorch",
    # ── NLP ───────────────────────────────────────────────
    "nlp":                   "sk_nlp_basic",
    "embedding":             "sk_embedding",
    "transformer":           "sk_transformer",
    "bert":                  "sk_transformer",
    # ── LLM 基础 ──────────────────────────────────────────
    "llm":                   "sk_llm_basic",
    "gpt":                   "sk_llm_basic",
    "openai-api":            "sk_llm_basic",
    "huggingface":           "sk_llm_basic",
    "prompt-engineering":    "sk_prompt_eng",
    # ── 向量数据库 ────────────────────────────────────────
    "vector-database":       "sk_vector_db",
    "pinecone":              "sk_vector_db",
    "milvus":                "sk_vector_db",
    "weaviate":              "sk_vector_db",
    "chroma":                "sk_vector_db",
    "faiss":                 "sk_vector_db",
    # ── LLM 工程 ──────────────────────────────────────────
    "langchain":             "sk_langchain",
    "llamaindex":            "sk_langchain",   # 同类工具，映射到 langchain
    "langgraph":             "sk_langchain",
    "rag":                   "sk_rag",
    "knowledge-graph":       "sk_rag",
    # ── Agent ─────────────────────────────────────────────
    "agent":                 "sk_agent",
    "mcp":                   "sk_tool_use",    # Model Context Protocol = Tool Use
    # ── 微调 ──────────────────────────────────────────────
    "fine-tuning":           "sk_lora_finetune",
    "mlops":                 "sk_lora_finetune",
    # ── 后端 / 部署 ───────────────────────────────────────
    "fastapi":               "sk_fastapi",
    "docker":                "sk_docker",
    "kubernetes":            "sk_docker",
}

# B 技能原始名称（小写）→ C 内部 ID（skill_norm 失效时的直接兜底）
_B_NAME_FALLBACK: dict[str, str] = {
    "machine learning":      "sk_ml_basic",
    "deep learning":         "sk_dl_basic",
    "vector database":       "sk_vector_db",
    "vector db":             "sk_vector_db",
    "prompt engineering":    "sk_prompt_eng",
    "fine-tuning":           "sk_lora_finetune",
    "fine tuning":           "sk_lora_finetune",
    "lora":                  "sk_lora_finetune",
    "qlora":                 "sk_lora_finetune",
    "natural language processing": "sk_nlp_basic",
    "large language model":  "sk_llm_basic",
    "ai agent":              "sk_agent",
    "function calling":      "sk_tool_use",
    "tool use":              "sk_tool_use",
    "retrieval augmented generation": "sk_rag",
    "text embedding":        "sk_embedding",
    "word embedding":        "sk_embedding",
}

# ════════════════════════════════════════════════════════════
# 岗位 ID 关键词 → 内部 target_role 映射
# 支持 B 模块英文岗位名称（如 "rag-engineer", "Data Analyst"）
# ════════════════════════════════════════════════════════════
_JOB_ROLE_KEYWORDS: dict[str, list[str]] = {
    "RAG应用工程师":   ["rag", "retrieval", "知识库"],
    "Agent应用工程师": ["agent", "智能体", "agentic"],
    "数据分析师":      ["analyst", "数据分析", "bi", "tableau", "data-analyst"],
    "后端工程师":      ["backend", "后端", "fastapi", "server", "back-end"],
}
_DEFAULT_ROLE = "RAG应用工程师"


def _resolve_target_role(target_job_id: str, profile_role: str | None) -> str:
    """将 B 模块的 job_id / UserProfile.target_role 映射到内部 target_role。"""
    for src in [profile_role or "", target_job_id]:
        src_lower = src.lower()
        for role, kws in _JOB_ROLE_KEYWORDS.items():
            if any(kw in src_lower for kw in kws):
                return role
    return _DEFAULT_ROLE


def _to_c_skill_id(raw: str) -> str | None:
    """
    将 B 模块输出的技能字符串转换为 C 内部 skill_id。
    三级查找：
      1. skill_norm（B 词表正向归一化）→ B ID → B_TO_C_ID 映射
      2. 直接在 B_TO_C_ID 中查找（处理 B 词表未加载的情况）
      3. 模糊匹配兜底
    """
    # Level 1: skill_norm → B 的 ID → C 的 ID
    b_id = _b_normalize(raw)
    if b_id:
        c_id = B_TO_C_ID.get(b_id)
        if c_id:
            return c_id

    # Level 2: 直接以 B 的 ID 格式查找（raw 可能已是 kebab 格式）
    raw_key = raw.lower().strip().replace(" ", "-")
    if raw_key in B_TO_C_ID:
        return B_TO_C_ID[raw_key]

    # Level 3: 兜底字符串匹配
    raw_lower = raw.lower().strip()
    return _B_NAME_FALLBACK.get(raw_lower)


def _map_skills_to_ids(skills: list[str]) -> set[str]:
    """将 B 模块输出的字符串技能列表转换为 C 内部 skill_id 集合。"""
    result: set[str] = set()
    for s in skills:
        sid = _to_c_skill_id(s)
        if sid:
            result.add(sid)
    return result


# ════════════════════════════════════════════════════════════
# 懒加载缓存
# ════════════════════════════════════════════════════════════
class _Cache:
    skill_data   = None
    prereq_map   = None
    resource_map = None

    @classmethod
    def ensure_loaded(cls) -> None:
        if cls.skill_data is None:
            from path_planner_v1 import load_skill_graph, load_resources_with_embedding
            cls.skill_data, cls.prereq_map = load_skill_graph()
            cls.resource_map = load_resources_with_embedding(cls.skill_data)


# ════════════════════════════════════════════════════════════
# 对外服务类
# ════════════════════════════════════════════════════════════
class PathPlannerService:
    """C部分学习路径服务入口。"""

    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
        strategy: str = "shortest",
    ) -> LearningPath:
        """
        生成单条学习路径。

        Args:
            profile:          用户画像（A 模块输出，skills 为英文名如 "Python", "Machine Learning"）
            target_job_id:    目标岗位ID（B 模块输出，如 "job_rag_001"）
            candidate_skills: 缺口技能（B 模块 SkillGap.missing_skills，英文名如 "RAG", "Vector Database"）
            strategy:         "shortest" | "easy_first" | "full_cover"
        """
        _Cache.ensure_loaded()

        target_role    = _resolve_target_role(target_job_id, profile.target_role)
        user_skill_ids = _map_skills_to_ids(profile.skills or [])

        # 识别无法映射到 C 图谱的技能（保留为补充步骤）
        unmapped = [s for s in candidate_skills if _to_c_skill_id(s) is None]

        from path_planner_v1 import generate_plan
        plan = generate_plan(
            user_skills  = user_skill_ids,
            target_role  = target_role,
            skill_data   = _Cache.skill_data,
            prereq_map   = _Cache.prereq_map,
            resource_map = _Cache.resource_map,
            strategy     = strategy,
        )

        steps: list[LearningPathStep] = []
        total_hours = 0

        for step in plan["steps"]:
            resources = [
                LearningResource(
                    resource_id = r.get("resource_id", f"res_{step['step']}_{i}"),
                    title       = r["title"],
                    url         = r["url"],
                    provider    = r.get("source", ""),
                    level       = step.get("difficulty", "beginner"),
                )
                for i, r in enumerate(step["resources"])
            ]
            difficulty = step.get("difficulty", "intermediate")
            steps.append(LearningPathStep(
                step_no   = step["step"],
                skill     = step["skill_name"],
                reason    = (
                    f"掌握「{step['skill_name']}」是{target_role}的"
                    f"{'核心进阶' if difficulty == 'advanced' else '必要基础'}技能，"
                    f"预计学习时长 {step['hours']}h"
                ),
                resources = resources,
            ))
            total_hours += step.get("hours", 0)

        # B 模块词表外技能：保留为补充步骤
        for extra_no, skill_str in enumerate(unmapped, start=len(steps) + 1):
            steps.append(LearningPathStep(
                step_no   = extra_no,
                skill     = skill_str,
                reason    = f"「{skill_str}」为岗位要求技能，建议自行搜索相关课程补充",
                resources = [],
            ))

        score_raw = plan["score"].get("coverage", 1.0) * (
            1.0 - 0.04 * max(0, plan["score"]["step_count"] - 5)
        )
        return LearningPath(
            target_job_id         = target_job_id,
            total_steps           = len(steps),
            total_estimated_hours = total_hours,
            score                 = round(max(0.5, min(1.0, score_raw)), 3),
            steps                 = steps,
        )

    @staticmethod
    def generate_all_strategies(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
    ) -> dict[str, LearningPath]:
        """同时生成三条候选路径。"""
        return {
            s: PathPlannerService.generate(
                profile, target_job_id, candidate_skills, strategy=s
            )
            for s in ("shortest", "easy_first", "full_cover")
        }
