"""ingest_jd: 多源 JD 统一入库.

把 zalizedata / minmaxxxer / nextgig / makenomistakes / jobicy 五个来源的
JD 数据（外加可选的 live_api 实时 API 月度快照，目录不存在时为空）
统一成一张宽表，按 posted_month 分区写到
``/data/shichaojian/JNIT/processed/jd_unified/``，description 大文本单独写到
``/data/shichaojian/JNIT/processed/jd_descriptions/{source}.parquet``，
并在 ``jd_unified/_qc_report.json`` 输出 QC 报告。

入口: ``python -m pipelines.foundation.ingest_jd`` （幂等，重复运行覆盖输出）.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_JD = Path("/data/shichaojian/JNIT/raw/jd")
OUT_UNIFIED = Path("/data/shichaojian/JNIT/processed/jd_unified")
OUT_DESCRIPTIONS = Path("/data/shichaojian/JNIT/processed/jd_descriptions")

MIN_POSTED_AT = pd.Timestamp("2020-01-01", tz="UTC")
# 发布时间晚于当前月份的视为异常（抓取错误或占位日期）
MAX_POSTED_AT = pd.Timestamp("2026-11-01", tz="UTC")

# 明显异常的薪资年化阈值（原币种数值，近似 USD 等值口径）
SALARY_ANNUAL_MIN = 10_000.0
SALARY_ANNUAL_MAX = 2_000_000.0

# 薪资周期 -> 年化乘数
SALARY_PERIOD_FACTOR = {
    "year": 1.0, "yearly": 1.0, "annual": 1.0, "annually": 1.0,
    "month": 12.0, "monthly": 12.0,
    "week": 52.0, "weekly": 52.0,
    "day": 260.0, "daily": 260.0,
    "hour": 2080.0, "hourly": 2080.0,
}

# 跨源去重优先级：有 description 的 minmaxxxer > 有 skills 的 zalizedata > 其他；
# live_api（remotive/jobicy 实时 API 月度快照）优先级最低，与静态源冲突时被去重剔除
SOURCE_PRIORITY = {
    "minmaxxxer": 0,
    "zalizedata": 1,
    "makenomistakes": 2,
    "nextgig": 3,
    "jobicy": 4,
    "live_remotive": 5,
    "live_jobicy": 6,
}

# IT 岗位轻量过滤：标题命中黑名单且未命中白名单则剔除
# （词边界匹配，避免 sales 命中 Salesforce、it 命中 waiter 之类误伤）
IT_TITLE_BLACKLIST = re.compile(
    r"\b(?:"
    r"sales|sale|seller|marketing|marketer|hr|human[\s-]?resources|recruit\w*|"
    r"talent acquisition|finance|financial|accountant|accounting|account manager|"
    r"account executive|chef|cook|nurse|nursing|teacher|teaching|professor|"
    r"lawyer|attorney|paralegal|real estate|realtor|warehouse|driver|delivery|"
    r"cashier|barista|bartender|waiter|waitress|hostess|hotel|restaurant|"
    r"hospitality|retail|merchandis\w*|store manager|physician|doctor|dentist|"
    r"therapist|chiropractor|veterinar\w*|pilot|flight attendant|mechanic|"
    r"surgeon|auditor|midwife|paramedic|emt|optometrist|pharmacist|"
    r"plumber|electrician|carpenter|construction|landscaper|janitor|housekeeper|"
    r"security guard|cosmetolog\w*|hairdress\w*|beautician|tailor|forklift|"
    r"welder|roofer|mason|bank teller|loan officer|insurance agent"
    r")\b", re.IGNORECASE)

IT_TITLE_WHITELIST = re.compile(
    r"\b(?:"
    r"engineer\w*|developer|devops|programmer|software|cloud|data|analyst|analytics|"
    r"machine[\s-]?learning|python|java|javascript|typescript|react|angular|vue|"
    r"frontend|front[\s-]?end|backend|back[\s-]?end|full[\s-]?stack|mobile|android|"
    r"database|architect|sysadmin|system[\s-]?admin|network|cybersecurity|security|"
    r"qa|quality assurance|test\w*|automation|kubernetes|docker|salesforce|sap|"
    r"sharepoint|tableau|scrum|site reliability|\bsre\b|helpdesk|help[\s-]?desk|"
    r"technical support|business intelligence|power[\s-]?bi|\bdba\b|\biot\b|"
    r"blockchain|\bai\b|\bml\b|\bit\b|\bbi\b|\bmlops\b|dataops"
    r")\b", re.IGNORECASE)

# zalizedata 的 department 可辅助判断：标题命中黑名单但部门明显是技术部门则保留
IT_DEPARTMENT_WHITELIST = re.compile(
    r"\b(?:engineer\w*|technology|software|data|product|dev\w*|\bit\b|platform|"
    r"infrastructure|security|cloud|research|science|technical|qa|design|"
    r"information systems?|digital)\b", re.IGNORECASE)

UNIFIED_COLUMNS = [
    "job_id", "source", "title", "company", "country", "city", "is_remote",
    "employment_type", "seniority", "salary_min_annual", "salary_max_annual",
    "salary_currency", "skills", "has_description", "posted_at",
    "posted_month", "url",
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _sha12(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _norm_key(text: object) -> str:
    """去重用归一化：小写、去所有非字母数字字符。"""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _clean_str(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})


def _parse_skills(value: object) -> list:
    """健壮解析 skills：numpy array / list / stringified list / 'nan' 字符串."""
    if value is None:
        return []
    if isinstance(value, float) and np.isnan(value):
        return []
    if isinstance(value, str):
        v = value.strip()
        if not v or v.lower() in ("nan", "none", "null"):
            return []
        if v.startswith(("[", "(")):
            try:
                import ast
                parsed = ast.literal_eval(v)
                if isinstance(parsed, (list, tuple)):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except (ValueError, SyntaxError):
                pass
            inner = v.strip("[]()")
            return [x.strip().strip("'\"") for x in inner.split(",") if x.strip().strip("'\"")]
        return [v]
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value)]


def _annualize(salary: pd.Series, period: pd.Series) -> pd.Series:
    """按周期把薪资统一成年化数值；周期缺失时原样返回。"""
    factor = (
        period.astype("string")
        .str.strip().str.lower()
        .map(lambda p: SALARY_PERIOD_FACTOR.get(p, np.nan))
    )
    out = pd.to_numeric(salary, errors="coerce")
    has_factor = factor.notna()
    out = out.astype("float64")
    out.loc[has_factor] = out.loc[has_factor] * factor.loc[has_factor].astype("float64")
    return out


def _clean_salary(lo: pd.Series, hi: pd.Series) -> tuple[pd.Series, pd.Series]:
    """明显异常的年化薪资（<1万 或 >200万）置空；min>max 时对调。"""
    lo = pd.to_numeric(lo, errors="coerce").astype("float64")
    hi = pd.to_numeric(hi, errors="coerce").astype("float64")
    for s in (lo, hi):
        s[(s < SALARY_ANNUAL_MIN) | (s > SALARY_ANNUAL_MAX)] = np.nan
    swapped = lo.notna() & hi.notna() & (lo > hi)
    lo.loc[swapped], hi.loc[swapped] = hi.loc[swapped], lo.loc[swapped]
    return lo, hi


def _norm_employment(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip().str.lower().str.replace(r"[^a-z]+", "_", regex=True)
    out = pd.Series(pd.NA, index=s.index, dtype="string")
    out[t.str.contains("intern", na=False)] = "internship"
    m = out.isna() & t.str.contains("full", na=False)
    out[m] = "full_time"
    m = out.isna() & t.str.contains("part", na=False)
    out[m] = "part_time"
    m = out.isna() & t.str.contains(r"contract|freelance|independent|temp", na=False)
    out[m] = "contract"
    return out


def _norm_seniority(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip().str.lower()
    out = pd.Series(pd.NA, index=s.index, dtype="string")
    out[t.str.contains("intern", na=False)] = "internship"
    m = out.isna() & t.str.contains(r"entry|junior|jr\b|graduate|assoc", na=False)
    out[m] = "junior"
    m = out.isna() & t.str.contains(r"\bmid\b|middle", na=False)
    out[m] = "mid"
    m = out.isna() & t.str.contains(r"senior|sr\b", na=False)
    out[m] = "senior"
    m = out.isna() & t.str.contains(
        r"lead|principal|staff|director|executive|head|chief", na=False)
    out[m] = "lead"
    return out


def _to_utc(series: pd.Series) -> pd.Series:
    """多种日期格式 -> tz-aware UTC；无法解析为 NaT。"""
    return pd.to_datetime(series, format="mixed", errors="coerce", utc=True)


def _is_it_title(title: object, department: object = None) -> bool:
    t = "" if title is None or (isinstance(title, float) and np.isnan(title)) else str(title)
    if not IT_TITLE_BLACKLIST.search(t):
        return True
    if IT_TITLE_WHITELIST.search(t):
        return True
    if department is not None and not (
            isinstance(department, float) and np.isnan(department)) \
            and IT_DEPARTMENT_WHITELIST.search(str(department)):
        return True
    return False


def _frame(job_key, source, title, company, country, city, is_remote,
           employment_type, seniority, salary_min_annual, salary_max_annual,
           salary_currency, skills, description, posted_at, url,
           department=None) -> pd.DataFrame:
    df = pd.DataFrame({
        "job_key": job_key, "title": title, "company": company,
        "country": country, "city": city, "is_remote": is_remote,
        "employment_type": employment_type, "seniority": seniority,
        "salary_min_annual": salary_min_annual,
        "salary_max_annual": salary_max_annual,
        "salary_currency": salary_currency, "skills": skills,
        "description": description, "posted_at": posted_at, "url": url,
        "department": department,
    })
    df["source"] = source
    return df


# ---------------------------------------------------------------------------
# 各源 loader: 输出统一中间 schema（宽字段 + department 辅助列）
# ---------------------------------------------------------------------------

def load_zalizedata() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_JD / "zalizedata_tech_postings/data/*/jobs-*.parquet")))
    cols = ["job_id", "title", "company_name", "country", "city", "is_remote",
            "employment_type", "salary_min", "salary_max", "salary_currency",
            "salary_period", "skills", "posted_at", "url", "department"]
    parts = [pd.read_parquet(f, columns=cols) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates(subset=["job_id"])  # M/S 内部有少量重复 job_id
    return _frame(
        job_key=df["job_id"], source="zalizedata",
        title=_clean_str(df["title"]), company=_clean_str(df["company_name"]),
        country=_clean_str(df["country"]), city=_clean_str(df["city"]),
        is_remote=df["is_remote"].astype("boolean"),
        employment_type=_norm_employment(df["employment_type"]),
        seniority=pd.Series(pd.NA, index=df.index, dtype="string"),
        salary_min_annual=_annualize(df["salary_min"], df["salary_period"]),
        salary_max_annual=_annualize(df["salary_max"], df["salary_period"]),
        salary_currency=_clean_str(df["salary_currency"]),
        skills=df["skills"].map(_parse_skills),
        description=pd.Series(pd.NA, index=df.index, dtype="string"),
        posted_at=_to_utc(df["posted_at"]),
        url=_clean_str(df["url"]), department=_clean_str(df["department"]),
    )


def load_minmaxxxer() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_JD / "minmaxxxer_2026_10/*.parquet"))) + \
            sorted(glob.glob(str(RAW_JD / "minmaxxxer_base/*.parquet")))
    cols = ["job_id", "title", "company", "city", "country_code", "workplace_type",
            "employment_type", "seniority", "salary_min_annual",
            "salary_max_annual", "salary_currency", "posted_at", "url",
            "description"]
    parts = [pd.read_parquet(f, columns=cols) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates(subset=["job_id"])  # 2026_10 与 base 有 ~1.5k 交集
    is_remote = df["workplace_type"].astype("string").str.strip().str.lower() \
        .map({"remote": True, "hybrid": False, "onsite": False}).astype("boolean")
    return _frame(
        job_key=df["job_id"], source="minmaxxxer",
        title=_clean_str(df["title"]), company=_clean_str(df["company"]),
        country=_clean_str(df["country_code"]), city=_clean_str(df["city"]),
        is_remote=is_remote,
        employment_type=_norm_employment(df["employment_type"]),
        seniority=_norm_seniority(df["seniority"]),
        salary_min_annual=pd.to_numeric(df["salary_min_annual"], errors="coerce"),
        salary_max_annual=pd.to_numeric(df["salary_max_annual"], errors="coerce"),
        salary_currency=_clean_str(df["salary_currency"]),
        skills=pd.Series([[]] * len(df), index=df.index, dtype="object"),
        description=_clean_str(df["description"]),
        posted_at=_to_utc(df["posted_at"]),
        url=_clean_str(df["url"]),
    )


def load_nextgig() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_JD / "nextgig_multi_ats/*.parquet")))
    cols = ["title", "company_name", "city", "country", "work_model",
            "employment_type", "experience_level", "skills_required",
            "salary_min", "salary_max", "salary_currency", "salary_rate_unit",
            "date_posted", "job_description"]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in files],
                   ignore_index=True)
    # 无 job_id / url 列：用 title+company+date 生成稳定 key
    key_src = (
        df["title"].astype("string").fillna("") + "|" +
        df["company_name"].astype("string").fillna("") + "|" +
        df["date_posted"].astype("string").fillna("")
    )
    job_key = "ng_" + key_src.map(_sha12)
    is_remote = df["work_model"].astype("string").str.strip().str.lower() \
        .map({"remote": True, "hybrid": False, "on-site": False, "onsite": False}) \
        .astype("boolean")
    return _frame(
        job_key=job_key, source="nextgig",
        title=_clean_str(df["title"]), company=_clean_str(df["company_name"]),
        country=_clean_str(df["country"]), city=_clean_str(df["city"]),
        is_remote=is_remote,
        employment_type=_norm_employment(df["employment_type"]),
        seniority=_norm_seniority(df["experience_level"]),
        salary_min_annual=_annualize(df["salary_min"], df["salary_rate_unit"]),
        salary_max_annual=_annualize(df["salary_max"], df["salary_rate_unit"]),
        salary_currency=_clean_str(df["salary_currency"]),
        skills=df["skills_required"].map(_parse_skills),
        description=_clean_str(df["job_description"]),
        posted_at=_to_utc(df["date_posted"]),
        url=pd.Series(pd.NA, index=df.index, dtype="string"),
        department=pd.Series(pd.NA, index=df.index, dtype="string"),
    )


def load_makenomistakes() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_JD / "makenomistakes_9ats/*.parquet")))
    cols = ["job_id", "title", "company", "city", "country", "is_remote",
            "employment_type", "salary_min", "salary_max", "salary_currency",
            "salary_period", "posted_at", "apply_url", "source_url",
            "description_text"]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in files],
                   ignore_index=True)
    url = _clean_str(df["apply_url"]).fillna(_clean_str(df["source_url"]))
    is_remote = df["is_remote"].map({"True": True, "False": False}).astype("boolean")
    return _frame(
        job_key=df["job_id"], source="makenomistakes",
        title=_clean_str(df["title"]), company=_clean_str(df["company"]),
        country=_clean_str(df["country"]), city=_clean_str(df["city"]),
        is_remote=is_remote,
        employment_type=_norm_employment(df["employment_type"]),
        seniority=pd.Series(pd.NA, index=df.index, dtype="string"),
        salary_min_annual=_annualize(df["salary_min"], df["salary_period"]),
        salary_max_annual=_annualize(df["salary_max"], df["salary_period"]),
        salary_currency=_clean_str(df["salary_currency"]),
        skills=pd.Series([[]] * len(df), index=df.index, dtype="object"),
        description=_clean_str(df["description_text"]),
        posted_at=_to_utc(df["posted_at"]),
        url=url,
    )


def load_jobicy() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_JD / "jobicy_remote/data/daily/*.jsonl")))
    recs = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
    df = pd.DataFrame(recs)
    if df.empty:
        return pd.DataFrame(columns=_frame([], "", [], [], [], [], [], [], [], [],
                                           [], [], [], [], [], [], []).columns)
    df = df.drop_duplicates(subset=["id"])
    job_key = "jobicy_" + df["id"].astype(str)
    return _frame(
        job_key=job_key, source="jobicy",
        title=_clean_str(df["jobTitle"]), company=_clean_str(df["companyName"]),
        country=pd.Series(pd.NA, index=df.index, dtype="string"),  # jobGeo 是区域不是国家
        city=pd.Series(pd.NA, index=df.index, dtype="string"),
        is_remote=pd.Series(True, index=df.index, dtype="boolean"),
        employment_type=_norm_employment(df["jobType"].map(
            lambda x: ", ".join(x) if isinstance(x, list) else x)),
        seniority=_norm_seniority(df["jobLevel"]),
        salary_min_annual=_annualize(df["salaryMin"], df["salaryPeriod"]),
        salary_max_annual=_annualize(df["salaryMax"], df["salaryPeriod"]),
        salary_currency=_clean_str(df["salaryCurrency"]),
        skills=df["jobIndustry"].map(_parse_skills),
        description=_clean_str(df["jobDescription"]),
        posted_at=_to_utc(df["pubDate"]),
        url=_clean_str(df["url"]),
    )


# ---------------------------------------------------------------------------
# live API 月度快照（remotive / jobicy，由 pipelines.monthly_update 拉取）
# ---------------------------------------------------------------------------

_REMOTIVE_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}


def _parse_remotive_salary(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """解析 remotive 的自由文本薪资，如 '$170k - $200k' / '60k-80k EUR'。

    返回 (min, max, currency)；无法解析时均为 NA。
    """
    lo = pd.Series(np.nan, index=s.index, dtype="float64")
    hi = pd.Series(np.nan, index=s.index, dtype="float64")
    cur = pd.Series(pd.NA, index=s.index, dtype="string")

    def _parse_one(text: object) -> tuple[float, float, str] | None:
        if text is None or (isinstance(text, float) and np.isnan(text)):
            return None
        t = str(text)
        m = re.findall(r"([$€£])?\s*(\d[\d,]*(?:\.\d+)?)\s*([kK])?", t)
        vals = []
        currency = None
        for sym, num, k in m:
            if sym:
                currency = currency or _REMOTIVE_CURRENCY[sym]
            v = float(num.replace(",", ""))
            if k:
                v *= 1000.0
            if v >= SALARY_ANNUAL_MIN:  # 明显是月薪/时薪的数值跳过
                vals.append(v)
        if not vals:
            return None
        return min(vals), max(vals), (currency or "USD")

    parsed = s.map(_parse_one)
    has = parsed.notna()
    lo.loc[has] = [p[0] for p in parsed.loc[has]]
    hi.loc[has] = [p[1] for p in parsed.loc[has]]
    cur.loc[has] = [p[2] for p in parsed.loc[has]]
    return lo, hi, cur


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_frame([], "", [], [], [], [], [], [], [], [],
                                       [], [], [], [], [], [], []).columns)


def _live_remotive_frame(df: pd.DataFrame) -> pd.DataFrame:
    salary_lo, salary_hi, currency = _parse_remotive_salary(df.get("salary"))
    return _frame(
        job_key="rem_" + df["id"].astype(str), source="live_remotive",
        title=_clean_str(df["title"]), company=_clean_str(df["company_name"]),
        country=pd.Series(pd.NA, index=df.index, dtype="string"),
        city=pd.Series(pd.NA, index=df.index, dtype="string"),
        is_remote=pd.Series(True, index=df.index, dtype="boolean"),
        employment_type=_norm_employment(df["job_type"]),
        seniority=pd.Series(pd.NA, index=df.index, dtype="string"),
        salary_min_annual=salary_lo, salary_max_annual=salary_hi,
        salary_currency=currency,
        skills=df["tags"].map(_parse_skills),
        description=_clean_str(df["description"]),
        posted_at=_to_utc(df["publication_date"]),
        url=_clean_str(df["url"]),
    )


def _live_jobicy_frame(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(
        job_key="jobicy_" + df["id"].astype(str), source="live_jobicy",
        title=_clean_str(df["jobTitle"]), company=_clean_str(df["companyName"]),
        country=pd.Series(pd.NA, index=df.index, dtype="string"),
        city=pd.Series(pd.NA, index=df.index, dtype="string"),
        is_remote=pd.Series(True, index=df.index, dtype="boolean"),
        employment_type=_norm_employment(df["jobType"].map(
            lambda x: ", ".join(x) if isinstance(x, list) else x)),
        seniority=_norm_seniority(df["jobLevel"]),
        salary_min_annual=_annualize(df["salaryMin"], df["salaryPeriod"]),
        salary_max_annual=_annualize(df["salaryMax"], df["salaryPeriod"]),
        salary_currency=_clean_str(df["salaryCurrency"]),
        skills=df["jobIndustry"].map(_parse_skills),
        description=_clean_str(df["jobDescription"]),
        posted_at=_to_utc(df["pubDate"]),
        url=_clean_str(df["url"]),
    )


def load_live_api() -> pd.DataFrame:
    """raw/jd/live_api/*.json：remotive / jobicy 实时 API 月度快照。

    支持两种文件形态：单个 API 的原始响应（顶层含 jobs），或
    monthly_update 写的合并文件（顶层含 remotive / jobicy 两个响应）。
    目录为空时返回空表，对原 5 源无影响。
    """
    remotive_recs, jobicy_recs = [], []
    for f in sorted(glob.glob(str(RAW_JD / "live_api" / "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        remotive = payload.get("remotive", payload)
        jobicy = payload.get("jobicy")
        for response in (remotive, jobicy):
            if not isinstance(response, dict):
                continue
            jobs = response.get("jobs")
            if not jobs:
                continue
            first = jobs[0] if isinstance(jobs[0], dict) else {}
            if "company_name" in first:      # remotive 结构
                remotive_recs.extend(jobs)
            elif "jobTitle" in first:        # jobicy 结构
                jobicy_recs.extend(jobs)
    frames = []
    if remotive_recs:
        frames.append(_live_remotive_frame(pd.DataFrame(remotive_recs)))
    if jobicy_recs:
        frames.append(_live_jobicy_frame(pd.DataFrame(jobicy_recs)))
    if not frames:
        return _empty_frame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _process(df: pd.DataFrame, source: str) -> tuple[pd.DataFrame, dict]:
    """统一清洗一个源：日期过滤、IT 过滤、薪资清洗，返回 (df, drop_counts)。"""
    n_in = len(df)
    drops = {"invalid_date": 0, "before_2020": 0, "future_date": 0,
             "empty_title": 0, "it_filtered": 0}

    if len(df) == 0:  # 空源（如 live_api 无快照）：补好派生列直接返回
        df = df.copy()
        df["posted_month"] = pd.Series(dtype="string")
        df["job_id"] = pd.Series(dtype="string")
        df["has_description"] = pd.Series(dtype="boolean")
        return df, drops

    df = df[df["posted_at"].notna()].copy()
    drops["invalid_date"] = n_in - len(df)

    n0 = len(df)
    df = df[df["posted_at"] >= MIN_POSTED_AT].copy()
    drops["before_2020"] = n0 - len(df)

    n0 = len(df)
    df = df[df["posted_at"] < MAX_POSTED_AT].copy()
    drops["future_date"] = n0 - len(df)

    n0 = len(df)
    df = df[df["title"].notna() & (df["title"].str.len() > 0)].copy()
    drops["empty_title"] = n0 - len(df)

    n0 = len(df)
    dept = df["department"] if "department" in df.columns else None
    keep = pd.Series(
        [_is_it_title(t, d) for t, d in zip(df["title"], dept if dept is not None else [None] * len(df))],
        index=df.index, dtype=bool)
    df = df[keep].copy()
    drops["it_filtered"] = n0 - len(df)

    df["salary_min_annual"], df["salary_max_annual"] = _clean_salary(
        df["salary_min_annual"], df["salary_max_annual"])
    df["posted_month"] = df["posted_at"].dt.strftime("%Y-%m")
    df["job_id"] = df["source"] + ":" + df["job_key"].map(_sha12)
    df["has_description"] = df["description"].notna() & (df["description"].str.len() > 0)
    return df, drops


def _dedup(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """跨源去重: (title, company, posted_month) 相同保留优先级更高的源."""
    before = len(df)
    df = df.assign(
        _pri=df["source"].map(SOURCE_PRIORITY),
        _dk=df["title"].map(_norm_key) + "|" + df["company"].map(_norm_key)
            + "|" + df["posted_month"],
    )
    df = df.sort_values(["_dk", "_pri"], kind="mergesort")
    df = df.drop_duplicates(subset=["_dk"], keep="first")
    removed = before - len(df)
    df = df.drop(columns=["_pri", "_dk"])
    return df, {"dedup_removed": removed}


def _month_dist(s: pd.Series) -> dict:
    vc = s.value_counts().sort_index()
    return {
        "min_month": str(vc.index.min()) if len(vc) else None,
        "max_month": str(vc.index.max()) if len(vc) else None,
        "n_months": int(len(vc)),
        "first_5_months": {str(k): int(v) for k, v in vc.head(5).items()},
        "last_5_months": {str(k): int(v) for k, v in vc.tail(5).items()},
    }


def main() -> None:
    loaders = {
        "zalizedata": load_zalizedata,
        "minmaxxxer": load_minmaxxxer,
        "nextgig": load_nextgig,
        "makenomistakes": load_makenomistakes,
        "jobicy": load_jobicy,
        "live_api": load_live_api,
    }

    qc: dict = {"sources": {}, "notes": []}
    frames = []
    for source, loader in loaders.items():
        print(f"[ingest_jd] loading {source} ...", flush=True)
        df = loader()
        n_in = len(df)
        df, drops = _process(df, source)
        # 源内 job_id 去重（防御）
        dup_ids = int(df["job_id"].duplicated().sum())
        df = df.drop_duplicates(subset=["job_id"], keep="first")
        frames.append(df)
        kept = df
        qc["sources"][source] = {
            "input_rows": int(n_in),
            "kept_rows": int(len(kept)),
            "drops": drops,
            "duplicate_job_id_removed": dup_ids,
            "posted_month_distribution": _month_dist(kept["posted_month"]),
            "skills_nonnull_rate": float((kept["skills"].map(len) > 0).mean()) if len(kept) else 0.0,
            "salary_nonnull_rate": float(kept["salary_min_annual"].notna().mean()) if len(kept) else 0.0,
            "description_coverage": float(kept["has_description"].mean()) if len(kept) else 0.0,
        }
        print(f"[ingest_jd] {source}: in={n_in} kept={len(kept)} drops={drops}",
              flush=True)

    all_df = pd.concat(frames, ignore_index=True)
    all_df, dedup_stats = _dedup(all_df)
    print(f"[ingest_jd] cross-source dedup removed {dedup_stats['dedup_removed']}",
          flush=True)

    # 去重后按源统计最终贡献
    final_counts = all_df["source"].value_counts().to_dict()
    for source, stats in qc["sources"].items():
        stats["final_rows_after_cross_source_dedup"] = int(final_counts.get(source, 0))

    qc["total_rows"] = int(len(all_df))
    qc["dedup_removed"] = dedup_stats["dedup_removed"]
    qc["it_filtered_total"] = int(sum(s["drops"]["it_filtered"] for s in qc["sources"].values()))
    qc["posted_month_distribution"] = _month_dist(all_df["posted_month"])
    qc["overall"] = {
        "skills_nonnull_rate": float((all_df["skills"].map(len) > 0).mean()),
        "salary_nonnull_rate": float(all_df["salary_min_annual"].notna().mean()),
        "description_coverage": float(all_df["has_description"].mean()),
    }
    qc["notes"] = [
        "nextgig_multi_ats 无 job_id/url 列：job_id 由 sha1(title|company|date_posted)[:12] 生成；"
        "skills_required 为 stringified list 或 'nan' 字符串，已健壮解析。",
        "nextgig date_posted 为 MM/DD/YYYY，存在 '00/00/2'、'Posted Yesterday' 等脏值；"
        "且 80.7% 的行 date_posted 为字面 NaN，按缺失丢弃（invalid_date=91813）。",
        "jobicy_remote 为 daily jsonl（全远程岗），无国家/城市字段（jobGeo 是区域标签），"
        "skills 取自 jobIndustry 标签列表，seniority 取自 jobLevel。",
        "makenomistakes 无 url 列：url 用 apply_url，缺失时回填 source_url；salary_min/max 为字符串。"
        "无 seniority 字段。",
        "minmaxxxer 2026_10 与 base 文件 job_id 有 ~1.5k 交集，源内已按 job_id 去重；"
        "salary_min/max_annual 为源站已年化值。",
        "zalizedata M/S 分片存在少量重复 job_id，源内已去重；skills 列为 numpy array 或空数组。",
        "去重优先级: minmaxxxer > zalizedata > makenomistakes > nextgig > jobicy "
        "> live_remotive > live_jobicy。",
        "live_api 为 remotive / jobicy 实时 API 月度快照（raw/jd/live_api/*.json，"
        "由 pipelines.monthly_update 拉取），无国家/城市字段，salary 为自由文本已解析；"
        "目录为空时该源贡献 0 行，不影响原 5 源。",
    ]

    # ---- 写主表（按 posted_month 分区，覆盖输出保证幂等）----
    if OUT_UNIFIED.exists():
        shutil.rmtree(OUT_UNIFIED)
    OUT_UNIFIED.mkdir(parents=True, exist_ok=True)
    out = all_df[UNIFIED_COLUMNS].copy()
    for month, part in out.groupby("posted_month", sort=True):
        pdir = OUT_UNIFIED / f"posted_month={month}"
        pdir.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(part, preserve_index=False)
        idx = table.column_names.index("posted_month")
        table = table.set_column(idx, "posted_month",
                                 table.column("posted_month").cast(pa.string()))
        pq.write_table(table, pdir / "part-0.parquet")

    # ---- 写 description 侧表 ----
    if OUT_DESCRIPTIONS.exists():
        shutil.rmtree(OUT_DESCRIPTIONS)
    OUT_DESCRIPTIONS.mkdir(parents=True, exist_ok=True)
    desc = all_df.loc[all_df["has_description"], ["job_id", "source", "description"]]
    for source, part in desc.groupby("source"):
        part[["job_id", "description"]].to_parquet(
            OUT_DESCRIPTIONS / f"{source}.parquet", engine="pyarrow", index=False)

    with open(OUT_UNIFIED / "_qc_report.json", "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=2)
    print(f"[ingest_jd] done. total_rows={len(all_df)} "
          f"months={qc['posted_month_distribution']['min_month']}.."
          f"{qc['posted_month_distribution']['max_month']}", flush=True)


if __name__ == "__main__":
    main()
