# JobNavigator-IT 行业趋势预测模块落地方案（MVP修订版）

> 版本：2026-06-07  
> 目标：在已有“69个标准岗位 + 岗位别名 + 相关技术词表”的基础上，完成一个**大学生项目可落地**的行业趋势预测模块。  
> 关键词：岗位标准化、JD趋势、GDELT新闻情绪、技术热度、PatchTST、RAG解释、后续Agent接入。

---

## 0. 本版方案相对上一版的调整

上一版方案偏“研究型全量系统”，这版改为**最小可行但逻辑完整**：

1. 不再追求覆盖所有招聘平台、所有事件类型、所有技术指标。
2. 不再把技术热度、GDELT事件都复杂映射到技能图谱后再匹配岗位。
3. 直接利用你们已经完成的**69个岗位标准库、岗位别名、岗位相关技术**进行匹配。
4. JD数据只保留与趋势预测相关的主要字段。
5. GDELT不拿全量事件，也不提人物实体、事件根类别、地理实体等复杂字段，只抽取新闻语义、情绪和证据链接。
6. 技术热度只选少数核心指标：Google Trends搜索兴趣、GitHub仓库活跃度、arXiv论文关注度。
7. 建模部分只保留MVP流程：特征构建 → 时间序列对齐 → PatchTST预测。暂时不做复杂对比模型。
8. 后续Agent接入时，只需要把本模块封装成查询接口，不需要大改整体流程。

---

## 1. 总体目标

本模块的目标不是预测“未来市场上会有多少个真实岗位”，而是预测：

- 某个IT岗位未来一段时间的**相对需求强度**；
- 某个岗位相关技术在招聘市场中的**出现趋势**；
- 社会事件、技术热度、招聘需求之间是否存在**同向或反向变化**；
- 为后续职业推荐Agent提供“为什么这个岗位在上升/下降”的解释依据。

最终输出建议为：

```json
{
  "canonical_role": "AI Agent Engineer",
  "horizon_months": 3,
  "trend_direction": "up",
  "predicted_demand_index": 0.73,
  "confidence": 0.68,
  "main_factors": [
    "JD中AI Agent相关岗位与别名出现频率上升",
    "GitHub中agentic AI、LangChain、RAG相关仓库活跃度较高",
    "GDELT中企业AI应用和自动化相关新闻情绪整体偏正面"
  ],
  "evidence_urls": [
    "..."
  ]
}
```

---

## 2. 已有数据基础：69个标准岗位库

你们已经完成了岗位匹配部分，有69个标准岗位、岗位别名和相关技术。这是行业预测模块的核心锚点。后续所有外部数据都要回到这69个岗位上，而不是重新从外部数据里聚类岗位。

### 2.1 标准岗位库建议格式

建议将已有岗位整理成一个 `role_taxonomy.csv` 或 `role_taxonomy.json`。

推荐字段：

| 字段名 | 含义 | 示例 |
|---|---|---|
| role_id | 岗位编号 | 2 |
| category | 岗位大类 | AI Engineering |
| canonical_role | 标准岗位名 | AI Agent Engineer |
| aliases | 岗位别名，英文列表 | agentic AI engineer; AI software engineer; generative AI engineer |
| top_skills | 该岗位最重要的10个技术词 | LLM; RAG; LangChain; vector database; Python; API; agent framework |
| existing_jd_count | 你们已有岗位库中的JD数 | 1313 |

示例：

```csv
role_id,category,canonical_role,aliases,top_skills,existing_jd_count
1,AI Engineering,Machine Learning Engineer,"ML platform engineer; inference engineer; deep learning engineer; NLP engineer; AI engineer","Python; PyTorch; TensorFlow; model training; inference; ML platform; NLP; deep learning; MLOps; Kubernetes",1684
2,AI Engineering,AI Agent Engineer,"agentic AI engineer; AI software engineer; generative AI engineer","LLM; AI agent; agentic AI; LangChain; RAG; tool calling; vector database; Python; prompt engineering; LLMOps",1313
12,AI Engineering,RAG Engineer,"generative AI engineer; AI software engineer; vector database engineer","RAG; vector database; embeddings; retrieval; LangChain; LlamaIndex; Python; LLM; semantic search; reranking",380
42,Cloud Native & DevOps,DevOps Engineer,"DevOps; Sysadmin; Python; Security; Java; Golang","Docker; Kubernetes; CI/CD; Linux; Terraform; AWS; Azure; monitoring; Python; DevOps",2239
69,Other IT,Rust Blockchain Engineer,"C++; Rust; Scala","Rust; blockchain; smart contract; Web3; cryptography; distributed system; Solana; Ethereum; C++; backend",271
```

### 2.2 本项目的匹配策略

三类外部数据的匹配方法不同：

| 数据来源 | 是否必须用技术词匹配 | 推荐匹配方式 |
|---|---:|---|
| JD招聘数据 | 不必须 | 岗位名称 + 别名为主，JD全文技能命中为辅 |
| GDELT社会事件 | 必须双关联 | 岗位名称/别名 + 该岗位10个重要技术词 |
| 技术热度 | 主要用技术词 | 直接使用你们已有岗位相关技术词表，不重新构建技术词表 |

这样做的原因是：

- JD本身就是岗位数据，原始岗位名称和别名最重要；
- GDELT是新闻数据，不一定直接出现岗位名，因此要同时匹配岗位名和关键技术；
- 技术热度本身就是技术关键词热度，不需要绕回JD再抽技能。

---

## 3. 数据源选择：只保留两个较新的英文JD来源

旧版方案中提到Kaggle的LinkedIn历史数据、Data Science岗位数据等，但这些数据多数停留在2023-2024年。如果你们要覆盖AI Agent Engineer、Context Engineer、RAG Engineer、LLM Inference Engineer等新兴岗位，历史数据可能缺失。因此本版建议优先使用**实时/近实时英文岗位API**。

经过检索，推荐两个数据源：

### 3.1 数据源一：JSearch Jobs API（主数据源）

#### 适合原因

JSearch提供来自Google for Jobs和公开网页的实时招聘数据，覆盖LinkedIn、Indeed、Glassdoor、ZipRecruiter等多个发布源。它适合做主数据源，因为它有较完整的JD字段，包括：岗位标题、公司、发布源、完整JD描述、发布时间、地点、薪资、工作安排、经验年限、教育要求、所需技术等。

#### 关键字段

建议保留：

| 原始字段 | 统一字段 | 说明 |
|---|---|---|
| job_id | source_job_id | 原始岗位ID |
| job_title | raw_job_title | 原始岗位名称 |
| job_description | raw_jd_text | 原始JD全文 |
| job_min_salary / job_max_salary / job_salary | salary_mid | 薪资中位值 |
| job_posted_at_datetime_utc | post_date | 发布时间 |
| education_required | education_required | 学历要求 |
| required_experience_years | experience_required_years | 经验年限 |
| employer_name | company_name | 公司名称 |
| work_arrangement / job_is_remote | work_arrangement | 远程/混合/现场 |
| job_apply_link / job_google_link | job_url | 证据链接 |

其中，用户要求保留的核心字段是：

- 原始岗位名称；
- 原始JD全文；
- 薪资中位值；
- 发布时间；
- 学历要求；
- 经验要求。

额外建议保留两个趋势解释有价值字段：

- `company_name`：用于去重和判断大厂/中小企业扩张情况；
- `work_arrangement`：用于分析远程/混合/现场岗位趋势。

#### JSearch采集代码

```python
import os
import time
import requests
import pandas as pd
from typing import Dict, List, Optional

JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY")
JSEARCH_URL = "https://api.openwebninja.com/jsearch/search-v2"


def calc_salary_mid(min_salary, max_salary, salary=None):
    """计算薪资中位值。"""
    try:
        if min_salary is not None and max_salary is not None:
            return (float(min_salary) + float(max_salary)) / 2
        if salary is not None:
            return float(salary)
    except Exception:
        return None
    return None


def normalize_jsearch_item(item: Dict, query_role: str) -> Dict:
    edu = item.get("education_required")
    if isinstance(edu, dict):
        edu_level = edu.get("level")
    else:
        edu_level = edu

    return {
        "source": "jsearch",
        "query_role": query_role,
        "source_job_id": item.get("job_id"),
        "raw_job_title": item.get("job_title"),
        "raw_jd_text": item.get("job_description"),
        "salary_min": item.get("job_min_salary"),
        "salary_max": item.get("job_max_salary"),
        "salary_mid": calc_salary_mid(
            item.get("job_min_salary"),
            item.get("job_max_salary"),
            item.get("job_salary")
        ),
        "salary_period": item.get("job_salary_period"),
        "post_date": item.get("job_posted_at_datetime_utc"),
        "education_required": edu_level,
        "experience_required_years": item.get("required_experience_years"),
        "seniority_level": item.get("seniority_level"),
        "company_name": item.get("employer_name"),
        "work_arrangement": item.get("work_arrangement"),
        "job_location": item.get("job_location"),
        "job_url": item.get("job_apply_link") or item.get("job_google_link"),
        "required_technologies": item.get("required_technologies"),
        "preferred_technologies": item.get("preferred_technologies"),
        "raw_json": item,
    }


def fetch_jsearch_jobs(query: str,
                       country: str = "us",
                       language: str = "en",
                       max_pages: int = 3,
                       date_posted: Optional[str] = "month") -> List[Dict]:
    """
    使用JSearch搜索岗位。
    query示例：'AI Agent Engineer jobs in United States'
    date_posted可以尝试：today / 3days / week / month，具体以API返回为准。
    """
    headers = {"x-api-key": JSEARCH_API_KEY}
    all_items = []
    cursor = None

    for _ in range(max_pages):
        params = {
            "query": query,
            "country": country,
            "language": language,
        }
        if date_posted:
            params["date_posted"] = date_posted
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(JSEARCH_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("data", [])
        all_items.extend(items)

        # search-v2 推荐使用cursor分页。不同版本返回字段名可能略有差异，做兼容处理。
        cursor = data.get("cursor") or data.get("next_cursor") or data.get("nextPageCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_items


def collect_jsearch_by_roles(role_taxonomy: pd.DataFrame,
                             max_pages_per_role: int = 2) -> pd.DataFrame:
    rows = []
    for _, role in role_taxonomy.iterrows():
        canonical_role = role["canonical_role"]
        aliases = str(role.get("aliases", "")).split(";")

        # 只用标准岗位名+前2个别名，避免查询过长。
        queries = [canonical_role] + [a.strip() for a in aliases[:2] if a.strip()]

        for q in queries:
            search_query = f'"{q}" jobs in United States'
            try:
                items = fetch_jsearch_jobs(search_query, max_pages=max_pages_per_role)
                for item in items:
                    rows.append(normalize_jsearch_item(item, query_role=canonical_role))
            except Exception as e:
                print(f"JSearch failed: {search_query} -> {e}")
            time.sleep(1)

    return pd.DataFrame(rows)
```

---

### 3.2 数据源二：RemoteOK API（补充新兴远程技术岗位）

#### 适合原因

RemoteOK的优势是新兴远程技术岗位多，尤其是AI、Web3、Rust、React、Node.js、DevOps等技术栈岗位，适合补充新兴岗位的JD文本和薪资区间。它不是全量招聘市场，但对你们的69个IT岗位，尤其是AI和远程开发类岗位，有较强补充价值。

#### 关键字段

建议保留：

| 原始字段 | 统一字段 | 说明 |
|---|---|---|
| id | source_job_id | 原始岗位ID |
| position | raw_job_title | 原始岗位名称 |
| description | raw_jd_text | JD全文 |
| salary_min / salary_max | salary_mid | 薪资中位值 |
| date | post_date | 发布时间 |
| tags | source_tags | 技术标签 |
| company | company_name | 公司名称 |
| location | work_arrangement / location | 远程范围 |
| url / apply_url | job_url | 证据链接 |

RemoteOK不一定直接给学历和经验要求，因此学历、经验可以从JD全文中用正则或LLM轻量抽取。

#### RemoteOK采集代码

```python
import re
import requests
import pandas as pd
from typing import Dict, List

REMOTEOK_URL = "https://remoteok.com/api"


def extract_experience_years(text: str):
    """从JD文本中粗略抽取经验年限。"""
    if not isinstance(text, str):
        return None
    patterns = [
        r"(\d+)\+?\s*years? of experience",
        r"(\d+)\+?\s*yrs? of experience",
        r"minimum of (\d+)\s*years?",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return int(m.group(1))
    return None


def extract_education_required(text: str):
    """从JD文本中粗略抽取学历要求。"""
    if not isinstance(text, str):
        return None
    t = text.lower()
    if "phd" in t or "ph.d" in t or "doctorate" in t:
        return "PhD"
    if "master" in t or "ms degree" in t or "m.s." in t:
        return "Master"
    if "bachelor" in t or "bs degree" in t or "b.s." in t:
        return "Bachelor"
    return None


def normalize_remoteok_item(item: Dict, query_role: str) -> Dict:
    desc = item.get("description") or ""
    salary_mid = calc_salary_mid(item.get("salary_min"), item.get("salary_max"))

    return {
        "source": "remoteok",
        "query_role": query_role,
        "source_job_id": item.get("id"),
        "raw_job_title": item.get("position"),
        "raw_jd_text": desc,
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
        "salary_mid": salary_mid,
        "salary_period": "YEAR",
        "post_date": item.get("date"),
        "education_required": extract_education_required(desc),
        "experience_required_years": extract_experience_years(desc),
        "seniority_level": None,
        "company_name": item.get("company"),
        "work_arrangement": "remote",
        "job_location": item.get("location"),
        "job_url": item.get("url") or item.get("apply_url"),
        "source_tags": item.get("tags"),
        "raw_json": item,
    }


def fetch_remoteok_all() -> List[Dict]:
    headers = {"User-Agent": "JobNavigator-IT research project"}
    resp = requests.get(REMOTEOK_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # RemoteOK第一个对象有时是legal/metadata，不是岗位。
    jobs = [x for x in data if isinstance(x, dict) and x.get("id") and x.get("position")]
    return jobs


def collect_remoteok_by_roles(role_taxonomy: pd.DataFrame) -> pd.DataFrame:
    all_jobs = fetch_remoteok_all()
    rows = []

    for _, role in role_taxonomy.iterrows():
        canonical_role = role["canonical_role"]
        aliases = [x.strip() for x in str(role.get("aliases", "")).split(";") if x.strip()]
        skills = [x.strip() for x in str(role.get("top_skills", "")).split(";") if x.strip()]
        terms = [canonical_role] + aliases + skills[:10]
        terms_lower = [t.lower() for t in terms]

        for job in all_jobs:
            text = " ".join([
                str(job.get("position", "")),
                str(job.get("description", "")),
                " ".join(job.get("tags", []) or [])
            ]).lower()
            if any(t.lower() in text for t in terms_lower):
                rows.append(normalize_remoteok_item(job, query_role=canonical_role))

    return pd.DataFrame(rows)
```

---

## 4. JD原始字段设计：保留少数但关键字段

### 4.1 原始JD表：`raw_jd_jobs`

不需要保留太细的字段，只保留下面这些。

| 字段名 | 类型 | 是否核心 | 说明 |
|---|---|---:|---|
| source | str | 是 | jsearch / remoteok |
| source_job_id | str | 是 | 原始数据源ID，用于去重 |
| raw_job_title | str | 是 | 原始岗位名称 |
| raw_jd_text | str | 是 | 原始JD全文 |
| salary_mid | float | 是 | 薪资中位值，salary_min和salary_max的均值 |
| post_date | datetime | 是 | 发布时间 |
| education_required | str | 是 | 学历要求 |
| experience_required_years | float | 是 | 经验要求年限 |
| company_name | str | 建议保留 | 公司名称，用于去重、解释和观察招聘主体 |
| work_arrangement | str | 建议保留 | remote / hybrid / onsite |
| job_url | str | 技术字段 | RAG解释时展示证据链接 |

### 4.2 处理后JD表：`processed_jd_jobs`

在原始字段基础上增加岗位标准化结果。

| 字段名 | 说明 |
|---|---|
| canonical_role | 映射到69个标准岗位之一 |
| role_match_score | 岗位匹配分数 |
| matched_by | title / alias / skill / mixed |
| matched_alias | 命中的别名 |
| matched_skills | 命中的岗位关键技术 |
| month | 发布时间所在月份 |
| jd_demand_weight | 该JD对岗位需求指数的权重 |

---

## 5. 岗位标准化：基于69岗位+别名+关键技术

### 5.1 为什么岗位标准化重要

外部JD中的岗位名称非常混乱。例如：

- `AI Software Engineer` 可能对应 `AI Agent Engineer`、`Applied AI Engineer` 或 `AI Engineer`；
- `ML Platform Engineer` 可能对应 `Machine Learning Engineer`、`MLOps Engineer` 或 `AI Data Engineer`；
- `Generative AI Engineer` 可能对应 `AI Agent Engineer`、`RAG Engineer` 或 `LLM Inference Engineer`。

因此不能只按原始标题统计频次，必须统一映射到你们已有的69个标准岗位。

### 5.2 MVP匹配规则

建议采用“标题/别名优先 + 技术命中辅助”的规则。

分数设计：

```text
final_score = 0.70 * title_alias_score + 0.30 * skill_score
```

其中：

- `title_alias_score`：原始岗位标题与标准岗位名、别名的匹配程度；
- `skill_score`：JD全文中命中的该岗位top10技术词比例。

判断逻辑：

| 情况 | 处理方式 |
|---|---|
| 标题直接包含标准岗位名 | 高置信匹配 |
| 标题直接包含别名 | 高置信匹配 |
| 标题模糊相似，但JD技能也命中 | 中高置信匹配 |
| 标题不相似，但技能命中很多 | 低置信，需要保守处理 |
| 多个岗位分数接近 | 取最高分，同时记录候选岗位 |

### 5.3 岗位标准化代码

```python
import re
from rapidfuzz import fuzz


def clean_text(x: str) -> str:
    if not isinstance(x, str):
        return ""
    x = x.lower()
    x = re.sub(r"[^a-z0-9\+\#\.\s/-]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def split_terms(x: str):
    if not isinstance(x, str):
        return []
    return [t.strip() for t in re.split(r"[;|,，、]", x) if t.strip()]


def phrase_hit(term: str, text: str) -> bool:
    term = clean_text(term)
    text = clean_text(text)
    if not term:
        return False
    # 对C++、C#、.NET等特殊词，不强行加词边界。
    if any(s in term for s in ["c++", "c#", ".net", "node.js"]):
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def compute_title_alias_score(raw_title: str, canonical_role: str, aliases: list):
    title = clean_text(raw_title)
    candidates = [canonical_role] + aliases

    best_score = 0
    best_term = None
    best_type = None

    for term in candidates:
        t = clean_text(term)
        if not t:
            continue
        if phrase_hit(t, title):
            score = 1.0
        else:
            score = fuzz.token_set_ratio(title, t) / 100
        if score > best_score:
            best_score = score
            best_term = term
            best_type = "canonical" if term == canonical_role else "alias"

    return best_score, best_term, best_type


def compute_skill_score(jd_text: str, skills: list):
    if not skills:
        return 0.0, []
    hits = []
    for skill in skills:
        if phrase_hit(skill, jd_text):
            hits.append(skill)
    return len(hits) / min(len(skills), 10), hits


def standardize_one_jd(row: dict, role_taxonomy: pd.DataFrame):
    raw_title = row.get("raw_job_title", "")
    jd_text = row.get("raw_jd_text", "") or ""
    full_text = raw_title + "\n" + jd_text

    best = None
    candidates = []

    for _, role in role_taxonomy.iterrows():
        canonical = role["canonical_role"]
        aliases = split_terms(role.get("aliases", ""))
        skills = split_terms(role.get("top_skills", ""))[:10]

        title_score, matched_term, match_type = compute_title_alias_score(raw_title, canonical, aliases)
        skill_score, matched_skills = compute_skill_score(full_text, skills)

        final_score = 0.70 * title_score + 0.30 * skill_score

        item = {
            "canonical_role": canonical,
            "role_match_score": final_score,
            "title_alias_score": title_score,
            "skill_score": skill_score,
            "matched_alias": matched_term,
            "matched_skills": matched_skills,
            "matched_by": "mixed" if matched_skills and title_score < 1 else match_type,
        }
        candidates.append(item)
        if best is None or final_score > best["role_match_score"]:
            best = item

    # 阈值可调。建议先用0.55，人工看一些样本再调。
    if best["role_match_score"] < 0.55:
        best["canonical_role"] = None
        best["matched_by"] = "unmatched"

    return best


def standardize_jd_dataframe(jd_df: pd.DataFrame, role_taxonomy: pd.DataFrame) -> pd.DataFrame:
    results = []
    for _, row in jd_df.iterrows():
        result = standardize_one_jd(row.to_dict(), role_taxonomy)
        results.append(result)

    result_df = pd.DataFrame(results)
    out = pd.concat([jd_df.reset_index(drop=True), result_df], axis=1)
    out["post_date"] = pd.to_datetime(out["post_date"], errors="coerce")
    out["month"] = out["post_date"].dt.to_period("M").astype(str)
    return out
```

---

## 6. JD趋势特征构建

### 6.1 月度岗位特征表：`jd_role_month_features`

按“岗位-月份”聚合即可，不要太复杂。

| 字段名 | 说明 |
|---|---|
| month | 月份 |
| canonical_role | 标准岗位 |
| jd_count | 该月该岗位JD数量 |
| salary_mid_median | 薪资中位数 |
| avg_experience_years | 平均经验要求 |
| bachelor_or_above_ratio | 本科及以上要求比例 |
| remote_ratio | 远程岗位比例 |
| high_confidence_ratio | 高置信岗位匹配比例 |

### 6.2 JD需求指数

由于原始JD数量不完整，不建议直接把 `jd_count` 当真实需求。建议构建归一化后的岗位需求指数：

```text
jd_demand_index = log(1 + jd_count) 的时间序列归一化值
```

代码：

```python
import numpy as np


def build_jd_month_features(processed_jd: pd.DataFrame) -> pd.DataFrame:
    df = processed_jd.copy()
    df = df[df["canonical_role"].notna()]

    df["is_remote"] = df["work_arrangement"].fillna("").str.lower().str.contains("remote")
    df["is_high_conf"] = df["role_match_score"] >= 0.75
    df["is_bachelor_or_above"] = df["education_required"].fillna("").str.lower().str.contains(
        "bachelor|master|phd|doctor"
    )

    g = df.groupby(["month", "canonical_role"]).agg(
        jd_count=("source_job_id", "nunique"),
        salary_mid_median=("salary_mid", "median"),
        avg_experience_years=("experience_required_years", "mean"),
        bachelor_or_above_ratio=("is_bachelor_or_above", "mean"),
        remote_ratio=("is_remote", "mean"),
        high_confidence_ratio=("is_high_conf", "mean"),
    ).reset_index()

    g["jd_demand_raw"] = np.log1p(g["jd_count"])

    # 在每个岗位内部做0-1归一化。
    def minmax(s):
        if s.max() == s.min():
            return s * 0 + 0.5
        return (s - s.min()) / (s.max() - s.min())

    g["jd_demand_index"] = g.groupby("canonical_role")["jd_demand_raw"].transform(minmax)
    return g
```

---

## 7. GDELT社会事件情绪：字段简化与筛选方法

### 7.1 GDELT在本项目中的定位

GDELT不是用来统计“事件数量越多，岗位越热”，而是用来判断：

- 与某岗位/技术相关的新闻整体是正面还是负面；
- 是否存在外部冲击，如监管、投资、裁员、安全事故、数据泄露、AI争议；
- 这些事件可能对岗位需求产生正向机会还是负向风险。

### 7.2 不需要的字段

本项目不需要：

- 事件根类别；
- CAMEO事件编码；
- 人物实体；
- 复杂地理坐标；
- Actor1、Actor2；
- 原始事件网络图。

这些字段对大学生项目来说解释成本高、噪声大，也不直接服务岗位趋势预测。

### 7.3 只保留的字段

GDELT处理后只保留：

| 字段名 | 说明 |
|---|---|
| month | 月份 |
| canonical_role | 标准岗位 |
| query_terms | 查询词，包括岗位名、别名、top10技能 |
| article_title | 新闻标题，作为解释证据 |
| article_url | 新闻链接 |
| source_domain | 新闻来源 |
| seendate | 新闻时间 |
| avg_tone | 平均情绪，正数偏正面，负数偏负面 |
| positive_score | 正向词强度，主要来自GKG V2Tone |
| negative_score | 负向词强度，主要来自GKG V2Tone |
| gdelt_sentiment_index | 归一化后的事件情绪指数 |
| impact_direction | positive / negative / mixed / neutral |
| impact_score | 对岗位的影响强度 |

### 7.4 岗位 + 重要技术 双关联模式

每个岗位构造GDELT查询时使用：

```text
岗位标准名 + 岗位别名 + 该岗位top10技术词
```

同时再加上事件影响关键词组：

#### 正向事件关键词

```text
investment, funding, adoption, partnership, expansion, growth, launch,
breakthrough, productivity, automation, enterprise adoption, open source
```

#### 负向事件关键词

```text
layoffs, job cuts, hiring freeze, lawsuit, regulation, ban, outage,
data breach, cyberattack, privacy concern, AI safety concern, backlash
```

#### 公众反应关键词

```text
public concern, public support, public backlash, user complaint,
consumer complaint, worker protest, controversy, criticism, concern
```

### 7.5 查询构造示例

以 `AI Agent Engineer` 为例：

```text
("AI Agent Engineer" OR "agentic AI engineer" OR "AI software engineer" OR "generative AI engineer" OR "AI agent" OR "LangChain" OR "RAG" OR "tool calling" OR "vector database")
AND
("investment" OR "adoption" OR "funding" OR "regulation" OR "privacy concern" OR "AI safety concern" OR "backlash" OR "productivity")
```

以 `Cloud Security Engineer` 为例：

```text
("Cloud Security Engineer" OR "Security" OR "DevOps" OR "cloud security" OR "AWS security" OR "Azure security" OR "data breach" OR "cyberattack")
AND
("data breach" OR "cyberattack" OR "ransomware" OR "regulation" OR "privacy concern" OR "investment" OR "adoption")
```

### 7.6 GDELT DOC API代码：近期新闻情绪和证据

DOC API适合抓近期新闻，尤其是最近三个月内的新闻情绪和文章证据。

```python
import requests
import pandas as pd
from urllib.parse import quote

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

POSITIVE_EVENT_TERMS = [
    "investment", "funding", "adoption", "partnership", "expansion", "growth",
    "launch", "breakthrough", "productivity", "automation", "enterprise adoption", "open source"
]

NEGATIVE_EVENT_TERMS = [
    "layoffs", "job cuts", "hiring freeze", "lawsuit", "regulation", "ban",
    "outage", "data breach", "cyberattack", "privacy concern", "AI safety concern", "backlash"
]

PUBLIC_REACTION_TERMS = [
    "public concern", "public support", "public backlash", "user complaint",
    "consumer complaint", "worker protest", "controversy", "criticism", "concern"
]


def gdelt_quote(term: str) -> str:
    term = term.strip()
    if " " in term or "+" in term or "." in term:
        return f'"{term}"'
    return term


def build_gdelt_query_for_role(role_row: pd.Series,
                               max_aliases: int = 4,
                               max_skills: int = 10) -> str:
    role_terms = [role_row["canonical_role"]]
    role_terms += split_terms(role_row.get("aliases", ""))[:max_aliases]
    role_terms += split_terms(role_row.get("top_skills", ""))[:max_skills]

    # 去重，避免query过长。
    role_terms = list(dict.fromkeys([x for x in role_terms if x]))

    event_terms = POSITIVE_EVENT_TERMS + NEGATIVE_EVENT_TERMS + PUBLIC_REACTION_TERMS
    event_terms = list(dict.fromkeys(event_terms))

    role_block = " OR ".join(gdelt_quote(x) for x in role_terms)
    event_block = " OR ".join(gdelt_quote(x) for x in event_terms)

    return f"({role_block}) ({event_block})"


def fetch_gdelt_timeline_tone(query: str,
                              startdatetime: str = None,
                              enddatetime: str = None,
                              timespan: str = "3months") -> dict:
    params = {
        "query": query,
        "mode": "timelinetone",
        "format": "json",
    }
    if startdatetime and enddatetime:
        params["startdatetime"] = startdatetime
        params["enddatetime"] = enddatetime
    else:
        params["timespan"] = timespan

    resp = requests.get(GDELT_DOC_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_gdelt_articles(query: str,
                         maxrecords: int = 50,
                         timespan: str = "3months",
                         sort: str = "datedesc") -> pd.DataFrame:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "timespan": timespan,
        "sort": sort,
    }
    resp = requests.get(GDELT_DOC_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    articles = data.get("articles", [])
    rows = []
    for a in articles:
        rows.append({
            "article_title": a.get("title"),
            "article_url": a.get("url"),
            "source_domain": a.get("domain"),
            "seendate": a.get("seendate"),
            "language": a.get("language"),
            "source_country": a.get("sourcecountry"),
        })
    return pd.DataFrame(rows)


def collect_gdelt_recent_by_roles(role_taxonomy: pd.DataFrame,
                                  maxrecords_per_role: int = 30) -> pd.DataFrame:
    rows = []
    for _, role in role_taxonomy.iterrows():
        canonical_role = role["canonical_role"]
        query = build_gdelt_query_for_role(role)

        try:
            articles = fetch_gdelt_articles(query, maxrecords=maxrecords_per_role)
            if len(articles) > 0:
                articles["canonical_role"] = canonical_role
                articles["query_terms"] = query
                rows.append(articles)
        except Exception as e:
            print(f"GDELT failed: {canonical_role} -> {e}")

    if rows:
        return pd.concat(rows, ignore_index=True)
    return pd.DataFrame()
```

### 7.7 GDELT长期情绪：BigQuery GKG方案

如果你们需要2024-2026这样的长期月度序列，不建议下载GDELT全量文件。GDELT官方数据非常大，应该用BigQuery查询后只导出聚合结果。

MVP只需要GKG字段：

- `DATE`：新闻时间；
- `DocumentIdentifier`：文章URL；
- `SourceCommonName`：来源域名；
- `V2Themes`：主题；
- `V2Tone`：情绪字段。

`V2Tone`通常可以拆成：

```text
AvgTone, PositiveScore, NegativeScore, Polarity, ActivityReferenceDensity, SelfGroupReferenceDensity, WordCount
```

BigQuery SQL模板：

```sql
-- 替换 role_regex 为某个岗位的关键词正则，例如：
-- r'ai agent|agentic ai|langchain|rag|tool calling|vector database'

WITH base AS (
  SELECT
    DATE_TRUNC(
      DATE(PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING))),
      MONTH
    ) AS month,
    DocumentIdentifier AS article_url,
    SourceCommonName AS source_domain,
    V2Themes,
    SPLIT(V2Tone, ',') AS tone_arr
  FROM `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE _PARTITIONTIME BETWEEN TIMESTAMP('2024-01-01') AND TIMESTAMP('2026-06-30')
    AND REGEXP_CONTAINS(
      LOWER(CONCAT(
        IFNULL(DocumentIdentifier, ''), ' ',
        IFNULL(V2Themes, '')
      )),
      r'ai agent|agentic ai|langchain|rag|tool calling|vector database'
    )
    AND REGEXP_CONTAINS(
      LOWER(CONCAT(IFNULL(DocumentIdentifier, ''), ' ', IFNULL(V2Themes, ''))),
      r'investment|funding|adoption|growth|layoffs|hiring freeze|regulation|data breach|cyberattack|privacy concern|backlash|controversy'
    )
)

SELECT
  month,
  AVG(SAFE_CAST(tone_arr[SAFE_OFFSET(0)] AS FLOAT64)) AS avg_tone,
  AVG(SAFE_CAST(tone_arr[SAFE_OFFSET(1)] AS FLOAT64)) AS positive_score,
  AVG(SAFE_CAST(tone_arr[SAFE_OFFSET(2)] AS FLOAT64)) AS negative_score,
  COUNT(*) AS article_count
FROM base
GROUP BY month
ORDER BY month;
```

### 7.8 GDELT影响指数构建

不要直接把文章数量当核心变量。文章数量只作为置信度或热度背景。核心变量是情绪和影响方向。

建议：

```text
gdelt_sentiment_index = normalized(avg_tone)

gdelt_risk_index = normalized(negative_score)

gdelt_opportunity_index = normalized(positive_score)

impact_score = 0.5 * gdelt_sentiment_index + 0.3 * opportunity_index - 0.2 * risk_index
```

但是要注意，负面新闻不一定让岗位需求下降。例如：

- 数据泄露新闻情绪负面，但可能提升安全岗位需求；
- AI监管新闻情绪中性或负面，但可能提升AI Governance、AI Evaluation、Security、Data Privacy岗位需求；
- 科技裁员新闻负面，通常对整体招聘需求是负面。

因此MVP中可以加入简单规则：

```python
SECURITY_ROLES = {
    "Cloud Security Engineer", "Information Security Analyst",
    "Security Operations Engineer", "Penetration Testing Engineer", "Security Software Engineer"
}

AI_GOVERNANCE_RELATED = {
    "AI Evaluation Engineer", "AI Solutions Architect", "AI Engineer", "AI Agent Engineer"
}


def infer_event_impact_direction(canonical_role: str, article_title: str, avg_tone: float = None):
    text = clean_text(article_title)

    # 安全事故：对安全岗位是机会，对普通岗位是风险。
    if any(k in text for k in ["data breach", "cyberattack", "ransomware", "privacy concern"]):
        if canonical_role in SECURITY_ROLES:
            return "positive"
        return "negative"

    # AI监管：对AI评测、合规、安全、解决方案类岗位可能是机会。
    if any(k in text for k in ["ai regulation", "ai safety", "privacy", "compliance"]):
        if canonical_role in AI_GOVERNANCE_RELATED or canonical_role in SECURITY_ROLES:
            return "positive"
        return "mixed"

    # 投资、扩张、采用：一般为正向。
    if any(k in text for k in ["investment", "funding", "adoption", "partnership", "expansion", "growth"]):
        return "positive"

    # 裁员、冻结招聘：一般为负向。
    if any(k in text for k in ["layoffs", "job cuts", "hiring freeze"]):
        return "negative"

    if avg_tone is not None:
        if avg_tone > 2:
            return "positive"
        if avg_tone < -2:
            return "negative"
    return "neutral"
```

---

## 8. 技术热度数据：基于已有技术词表，不重新构建

### 8.1 技术词表来源

你们已经有岗位相关技术，因此技术热度部分不再重新生成技术CSV。每个岗位直接取其 `top_skills` 中的核心技术词。

例如：

```python
role = "AI Agent Engineer"
skills = ["LLM", "AI agent", "agentic AI", "LangChain", "RAG", "tool calling", "vector database", "Python", "prompt engineering", "LLMOps"]
```

为了避免请求过多，每个岗位只取前3-5个关键技术词做热度即可。

### 8.2 保留三个技术热度来源

| 来源 | 保留指标 | 用途 |
|---|---|---|
| Google Trends | interest_over_time | 反映公众/市场搜索关注度 |
| GitHub | repo_count、top_repo_stars | 反映开发者生态活跃度 |
| arXiv | paper_count | 反映学术和前沿研究关注度 |

不再加入太多指标，比如commit、issue、fork、StackOverflow、HuggingFace下载量等。这些可以以后扩展。

### 8.3 Google Trends代码

```python
from pytrends.request import TrendReq
import pandas as pd
import time


def fetch_google_trends_monthly(keywords, timeframe="today 12-m", geo="US"):
    """
    keywords最多建议一次5个，Google Trends会做相对归一化。
    如果关键词很多，分批查询。
    """
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()
    if df.empty:
        return pd.DataFrame()
    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    monthly = df.resample("MS").mean().reset_index().rename(columns={"date": "month"})
    long_df = monthly.melt(id_vars="month", var_name="skill", value_name="google_trend")
    long_df["month"] = pd.to_datetime(long_df["month"]).dt.to_period("M").astype(str)
    return long_df
```

### 8.4 GitHub热度代码

```python
import os
import requests
import pandas as pd

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def fetch_github_heat(skill: str, month: str, per_page: int = 10):
    """
    用GitHub Search API按月份搜索仓库。
    指标：total_count、top_repo_stars。
    """
    start = pd.Period(month).start_time.strftime("%Y-%m-%d")
    end = pd.Period(month).end_time.strftime("%Y-%m-%d")

    q = f'"{skill}" in:name,description,readme created:{start}..{end}'
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    params = {
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    resp = requests.get(GITHUB_SEARCH_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    top_repo_stars = sum(x.get("stargazers_count", 0) for x in items)

    return {
        "month": month,
        "skill": skill,
        "github_repo_count": data.get("total_count", 0),
        "github_top_repo_stars": top_repo_stars,
    }
```

### 8.5 arXiv热度代码

```python
import feedparser
import urllib.parse
import pandas as pd

ARXIV_API_URL = "http://export.arxiv.org/api/query"


def fetch_arxiv_count(skill: str, max_results: int = 100):
    """
    arXiv API返回Atom XML。MVP做法：按关键词取最近论文，再按published月份聚合。
    """
    query = f'all:"{skill}" AND (cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV OR cat:cs.SE)'
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API_URL + "?" + urllib.parse.urlencode(params)
    feed = feedparser.parse(url)

    rows = []
    for entry in feed.entries:
        published = pd.to_datetime(entry.get("published"), errors="coerce")
        if pd.isna(published):
            continue
        rows.append({
            "month": published.to_period("M").strftime("%Y-%m"),
            "skill": skill,
            "paper_title": entry.get("title"),
            "paper_url": entry.get("id"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["month", "skill", "arxiv_paper_count"])
    return df.groupby(["month", "skill"]).size().reset_index(name="arxiv_paper_count")
```

### 8.6 技术热度聚合表

最终保留：

| 字段 | 说明 |
|---|---|
| month | 月份 |
| skill | 技术词 |
| google_trend | Google Trends搜索热度 |
| github_repo_count | GitHub新增相关仓库数量 |
| github_top_repo_stars | 当月Top仓库星标合计 |
| arxiv_paper_count | arXiv相关论文数 |
| tech_heat_index | 综合技术热度指数 |

MVP综合指数：

```text
tech_heat_index = 0.4 * google_trend_z + 0.4 * github_repo_count_z + 0.2 * arxiv_paper_count_z
```

---

## 9. 三类数据如何合并成PatchTST输入

### 9.1 粒度统一

统一成：

```text
month + canonical_role
```

也就是说，每一行表示：某个标准岗位在某个月的需求、事件情绪和技术热度。

### 9.2 技术热度如何归到岗位

由于你们每个岗位已有top_skills，因此可以将技术热度聚合到岗位：

```python

def map_tech_heat_to_roles(tech_heat_df: pd.DataFrame, role_taxonomy: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, role in role_taxonomy.iterrows():
        canonical_role = role["canonical_role"]
        skills = split_terms(role.get("top_skills", ""))[:5]
        sub = tech_heat_df[tech_heat_df["skill"].isin(skills)].copy()
        if sub.empty:
            continue
        sub["canonical_role"] = canonical_role
        rows.append(sub)

    mapped = pd.concat(rows, ignore_index=True)
    role_heat = mapped.groupby(["month", "canonical_role"]).agg(
        role_google_trend=("google_trend", "mean"),
        role_github_repo_count=("github_repo_count", "sum"),
        role_github_top_repo_stars=("github_top_repo_stars", "sum"),
        role_arxiv_paper_count=("arxiv_paper_count", "sum"),
        role_tech_heat_index=("tech_heat_index", "mean"),
    ).reset_index()
    return role_heat
```

### 9.3 最终模型输入表：`model_role_month_features`

| 字段 | 来源 |
|---|---|
| month | 时间 |
| canonical_role | 标准岗位 |
| jd_demand_index | JD |
| jd_count | JD |
| salary_mid_median | JD |
| avg_experience_years | JD |
| bachelor_or_above_ratio | JD |
| remote_ratio | JD |
| gdelt_sentiment_index | GDELT |
| gdelt_risk_index | GDELT |
| gdelt_opportunity_index | GDELT |
| gdelt_article_count | GDELT，仅作置信度 |
| role_google_trend | 技术热度 |
| role_github_repo_count | 技术热度 |
| role_arxiv_paper_count | 技术热度 |
| role_tech_heat_index | 技术热度 |

合并代码：

```python

def build_final_model_table(jd_features, gdelt_features, role_tech_heat):
    df = jd_features.merge(
        gdelt_features,
        on=["month", "canonical_role"],
        how="left"
    ).merge(
        role_tech_heat,
        on=["month", "canonical_role"],
        how="left"
    )

    numeric_cols = [
        "gdelt_sentiment_index", "gdelt_risk_index", "gdelt_opportunity_index", "gdelt_article_count",
        "role_google_trend", "role_github_repo_count", "role_arxiv_paper_count", "role_tech_heat_index"
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    df = df.sort_values(["canonical_role", "month"])
    return df
```

---

## 10. PatchTST建模：只做MVP，不钻牛角尖

### 10.1 预测目标

建议先预测一个目标：

```text
未来1个月或3个月的 jd_demand_index
```

不要一开始同时预测薪资、岗位数量、技术热度、风险指数等多个目标。

### 10.2 输入特征

MVP输入特征：

```python
FEATURE_COLS = [
    "jd_demand_index",
    "salary_mid_median",
    "avg_experience_years",
    "remote_ratio",
    "gdelt_sentiment_index",
    "gdelt_risk_index",
    "gdelt_opportunity_index",
    "role_google_trend",
    "role_github_repo_count",
    "role_arxiv_paper_count",
    "role_tech_heat_index",
]

TARGET_COL = "jd_demand_index"
```

### 10.3 数据长度建议

如果你们只有2026年实时数据，月度数据太少，不够训练PatchTST。建议：

- 近期API数据用于展示和增量更新；
- 旧LinkedIn/Data Science历史数据可作为历史训练补充；
- 如果暂时没有足够月度数据，可以先做“滚动趋势评分”作为MVP，再把PatchTST作为可接入模块。

实际项目答辩时可以这样说：

> 由于近实时招聘API的历史窗口有限，本系统先构建岗位—月份特征表和趋势评分机制；当历史序列累计到足够长度后，将该表直接输入PatchTST进行多变量时间序列预测。

### 10.4 PatchTST输入形状

对每个岗位构建一个时间序列：

```text
X: [batch_size, input_length, num_features]
y: [batch_size, prediction_length]
```

例如：

```text
过去12个月特征 → 预测未来3个月 jd_demand_index
```

---

## 11. MVP执行流程

### 第一步：准备岗位库

文件：`role_taxonomy.csv`

必须包含：

- 69个标准岗位；
- 每个岗位的召回别名；
- 每个岗位的top10技术词。

### 第二步：采集JD数据

推荐顺序：

1. 先用JSearch按69个岗位名和主要别名查询；
2. 再用RemoteOK补充远程新兴技术岗位；
3. 合并成 `raw_jd_jobs.parquet`。

### 第三步：JD标准化

使用岗位标准化代码将外部JD映射到69个岗位。

输出：

```text
processed_jd_jobs.parquet
```

### 第四步：构建JD月度特征

输出：

```text
jd_role_month_features.csv
```

### 第五步：采集GDELT新闻情绪

MVP建议：

- 最近3个月用DOC API；
- 如果需要2024-2026长序列，用BigQuery GKG聚合。

输出：

```text
gdelt_role_month_features.csv
```

### 第六步：采集技术热度

使用已有技术词表，取每个岗位top3-5技术词。

输出：

```text
tech_heat_month.csv
role_tech_heat_month.csv
```

### 第七步：合并模型输入

输出：

```text
model_role_month_features.csv
```

### 第八步：预测与解释

MVP输出：

```text
prediction_results.json
industry_trend_report.md
```

---

## 12. 后续接Agent是否需要大改

不需要大改。只要当前模块输出结构化结果即可。

后续Agent只需要调用这些接口：

```python
query_role_trend(canonical_role: str, horizon: int)
query_role_evidence(canonical_role: str)
query_role_jd_features(canonical_role: str)
query_role_gdelt_features(canonical_role: str)
query_role_tech_heat(canonical_role: str)
```

Agent回答用户问题时，流程是：

```text
用户问题
→ 识别岗位名/别名
→ 映射到69个标准岗位
→ 调用趋势预测结果
→ 调用JD/GDELT/技术热度证据
→ 生成自然语言解释
```

---

## 13. 本方案最小可行版本总结

最小可行版本只需要完成：

1. 69岗位标准库整理成CSV；
2. 用JSearch + RemoteOK获取近期英文JD；
3. JD映射到69个标准岗位；
4. 用GDELT DOC API获取近期相关新闻情绪和证据；
5. 用Google Trends、GitHub、arXiv获取少量技术热度指标；
6. 合并成 `month + canonical_role` 表；
7. 输出岗位趋势评分或接入PatchTST；
8. 保留原始JD和新闻链接给后续RAG/Agent解释。

一句话概括：

> 本模块以已有69个岗位库为核心，不再重新发现岗位；通过实时英文JD、GDELT新闻情绪和少量技术热度指标，构建岗位—月份级别的多源特征表，并输入PatchTST或趋势评分模型预测岗位需求变化，最终为职业规划Agent提供可解释的行业趋势依据。

---

## 14. 参考资料

1. JSearch API: Real-time job listings and salary data from Google for Jobs and public web.  
   https://www.openwebninja.com/api/jsearch

2. RemoteOK API / RemoteOK Scraper documentation: public JSON API with title, company, salary, tags, date and description.  
   https://remoteok.com/api  
   https://apify.com/jp_data_tools/remoteok-scraper

3. GDELT Project overview and data access.  
   https://www.gdeltproject.org/

4. GDELT DOC 2.0 API documentation and modes: ArtList, TimelineTone, Tone/ToneAbs filters.  
   https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

5. GitHub REST API documentation.  
   https://docs.github.com/en/rest

6. pytrends project: Google Trends Interest Over Time.  
   https://github.com/GeneralMills/pytrends

7. arXiv API User Manual.  
   https://info.arxiv.org/help/api/user-manual.html
