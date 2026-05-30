"""
细粒度岗位聚类 - 分层版

输入:data/silver/all_jd_skills_v1.jsonl
输出:
  data/gold/fine_grained_roles_v1.json
  data/gold/job_skill_profile_v1.json

核心策略:
  1. 不再直接读三份原始数据,统一读取 extract_all_skills.py 的产物
  2. emerging 单独聚类,避免被 14 万 Djinni 大类淹没
  3. 聚类文本使用 title + search_keyword + skills + JD 摘要
  4. 命名优先看 search_keyword 和技能画像,不是只看 title

运行:
  python -m pipelines.taxonomy.cluster_roles
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

IN_JSONL = Path("data/silver/all_jd_skills_v1.jsonl")
OUT_ROLES = Path("data/gold/fine_grained_roles_v1.json")
OUT_PROFILE = Path("data/gold/job_skill_profile_v1.json")

MODEL_NAME = "TechWolf/JobBERT-v3"
RANDOM_STATE = 42
TOP_SKILLS = 15
TOP_TITLES = 8
TOP_KEYWORDS = 8

TRADITIONAL_SAMPLE_PER_BUCKET = int(os.environ.get("TRADITIONAL_SAMPLE_PER_BUCKET", "5000"))
EMERGING_SAMPLE = int(os.environ.get("EMERGING_SAMPLE", "20000"))

NON_IT_KEYWORDS = {
    "marketing", "sales", "hr", "recruiter", "lead generation", "artist",
    "seo", "support", "technical writing",
}

COARSE_PRIORITY = [
    "emerging_ai",
    "ai_data",
    "backend",
    "frontend",
    "mobile",
    "devops_cloud",
    "qa_testing",
    "security",
    "game",
    "pm_ba",
    "other_it",
]

COARSE_LABELS = {
    "emerging_ai": "Emerging AI",
    "ai_data": "AI & Data",
    "backend": "Backend Development",
    "frontend": "Frontend Development",
    "mobile": "Mobile Development",
    "devops_cloud": "Cloud Native & DevOps",
    "qa_testing": "QA & Testing",
    "security": "Security",
    "game": "Game Development",
    "pm_ba": "Product & Business Analysis",
    "other_it": "Other IT",
}

COARSE_RULES = {
    "ai_data": {
        "skills": {
            "Machine Learning", "Deep Learning", "Data Science", "Data Analysis",
            "Data Engineering", "Computer Vision", "NLP", "Apache Spark", "Hadoop",
            "ETL", "Data Warehouse", "Data Pipeline", "Tableau", "Power BI",
        },
        "keywords": {"data", "machine learning", "ai", "analyst", "scientist"},
    },
    "backend": {
        "skills": {
            "Java", "Python", "Go", "C#", ".NET", "PHP", "Ruby", "Spring",
            "Django", "FastAPI", "Flask", "Laravel", "Node.js", "API",
            "REST API", "Microservices",
        },
        "keywords": {"java", "python", "backend", "node.js", ".net", "php", "golang", "ruby"},
    },
    "frontend": {
        "skills": {
            "JavaScript", "TypeScript", "React", "Vue.js", "Angular", "HTML",
            "CSS", "Redux", "Webpack", "Sass", "Next.js",
        },
        "keywords": {"javascript", "frontend", "front-end", "react", "angular", "vue"},
    },
    "mobile": {
        "skills": {"Android", "iOS", "Kotlin", "Swift", "Flutter", "React Native"},
        "keywords": {"android", "ios", "flutter", "mobile"},
    },
    "devops_cloud": {
        "skills": {
            "DevOps", "Docker", "Kubernetes", "AWS", "Microsoft Azure", "Google Cloud",
            "Terraform", "Ansible", "Jenkins", "CI/CD", "Linux", "Prometheus",
            "Grafana", "Helm",
        },
        "keywords": {"devops", "sysadmin", "cloud", "infrastructure", "platform"},
    },
    "qa_testing": {
        "skills": {"QA Automation", "Selenium", "Playwright", "Appium", "JMeter", "Unit Testing", "Jest"},
        "keywords": {"qa", "testing", "automation"},
    },
    "security": {
        "skills": {"Cybersecurity", "OAuth", "JWT", "Encryption", "IAM"},
        "keywords": {"security", "cybersecurity"},
    },
    "game": {
        "skills": {"Unity", "Unreal Engine", "C++", "C#"},
        "keywords": {"unity", "game", "unreal"},
    },
    "pm_ba": {
        "skills": {"Agile", "Scrum", "Jira", "Confluence", "Data Analysis"},
        "keywords": {"product manager", "project manager", "business analyst", "scrum master"},
    },
}

EMERGING_NAME_RULES = [
    ("RAG Engineer", {"RAG", "LangChain", "LlamaIndex", "Vector Database"}),
    ("AI Agent Engineer", {"AI Agent", "Agentic AI", "MCP", "LangGraph", "Tool Calling"}),
    ("LLMOps Engineer", {"LLMOps", "MLOps", "Model Serving"}),
    ("LLM Fine-tuning Engineer", {"Fine-tuning", "LoRA", "PEFT", "Hugging Face"}),
    ("Vector Search Engineer", {"Vector Database", "Vector Search", "Pinecone", "Milvus", "Weaviate"}),
    ("AI Evaluation Engineer", {"AI Evaluation", "LLM Evaluation", "Evals"}),
    ("Multimodal AI Engineer", {"Multimodal", "Computer Vision"}),
    ("Recommendation Systems Engineer", {"Recommendation System", "Ranking"}),
]

EMERGING_KEYWORD_NAMES = [
    ("AI Product Manager", {"ai product manager"}),
    ("Forward Deployed AI Engineer", {"forward deployed engineer", "ai delivery engineer"}),
    ("AI Solutions Architect", {"ai solutions architect"}),
    ("AI Infrastructure Engineer", {"ai infrastructure engineer"}),
    ("MLOps Engineer", {"mlops engineer", "ml platform engineer"}),
    ("LLMOps Engineer", {"llmops engineer"}),
    ("Inference Engineer", {"inference engineer"}),
    ("Embedding Engineer", {"embedding engineer"}),
    ("RAG Engineer", {"rag engineer", "langchain developer"}),
    ("AI Agent Engineer", {"ai agent engineer", "agentic ai engineer"}),
    ("Prompt Engineer", {"prompt engineer", "context engineer"}),
    ("AI Evaluation Engineer", {"ai evaluation engineer"}),
    ("Multimodal AI Engineer", {"multimodal engineer"}),
    ("Computer Vision Engineer", {"computer vision engineer"}),
    ("NLP Engineer", {"nlp engineer", "conversational ai engineer"}),
    ("LLM Fine-tuning Engineer", {"llm fine-tuning engineer"}),
    ("Recommendation Systems Engineer", {"recommendation system engineer"}),
    ("LLM Engineer", {"llm engineer", "foundation model engineer", "generative ai engineer"}),
    ("AI Research Engineer", {"ai research engineer", "deep learning engineer"}),
    ("Applied AI Engineer", {"applied ai engineer", "ai software engineer", "ai engineer"}),
]

LOW_SIGNAL_SKILLS = {
    "Excel", "Oracle Database", "C", "R", "Go", "Agile", "Jira", "Scrum",
    "Confluence", "Data Analysis", "Statistics",
}

REJECT_ROLE_TERMS = {
    "account manager", "finance manager", "brand manager", "graphic designer",
    "product marketing manager", "sales", "recruiter", "hr manager",
}


def read_records() -> pd.DataFrame:
    if not IN_JSONL.exists():
        raise FileNotFoundError(f"未找到 {IN_JSONL},请先运行 python -m pipelines.extract.extract_all_skills")

    rows = []
    with IN_JSONL.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["skills"] = df["skills"].apply(lambda x: x if isinstance(x, list) else [])
    df["skill_ids"] = df["skill_ids"].apply(lambda x: x if isinstance(x, list) else [])
    df["title"] = df["title"].fillna("")
    df["text"] = df["text"].fillna("")
    df["search_keyword"] = df["search_keyword"].fillna("")
    return df


def is_noise(row) -> bool:
    kw = str(row.search_keyword).lower()
    title = str(row.title).lower()
    if row.source == "emerging":
        return False
    if kw in NON_IT_KEYWORDS:
        return True
    return any(term in title for term in ["nurse", "medical", "sales manager", "brand manager"])


def assign_coarse(row) -> str:
    if row.source == "emerging":
        return "emerging_ai"

    skills = set(row.skills)
    keyword = str(row.search_keyword).lower()
    title = str(row.title).lower()
    haystack = f"{keyword} {title}"

    best_name, best_score = "other_it", 0
    for name, rule in COARSE_RULES.items():
        score = len(skills & rule["skills"])
        score += sum(2 for kw in rule["keywords"] if kw in haystack)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def cluster_text(row) -> str:
    skills = ", ".join(row.skills[:25])
    return (
        f"Title: {row.title}. Search keyword: {row.search_keyword}. "
        f"Skills: {skills}. Description: {str(row.text)[:700]}"
    )


def choose_k(n: int, coarse: str) -> int:
    if n < 80:
        return 1
    if coarse == "emerging_ai":
        return min(32, max(8, round(math.sqrt(n / 18))))
    return min(18, max(3, round(math.sqrt(n / 60))))


def sample_bucket(df: pd.DataFrame, coarse: str) -> pd.DataFrame:
    limit = EMERGING_SAMPLE if coarse == "emerging_ai" else TRADITIONAL_SAMPLE_PER_BUCKET
    if len(df) <= limit:
        return df.reset_index(drop=True)
    return df.sample(limit, random_state=RANDOM_STATE).reset_index(drop=True)


def top_list(values, n: int) -> list[str]:
    counter = Counter(v for v in values if v)
    return [v for v, _ in counter.most_common(n)]


def top_skills(rows: pd.DataFrame, n: int = TOP_SKILLS) -> tuple[list[str], list[str], dict]:
    counter = Counter()
    id_by_name = {}
    for _, row in rows.iterrows():
        for name, sid in zip(row.skills, row.skill_ids):
            counter[name] += 1
            id_by_name.setdefault(name, sid)
    names = [name for name, _ in counter.most_common(n)]
    cluster_size = len(rows)
    # 全部技能的簇内频率(不止 top n,留给 postprocess 做 core/optional 阈值过滤)
    skill_freq = {name: round(cnt / cluster_size, 4) for name, cnt in counter.items()}
    return names, [id_by_name.get(name) for name in names], skill_freq


def keyword_words(rows: pd.DataFrame, n: int = TOP_KEYWORDS) -> list[str]:
    text = " ".join(str(x) for x in rows["search_keyword"].tolist() + rows["title"].head(200).tolist())
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", text.lower())
    stop = {"engineer", "developer", "senior", "middle", "junior", "lead", "manager", "specialist"}
    return [w for w, _ in Counter(w for w in words if w not in stop).most_common(n)]


def infer_emerging_name(rows: pd.DataFrame, skills: list[str], search_keywords: list[str]) -> str | None:
    skill_set = set(skills)
    keyword_text = " ".join(search_keywords).lower()

    for name, keywords in EMERGING_KEYWORD_NAMES:
        if any(keyword in keyword_text for keyword in keywords):
            return name

    for name, required in EMERGING_NAME_RULES:
        # 至少命中明确细分技能;Machine Learning/LLM 这种泛技能不单独决定岗位名
        if len(skill_set & required) >= 1:
            return name
    return None


def infer_name(rows: pd.DataFrame, coarse: str, skills: list[str], search_keywords: list[str]) -> str:
    if coarse == "emerging_ai":
        name = infer_emerging_name(rows, skills, search_keywords)
        if name:
            return name

    keyword = search_keywords[0] if search_keywords else ""
    if keyword and keyword.lower() not in {"other", "lead"}:
        return keyword

    titles = top_list(rows["title"], TOP_TITLES)
    if titles:
        title = titles[0]
        title = re.sub(r"(?i)\b(senior|junior|middle|lead|principal|staff|sr\.?|jr\.?)\b", "", title)
        title = re.sub(r"\s+", " ", title).strip(" -/")
        if title:
            return title

    return COARSE_LABELS.get(coarse, coarse)


def role_quality_ok(role: dict) -> bool:
    """过滤明显不适合作为最终细粒度岗位的低质量簇。"""
    name_text = " ".join(
        [role["role_name"]]
        + role.get("search_keywords", [])
        + role.get("example_titles", [])[:5]
    ).lower()
    if any(term in name_text for term in REJECT_ROLE_TERMS):
        return False

    skills = set(role.get("required_skills", []))
    strong_skills = skills - LOW_SIGNAL_SKILLS

    if role["coarse_key"] == "emerging_ai":
        keyword_text = " ".join(role.get("search_keywords", [])).lower()
        emerging_signal = any(
            keyword in keyword_text
            for _, keywords in EMERGING_KEYWORD_NAMES
            for keyword in keywords
        )
        # emerging 描述很短,允许 keyword 强但技能少;否则至少要有两个强技能
        return emerging_signal or len(strong_skills) >= 2

    if role["coarse_key"] == "other_it":
        return len(strong_skills) >= 3

    return True


def make_role_id(coarse: str, idx: int) -> str:
    return f"{coarse}_{idx:02d}"


def build_roles_for_bucket(model, bucket: pd.DataFrame, coarse: str) -> list[dict]:
    bucket = sample_bucket(bucket, coarse)
    k = choose_k(len(bucket), coarse)
    print(f"    {coarse}: n={len(bucket)}, k={k}")

    if k == 1:
        labels = np.zeros(len(bucket), dtype=int)
    else:
        texts = [cluster_text(row) for row in bucket.itertuples(index=False)]
        vecs = model.encode(texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)
        labels = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit_predict(vecs)

    bucket = bucket.copy()
    bucket["cluster"] = labels

    roles = []
    for cluster_id in sorted(bucket["cluster"].unique()):
        sub = bucket[bucket["cluster"] == cluster_id]
        skills, skill_ids, skill_freq = top_skills(sub)
        search_keywords = top_list(sub["search_keyword"], TOP_KEYWORDS)
        titles = top_list(sub["title"], TOP_TITLES)
        role_name = infer_name(sub, coarse, skills, search_keywords)
        local_idx = len(roles)
        role_id = make_role_id(coarse, local_idx)

        roles.append({
            "role_id": role_id,
            "role_name": role_name,
            "fine_role": role_name,
            "coarse_role": COARSE_LABELS.get(coarse, coarse),
            "coarse_key": coarse,
            "size": int(len(sub)),
            "source_mix": dict(Counter(sub["source"])),
            "search_keywords": search_keywords,
            "example_titles": titles,
            "keywords": keyword_words(sub),
            "required_skills": skills,
            "required_skill_ids": skill_ids,
            "skill_freq": skill_freq,
        })

    roles = [role for role in roles if role_quality_ok(role)]
    roles.sort(key=lambda r: (-r["size"], r["role_name"]))
    return roles


def deduplicate_names(roles: list[dict]) -> list[dict]:
    seen = Counter()
    for role in roles:
        key = (role["coarse_key"], role["role_name"])
        seen[key] += 1
        if seen[key] > 1:
            base = role["role_name"].lower()
            candidates = role.get("search_keywords", []) + role.get("required_skills", [])
            hint = None
            for candidate in candidates:
                c = str(candidate).strip()
                if c and c.lower() not in base and c.lower() not in {"other", "lead"}:
                    hint = c
                    break
            if not hint:
                hint = f"细分{seen[key]}"
            role["role_name"] = f"{role['role_name']}({hint})"
            role["fine_role"] = role["role_name"]
    return roles


def main() -> None:
    OUT_ROLES.parent.mkdir(parents=True, exist_ok=True)

    print(">>> 1/5 读取统一技能数据 ...")
    df = read_records()
    print(f"    原始记录: {len(df)}")

    print(">>> 2/5 过滤噪声并分配大类 ...")
    df = df[~df.apply(is_noise, axis=1)].copy()
    df = df[df["skills"].apply(len) > 0].copy()
    df["coarse_key"] = df.apply(assign_coarse, axis=1)
    print(f"    保留记录: {len(df)}")
    print(f"    大类分布: {dict(Counter(df['coarse_key']))}")

    print(">>> 3/5 加载向量模型 ...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)

    print(">>> 4/5 分层聚类 ...")
    all_roles = []
    for coarse in COARSE_PRIORITY:
        bucket = df[df["coarse_key"] == coarse]
        if bucket.empty:
            continue
        all_roles.extend(build_roles_for_bucket(model, bucket, coarse))

    all_roles = deduplicate_names(all_roles)
    all_roles.sort(key=lambda r: (COARSE_PRIORITY.index(r["coarse_key"]), -r["size"], r["role_name"]))

    # 全局重编号,便于下游稳定读取
    profile = {}
    for idx, role in enumerate(all_roles):
        role["role_id"] = f"role_{idx:03d}"
        profile[role["role_id"]] = {
            "role_name": role["role_name"],
            "fine_role": role["fine_role"],
            "coarse_role": role["coarse_role"],
            "required_skills": role["required_skills"],
            "required_skill_ids": role["required_skill_ids"],
        }

    print(">>> 5/5 写出岗位库和技能画像 ...")
    with OUT_ROLES.open("w", encoding="utf-8") as f:
        json.dump(all_roles, f, ensure_ascii=False, indent=2)
    with OUT_PROFILE.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"    已写出: {OUT_ROLES}")
    print(f"    已写出: {OUT_PROFILE}")
    print(f"    岗位簇总数: {len(all_roles)}")
    for role in all_roles[:20]:
        print(f"    [{role['role_id']}] {role['coarse_role']} / {role['role_name']} n={role['size']}")


if __name__ == "__main__":
    main()
