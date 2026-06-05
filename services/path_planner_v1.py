"""
services/path_planner_v1.py  --  C部分学习路径规划模块 v2.0
输入：用户已有技能 + 目标岗位 + 路径策略
输出：有序学习计划卡片（步骤、时长、资源链接）

v2.0 新增：
  - 路径策略三选一：
      strategy="shortest"   最短路径（快速通道，跳过理论，步骤最少）
      strategy="easy_first" 最低难度（完整路径，由易到难排序）
      strategy="full_cover" 最全覆盖（含扩展技能，系统性最强）
  - 同时输出三条候选路径供对比
  - DAG无环显式验证（detect_cycles）
  - 路径指向 data/gold/ 目录规范化位置
  - 资源优先从 learning_resources_v1.json 加载，降级到原始CSV

v1.1 保留修复：
  - BFS在用户已知技能处停止
  - 覆盖率计算纳入用户已有技能
  - MAX_REUSE=2 资源去重
  - 评分制关键词匹配（标题×2 正文×1）
  - Bilibili标签精确映射
"""

import json
import csv
import heapq
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

# 根目录自动定位（services/ 上一层即仓库根）
BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data" / "gold"
MODEL_DIR = BASE_DIR / "models"

SKILL_GRAPH_PATH  = DATA_DIR / "skill_prerequisite_v2.json"    # v2: 使用B的技能ID
RESOURCES_JSON    = DATA_DIR / "learning_resources_v1.json"     # 优先
BILIBILI_PATH     = DATA_DIR / "bilibili_resources_C部分.csv"   # 降级
GITHUB_PATH       = BASE_DIR / "github_resources.csv"
COURSERA_PATH     = BASE_DIR / "coursera_it_courses.csv"

DIFFICULTY_NUM = {"beginner": 1, "intermediate": 2, "advanced": 3}

# ── 英文关键词（供 Embedding 双语技能文本构造用，key = B vocab skill_id） ──
SKILL_EN_KEYWORDS = {
    "python":            "python programming beginners tutorial basics",
    "sql-lang":          "sql database mysql relational query",
    "git":               "git github version control",
    "linux":             "linux bash shell scripting command line",
    "pandas":            "pandas dataframe data analysis python",
    "numpy":             "numpy numerical computing arrays python",
    "data-structures":   "data structures algorithms leetcode",
    "matplotlib":        "matplotlib data visualization seaborn python",
    "statistics":        "statistics probability hypothesis testing",
    "postgresql":        "advanced sql window functions analytics optimization",
    "tableau":           "tableau powerbi business intelligence visualization",
    "fastapi":           "fastapi rest api python web",
    "sk_docker":         "docker containerization kubernetes dockerfile",
    "sk_ab_test":        "ab testing experiment design hypothesis statistics",
    "sk_ml_basic":       "machine learning scikit-learn supervised regression classification",
    "sk_dl_basic":       "deep learning neural networks tensorflow keras",
    "sk_pytorch":        "pytorch deep learning neural networks",
    "sk_nlp_basic":      "nlp natural language processing text classification",
    "sk_embedding":      "word embedding text embedding word2vec sentence embedding",
    "sk_transformer":    "transformer attention mechanism bert self-attention",
    "sk_llm_basic":      "large language model llm generative ai gpt",
    "sk_prompt_eng":     "prompt engineering prompt design prompting",
    "sk_vector_db":      "vector database milvus faiss pinecone chroma",
    "sk_langchain":      "langchain llm framework python",
    "sk_lora_finetune":  "lora qlora fine-tuning llm peft parameter efficient",
    "sk_rag":            "retrieval augmented generation rag langchain",
    "sk_agent":          "ai agent agentic multi-agent autonomous",
    "sk_tool_use":       "function calling tool use tool calling llm",
    "html":              "html web frontend basics",
    "css":               "css styling web design",
    "javascript":        "javascript es6 dom web programming",
    "typescript":        "typescript javascript typed",
    "react":             "react frontend framework jsx hooks",
    "vue":               "vue.js frontend framework components",
    "angular":           "angular frontend framework typescript",
    "nextjs":            "next.js react ssr full-stack",
    "nodejs":            "node.js javascript backend server",
    "nestjs":            "nestjs node.js typescript backend",
    "django":            "django flask python web framework",
    "fastapi":           "fastapi python rest api",
    "springboot":        "spring boot java backend",
    "mongodb":           "mongodb nosql document database",
    "redis":             "redis cache in-memory database",
    "aws":               "aws cloud amazon web services ec2 s3 lambda",
    "azure":             "azure microsoft cloud services",
    "gcp":               "google cloud platform gcp",
    "docker":            "docker containerization kubernetes",
    "kubernetes":        "kubernetes k8s container orchestration",
    "spark":             "apache spark big data pyspark",
    "kafka":             "apache kafka message queue streaming",
    "airflow":           "apache airflow data pipeline orchestration",
    "dbt":               "dbt data build tool analytics",
    "snowflake":         "snowflake data warehouse cloud",
    "databricks":        "databricks spark delta lake",
    "machine-learning":  "machine learning scikit-learn supervised",
    "deep-learning":     "deep learning neural networks tensorflow",
    "pytorch":           "pytorch deep learning neural networks",
    "nlp":               "nlp natural language processing text",
    "computer-vision":   "computer vision cnn image recognition opencv",
    "transformer":       "transformer attention bert self-attention",
    "llm":               "large language model llm generative ai gpt",
    "embedding":         "word embedding text embedding word2vec",
    "prompt-engineering":"prompt engineering prompt design",
    "vector-database":   "vector database milvus faiss pinecone chroma",
    "langchain":         "langchain llm framework python",
    "rag":               "retrieval augmented generation rag",
    "agent":             "ai agent agentic multi-agent autonomous",
    "fine-tuning":       "lora qlora fine-tuning llm peft",
    "tool-calling":      "function calling tool use tool calling llm",
    "mlops":             "mlops machine learning operations deployment",
    "cybersecurity":     "cybersecurity network security oauth jwt",
    "flutter":           "flutter mobile dart cross-platform",
    "system-design":     "system design distributed microservices scalability",
}

# ── Bilibili 标签精确映射（bili CSV tag → B vocab skill_id）──────────────
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

# ── 评分制关键词（key = B vocab skill_id）────────────────────────────────
SKILL_KEYWORDS = {
    "python":            ["python programming", "learn python", "python for beginners",
                          "python basics", "python tutorial"],
    "sql-lang":          ["sql basics", "introduction to sql", "sql for beginners",
                          "relational database", "sql tutorial"],
    "git":               ["git and github", "version control with git", "git for beginners",
                          "github tutorial", "git tutorial"],
    "linux":             ["linux command", "linux for beginners", "bash scripting",
                          "shell scripting", "linux tutorial", "command line"],
    "pandas":            ["pandas tutorial", "pandas dataframe", "data analysis with pandas"],
    "numpy":             ["numpy tutorial", "numpy arrays", "numerical computing with python"],
    "data-structures":   ["data structures and algorithms", "leetcode", "algorithms and data structures"],
    "statistics":        ["statistics for data science", "statistical analysis",
                          "probability and statistics", "hypothesis testing"],
    "postgresql":        ["advanced sql", "sql window functions", "sql analytics",
                          "sql query optimization", "postgresql tutorial"],
    "tableau":           ["tableau tutorial", "power bi tutorial", "powerbi",
                          "business intelligence", "data visualization with tableau"],
    "fastapi":           ["fastapi tutorial", "fastapi python", "rest api with fastapi"],
    "docker":            ["docker tutorial", "docker for beginners", "containerization",
                          "docker and kubernetes", "dockerfile"],
    "ab-testing":        ["a/b testing", "ab testing", "experiment design",
                          "statistical hypothesis testing"],
    "machine-learning":  ["machine learning course", "machine learning tutorial",
                          "scikit-learn", "supervised learning", "introduction to machine learning"],
    "deep-learning":     ["deep learning tutorial", "neural networks tutorial",
                          "tensorflow tutorial", "introduction to deep learning"],
    "pytorch":           ["pytorch tutorial", "pytorch deep learning", "learn pytorch"],
    "nlp":               ["natural language processing", "nlp with python",
                          "text classification", "nlp course", "introduction to nlp"],
    "embedding":         ["word embedding", "text embedding", "word2vec tutorial",
                          "sentence embedding", "embedding tutorial"],
    "transformer":       ["transformer architecture", "attention mechanism",
                          "bert tutorial", "transformer model", "self-attention"],
    "llm":               ["large language model", "llm tutorial", "generative ai course",
                          "introduction to llm", "gpt tutorial", "llm for beginners"],
    "prompt-engineering":["prompt engineering", "prompt design", "prompting techniques"],
    "vector-database":   ["vector database", "milvus tutorial", "chroma tutorial",
                          "faiss tutorial", "pinecone tutorial", "vector search"],
    "langchain":         ["langchain tutorial", "langchain python", "build with langchain"],
    "fine-tuning":       ["lora fine-tuning", "qlora", "fine-tuning llm",
                          "parameter efficient fine-tuning", "peft tutorial"],
    "rag":               ["retrieval augmented generation", "rag tutorial",
                          "rag system", "rag with langchain", "build rag"],
    "agent":             ["ai agent tutorial", "agentic ai", "multi-agent system",
                          "autonomous agent", "ai agent development"],
    "tool-calling":      ["function calling", "tool use llm", "tool calling",
                          "openai function calling"],
    "html":              ["html tutorial", "html for beginners", "html and css"],
    "css":               ["css tutorial", "css for beginners", "web design css"],
    "javascript":        ["javascript tutorial", "javascript for beginners", "es6 javascript",
                          "learn javascript", "javascript programming"],
    "typescript":        ["typescript tutorial", "learn typescript", "typescript for beginners"],
    "react":             ["react tutorial", "react.js", "react hooks", "react for beginners"],
    "vue":               ["vue tutorial", "vue.js", "vue for beginners", "learn vue"],
    "nodejs":            ["node.js tutorial", "nodejs backend", "express tutorial",
                          "server side javascript"],
    "nestjs":            ["nestjs tutorial", "nestjs typescript", "node.js nestjs"],
    "django":            ["django tutorial", "flask tutorial", "python web framework",
                          "django rest framework"],
    "springboot":        ["spring boot tutorial", "spring framework", "java backend",
                          "spring rest api"],
    "mongodb":           ["mongodb tutorial", "nosql database", "mongodb for beginners"],
    "redis":             ["redis tutorial", "redis cache", "in-memory database"],
    "aws":               ["aws tutorial", "amazon web services", "aws for beginners",
                          "cloud computing aws", "aws solutions architect"],
    "azure":             ["azure tutorial", "microsoft azure", "azure for beginners"],
    "gcp":               ["google cloud tutorial", "gcp for beginners", "google cloud platform"],
    "spark":             ["apache spark tutorial", "pyspark tutorial", "big data processing"],
    "kafka":             ["apache kafka tutorial", "kafka for beginners", "event streaming kafka"],
    "airflow":           ["apache airflow tutorial", "data pipeline airflow", "workflow orchestration"],
    "dbt":               ["dbt tutorial", "data build tool", "analytics engineering dbt"],
    "snowflake":         ["snowflake tutorial", "snowflake data warehouse", "snowflake sql"],
    "databricks":        ["databricks tutorial", "databricks spark", "delta lake"],
    "cybersecurity":     ["cybersecurity tutorial", "network security", "ethical hacking", "owasp"],
    "flutter":           ["flutter tutorial", "dart flutter", "flutter for beginners",
                          "cross platform mobile"],
    "computer-vision":   ["computer vision tutorial", "opencv tutorial", "image recognition",
                          "cnn computer vision", "object detection"],
    "system-design":     ["system design", "distributed systems", "microservices architecture",
                          "system design interview"],
    "kubernetes":        ["kubernetes tutorial", "k8s tutorial", "container orchestration"],
    "terraform":         ["terraform tutorial", "infrastructure as code", "terraform aws"],
    "mlops":             ["mlops tutorial", "ml pipeline", "model deployment mlops"],
}

# ── 快速通道：跳过技能（key = B vocab skill_id）──────────────────────────
FAST_TRACK_SKIP = {
    "RAG应用工程师":   {"statistics", "machine-learning", "deep-learning",
                       "data-structures", "ab-testing"},
    "Agent应用工程师": {"statistics", "machine-learning", "deep-learning",
                       "data-structures", "ab-testing"},
    "数据分析师":      set(),
    "后端工程师":      {"statistics", "machine-learning", "deep-learning"},
    "前端工程师":      {"statistics", "machine-learning", "deep-learning",
                       "data-structures", "sql-lang"},
    "数据工程师":      {"machine-learning", "deep-learning"},
}

# ── 最全覆盖：各岗位增补扩展技能（选修）──────────────────────────────────
ROLE_ENRICHMENT = {
    "RAG应用工程师":   ["transformer", "fine-tuning", "nlp", "pytorch", "deep-learning"],
    "Agent应用工程师": ["rag", "transformer", "nlp", "embedding", "vector-database"],
    "数据分析师":      ["data-structures", "machine-learning"],
    "后端工程师":      ["data-structures", "numpy", "pandas"],
    "前端工程师":      ["typescript", "nextjs", "nodejs"],
    "数据工程师":      ["airflow", "dbt", "kafka"],
}

# ── 目标岗位核心技能（key = B vocab skill_id）────────────────────────────
TARGET_ROLE_SKILLS = {
    "RAG应用工程师":   ["python", "llm", "prompt-engineering",
                       "embedding", "vector-database", "langchain", "rag", "fastapi"],
    "Agent应用工程师": ["python", "llm", "prompt-engineering",
                       "langchain", "agent", "tool-calling", "fastapi"],
    "数据分析师":      ["python", "sql-lang", "pandas", "numpy",
                       "statistics", "tableau", "ab-testing"],
    "后端工程师":      ["python", "sql-lang", "git", "linux", "fastapi", "docker"],
    "前端工程师":      ["html", "css", "javascript", "typescript", "react", "nodejs"],
    "数据工程师":      ["python", "sql-lang", "spark", "kafka", "airflow", "docker"],
}


# ════════════════════════════════════════════════════════
# 0. DAG 无环显式验证
# ════════════════════════════════════════════════════════
def detect_cycles(skill_data, prereq_map):
    """
    使用 DFS 颜色标记法检测有向图中的环路。
    WHITE=未访问, GRAY=栈中(正在访问), BLACK=已完成。
    返回 (has_cycle: bool, cycle_path: list)。
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in skill_data}
    cycle_path = []

    def dfs(v, path):
        color[v] = GRAY
        path.append(v)
        for nbr in prereq_map.get(v, []):
            if nbr not in color:
                continue
            if color[nbr] == GRAY:
                # 找到环：从 nbr 回到当前节点
                idx = path.index(nbr)
                cycle_path.extend(path[idx:] + [nbr])
                return True
            if color[nbr] == WHITE:
                if dfs(nbr, path):
                    return True
        path.pop()
        color[v] = BLACK
        return False

    for sid in skill_data:
        if color[sid] == WHITE:
            if dfs(sid, []):
                return True, cycle_path
    return False, []


def validate_dag(skill_data, prereq_map):
    """打印DAG验证结果，返回 is_valid: bool"""
    has_cycle, path = detect_cycles(skill_data, prereq_map)
    if has_cycle:
        print(f"[FAIL] DAG验证失败：发现环路 {' -> '.join(path)}")
        return False
    print(f"[OK]   DAG验证通过：{len(skill_data)}个节点，无环路")
    return True


# ════════════════════════════════════════════════════════
# 1. 加载技能图谱
# ════════════════════════════════════════════════════════
def load_skill_graph():
    path = SKILL_GRAPH_PATH if SKILL_GRAPH_PATH.exists() else BASE_DIR / "skill_prerequisite_v1.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    skill_data = {}
    prereq_map = {}
    for s in data["skills"]:
        skill_data[s["skill_id"]] = s
        prereq_map[s["skill_id"]] = s.get("prerequisites", [])
    return skill_data, prereq_map


# ════════════════════════════════════════════════════════
# 2. 加载资源
#    优先：learning_resources_v1.json（预计算索引）
#    降级：原始 CSV 三源匹配
# ════════════════════════════════════════════════════════
def load_resources_from_json():
    """从 learning_resources_v1.json 加载资源，转为内部格式"""
    resources = []
    with open(RESOURCES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    for sid, skill_info in data["skills"].items():
        for r in skill_info["resources"]:
            # 找到对应 resource_id 是否已加入（一个资源可属于多个技能）
            existing = next((x for x in resources if x["resource_id"] == r["resource_id"]), None)
            if existing:
                existing["skill_scores"][sid] = 3
            else:
                resources.append({
                    "resource_id":   r["resource_id"],
                    "title":         r["title"],
                    "url":           r["url"],
                    "source":        r["source"],
                    "hours":         r.get("hours_estimate", 0.0),
                    "difficulty":    r.get("difficulty", "beginner"),
                    "skill_scores":  {sid: 3},
                    "note":          r.get("note", ""),
                })
    return resources


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


def load_resources_from_csv():
    """原始CSV三源加载（降级路径）"""
    resources = []
    bili_path = BILIBILI_PATH if BILIBILI_PATH.exists() else BASE_DIR / "bilibili_resources_C部分.csv"
    try:
        with open(bili_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                tags = [t.strip() for t in row.get("覆盖技能(;分隔)", "").split(";") if t.strip()]
                skill_ids = [BILI_TAG_TO_SKILL[t] for t in tags if t in BILI_TAG_TO_SKILL]
                if not skill_ids:
                    continue
                try:
                    hours = float(row.get("估计时长(小时)", 0) or 0)
                except ValueError:
                    hours = 0.0
                bv = row.get("URL", "").rstrip("/").split("/")[-1]
                resources.append({
                    "resource_id": f"bili_{bv}",
                    "title":  row.get("视频标题", ""),
                    "url":    row.get("URL", ""),
                    "source": "bilibili",
                    "hours":  hours,
                    "difficulty": row.get("难度", "beginner"),
                    "skill_scores": {sid: 3 for sid in skill_ids},
                    "note":   f"UP:{row.get('UP主','')}",
                })
    except FileNotFoundError:
        pass

    try:
        with open(GITHUB_PATH, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                title  = row.get("title", "")
                topics = row.get("topics", "")
                desc   = row.get("description", "")
                scores = _score_resource(title, topics + " " + desc)
                scores = {k: v for k, v in scores.items() if v >= 2}
                if not scores:
                    continue
                resources.append({
                    "resource_id": row.get("resource_id", ""),
                    "title":  title,
                    "url":    row.get("url", ""),
                    "source": "github",
                    "hours":  0.0,
                    "difficulty": row.get("difficulty", "intermediate"),
                    "skill_scores": scores,
                    "note":   f"stars:{row.get('stars','0')}",
                })
    except FileNotFoundError:
        pass

    try:
        with open(COURSERA_PATH, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                title = row.get("title", "")
                body  = row.get("skills_raw", "")
                scores = _score_resource(title, body)
                scores = {k: v for k, v in scores.items() if v >= 2}
                if not scores:
                    continue
                try:
                    hours = float(row.get("hours_estimate", 0) or 0)
                except ValueError:
                    hours = 0.0
                resources.append({
                    "resource_id": row.get("resource_id", ""),
                    "title":  title,
                    "url":    f"https://www.coursera.org/search?query={title.replace(' ','+')}",
                    "source": "coursera",
                    "hours":  hours,
                    "difficulty": row.get("level", "beginner"),
                    "skill_scores": scores,
                    "note":   f"{row.get('institution','')} | rating:{row.get('rating','')}",
                })
    except FileNotFoundError:
        pass
    return resources


def load_resources():
    if RESOURCES_JSON.exists():
        return load_resources_from_json()
    return load_resources_from_csv()


# ════════════════════════════════════════════════════════
# 3. 构建 skill_id → 排序资源列表
# ════════════════════════════════════════════════════════
def build_skill_resource_map(resources, max_per_skill=5):
    """关键词降级匹配：三源均衡选取（各取1条），避免全部来自同一平台。"""
    skill_map = defaultdict(lambda: {"bilibili": [], "coursera": [], "github": []})
    for res in resources:
        src = res.get("source", "other")
        for sid, score in res["skill_scores"].items():
            if src in skill_map[sid]:
                skill_map[sid][src].append((score, res))

    result = {}
    for sid, by_src in skill_map.items():
        # 每源按分数降序，各取最优1条，再补充到 max_per_skill
        picked = []
        for src in ["bilibili", "coursera", "github"]:
            candidates = sorted(by_src[src], key=lambda x: -x[0])
            if candidates:
                picked.append(candidates[0][1])
        # 如果不足 max_per_skill，从剩余资源补充
        used_ids = {r["resource_id"] for r in picked}
        for src in ["bilibili", "coursera", "github"]:
            for _, res in sorted(by_src[src], key=lambda x: -x[0]):
                if len(picked) >= max_per_skill:
                    break
                if res["resource_id"] not in used_ids:
                    picked.append(res)
                    used_ids.add(res["resource_id"])
        result[sid] = picked[:max_per_skill]
    return result


# ════════════════════════════════════════════════════════
# 3b. Embedding 版资源匹配（使用 ST 微调模型）
# ════════════════════════════════════════════════════════
def _build_skill_texts(skill_data):
    """与 embedding_matcher.py 一致的双语技能文本构造"""
    skill_name_map = {sid: s["skill_name"] for sid, s in skill_data.items()}
    texts = {}
    for sid, s in skill_data.items():
        prereq_names = " ".join(
            skill_name_map.get(p, "") for p in s.get("prerequisites", [])
        )
        en_kw = SKILL_EN_KEYWORDS.get(sid, "")
        texts[sid] = (
            f"{s['skill_name']} {s.get('category','')} {prereq_names} "
            f"{en_kw} {s.get('difficulty','')} level{s.get('level',0)}"
        )
    return texts


MIN_GITHUB_STARS = 5   # 低于此星数的 GitHub 资源过滤掉


def _parse_stars(note: str) -> int:
    """从 note 字段解析 stars 数量，支持 'stars:14897' 和 'stars:28k+' 两种格式"""
    if not note:
        return 0
    for part in note.split("|"):
        part = part.strip()
        if part.startswith("stars:"):
            val = part.split(":")[1].strip().replace(",", "").lower().rstrip("+")
            try:
                if val.endswith("k"):
                    return int(float(val[:-1]) * 1000)
                return int(val)
            except ValueError:
                pass
    return 0


def build_skill_resource_map_embedding(resources, skill_data, max_per_skill=5):
    """
    用 ST 微调模型对资源进行语义相似度排序。
    策略：JSON 标注资源 = 候选池（保证相关性），Embedding 在候选池内重排（提升质量）。
    若标注资源不足 max_per_skill 才扩充到全量池。
    """
    model_path = MODEL_DIR / "st_finetuned"
    # 需要同时有目录和权重文件才能加载（config文件单独存在不够）
    if not model_path.exists() or not (model_path / "model.safetensors").exists():
        return None

    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.preprocessing import normalize
        import numpy as np
    except ImportError:
        return None

    print("[Embedding] 加载 ST 微调模型...")
    model = SentenceTransformer(str(model_path))

    # ── 去重全量资源池，并过滤低质量 GitHub ──────────────────────
    unique_res = {}
    for r in resources:
        rid = r["resource_id"]
        if rid in unique_res:
            continue
        # 过滤：GitHub 仓库 stars 不足阈值
        if r.get("source") == "github" and _parse_stars(r.get("note", "")) < MIN_GITHUB_STARS:
            continue
        unique_res[rid] = r

    # ── 按技能分组 JSON 标注资源（已去重、已过滤）────────────────
    skill_labeled = defaultdict(list)   # sid → [resource, ...]
    for rid, r in unique_res.items():
        for sid in r.get("skill_scores", {}):
            skill_labeled[sid].append(rid)

    res_ids   = list(unique_res.keys())
    res_idx   = {rid: i for i, rid in enumerate(res_ids)}
    res_texts = [
        f"{unique_res[rid]['title']} {unique_res[rid].get('source','')} "
        f"{unique_res[rid].get('note','')}"
        for rid in res_ids
    ]
    skill_texts = _build_skill_texts(skill_data)
    skill_ids   = list(skill_texts.keys())

    # ── 批量编码（一次性，避免重复调用 model）────────────────────
    print(f"[Embedding] 编码 {len(res_ids)} 条资源 + {len(skill_ids)} 个技能...")
    r_embs = model.encode(res_texts, batch_size=64, show_progress_bar=False)
    s_embs = model.encode([skill_texts[s] for s in skill_ids],
                          batch_size=64, show_progress_bar=False)
    r_n = normalize(r_embs)
    s_n = normalize(s_embs)
    sim = s_n @ r_n.T   # (n_skills, n_res)

    DISPLAY_PER_STEP = 3   # 每步骤实际展示资源数，用作候选池充足与否的判断阈值

    result = {}
    for i, sid in enumerate(skill_ids):
        labeled_rids = [rid for rid in skill_labeled.get(sid, [])
                        if rid in res_idx]   # 过滤掉已被质量筛除的资源

        if len(labeled_rids) >= DISPLAY_PER_STEP:
            # ✅ 标注资源足够展示：只在标注集内用 Embedding 重排，确保相关性
            candidate_idx = [res_idx[rid] for rid in labeled_rids]
        elif labeled_rids:
            # 标注资源存在但不足3条：标注集优先，全量补充不足部分
            labeled_set  = set(labeled_rids)
            labeled_idx  = [res_idx[rid] for rid in labeled_rids]
            all_ranked   = list(np.argsort(sim[i])[::-1])
            need_extra   = DISPLAY_PER_STEP - len(labeled_idx)
            extra_idx    = [j for j in all_ranked
                            if res_ids[j] not in labeled_set][:need_extra]
            candidate_idx = labeled_idx + extra_idx
        else:
            # 无标注资源：完全依赖 Embedding 从全量选取
            candidate_idx = list(np.argsort(sim[i])[::-1][:max_per_skill])

        if not candidate_idx:
            result[sid] = []
            continue

        # 在候选集内按 Embedding 分数降序
        scored = sorted(candidate_idx, key=lambda j: sim[i, j], reverse=True)
        result[sid] = [unique_res[res_ids[j]] for j in scored[:max_per_skill]]

    print(f"[Embedding] 资源-技能相似度矩阵构建完成 ({sim.shape})")
    return result


def load_resources_with_embedding(skill_data):
    """
    加载资源并选择最优匹配方式：
      - 若 models/st_finetuned/ 存在 → Embedding 语义相似度排序
      - 否则 → 关键词规则降级
    """
    resources = load_resources()
    emb_map   = build_skill_resource_map_embedding(resources, skill_data)
    if emb_map is not None:
        print("[Embedding] 使用 ST 微调模型资源匹配 [OK]")
        return emb_map
    # 降级：关键词规则
    print("[Fallback] 使用关键词规则资源匹配")
    return build_skill_resource_map(resources)


# ════════════════════════════════════════════════════════
# 4. 路径生成核心
# ════════════════════════════════════════════════════════
def get_required_skills(target_skills, user_skills, prereq_map,
                        fast_track_skip=None, enrichment=None):
    """
    BFS反推所有必要前置技能。
    - assume_known：用户已有 + 快速通道跳过的技能，BFS在此处停止
    - enrichment：最全覆盖模式额外追加的扩展技能（可选修）
    """
    assume_known = set(user_skills)
    if fast_track_skip:
        assume_known |= fast_track_skip

    visited  = set()
    queue    = deque()
    required = set()

    seeds = list(target_skills)
    if enrichment:
        seeds += [s for s in enrichment if s not in assume_known]

    for s in seeds:
        if s not in assume_known and s not in visited:
            visited.add(s)
            queue.append(s)

    while queue:
        skill = queue.popleft()
        required.add(skill)
        for prereq in prereq_map.get(skill, []):
            if prereq not in visited and prereq not in assume_known:
                visited.add(prereq)
                queue.append(prereq)

    return required


def topological_sort(required_skills, prereq_map, skill_data, order_by="level"):
    """
    拓扑排序，三种排序策略：
      "level"      — Kahn + 按(level, difficulty)批次排序（最短/最全覆盖策略）
      "easy_first" — 最小堆贪心：始终从当前可学技能里选最简单的
                     保证 beginner 技能全部先于 intermediate，
                     intermediate 全部先于 advanced（在前置满足的前提下）
    """
    skills = set(required_skills)
    successors = defaultdict(list)
    in_degree  = {s: 0 for s in skills}

    for skill in skills:
        for prereq in prereq_map.get(skill, []):
            if prereq in skills:
                successors[prereq].append(skill)
                in_degree[skill] += 1

    def heap_key(s):
        meta = skill_data.get(s, {})
        lv   = meta.get("level", 0)
        diff = DIFFICULTY_NUM.get(meta.get("difficulty", "intermediate"), 2)
        if order_by == "easy_first":
            return (diff, lv, s)   # 最小堆：难度 → 层级 → id 三级稳定排序
        return (lv, diff, s)       # 层级 → 难度 → id

    if order_by == "easy_first":
        # 贪心最小堆：任意时刻从所有「前置已满足」技能中选最简单的
        heap = [heap_key(s) for s in skills if in_degree[s] == 0]
        heapq.heapify(heap)
        ordered = []
        # heapq 存的是 key tuple，最后一项是 skill_id
        while heap:
            key = heapq.heappop(heap)
            skill = key[-1]
            ordered.append(skill)
            for d in successors[skill]:
                in_degree[d] -= 1
                if in_degree[d] == 0:
                    heapq.heappush(heap, heap_key(d))
        return ordered
    else:
        # 批次排序 Kahn（level 优先）
        ready = sorted(
            [s for s in skills if in_degree[s] == 0],
            key=heap_key,
        )
        queue   = deque(ready)
        ordered = []
        while queue:
            skill = queue.popleft()
            ordered.append(skill)
            next_ready = sorted(
                [d for d in successors[skill] if in_degree[d] - 1 == 0],
                key=heap_key,
            )
            for d in successors[skill]:
                in_degree[d] -= 1
            queue.extend(next_ready)
        return ordered


# ════════════════════════════════════════════════════════
# 5. 路径打分
# ════════════════════════════════════════════════════════
def score_path(ordered_skills, skill_data, target_skills, user_skills):
    if not ordered_skills and not user_skills:
        return {"total_hours": 0, "coverage": 0.0, "step_count": 0,
                "avg_difficulty": "-", "difficulty_dist": {}}

    total_hours = sum(skill_data.get(s, {}).get("hours_estimate", 0)
                      for s in ordered_skills)
    diffs = [DIFFICULTY_NUM.get(skill_data.get(s, {}).get("difficulty", "intermediate"), 2)
             for s in ordered_skills] or [1]
    avg_d = sum(diffs) / len(diffs)
    avg_diff_label = ("beginner" if avg_d < 1.5 else
                      ("advanced"  if avg_d > 2.5 else "intermediate"))

    target_set = set(target_skills)
    already    = len(target_set & set(user_skills))
    new_cover  = len(target_set & set(ordered_skills))
    coverage   = round((already + new_cover) / len(target_set), 2) if target_set else 0.0

    dist = {"beginner": 0, "intermediate": 0, "advanced": 0}
    for s in ordered_skills:
        d = skill_data.get(s, {}).get("difficulty", "intermediate")
        dist[d] = dist.get(d, 0) + 1

    return {
        "total_hours":     total_hours,
        "avg_difficulty":  avg_diff_label,
        "coverage":        coverage,
        "step_count":      len(ordered_skills),
        "difficulty_dist": dist,
    }


# ════════════════════════════════════════════════════════
# 6. 生成单条学习计划
# ════════════════════════════════════════════════════════
def generate_plan(user_skills, target_role, skill_data, prereq_map,
                  resource_map, strategy="shortest"):
    """
    strategy:
      "shortest"   — 快速通道，跳过理论基础，步骤最少，实用优先
      "easy_first" — 完整前置路径，由易到难排序，适合零基础
      "full_cover" — 完整路径+扩展技能，系统性最强，覆盖最全
    """
    target_skills = TARGET_ROLE_SKILLS.get(target_role, [])

    if strategy == "shortest":
        skip_set    = FAST_TRACK_SKIP.get(target_role, set())
        enrichment  = None
        order_by    = "level"
    elif strategy == "easy_first":
        skip_set    = set()
        enrichment  = None
        order_by    = "easy_first"
    else:  # full_cover
        skip_set    = set()
        enrichment  = ROLE_ENRICHMENT.get(target_role, [])
        order_by    = "level"

    required = get_required_skills(
        target_skills, user_skills, prereq_map,
        fast_track_skip=skip_set,
        enrichment=enrichment,
    )
    ordered  = topological_sort(required, prereq_map, skill_data, order_by=order_by)
    score    = score_path(ordered, skill_data, target_skills, user_skills)

    MAX_REUSE = 2
    resource_use_count = defaultdict(int)   # 跨步骤：同一资源最多出现 MAX_REUSE 次
    title_use_count    = defaultdict(int)   # 跨步骤：同一标题最多出现 MAX_REUSE 次

    steps = []
    for i, sid in enumerate(ordered, 1):
        sk         = skill_data.get(sid, {})
        candidates = resource_map.get(sid, [])
        deduped    = []
        step_seen_rids   = set()   # 步骤内去重：同一资源 ID 只出现一次
        step_seen_titles = set()   # 步骤内去重：同一标题只出现一次
        for r in candidates:
            rid       = r["resource_id"]
            title_key = r["title"].strip().lower()
            # 步骤内不重复 + 跨步骤不超过 MAX_REUSE
            if (rid not in step_seen_rids
                    and title_key not in step_seen_titles
                    and resource_use_count[rid] < MAX_REUSE
                    and title_use_count[title_key] < MAX_REUSE):
                deduped.append(r)
                step_seen_rids.add(rid)
                step_seen_titles.add(title_key)
                resource_use_count[rid]    += 1
                title_use_count[title_key] += 1
            if len(deduped) >= 3:
                break

        steps.append({
            "step":       i,
            "skill_id":   sid,
            "skill_name": sk.get("skill_name", sid),
            "category":   sk.get("category", ""),
            "hours":      sk.get("hours_estimate", 0),
            "difficulty": sk.get("difficulty", ""),
            "resources": [
                {"title": r["title"], "url": r["url"],
                 "source": r["source"], "note": r["note"]}
                for r in deduped
            ],
        })

    skill_name_map = {sid: skill_data[sid]["skill_name"]
                      for sid in skill_data if "skill_name" in skill_data[sid]}
    gap_ids = sorted(set(target_skills) - set(user_skills))

    return {
        "target_role":  target_role,
        "strategy":     strategy,
        "user_skills":  sorted(user_skills),
        "gap_skills":   gap_ids,
        "gap_skills_cn": [skill_name_map.get(s, s) for s in gap_ids],
        "score":        score,
        "steps":        steps,
    }


# ════════════════════════════════════════════════════════
# 7. 三策略对比生成
# ════════════════════════════════════════════════════════
def generate_all_strategies(user_skills, target_role, skill_data,
                            prereq_map, resource_map):
    """同时生成三条候选路径供用户选择"""
    strategies = ["shortest", "easy_first", "full_cover"]
    results = {}
    for s in strategies:
        results[s] = generate_plan(
            user_skills, target_role, skill_data, prereq_map, resource_map,
            strategy=s,
        )
    return results


# ════════════════════════════════════════════════════════
# 8. 渲染 Markdown
# ════════════════════════════════════════════════════════
STRATEGY_LABEL = {
    "shortest":   "[最短路径] 快速通道",
    "easy_first": "[最低难度] 由易到难",
    "full_cover": "[最全覆盖] 系统学习",
}

def render_plan_md(plan):
    score    = plan["score"]
    dist     = score.get("difficulty_dist", {})
    mode_tag = STRATEGY_LABEL.get(plan["strategy"], plan["strategy"])

    lines = [
        f"## 目标岗位：{plan['target_role']}  {mode_tag}",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总学时 | **{score['total_hours']}h** |",
        f"| 学习步骤 | **{score['step_count']} 步** |",
        f"| 目标技能覆盖 | **{int(score['coverage']*100)}%** |",
        f"| 平均难度 | **{score['avg_difficulty']}** |",
        f"| 难度分布 | 入门{dist.get('beginner',0)}步 / 中级{dist.get('intermediate',0)}步 /"
        f" 进阶{dist.get('advanced',0)}步 |",
        f"",
        f"**用户已有**：{', '.join(plan['user_skills']) or '零基础'}",
        f"**缺口技能**：{', '.join(plan.get('gap_skills_cn', plan['gap_skills']))}",
        f"",
        "---",
        "",
    ]

    for step in plan["steps"]:
        d    = step["difficulty"]
        icon = {"beginner": "[入门]", "intermediate": "[中级]",
                "advanced": "[进阶]"}.get(d, "")
        lines.append(f"### Step {step['step']}. {step['skill_name']} {icon}")
        lines.append(f"- 分类：{step['category']}　学时：{step['hours']}h　难度：{d}")
        if step["resources"]:
            lines.append("- 推荐资源：")
            for r in step["resources"]:
                lines.append(f"  - [{r['title']}]({r['url']}) `{r['source']}` {r['note']}")
        else:
            lines.append("- 推荐资源：暂无匹配，建议手动补充")
        lines.append("")

    return "\n".join(lines)


def render_strategy_comparison_md(role, all_plans, user_skills_label=""):
    """渲染三策略对比摘要表（含前3步技能顺序，展示ordering差异）"""
    skill_orders = {
        s: [step["skill_id"] for step in all_plans[s]["steps"]]
        for s in ["shortest", "easy_first", "full_cover"]
    }
    # 判断 shortest 与 easy_first 是否路径等效
    equiv_note = ""
    if skill_orders["shortest"] == skill_orders["easy_first"]:
        equiv_note = "  *(注：该场景下最短路径与最低难度路径完全等效，见下方说明)*"

    lines = [
        f"## 三策略对比摘要 — {role} {user_skills_label}",
        "",
        f"| 策略 | 步骤数 | 总学时 | 目标覆盖 | 平均难度 | 前3步技能顺序 |",
        f"|------|--------|--------|----------|----------|--------------|",
    ]
    for s in ["shortest", "easy_first", "full_cover"]:
        plan  = all_plans[s]
        score = plan["score"]
        label = STRATEGY_LABEL[s]
        top3  = " → ".join(step["skill_name"] for step in plan["steps"][:3])
        # 标注等效路径
        equiv_marker = " (≡最短)" if (s == "easy_first" and
                                       skill_orders["shortest"] == skill_orders["easy_first"]) else ""
        lines.append(
            f"| {label}{equiv_marker} | {score['step_count']}步 | {score['total_hours']}h"
            f" | {int(score['coverage']*100)}% | {score['avg_difficulty']}"
            f" | {top3} |"
        )
    lines.append("")
    lines.append("> **选路说明**")
    lines.append("> - **最短路径**：跳过理论基础直达应用层，步骤最少，适合有一定背景、追求速成的学习者")
    lines.append("> - **最低难度**：完整前置链路，贪心优先选最简单的可学技能，适合零基础逐步进阶")
    lines.append("> - **最全覆盖**：完整路径+扩展技能，含底层原理，适合追求系统掌握的学习者")
    if equiv_note:
        lines.append(f">")
        lines.append(f"> {equiv_note.strip()}")
        lines.append(f"> 等效原因：该岗位无需跳过理论基础（FAST_TRACK_SKIP=空集），")
        lines.append(f"> 或用户已有技能覆盖了快速通道的跳过项，两条路径所需技能集合完全一致。")
    lines.append("")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════
# 主程序
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== services/path_planner_v1.py  v2.0 ===\n")

    skill_data, prereq_map = load_skill_graph()
    print(f"[OK] 技能节点: {len(skill_data)}")

    # DAG 验证（显式输出 + 保存报告文件）
    is_valid = validate_dag(skill_data, prereq_map)

    # 计算节点入度/出度，写入 reports/dag_validation.json
    in_deg  = defaultdict(int)
    out_deg = defaultdict(int)
    for sid, prereqs in prereq_map.items():
        for p in prereqs:
            out_deg[p] += 1
            in_deg[sid] += 1

    dag_report = {
        "validation_date": str(date.today()),
        "algorithm": "DFS三色标记法（WHITE/GRAY/BLACK）",
        "result": "PASS" if is_valid else "FAIL",
        "has_cycle": not is_valid,
        "graph_stats": {
            "total_nodes": len(skill_data),
            "root_nodes": [s for s in skill_data if in_deg[s] == 0],
            "leaf_nodes": [s for s in skill_data if out_deg[s] == 0],
            "direct_edges": len([
                (sid, p) for sid, plist in prereq_map.items() for p in plist
            ]),
        },
    }
    dag_report_path = BASE_DIR / "reports" / "dag_validation.json"
    dag_report_path.parent.mkdir(parents=True, exist_ok=True)
    dag_report_path.write_text(
        json.dumps(dag_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] DAG验证报告: {dag_report_path}")

    resource_map = load_resources_with_embedding(skill_data)
    covered      = sum(1 for sid in skill_data if resource_map.get(sid))
    src_label    = ("ST微调模型 + learning_resources_v1.json"
                    if (MODEL_DIR / "st_finetuned").exists()
                    else "关键词规则 + CSV三源")
    print(f"[OK] 资源匹配: {src_label}")
    print(f"[OK] 有资源技能: {covered}/{len(skill_data)}\n")

    test_cases = [
        {"label": "RAG应用工程师（仅Python基础）",
         "user_skills": {"sk_python_basic", "sk_git"},
         "target_role": "RAG应用工程师"},
        {"label": "Agent应用工程师（有ML/DL基础）",
         "user_skills": {"sk_python_basic", "sk_pandas", "sk_numpy",
                         "sk_ml_basic", "sk_dl_basic", "sk_git"},
         "target_role": "Agent应用工程师"},
        {"label": "数据分析师（零基础）",
         "user_skills": set(),
         "target_role": "数据分析师"},
        {"label": "后端工程师（有Python+SQL）",
         "user_skills": {"sk_python_basic", "sk_sql_basic"},
         "target_role": "后端工程师"},
    ]

    md_parts  = ["# C部分 学习路径评估报告（三策略版）",
                 f"生成日期：{date.today()}", ""]
    all_plans_export = []

    for tc in test_cases:
        print(f"[{tc['label']}]")
        all_s = generate_all_strategies(
            user_skills=tc["user_skills"],
            target_role=tc["target_role"],
            skill_data=skill_data,
            prereq_map=prereq_map,
            resource_map=resource_map,
        )
        # 控制台对比
        for s_name in ["shortest", "easy_first", "full_cover"]:
            plan  = all_s[s_name]
            score = plan["score"]
            print(f"  {STRATEGY_LABEL[s_name]:18s}: "
                  f"步骤={score['step_count']:2d}  总学时={score['total_hours']:4d}h  "
                  f"覆盖={int(score['coverage']*100):3d}%  难度={score['avg_difficulty']}")
        print()

        # Markdown 报告
        md_parts.append(render_strategy_comparison_md(
            tc["target_role"], all_s, f"（{tc['label']}）"))
        for s_name in ["shortest", "easy_first", "full_cover"]:
            md_parts.append(render_plan_md(all_s[s_name]))
            md_parts.append("\n---\n")

        all_plans_export.append({
            "case": tc["label"],
            "plans": {k: v for k, v in all_s.items()}
        })

    # 保存报告
    report_path = BASE_DIR / "reports" / "path_eval_v1.md"
    report_path.write_text("\n".join(md_parts), encoding="utf-8")
    print(f"[OK] 报告已保存: {report_path}")

    json_path = BASE_DIR / "reports" / "path_plans_sample.json"
    json_path.write_text(
        json.dumps(all_plans_export, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] JSON已保存: {json_path}")
