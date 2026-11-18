"""统一 JD 数据集 v3：多源招聘 JD 读取 -> 标准化 -> IT 过滤 -> 去重 -> 按月分区输出。

覆盖窗口：2023-10 至 2026-10（含 unknown 分区存放无法解析日期的记录）。

数据源（均已本地下载，勿重新下载）：
  - zalizedata_tech_postings  主源，~39 万行 tech JD，skills 为 slug 列表
  - minmaxxxer_base / minmaxxxer_2026_10  每月快照，schema 规整（非纯 tech，需 IT 过滤）
  - nextgig_multi_ats  schema 最全（非纯 tech，需 IT 过滤；date_posted 缺失率高）
  - makenomistakes_9ats  纯 tech 小源，description 规整
  - jobicy_remote  远程岗 JSONL（按 jobIndustry 过滤 IT）
  - live_api/2026-10.json  remotive + jobicy API 当月抓取
  - joa_YYYY_MM  JOA 雇主直采月度快照（CC-BY-4.0，first_seen 作 posted_at；
    industry 缺失率高，按 title 白/黑名单过滤 IT）

用法：
  /var/lib/jobnav-env/bin/python pipelines/extract/unify_jd_v3.py

输出（幂等，先清空输出目录）：
  /data/shichaojian/JNIT/processed/jd_unified_v3/posted_month=YYYY-MM/part-0.parquet
  /data/shichaojian/JNIT/processed/jd_unified_v3/posted_month=unknown/part-0.parquet
  /data/shichaojian/JNIT/processed/jd_unified_v3/_qc_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

RAW_JD_DIR = Path("/data/shichaojian/JNIT/raw/jd")
DEFAULT_OUTPUT_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3")

WINDOW_START = pd.Timestamp("2023-10-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-10-31 23:59:59", tz="UTC")

# ---------------------------------------------------------------------------
# 近似汇率常量（-> USD），仅用于统一薪资口径，2026-10 近似值，QC 报告中注明。
FX_TO_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.74, "AUD": 0.66,
    "SGD": 0.74, "CHF": 1.12, "NZD": 0.60, "CNY": 0.14, "JPY": 0.0067,
    "INR": 0.012, "PLN": 0.25, "CZK": 0.043, "ZAR": 0.055, "AED": 0.27,
    "PHP": 0.017, "BRL": 0.18, "MXN": 0.055, "SEK": 0.095, "NOK": 0.094,
    "DKK": 0.145, "HKD": 0.128, "KRW": 0.00075,
}

# 薪资周期 -> 年倍率（按 2080 小时/年、260 工作日/年、52 周/年）
PERIOD_TO_ANNUAL = {
    "hour": 2080, "hourly": 2080, "day": 260, "daily": 260,
    "week": 52, "weekly": 52, "month": 12, "monthly": 12,
    "year": 1, "annual": 1, "yearly": 1,
}

# 各源加载时记录的输入/过滤统计（loader 内写入，main 汇总进 QC）
_LOAD_STATS: dict[str, dict] = {}


def record_stats(source: str, input_rows: int, it_filter_dropped: int = 0) -> None:
    _LOAD_STATS[source] = {
        "input_rows": int(input_rows),
        "it_filter_dropped": int(it_filter_dropped),
    }


# ---------------------------------------------------------------------------
# IT 岗位 title 过滤（仅用于 minmaxxxer / nextgig 等非纯 tech 源）。
# 规则：title（小写、空格归一）命中白名单且不命中黑名单才保留。
IT_TITLE_WHITELIST = [
    # 软件研发
    "software", "developer", "programmer", "web dev", "fullstack", "full-stack",
    "full stack", "frontend", "front-end", "front end", "backend", "back-end",
    "back end", "mobile dev", "ios dev", "android dev", "application dev",
    "app dev", " api", "microservice", "embedded", "firmware", "game dev",
    "unity dev", "unreal", "low-code", "salesforce", "sap ", "abap", "erp ",
    # 数据 / AI
    "data engineer", "data scientist", "data analyst", "data architect",
    "data ", "database", " dba", "etl", "business intelligence", "bi dev",
    "bi eng", "machine learning", "ml eng", "ml ops", "mlops", " ai ",
    "artificial intelligence", "deep learning", "computer vision", "nlp",
    " llm", "genai", "generative ai", "prompt engineer", "data science",
    # 运维 / 云 / 基础设施
    "devops", "sre", "site reliability", "cloud", "platform eng", "infrastructure",
    "kubernetes", "docker", "terraform", " aws", "azure", "gcp", "sysadmin",
    "system admin", "it admin", "network eng", "network admin", "data center",
    "it support", "it eng", "it manager", "it director", "helpdesk", "help desk",
    "service desk", "systems eng", "system eng", "release eng", "build eng",
    # 安全
    "cybersecurity", "cyber security", "security eng", "security analyst",
    "infosec", "information security", "soc analyst", "penetration", "devsecops",
    # 测试 / QA
    "qa ", " q a", "quality assurance", "test eng", "software test",
    "test automation", "automation eng", "sdet",
    # 技术产品 / 架构 / 管理
    "architect", "scrum master", "technical product", "product manager",
    "product owner", " cto", "vp of eng", "head of eng", "engineering manager",
    "tech lead", "technical lead", "delivery lead",
    # 其他技术岗
    "blockchain", "smart contract", "web3", "computer", "information technology",
    "digital ", "ux ", "ui ", "product designer", "web designer", "seo ",
    "it security", "iot", "computer vision eng",
]

IT_TITLE_BLACKLIST = [
    "nurse", "nursing", "clinical", "dentist", "physician", "pharmacist",
    "therapist", "teacher", "teaching", "professor", "tutor", "instructor",
    "sales representative", "sales associate", "account executive", "account manager",
    "sales development", "business development", "recruiter", "marketing", "real estate", "cashier",
    "warehouse", "driver", "delivery", "chef", " cook", "kitchen", "hair stylist", "barista",
    "mechanical eng", "civil eng", "electrical eng", "electronics eng",
    "instrument eng", "chemical eng", "process eng", "manufacturing eng",
    "industrial eng", "aerospace eng", "avionics", "structural eng", "construction",
    "plumber", "electrician", "welder", "technician - plant", "field service",
    "maintenance", "surveyor", "landscaper", "custodian", "janitor",
    "digital marketing", "digital media", "social media",
    "mechanic", "cnc", "machinist", "hair stylist", "makeup", "ausbildung",
    "mechatronik", "technico commercial", "supplier", "industrialization",
    "optician", "seamstress", "gardener", "housekeeper",
    "inspector", "civil", "geotechnical", "crane", "roofing",
    "injection molding", "welding", "carpenter",
]

# zalizedata department 白名单（子串匹配于小写归一、首尾补空格的 department）；
# 规则：title 黑名单全局生效 -> department 命中即保留 -> title 白名单命中保留 -> 其余丢弃。
ZALIZEDATA_IT_DEPT_TOKENS = [
    "engineering", "software", "technology", "information technology", " it ",
    "data", "database", "analytics", " product", "design", " ux", " ui ",
    "quality assurance", " qa", "devops", "development", "r&d", "research",
    "platform", "infrastructure", "cloud", "security", "cyber",
    "machine learning", "artificial intelligence", " ai ", "web", "systems",
    "application", "mobile", "gaming", "blockchain", "workday", "devops",
]

# jobicy jobIndustry 白名单（远程岗按行业筛 IT）
JOBICY_IT_INDUSTRIES = {
    "software engineering", "data science & analytics", "devops & infrastructure",
    "cybersecurity", "qa & testing", "technical support", "web, ui & ux design",
}

# fliarbi role / category 白名单（非纯 tech 源，先按结构化字段筛，title 兜底）
FLIARBI_IT_ROLES = {
    "software-eng", "data", "devops-cloud", "it-support", "security",
    "product", "design",
}
FLIARBI_IT_CATEGORIES = {"software & it", "computer & mathematical"}

UNIFIED_COLUMNS = [
    "job_id", "source", "title", "company", "location", "country", "is_remote",
    "employment_type", "seniority", "salary_min", "salary_max", "salary_currency",
    "salary_period", "salary_min_annual_usd", "salary_max_annual_usd",
    "skills", "posted_at", "posted_month", "url", "description_text",
]


# ---------------------------------------------------------------------------
def norm_text(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def norm_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", norm_text(value)).strip()


def is_it_title(title: str) -> bool:
    t = " " + norm_text(title) + " "
    if any(k in t for k in IT_TITLE_BLACKLIST):
        return False
    return any(k in t for k in IT_TITLE_WHITELIST)


def slug_skills(values) -> list[str]:
    """统一技能为小写 slug（空格/下划线 -> 连字符），保序去重。

    支持 list / JSON 字符串（双引号 list，含含撇号的合法 JSON）/ 分隔符字符串
    （nextgig 存在无括号逗号分隔形态，fliarbi 为管道分隔且段内可能再有逗号，
    故非 JSON 字符串统一按逗号或管道切分，避免整串被当成单个技能）。
    """
    if values is None:
        return []
    if isinstance(values, (int, float, np.integer)) and not isinstance(values, bool):
        return []  # 标量脏数据 / NaN
    if isinstance(values, str):
        s = values.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    values = parsed
                else:
                    return []
            except json.JSONDecodeError:
                # 单引号 Python-repr 等非法 JSON：去括号后按分隔符兜底切分
                values = re.split(r"[,|]", s.strip("[]"))
        else:
            values = re.split(r"[,|]", s)
    if not isinstance(values, (list, tuple, np.ndarray)):
        values = [values]
    out, seen = [], set()
    for v in values:
        s = re.sub(r"[\s_]+", "-", norm_text(v))
        s = re.sub(r"-{2,}", "-", s).strip("-\"'")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def parse_dates(series: pd.Series) -> pd.Series:
    """健壮解析混合格式时间字符串，统一 UTC；失败为 NaT。"""
    if series.dtype.kind == "M":
        return pd.to_datetime(series, utc=True)
    return pd.to_datetime(series, format="mixed", utc=True, errors="coerce")


def make_job_id(source: str, *parts) -> str:
    raw = "|".join(str(p) for p in parts if p)
    if raw:
        return f"{source}:{hashlib.md5(raw.encode()).hexdigest()[:16]}"
    return f"{source}:{hashlib.md5(np.random.bytes(8)).hexdigest()[:16]}"


def normalize_salary(df: pd.DataFrame, annual_cols: tuple[str, str] | None = None) -> pd.DataFrame:
    """按 currency * period 换算出年薪 USD 列。"""
    df = df.copy()
    for col in ("salary_currency", "salary_period"):
        df[col] = df[col].astype("string").str.strip().str.lower()
    period_factor = df["salary_period"].map(PERIOD_TO_ANNUAL)
    fx = df["salary_currency"].str.upper().map(FX_TO_USD)
    for src, dst in (("salary_min", "salary_min_annual_usd"), ("salary_max", "salary_max_annual_usd")):
        annual = pd.to_numeric(df[src], errors="coerce") * period_factor * fx
        if annual_cols:
            fallback = pd.to_numeric(df[annual_cols[0 if src == "salary_min" else 1]], errors="coerce") * fx
            annual = annual.fillna(fallback)
        # 合理性截断：年薪 USD 超过 5M 视为脏数据
        annual = annual.where((annual >= 500) & (annual <= 5_000_000))
        df[dst] = annual.round(0)
    return df


def finalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """统一窗口过滤、posted_month 生成、列对齐。"""
    df = df.copy()
    df["source"] = source
    df["posted_at"] = parse_dates(df["posted_at"])
    # 日期落在覆盖窗口外（未来或早于 2023-10）的记录打标记，由 main 统一剔除
    df["_out_of_window"] = df["posted_at"].notna() & (
        (df["posted_at"] < WINDOW_START) | (df["posted_at"] > WINDOW_END)
    )
    df["posted_month"] = df["posted_at"].dt.strftime("%Y-%m")
    df["_unparsed_date"] = df["posted_at"].isna()
    for col in UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA if col not in ("skills",) else None
    df["skills"] = df["skills"].apply(lambda s: s if isinstance(s, list) else [])
    for col in ("salary_min", "salary_max"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("salary_currency", "salary_period", "employment_type", "seniority",
                "location", "country", "company", "title"):
        df[col] = df[col].astype("string")
    df["is_remote"] = (df["is_remote"].map({True: True, False: False, "true": True,
                                            "false": False, "True": True, "False": False})
                       .astype("boolean"))
    df["description_text"] = df["description_text"].astype("string")
    df["url"] = df["url"].astype("string")
    return df[UNIFIED_COLUMNS + ["_out_of_window", "_unparsed_date"]]


# ---------------------------------------------------------------------------
ZALIZEDATA_NON_IT_DEPT_TOKENS = [
    "sales", "marketing", "recruiting", "human resources", "legal", "finance",
    "clinical", "nursing", "retail", "hospitality", "restaurant", "construction",
    "real estate", "teacher", "store", "warehouse", "logistics", "procurement",
]


def is_it_department(department) -> bool:
    if not isinstance(department, str) or not department.strip():
        return False
    t = " " + re.sub(r"\s+", " ", department).strip().lower() + " "
    if any(k in t for k in ZALIZEDATA_NON_IT_DEPT_TOKENS):
        return False
    return any(k in t for k in ZALIZEDATA_IT_DEPT_TOKENS)


def load_zalizedata(raw_dir: Path) -> pd.DataFrame:
    fp = raw_dir / "zalizedata_tech_postings/data/L/jobs-00000-of-00001.parquet"
    df = pd.read_parquet(fp)
    record_stats("zalizedata", len(df))
    df = df.rename(columns={
        "company_name": "company", "location_raw": "location",
    })
    # IT 过滤：title 黑名单全局生效；department 白名单命中或 title 白名单命中才保留
    dept_hit = df["department"].apply(is_it_department)
    title_ok = df["title"].apply(is_it_title)
    keep = title_ok | dept_hit
    st = _LOAD_STATS["zalizedata"]
    st["it_filter_dropped"] = int((~keep).sum())
    st["kept_by_department"] = int((keep & dept_hit).sum())
    st["kept_by_title_only"] = int((keep & ~dept_hit).sum())
    df = df[keep]
    df["job_id"] = "zalizedata:" + df["job_id"].astype(str)
    df["seniority"] = pd.NA
    df["description_text"] = pd.NA
    df["skills"] = df["skills"].apply(slug_skills)
    df = normalize_salary(df)
    return finalize(df, "zalizedata")


def load_minmaxxxer(raw_dir: Path, sub: str, file: str, source: str) -> pd.DataFrame:
    fp = raw_dir / sub / file
    df = pd.read_parquet(fp)
    df["location"] = df["location"].fillna(df["city"])
    df["country"] = df["country_code"]
    wt = df["workplace_type"].astype("string").str.lower()
    df["is_remote"] = wt.eq("remote")
    df["url"] = df["url"].fillna(df["apply_url"])
    df["job_id"] = source + ":" + df["job_id"].astype(str)
    df["skills"] = None
    df["description_text"] = df["description"]
    df = normalize_salary(df, annual_cols=("salary_min_annual", "salary_max_annual"))
    keep = df["title"].apply(is_it_title)
    record_stats(source, len(df), int((~keep).sum()))
    return finalize(df[keep], source)


def load_nextgig(raw_dir: Path) -> pd.DataFrame:
    fp = raw_dir / "nextgig_multi_ats/nextgig_jobs_2026-06.parquet"
    df = pd.read_parquet(fp)
    record_stats("nextgig", len(df))
    df = df.rename(columns={
        "company_name": "company", "date_posted": "posted_at",
        "job_description": "description_text", "salary_rate_unit": "salary_period",
    })
    df["job_id"] = [make_job_id("nextgig", t, c, ci, str(d)[:200]) for t, c, ci, d in
                    zip(df["title"], df["company"], df["city"], df["description_text"])]
    wm = df["work_model"].astype("string").str.lower()
    df["is_remote"] = wm.eq("remote")
    df["location"] = df["location_resolved"].fillna(df["city"])
    df["skills"] = df["skills_required"].apply(slug_skills)
    df["seniority"] = df["experience_level"].astype("string").str.lower().map(
        lambda s: pd.NA if pd.isna(s)
        else "internship" if "intern" in s
        else "entry" if "entry" in s
        else "executive" if ("execut" in s or "director" in s)
        else "senior" if "senior" in s
        else "mid" if "mid" in s else pd.NA
    )
    df = normalize_salary(df)
    keep = df["title"].apply(is_it_title)
    _LOAD_STATS["nextgig"]["it_filter_dropped"] = int((~keep).sum())
    return finalize(df[keep], "nextgig")


def load_fliarbi(raw_dir: Path) -> pd.DataFrame:
    """fliarbi/job-postings-2026：公开版覆盖 2026-01..2026-06（印度+美国）。

    role/category 结构化字段筛 IT，title 白名单兜底；skills 为管道分隔字符串；
    salary_annual_usd 直接作为 min/max 年薪 USD。
    """
    fp = raw_dir / "fliarbi_2026/data.parquet"
    df = pd.read_parquet(fp)
    record_stats("fliarbi", len(df))
    df = df.rename(columns={
        "posted_date": "posted_at", "fliar_profile_url": "url",
    })
    df["job_id"] = "fliarbi:" + df["posting_id"].astype(str)
    df["location"] = df["city"].fillna("") + ", " + df["region"].fillna("")
    df["location"] = df["location"].str.replace(r"^, |, $", "", regex=True)
    df["location"] = df["location"].replace("", pd.NA)
    df["is_remote"] = df["remote"].eq("remote")
    df["employment_type"] = pd.NA
    df["seniority"] = df["seniority"].map(_norm_seniority)
    df["salary_min"] = df["salary_annual_usd"]
    df["salary_max"] = df["salary_annual_usd"]
    df["salary_currency"] = "usd"
    df["salary_period"] = "year"
    df["skills"] = df["skills"].apply(slug_skills)
    df["description_text"] = pd.NA
    df = normalize_salary(df)

    role = df["role"].map(norm_text)
    category = df["category"].map(norm_text)
    title_ok = df["title"].apply(is_it_title)
    keep = (title_ok
            | role.isin(FLIARBI_IT_ROLES)
            | category.isin(FLIARBI_IT_CATEGORIES))
    _LOAD_STATS["fliarbi"]["it_filter_dropped"] = int((~keep).sum())
    return finalize(df[keep], "fliarbi")


def load_makenomistakes(raw_dir: Path) -> pd.DataFrame:
    fp = raw_dir / "makenomistakes_9ats/tech_jobs_9_ats_2026-09-22.parquet"
    df = pd.read_parquet(fp)
    record_stats("makenomistakes", len(df))
    df["location"] = df["location_raw"].fillna(df["city"])
    df["url"] = df["apply_url"].fillna(df["source_url"])
    df["job_id"] = "makenomistakes:" + df["job_id"].astype(str)
    df["skills"] = None
    df["seniority"] = pd.NA
    df = normalize_salary(df)
    return finalize(df, "makenomistakes")


def _norm_seniority(value) -> object:
    s = norm_text(value)
    if not s:
        return pd.NA
    if "intern" in s:
        return "internship"
    if "entry" in s or "junior" in s:
        return "entry"
    if "execut" in s or "director" in s or "vp" in s or "head" in s:
        return "executive"
    if "senior" in s or "lead" in s or "principal" in s or "staff" in s:
        return "senior"
    if "mid" in s:
        return "mid"
    return pd.NA


def _jobicy_frame(records: list[dict], source: str) -> pd.DataFrame:
    rows = []
    dropped = 0
    for r in records:
        industries = {norm_text(i) for i in (r.get("jobIndustry") or [])}
        it_by_industry = bool(industries & JOBICY_IT_INDUSTRIES)
        it_by_title = is_it_title(r.get("jobTitle", ""))
        if (industries and not (it_by_industry or it_by_title)) or (
                not industries and not it_by_title):
            dropped += 1
            continue
        rows.append({
            "job_id": f"{source}:{r.get('id')}",
            "title": r.get("jobTitle"),
            "company": r.get("companyName"),
            "location": r.get("jobGeo"),
            "country": pd.NA,
            "is_remote": True,
            "employment_type": r.get("jobType"),
            "seniority": _norm_seniority(r.get("jobLevel")),
            "salary_min": r.get("salaryMin"),
            "salary_max": r.get("salaryMax"),
            "salary_currency": r.get("salaryCurrency"),
            "salary_period": r.get("salaryPeriod"),
            "skills": None,
            "posted_at": r.get("pubDate"),
            "url": r.get("url"),
            "description_text": r.get("jobDescription"),
        })
    record_stats(source, len(records), dropped)
    df = pd.DataFrame(rows)
    if df.empty:
        return finalize(df, source)
    df = normalize_salary(df)
    return finalize(df, source)


def load_jobicy_daily(raw_dir: Path) -> pd.DataFrame:
    records = []
    for fp in sorted((raw_dir / "jobicy_remote/data/daily").glob("*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return _jobicy_frame(records, "jobicy")


def load_joa(raw_dir: Path) -> pd.DataFrame:
    """JOA 雇主直采月度快照（JobOpportunitiesAPI/joa-employer-direct-job-postings-YYYY-MM）。

    JSONL，25k 行/月；schema 与 minmaxxxer 同构但更精简。industry 字段
    缺失率 ~60%，IT 过滤沿用 title 白/黑名单；first_seen_at 作 posted_at
    （岗位首次被 JOA 观察到的月份，非原始发布日）。
    """
    frames = []
    for sub in sorted(raw_dir.glob("joa_*")):
        source = sub.name  # joa_2026_10
        jsonls = sorted(sub.glob("*.jsonl"))
        jsonls = [f for f in jsonls if not f.name.startswith(".")]
        if not jsonls:
            continue
        records = []
        for fp in jsonls:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        df = pd.DataFrame(records)
        if df.empty:
            continue
        df = df.rename(columns={"employer": "company", "apply_url": "url",
                                "first_seen_at": "posted_at"})
        df["job_id"] = f"{source}:" + df["job_id"].astype(str)
        df["description_text"] = df.get("description")
        df["skills"] = None
        df["seniority"] = pd.NA
        df["is_remote"] = pd.NA  # 快照无 workplace_type 字段
        # 脏字符串兜底：'None'/'' -> NA
        for col in ("salary_min", "salary_max"):
            df[col] = (df[col].replace({"None": None, "": None})
                       if col in df else pd.NA)
        df = normalize_salary(df)
        keep = df["title"].apply(is_it_title)
        # 各月快照汇总进统一 "joa" 源条目（main 按 loader 名取统计）
        agg = _LOAD_STATS.setdefault("joa", {"input_rows": 0, "it_filter_dropped": 0})
        agg["input_rows"] += len(df)
        agg["it_filter_dropped"] += int((~keep).sum())
        agg.setdefault("snapshots", []).append(
            {"dir": sub.name, "input_rows": int(len(df)),
             "kept": int(keep.sum())})
        frames.append(finalize(df[keep], source))
    if not frames:
        return finalize(pd.DataFrame(), "joa")
    return pd.concat(frames, ignore_index=True)


def load_live_api(raw_dir: Path) -> pd.DataFrame:
    fp = raw_dir / "live_api/2026-10.json"
    with open(fp, encoding="utf-8") as f:
        payload = json.load(f)
    remotive = payload.get("remotive", {}).get("jobs", [])
    jobicy = payload.get("jobicy", {}).get("jobs", [])
    record_stats("remotive", len(remotive))
    frames = []
    if remotive:
        df = pd.DataFrame([{
            "job_id": f"remotive:{r.get('id')}",
            "title": r.get("title"),
            "company": r.get("company_name"),
            "location": r.get("candidate_required_location"),
            "country": pd.NA,
            "is_remote": True,
            "employment_type": r.get("job_type"),
            "seniority": pd.NA,
            "salary_min": pd.NA, "salary_max": pd.NA,
            "salary_currency": pd.NA, "salary_period": pd.NA,
            "skills": slug_skills(r.get("tags") or []),
            "posted_at": r.get("publication_date"),
            "url": r.get("url"),
            "description_text": r.get("description"),
        } for r in remotive])
        df = normalize_salary(df)
        frames.append(finalize(df, "remotive"))
    if jobicy:
        frames.append(_jobicy_frame(jobicy, "jobicy_api"))
    record_stats("live_api", len(remotive) + len(jobicy),
                 _LOAD_STATS.get("jobicy_api", {}).get("it_filter_dropped", 0))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
def richness_score(df: pd.DataFrame) -> pd.Series:
    return (
        df["skills"].apply(len).clip(upper=1) * 3
        + df["salary_min_annual_usd"].notna().astype(int) * 2
        + df["description_text"].notna().astype(int)
    )


def dedup(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """去重：先按规范化 url，再按 (规范化 title, 规范化 company, posted_month)。

    同一 (title, company, month) 键下的多条记录若来自多个源，判定为同一岗位的
    跨源重复抓取，保留信息更全的一条；若全部来自同一源，视为同公司在招的多个
    不同 opening（url/城市不同），予以保留。
    """
    df = df.copy()
    df["_norm_title"] = df["title"].map(norm_key)
    df["_norm_company"] = df["company"].map(norm_key)
    df["_url_key"] = df["url"].fillna("").map(norm_text)
    df["_score"] = richness_score(df)

    # title/company 为空的记录不参与键去重（键加上 job_id 保证唯一）
    no_key = df["_norm_title"].eq("") | df["_norm_company"].eq("")
    df.loc[no_key, "_norm_title"] = "noid:" + df.loc[no_key, "job_id"].astype(str)

    stats = {}
    # 1) 按 url 去重（url 相同即同一职位页，跨源或同源重复均只留信息更全的一条）
    with_url = df["_url_key"].ne("")
    before = int(with_url.sum())
    url_part = (df[with_url].sort_values("_score", ascending=False)
                .drop_duplicates(subset=["_url_key"], keep="first"))
    stats["dedup_removed_by_url"] = int(before - len(url_part))
    df = pd.concat([url_part, df[~with_url]], ignore_index=True)

    # 2) 跨源同键去重：(规范化 title, 规范化 company, posted_month)
    known = df["posted_month"].notna()
    unknown_key = pd.Series(
        "unknown:" + pd.util.hash_pandas_object(
            df["url"].fillna("") + "|" + df["description_text"].fillna("").str[:512],
            index=False,
        ).astype(str),
        index=df.index,
    )
    df["_month_key"] = df["posted_month"].where(known, unknown_key)
    key_cols = ["_norm_title", "_norm_company", "_month_key"]
    cross_source = df.groupby(key_cols, dropna=False, sort=False)["source"].transform("nunique").gt(1)
    before = int(cross_source.sum())
    cross_part = (df[cross_source].sort_values("_score", ascending=False)
                  .drop_duplicates(subset=key_cols, keep="first"))
    stats["dedup_removed_cross_source_same_job"] = int(before - len(cross_part))
    df = pd.concat([df[~cross_source], cross_part], ignore_index=True)
    return df.drop(columns=["_norm_title", "_norm_company", "_url_key", "_score", "_month_key"]), stats


def build_qc(df: pd.DataFrame, source_stats: dict, dedup_stats: dict,
             monthly: pd.Series, total_input: int) -> dict:
    n = len(df)
    month_index = pd.period_range("2023-10", "2026-10", freq="M").astype(str)
    monthly_table = {m: int(monthly.get(m, 0)) for m in month_index}
    monthly_table["unknown"] = int(monthly.get("unknown", 0))

    top_titles = (df["title"].map(norm_text).value_counts().head(30)
                  .rename_axis("title").reset_index(name="count"))
    skills_nonempty = df["skills"].apply(len).gt(0).mean()
    salary_nonempty = df["salary_min_annual_usd"].notna().mean()
    desc_nonempty = df["description_text"].notna().mean()

    # 按月 skills 非空率 + 近三月逐源构成（供下游评估趋势可信度）
    df = df.copy()
    df["_month"] = df["posted_month"].fillna("unknown")
    monthly_skills = {}
    recent_composition = {}
    for m in list(month_index) + ["unknown"]:
        part = df[df["_month"] == m]
        if not len(part):
            monthly_skills[m] = {"rows": 0, "skills_nonempty_ratio": None, "by_source": {}}
            continue
        by_source = {}
        for src, g in part.groupby("source"):
            by_source[src] = {
                "rows": int(len(g)),
                "skills_nonempty_ratio": round(float(g["skills"].apply(len).gt(0).mean()), 4),
            }
        monthly_skills[m] = {
            "rows": int(len(part)),
            "skills_nonempty_ratio": round(float(part["skills"].apply(len).gt(0).mean()), 4),
            "by_source": by_source,
        }
    for m in ("2026-08", "2026-09", "2026-10"):
        recent_composition[m] = monthly_skills[m]

    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "window": ["2023-10", "2026-10"],
        "total_input_rows": total_input,
        "total_output_rows": n,
        "unparsed_date_rows": int(df["_unparsed_date"].sum()),
        "unparsed_date_ratio": round(float(df["_unparsed_date"].mean()), 4),
        "sources": source_stats,
        "dedup": dedup_stats,
        "monthly_distribution": monthly_table,
        "monthly_skills_nonempty": monthly_skills,
        "recent_months_source_composition": recent_composition,
        "coverage": {
            "recent_3_months_2026_08_09_10": int(sum(monthly_table[m] for m in
                                                     ("2026-08", "2026-09", "2026-10"))),
            "share_from_2023_10_onwards": round(
                float(sum(v for k, v in monthly_table.items() if k != "unknown")) / n, 4),
        },
        "field_quality": {
            "skills_nonempty_ratio": round(float(skills_nonempty), 4),
            "salary_annual_usd_nonempty_ratio": round(float(salary_nonempty), 4),
            "description_nonempty_ratio": round(float(desc_nonempty), 4),
        },
        "top_30_titles": top_titles.to_dict(orient="records"),
        "fx_constants_to_usd": FX_TO_USD,
        "notes": [
            "薪资 USD 年化为近似汇率常量换算（见 fx_constants_to_usd），2026-10 时点近似值，非精确汇率。",
            "无法解析 posted_at 的记录保留在 posted_month=unknown 分区，不进入月度时序；日期解析成功但落在 2023-10..2026-10 窗口外的记录已剔除（见 dedup.out_of_window_rows_dropped）。",
            "IT 过滤采用 pipelines/extract/unify_jd_v3.py 内显式白/黑名单：zalizedata 用 department 白名单优先+title 兜底；minmaxxxer/nextgig 用 title 白/黑名单；fliarbi 用 role/category 白名单+title 兜底；jobicy 用 jobIndustry 白名单+title 兜底。",
            "各源 skills 可用性：zalizedata/nextgig/fliarbi/remotive 有现成 skills/tags 已并入统一 skills 列；makenomistakes/minmaxxxer/joa 无技能字段、jobicy 无 tags 字段，skills 留空由下游抽取。",
            "去重：先按规范化 url；再按 (规范化 title, 规范化 company, posted_month) 键做跨源同岗去重——同键且来源>=2 个源时保留 skills/薪资/description 更全的一条；同键但全部来自同一源时视为同公司同月在招的不同 opening，予以保留。",
            "fliarbi/job-postings-2026 公开版数据范围为 2026-01-01..2026-06-30（印度+美国，README 明确声明），无法补充 2026-07 之后月份；近三月覆盖仍依赖 zalizedata/makenomistakes/minmaxxxer/jobicy。",
            "2026-08/09/10 近三个月行数受限于已下载源的实际覆盖（zalizedata 止于 2026-08，makenomistakes 止于 2026-09，minmaxxxer 两个快照 IT 过滤保留约 23%），无法从现有原始数据达到 3 万行。",
            "近三月 skills 非空率低是源结构性的：2026-09/10 的行几乎全部来自 makenomistakes/minmaxxxer/jobicy（均无技能字段），仅 remotive/nextgig 有技能；详见 monthly_skills_nonempty 与 recent_months_source_composition。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="构建统一 JD 数据集 v3")
    parser.add_argument("--raw-dir", type=Path, default=RAW_JD_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    loaders = [
        ("zalizedata", load_zalizedata, False),
        ("minmaxxxer_base", lambda d: load_minmaxxxer(d, "minmaxxxer_base",
                                                     "job_postings_with_salaries.parquet",
                                                     "minmaxxxer_base"), True),
        ("minmaxxxer_2026_10", lambda d: load_minmaxxxer(d, "minmaxxxer_2026_10",
                                                         "job_postings_with_salaries_2026_10.parquet",
                                                         "minmaxxxer_2026_10"), True),
        ("nextgig", load_nextgig, True),
        ("makenomistakes", load_makenomistakes, False),
        ("fliarbi", load_fliarbi, True),
        ("jobicy", load_jobicy_daily, False),
        ("live_api", load_live_api, False),
        ("joa", load_joa, True),
    ]

    frames, source_stats = [], {}
    for name, loader, _ in loaders:
        df = loader(args.raw_dir)
        frames.append(df)
        stats = dict(_LOAD_STATS.get(name, {}))
        stats["rows_after_window_and_filter"] = int(len(df))
        stats["unparsed_date_rows"] = int(df["_unparsed_date"].sum())
        source_stats[name] = stats
    total_input = sum(s.get("input_rows", 0) for s in _LOAD_STATS.values())

    merged = pd.concat(frames, ignore_index=True)
    deduped, dedup_stats = dedup(merged)

    # 剔除覆盖窗口外（早于 2023-10 或晚于 2026-10）的记录
    n_oow = int(deduped["_out_of_window"].sum())
    in_window = deduped[~deduped["_out_of_window"]]
    dedup_stats["out_of_window_rows_dropped"] = n_oow

    out_df = in_window.drop(columns=["_out_of_window", "_unparsed_date"])
    out_df["posted_month"] = out_df["posted_month"].fillna("unknown")
    monthly = out_df["posted_month"].value_counts()

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for month, part in out_df.groupby("posted_month", sort=True):
        part_dir = args.output_dir / f"posted_month={month}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["posted_month"]).to_parquet(part_dir / "part-0.parquet", index=False)

    qc = build_qc(in_window, source_stats, dedup_stats, monthly, total_input)
    with open(args.output_dir / "_qc_report.json", "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=2)

    print(json.dumps({k: qc[k] for k in (
        "total_output_rows", "coverage", "field_quality", "dedup")}, ensure_ascii=False, indent=2))
    print("\n月度分布 (2023-10 .. 2026-10 + unknown):")
    for m, c in qc["monthly_distribution"].items():
        print(f"  {m}: {c}")


if __name__ == "__main__":
    main()
