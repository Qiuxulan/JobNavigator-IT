"""
Djinni 技能抽取 - 词典匹配版(全量)

思路:用 asaniczka 已有的技能名组成词表 -> 在 Djinni JD 正文里扫描匹配
优点:与 asaniczka 风格统一、无碎片、无模型、快
产出:data/gold/djinni_skill_match_v1.json
运行:python -m pipelines.extract.match_djinni_skills
"""

import re
import json
from collections import Counter

import pandas as pd

ASANICZKA_SKILLS_CSV = "data/raw/asaniczka/job_skills.csv"
DJINNI_CSV = "data/raw/djinni/djinni_jd.csv"
OUT_JSON = "data/gold/djinni_skill_match_v1.json"
N_PREVIEW = 8          # 控制台只打印前几条效果,JSON 写全量
MIN_SKILL_FREQ = 3     # 技能在 asaniczka 出现少于这个次数就不要(去掉长尾噪声)
MIN_SKILL_LEN = 2      # 技能名太短(如单字母)丢弃
MAX_SKILLS_PER_JD = 30 # 单条 JD 最多保留多少技能,防止极长 JD 引入噪声
REGEX_CHUNK_SIZE = 300 # 合并正则时每组技能数,避免一次性正则过大
PROGRESS_EVERY = 5000  # 每处理多少条打印一次进度

IT_KEYWORDS = {
    ".net", "ab test", "abap", "airflow", "algorithm", "android", "angular",
    "ansible", "apache", "api", "appium", "architecture", "asp.net", "asyncio",
    "aurora", "aws", "azure", "backend", "bash", "bert", "bigquery", "bitbucket",
    "blockchain", "bootstrap", "c#", "c++", "c/c++", "cassandra", "chatgpt",
    "ci/cd", "clickhouse", "cloud", "cloudformation", "computer vision",
    "container", "cplusplus", "css", "cuda", "cybersecurity", "dagster",
    "data analysis", "data analytics", "data engineering", "data lake",
    "data mining", "data modeling", "data science", "data visualization",
    "database", "databricks", "db2", "deep learning", "devops", "django",
    "docker", "dynamodb", "elasticsearch", "electron", "etl", "express",
    "fastapi", "figma", "firebase", "flask", "flutter", "frontend", "gcp",
    "git", "github", "gitlab", "go", "golang", "grafana", "graphql", "hadoop",
    "helm", "hibernate", "html", "ios", "java", "javascript", "jenkins",
    "jira", "jmeter", "jquery", "json", "jupyter", "jwt", "kafka", "keras",
    "kotlin", "kubernetes", "langchain", "linux", "llm", "machine learning",
    "matlab", "microservice", "mongodb", "mysql", "neo4j", "next.js", "nlp",
    "node", "node.js", "nosql", "numpy", "oauth", "opencv", "oracle",
    "pandas", "php", "playwright", "postgres", "postgresql", "power bi",
    "powershell", "pytorch", "qa automation", "rabbitmq", "rag", "react",
    "react native", "redis", "redux", "rest", "rust", "scala", "scikit",
    "scrum", "selenium", "shell", "snowflake", "spark", "spring", "sql",
    "sqlite", "swift", "tableau", "tensorflow", "terraform", "typescript",
    "ui/ux", "unity", "unix", "unreal", "vue", "web3", "webpack", "xml",
}

GENERIC_TERMS = {
    "ability", "abilities", "analysis", "applications", "business", "career growth",
    "collaboration", "communication", "communication skills", "compensation",
    "competitive compensation", "customer satisfaction", "development", "developers",
    "developing", "digital", "digital marketing", "engineering", "environment",
    "equal employment opportunity", "equal opportunity", "experience",
    "implementation", "knowledge", "marketing", "paid vacation", "prototypes",
    "relationships", "remote work",
    "requirements", "requirements:", "software development", "technologies",
    "understanding", "work experience",
}


def is_it_skill(skill: str) -> bool:
    """只保留 IT 技术栈相关词,过滤软技能/业务词/福利词。"""
    s = skill.strip(" *-").lower()
    if not s or s in GENERIC_TERMS:
        return False
    if re.search(r"\b\d+\+?\s*(year|years|yr|yrs)\b", s):
        return False
    if re.search(r"\bexperience\s+(with|in|using)\b", s):
        return False
    if re.search(r"\b(experience|expertise|certification|certifications|certified)\b", s):
        return False
    if len(s.split()) > 8:
        return False
    if s in IT_KEYWORDS:
        return True
    return any(keyword in s for keyword in IT_KEYWORDS if len(keyword) >= 3)


def build_vocab():
    """从 asaniczka job_skills 列收集技能词表"""
    df = pd.read_csv(ASANICZKA_SKILLS_CSV)
    counter = Counter()
    for s in df["job_skills"].dropna():
        for sk in str(s).split(","):
            sk = sk.strip(" *-")
            if sk:
                counter[sk] += 1
    # 过滤低频和过短
    freq_vocab = {
        sk.strip()
        for sk, c in counter.items()
        if c >= MIN_SKILL_FREQ and len(sk.strip()) >= MIN_SKILL_LEN
    }
    vocab = {sk for sk in freq_vocab if is_it_skill(sk)}
    print(f"    asaniczka 原始技能: {len(counter)} 种")
    print(f"    频次过滤后词表: {len(freq_vocab)} 种 (freq>={MIN_SKILL_FREQ})")
    print(f"    IT技能过滤后词表: {len(vocab)} 种")
    return vocab


def make_patterns(vocab):
    """把多个技能合并成分块正则,避免 14 万 JD * 1 万技能的双重循环。"""
    skills = sorted(vocab, key=lambda s: (-len(s), s.lower()))
    patterns = []
    for i in range(0, len(skills), REGEX_CHUNK_SIZE):
        chunk = skills[i:i + REGEX_CHUNK_SIZE]
        alternatives = "|".join(re.escape(sk) for sk in chunk)
        pattern = re.compile(
            r"(?<![A-Za-z0-9])(" + alternatives + r")(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        # lower -> canonical,用于把大小写不同的命中统一回词表写法
        canonical = {sk.lower(): sk for sk in chunk}
        patterns.append((pattern, canonical))
    return patterns


def match_skills(text, patterns):
    text = str(text)
    found = set()
    for pat, canonical in patterns:
        for m in pat.finditer(text):
            sk = canonical.get(m.group(1).lower(), m.group(1))
            found.add(sk)
            if len(found) >= MAX_SKILLS_PER_JD:
                break
        if len(found) >= MAX_SKILLS_PER_JD:
            break
    # 长技能通常更具体,同长度时按字母序保证输出稳定
    found = sorted(found, key=lambda s: (-len(s), s.lower()))
    return found[:MAX_SKILLS_PER_JD]


def main():
    print(">>> 1/3 从 asaniczka 构建技能词表 ...")
    vocab = build_vocab()
    patterns = make_patterns(vocab)

    print(">>> 2/3 读取 Djinni ...")
    df = pd.read_csv(DJINNI_CSV)
    df = df.dropna(subset=["Long Description"])
    df = df[df["Long Description"].str.len() > 100]
    print(f"    Djinni 有效 JD: {len(df)}")

    print(">>> 3/3 全量匹配 Djinni 技能 ...\n")
    records = []
    non_empty = 0
    total = len(df)
    for pos, (idx, row) in enumerate(df.iterrows(), start=1):
        skills = match_skills(row["Long Description"], patterns)
        if skills:
            non_empty += 1

        record = {
            "id": str(row.get("id", idx)),
            "title": str(row.get("Position", "")),
            "primary_keyword": str(row.get("Primary Keyword", "")),
            "matched_skills": skills,
            "skill_count": len(skills),
        }
        records.append(record)

        if len(records) <= N_PREVIEW:
            print(f"岗位: {record['title']}")
            print(f"  匹配技能({len(skills)}): {', '.join(skills[:15])}")
            print()
        elif pos % PROGRESS_EVERY == 0:
            coverage = non_empty / pos if pos else 0
            print(f"    进度: {pos}/{total} ({pos / total:.1%}), 当前覆盖率={coverage:.1%}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    coverage = non_empty / len(records) if records else 0
    print(f"已写出: {OUT_JSON}")
    print(f"全量 JD: {len(records)}")
    print(f"匹配到至少 1 个技能: {non_empty} ({coverage:.1%})")
    print("下一步:运行 pipelines/taxonomy/cluster_roles.py,聚类会自动读取该文件。")


if __name__ == "__main__":
    main()
    
