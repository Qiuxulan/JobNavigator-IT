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

BASE  = Path(r"C:\Users\24222\Desktop\社会计算项目")
OUT   = BASE / "data" / "gold" / "learning_resources_v1.json"

BILI_PATH    = BASE / "bilibili_resources_C部分.csv"
GITHUB_PATH  = BASE / "github_resources.csv"
COURSERA_PATH= BASE / "coursera_it_courses.csv"
SKILL_PATH   = BASE / "skill_prerequisite_v1.json"

# ── Bilibili 标签精确映射 ─────────────────────────────────────────────────
BILI_TAG_TO_SKILL = {
    "llm":                "sk_llm_basic",
    "prompt_engineering": "sk_prompt_eng",
    "langchain":          "sk_langchain",
    "rag":                "sk_rag",
    "agent":              "sk_agent",
    "lora_finetune":      "sk_lora_finetune",
    "vector_db":          "sk_vector_db",
    "transformer":        "sk_transformer",
    "pytorch":            "sk_pytorch",
    "embedding":          "sk_embedding",
    "fastapi":            "sk_fastapi",
    "nlp":                "sk_nlp_basic",
}

# ── 关键词评分表（与 path_planner_v1.py 保持同步）────────────────────────
SKILL_KEYWORDS = {
    "sk_python_basic":   ["python programming", "learn python", "python for beginners",
                          "intro to python", "python basics", "python tutorial"],
    "sk_sql_basic":      ["sql basics", "introduction to sql", "sql for beginners",
                          "relational database", "mysql", "postgresql", "sql tutorial"],
    "sk_git":            ["git and github", "version control with git", "git for beginners",
                          "github tutorial", "git tutorial"],
    "sk_linux_basic":    ["linux command", "linux for beginners", "bash scripting",
                          "shell scripting", "linux tutorial", "command line"],
    "sk_math_basic":     ["linear algebra for machine learning", "mathematics for machine learning",
                          "probability and statistics", "calculus for machine learning",
                          "math for data science", "linear algebra and statistics"],
    "sk_pandas":         ["pandas tutorial", "pandas dataframe", "data analysis with pandas",
                          "pandas for data analysis"],
    "sk_numpy":          ["numpy", "numpy tutorial", "numpy arrays",
                          "numpy for data science", "numerical computing with python"],
    "sk_data_structure": ["data structures and algorithms", "leetcode", "algorithms and data structures",
                          "data structures tutorial"],
    "sk_matplotlib":     ["matplotlib tutorial", "data visualization with python",
                          "seaborn tutorial", "python visualization"],
    "sk_stats":          ["statistics for data science", "statistical analysis",
                          "probability and statistics for machine learning",
                          "statistics and probability", "hypothesis testing"],
    "sk_sql_advanced":   ["advanced sql", "sql window functions", "sql analytics",
                          "sql query optimization", "sql for data analysis"],
    "sk_tableau":        ["tableau tutorial", "power bi tutorial", "powerbi",
                          "business intelligence", "data visualization with tableau"],
    "sk_fastapi":        ["fastapi tutorial", "fastapi python", "rest api with fastapi",
                          "building apis with fastapi"],
    "sk_docker":         ["docker tutorial", "docker for beginners", "containerization",
                          "docker and kubernetes", "dockerfile"],
    "sk_ab_test":        ["a/b testing", "ab testing", "experiment design",
                          "online experiments", "statistical hypothesis testing"],
    "sk_ml_basic":       ["machine learning course", "machine learning tutorial",
                          "scikit-learn", "supervised learning", "machine learning a-z",
                          "introduction to machine learning"],
    "sk_dl_basic":       ["deep learning tutorial", "neural networks tutorial",
                          "tensorflow tutorial", "keras tutorial",
                          "introduction to deep learning"],
    "sk_pytorch":        ["pytorch tutorial", "pytorch deep learning", "learn pytorch",
                          "pytorch for beginners"],
    "sk_nlp_basic":      ["nlp", "natural language processing", "natural language processing tutorial",
                          "nlp with python", "text classification", "nlp course", "introduction to nlp"],
    "sk_embedding":      ["word embedding", "text embedding", "word2vec tutorial",
                          "sentence embedding", "embedding tutorial"],
    "sk_transformer":    ["transformer architecture", "attention mechanism",
                          "bert tutorial", "transformer model", "self-attention"],
    "sk_llm_basic":      ["large language model", "llm tutorial", "generative ai course",
                          "introduction to llm", "gpt tutorial", "llm for beginners"],
    "sk_prompt_eng":     ["prompt engineering", "prompt design", "prompting techniques",
                          "prompt tutorial"],
    "sk_vector_db":      ["vector database", "milvus tutorial", "chroma tutorial",
                          "faiss tutorial", "pinecone tutorial", "vector search"],
    "sk_langchain":      ["langchain tutorial", "langchain python", "build with langchain",
                          "langchain course"],
    "sk_lora_finetune":  ["lora fine-tuning", "qlora", "fine-tuning llm",
                          "parameter efficient fine-tuning", "peft tutorial",
                          "finetuning large language model"],
    "sk_rag":            ["retrieval augmented generation", "rag tutorial",
                          "rag system", "rag with langchain", "build rag"],
    "sk_agent":          ["ai agent tutorial", "agentic ai", "multi-agent system",
                          "autonomous agent", "ai agent development"],
    "sk_tool_use":       ["function calling", "tool use llm", "tool calling",
                          "llm tool use", "openai function calling"],
}

# ── 手工补录：无法通过关键词捕获的技能资源映射 ───────────────────────────
# 用于 sk_tool_use、sk_sql_advanced、sk_tableau、sk_ab_test 等无覆盖技能
MANUAL_RESOURCES = {
    "sk_tool_use": [
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
            "skill_scores": {"sk_tool_use": 3, "sk_agent": 3}
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
            "skill_scores": {"sk_tool_use": 3, "sk_langchain": 2}
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
            "skill_scores": {"sk_tool_use": 3, "sk_agent": 3}
        },
    ],
    "sk_sql_advanced": [
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
            "skill_scores": {"sk_sql_advanced": 2, "sk_sql_basic": 2}
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
            "skill_scores": {"sk_sql_advanced": 2}
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
            "skill_scores": {"sk_sql_advanced": 2}
        },
    ],
    "sk_tableau": [
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
            "skill_scores": {"sk_tableau": 2}
        },
    ],
    "sk_docker": [
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
            "skill_scores": {"sk_docker": 2}
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
            "skill_scores": {"sk_docker": 2}
        },
    ],
    "sk_ab_test": [
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
            "skill_scores": {"sk_ab_test": 2}
        },
    ],
    "sk_math_basic": [
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
            "skill_scores": {"sk_math_basic": 2}
        },
    ],
    "sk_matplotlib": [
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
            "skill_scores": {"sk_matplotlib": 2, "sk_pandas": 2, "sk_numpy": 2}
        },
    ],
    "sk_git": [
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
            "skill_scores": {"sk_git": 2}
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
