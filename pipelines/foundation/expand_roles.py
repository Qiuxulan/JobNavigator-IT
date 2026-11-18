"""新岗位发现与岗位库 v2：从 ~20 万条未分配 JD 中数据驱动地发现新岗位。

背景：jd_role_assignments.parquet 只覆盖了 69 个细粒度岗位（~5 万条 JD），
统一 JD 库中约 20 万条未分配 JD 藏着明显缺口（Data Analyst、通用 Software
Engineer、QA、IT Support、Product Designer、Engineering Manager 等）。

流程（幂等，产物覆盖写）：
  1. 读 jd_unified，排除已分配 job_id → 未分配子集
  2. JobBERT-v3 编码 "title + 前 8 个 skills"（batch 256），向量缓存到
     /data/shichaojian/JNIT/processed/role_discovery_embeddings.npy（+ job_id 索引），
     重跑时若 job_id 集合一致直接复用
  3. title 归一化聚合；规则桶（RULE_CLUSTERS，正则归堆明显岗位）+ 剩余高频
     title 的均值向量 KMeans（k=KMEANS_K）混合聚类
  4. 质量控制：规模 >= MIN_CLUSTER_SIZE、内聚度（簇内 JD 向量对质心平均余弦）
     >= MIN_COHESION、IT 纯度（title/技能命中 IT 信号的比例）>= MIN_IT_RATIO、
     与最近现有 69 岗的 JD 向量质心余弦 < MAX_EXISTING_SIM（区分度）
  5. 命名：规则桶用规则名；KMeans 簇用去 seniority 的 top title；技能按
     profiles v2 口径切 core(>=0.20,<=5)/required(>=0.08,<=15)/optional(>=0.03,<=10)
  6. 中文名：规则翻译表 + 逐词直译；翻不全的标 zh_review_needed
  7. 产出 data/gold/fine_grained_roles_v2.json（69 旧岗原样 + 新岗）、
     data/gold/role_taxonomy_v2.json、data/gold/expand_roles_qc.json

用法：
  HF_HOME=/var/lib/hf python -m pipelines.foundation.expand_roles
"""

from __future__ import annotations

import glob
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[2]
DATA_GOLD_DIR = ROOT / "data" / "gold"
ROLES_V1_JSON = DATA_GOLD_DIR / "fine_grained_roles_v1.json"
TAXONOMY_V1_JSON = DATA_GOLD_DIR / "role_taxonomy.json"
SKILL_VOCAB_JSON = DATA_GOLD_DIR / "skill_vocab_v2.json"
ROLES_V2_JSON = DATA_GOLD_DIR / "fine_grained_roles_v2.json"
TAXONOMY_V2_JSON = DATA_GOLD_DIR / "role_taxonomy_v2.json"
QC_JSON = DATA_GOLD_DIR / "expand_roles_qc.json"

JD_ROOT = Path("/data/shichaojian/JNIT/processed/jd_unified")
ASSIGNMENTS_PARQUET = JD_ROOT.parent / "jd_role_assignments.parquet"
EMB_NPY = JD_ROOT.parent / "role_discovery_embeddings.npy"
EMB_IDS_NPY = JD_ROOT.parent / "role_discovery_job_ids.npy"

MODEL_NAME = "TechWolf/JobBERT-v3"
ENCODE_BATCH = 256

KMEANS_K = 50
MIN_CLUSTER_SIZE = 200
MIN_COHESION = 0.45
MIN_IT_RATIO = 0.6
MAX_EXISTING_SIM = 0.87
MIN_TITLE_FREQ_KMEANS = 2  # 进入 KMeans 的 title 最少出现次数
MAX_NEIGHBOR_CHECK = 2000  # 内聚度/区分度采样上限

# ---------------------------------------------------------------------------
# 规则桶：(rule_key, canonical 名称, title 正则)。按顺序匹配，先到先得。
# 正则作用于 normalize_title 后的字符串。
# guard 仅用于 Software Engineer (General) / QA Engineer (General) 这类
# "裸头衔"角色：在 build_role_profiles_v2 重分配时只允许全匹配 title，
# 防止 "software engineer, machine learning" 这类修饰头衔被误吸。
# ---------------------------------------------------------------------------
RULE_CLUSTERS: list[dict[str, Any]] = [
    {"key": "data_analyst", "name": "Data Analyst",
     "regex": r"\bdata analyst\b|\b(bi|business intelligence) analyst\b|\bdata analytics analyst\b",
     "coarse": "AI & Data"},
    {"key": "analytics_engineer", "name": "Analytics Engineer",
     "regex": r"\banalytics engineer\b",
     "coarse": "AI & Data"},
    {"key": "bi_developer", "name": "BI Developer",
     "regex": r"\b(bi|business intelligence)\b[^,]*\bdeveloper\b|\bbi developer\b|\bpower bi developer\b|\btableau developer\b|\blooker developer\b",
     "coarse": "AI & Data"},
    {"key": "data_governance", "name": "Data Governance Specialist",
     "regex": r"\b(data quality|data governance|data steward|master data|data operations)\b",
     "coarse": "AI & Data"},
    {"key": "sw_general", "name": "Software Engineer (General)",
     "regex": r"^(senior|sr|staff|principal|lead|junior|jr|mid|associate)?\s*(software engineer|software developer|sde|full ?stack (engineer|developer)|fullstack (engineer|developer)|generalist|member of technical staff|engineer|developer)\s*(i{1,3}|iv|i{1,2}v|1|2|3|4|new grad|intern|growth)?\s*(full ?stack|fullstack)?\s*(remote|hybrid)?$",
     "guard": True, "coarse": "General Engineering"},
    {"key": "qa_general", "name": "QA Engineer (General)",
     "regex": r"\b(qa engineer|quality assurance engineer|sdet|software development engineer in test|qa lead|test lead|qa manager|test manager|qa analyst|test analyst|software tester|qa tester)\b",
     "guard": True, "coarse": "QA & Testing"},
    {"key": "it_support", "name": "IT Support Specialist",
     "regex": r"\b(technical support|it support|help ?desk|service desk|desktop support|application support|technical assistance|it technician|support technician|pc technician|field service technician)\b|\b(technical|application|product|customer|it|desktop|cloud|salesforce)\s+support\s+(engineer|specialist|analyst)\b",
     "coarse": "Other IT"},
    {"key": "product_designer", "name": "Product Designer",
     "regex": r"\b(product designer|ux designer|ux researcher|product design|visual designer|interaction designer|design lead|content designer|product design lead|head of product design|director of product design|director product design)\b",
     "coarse": "Frontend Development"},
    {"key": "eng_manager", "name": "Engineering Manager",
     "regex": r"\b(engineering manager|engineering director|director of engineering|head of engineering|vp of engineering|vice president of engineering|vp engineering|head of software engineering|director of software engineering|engineering lead|manager of engineering|engineering manager)\b",
     "coarse": "General Engineering"},
    {"key": "tech_writer", "name": "Technical Writer",
     "regex": r"\b(technical writer|tech writer|documentation engineer|technical author|technical documentation|technical editor|documentation specialist)\b",
     "coarse": "Other IT"},
    {"key": "solutions_engineer", "name": "Solutions Engineer",
     "regex": r"\b(solutions? engineer|pre[- ]?sales engineer|sales engineer|customer engineer|deployment strategist|value engineer|solutions consultant)\b",
     "coarse": "Other IT"},
    {"key": "solutions_architect", "name": "Solutions Architect",
     "regex": r"\b(solutions? architect|enterprise architect)\b",
     "coarse": "General Engineering"},
    {"key": "sre", "name": "Site Reliability Engineer",
     "regex": r"\b(site reliability engineer|sre|reliability engineer)\b",
     "coarse": "Cloud Native & DevOps"},
    {"key": "network_engineer", "name": "Network Engineer",
     "regex": r"\b(network engineer|network administrator|network admin|noc engineer|network operations engineer|network analyst|wireless network engineer|voice engineer)\b",
     "coarse": "Cloud Native & DevOps"},
    {"key": "platform_engineer", "name": "Platform Engineer",
     "regex": r"\b(platform engineer|infrastructure engineer|build engineer|release engineer|developer productivity|internal tools engineer|dev infra|ci cd engineer)\b",
     "coarse": "Cloud Native & DevOps"},
    {"key": "tpm", "name": "Technical Program Manager",
     "regex": r"\b(technical program manager|technical project manager)\b",
     "coarse": "Product & Business Analysis"},
    {"key": "sys_analyst", "name": "Business Systems Analyst",
     "regex": r"\b(business systems analyst|systems analyst|system analyst|it business analyst|application analyst|business technology analyst)\b",
     "coarse": "Product & Business Analysis"},
    {"key": "salesforce", "name": "Salesforce Developer",
     "regex": r"\bsalesforce\b",
     "coarse": "Other IT"},
    {"key": "servicenow", "name": "ServiceNow Developer",
     "regex": r"\bservicenow\b|\bservice now developer\b",
     "coarse": "Other IT"},
    {"key": "embedded", "name": "Embedded Software Engineer",
     "regex": r"\b(embedded|firmware|iot)\b[^,]*\b(engineer|developer)\b|\bembedded software\b",
     "coarse": "General Engineering"},
    {"key": "cyber", "name": "Cybersecurity Engineer",
     "regex": r"\b(cyber ?security|soc analyst|grc analyst|grc manager|incident response|threat hunter|detection engineer)\b",
     "coarse": "Security"},
    {"key": "software_architect", "name": "Software Architect",
     "regex": r"\b(software architect|technical architect|systems architect|system architect|chief architect|principal architect|ai architect|data architect)\b",
     "coarse": "General Engineering"},
    {"key": "devrel", "name": "Developer Advocate",
     "regex": r"\b(developer advocate|developer relations|devrel|technical evangelist)\b",
     "coarse": "Other IT"},
    {"key": "it_ops", "name": "IT Operations Specialist",
     "regex": r"\b(it operations|it ops|it infrastructure|it administrator|it admin|it engineer|it specialist|it generalist|it systems|systems administrator|system administrator|systems admin|sysadmin|infrastructure administrator|workplace it)\b",
     "coarse": "Other IT"},
    {"key": "quant", "name": "Quantitative Developer",
     "regex": r"\b(quantitative developer|quant developer|quantitative analyst|quant analyst|trading systems developer)\b",
     "coarse": "General Engineering"},
    {"key": "sap", "name": "SAP Consultant",
     "regex": r"\bsap\b",
     "coarse": "Other IT"},
    {"key": "product_owner", "name": "Product Owner",
     "regex": r"\bproduct owner\b",
     "coarse": "Product & Business Analysis"},
    {"key": "erp_platform", "name": "Enterprise Platform Developer",
     "regex": r"\b(workday|peoplesoft|dynamics 365|ms dynamics|netsuite)\b",
     "coarse": "Other IT"},
]

# ---------------------------------------------------------------------------
# IT / 非 IT 判定（QC 用）
# 三层信号：
#   NON_IT 命中且 DECISIVE_TECH 未命中 → 非 IT（强排除，如 mechanical engineer）
#   IT_TITLE 命中 → IT（工程师/开发者/数据/云等硬信号）
#   其余模糊 title → 看 JD 技能是否映射进 IT 技能词表
# ---------------------------------------------------------------------------
IT_TITLE = re.compile(
    r"engineer|developer|software|devops|cloud|kubernetes|docker|\bk8s\b|aws|azure|gcp|"
    r"\bsre\b|sysadmin|administrator|network|security|cyber|help ?desk|service desk|"
    r"desktop support|technical support|application support|\bit\b|technician|"
    r"programmer|architect|\bux\b|\bui\b|designer|frontend|front end|backend|back end|"
    r"full ?stack|fullstack|embedded|firmware|\biot\b|data|analytic|database|\bdba\b|"
    r"etl|business intelligence|\bbi\b|tableau|power bi|looker|machine learning|\bml\b|"
    r"\bai\b|llm|prompt|scrum|salesforce|servicenow|\bsap\b|erp|crm|mainframe|"
    r"sharepoint|dynamics|workday|peoplesoft|oracle|\.net|c#|c\+\+|php|ruby|\bgo\b|"
    r"rust|kotlin|swift|flutter|unity|unreal|blockchain|web3|linux|sql|python|java|"
    r"javascript|typescript|react|angular|vue|node|api|microservice|infrastructure|"
    r"platform|site reliability|noc\b|devsecops|itil|web developer|support|automation|"
    r"product owner"
)
DECISIVE_TECH = re.compile(
    r"software|data|devops|cloud|kubernetes|docker|\bk8s\b|aws|azure|gcp|\bsre\b|"
    r"network|security|cyber|frontend|front end|backend|back end|full ?stack|fullstack|"
    r"embedded|firmware|\biot\b|qa\b|test|database|\bdba\b|sql|python|java|javascript|"
    r"typescript|react|angular|vue|node|\.net|c#|c\+\+|php|ruby|\brust\b|kotlin|swift|"
    r"flutter|unity|unreal|blockchain|web3|salesforce|servicenow|\bsap\b|"
    r"machine learning|\bml\b|\bai\b|llm|automation|infrastructure|platform|linux|api|"
    r"microservice|tableau|power bi|looker|etl|mainframe|sharepoint|workday|peoplesoft|"
    r"erp|crm|\bit\b|help ?desk|service desk|desktop support|technical support|"
    r"application support|site reliability|noc\b|devsecops|web developer"
)
NON_IT_SIGNAL = re.compile(
    r"nurse|carer|care assistant|caregiver|senior care|support worker|"
    r"retail|store manager|shop assistant|chef|\bcook\b|waiter|bartender|"
    r"housekeeper|cleaner|housekeeping|laundry|\bdriver\b|delivery driver|"
    r"warehouse|forklift|truck|construction|carpenter|electrician|plumber|"
    r"mechanic|hvac|teacher|tutor|teaching|nanny|babysitter|sales representative|"
    r"real estate|property manager|estate agent|lawyer|legal|paralegal|attorney|"
    r"accountant|bookkeeper|payroll|accounts payable|accounts receivable|payable|"
    r"bank|\bteller\b|cashier|receptionist|administrative|executive assistant|"
    r"office manager|customer service|call center|medical|dental|pharmacist|"
    r"physio|therapist|veterinary|clinical|phlebotomy|agricultur|farm|gardener|"
    r"landscape|security guard|police|firefighter|\barmy\b|military|pilot|"
    r"cabin crew|flight attendant|hotel|hospitality|catering|travel agent|"
    r"beautician|hairdresser|barber|massage|fitness|personal trainer|yoga|"
    r"translator|copywriter|journalist|photographer|videographer|actor|musician|"
    r"production operator|assembly|machine operator|packer|picker|"
    r"mechanical|electrical|manufacturing|process engineer|production engineer|"
    r"quality engineer|quality manager|supplier quality|maintenance|automotive|"
    r"field service|\bcontroller\b|dispatcher|document control|procurement|"
    r"customer success|client success|business development|sales development|"
    r"\bsdr\b|go to market|\bgtm\b|\bgrowth\b|partnerships|engagement manager|"
    r"revenue operations|revops|graphic|interior|data entry|laboratory|"
    r"recruiter|recruitment|\bcounsel\b|field engineer|service engineer|"
    r"project engineer|civil|structural|financial|finance|treasury|"
    r"quantitative researcher|quantitative|\btrader\b"
)


def classify_it(title_norm: str, skill_ids: set[str]) -> bool:
    if NON_IT_SIGNAL.search(title_norm) and not DECISIVE_TECH.search(title_norm):
        return False
    if IT_TITLE.search(title_norm):
        return True
    return bool(skill_ids)

SENIORITY_PREFIX = re.compile(
    r"^(senior|sr\.?|junior|jr\.?|staff|principal|lead|associate|mid[- ]level|mid|"
    r"chief|head of|director|vice president|vp|executive|global|regional|"
    r"intern|trainee|entry level|founding|remote|hybrid)\s+", re.IGNORECASE)
LEVEL_SUFFIX = re.compile(
    r"\s+(-\s*)?(i{1,3}v?|iv|v|1|2|3|4|5|new grad|intern|remote|hybrid|"
    r"m w d|m f d|h f|f m d)$", re.IGNORECASE)

# 逐词直译表（中文名生成兜底）
ZH_WORDS = {
    "data": "数据", "analyst": "分析师", "analytics": "分析", "engineer": "工程师",
    "developer": "开发工程师", "software": "软件", "qa": "QA", "test": "测试",
    "testing": "测试", "support": "支持", "specialist": "专员", "it": "IT",
    "product": "产品", "designer": "设计师", "design": "设计", "manager": "经理",
    "technical": "技术", "writer": "文档工程师", "documentation": "文档",
    "solutions": "解决方案", "solution": "解决方案", "architect": "架构师",
    "site": "站点", "reliability": "可靠性", "network": "网络", "platform": "平台",
    "program": "项目", "project": "项目", "business": "业务", "systems": "系统",
    "system": "系统", "salesforce": "Salesforce", "servicenow": "ServiceNow",
    "embedded": "嵌入式", "firmware": "固件", "cybersecurity": "网络安全的",
    "cyber": "网络", "security": "安全", "quantitative": "量化", "sap": "SAP",
    "general": "通用", "operations": "运维", "operation": "运维", "quality": "质量",
    "governance": "治理", "governance": "治理", "devops": "DevOps",
    "cloud": "云", "automation": "自动化", "manual": "手工", "full-stack": "全栈",
    "fullstack": "全栈", "frontend": "前端", "backend": "后端", "mobile": "移动",
    "bi": "BI", "intelligence": "智能", "research": "研究", "science": "科学",
    "scientist": "科学家", "infrastructure": "基础设施", "devrel": "开发者关系",
    "advocate": "布道师", "ux": "UX", "uxr": "用研", "game": "游戏",
    "administrator": "管理员", "admin": "管理员", "consultant": "顾问",
    "recruiter": "招聘专员", "writer": "文档工程师",
}
ZH_SPECIAL = {
    "sre": "SRE", "sdet": "SDET", "qa": "QA", "ux": "UX", "bi": "BI",
    "it": "IT", "noc": "NOC", "crm": "CRM", "erp": "ERP", "iot": "IoT",
    "ai": "AI", "ml": "ML", "sdet": "SDET",
}

COARSE_TO_KEY = {
    "Emerging AI": "emerging_ai",
    "Backend Development": "backend",
    "Frontend Development": "frontend",
    "Cloud Native & DevOps": "devops_cloud",
    "QA & Testing": "qa_testing",
    "Mobile Development": "mobile",
    "Game Development": "game",
    "AI & Data": "ai_data",
    "Security": "security",
    "Product & Business Analysis": "pm_ba",
    "Other IT": "other_it",
    "General Engineering": "general_engineering",
}


def normalize_title(title: Any) -> str:
    text = re.sub(r"[^a-z0-9+#.\s]", " ", str(title or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def jd_text(title: Any, skills: Any) -> str:
    skill_list = []
    if skills is not None:
        try:
            skill_list = [str(s) for s in list(skills)[:8] if str(s).strip()]
        except TypeError:
            skill_list = []
    head = str(title or "").strip()
    return f"{head}. Skills: {', '.join(skill_list)}" if skill_list else head


def load_unassigned() -> pd.DataFrame:
    files = sorted(glob.glob(str(JD_ROOT / "posted_month=*" / "part-0.parquet")))
    if not files:
        raise FileNotFoundError(f"no unified JD files under {JD_ROOT}")
    cols = ["job_id", "title", "skills", "source", "posted_month"]
    frame = pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)
    assigned = pd.read_parquet(ASSIGNMENTS_PARQUET, columns=["job_id"])
    un = frame[~frame["job_id"].isin(set(assigned["job_id"]))].reset_index(drop=True)
    return un


def encode_unassigned(un: pd.DataFrame) -> np.ndarray:
    """向量化未分配 JD；命中缓存（job_id 集合一致）直接复用。"""
    job_ids = un["job_id"].to_numpy()
    if EMB_NPY.exists() and EMB_IDS_NPY.exists():
        cached_ids = np.load(EMB_IDS_NPY, allow_pickle=True)
        if len(cached_ids) == len(job_ids) and set(cached_ids.tolist()) == set(job_ids.tolist()):
            emb = np.load(EMB_NPY)
            if emb.shape[0] == len(job_ids):
                print(f"embedding cache hit: {EMB_NPY} ({emb.shape})")
                return emb
        print("embedding cache stale (job_id set changed), re-encoding")

    import os
    os.environ.setdefault("HF_HOME", "/var/lib/hf")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
    texts = [jd_text(t, s) for t, s in zip(un["title"], un["skills"])]
    emb = model.encode(
        texts, batch_size=ENCODE_BATCH, normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    ).astype(np.float32)
    np.save(EMB_NPY, emb)
    np.save(EMB_IDS_NPY, job_ids)
    print(f"wrote {EMB_NPY} {emb.shape}")
    return emb


def load_skill_vocab() -> tuple[dict[str, str], dict[str, str]]:
    vocab = json.loads(SKILL_VOCAB_JSON.read_text(encoding="utf-8"))
    alias_to_id = {}
    for alias, skill_id in vocab.get("alias_to_id", {}).items():
        alias_to_id.setdefault(str(alias).strip().lower(), skill_id)
    for skill_id, name in vocab.get("id_to_name", {}).items():
        alias_to_id.setdefault(str(name).strip().lower(), skill_id)
    return alias_to_id, vocab.get("id_to_name", {})


def jd_skill_ids(skills: Any, alias_to_id: dict[str, str]) -> set[str]:
    if skills is None:
        return set()
    try:
        values = list(skills)
    except TypeError:
        return set()
    return {alias_to_id[str(v).strip().lower()] for v in values
            if str(v).strip().lower() in alias_to_id}


# ---------------------------------------------------------------------------
# 现有 69 岗：给未分配 JD 打"最近现有岗"标签，构建现有岗的 JD 向量质心
# ---------------------------------------------------------------------------
def build_existing_role_index() -> list[dict[str, Any]]:
    roles = json.loads(ROLES_V1_JSON.read_text(encoding="utf-8"))
    taxonomy = {r["role_id"]: r for r in json.loads(TAXONOMY_V1_JSON.read_text(encoding="utf-8"))}
    index = []
    for role in roles:
        name = role["role_name"]
        aliases = set()
        tax = taxonomy.get(role["role_id"], {})
        for a in tax.get("aliases") or []:
            aliases.add(str(a).strip().lower())
        for kw in role.get("search_keywords") or []:
            if len(str(kw).split()) >= 2:
                aliases.add(str(kw).strip().lower())
        aliases.discard(name.lower())
        pats = []
        for a in sorted(aliases, key=len, reverse=True):
            if len(a) < 3:
                continue
            pats.append(re.compile(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])"))
        tokens = {t for t in re.findall(r"[a-z0-9+#.]+", name.lower())
                  if t not in {"engineer", "developer", "software", "analyst", "administrator"}}
        index.append({"role_id": role["role_id"], "role_name": name,
                      "patterns": pats, "tokens": tokens})
    return index


def label_existing(title_norm: str, index: list[dict[str, Any]]) -> str | None:
    best_id, best_score = None, 0.0
    for role in index:
        score = 0.0
        for pat in role["patterns"]:
            if pat.search(title_norm):
                score = 0.9
                break
        if not score and role["tokens"]:
            toks = set(re.findall(r"[a-z0-9+#.]+", title_norm))
            hit = len(role["tokens"] & toks)
            if hit >= 2:
                score = 0.5
        if score > best_score:
            best_id, best_score = role["role_id"], score
    return best_id


def existing_centroids(un: pd.DataFrame, emb: np.ndarray) -> dict[str, np.ndarray]:
    index = build_existing_role_index()
    norm_titles = un["title"].map(normalize_title)
    unique = norm_titles.unique()
    label_map = {t: label_existing(t, index) for t in unique}
    labels = norm_titles.map(label_map)

    centroids: dict[str, np.ndarray] = {}
    for role_id in {l for l in labels if l}:
        mask = (labels == role_id).to_numpy()
        if mask.sum() >= 30:
            centroids[role_id] = emb[mask].mean(axis=0)
    # 无足够未分配 JD 的现有岗：编码其 profile 文本作质心
    missing = [r for r in index if r["role_id"] not in centroids]
    if missing:
        import os
        os.environ.setdefault("HF_HOME", "/var/lib/hf")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
        texts = [r["role_name"] for r in missing]
        vecs = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        for r, v in zip(missing, vecs):
            centroids[r["role_id"]] = v.astype(np.float32)
    return centroids


# ---------------------------------------------------------------------------
# 聚类
# ---------------------------------------------------------------------------
def rule_buckets(un: pd.DataFrame, norm_titles: pd.Series) -> tuple[dict[str, list[int]], set[str]]:
    """规则桶：返回 {rule_key: [行号]} 与被规则覆盖的 title 集合。"""
    buckets: dict[str, list[int]] = {}
    covered_titles: set[str] = set()
    claimed = np.zeros(len(un), dtype=bool)
    for rule in RULE_CLUSTERS:
        pat = re.compile(rule["regex"])
        mask = norm_titles.map(lambda t: bool(pat.search(t))) & ~pd.Series(claimed, index=un.index)
        idx = un.index[mask].tolist()
        if idx:
            buckets[rule["key"]] = idx
            claimed[idx] = True
            covered_titles |= set(norm_titles.loc[idx].unique())
    return buckets, covered_titles


def kmeans_buckets(
    un: pd.DataFrame, emb: np.ndarray, norm_titles: pd.Series,
    covered_titles: set[str],
) -> dict[int, list[int]]:
    """剩余 title（freq>=阈值、未覆盖）按 title 均值向量 KMeans。"""
    counts = norm_titles.value_counts()
    cand_titles = [t for t, c in counts.items()
                   if c >= MIN_TITLE_FREQ_KMEANS and t and t not in covered_titles]
    if not cand_titles:
        return {}
    title_to_rows: dict[str, list[int]] = {}
    for i, t in enumerate(norm_titles):
        title_to_rows.setdefault(t, []).append(i)

    vecs = np.zeros((len(cand_titles), emb.shape[1]), dtype=np.float32)
    weights = np.zeros(len(cand_titles), dtype=np.float64)
    for j, t in enumerate(cand_titles):
        rows = title_to_rows[t]
        vecs[j] = emb[rows].mean(axis=0)
        weights[j] = len(rows)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.maximum(norms, 1e-9)

    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=KMEANS_K, n_init=4, random_state=42)
    km.fit(vecs, sample_weight=weights)

    buckets: dict[int, list[int]] = {}
    for j, t in enumerate(cand_titles):
        buckets.setdefault(int(km.labels_[j]), []).extend(title_to_rows[t])
    return buckets


def canonicalize_name(top_titles: list[str]) -> str:
    for t in top_titles:
        name = SENIORITY_PREFIX.sub("", t).strip()
        name = LEVEL_SUFFIX.sub("", name).strip()
        if not name or len(name) < 3:
            continue
        words = name.split()
        capped = []
        special = {".net", "c++", "c#", "node.js", "sre", "sde", "sdet", "qa", "it", "bi",
                   "ux", "ui", "ai", "ml", "sap", "erp", "crm", "iot", "noc", "devops",
                   "sql", "aws", "gcp", "saas", "paas"}
        for w in words:
            lw = w.lower()
            if lw in special or re.search(r"[+.#'0-9]", lw):
                capped.append(lw if lw not in {".net", "c++", "c#"} else lw.upper() if lw == "c#" else lw)
            else:
                capped.append(lw.capitalize())
        name = " ".join(capped)
        if name.lower() not in {"engineer", "developer", "analyst", "manager", "specialist",
                                "developerengineer", "consultant", "none", "test"}:
            return name
    return ""


def cluster_stats(
    rows: list[int], emb: np.ndarray, un: pd.DataFrame,
    alias_to_id: dict[str, str], id_to_name: dict[str, str],
) -> dict[str, Any]:
    idx = np.asarray(rows, dtype=np.int64)
    vecs = emb[idx]
    centroid = vecs.mean(axis=0)
    cnorm = centroid / max(np.linalg.norm(centroid), 1e-9)
    sample = idx if len(idx) <= MAX_NEIGHBOR_CHECK else np.random.RandomState(42).choice(idx, MAX_NEIGHBOR_CHECK, replace=False)
    sims = emb[sample] @ cnorm
    cohesion = float(np.mean(sims))

    sub = un.iloc[rows]
    raw_titles = Counter(str(t).strip() for t in sub["title"] if str(t).strip())
    norm_counts = Counter(normalize_title(t) for t in sub["title"])

    skill_counter: Counter[str] = Counter()
    it_hits = 0
    non_it_hits = 0
    for t, s in zip(sub["title"], sub["skills"]):
        tn = normalize_title(t)
        ids = jd_skill_ids(s, alias_to_id)
        is_it = classify_it(tn, ids)
        it_hits += int(is_it)
        non_it_hits += int(not is_it and bool(NON_IT_SIGNAL.search(tn)))
        skill_counter.update(ids)

    n = len(rows)
    skill_freq = {id_to_name.get(sid, sid): round(c / n, 6)
                  for sid, c in skill_counter.most_common()}
    it_ratio = round(it_hits / n, 4)
    return {
        "size": n,
        "cohesion": round(cohesion, 4),
        "it_ratio": it_ratio,
        "non_it_ratio": round(non_it_hits / n, 4),
        "top_raw_titles": [t for t, _ in raw_titles.most_common(10)],
        "top_norm_titles": [t for t, _ in norm_counts.most_common(12)],
        "skill_counter": skill_counter,
        "skill_freq": skill_freq,
    }


def nearest_existing(centroid_idx: np.ndarray, emb: np.ndarray,
                     centroids: dict[str, np.ndarray],
                     existing_names: dict[str, str]) -> tuple[str, float]:
    centroid = emb[np.asarray(centroid_idx, dtype=np.int64)].mean(axis=0)
    centroid = centroid / max(np.linalg.norm(centroid), 1e-9)
    best_role, best_sim = "", -1.0
    for role_id, cen in centroids.items():
        sim = float(centroid @ (cen / max(np.linalg.norm(cen), 1e-9)))
        if sim > best_sim:
            best_role, best_sim = role_id, sim
    return existing_names.get(best_role, best_role), round(best_sim, 4)


# ---------------------------------------------------------------------------
# 中文名
# ---------------------------------------------------------------------------
def zh_name(name: str) -> tuple[str, bool]:
    if name in ROLE_ZH_OVERRIDES:
        return ROLE_ZH_OVERRIDES[name], False
    lowered = name.lower().replace("(", " ").replace(")", " ")
    words = [w for w in re.split(r"[\s/,-]+", lowered) if w]
    parts, missing = [], False
    for w in words:
        if w in ZH_SPECIAL:
            parts.append(ZH_SPECIAL[w])
        elif w in ZH_WORDS:
            parts.append(ZH_WORDS[w])
        elif re.match(r"^[a-z0-9+#.]+$", w) and len(w) <= 4 and w in {"sre", "sde"}:
            parts.append(w.upper())
        else:
            missing = True
    if not parts or missing:
        return name, True
    return "".join(parts), False


ROLE_ZH_OVERRIDES: dict[str, str] = {
    "Data Analyst": "数据分析师",
    "Analytics Engineer": "分析工程师",
    "BI Developer": "BI 开发工程师",
    "Data Governance Specialist": "数据治理专员",
    "Software Engineer (General)": "通用软件工程师",
    "QA Engineer (General)": "通用 QA 工程师",
    "IT Support Specialist": "IT 支持专员",
    "Product Designer": "产品设计师",
    "Engineering Manager": "工程经理",
    "Technical Writer": "技术文档工程师",
    "Solutions Engineer": "解决方案工程师",
    "Solutions Architect": "解决方案架构师",
    "Site Reliability Engineer": "站点可靠性工程师",
    "Network Engineer": "网络工程师",
    "Platform Engineer": "平台工程师",
    "Technical Program Manager": "技术项目经理",
    "Business Systems Analyst": "业务系统分析师",
    "Salesforce Developer": "Salesforce 开发工程师",
    "ServiceNow Developer": "ServiceNow 开发工程师",
    "Embedded Software Engineer": "嵌入式软件工程师",
    "Cybersecurity Engineer": "网络安全工程师",
    "Software Architect": "软件架构师",
    "Developer Advocate": "开发者布道师",
    "IT Operations Specialist": "IT 运维专员",
    "Quantitative Developer": "量化开发工程师",
    "SAP Consultant": "SAP 顾问",
    "Product Owner": "产品负责人",
    "Enterprise Platform Developer": "企业平台开发工程师",
}


def pick_skills(skill_counter: Counter[str], n: int,
                id_to_name: dict[str, str]) -> tuple[list[str], list[str], list[str],
                                                     list[str], list[str], list[str], dict[str, float]]:
    """profiles v2 口径：core>=0.20 封顶5 / required>=0.08 封顶15 / optional>=0.03 封顶10。"""
    ordered = sorted(skill_counter.items(), key=lambda kv: (-kv[1] / n, kv[0]))
    freq = {id_to_name.get(sid, sid): round(c / n, 6) for sid, c in ordered}
    core = [(sid, c / n) for sid, c in ordered if c / n >= 0.20][:5]
    required = [(sid, c / n) for sid, c in ordered if c / n >= 0.08][:15]
    req_ids = {sid for sid, _ in required}
    optional = [(sid, c / n) for sid, c in ordered if c / n >= 0.03 and sid not in req_ids][:10]

    def names(pairs):
        return [id_to_name.get(sid, sid) for sid, _ in pairs]

    return (names(core), [sid for sid, _ in core],
            names(required), [sid for sid, _ in required],
            names(optional), [sid for sid, _ in optional], freq)


def coarse_for_name(name: str, default: str) -> str:
    n = name.lower()
    if re.search(r"data|analytic|bi\b|tableau|power bi", n):
        return "AI & Data"
    if re.search(r"qa|test", n):
        return "QA & Testing"
    if re.search(r"security|cyber", n):
        return "Security"
    if re.search(r"design|ux\b|ui\b|visual", n):
        return "Frontend Development"
    if re.search(r"devops|sre|reliability|network|platform|infrastructure|cloud", n):
        return "Cloud Native & DevOps"
    if re.search(r"game|unity|unreal", n):
        return "Game Development"
    if re.search(r"mobile|android|ios|flutter", n):
        return "Mobile Development"
    if re.search(r"program manager|project manager|product manager|scrum|business", n):
        return "Product & Business Analysis"
    if re.search(r"machine learning|\bai\b|llm|prompt|rag\b", n):
        return "Emerging AI"
    if re.search(r"engineer|architect|embedded|firmware|quant|developer", n):
        return "General Engineering"
    return default


def main() -> None:
    print(">>> 加载未分配 JD ...")
    un = load_unassigned()
    print(f"    unassigned JD: {len(un)}")
    norm_titles = un["title"].map(normalize_title)
    print(f"    unique normalized titles: {norm_titles.nunique()}")

    emb = encode_unassigned(un)

    alias_to_id, id_to_name = load_skill_vocab()

    print(">>> 规则归堆 ...")
    rule_rows, covered_titles = rule_buckets(un, norm_titles)
    for key, rows in rule_rows.items():
        print(f"    rule {key}: {len(rows)} JDs")

    print(">>> KMeans 聚类剩余高频 title ...")
    km_rows = kmeans_buckets(un, emb, norm_titles, covered_titles)
    for cid, rows in sorted(km_rows.items(), key=lambda kv: -len(kv[1])):
        print(f"    kmeans cluster {cid}: {len(rows)} JDs")

    print(">>> 计算现有 69 岗 JD 向量质心 ...")
    centroids = existing_centroids(un, emb)
    v1_roles = json.loads(ROLES_V1_JSON.read_text(encoding="utf-8"))
    existing_names = {r["role_id"]: r["role_name"] for r in v1_roles}
    existing_name_set = {r["role_name"].lower() for r in v1_roles}

    # ------------------------------------------------------------------ QC
    accepted: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    def evaluate(cluster_id: str, rows: list[int], default_name: str, coarse: str,
                 guard: bool = False) -> None:
        stats = cluster_stats(rows, emb, un, alias_to_id, id_to_name)
        near_name, near_sim = nearest_existing(rows, emb, centroids, existing_names)
        record = {
            "cluster_id": cluster_id,
            "candidate_name": default_name,
            "size": stats["size"],
            "cohesion": stats["cohesion"],
            "it_ratio": stats["it_ratio"],
            "non_it_ratio": stats["non_it_ratio"],
            "nearest_existing_role": near_name,
            "nearest_existing_sim": near_sim,
            "top_norm_titles": stats["top_norm_titles"],
            "top_raw_titles": stats["top_raw_titles"],
            "top_skills": [k for k in list(stats["skill_freq"])[:10]],
        }
        if not default_name:
            record["reason"] = "empty_name"
            dropped.append(record)
            return
        lname = default_name.lower()
        if NON_IT_SIGNAL.search(lname) and not DECISIVE_TECH.search(lname):
            record["reason"] = "non_it_role_name"
            dropped.append(record)
            return
        if stats["size"] < MIN_CLUSTER_SIZE:
            record["reason"] = f"too_small (<{MIN_CLUSTER_SIZE})"
            dropped.append(record)
            return
        if stats["it_ratio"] < MIN_IT_RATIO:
            record["reason"] = f"low_it_ratio (<{MIN_IT_RATIO})"
            dropped.append(record)
            return
        if stats["cohesion"] < MIN_COHESION:
            record["reason"] = f"low_cohesion (<{MIN_COHESION})"
            dropped.append(record)
            return
        if near_sim >= MAX_EXISTING_SIM:
            record["reason"] = f"too_similar_to_existing({near_name}={near_sim})"
            dropped.append(record)
            return
        record["guard"] = guard
        record["coarse_role"] = coarse
        accepted.append(record)

    rule_meta = {r["key"]: r for r in RULE_CLUSTERS}
    for key, rows in rule_rows.items():
        meta = rule_meta[key]
        evaluate(f"rule:{key}", rows, meta["name"], meta["coarse"], guard=bool(meta.get("guard")))

    # KMeans 簇命名；与规则桶语义重名（如 Software Engineer vs Software Engineer
    # (General)）的簇并入规则桶，避免 downstream 出现两个同义岗位。
    def _norm_name(n: str) -> str:
        return re.sub(r"\s*\(\s*general\s*\)", "", n or "",
                      flags=re.IGNORECASE).strip().lower()

    # 与规则桶语义重名（如 Software Engineer vs Software Engineer (General)）
    # 或近义（Test Engineer vs QA Engineer (General)）的簇并入规则桶。
    EXTRA_MERGE_INTO_RULE = {"test engineer": "qa_general"}
    rule_name_norm = {r["key"]: _norm_name(r["name"]) for r in RULE_CLUSTERS}
    km_named: dict[int, tuple[str, list[int]]] = {}
    for cid, rows in sorted(km_rows.items(), key=lambda kv: -len(kv[1])):
        name = canonicalize_name(
            [t for t, _ in Counter(normalize_title(t) for t in un.iloc[rows]["title"]).most_common(15)]
        )
        merged_key = EXTRA_MERGE_INTO_RULE.get(_norm_name(name))
        hit = merged_key if (merged_key and merged_key in rule_rows) else next(
            (k for k, v in rule_name_norm.items()
             if v and v == _norm_name(name) and k in rule_rows), None)
        if hit:
            print(f"    kmeans cluster {cid} ({name}) merged into rule:{hit}")
            rule_rows[hit] = rule_rows[hit] + rows
            continue
        km_named[cid] = (name, rows)

    # 规则桶合入后重新评估受影响的簇（rule 评估已跑，重新整体跑一遍最干净）
    accepted = [a for a in accepted if not a["cluster_id"].startswith("rule:")]
    dropped = [d for d in dropped if not d["cluster_id"].startswith("rule:")]
    for key, rows in rule_rows.items():
        meta = rule_meta[key]
        evaluate(f"rule:{key}", rows, meta["name"], meta["coarse"], guard=bool(meta.get("guard")))

    for cid, (name, rows) in km_named.items():
        evaluate(f"kmeans:{cid}", rows, name or f"Cluster {cid}", "Other IT")

    # ------------------------------------------------- 命名去重（与 69 岗 & 新岗之间）
    final_new: list[dict[str, Any]] = []
    used_names = set(existing_name_set)
    for rec in accepted:
        name = rec["candidate_name"]
        if not name or name.lower() in used_names:
            rec["reason"] = (f"duplicate_or_empty_name({name})" if name else "empty_name")
            dropped.append(rec)
            continue
        used_names.add(name.lower())
        rec["role_name"] = name
        final_new.append(rec)

    print(f">>> QC 通过 {len(final_new)} 个候选新岗，丢弃 {len(dropped)} 个簇")

    # ------------------------------------------------- 组装 v2
    next_num = max(int(r["role_id"].split("_")[1]) for r in v1_roles) + 1
    v2_roles: list[dict[str, Any]] = [dict(r) for r in v1_roles]
    v2_taxonomy: list[dict[str, Any]] = [dict(r) for r in json.loads(TAXONOMY_V1_JSON.read_text(encoding="utf-8"))]
    new_role_reports: list[dict[str, Any]] = []

    for offset, rec in enumerate(final_new):
        role_id = f"role_{next_num + offset:03d}"
        rows_idx = (rule_rows.get(rec["cluster_id"].split(":", 1)[1])
                    if rec["cluster_id"].startswith("rule:") else None)
        if rows_idx is None:
            rows_idx = km_rows[int(rec["cluster_id"].split(":")[1])]
        sub = un.iloc[rows_idx]
        skill_counter: Counter[str] = Counter()
        for s in sub["skills"]:
            skill_counter.update(jd_skill_ids(s, alias_to_id))
        n = len(rows_idx)
        core_names, core_ids, req_names, req_ids, opt_names, opt_ids, skill_freq = pick_skills(
            skill_counter, n, id_to_name)

        name = rec["role_name"]
        coarse = rec.get("coarse_role") or "Other IT"
        if rec["cluster_id"].startswith("kmeans:"):
            coarse = coarse_for_name(name, coarse)
        zh, needs_review = zh_name(name)

        search_keywords = [t for t in rec["top_norm_titles"] if t != name.lower()][:12]
        source_mix = dict(Counter(str(s) for s in sub["source"]))
        keywords = [w for w, _ in Counter(
            w for t in rec["top_norm_titles"][:8] for w in t.split()
            if w not in {"senior", "junior", "staff", "remote", "hybrid", ""}).most_common(12)]

        entry = {
            "role_id": role_id,
            "role_name": name,
            "fine_role": name,
            "coarse_role": coarse,
            "coarse_key": COARSE_TO_KEY.get(coarse, "other_it"),
            "size": n,
            "source_mix": source_mix,
            "search_keywords": search_keywords,
            "example_titles": rec["top_raw_titles"][:10],
            "keywords": keywords,
            "required_skills": req_names,
            "required_skill_ids": req_ids,
            "core_skills": core_names,
            "core_skill_ids": core_ids,
            "optional_skills": opt_names,
            "optional_skill_ids": opt_ids,
            "skill_freq": skill_freq,
            "role_name_zh": zh,
            "zh_review_needed": needs_review,
        }
        if rec.get("guard"):
            meta = rule_meta.get(rec["cluster_id"].split(":", 1)[1], {})
            entry["matcher_guard"] = meta.get("regex", "")
        v2_roles.append(entry)
        v2_taxonomy.append({
            "role_id": role_id,
            "category": coarse,
            "canonical_role": name,
            "aliases": search_keywords[:8],
            "top_skills": req_names[:10],
            "existing_jd_count": 0,
        })
        new_role_reports.append({
            "role_id": role_id,
            "role_name": name,
            "role_name_zh": zh,
            "zh_review_needed": needs_review,
            "coarse_role": coarse,
            "discovery_jd_count": n,
            "cohesion": rec["cohesion"],
            "it_ratio": rec["it_ratio"],
            "nearest_existing_role": rec["nearest_existing_role"],
            "nearest_existing_sim": rec["nearest_existing_sim"],
            "top_skills": req_names[:8],
            "top_titles": rec["top_norm_titles"][:8],
        })

    ROLES_V2_JSON.write_text(json.dumps(v2_roles, ensure_ascii=False, indent=2), encoding="utf-8")
    TAXONOMY_V2_JSON.write_text(json.dumps(v2_taxonomy, ensure_ascii=False, indent=2), encoding="utf-8")

    qc = {
        "inputs": {
            "unassigned_jd": int(len(un)),
            "embeddings": str(EMB_NPY),
            "kmeans_k": KMEANS_K,
            "min_cluster_size": MIN_CLUSTER_SIZE,
            "min_cohesion": MIN_COHESION,
            "min_it_ratio": MIN_IT_RATIO,
            "max_existing_sim": MAX_EXISTING_SIM,
        },
        "new_roles": new_role_reports,
        "dropped_clusters": sorted(dropped, key=lambda r: -r["size"]),
        "summary": {
            "v1_roles": len(v1_roles),
            "new_roles": len(new_role_reports),
            "v2_total": len(v2_roles),
        },
    }
    QC_JSON.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {ROLES_V2_JSON} ({len(v2_roles)} roles)")
    print(f"wrote {TAXONOMY_V2_JSON} ({len(v2_taxonomy)} roles)")
    print(f"wrote {QC_JSON}")
    for rep in new_role_reports:
        print(f"  + {rep['role_id']} {rep['role_name']:35s} n={rep['discovery_jd_count']:5d} "
              f"coh={rep['cohesion']:.3f} sim69={rep['nearest_existing_sim']:.3f} zh={rep['role_name_zh']}")


if __name__ == "__main__":
    main()
