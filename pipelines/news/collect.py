"""实时新闻情报层采集器。

用法::

    python -m pipelines.news.collect [--hours 48]

16 个源（RSS / API / 页面解析 / Google News 聚合），全部走 https_proxy 代理；
失败的源记 error 不阻塞。幂等增量：news_id 主键 ON CONFLICT DO NOTHING，
状态文件记录每源最后采集时间，QC 写 /data/shichaojian/JNIT/processed/news_collect_qc.json。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

from pipelines.evidence_v2._gnews_decode import GoogleNewsDecoder

# ---------------------------------------------------------------- 常量

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = Path("/data/shichaojian/JNIT/processed/news_state.json")
QC_PATH = Path("/data/shichaojian/JNIT/processed/news_collect_qc.json")
SKILL_VOCAB_PATH = ROOT / "data/gold/skill_vocab_v2.json"
ROLES_PATH = ROOT / "data/gold/fine_grained_roles_v2.json"

DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 25.0
SOURCE_SLEEP_SEC = 4.0

CATEGORIES = [
    "hiring", "layoff", "funding", "product_release",
    "research", "policy", "security", "tech_general",
]

# 有序规则：先命中先分类，tech_general 兜底
CATEGORY_RULES = [
    ("hiring", ["招聘", "扩招", "招募", "招人", "校招", "社招", "岗位新增", "headcount",
                "hiring", "job opening", "job posting", "we're hiring", "now hiring",
                "is hiring", "recruit", "job fair", "talent acquisition", "open roles"]),
    ("layoff", ["裁员", "缩编", "精简人员", "缩员", "削减岗位", "解雇",
                "layoff", "laid off", "lay off", "job cut", "workforce reduction",
                "eliminate", "redundan", "fired", "downsiz", "restructur"]),
    ("funding", ["融资", "募资", "领投", "跟投", "估值", "投资", "注资", "收购",
                 "funding", "funded", "raised", "raises", "series a", "series b",
                 "series c", "invest", "valuation", "acqui", "acquisition"]),
    ("research", ["论文", "研究", "突破", "新模型", "评测", "开源模型", "sota",
                  "paper", "research", "breakthrough", "benchmark", "state-of-the-art",
                  "arxiv", "study finds", "survey"]),
    ("policy", ["政策", "监管", "条例", "法案", "合规", "制裁", "出口管制",
                "regulation", "policy", "antitrust", "sanction", "bill", "compliance",
                "executive order", "export control"]),
    ("security", ["漏洞", "安全事件", "攻击", "泄露", "勒索", "入侵", "修复",
                  "vulnerability", "cve-", "data breach", "breach", "hack",
                  "ransomware", "exploit", "malware", "security flaw", "zero-day"]),
    ("product_release", ["发布", "上线", "推出", "发售", "首发", "公测", "正式版",
                         "launch", "release", "released", "announc", "debut",
                         "rollout", "unveil", "ship", "available now", "generally available"]),
]

_TRACKING_PARAMS = re.compile(r"^(utm_|spm|fbclid|gclid|dclid|mc_|ref$|ref_src$)", re.I)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- HTTP

def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA})


# ---------------------------------------------------------------- RSS 解析

def _text_of(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _first(elem: ET.Element, *tags: str) -> ET.Element | None:
    for tag in tags:
        found = elem.find(tag)
        if found is not None:
            return found
    return None


def _parse_rss_items(xml_bytes: bytes) -> list[dict]:
    """同时兼容 RSS 2.0 与 Atom；返回 {title,url,published,summary,content}。"""
    root = ET.fromstring(xml_bytes)
    items: list[dict] = []
    channel = root.find("channel")
    entries = channel.findall("item") if channel is not None else root.findall(
        "{http://www.w3.org/2005/Atom}entry"
    )
    for it in entries:
        if channel is not None:
            title = _text_of(it.find("title"))
            link_el = it.find("link")
            url = (link_el.text or "").strip() if link_el is not None else ""
            date_s = _text_of(_first(it, "pubDate", "date", "dc:date"))
            desc = _text_of(_first(it, "description", "summary"))
            content = _text_of(it.find("{http://purl.org/rss/1.0/modules/content/}encoded"))
        else:
            ns = "{http://www.w3.org/2005/Atom}"
            title = _text_of(it.find(f"{ns}title"))
            link_el = it.find(f"{ns}link")
            url = link_el.get("href", "") if link_el is not None else ""
            date_s = _text_of(_first(it, f"{ns}updated", f"{ns}published"))
            desc = _text_of(it.find(f"{ns}summary"))
            content = _text_of(it.find(f"{ns}content"))
        published = None
        if date_s:
            try:
                published = parsedate_to_datetime(date_s)
            except (TypeError, ValueError):
                try:
                    published = datetime.fromisoformat(date_s.replace("Z", "+00:00"))
                except ValueError:
                    published = None
        if published is not None and published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        items.append({
            "title": re.sub(r"<[^>]+>", "", title),
            "url": url,
            "published": published,
            "summary": re.sub(r"<[^>]+>", "", desc).strip(),
            "content": re.sub(r"<[^>]+>", "", content).strip(),
        })
    return items


def _fetch_rss(client: httpx.Client, feed_url: str, cutoff: datetime) -> list[dict]:
    resp = client.get(feed_url)
    resp.raise_for_status()
    out = []
    for it in _parse_rss_items(resp.content):
        if it["published"] is None or it["published"] < cutoff:
            continue
        out.append(it)
    return out


# ---------------------------------------------------------------- 各源 fetcher
# 统一返回 list[dict]: title, url, published(utc datetime), summary, content

def fetch_ithome(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.ithome.com/rss/", cutoff)


def fetch_infoq_cn(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.infoq.cn/feed", cutoff)


def fetch_oschina(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.oschina.net/news/rss", cutoff)


def fetch_solidot(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.solidot.org/index.rss", cutoff)


def fetch_cnbeta(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.cnbeta.com.tw/backend.php", cutoff)


def fetch_ars(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://feeds.arstechnica.com/arstechnica/index", cutoff)


def fetch_verge(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://www.theverge.com/rss/index.xml", cutoff)


def fetch_techcrunch(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_rss(client, "https://techcrunch.com/feed/", cutoff)


def fetch_gnews_36kr(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_gnews(client, "site:36kr.com", cutoff)


def fetch_gnews_jiqizhixin(client: httpx.Client, cutoff: datetime) -> list[dict]:
    return _fetch_gnews(client, "site:jiqizhixin.com", cutoff)


def _fetch_gnews(client: httpx.Client, query: str, cutoff: datetime) -> list[dict]:
    """Google News RSS 聚合；批量解码跳转链接，失败保留原链并标 url_resolved=False。"""
    url = (
        "https://news.google.com/rss/search?"
        + urlencode({"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})
    )
    resp = client.get(url)
    resp.raise_for_status()
    raw = _parse_rss_items(resp.content)
    items = [it for it in raw if it["published"] is None or it["published"] >= cutoff]
    # 标题形如 "标题 - 来源"，去掉来源后缀
    for it in items:
        it["title"] = re.sub(r"\s+-\s+[^-]{1,40}$", "", it["title"]).strip()
    # 批量解码跳转链接
    article_ids = []
    for it in items:
        m = re.search(r"/articles/([A-Za-z0-9_-]+)", it["url"] or "")
        article_ids.append(m.group(1) if m else None)
    with GoogleNewsDecoder(timeout=TIMEOUT) as dec:
        params = {aid: dec.fetch_params(aid) for aid in set(article_ids) if aid}
        batch = [(aid, p[0], p[1]) for aid, p in params.items() if p]
        decoded = dec.decode_batch(batch) if batch else {}
    for it, aid in zip(items, article_ids):
        if aid and aid in decoded:
            it["url"] = decoded[aid]
            it["resolved"] = True
        else:
            it["resolved"] = False
    return items


def fetch_hn(client: httpx.Client, cutoff: datetime) -> list[dict]:
    """HN Algolia：AI/tech 两个查询，按时间排序，48h 窗口（控速间隔 10s）。"""
    cutoff_ts = int(cutoff.timestamp())
    out, seen = [], set()
    for query in ("AI", "tech"):
        params = {
            "tags": "story",
            "query": query,
            "numericFilters": f"created_at_i>{cutoff_ts}",
            "hitsPerPage": 60,
        }
        resp = client.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params=params,
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            oid = hit.get("objectID")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            ts = hit.get("created_at_i")
            out.append({
                "title": (hit.get("title") or "").strip(),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "published": datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                "summary": f"{hit.get('points', 0)} points, {hit.get('num_comments', 0)} comments",
                "content": "",
                "resolved": True,
            })
        time.sleep(10.0)
    return out


def fetch_juejin(client: httpx.Client, cutoff: datetime) -> list[dict]:
    """掘金推荐 API（POST JSON）。新版响应行结构为 item_info.article_info。"""
    url = "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
    payload = {"id_type": 2, "sort_type": 300, "cate_id": "0", "cursor": "0", "limit": 30}
    resp = client.post(url, json=payload)
    resp.raise_for_status()
    out = []
    for row in resp.json().get("data") or []:
        if row.get("item_type") != 2:
            continue
        info = (row.get("item_info") or {}).get("article_info") or {}
        ts = info.get("ctime")
        published = datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else None
        if published is None or published < cutoff:
            continue
        aid = info.get("article_id") or ""
        title = re.sub(r"<[^>]+>", "", info.get("title") or "").strip()
        brief = re.sub(r"<[^>]+>", "", info.get("brief_content") or "").strip()
        out.append({
            "title": title,
            "url": f"https://juejin.cn/post/{aid}" if aid else "",
            "published": published,
            "summary": brief[:500],
            "content": brief,
            "resolved": True,
        })
    return out


def fetch_layoffs(client: httpx.Client, cutoff: datetime) -> list[dict]:
    """layoffs.fyi annual-stats API（页面内嵌的真实数据源）→ 年度统计情报。"""
    resp = client.get("https://layoffs-fyi.onrender.com/api/annual-stats")
    resp.raise_for_status()
    data = resp.json()
    years = data.get("years") or []
    if not years:
        return []
    cur_year = max(years, key=lambda y: y.get("year", 0))
    hist = ", ".join(
        f"{y['year']}: {y.get('employees', '?')} employees / {y.get('companies', '?')} companies"
        for y in sorted(years, key=lambda y: -y.get("year", 0))[:4]
    )
    total_emp = cur_year.get("employees", "?")
    total_co = cur_year.get("companies", "?")
    content = (
        f"Layoffs.fyi annual stats (fetched {_utcnow().date().isoformat()}): "
        f"in {cur_year.get('year')}, {total_emp} tech employees laid off across "
        f"{total_co} tech companies. Recent years: {hist}. "
        f"Total events tracked: {data.get('totalEvents', '?')}. "
        f"Source: https://layoffs.fyi/"
    )
    return [{
        "title": (
            f"Layoffs.fyi 年度裁员统计：{cur_year.get('year')} 年已有 "
            f"{total_emp} 名科技员工被裁（{total_co} 家公司）"
        ),
        "url": "https://layoffs.fyi/",
        "published": _utcnow(),
        "summary": content[:500],
        "content": content,
        "resolved": True,
    }]


def fetch_github_trending(client: httpx.Client, cutoff: datetime) -> list[dict]:
    resp = client.get("https://github.com/trending?since=daily")
    resp.raise_for_status()
    out = []
    if BeautifulSoup is not None:
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article.Box-row"):
            a = article.select_one("h2 a")
            if a is None:
                continue
            repo = a.get("href", "").strip("/")
            desc_el = article.select_one("p")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            star_el = article.select_one('a[href$="/stargazers"]')
            stars = star_el.get_text(" ", strip=True) if star_el else ""
            if not repo:
                continue
            out.append({
                "title": f"GitHub Trending: {repo.replace('/', ' / ')}",
                "url": f"https://github.com/{repo}",
                "published": _utcnow(),
                "summary": f"⭐ {stars} | {desc}" if stars else desc,
                "content": desc,
                "resolved": True,
            })
    else:  # 正则兜底
        for repo, desc in re.findall(
            r'href="/([^"/]+/[^"/]+)"[\s\S]{0,2000}?<p[^>]*>([\s\S]*?)</p>',
            resp.text,
        )[:25]:
            desc_clean = re.sub(r"<[^>]+>", "", desc).strip()
            out.append({
                "title": f"GitHub Trending: {repo}",
                "url": f"https://github.com/{repo}",
                "published": _utcnow(),
                "summary": desc_clean,
                "content": desc_clean,
                "resolved": True,
            })
    return out


SOURCES = [
    ("ithome", "IT之家", "zh", fetch_ithome),
    ("infoq_cn", "InfoQ中文", "zh", fetch_infoq_cn),
    ("oschina", "开源中国", "zh", fetch_oschina),
    ("solidot", "Solidot", "zh", fetch_solidot),
    ("cnbeta", "cnBeta", "zh", fetch_cnbeta),
    ("ars", "Ars Technica", "en", fetch_ars),
    ("verge", "The Verge", "en", fetch_verge),
    ("techcrunch", "TechCrunch", "en", fetch_techcrunch),
    ("gnews_36kr", "GoogleNews(36氪)", "zh", fetch_gnews_36kr),
    ("gnews_jiqizhixin", "GoogleNews(机器之心)", "zh", fetch_gnews_jiqizhixin),
    ("hn", "HackerNews", "en", fetch_hn),
    ("juejin", "掘金", "zh", fetch_juejin),
    ("layoffs", "layoffs.fyi", "zh", fetch_layoffs),
    ("github_trending", "GitHub Trending", "en", fetch_github_trending),
]


# ---------------------------------------------------------------- 规范化 / 打标

def normalize_url(url: str) -> str:
    """去跟踪参数、小写 scheme/host、去 www、去尾斜杠。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING_PARAMS.match(k)
    ]
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def make_news_id(url: str, source: str, title: str) -> str:
    base = normalize_url(url) or f"{source}::{title.strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def title_fingerprint(title: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", title.lower())


def detect_lang(text: str) -> str:
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return "zh" if cjk / max(len(text), 1) > 0.2 else "en"


def classify(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    # "优化/毕业" 必须紧邻人员语境才算裁员信号（性能优化、CNCF 毕业是误报大户）
    if re.search(r"(人员|员工|大厂|被裁)[^。；]{0,8}(优化|毕业)|(优化|毕业)[^。；]{0,8}(人员|员工)", text):
        return "layoff"
    for cat, words in CATEGORY_RULES:
        for w in words:
            if w in text:
                return cat
    return "tech_general"


class Tagger:
    """技能 / 岗位词表打标。短别名（go/c/r/ts/js）大小写敏感+词边界。"""

    def __init__(self) -> None:
        vocab = json.loads(SKILL_VOCAB_PATH.read_text(encoding="utf-8"))
        self.skill_patterns: list[tuple[str, re.Pattern]] = []
        for alias, skill_id in (vocab.get("alias_to_id") or {}).items():
            pat = self._compile_alias(alias)
            if pat is not None:
                self.skill_patterns.append((skill_id, pat))
        roles = json.loads(ROLES_PATH.read_text(encoding="utf-8"))
        # 岗位全名去掉通用尾词（Engineer/Developer 等）后剩下的特征短语
        # 才是新闻文本里会出现的信号；"data/software/cloud" 等单泛词丢弃。
        generic_tail = {
            "engineer", "developer", "scientist", "manager", "lead",
            "architect", "programmer", "analyst", "administrator",
            "specialist", "designer", "consultant", "developer", "qa",
        }
        generic_single = {"data", "software", "cloud", "web", "it"}
        self.role_patterns: list[tuple[str, re.Pattern]] = []
        seen_pat: set[tuple[str, str]] = set()
        for role in roles:
            rid = role.get("role_id") or role.get("fine_role")
            for ph in {role.get("role_name"), role.get("fine_role")}:
                if not ph:
                    continue
                tokens = re.findall(r"[a-z0-9+#.\-]+|[一-鿿]+", ph.lower())
                while tokens and tokens[-1] in generic_tail:
                    tokens.pop()
                if not tokens:
                    continue
                core = " ".join(tokens)
                if len(core) < 4 or (len(tokens) == 1 and tokens[0] in generic_single):
                    continue
                pat = self._compile_alias(core, case_insensitive=True)
                if pat is not None and (rid, pat.pattern) not in seen_pat:
                    seen_pat.add((rid, pat.pattern))
                    self.role_patterns.append((rid, pat))

    @staticmethod
    def _compile_alias(alias: str, case_insensitive: bool | None = None) -> re.Pattern | None:
        if not alias or len(alias) > 40:
            return None
        has_cjk = any("一" <= ch <= "鿿" for ch in alias)
        if has_cjk:
            return re.compile(re.escape(alias), re.I)
        short = len(alias) <= 3 or alias.isupper()
        if case_insensitive is None:
            case_insensitive = not short
        flags = re.I if case_insensitive else 0
        # 纯字母别名加词边界；含特殊字符的（c++/.net 等）直接子串
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9+#.\-]*", alias):
            return re.compile(rf"\b{re.escape(alias)}\b", flags)
        return re.compile(re.escape(alias), flags)

    def tag(self, title: str, summary: str) -> tuple[list[str], list[str]]:
        text = f"{title}\n{summary}"
        skills = sorted({sid for sid, pat in self.skill_patterns if pat.search(text)})
        roles = sorted({rid for rid, pat in self.role_patterns if pat.search(text)})
        return skills, roles


def normalize_item(source_key: str, source_name: str, lang_fixed: str,
                   raw: dict, tagger: Tagger) -> dict:
    title = (raw.get("title") or "").strip()
    if not title:
        raise ValueError("empty title")
    url = (raw.get("url") or "").strip() or None
    summary = (raw.get("summary") or "").strip() or None
    content = (raw.get("content") or "").strip()
    published = raw.get("published") or _utcnow()
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    resolved = bool(raw.get("resolved", True)) and bool(url)
    if not content and summary:
        content = summary  # 摘要源诚实存摘要
    lang = lang_fixed or detect_lang(title + (summary or ""))
    skills, role_ids = tagger.tag(title, summary or "")
    return {
        "news_id": make_news_id(url or "", source_key, title),
        "title": title[:1000],
        "url": url,
        "url_resolved": resolved,
        "source": source_name,
        "lang": lang,
        "published_at": published,
        "summary": summary[:4000] if summary else None,
        "content_text": content[:20000] if content else None,
        "category": classify(title, summary or ""),
        "skills": skills,
        "role_ids": role_ids,
    }


# ---------------------------------------------------------------- 主流程

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def insert_items(items: list[dict]) -> int:
    """幂等插入，返回实际新增条数。"""
    if not items:
        return 0
    import psycopg

    sql = """
        INSERT INTO news_items
          (news_id, title, url, url_resolved, source, lang, published_at,
           summary, content_text, category, skills, role_ids)
        VALUES (%(news_id)s, %(title)s, %(url)s, %(url_resolved)s, %(source)s,
                %(lang)s, %(published_at)s, %(summary)s, %(content_text)s,
                %(category)s, %(skills)s, %(role_ids)s)
        ON CONFLICT (news_id) DO NOTHING
    """
    added = 0
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(sql, it)
                if cur.rowcount == 1:
                    added += 1
        conn.commit()
    return added


def run(hours: float = 48.0, quiet: bool = False) -> dict:
    cutoff = _utcnow() - timedelta(hours=hours)
    tagger = Tagger()
    state = load_state()
    qc: dict = {
        "run_at": _utcnow().isoformat(),
        "hours": hours,
        "sources": {},
        "totals": {"fetched": 0, "added": 0},
        "category_dist": {},
        "lang_dist": {},
    }
    seen_fp: set[str] = set()  # Google News 跨媒体标题去重（全局同样生效）

    with _client() as client:
        for idx, (key, name, lang_fixed, fetcher) in enumerate(SOURCES):
            entry: dict = {"fetched": 0, "added": 0, "error": None}
            try:
                raws = fetcher(client, cutoff)
            except Exception as exc:  # 失败的源不阻塞
                entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
                raws = []
            norm_items: list[dict] = []
            for raw in raws:
                try:
                    item = normalize_item(
                        key, name, lang_fixed if lang_fixed else None, raw, tagger
                    )
                except ValueError:
                    continue
                fp = title_fingerprint(item["title"])
                if fp in seen_fp:
                    continue
                seen_fp.add(fp)
                norm_items.append(item)
            entry["fetched"] = len(norm_items)
            entry["added"] = insert_items(norm_items)
            for it in norm_items:
                qc["category_dist"][it["category"]] = (
                    qc["category_dist"].get(it["category"], 0) + 1
                )
                qc["lang_dist"][it["lang"]] = qc["lang_dist"].get(it["lang"], 0) + 1
            qc["sources"][name] = entry
            qc["totals"]["fetched"] += entry["fetched"]
            qc["totals"]["added"] += entry["added"]
            state[key] = {"last_collect": _utcnow().isoformat()}
            if not quiet:
                print(f"[{key}] fetched={entry['fetched']} added={entry['added']}"
                      + (f" ERROR={entry['error']}" if entry["error"] else ""))
            if idx < len(SOURCES) - 1:
                time.sleep(SOURCE_SLEEP_SEC)

    save_state(state)
    QC_PATH.parent.mkdir(parents=True, exist_ok=True)
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quiet:
        print(f"TOTAL fetched={qc['totals']['fetched']} added={qc['totals']['added']}")
        print(f"categories={qc['category_dist']} lang={qc['lang_dist']}")
        print(f"QC -> {QC_PATH}")
    return qc


def main() -> None:
    parser = argparse.ArgumentParser(description="JobNavigator-IT 新闻采集器")
    parser.add_argument("--hours", type=float, default=48.0, help="采集时间窗口（小时）")
    args = parser.parse_args()
    run(hours=args.hours)


if __name__ == "__main__":
    main()
