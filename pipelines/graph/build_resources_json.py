"""
build_resources_json.py
一次性脚本：从三源CSV生成 data/gold/learning_resources_v1.json
逻辑与 path_planner_v1.py 的资源加载保持一致，额外添加：
  - 每个技能的完整资源列表（非截断到5条）
  - 技能元数据（skill_name / category / level / difficulty / hours_estimate）
  - 统计摘要（覆盖技能数、各源数量、无资源技能列表）
"""

import json, csv
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).parents[2]
# 原始 CSV 爬取数据的可选外部目录（未纳入仓库时的兜底，可用环境变量覆盖）
import os
_RAW_DIR = Path(os.environ.get("JOBNAV_RAW_DIR", _REPO / "data" / "raw"))


def _resolve_csv(filename: str) -> Path:
    """优先仓库内 data/raw，其次外部原始目录，返回首个存在的路径（都不存在则返回仓库内路径用于报错）"""
    for base in (_REPO / "data" / "raw", _RAW_DIR,
                 Path(r"C:\Users\24222\Desktop\社会计算项目")):
        p = base / filename
        if p.exists():
            return p
    return _REPO / "data" / "raw" / filename


BILI_PATH    = _resolve_csv("bilibili_resources_C部分.csv")
GITHUB_PATH  = _resolve_csv("github_resources.csv")
COURSERA_PATH= _resolve_csv("coursera_it_courses.csv")
SKILL_PATH   = _REPO / "data" / "gold" / "skill_prerequisite_v2.json"   # v2: B vocab ID
OUT          = _REPO / "data" / "gold" / "learning_resources_v1.json"

# ── Bilibili 标签精确映射 ─────────────────────────────────────────────────
BILI_TAG_TO_SKILL = {
    "llm":                "llm",
    "prompt_engineering": "prompt-engineering",
    "langchain":          "langchain",
    "rag":                "rag",
    "agent":              "agent",
    "lora_finetune":      "fine-tuning",
    "vector_db":          "vector-database",
    "transformer":        "transformer",
    "pytorch":            "pytorch",
    "embedding":          "embedding",
    "fastapi":            "fastapi",
    "nlp":                "nlp",
}

# ── 关键词评分表（与 path_planner_v1.py 保持同步）────────────────────────
SKILL_KEYWORDS = {
    "python":   ["python programming", "learn python", "python for beginners",
                          "intro to python", "python basics", "python tutorial"],
    "sql-lang":      ["sql basics", "introduction to sql", "sql for beginners",
                          "relational database", "mysql", "postgresql", "sql tutorial"],
    "git":            ["git and github", "version control with git", "git for beginners",
                          "github tutorial", "git tutorial"],
    "linux":    ["linux command", "linux for beginners", "bash scripting",
                          "shell scripting", "linux tutorial", "command line"],
    "statistics":     ["linear algebra for machine learning", "mathematics for machine learning",
                          "probability and statistics", "calculus for machine learning",
                          "math for data science", "linear algebra and statistics"],
    "pandas":         ["pandas tutorial", "pandas dataframe", "data analysis with pandas",
                          "pandas for data analysis"],
    "numpy":          ["numpy", "numpy tutorial", "numpy arrays",
                          "numpy for data science", "numerical computing with python"],
    "data-structures": ["data structures and algorithms", "leetcode", "algorithms and data structures",
                          "data structures tutorial"],
    "statistics":     ["matplotlib tutorial", "data visualization with python",
                          "seaborn tutorial", "python visualization"],
    "statistics":          ["statistics for data science", "statistical analysis",
                          "probability and statistics for machine learning",
                          "statistics and probability", "hypothesis testing"],
    "postgresql":   ["advanced sql", "sql window functions", "sql analytics",
                          "sql query optimization", "sql for data analysis"],
    "tableau":        ["tableau tutorial", "power bi tutorial", "powerbi",
                          "business intelligence", "data visualization with tableau"],
    "fastapi":        ["fastapi tutorial", "fastapi python", "rest api with fastapi",
                          "building apis with fastapi"],
    "docker":         ["docker tutorial", "docker for beginners", "containerization",
                          "docker and kubernetes", "dockerfile"],
    "ab-testing":        ["a/b testing", "ab testing", "experiment design",
                          "online experiments", "statistical hypothesis testing"],
    "machine-learning":       ["machine learning course", "machine learning tutorial",
                          "scikit-learn", "supervised learning", "machine learning a-z",
                          "introduction to machine learning"],
    "deep-learning":       ["deep learning tutorial", "neural networks tutorial",
                          "tensorflow tutorial", "keras tutorial",
                          "introduction to deep learning"],
    "pytorch":        ["pytorch tutorial", "pytorch deep learning", "learn pytorch",
                          "pytorch for beginners"],
    "nlp":      ["nlp", "natural language processing", "natural language processing tutorial",
                          "nlp with python", "text classification", "nlp course", "introduction to nlp"],
    "embedding":      ["word embedding", "text embedding", "word2vec tutorial",
                          "sentence embedding", "embedding tutorial"],
    "transformer":    ["transformer architecture", "attention mechanism",
                          "bert tutorial", "transformer model", "self-attention"],
    "llm":      ["large language model", "llm tutorial", "generative ai course",
                          "introduction to llm", "gpt tutorial", "llm for beginners"],
    "prompt-engineering":     ["prompt engineering", "prompt design", "prompting techniques",
                          "prompt tutorial"],
    "vector-database":      ["vector database", "milvus tutorial", "chroma tutorial",
                          "faiss tutorial", "pinecone tutorial", "vector search"],
    "langchain":      ["langchain tutorial", "langchain python", "build with langchain",
                          "langchain course"],
    "fine-tuning":  ["lora fine-tuning", "qlora", "fine-tuning llm",
                          "parameter efficient fine-tuning", "peft tutorial",
                          "finetuning large language model"],
    "rag":            ["retrieval augmented generation", "rag tutorial",
                          "rag system", "rag with langchain", "build rag"],
    "agent":          ["ai agent tutorial", "agentic ai", "multi-agent system",
                          "autonomous agent", "ai agent development"],
    "tool-calling":       ["function calling", "tool use llm", "tool calling",
                          "llm tool use", "openai function calling"],
    # ── v2 新增17个技能 ──
    "html":       ["html tutorial", "css tutorial", "html and css", "web design basics",
                          "html css for beginners", "frontend basics"],
    "javascript":     ["javascript tutorial", "javascript for beginners", "es6 javascript",
                          "learn javascript", "javascript programming"],
    "react":          ["react tutorial", "react.js", "react hooks", "react for beginners",
                          "build with react", "nextjs tutorial"],
    "vue":            ["vue tutorial", "vue.js", "vue for beginners", "learn vue"],
    "django":         ["django tutorial", "flask tutorial", "python web framework",
                          "django rest framework"],
    "springboot":     ["spring boot tutorial", "spring framework", "java backend",
                          "spring rest api"],
    "nodejs":         ["node.js tutorial", "nodejs backend", "express tutorial",
                          "server side javascript"],
    "mongodb":        ["mongodb tutorial", "nosql database", "mongodb for beginners",
                          "mongoose tutorial"],
    "redis":          ["redis tutorial", "redis cache", "in-memory database"],
    "aws":            ["aws tutorial", "amazon web services", "aws for beginners",
                          "cloud computing aws", "aws solutions architect"],
    "azure":          ["azure tutorial", "microsoft azure", "azure for beginners"],
    "spark":          ["apache spark tutorial", "pyspark tutorial", "big data processing",
                          "spark streaming"],
    "kafka":          ["apache kafka tutorial", "kafka for beginners", "message queue kafka",
                          "event streaming kafka"],
    "cybersecurity":       ["cybersecurity tutorial", "network security", "ethical hacking",
                          "oauth jwt", "web security owasp"],
    "flutter":        ["flutter tutorial", "dart flutter", "flutter for beginners",
                          "cross platform mobile flutter"],
    "computer-vision":             ["computer vision tutorial", "opencv tutorial", "image recognition",
                          "cnn computer vision", "object detection"],
    "system-design":  ["system design", "distributed systems", "microservices architecture",
                          "scalability", "system design interview"],
}

# ── 手工补录：无法通过关键词捕获的技能资源映射 ───────────────────────────
# 用于 sk_tool_use、sk_sql_advanced、sk_tableau、sk_ab_test 等无覆盖技能
MANUAL_RESOURCES = {
    "tool-calling": [
        {
            "resource_id": "bili_BV1DfrdByE2H_tooluse",
            "title": "2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）",
            "source": "bilibili",
            "url": "https://www.bilibili.com/video/BV1DfrdByE2H/",
            "difficulty": "intermediate",
            "hours_estimate": 12.0,
            "language": "zh",
            "note": "UP:吴恩达Agent | 含Tool Use/Function Calling设计模式讲解",
            "match_reason": "manual_tag",
            "skill_scores": {"tool-calling": 3, "agent": 3}
        },
        {
            "resource_id": "github_0001_tooluse",
            "title": "GenAI_Agents",
            "source": "github",
            "url": "https://github.com/NirDiamant/GenAI_Agents",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:22236 | 50+ tutorials including Tool Use & Function Calling patterns",
            "match_reason": "manual_tag",
            "skill_scores": {"tool-calling": 3, "langchain": 2}
        },
        {
            "resource_id": "github_0004_tooluse",
            "title": "AgentGuide",
            "source": "github",
            "url": "https://github.com/adongwanai/AgentGuide",
            "difficulty": "advanced",
            "hours_estimate": 0.0,
            "language": "zh",
            "note": "stars:5259 | 含Function Calling实战 + LangGraph Tool Use",
            "match_reason": "manual_tag",
            "skill_scores": {"tool-calling": 3, "agent": 3}
        },
    ],
    "postgresql": [
        {
            "resource_id": "coursera_0012_sqladv",
            "title": "Web Applications for Everybody",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=Web+Applications+for+Everybody",
            "difficulty": "intermediate",
            "hours_estimate": 100.0,
            "language": "en",
            "note": "University of Michigan ★4.7 | 含SQL/MySQL/关系数据库/数据建模",
            "match_reason": "manual_tag",
            "skill_scores": {"postgresql": 2, "sql-lang": 2}
        },
        {
            "resource_id": "manual_sqladv_bili_001",
            "title": "SQL进阶教程：窗口函数/子查询/性能优化全解析",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=SQL进阶+窗口函数+数据分析",
            "difficulty": "intermediate",
            "hours_estimate": 8.0,
            "language": "zh",
            "note": "B站搜索补充资源 | 推荐搜索: SQL进阶 窗口函数 数据分析",
            "match_reason": "manual_supplement",
            "skill_scores": {"postgresql": 2}
        },
        {
            "resource_id": "manual_sqladv_github_001",
            "title": "sql-tutorial (advanced SQL patterns and analytics)",
            "source": "github",
            "url": "https://github.com/topics/sql-tutorial",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "GitHub SQL tutorial topic page | 窗口函数/CTE/性能优化实例",
            "match_reason": "manual_supplement",
            "skill_scores": {"postgresql": 2}
        },
    ],
    "tableau": [
        {
            "resource_id": "manual_tableau_001",
            "title": "【推荐搜索】B站搜索 Tableau入门教程 或 PowerBI教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Tableau+PowerBI+教程",
            "difficulty": "beginner",
            "hours_estimate": 10.0,
            "language": "zh",
            "note": "当前资源库暂无Tableau专项，建议在B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"tableau": 2}
        },
    ],
    "docker": [
        {
            "resource_id": "manual_docker_bili_001",
            "title": "Docker从入门到实战：容器化部署全流程教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Docker入门+容器化+部署",
            "difficulty": "intermediate",
            "hours_estimate": 10.0,
            "language": "zh",
            "note": "B站搜索补充资源 | 推荐搜索: Docker入门 容器化 K8s",
            "match_reason": "manual_supplement",
            "skill_scores": {"docker": 2}
        },
        {
            "resource_id": "manual_docker_github_001",
            "title": "awesome-docker",
            "source": "github",
            "url": "https://github.com/veggiemonk/awesome-docker",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:28k+ | Docker官方推荐资源合集，含教程/工具/最佳实践",
            "match_reason": "manual_supplement",
            "skill_scores": {"docker": 2}
        },
    ],
    "ab-testing": [
        {
            "resource_id": "manual_abtest_001",
            "title": "【推荐搜索】B站搜索 A/B测试 数据分析",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=AB测试+数据分析",
            "difficulty": "intermediate",
            "hours_estimate": 8.0,
            "language": "zh",
            "note": "当前资源库暂无A/B测试专项，建议在B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"ab-testing": 2}
        },
    ],
    "statistics": [
        {
            "resource_id": "manual_math_001",
            "title": "【推荐搜索】B站搜索 线性代数/概率论/机器学习数学基础",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=线性代数+概率论+机器学习",
            "difficulty": "beginner",
            "hours_estimate": 60.0,
            "language": "zh",
            "note": "当前资源库暂无专项数学课程，推荐B站搜索：3Blue1Brown线代/概率论",
            "match_reason": "manual_supplement",
            "skill_scores": {"statistics": 2}
        },
    ],
    "statistics": [
        {
            "resource_id": "github_0097_vis",
            "title": "data-science-complete-tutorial",
            "source": "github",
            "url": "https://github.com/edyoda/data-science-complete-tutorial",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程",
            "match_reason": "manual_tag",
            "skill_scores": {"statistics": 2, "pandas": 2, "numpy": 2}
        },
    ],
    "git": [
        {
            "resource_id": "manual_git_001",
            "title": "【推荐搜索】B站搜索 Git教程 版本控制",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Git+版本控制+教程",
            "difficulty": "beginner",
            "hours_estimate": 8.0,
            "language": "zh",
            "note": "当前资源库暂无Git专项，推荐B站搜索黑马程序员Git教程",
            "match_reason": "manual_supplement",
            "skill_scores": {"git": 2}
        },
    ],
    # ── v2 新增17个技能手工资源 ──
    "html": [
        {
            "resource_id": "manual_htmlcss_bili_001",
            "title": "HTML+CSS前端开发入门教程（黑马程序员）",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=HTML+CSS+前端入门+黑马",
            "difficulty": "beginner",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | 推荐：黑马/尚硅谷HTML CSS教程",
            "match_reason": "manual_supplement",
            "skill_scores": {"html": 3}
        },
        {
            "resource_id": "manual_htmlcss_github_001",
            "title": "freeCodeCamp - Responsive Web Design",
            "source": "github",
            "url": "https://github.com/freeCodeCamp/freeCodeCamp",
            "difficulty": "beginner",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:400k+ | 免费全套前端课程，HTML/CSS/JavaScript全覆盖",
            "match_reason": "manual_supplement",
            "skill_scores": {"html": 3, "javascript": 2}
        },
    ],
    "javascript": [
        {
            "resource_id": "manual_js_bili_001",
            "title": "JavaScript入门到精通完整版（尚硅谷）",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=JavaScript+入门+尚硅谷",
            "difficulty": "beginner",
            "hours_estimate": 30.0,
            "language": "zh",
            "note": "B站搜索补充 | 推荐：尚硅谷/黑马JS完整教程",
            "match_reason": "manual_supplement",
            "skill_scores": {"javascript": 3}
        },
        {
            "resource_id": "manual_js_github_001",
            "title": "javascript-algorithms",
            "source": "github",
            "url": "https://github.com/trekhleb/javascript-algorithms",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:190k+ | JavaScript数据结构和算法实现",
            "match_reason": "manual_supplement",
            "skill_scores": {"javascript": 2, "data-structures": 2}
        },
    ],
    "react": [
        {
            "resource_id": "manual_react_bili_001",
            "title": "React18入门到实战完整版",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=React+18+入门+实战",
            "difficulty": "intermediate",
            "hours_estimate": 25.0,
            "language": "zh",
            "note": "B站搜索补充 | 推荐：尚硅谷/coderwhy React18教程",
            "match_reason": "manual_supplement",
            "skill_scores": {"react": 3}
        },
        {
            "resource_id": "manual_react_github_001",
            "title": "awesome-react",
            "source": "github",
            "url": "https://github.com/enaqx/awesome-react",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:65k+ | React生态资源合集",
            "match_reason": "manual_supplement",
            "skill_scores": {"react": 2}
        },
    ],
    "vue": [
        {
            "resource_id": "manual_vue_bili_001",
            "title": "Vue3+TypeScript实战教程（尚硅谷）",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Vue3+TypeScript+尚硅谷",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | Vue3/Vite/Pinia完整栈",
            "match_reason": "manual_supplement",
            "skill_scores": {"vue": 3}
        },
    ],
    "django": [
        {
            "resource_id": "manual_django_bili_001",
            "title": "Django+DRF REST API实战教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Django+REST+API+实战",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | Django/Flask/FastAPI后端开发",
            "match_reason": "manual_supplement",
            "skill_scores": {"django": 3, "fastapi": 2}
        },
    ],
    "springboot": [
        {
            "resource_id": "manual_spring_bili_001",
            "title": "SpringBoot3+MyBatis-Plus实战（黑马程序员）",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=SpringBoot3+MyBatis+黑马",
            "difficulty": "intermediate",
            "hours_estimate": 30.0,
            "language": "zh",
            "note": "B站搜索补充 | Java后端主流技术栈",
            "match_reason": "manual_supplement",
            "skill_scores": {"springboot": 3}
        },
    ],
    "nodejs": [
        {
            "resource_id": "manual_nodejs_bili_001",
            "title": "Node.js+Express+MongoDB全栈开发教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Node.js+Express+全栈",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | Node.js后端开发",
            "match_reason": "manual_supplement",
            "skill_scores": {"nodejs": 3, "mongodb": 2}
        },
    ],
    "mongodb": [
        {
            "resource_id": "manual_mongo_bili_001",
            "title": "MongoDB入门到实战教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=MongoDB+入门+教程",
            "difficulty": "beginner",
            "hours_estimate": 10.0,
            "language": "zh",
            "note": "B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"mongodb": 3}
        },
        {
            "resource_id": "manual_mongo_github_001",
            "title": "awesome-mongodb",
            "source": "github",
            "url": "https://github.com/ramnes/awesome-mongodb",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:2.5k+ | MongoDB资源合集",
            "match_reason": "manual_supplement",
            "skill_scores": {"mongodb": 2}
        },
    ],
    "redis": [
        {
            "resource_id": "manual_redis_bili_001",
            "title": "Redis从入门到实战（黑马程序员）",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Redis+入门+黑马",
            "difficulty": "intermediate",
            "hours_estimate": 15.0,
            "language": "zh",
            "note": "B站搜索补充 | Redis缓存/持久化/集群",
            "match_reason": "manual_supplement",
            "skill_scores": {"redis": 3}
        },
    ],
    "aws": [
        {
            "resource_id": "manual_aws_coursera_001",
            "title": "AWS Cloud Practitioner Essentials",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=AWS+Cloud+Practitioner+Essentials",
            "difficulty": "beginner",
            "hours_estimate": 15.0,
            "language": "en",
            "note": "Amazon官方 ★4.7 | AWS CLF-C02备考首选",
            "match_reason": "manual_supplement",
            "skill_scores": {"aws": 3}
        },
        {
            "resource_id": "manual_aws_bili_001",
            "title": "AWS云计算从入门到SAA认证",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=AWS+云计算+SAA+认证",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | AWS Solutions Architect备考",
            "match_reason": "manual_supplement",
            "skill_scores": {"aws": 3}
        },
    ],
    "azure": [
        {
            "resource_id": "manual_azure_coursera_001",
            "title": "Microsoft Azure Fundamentals AZ-900",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=Microsoft+Azure+AZ-900",
            "difficulty": "beginner",
            "hours_estimate": 10.0,
            "language": "en",
            "note": "Microsoft官方 | AZ-900认证备考",
            "match_reason": "manual_supplement",
            "skill_scores": {"azure": 3}
        },
    ],
    "spark": [
        {
            "resource_id": "manual_spark_coursera_001",
            "title": "Big Data Analysis with Scala and Spark",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=Big+Data+Analysis+Scala+Spark",
            "difficulty": "intermediate",
            "hours_estimate": 40.0,
            "language": "en",
            "note": "EPFL ★4.6 | Spark核心课程",
            "match_reason": "manual_supplement",
            "skill_scores": {"spark": 3}
        },
        {
            "resource_id": "manual_spark_bili_001",
            "title": "PySpark大数据处理实战教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=PySpark+大数据+实战",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充 | PySpark/Hadoop/Hive大数据栈",
            "match_reason": "manual_supplement",
            "skill_scores": {"spark": 3}
        },
    ],
    "kafka": [
        {
            "resource_id": "manual_kafka_bili_001",
            "title": "Apache Kafka消息队列从入门到实战",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Kafka+消息队列+实战",
            "difficulty": "intermediate",
            "hours_estimate": 15.0,
            "language": "zh",
            "note": "B站搜索补充 | Kafka架构/生产消费/实时流",
            "match_reason": "manual_supplement",
            "skill_scores": {"kafka": 3}
        },
        {
            "resource_id": "manual_kafka_github_001",
            "title": "awesome-kafka",
            "source": "github",
            "url": "https://github.com/infoslack/awesome-kafka",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "Kafka资源合集",
            "match_reason": "manual_supplement",
            "skill_scores": {"kafka": 2}
        },
    ],
    "cybersecurity": [
        {
            "resource_id": "manual_security_coursera_001",
            "title": "Google Cybersecurity Professional Certificate",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=Google+Cybersecurity+Professional+Certificate",
            "difficulty": "beginner",
            "hours_estimate": 180.0,
            "language": "en",
            "note": "Google官方 ★4.8 | 网络安全入门系列",
            "match_reason": "manual_supplement",
            "skill_scores": {"cybersecurity": 3}
        },
        {
            "resource_id": "manual_security_bili_001",
            "title": "网络安全/渗透测试入门教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=网络安全+渗透测试+入门",
            "difficulty": "beginner",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"cybersecurity": 3}
        },
    ],
    "flutter": [
        {
            "resource_id": "manual_flutter_bili_001",
            "title": "Flutter3.x移动端实战开发教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=Flutter3+移动端+实战",
            "difficulty": "intermediate",
            "hours_estimate": 25.0,
            "language": "zh",
            "note": "B站搜索补充 | Flutter/Dart跨平台开发",
            "match_reason": "manual_supplement",
            "skill_scores": {"flutter": 3}
        },
        {
            "resource_id": "manual_flutter_github_001",
            "title": "awesome-flutter",
            "source": "github",
            "url": "https://github.com/Solido/awesome-flutter",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:53k+ | Flutter资源合集",
            "match_reason": "manual_supplement",
            "skill_scores": {"flutter": 2}
        },
    ],
    "computer-vision": [
        {
            "resource_id": "manual_cv_coursera_001",
            "title": "Deep Learning Specialization (Course 4 - CNN)",
            "source": "coursera",
            "url": "https://www.coursera.org/search?query=Convolutional+Neural+Networks+deeplearning.ai",
            "difficulty": "intermediate",
            "hours_estimate": 35.0,
            "language": "en",
            "note": "deeplearning.ai ★4.9 | CNN/YOLO/人脸识别",
            "match_reason": "manual_supplement",
            "skill_scores": {"computer-vision": 3, "deep-learning": 2}
        },
        {
            "resource_id": "manual_cv_bili_001",
            "title": "计算机视觉OpenCV+YOLO实战教程",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=计算机视觉+OpenCV+YOLO+实战",
            "difficulty": "intermediate",
            "hours_estimate": 20.0,
            "language": "zh",
            "note": "B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"computer-vision": 3}
        },
    ],
    "system-design": [
        {
            "resource_id": "manual_sysdesign_github_001",
            "title": "system-design-primer",
            "source": "github",
            "url": "https://github.com/donnemartin/system-design-primer",
            "difficulty": "intermediate",
            "hours_estimate": 0.0,
            "language": "en",
            "note": "stars:290k+ | 系统设计面试圣经，分布式/高可用/微服务",
            "match_reason": "manual_supplement",
            "skill_scores": {"system-design": 3}
        },
        {
            "resource_id": "manual_sysdesign_bili_001",
            "title": "系统设计面试/分布式系统架构讲解",
            "source": "bilibili",
            "url": "https://search.bilibili.com/all?keyword=系统设计+分布式+架构+面试",
            "difficulty": "advanced",
            "hours_estimate": 15.0,
            "language": "zh",
            "note": "B站搜索补充",
            "match_reason": "manual_supplement",
            "skill_scores": {"system-design": 3}
        },
    ],
}


def _score_resource(title, body):
    t = title.lower()
    b = body.lower()
    scores = {}
    for sid, kws in SKILL_KEYWORDS.items():
        th = sum(1 for kw in kws if kw in t)
        bh = sum(1 for kw in kws if kw in b)
        s  = th * 2 + bh
        if s > 0:
            scores[sid] = s
    return scores


def load_all_resources():
    resources = []

    # ── Bilibili ──
    with open(BILI_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tags = [t.strip() for t in row.get("覆盖技能(;分隔)", "").split(";") if t.strip()]
            skill_ids = [BILI_TAG_TO_SKILL[t] for t in tags if t in BILI_TAG_TO_SKILL]
            if not skill_ids:
                continue
            try:
                hours = float(row.get("估计时长(小时)", 0) or 0)
            except ValueError:
                hours = 0.0
            bv  = row.get("URL", "").rstrip("/").split("/")[-1]
            rid = f"bili_{bv}"
            note_str = row.get("备注", "")
            resources.append({
                "resource_id":   rid,
                "title":         row.get("视频标题", ""),
                "source":        "bilibili",
                "url":           row.get("URL", ""),
                "difficulty":    row.get("难度", "beginner"),
                "hours_estimate":hours,
                "language":      "zh",
                "note":          f"UP:{row.get('UP主','')} | {note_str}",
                "match_reason":  "bili_tag",
                "skill_scores":  {sid: 3 for sid in skill_ids},
            })

    # ── GitHub ──
    with open(GITHUB_PATH, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            title  = row.get("title", "")
            topics = row.get("topics", "")
            desc   = row.get("description", "")
            lang_c = row.get("language_content", "en")
            scores = _score_resource(title, topics + " " + desc)
            scores = {k: v for k, v in scores.items() if v >= 2}
            if not scores:
                continue
            try:
                stars = int(row.get("stars", 0))
            except ValueError:
                stars = 0
            resources.append({
                "resource_id":   row.get("resource_id", ""),
                "title":         title,
                "source":        "github",
                "url":           row.get("url", ""),
                "difficulty":    row.get("difficulty", "intermediate"),
                "hours_estimate":0.0,
                "language":      lang_c if lang_c else "en",
                "note":          f"stars:{stars} | {row.get('full_name','')}",
                "match_reason":  "keyword_score",
                "skill_scores":  scores,
            })

    # ── Coursera ──
    with open(COURSERA_PATH, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            title  = row.get("title", "")
            body   = row.get("skills_raw", "")
            scores = _score_resource(title, body)
            scores = {k: v for k, v in scores.items() if v >= 2}
            if not scores:
                continue
            try:
                hours = float(row.get("hours_estimate", 0) or 0)
            except ValueError:
                hours = 0.0
            inst   = row.get("institution", "")
            rating = row.get("rating", "")
            resources.append({
                "resource_id":   row.get("resource_id", ""),
                "title":         title,
                "source":        "coursera",
                "url":           f"https://www.coursera.org/search?query={title.replace(' ','+')}",
                "difficulty":    row.get("level", "beginner"),
                "hours_estimate":hours,
                "language":      "en",
                "note":          f"{inst} | rating:{rating}",
                "match_reason":  "keyword_score",
                "skill_scores":  scores,
            })

    return resources


def build_json():
    # 技能元数据
    with open(SKILL_PATH, encoding="utf-8") as f:
        skill_graph = json.load(f)
    skill_meta = {s["skill_id"]: s for s in skill_graph["skills"]}
    all_skill_ids = [s["skill_id"] for s in skill_graph["skills"]]

    resources = load_all_resources()

    # 手工补录
    manual_added = []
    for sid, res_list in MANUAL_RESOURCES.items():
        for r in res_list:
            manual_added.append(r)
    resources += manual_added

    # 按 skill_id 分组（保留全部，不截断）
    skill_resource_map = defaultdict(list)
    seen_per_skill = defaultdict(set)  # 去重同一 resource_id 在同一 skill 下
    source_order = {"bilibili": 0, "github": 1, "coursera": 2}

    for res in resources:
        for sid, score in res["skill_scores"].items():
            key = (sid, res["resource_id"])
            if key not in seen_per_skill[sid]:
                seen_per_skill[sid].add(res["resource_id"])
                skill_resource_map[sid].append({
                    "_sort_key": (-score, source_order.get(res["source"], 3)),
                    **{k: v for k, v in res.items() if k != "skill_scores"}
                })

    # 排序
    for sid in skill_resource_map:
        skill_resource_map[sid].sort(key=lambda x: x["_sort_key"])
        for r in skill_resource_map[sid]:
            del r["_sort_key"]

    # 统计
    covered   = [sid for sid in all_skill_ids if sid in skill_resource_map]
    uncovered = [sid for sid in all_skill_ids if sid not in skill_resource_map]
    source_cnt= defaultdict(int)
    for sid, rl in skill_resource_map.items():
        for r in rl:
            source_cnt[r["source"]] += 1

    # 构建输出
    output = {
        "version":     "v1",
        "created":     "2026-06-01",
        "description": "学习资源库（按skill_id索引），整合Bilibili视频/GitHub仓库/Coursera课程三源，供路径规划模块调用",
        "metadata": {
            "total_skills":             len(all_skill_ids),
            "skills_with_resources":    len(covered),
            "skills_without_resources": uncovered,
            "source_counts": dict(source_cnt),
            "total_resource_skill_pairs": sum(len(v) for v in skill_resource_map.values()),
        },
        "skills": {}
    }

    for sid in all_skill_ids:
        meta = skill_meta.get(sid, {})
        output["skills"][sid] = {
            "skill_name":    meta.get("skill_name", sid),
            "category":      meta.get("category", ""),
            "level":         meta.get("level", 0),
            "difficulty":    meta.get("difficulty", ""),
            "hours_estimate":meta.get("hours_estimate", 0),
            "prerequisites": meta.get("prerequisites", []),
            "resources":     skill_resource_map.get(sid, []),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 输出至: {OUT}")
    print(f"     技能总数: {len(all_skill_ids)}")
    print(f"     有资源技能: {len(covered)}/{len(all_skill_ids)}")
    if uncovered:
        print(f"     无资源技能: {uncovered}")
    print(f"     各源资源数: {dict(source_cnt)}")
    print(f"     资源-技能对总数: {sum(len(v) for v in skill_resource_map.values())}")


if __name__ == "__main__":
    build_json()
