"""
app/services/path_planner.py  —  C部分对接层  v6.0
====================================================
v6.0: 图谱节点 ID 与 B 词表完全对齐，去除翻译层。

技能处理策略（两层）：
  Layer 1  skill_norm 归一化 → B vocab skill_id → 图谱中直接查找 → 完整 DAG 路径
  Layer 2  图谱外的技能 → 自动生成 Coursera/GitHub/Amazon 搜索资源（绝不返回空）

设计原则：
  - skill_norm 将用户输入的任意技能名归一化为 B vocab ID
  - 归一化后直接走图谱，无需中间翻译
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote_plus

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "services"))

from app.schemas.domain import (
    LearningPath, LearningPathStep, LearningResource, UserProfile,
)

try:
    from app.services.skill_norm import normalize_skill_id as _b_normalize
except Exception:
    def _b_normalize(s): return None

# ════════════════════════════════════════════════════════════
# 已废弃：B→C 翻译映射（v6.0 图谱节点 ID 与 B 对齐，无需翻译）
# ════════════════════════════════════════════════════════════
B_TO_C_ID: dict[str, str] = {  # 保留结构防止旧调用报错，内容已清空
    # ── 编程语言 ──────────────────────────────────────────
    "python":                "sk_python_basic",
    "sql":                   "sk_sql_basic",
    "sql-lang":              "sk_sql_basic",
    "mysql":                 "sk_sql_basic",
    "postgresql":            "sk_sql_basic",
    "r":                     "sk_math_basic",
    "matlab":                "sk_math_basic",
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
    "data-mining":           "sk_pandas",
    "statistics":            "sk_stats",
    "ab-testing":            "sk_ab_test",
    "business-intelligence": "sk_tableau",
    "time-series":           "sk_stats",
    "hypothesis-testing":    "sk_stats",
    # ── 机器学习 / 深度学习 ───────────────────────────────
    "machine-learning":      "sk_ml_basic",
    "scikit-learn":          "sk_ml_basic",
    "deep-learning":         "sk_dl_basic",
    "tensorflow":            "sk_dl_basic",
    "keras":                 "sk_dl_basic",
    "pytorch":               "sk_pytorch",
    "xgboost":               "sk_ml_basic",
    "data-science":          "sk_ml_basic",
    "feature-engineering":   "sk_ml_basic",
    "model-deployment":      "sk_fastapi",
    # ── NLP ───────────────────────────────────────────────
    "nlp":                   "sk_nlp_basic",
    "text-classification":   "sk_nlp_basic",
    "ner":                   "sk_nlp_basic",
    "sentiment-analysis":    "sk_nlp_basic",
    "information-extraction":"sk_nlp_basic",
    "embedding":             "sk_embedding",
    "transformer":           "sk_transformer",
    "bert":                  "sk_transformer",
    # ── LLM 基础 ──────────────────────────────────────────
    "llm":                   "sk_llm_basic",
    "gpt":                   "sk_llm_basic",
    "openai-api":            "sk_llm_basic",
    "huggingface":           "sk_llm_basic",
    "aigc":                  "sk_llm_basic",
    "multimodal":            "sk_llm_basic",
    "diffusion":             "sk_dl_basic",
    "prompt-engineering":    "sk_prompt_eng",
    # ── 向量数据库 ────────────────────────────────────────
    "vector-database":       "sk_vector_db",
    "pinecone":              "sk_vector_db",
    "milvus":                "sk_vector_db",
    "weaviate":              "sk_vector_db",
    "chroma":                "sk_vector_db",
    "faiss":                 "sk_vector_db",
    "knowledge-graph":       "sk_vector_db",
    # ── LLM 工程 ──────────────────────────────────────────
    "langchain":             "sk_langchain",
    "llamaindex":            "sk_langchain",
    "langgraph":             "sk_langchain",
    "rag":                   "sk_rag",
    # ── Agent ─────────────────────────────────────────────
    "agent":                 "sk_agent",
    "multi-agent":           "sk_agent",
    "mcp":                   "sk_tool_use",
    "tool-calling":          "sk_tool_use",
    "quantization":          "sk_lora_finetune",
    # ── 微调 ──────────────────────────────────────────────
    "fine-tuning":           "sk_lora_finetune",
    "mlops":                 "sk_lora_finetune",
    # ── 后端 / 部署 ───────────────────────────────────────
    "fastapi":               "sk_fastapi",
    "rest":                  "sk_fastapi",
    "grpc":                  "sk_fastapi",
    "graphql":               "sk_fastapi",
    "docker":                "sk_docker",
    "kubernetes":            "sk_docker",
    "cicd":                  "sk_docker",
    "microservices":         "sk_docker",
    "serverless":            "sk_docker",
    # ── 数据结构 ──────────────────────────────────────────
    "data-structures":       "sk_data_structure",
    "algorithms":            "sk_data_structure",
}

# ════════════════════════════════════════════════════════════
# Layer 2：语义近似映射（B 技能 → C 图谱里最接近的技能）
# 用于 B 技能无直接对应但有相关性的情况
# ════════════════════════════════════════════════════════════
_SEMANTIC_APPROX: dict[str, str] = {
    # 前端（精确映射到新图谱节点）
    "react":               "sk_react",
    "vue":                 "sk_vue",
    "angular":             "sk_react",
    "nextjs":              "sk_react",
    "javascript":          "sk_javascript",
    "html":                "sk_html_css",
    "css":                 "sk_html_css",
    "nodejs":              "sk_nodejs",
    "express":             "sk_nodejs",
    # 后端框架（精确映射到新图谱节点）
    "django":              "sk_django",
    "flask":               "sk_django",
    "springboot":          "sk_springboot",
    "spring":              "sk_springboot",
    # 数据库（精确映射到新图谱节点）
    "mongodb":             "sk_mongodb",
    "redis":               "sk_redis",
    "elasticsearch":       "sk_mongodb",
    "cassandra":           "sk_mongodb",
    "neo4j":               "sk_mongodb",
    "dynamodb":            "sk_mongodb",
    # 云服务（精确映射到新图谱节点）
    "aws":                 "sk_aws",
    "azure":               "sk_azure",
    "gcp":                 "sk_aws",
    "cloud-computing":     "sk_aws",
    "terraform":           "sk_docker",
    "ansible":             "sk_docker",
    "helm":                "sk_docker",
    # 大数据（精确映射到新图谱节点）
    "spark":               "sk_spark",
    "hadoop":              "sk_spark",
    "kafka":               "sk_kafka",
    "flink":               "sk_spark",
    "bigquery":            "sk_sql_advanced",
    "snowflake":           "sk_sql_advanced",
    "dbt":                 "sk_sql_advanced",
    # 安全（精确映射到新图谱节点）
    "cybersecurity":       "sk_security",
    "penetration-testing": "sk_security",
    "network-security":    "sk_security",
    # 计算机视觉（精确映射到新图谱节点）
    "computer-vision":     "sk_cv",
    "cuda":                "sk_cv",
    "cnn":                 "sk_cv",
    # 移动开发（精确映射到新图谱节点）
    "flutter":             "sk_flutter",
    "android":             "sk_flutter",
    "ios":                 "sk_flutter",
    # 系统设计（精确映射到新图谱节点）
    "system-design":       "sk_system_design",
    "distributed-systems": "sk_system_design",
    # 其他 ML
    "reinforcement-learning": "sk_ml_basic",
    "rnn":                 "sk_dl_basic",
    "linear-algebra":      "sk_math_basic",
    "probability":         "sk_math_basic",
    "pytest":              "sk_python_basic",
    "unit-testing":        "sk_python_basic",
    # ── 热门技能补充（原 Layer 3 → 提升至 Layer 2）──────────────
    # 前端
    "typescript":          "sk_javascript",
    "svelte":              "sk_javascript",
    "tailwind":            "sk_html_css",
    "vite":                "sk_javascript",
    "react-native":        "sk_react",
    "jetpack-compose":     "sk_flutter",
    # 后端 / DevOps
    "nestjs":              "sk_nodejs",
    "devops":              "sk_docker",
    "argocd":              "sk_docker",
    "github-actions":      "sk_git",
    "sre":                 "sk_system_design",
    # 大数据
    "airflow":             "sk_spark",
    "dagster":             "sk_spark",
    "databricks":          "sk_spark",
    "clickhouse":          "sk_sql_advanced",
    # AI
    "coze":                "sk_agent",
    "qwen":                "sk_llm_basic",
    # 测试
    "cypress":             "sk_javascript",
    "playwright":          "sk_javascript",
    # 安全
    "zero-trust":          "sk_security",
    # 语言（映射到最接近的通用编程路径）
    "go":                  "sk_python_basic",
    "rust":                "sk_python_basic",
    # 其他
    "iot":                 "sk_linux_basic",
    "blockchain":          "sk_system_design",
    "edge-computing":      "sk_linux_basic",
}

# ════════════════════════════════════════════════════════════
# Layer 3：兜底字符串匹配（skill_norm 失效时）
# ════════════════════════════════════════════════════════════
_B_NAME_FALLBACK: dict[str, str] = {
    "machine learning":       "sk_ml_basic",
    "deep learning":          "sk_dl_basic",
    "vector database":        "sk_vector_db",
    "prompt engineering":     "sk_prompt_eng",
    "fine-tuning":            "sk_lora_finetune",
    "fine tuning":            "sk_lora_finetune",
    "natural language processing": "sk_nlp_basic",
    "large language model":   "sk_llm_basic",
    "ai agent":               "sk_agent",
    "function calling":       "sk_tool_use",
    "tool use":               "sk_tool_use",
    "retrieval augmented generation": "sk_rag",
    "text embedding":         "sk_embedding",
    "word embedding":         "sk_embedding",
}


def _normalize_skill(raw: str, graph_ids: set[str]) -> str | None:
    """
    将用户输入的技能名归一化为 B vocab skill_id。
    v6.0: 图谱节点 ID 即为 B vocab ID，归一化后直接查图谱。
    """
    # Step 1: skill_norm 模块（B 词表别名匹配）
    b_id = _b_normalize(raw)
    if b_id and b_id in graph_ids:
        return b_id

    # Step 2: 直接 kebab 化后查图谱
    kebab = raw.lower().strip().replace(" ", "-").replace("_", "-")
    if kebab in graph_ids:
        return kebab

    # Step 3: skill_norm 结果即使不在图谱也返回（供 Layer 2 兜底）
    return b_id or None


# ════════════════════════════════════════════════════════════
# Amazon 书单：为 C 图谱外技能提供经典书籍推荐
# 参考：Ashrafi et al. (2023) Career-gAIde 框架的书籍推荐机制
# DOI: 10.1109/ACCESS.2023.3329576
# ════════════════════════════════════════════════════════════
_AMAZON_BOOKS: dict[str, list[dict]] = {
    # ── 前端开发 ──────────────────────────────────────────
    "react": [
        {"title": "Learning React: Modern Patterns for Developing React Apps",
         "url": "https://www.amazon.com/s?k=Learning+React+Modern+Patterns",
         "level": "intermediate"},
        {"title": "React: Up & Running - Building Web Applications",
         "url": "https://www.amazon.com/s?k=React+Up+Running+Building+Web+Applications",
         "level": "beginner"},
    ],
    "vue": [
        {"title": "Vue.js 3 - The Complete Guide (incl. Router & Composition API)",
         "url": "https://www.amazon.com/s?k=Vue.js+3+Complete+Guide",
         "level": "beginner"},
    ],
    "angular": [
        {"title": "Angular: Up and Running - Learning Angular, Step by Step",
         "url": "https://www.amazon.com/s?k=Angular+Up+and+Running",
         "level": "intermediate"},
    ],
    "nodejs": [
        {"title": "Node.js Design Patterns: Design and implement production-grade Node.js",
         "url": "https://www.amazon.com/s?k=Node.js+Design+Patterns",
         "level": "intermediate"},
    ],
    # ── 后端框架 ──────────────────────────────────────────
    "django": [
        {"title": "Django for Beginners: Build websites with Python and Django",
         "url": "https://www.amazon.com/s?k=Django+for+Beginners+William+Vincent",
         "level": "beginner"},
        {"title": "Two Scoops of Django: Best Practices for the Django Web Framework",
         "url": "https://www.amazon.com/s?k=Two+Scoops+of+Django",
         "level": "intermediate"},
    ],
    "springboot": [
        {"title": "Spring Boot: Up and Running - Building Cloud Native Java and Kotlin Applications",
         "url": "https://www.amazon.com/s?k=Spring+Boot+Up+and+Running",
         "level": "intermediate"},
        {"title": "Learning Spring Boot 3.0 - Simplify the development of production-grade applications",
         "url": "https://www.amazon.com/s?k=Learning+Spring+Boot+3",
         "level": "beginner"},
    ],
    # ── 云计算 ────────────────────────────────────────────
    "aws": [
        {"title": "AWS Certified Solutions Architect Study Guide: Associate SAA-C03 Exam",
         "url": "https://www.amazon.com/s?k=AWS+Certified+Solutions+Architect+Study+Guide",
         "level": "intermediate"},
        {"title": "Amazon Web Services in Action: An in-depth guide to AWS",
         "url": "https://www.amazon.com/s?k=Amazon+Web+Services+in+Action",
         "level": "beginner"},
        {"title": "Cloud Computing: Concepts, Technology, Security, and Architecture",
         "url": "https://www.amazon.com/s?k=Cloud+Computing+Concepts+Technology+Architecture",
         "level": "beginner"},
    ],
    "azure": [
        {"title": "Microsoft Azure Administrator Study Guide: Exam AZ-104",
         "url": "https://www.amazon.com/s?k=Microsoft+Azure+Administrator+Study+Guide+AZ-104",
         "level": "intermediate"},
    ],
    "gcp": [
        {"title": "Google Cloud Platform in Action",
         "url": "https://www.amazon.com/s?k=Google+Cloud+Platform+in+Action",
         "level": "intermediate"},
    ],
    # ── 数据库 ────────────────────────────────────────────
    "mongodb": [
        {"title": "MongoDB: The Definitive Guide - Powerful and Scalable Data Storage",
         "url": "https://www.amazon.com/s?k=MongoDB+The+Definitive+Guide",
         "level": "beginner"},
        {"title": "MongoDB in Action: Covers MongoDB version 3.0",
         "url": "https://www.amazon.com/s?k=MongoDB+in+Action",
         "level": "intermediate"},
    ],
    "redis": [
        {"title": "Redis in Action",
         "url": "https://www.amazon.com/s?k=Redis+in+Action",
         "level": "intermediate"},
    ],
    "elasticsearch": [
        {"title": "Elasticsearch: The Definitive Guide",
         "url": "https://www.amazon.com/s?k=Elasticsearch+The+Definitive+Guide",
         "level": "intermediate"},
    ],
    # ── 大数据 ────────────────────────────────────────────
    "spark": [
        {"title": "Learning Spark: Lightning-Fast Data Analytics (2nd Edition)",
         "url": "https://www.amazon.com/s?k=Learning+Spark+Lightning+Fast+Data+Analytics",
         "level": "intermediate"},
        {"title": "Spark: The Definitive Guide - Big Data Processing Made Simple",
         "url": "https://www.amazon.com/s?k=Spark+The+Definitive+Guide",
         "level": "intermediate"},
    ],
    "kafka": [
        {"title": "Kafka: The Definitive Guide - Real-Time Data and Stream Processing",
         "url": "https://www.amazon.com/s?k=Kafka+The+Definitive+Guide",
         "level": "intermediate"},
    ],
    # ── DevOps ────────────────────────────────────────────
    "terraform": [
        {"title": "Terraform: Up & Running - Writing Infrastructure as Code",
         "url": "https://www.amazon.com/s?k=Terraform+Up+Running+Infrastructure+Code",
         "level": "intermediate"},
    ],
    "kubernetes": [
        {"title": "Kubernetes in Action (2nd Edition)",
         "url": "https://www.amazon.com/s?k=Kubernetes+in+Action",
         "level": "intermediate"},
        {"title": "Kubernetes: Up and Running: Dive into the Future of Infrastructure",
         "url": "https://www.amazon.com/s?k=Kubernetes+Up+and+Running",
         "level": "beginner"},
    ],
    # ── 安全 ──────────────────────────────────────────────
    "cybersecurity": [
        {"title": "CompTIA Security+ Study Guide: Exam SY0-701",
         "url": "https://www.amazon.com/s?k=CompTIA+Security+Plus+Study+Guide+SY0-701",
         "level": "beginner"},
        {"title": "The Web Application Hacker's Handbook: Finding and Exploiting Security Flaws",
         "url": "https://www.amazon.com/s?k=Web+Application+Hackers+Handbook",
         "level": "advanced"},
    ],
    # ── 移动开发 ──────────────────────────────────────────
    "flutter": [
        {"title": "Flutter Complete Reference: Create Beautiful, Fast and Native Apps",
         "url": "https://www.amazon.com/s?k=Flutter+Complete+Reference",
         "level": "beginner"},
    ],
    "android": [
        {"title": "Android Programming: The Big Nerd Ranch Guide",
         "url": "https://www.amazon.com/s?k=Android+Programming+Big+Nerd+Ranch",
         "level": "beginner"},
    ],
    # ── 计算机视觉 ────────────────────────────────────────
    "computer-vision": [
        {"title": "Programming Computer Vision with Python: Tools and algorithms for analyzing images",
         "url": "https://www.amazon.com/s?k=Programming+Computer+Vision+Python",
         "level": "intermediate"},
        {"title": "Deep Learning for Computer Vision with Python",
         "url": "https://www.amazon.com/s?k=Deep+Learning+Computer+Vision+Python+Rosebrock",
         "level": "advanced"},
    ],
    # ── 系统设计 ──────────────────────────────────────────
    "system-design": [
        {"title": "System Design Interview - An Insider's Guide (Volume 1)",
         "url": "https://www.amazon.com/s?k=System+Design+Interview+Insiders+Guide",
         "level": "intermediate"},
        {"title": "Designing Data-Intensive Applications: The Big Ideas Behind Reliable Systems",
         "url": "https://www.amazon.com/s?k=Designing+Data+Intensive+Applications",
         "level": "advanced"},
    ],
    # ── 区块链 ────────────────────────────────────────────
    "blockchain": [
        {"title": "Mastering Bitcoin: Programming the Open Blockchain",
         "url": "https://www.amazon.com/s?k=Mastering+Bitcoin+Programming+Open+Blockchain",
         "level": "intermediate"},
        {"title": "Mastering Ethereum: Building Smart Contracts and DApps",
         "url": "https://www.amazon.com/s?k=Mastering+Ethereum+Building+Smart+Contracts",
         "level": "intermediate"},
    ],
    # ── 测试 ──────────────────────────────────────────────
    "selenium": [
        {"title": "Selenium WebDriver 3 Practical Guide: End-to-end automation",
         "url": "https://www.amazon.com/s?k=Selenium+WebDriver+3+Practical+Guide",
         "level": "beginner"},
    ],
}


def _make_fallback_resources(skill_name: str) -> list[LearningResource]:
    """
    为 C 图谱外的技能生成学习资源：
    1. 优先使用 Amazon 书单（参考 Career-gAIde 论文的书籍推荐机制）
    2. 补充 Coursera 课程搜索链接
    3. 补充 GitHub 仓库搜索链接
    确保任何技能都有至少 3 条可点击的学习资源。
    """
    q        = quote_plus(skill_name)
    b_key    = skill_name.lower().strip().replace(" ", "-")
    books    = _AMAZON_BOOKS.get(b_key, [])
    resources: list[LearningResource] = []

    # Amazon 书单（如有）
    for i, book in enumerate(books[:2]):
        resources.append(LearningResource(
            resource_id = f"amazon_{b_key}_{i}",
            title       = book["title"],
            url         = book["url"],
            provider    = "amazon",
            level       = book.get("level", "intermediate"),
        ))

    # Coursera 搜索（补充）
    resources.append(LearningResource(
        resource_id = f"search_coursera_{b_key[:20]}",
        title       = f"{skill_name} - Coursera 课程搜索",
        url         = f"https://www.coursera.org/search?query={q}",
        provider    = "coursera",
        level       = "beginner",
    ))

    # GitHub 搜索（补充）
    resources.append(LearningResource(
        resource_id = f"search_github_{b_key[:20]}",
        title       = f"{skill_name} tutorial - GitHub 仓库搜索",
        url         = f"https://github.com/search?q={q}+tutorial&type=repositories",
        provider    = "github",
        level       = "beginner",
    ))

    return resources


def _map_skills_to_ids(skills: list[str], graph_ids: set[str]) -> set[str]:
    result: set[str] = set()
    for s in skills:
        sid = _normalize_skill(s, graph_ids)
        if sid and sid in graph_ids:
            result.add(sid)
    return result


# ════════════════════════════════════════════════════════════
# 岗位 ID → 内部 target_role 映射
# ════════════════════════════════════════════════════════════
_JOB_ROLE_KEYWORDS: dict[str, list[str]] = {
    "RAG应用工程师":   ["rag", "retrieval", "知识库"],
    "Agent应用工程师": ["agent", "智能体", "agentic"],
    "数据分析师":      ["analyst", "数据分析", "bi", "tableau", "data-analyst"],
    "数据工程师":      ["data-engineer", "数据工程", "etl", "data-pipeline", "dataeng"],
    "前端工程师":      ["frontend", "前端", "front-end", "react", "vue", "web前端"],
    "后端工程师":      ["backend", "后端", "fastapi", "server", "back-end"],
}
_DEFAULT_ROLE = "RAG应用工程师"


def _resolve_target_role(target_job_id: str, profile_role: str | None) -> str:
    for src in [profile_role or "", target_job_id]:
        src_lower = src.lower()
        for role, kws in _JOB_ROLE_KEYWORDS.items():
            if any(kw in src_lower for kw in kws):
                return role
    return _DEFAULT_ROLE


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

    @staticmethod
    def generate(
        profile: UserProfile,
        target_job_id: str,
        candidate_skills: list[str],
        strategy: str = "shortest",
    ) -> LearningPath:
        """
        生成学习路径。

        技能处理两层策略：
          Layer 1  skill_norm 归一化 → B vocab ID → 图谱内 → 完整 DAG 路径 + 真实资源
          Layer 2  图谱外的技能 → 自动生成 Coursera/GitHub/Amazon 搜索资源
        """
        _Cache.ensure_loaded()

        graph_ids      = set(_Cache.skill_data.keys())
        target_role    = _resolve_target_role(target_job_id, profile.target_role)
        user_skill_ids = _map_skills_to_ids(profile.skills or [], graph_ids)

        # 分类处理 candidate_skills
        in_graph:  set[str]  = set()   # 在图谱内的技能 ID
        out_graph: list[str] = []      # 图谱外（用原始名生成搜索链接）

        for s in candidate_skills:
            sid = _normalize_skill(s, graph_ids)
            if sid and sid in graph_ids:
                in_graph.add(sid)
            else:
                out_graph.append(s)

        all_ids = in_graph

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
            reason = (
                f"掌握「{step['skill_name']}」是{target_role}的"
                f"{'核心进阶' if difficulty == 'advanced' else '必要基础'}技能，"
                f"预计学习时长 {step['hours']}h"
            )
            steps.append(LearningPathStep(
                step_no   = step["step"],
                skill     = step["skill_name"],
                reason    = reason,
                resources = resources,
            ))
            total_hours += step.get("hours", 0)

        # Layer 2：图谱外技能 → 搜索资源兜底，绝不返回空
        for extra_no, skill_str in enumerate(out_graph, start=len(steps) + 1):
            steps.append(LearningPathStep(
                step_no   = extra_no,
                skill     = skill_str,
                reason    = (
                    f"「{skill_str}」超出当前学习路径图谱范围，"
                    f"已为您生成三个平台的搜索入口，可直接点击学习"
                ),
                resources = _make_fallback_resources(skill_str),
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
        return {
            s: PathPlannerService.generate(
                profile, target_job_id, candidate_skills, strategy=s
            )
            for s in ("shortest", "easy_first", "full_cover")
        }
