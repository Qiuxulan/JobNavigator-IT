"""岗位级月度证据采集（Google News RSS + layoffs.fyi + SEC EDGAR）。

用法：
    python -m pipelines.evidence_v2.collect [--months 6] [--roles all]

输出：
- /data/shichaojian/JNIT/processed/evidence_v2/{role_id}/{YYYY-MM}.jsonl（按月分片，幂等合并）
- /data/shichaojian/JNIT/processed/evidence_v2/_market/（layoffs.fyi 明细、SEC EDGAR 8-K 月度）
- data/gold/evidence_v2_summary.json（API 层直接读）
- data/gold/evidence_v2_qc.json（质量报告）

设计要点：
- 幂等：按月分片、按 evidence_id(google news url sha1[:12]) 去重合并，可重复跑。
- 相关性过滤：岗位锚词（canonical/alias 词边界命中）或（IT 上下文词 + 岗位技能词）共现；
  再剔除体育/娱乐/政治噪声域名与标题。过滤在解码前做，控制解码请求量。
- 诚实降级：URL 解码失败保留原始跳转链接并标 url_resolved=False，不编造。
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

from pipelines.evidence_v2._gnews_decode import GoogleNewsDecoder

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
# v2 岗位库优先（含 expand_roles 新岗）；缺文件回退 v1。
_TAXONOMY_V2 = REPO_ROOT / "data" / "gold" / "role_taxonomy_v2.json"
ROLE_TAXONOMY_PATH = _TAXONOMY_V2 if _TAXONOMY_V2.exists() else REPO_ROOT / "data" / "gold" / "role_taxonomy.json"
EVIDENCE_ROOT = Path("/data/shichaojian/JNIT/processed/evidence_v2")
MARKET_DIR = EVIDENCE_ROOT / "_market"
SUMMARY_PATH = REPO_ROOT / "data" / "gold" / "evidence_v2_summary.json"
QC_PATH = REPO_ROOT / "data" / "gold" / "evidence_v2_qc.json"
LAYOFFS_ANNUAL_LOCAL = Path(
    "/data/shichaojian/JNIT/raw/events/layoffs_fyi_annual_stats.json"
)

# ---------------------------------------------------------------------------
# 采集参数
# ---------------------------------------------------------------------------
RSS_BASE = "https://news.google.com/rss/search"
RSS_HL = "en-US"
RSS_DELAY_SEC = 1.0          # 限速：请求间隔
RSS_RETRY = 2                # 失败重试次数
RSS_TIMEOUT = 30

DECODE_TOP_N = 12            # 每个 (role, month) 最多解码条数（按初筛 relevance 排序）
DECODE_PAGE_DELAY = 0.15     # 解码取参请求间隔
DECODE_WORKERS = 3
DECODE_BATCH = 50            # 单次 batchexecute 最多信封数

EDGAR_EMAIL_UA = "JobNavigator-IT research contact@example.com"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_QUERY = '"workforce reduction"'
EDGAR_DELAY_SEC = 0.5

LAYOFFS_MIRROR_ZIP = (
    "https://codeload.github.com/frankwang0909/tech-layoff-tracker/zip/refs/heads/main"
)
LAYOFFS_MIRROR_MAX_AGE_H = 24

# ---------------------------------------------------------------------------
# 相关性过滤词表
# ---------------------------------------------------------------------------
IT_CONTEXT_WORDS = {
    "software", "tech", "technology", "technologies", "engineering", "engineer",
    "engineers", "developer", "developers", "cloud", "data", "startup", "startups",
    "digital", "platform", "saas", "enterprise", "app", "apps", "application",
    "applications", "internet", "web", "silicon valley", "semiconductor", "chip",
    "coding", "programming", "devops", "api", "cybersecurity", "database",
    "machine learning", "artificial intelligence", "automation", "open source",
    "h-1b", "gpu", "gaming", "gamedev", "video game", "blockchain", "crypto",
    "ai", "ml",
}

# 科技媒体 source 名（RSS <source> 文本，小写子串匹配）：锚词命中 + 科技媒体
# 即可通过，用于无显式上下文词的技术报道（薪资报告、工具评测、播客等）。
TECH_SOURCE_NAMES = {
    "techcrunch", "venturebeat", "zdnet", "arstechnica", "ars technica",
    "the verge", "wired", "cnet", "infoworld", "cio", "csoonline",
    "techtarget", "thenextweb", "siliconangle", "dzone", "infoq",
    "dev.to", "medium", "towards data science", "kdnuggets", "thenewstack",
    "the new stack", "darkreading", "dark reading", "securityweek",
    "bleepingcomputer", "bleeping computer", "thehackernews", "hacker news",
    "securityaffairs", "security affairs", "hackread", "gbhackers",
    "devops.com", "containerjournal", "cloud native", "github",
    "androidauthority", "9to5google", "9to5mac", "xda", "android central",
    "androidcentral", "iphonehacks", "macrumors", "appleinsider",
    "windows central", "windowscentral", "how-to geek", "howtogeek",
    "makeuseof", "make tech easier", "muo", "tom's hardware", "tomshardware",
    "anandtech", "pcworld", "pc mag", "pcmag", "gizmodo", "engadget",
    "mashable", "the register", "theregister", "el reg", "datacenter",
    "data center", "servicenow", "aws", "azure", "techradar", "extremetech",
    "neowin", "slashdot", "osnews", "lobste.rs", "stack overflow",
    "stackoverflow", "freecodecamp", "free code camp", "hackernoon",
    "hackernoon", "dzone", "jetbrains", "visual studio", "info world",
}

NOISE_DOMAINS = {
    "espn.com", "nfl.com", "nba.com", "mlb.com", "nhl.com", "fifa.com",
    "uefa.com", "tmz.com", "people.com", "usmagazine.com", "eonline.com",
    "variety.com", "hollywoodreporter.com", "billboard.com", "rollingstone.com",
    "pitchfork.com", "thesun.co.uk", "mirror.co.uk", "dailystar.co.uk",
    "okmagazine.com", "inquisitr.com", "buzzfeed.com", "theblast.com",
    "pagesix.com", "justjared.com", "etonline.com",
}

NOISE_TITLE_PATTERNS = [
    r"\bnfl\b", r"\bnba\b", r"\bmlb\b", r"\bnhl\b", r"\bsoccer\b", r"\bfootball\b",
    r"\bbasketball\b", r"\bbaseball\b", r"\btennis\b", r"\bgolf\b", r"\bcricket\b",
    r"\bolympics?\b", r"super bowl", r"world cup", r"premier league",
    r"formula 1|\bf1\b", r"\bboxing\b", r"\b UFC \b", r"\bwwe\b", r"\bpoker\b",
    r"\bcasino\b", r"\blottery\b", r"\btransfer\b.{0,20}\b(club|player)\b",
    r"\boscars?\b", r"\bgrammy\b", r"\bemmy\b", r"golden globe", r"\bcannes\b",
    r"\bcelebrity\b", r"kardashian", r"\bbachelor\b", r"\bbachelorette\b",
    r"\bsitcom\b", r"\bsoundtrack\b", r"\bhoroscope\b",
    r"\belection\b", r"\bsenate\b", r"\bgop\b", r"\bdemocrat\b", r"\brepublican\b",
    r"\bpresident\b", r"white house", r"\bgovernor\b", r"\bcongress\b",
    r"\bparliament\b", r"\bminister\b", r"\bpoll(s|ing)?\b", r"\bvoting\b",
    r"\btrump\b", r"\bbiden\b", r"\bkamala\b", r"\bputin\b", r"\bzelensky\b",
    r"\bgaza\b", r"\bukraine\b", r"\btroops\b", r"\bmilitary\b", r"\bmissile\b",
    r"\bshooting\b", r"\bmurder\b", r"\barrest(ed)?\b", r"\bverdict\b",
    r"\bsentenced\b", r"\bprison\b", r"\bearthquake\b", r"\bhurricane\b",
]
_NOISE_TITLE_RE = re.compile("|".join(NOISE_TITLE_PATTERNS), re.IGNORECASE)

# 事件分类（按优先级命中即停）
_EVENT_RULES = [
    ("layoff", [
        r"\blayoffs?\b", r"\blay off\b", r"\blaid off\b", r"job cuts?",
        r"workforce reduction", r"downsiz", r"restructur", r"staff cuts?",
        r"job losses", r"redundanc", r"eliminating\s+\d+", r"eliminate\s+\d+.*(jobs|positions|roles)",
        r"\bfire[sd]?\b.{0,30}\b(employees?|staff|workers?)\b",
    ]),
    ("security_incident", [
        r"\bbreach\b", r"\bhack(ed|ing|s)?\b", r"\bransomware\b",
        r"vulnerabilit", r"\bcve-\d", r"data leak", r"\bcyberattack\b",
        r"\bphishing\b", r"zero[- ]day", r"malware",
    ]),
    ("policy", [
        r"\bregulation\b", r"\bregulator(s|y)?\b", r"\bantitrust\b",
        r"executive order", r"\bai act\b", r"\bgdpr\b", r"\bcfpb\b", r"\bftc\b",
        r"\bdoj\b", r"\bbill\b.{0,30}\b(ai|tech|data)\b", r"bipartisan",
        r"\btariff(s)?\b",
    ]),
    ("funding", [
        r"\bfunding\b", r"\braises?\b", r"\braised\b", r"series [a-e]\b",
        r"\bvaluation\b", r"\bipo\b", r"\bacqui(re|sition|red)\b", r"\bmerger\b",
        r"\binvest(s|ed|ment|or)?\b", r"\bunicorn\b", r"venture capital",
        r"\bbootstrap",
    ]),
    ("hiring", [
        r"\bhiring\b", r"\bhires?\b", r"\bhired\b", r"job opening", r"open roles?",
        r"talent acquisition", r"expand(s|ing)? (its |the )?(team|workforce)",
        r"\brecruit(s|ing|ment)?\b", r"is hiring", r"\bcareers?\b", r"new grad",
        r"\bheadcount\b.{0,20}(grow|expan|add)",
    ]),
    ("ai_adoption", [
        r"\bai adoption\b", r"adopts? (generative )?ai\b", r"deploy(s|ing)? (generative )?ai\b",
        r"ai agents?\b", r"\bgenai\b", r"generative ai", r"\bllm(s)?\b",
        r"\bcopilot\b", r"ai-powered", r"integrates? (generative )?ai\b",
        r"agentic", r"\bai strategy\b", r"\bai transformation\b", r"\bchatgpt\b",
        r"\bclaude\b", r"\bgemini\b",
    ]),
    ("product_release", [
        r"\blaunch", r"\breleas", r"\bunveil", r"\bdebut", r"now available",
        r"generally available", r"\bbeta\b", r"\bversion \d", r"\bships?\b",
        r"\brolls? out\b",
    ]),
]
_EVENT_RES = [
    (name, re.compile("|".join(patterns), re.IGNORECASE))
    for name, patterns in _EVENT_RULES
]

GENERIC_SKILLS = {
    "agile", "git", "jira", "confluence", "scrum", "excel", "kanban",
    "rest api", "oop", "html", "css", "sql", "linux", "aws", "azure",
    "google cloud", "docker", "kubernetes",
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", flush=True)


def month_add(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def recent_months(n: int, today: datetime | None = None) -> list[str]:
    today = today or datetime.now(UTC)
    cur = f"{today.year:04d}-{today.month:02d}"
    return [month_add(cur, -i) for i in reversed(range(n))]


def build_anchor_re(role: dict) -> list[tuple[str, "re.Pattern[str]"]]:
    """岗位锚词正则：canonical + aliases 前 2 个，整短语词边界命中。

    短语首/尾为非单词字符（.NET、C++、C#）时该侧的 \\b 永不成立，需省略；
    末词兼容复数（Engineer/Engineers）。
    """
    phrases = [role["canonical_role"]] + list(role.get("aliases") or [])[:2]
    out = []
    for p in phrases:
        words = p.split()
        escaped = [re.escape(w) for w in words]
        escaped[-1] += r"s?"
        body = r"[\s\-]+".join(escaped)
        head = r"\b" if words and (words[0][0].isalnum() or words[0][0] == "_") else ""
        tail = r"\b" if words and (words[-1][-1].isalnum() or words[-1][-1] == "_") else ""
        out.append((p, re.compile(head + body + tail, re.IGNORECASE)))
    return out


def build_skill_res(role: dict) -> list[tuple[str, "re.Pattern[str]"]]:
    out = []
    for s in role.get("top_skills") or []:
        words = s.split()
        body = r"[\s/\-]*".join(re.escape(w) for w in words)
        head = r"\b" if words and (words[0][0].isalnum() or words[0][0] == "_") else ""
        tail = r"\b" if words and (words[-1][-1].isalnum() or words[-1][-1] == "_") else ""
        out.append((s, re.compile(head + body + tail, re.IGNORECASE)))
    return out


def classify_event(title: str) -> str:
    for name, rx in _EVENT_RES:
        if rx.search(title):
            return name
    return "general"


def is_noise(title: str, link: str) -> bool:
    if _NOISE_TITLE_RE.search(title):
        return True
    host = (urlparse(link).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith("." + d) for d in NOISE_DOMAINS)


def relevance_score(
    title: str,
    anchor_hits: list[str],
    skill_hits: list[str],
) -> float:
    if anchor_hits:
        score = 0.7 + 0.1 * min(len(anchor_hits) - 1, 1)
    else:
        score = 0.5
    score += min(0.2, 0.05 * len(skill_hits))
    # 技能过于泛化（agile/git/excel...）不给加成上限外的好处已由 skill_hits 数量控制
    return round(min(1.0, score), 2)


def _context_hit(title: str) -> bool:
    return (
        any(re.search(r"\b" + re.escape(w) + r"\b", title, re.IGNORECASE)
            for w in IT_CONTEXT_WORDS if " " not in w)
        or any(w in title.lower() for w in IT_CONTEXT_WORDS if " " in w)
    )


def _tech_source_hit(source_name: str) -> bool:
    s = (source_name or "").lower()
    return any(name in s for name in TECH_SOURCE_NAMES)


def assess_relevance(
    title: str, role: dict, anchors, skill_res, source_name: str = "",
) -> tuple[float, list[str], list[str]] | None:
    """返回 (score, anchor_hits, skill_hits)；不相关返回 None。

    两道闸门：
    1. 锚词命中 且 (IT 上下文词 或 技能词 或 科技媒体来源)；
    2. (IT 上下文词 且 技能词) 共现。
    单有锚词不够——"food & drink product manager" 这类非 IT 岗位提及要剔除。
    """
    anchor_hits = [name for name, rx in anchors if rx.search(title)]
    skill_hits = [name for name, rx in skill_res if rx.search(title)]
    context = _context_hit(title)
    relevant = (
        bool(anchor_hits) and (context or bool(skill_hits) or _tech_source_hit(source_name))
    ) or (context and bool(skill_hits))
    if not relevant:
        return None
    return relevance_score(title, anchor_hits, skill_hits), anchor_hits, skill_hits


# ---------------------------------------------------------------------------
# Google News RSS
# ---------------------------------------------------------------------------
def rss_search_url(query: str, month: str, is_current: bool, quoted: bool = True) -> str:
    q = f'"{query}"' if quoted else query
    if is_current:
        q += " when:30d"
    else:
        start = f"{month}-01"
        end = f"{month_add(month, 1)}-01"
        q += f" after:{start} before:{end}"
    return (
        f"{RSS_BASE}?q={quote_plus(q)}&hl={RSS_HL}&gl=US&ceid=US:en"
    )


# 岗位名中的方向/平台修饰词：无引号 AND 查询全词命中过严，降级查询时去掉。
_CORE_DROP_WORDS = {
    "frontend", "front-end", "backend", "back-end", "mobile", "full-stack",
    "fullstack", "full stack", "cloud", "linux", "azure", "web",
}


def core_query(query: str) -> str:
    """去掉方向修饰词后的核心查询词（Frontend Vue Engineer -> Vue Engineer）。"""
    words = query.split()
    kept = [w for w in words if w.lower().strip("/") not in _CORE_DROP_WORDS]
    return " ".join(kept) if kept else query


def fetch_rss(url: str, session: requests.Session) -> tuple[list[dict], bool]:
    """解析 RSS -> ([{title, link, source, pub_date_str}], 是否请求失败)。

    失败重试后返回 ([], True)；当月本来无结果返回 ([], False)。
    """
    last_err: Exception | None = None
    for attempt in range(RSS_RETRY + 1):
        try:
            resp = session.get(url, timeout=RSS_TIMEOUT)
            if resp.status_code != 200:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                time.sleep(2 * (attempt + 1))
                continue
            root = ET.fromstring(resp.text)
            items = []
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                src_el = it.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if title and link:
                    items.append({
                        "title": title, "link": link,
                        "source": source, "pub_date_str": pub,
                    })
            return items, False
        except (requests.RequestException, ET.ParseError) as exc:
            last_err = exc
            time.sleep(2 * (attempt + 1))
    log(f"  ! RSS 失败(重试{RSS_RETRY}次): {url[:110]} err={last_err}")
    return [], True


def parse_pub_month(pub_date_str: str) -> tuple[str, str] | None:
    """pubDate -> (YYYY-MM, iso)；解析失败返回 None。"""
    try:
        dt = parsedate_to_datetime(pub_date_str)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return f"{dt.year:04d}-{dt.month:02d}", dt.astimezone(UTC).isoformat()


# ---------------------------------------------------------------------------
# 分片读写（幂等）
# ---------------------------------------------------------------------------
def shard_path(role_id: str, month: str) -> Path:
    return EVIDENCE_ROOT / role_id / f"{month}.jsonl"


def read_shard(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[item["evidence_id"]] = item
    return out


def write_shard(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=lambda x: (x.get("published_at") or "",), reverse=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------
def collect_edgar_month(session: requests.Session, month: str) -> dict:
    start = f"{month}-01"
    last_day = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
    end = f"{month}-{last_day:02d}"
    headers = {
        "User-Agent": EDGAR_EMAIL_UA,
        "Accept-Encoding": "gzip, deflate",
    }
    params = {
        "q": EDGAR_QUERY,
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
    }
    out = {
        "month": month,
        "query": EDGAR_QUERY,
        "total_hits": None,
        "filings_8k": [],
        "error": None,
    }
    try:
        resp = session.get(EDGAR_SEARCH, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}"
            return out
        data = resp.json()
        hits = data.get("hits") or {}
        total = hits.get("total") or {}
        out["total_hits"] = total.get("value")
        seen_adsh: set[str] = set()
        filings = []
        for h in hits.get("hits") or []:
            src = h.get("_source") or {}
            root_forms = src.get("root_forms") or []
            if not any(str(f).startswith("8-K") for f in root_forms):
                continue
            adsh = src.get("adsh") or ""
            if not adsh or adsh in seen_adsh:
                continue
            file_id = h.get("_id") or ""
            filename = file_id.split(":", 1)[1] if ":" in file_id else ""
            if src.get("file_type") != "8-K" and filename:
                # 同一 filing 有多份文件命中时优先主文档
                continue
            seen_adsh.add(adsh)
            ciks = src.get("ciks") or []
            cik = str(int(ciks[0])) if ciks else ""
            names = src.get("display_names") or []
            company = re.sub(r"\s*\(CIK[^)]*\)\s*", "", names[0]).strip() if names else ""
            url = ""
            if cik and filename:
                url = (
                    "https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{adsh.replace('-', '')}/{filename}"
                )
            filings.append({
                "company": company,
                "file_date": src.get("file_date"),
                "form": src.get("form"),
                "url": url,
            })
        out["filings_8k"] = filings
    except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
        out["error"] = str(exc)
    return out


# ---------------------------------------------------------------------------
# layoffs.fyi 明细（GitHub 镜像）
# ---------------------------------------------------------------------------
def collect_layoffs_detail(session: requests.Session) -> dict:
    """从 GitHub 镜像(codeload zip)拉裁员明细，按月聚合。失败诚实标注。"""
    out = {
        "source": LAYOFFS_MIRROR_ZIP,
        "annual_stats_local": str(LAYOFFS_ANNUAL_LOCAL),
        "fetched_at": datetime.now(UTC).isoformat(),
        "monthly": {},
        "ai_related_companies": [],
        "error": None,
    }
    cache = MARKET_DIR / "layoffs_tracker_cache.zip"
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    use_cache = (
        cache.exists()
        and (time.time() - cache.stat().st_mtime) < LAYOFFS_MIRROR_MAX_AGE_H * 3600
    )
    try:
        if use_cache:
            blob = cache.read_bytes()
        else:
            resp = session.get(LAYOFFS_MIRROR_ZIP, timeout=120)
            if resp.status_code != 200:
                out["error"] = f"mirror HTTP {resp.status_code}"
                return out
            blob = resp.content
            cache.write_bytes(blob)
        zf = zipfile.ZipFile(io.BytesIO(blob))
        csv_name = next(
            (n for n in zf.namelist() if n.endswith("data/raw/layoffs_raw.csv")),
            None,
        )
        if not csv_name:
            out["error"] = "layoffs_raw.csv not found in mirror zip"
            return out
        text = zf.read(csv_name).decode("utf-8-sig", "replace")
        monthly: dict[str, dict] = {}
        ai_companies: set[str] = set()
        for row in csv.DictReader(io.StringIO(text)):
            date_str = (row.get("date") or "").strip()
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                continue
            month = date_str[:7]
            company = (row.get("company") or "").strip()
            industry = (row.get("industry") or "").strip()
            try:
                num = int(float(row.get("num_laid_off") or 0))
            except ValueError:
                num = 0
            bucket = monthly.setdefault(month, {
                "events": 0, "total_laid_off": 0,
                "companies": [], "ai_related_events": 0,
            })
            bucket["events"] += 1
            bucket["total_laid_off"] += num
            if company and company not in bucket["companies"]:
                bucket["companies"].append(company)
            if re.search(r"\bai\b|artificial intelligence", industry, re.IGNORECASE):
                bucket["ai_related_events"] += 1
                if company:
                    ai_companies.add(company)
        out["monthly"] = dict(sorted(monthly.items()))
        out["ai_related_companies"] = sorted(ai_companies)
    except (requests.RequestException, zipfile.BadZipFile, OSError) as exc:
        out["error"] = str(exc)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def decode_candidates(
    decoder: GoogleNewsDecoder, candidates: list[dict]
) -> dict[str, str]:
    """对候选条目批量解码：先并发取 (sig, ts)，再一次/多次 batchexecute。

    返回 {evidence_id: decoded_url}。
    """
    if not candidates:
        return {}

    def fetch_params(item: dict):
        eid = item["evidence_id"]
        art_id = item["google_news_url"].rsplit("/articles/", 1)[-1].split("?")[0]
        params = decoder.fetch_params(art_id)
        time.sleep(DECODE_PAGE_DELAY)
        return eid, art_id, params

    resolved: dict[str, str] = {}
    pending: list[tuple[str, str, str, int]] = []
    with ThreadPoolExecutor(max_workers=DECODE_WORKERS) as pool:
        for eid, art_id, params in pool.map(fetch_params, candidates):
            if params is None:
                continue
            sig, ts = params
            pending.append((eid, art_id, sig, ts))
    for i in range(0, len(pending), DECODE_BATCH):
        chunk = pending[i:i + DECODE_BATCH]
        art_id_map = decoder.decode_batch([(a, s, t) for _, a, s, t in chunk])
        for eid, art_id, _, _ in chunk:
            if art_id in art_id_map:
                resolved[eid] = art_id_map[art_id]
        if i + DECODE_BATCH < len(pending):
            time.sleep(DECODE_PAGE_DELAY)
    return resolved


def run(months: int, roles_arg: str) -> dict:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    MARKET_DIR.mkdir(parents=True, exist_ok=True)

    taxonomy_all = json.loads(ROLE_TAXONOMY_PATH.read_text(encoding="utf-8"))
    taxonomy = taxonomy_all
    if roles_arg != "all":
        wanted = {r.strip() for r in roles_arg.split(",") if r.strip()}
        taxonomy = [r for r in taxonomy_all if r["role_id"] in wanted]
    if not taxonomy:
        raise SystemExit(f"没有匹配岗位: {roles_arg}")

    month_list = recent_months(months)
    current_month = month_list[-1]
    log(f"岗位 {len(taxonomy)} 个，月份 {month_list[0]}..{month_list[-1]}")

    stats = {
        "rss_requests": 0,
        "rss_failures": 0,
        "raw_items": 0,
        "after_filter": 0,
        "noise_dropped": 0,
        "decode_attempted": 0,
        "decode_succeeded": 0,
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "JobNavigator-IT/2.0 (evidence collector; research)"
    })

    decode_available = True
    try:
        import h2  # noqa: F401
    except ImportError:
        decode_available = False
        log("! 未安装 h2，batchexecute 解码不可用（pip install h2）；全部保留跳转链接")

    with GoogleNewsDecoder() as decoder:
        for role in taxonomy:
            role_id = role["role_id"]
            canonical = role["canonical_role"]
            queries = [canonical] + list(role.get("aliases") or [])[:2]
            anchors = build_anchor_re(role)
            skill_res = build_skill_res(role)

            # role_id -> month -> {evidence_id: item}
            new_by_month: dict[str, dict[str, dict]] = {}
            for month in month_list:
                is_current = month == current_month
                for query in queries:
                    # 整短语引号过严（长岗位名常 0 结果）→ 无引号 AND；
                    # 方向修饰词(Frontend/Backend/Cloud...)AND 过严 → 无引号核心词。
                    # 三级查询共用同一相关性过滤，精度不受影响。
                    core = core_query(query)
                    variants: list[tuple[str, bool]] = [
                        (query, True),
                        (query, False),
                    ]
                    if core != query:
                        variants.append((core, False))
                    for q, quoted in variants:
                        url = rss_search_url(q, month, is_current, quoted=quoted)
                        stats["rss_requests"] += 1
                        time.sleep(RSS_DELAY_SEC)
                        items, failed = fetch_rss(url, session)
                        if items or failed:
                            break  # 命中或真失败即停（failed 时也停止降级）
                    if failed:
                        stats["rss_failures"] += 1
                    stats["raw_items"] += len(items)
                    for it in items:
                        title = it["title"]
                        if is_noise(title, it["link"]):
                            stats["noise_dropped"] += 1
                            continue
                        assessed = assess_relevance(
                            title, role, anchors, skill_res,
                            source_name=it["source"],
                        )
                        if assessed is None:
                            continue
                        score, anchor_hits, skill_hits = assessed
                        parsed = parse_pub_month(it["pub_date_str"])
                        if parsed is None:
                            continue
                        pub_month, pub_iso = parsed
                        gn_url = it["link"].split("?")[0]
                        eid = hashlib.sha1(gn_url.encode("utf-8")).hexdigest()[:12]
                        bucket = new_by_month.setdefault(pub_month, {})
                        if eid in bucket:
                            continue  # 同月内多 query 命中去重
                        stats["after_filter"] += 1
                        bucket[eid] = {
                            "evidence_id": eid,
                            "role_id": role_id,
                            "title": title,
                            "url": gn_url,
                            "url_resolved": False,
                            "google_news_url": gn_url,
                            "source_name": it["source"],
                            "published_at": pub_iso,
                            "month": pub_month,
                            "event_type": classify_event(title),
                            "relevance_score": score,
                            "query_used": query,
                            "anchor_hits": anchor_hits,
                            "skill_hits": [
                                s for s in skill_hits if s.lower() not in GENERIC_SKILLS
                            ] or skill_hits[:3],
                        }

            # 合并写分片 + 解码未解析的
            for month, bucket in sorted(new_by_month.items()):
                path = shard_path(role_id, month)
                existing = read_shard(path)
                merged = {**existing, **bucket}
                unresolved = [
                    it for it in merged.values() if not it.get("url_resolved")
                ]
                unresolved.sort(key=lambda x: -x["relevance_score"])
                to_try = unresolved[:DECODE_TOP_N]
                if decode_available and to_try:
                    stats["decode_attempted"] += len(to_try)
                    resolved = decode_candidates(decoder, to_try)
                    stats["decode_succeeded"] += len(resolved)
                    for eid, real_url in resolved.items():
                        merged[eid]["url"] = real_url
                        merged[eid]["url_resolved"] = True
                    for it in to_try:
                        if it["evidence_id"] not in resolved:
                            it["url_resolved"] = False
                write_shard(path, list(merged.values()))
            log(
                f"{role_id} {canonical}: "
                + ", ".join(f"{m}:{len(b)}" for m, b in sorted(new_by_month.items()))
            )

    # ---------------- 市场级源 ----------------
    log("采集 SEC EDGAR 8-K 裁员披露 ...")
    edgar_results = {}
    for month in month_list:
        time.sleep(EDGAR_DELAY_SEC)
        res = collect_edgar_month(session, month)
        edgar_results[month] = res
        (MARKET_DIR / "sec_edgar").mkdir(parents=True, exist_ok=True)
        (MARKET_DIR / "sec_edgar" / f"{month}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"  EDGAR {month}: total={res['total_hits']} 8-K={len(res['filings_8k'])}"
            + (f" err={res['error']}" if res["error"] else ""))

    log("采集 layoffs.fyi 明细镜像 ...")
    layoffs = collect_layoffs_detail(session)
    (MARKET_DIR / "layoffs_fyi_detail.json").write_text(
        json.dumps(layoffs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  layoffs.fyi: months={len(layoffs['monthly'])}"
        + (f" err={layoffs['error']}" if layoffs["error"] else ""))

    # ---------------- 汇总与 QC ----------------
    # summary/QC 始终覆盖全部岗位（--roles 只限制本轮采集范围）
    summary = build_summary(taxonomy_all)
    qc = build_qc(stats, month_list, summary, edgar_results, layoffs,
                  decode_available)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    QC_PATH.write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"summary -> {SUMMARY_PATH}")
    log(f"qc -> {QC_PATH}")
    return qc


def build_summary(taxonomy: list[dict]) -> list[dict]:
    """扫描全部分片生成 API 层摘要。"""
    summary = []
    for role in taxonomy:
        role_id = role["role_id"]
        role_dir = EVIDENCE_ROOT / role_id
        months_covered = []
        total_items = 0
        by_type: dict[str, int] = {}
        top_items: dict[str, list[dict]] = {}
        if role_dir.exists():
            for shard in sorted(role_dir.glob("*.jsonl")):
                month = shard.stem
                items = list(read_shard(shard).values())
                if not items:
                    continue
                months_covered.append(month)
                total_items += len(items)
                for it in items:
                    by_type[it["event_type"]] = by_type.get(it["event_type"], 0) + 1
                top = sorted(items, key=lambda x: (-x["relevance_score"], x["published_at"]))[:3]
                top_items[month] = [
                    {
                        "evidence_id": t["evidence_id"],
                        "title": t["title"],
                        "url": t["url"],
                        "url_resolved": t["url_resolved"],
                        "source_name": t["source_name"],
                        "published_at": t["published_at"],
                        "event_type": t["event_type"],
                        "relevance_score": t["relevance_score"],
                    }
                    for t in top
                ]
        summary.append({
            "role_id": role_id,
            "canonical_role": role["canonical_role"],
            "months_covered": months_covered,
            "total_items": total_items,
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "top_items": top_items,
        })
    return summary


def build_qc(
    stats: dict,
    month_list: list[str],
    summary: list[dict],
    edgar_results: dict,
    layoffs: dict,
    decode_available: bool,
) -> dict:
    total_items = sum(s["total_items"] for s in summary)
    role_months = sum(len(s["months_covered"]) for s in summary)
    by_type_all: dict[str, int] = {}
    for s in summary:
        for t, n in s["by_type"].items():
            by_type_all[t] = by_type_all.get(t, 0) + n
    raw = stats["raw_items"]
    kept = stats["after_filter"]
    decode_rate = (
        round(stats["decode_succeeded"] / stats["decode_attempted"], 4)
        if stats["decode_attempted"] else None
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "months": month_list,
        "total_items": total_items,
        "roles_covered": len(summary),
        "avg_items_per_role_month": (
            round(total_items / role_months, 2) if role_months else 0
        ),
        "rss": {
            "requests": stats["rss_requests"],
            "failures": stats["rss_failures"],
            "raw_items_fetched": raw,
            "items_after_relevance_filter": kept,
            "filter_keep_rate": round(kept / raw, 4) if raw else None,
            "filter_drop_rate": round(1 - kept / raw, 4) if raw else None,
            "noise_dropped": stats["noise_dropped"],
        },
        "decode": {
            "available": decode_available,
            "attempted": stats["decode_attempted"],
            "succeeded": stats["decode_succeeded"],
            "success_rate": decode_rate,
        },
        "by_type": dict(sorted(by_type_all.items(), key=lambda kv: -kv[1])),
        "edgar": {
            month: {
                "total_hits": r["total_hits"],
                "filings_8k": len(r["filings_8k"]),
                "error": r["error"],
            }
            for month, r in edgar_results.items()
        },
        "layoffs_fyi": {
            "detail_source": layoffs["source"],
            "detail_error": layoffs["error"],
            "detail_months": len(layoffs["monthly"]),
            "annual_stats_local": str(LAYOFFS_ANNUAL_LOCAL),
            "annual_stats_exists": LAYOFFS_ANNUAL_LOCAL.exists(),
            "ai_related_companies": len(layoffs.get("ai_related_companies") or []),
        },
        "notes": [
            "Google News RSS 历史月查询 after:YYYY-MM-01 before:下月01 实测可用(2026-10-17)。",
            "查询三级降级：整短语引号 → 无引号 AND → 无引号核心词(去 Frontend/Backend/Cloud 等修饰词)；"
            "0 结果才降级，三级共用同一相关性过滤，精度不受影响。",
            "GDELT DOC API 本机被限流(429)，本层不使用 GDELT。",
            "跳转链接解码走 batchexecute RPC，需 httpx[http2](h2 包)；失败保留原始链接 resolved=False。",
            f"每 (role, month) 最多解码 top {DECODE_TOP_N} 条控制耗时；未解码条目 url 为 news.google.com 跳转链接。",
            "layoffs.fyi 官网 Airtable 未直接抓取，明细用 GitHub 镜像(codeload zip)，年度总量用本地已存统计。",
            "SEC EDGAR 为公司级 8-K 披露(市场级信号)，写入 _market/sec_edgar/，不计入岗位条目。",
        ],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="岗位级月度证据采集 (Google News RSS + layoffs.fyi + SEC EDGAR)"
    )
    parser.add_argument("--months", type=int, default=6, help="最近 N 个月（含当月）")
    parser.add_argument("--roles", type=str, default="all", help="all 或逗号分隔 role_id")
    args = parser.parse_args(argv)
    run(months=args.months, roles_arg=args.roles)


if __name__ == "__main__":
    main(sys.argv[1:])
