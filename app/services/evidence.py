"""C 模块 ② 检索核心 + 运行时接口：证据检索（RAG）。

对外契约（02_队友任务分工.md §3 / §5.1）：
    retrieve_evidence(role, months, top_k) -> {events: [...], jobs: [...]}

流程：读角色分片 → BM25 主题召回 → 方向归因复合排序 → 混 JD → 去重 TopK。
索引由 pipelines/trend/build_evidence_index.py 预先生成（零依赖分片）。

复合排序分（决策：方向软加权）：
    composite = 0.4·主题相关(BM25) + 0.3·方向对齐 + 0.2·事件重要性 + 0.1·时间近度
direction 为空时方向对齐取中性 0.5（退化为纯主题+重要性）。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

INDEX_DIR = Path("data/processed/evidence_index")
EVENTS_DIR = INDEX_DIR / "events"
JOBS_DIR = INDEX_DIR / "jobs"
TAXONOMY_PATH = Path("data/gold/role_taxonomy.json")

OPPORTUNITY_TYPES = {"funding", "product_release", "research_breakthrough"}
RISK_TYPES = {"layoff", "policy", "security_incident"}
# 顺序敏感：具体的在前，宽泛的在后。去掉 EPU_POLICY/GENERAL_GOVERNMENT 这类
# 几乎每条新闻都带的宏观标签，避免 policy 被过度分类。
EVENT_TYPE_RULES = [
    (("LAYOFF", "UNEMPLOY", "JOB_CUT", "WORKER_STRIKE"), "layoff"),
    (("CYBER_ATTACK", "SECURITY_SERVICES", "HACK", "DATA_BREACH", "MALWARE", "RANSOMWARE"), "security_incident"),
    (("FUNDING", "VENTURE", "ECON_STOCKMARKET", "ECON_EARNINGS", "IPO", "ECON_INVESTMENT"), "funding"),
    (("PATENT", "SCIENCE_RESEARCH", "INNOVATION", "BREAKTHROUGH"), "research_breakthrough"),
    (("PRODUCT_RELEASE", "_LAUNCH", "NEW_PRODUCT"), "product_release"),
    (("LEGISLATION", "REGULATION", "ANTITRUST", "DATA_PROTECTION"), "policy"),
]

_SAFE = re.compile(r"[^A-Za-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# ── 完整版四重约束相关性闸门 ────────────────────────────────────────────────
# 受限于数据（无标题/正文、匹配多为 URL 伪词），用“技能白名单 + 主题共现 +
# 域名黑名单 + 方向一致”叠加约束，换取高精度的干净样本；召回不足由聚合信号兜底。

SKILL_VOCAB_PATH = Path("data/gold/skill_vocab.json")

# URL/后缀伪词：来自链接/域名，非正文内容（占样本约 88%）
ARTIFACT_TERMS = {"html", "htm", "php", "aspx", ".net", "www", "amp", "com", "org", "co", "io"}
# 歧义泛词：本身是技能名但又是常用英文词，单独命中极易误匹配（react/go/rust…）
AMBIGUOUS_TERMS = {
    "react", "reacts", "reacted", "reaction", "go", "going", "swift", "rust", "java",
    "python", "ruby", "scala", "spring", "c", "r", "d", "node", "next", "dart",
    "algorithm", "algorithms", "shell", "pandas", "spark", "agent",
}
# 严格科技主题
TECH_THEMES = (
    "SOFTWARE", "COMPUTER", "CYBER", "ARTIFICIAL_INTELLIGENCE",
    "MACHINE_LEARNING", "WB_652_ICT_APPLICATIONS", "TECHNOLOGY",
)
# 经济/劳动力主题（与科技主题共现才算“真就业相关事件”）
ECON_THEMES = (
    "ECON_", "LAYOFF", "UNEMPLOY", "WB_855_LABOR", "ENTREPRENEUR",
    "EPU_ECONOMY", "HIRING", "RECRUIT", "WB_2024",
)
# 垃圾来源（股票自动聚合站/小报/八卦）域名子串黑名单
JUNK_DOMAIN_SUBSTR = (
    "ticker", "marketsdaily", "dailypolitical", "defenseworld", "prokerala",
    "starmagazine", "newsbusters", "ghanamma", "wyomingnewsnow", "dailymail",
    "insidermonkey", "finanznachrichten",
)
# 弱可信来源（财经自动聚合/泛地方新闻）：不删，降权
WEAK_DOMAIN_SUBSTR = ("manilatimes", "webindia", "calcuttanews", "moneycontrol",
                      "tickerreport", "livemint")
# 岗位/职业/招聘上下文词：标题或 URL slug 里出现 -> 真 IT 岗位语境
ROLE_CONTEXT_WORDS = {
    "frontend", "backend", "fullstack", "devops", "developer", "developers",
    "engineer", "engineering", "architect", "programmer", "software", "sysadmin",
    "qa", "sre", "cloud", "data", "mobile", "web", "api", "recruitment",
    "recruiting", "hiring", "vacancy", "job", "jobs",
}
# 内容型强科技主题（比 WB_ 系列更可信）
STRICT_TECH_THEMES = ("SOFTWARE", "COMPUTER", "CYBER", "ARTIFICIAL_INTELLIGENCE",
                      "MACHINE_LEARNING")
# 坏标题模式：非技术/灾难/政治场景，命中直接挡
BAD_TITLE_PHRASES = ("reacts to", "readers react", "doctor reacts", "bridge cracks",
                     "schools react", "neighbors react", "netizens react",
                     "employees react",
                     "python eggs", "dumsor theatricals", "missing containers",
                     "florida woman", "is python becoming pinyin", "koenigsegg statistics",
                     "tarmac scrum", "tony khan", "kapil sibal", "shell casing",
                     "family of late shell", "saved life",
                     "amid crisis")
BAD_TITLE_WORDS = {"war", "iran", "trump", "protesters", "protest", "shooting",
                   "murder", "ceasefire", "sudan", "gaza", "ukraine", "flood",
                   "earthquake", "storm", "anxiety", "runner", "collapses",
                   "pythons"}
GENERIC_ROLE_TOKENS = {
    "engineer", "developer", "architect", "specialist", "administrator",
    "manager", "master", "analyst", "designer", "technical", "software",
}
HARD_TECH_CONTEXT_WORDS = {
    "frontend", "backend", "fullstack", "developer", "developers", "software",
    "programmer", "devops", "sre", "qa", "cloud", "data", "mobile", "web",
    "api", "javascript", "typescript", "css", "html", "node", "reactjs",
    "react.js", "vue", "angular", "kubernetes", "docker", "linux",
}
ROLE_ANCHOR_EXPANSIONS = {
    "ai": {"ai", "artificial", "intelligence", "machine", "learning", "llm", "openai", "agent"},
    "game": {"game", "gaming", "unreal", "gamedev", "csharp"},
    "wordpress": {"wordpress", "php", "cms", "woocommerce"},
    "mobile": {"mobile", "android", "ios", "kotlin", "swift", "react", "native"},
    "frontend": {"frontend", "front", "react", "vue", "angular", "javascript", "typescript", "css", "html"},
    "backend": {"backend", "server", "api", "java", "python", "node", "golang", "microservices"},
    "security": {"security", "cyber", "cybersecurity", "breach", "malware", "ransomware", "vulnerability"},
    "devops": {"devops", "kubernetes", "docker", "terraform", "ansible", "ci", "cd"},
    "data": {"data", "etl", "pipeline", "warehouse", "spark", "snowflake", "databricks"},
    "system": {"system", "sysadmin", "administrator", "linux", "unix", "powershell"},
}
ROLE_REQUIRED_TERMS = {
    "backend go engineer": {"go", "golang"},
    "backend java engineer": {"java", "spring"},
    "cloud java engineer": {"java", "spring", "oracle"},
    "backend ruby engineer": {"ruby", "rails"},
    "backend php engineer": {"php", "laravel"},
    "backend node.js engineer": {"node", "nodejs", "javascript", "typescript"},
    "node.js devops engineer": {"node", "nodejs", "javascript", "typescript", "devops"},
    "frontend react engineer": {"react", "reactjs", "javascript", "typescript", "frontend"},
    "frontend angular engineer": {"angular"},
    "frontend vue engineer": {"vue", "javascript", "typescript", "frontend"},
    "wordpress developer": {"wordpress", "php", "cms"},
    "data scientist": {"scientist", "machine", "learning", "model", "analytics"},
    "mlops engineer": {"mlops"},
    "mobile c++ engineer": {"c", "cpp"},
    "mobile qa automation engineer": {"qa", "test", "testing", "automation"},
}


def _load_skill_vocab() -> set[str]:
    if SKILL_VOCAB_PATH.exists():
        try:
            d = json.loads(SKILL_VOCAB_PATH.read_text(encoding="utf-8"))
            return {str(a).lower() for a in d.get("all_aliases", [])}
        except (json.JSONDecodeError, OSError):
            pass
    return set()


_SKILL_VOCAB = _load_skill_vocab()


def _is_junk_domain(dom: str) -> bool:
    d = (dom or "").lower()
    return any(s in d for s in JUNK_DOMAIN_SUBSTR)


def _strong_skill_terms(terms: list[str]) -> list[str]:
    """明确技能词：在词表、非歧义、非伪词、长度≥3（如 kubernetes/encryption/jira）。"""
    return [t for t in terms
            if t in _SKILL_VOCAB and t not in AMBIGUOUS_TERMS
            and t not in ARTIFACT_TERMS and len(t) >= 3]


def _title_tokens(title: str) -> list[str]:
    return _TOKEN_RE.findall((title or "").lower())


def _is_weak_domain(dom: str) -> bool:
    d = (dom or "").lower()
    return any(s in d for s in WEAK_DOMAIN_SUBSTR)


def _bad_title(title: str) -> bool:
    t = (title or "").lower()
    if any(p in t for p in BAD_TITLE_PHRASES):
        return True
    return bool(set(_title_tokens(title)) & BAD_TITLE_WORDS)


def _title_has_context(title: str) -> bool:
    """标题/URL slug 里有岗位/职业词，或另一个明确技能词 -> 真 IT 语境。"""
    toks = set(_title_tokens(title))
    if toks & ROLE_CONTEXT_WORDS:
        return True
    return any(t in _SKILL_VOCAB and t not in AMBIGUOUS_TERMS and len(t) >= 3 for t in toks)


def _title_quality(title: str, domain: str) -> float:
    """证据可解释性分 0..1：标题越像真 IT 岗位/技术，分越高（坏标题=0）。"""
    if _bad_title(title):
        return 0.0
    toks = _title_tokens(title)
    if not toks or all(t.isdigit() for t in toks):
        return 0.1
    tset, score = set(toks), 0.3
    if tset & ROLE_CONTEXT_WORDS:
        score += 0.4
    if any(t in _SKILL_VOCAB and t not in AMBIGUOUS_TERMS and len(t) >= 3 for t in toks):
        score += 0.3
    if _is_weak_domain(domain):
        score *= 0.7
    return min(1.0, score)


def _role_anchor_terms(role: str, info: dict) -> set[str]:
    role_tokens = set(_title_tokens(role)) - GENERIC_ROLE_TOKENS
    anchors = set(role_tokens)
    role_l = (role or "").lower()
    for key, terms in ROLE_ANCHOR_EXPANSIONS.items():
        if key in role_l or key in role_tokens:
            anchors.update(terms)
    for alias in info.get("aliases", []) or []:
        anchors.update(set(_title_tokens(alias)) - GENERIC_ROLE_TOKENS)
    return {a for a in anchors if len(a) >= 2}


def _role_required_terms(role: str) -> set[str]:
    return ROLE_REQUIRED_TERMS.get((role or "").lower(), set())


def _role_required_satisfied(role: str, toks: set[str]) -> bool:
    role_l = (role or "").lower()
    required = _role_required_terms(role)
    if not required:
        return True
    if role_l == "mobile qa automation engineer":
        return bool(toks & {"mobile", "android", "ios"}) and bool(toks & required)
    if role_l == "mobile c++ engineer":
        return bool(toks & {"mobile", "android", "ios"}) and bool(toks & required)
    return bool(toks & required)


def _role_title_affinity(role: str, info: dict, title: str) -> float:
    """岗位相关性 0..1：标题要像该岗位的证据，而不只是泛技术新闻。"""
    if _bad_title(title):
        return 0.0
    toks = set(_title_tokens(title))
    if not toks:
        return 0.0
    anchors = _role_anchor_terms(role, info)
    hit = toks & anchors
    if not hit:
        return 0.0
    if not _role_required_satisfied(role, toks):
        return 0.0
    strong_title_skills = {
        t for t in toks
        if t in _SKILL_VOCAB and t not in AMBIGUOUS_TERMS and len(t) >= 3
    }
    if all(t in AMBIGUOUS_TERMS for t in hit) and not (toks & HARD_TECH_CONTEXT_WORDS or strong_title_skills):
        return 0.0
    score = 0.55
    if len(hit) >= 2:
        score += 0.2
    if toks & ROLE_CONTEXT_WORDS:
        score += 0.15
    if strong_title_skills:
        score += 0.1
    return min(1.0, score)


def _is_relevant(c: dict) -> bool:
    """精排前约束：黑名单/坏标题直接丢；明确技能词放行；
    歧义技能词必须有岗位/技术上下文（标题岗位词 / 另一强技能词 / 科技∧经济主题）。"""
    domain = c.get("source_domain")
    if _is_junk_domain(domain):
        return False
    title = _title_from_url(c.get("url", ""), domain or "")
    if _bad_title(title):
        return False
    terms = [str(t).lower() for t in (c.get("matched_terms") or [])]
    if not terms:
        return False
    if _strong_skill_terms(terms):
        return True
    amb_skill = [t for t in terms if t in _SKILL_VOCAB and t in AMBIGUOUS_TERMS]
    if amb_skill:
        if _title_has_context(title):                 # 标题有岗位/技术上下文
            return True
        themes = (c.get("themes") or "").upper()       # 或 科技∧经济主题共现
        if any(t in themes for t in STRICT_TECH_THEMES) and any(t in themes for t in ECON_THEMES):
            return True
    return False


def _safe_name(s: str) -> str:
    return _SAFE.sub("_", str(s or "unknown")).strip("_") or "unknown"


def _tok(text: str) -> list[str]:
    if not text:
        return []
    return _TOKEN_RE.findall(str(text).replace("_", " ").replace(";", " ").lower())


def _classify(themes: str) -> str:
    up = (themes or "").upper()
    for keys, label in EVENT_TYPE_RULES:
        if any(k in up for k in keys):
            return label
    return "market_report"


def _title_from_url(url: str, domain: str) -> str:
    if not url:
        return f"{domain} 相关报道" if domain else "相关报道"
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug)
    slug = re.sub(r"[-_]+", " ", slug).strip()
    if len(slug) < 8 or not re.search(r"[a-z]{3,}", slug.lower()):
        return f"{domain} 相关报道" if domain else "相关报道"
    return slug[:120]


def _title_sig(title: str) -> str:
    """标题归一签名：取前 7 个实词，用于合并同一新闻的近重复版本（不同 URL/日期）。"""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return " ".join(words[:7])


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(corpus)
        self.dl = [len(d) for d in corpus]
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in corpus]
        df: Counter = Counter()
        for d in corpus:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def score(self, q: list[str], i: int) -> float:
        if self.avgdl == 0:
            return 0.0
        tf, dl, s = self.tf[i], self.dl[i], 0.0
        for t in q:
            if t in tf:
                idf = self.idf.get(t, 0.0)
                f = tf[t]
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


def _ym(month: str) -> str:
    return str(month or "")[:7]


class EvidenceService:
    _tax: dict | None = None
    RELEVANCE_GATE = True   # 相关性闸门开关（评估消融时可关）
    ROLE_AFFINITY_DISPLAY_MIN = 0.5
    WEAK_TITLE_QUALITY_MIN = 0.5

    # ---- 资源加载 ----
    @classmethod
    def _taxonomy(cls) -> dict:
        if cls._tax is None:
            cls._tax = {}
            if TAXONOMY_PATH.exists():
                for t in json.loads(TAXONOMY_PATH.read_text(encoding="utf-8")):
                    cls._tax[t["canonical_role"]] = t
        return cls._tax

    @classmethod
    def _load_events(cls, role: str, months: tuple[str, str]) -> list[dict]:
        d = EVENTS_DIR / _safe_name(role)
        if not d.is_dir():
            return []
        lo, hi = _ym(months[0]), _ym(months[1])
        out = []
        for shard in d.glob("*.jsonl"):
            if not (lo <= _ym(shard.stem) <= hi):
                continue
            with open(shard, encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out

    @classmethod
    def _load_jobs(cls, role: str, months: tuple[str, str], limit: int) -> list[dict]:
        p = JOBS_DIR / f"{_safe_name(role)}.jsonl"
        if not p.exists():
            return []
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        lo, hi = _ym(months[0]), _ym(months[1])
        in_range = [r for r in rows if lo <= _ym(r.get("month")) <= hi]
        pool = in_range or rows  # 区间内无 JD 则回退到该角色全部（存在性证据不强依赖时间）
        pool.sort(key=lambda r: (r.get("post_date") or "", r.get("role_match_score") or 0), reverse=True)
        out = []
        for r in pool[:limit]:
            out.append({
                "evidence_type": "job_posting",
                "company_name": r.get("company_name"),
                "title": r.get("raw_job_title"),
                "post_date": r.get("post_date"),
                "salary_mid": r.get("salary_mid"),
                "job_url": r.get("job_url"),          # 现状多为空
                "role_match_score": r.get("role_match_score"),
                "out_of_range": not bool(in_range),
            })
        return out

    # ---- 方向对齐 ----
    @staticmethod
    def _direction_align(tone: float, etype: str, direction: str | None) -> float:
        if not direction or direction in ("flat", "stable"):
            return 0.5  # 中性：无方向偏好
        base = 0.5 + 0.5 * math.tanh(tone / 5.0)      # tone>0 -> >0.5
        if direction == "down":
            base = 1.0 - base
        if etype in (OPPORTUNITY_TYPES if direction == "up" else RISK_TYPES):
            base = min(1.0, base + 0.2)
        if etype in (RISK_TYPES if direction == "up" else OPPORTUNITY_TYPES):
            base = max(0.0, base - 0.2)
        return base

    # ---- 主入口 ----
    @classmethod
    def retrieve_evidence(cls, role: str, months: tuple[str, str],
                          top_k: int = 5, direction: str | None = None) -> dict:
        """契约接口。direction 可选（'up'/'down'/'flat'），给了就做方向归因排序。"""
        raw_cands = cls._load_events(role, months)
        total = len(raw_cands)
        aggregate = cls._aggregate(raw_cands)          # 聚合信号：稳健、主力
        cands = [c for c in raw_cands if _is_relevant(c)] if cls.RELEVANCE_GATE else raw_cands
        kept = len(cands)
        # flat/无方向时按聚合真实情绪定排序方向，避免清一色正面招聘霸榜、负面事件被埋
        eff_dir = direction
        if direction in (None, "flat", "stable") and aggregate:
            net = aggregate.get("net_signal")
            eff_dir = "down" if net == "negative" else "up" if net == "positive" else direction
        events = cls._rank_events(role, cands, top_k, eff_dir) if cands else []  # 干净样本：佐证
        jobs = cls._load_jobs(role, months, top_k)
        weak_count = sum(1 for ev in events if ev.get("evidence_strength") == "weak")
        if events and weak_count:
            note = f"强相关事件不足，补充 {weak_count} 条弱相关事件；趋势佐证以 aggregate/JD 为准"
        elif events:
            note = "事件为代表性样本，相关性近似；趋势佐证以 aggregate 为准"
        elif kept:
            note = f"基础闸门保留 {kept} 条候选，但 TopK 无足够岗位相关证据；以 aggregate/JD 为准"
        elif total and not kept:
            note = f"召回 {total} 条候选全部被四重约束过滤（疑似纯关键词噪音）；以 aggregate 为准"
        else:
            note = "区间内无匹配事件证据"
        return {
            "role": role,
            "months": list(months),
            "direction": direction,
            "aggregate": aggregate,
            "events": events,
            "jobs": jobs,
            "candidates_total": total,
            "candidates_kept": kept,
            "note": note,
        }

    @classmethod
    def _aggregate(cls, cands: list[dict]) -> dict | None:
        """聚合证据信号：多篇噪音文档的统计量稳健，作为趋势佐证的主力。"""
        if not cands:
            return None
        tones = [float(c.get("avg_tone") or 0.0) for c in cands]
        n = len(cands)
        opp = risk = 0
        themes_ct: Counter = Counter()
        domains_ct: Counter = Counter()
        for c, tone in zip(cands, tones):
            th = (c.get("themes") or "").upper()
            is_econ = any(t in th for t in ECON_THEMES)
            if is_econ and tone > 0:
                opp += 1
            elif is_econ and tone < 0:
                risk += 1
            for t in (c.get("themes") or "").split(";"):
                t = t.strip()
                if t and not t.startswith(("TAX_", "UNGP_", "CRISISLEX")):
                    themes_ct[t] += 1
            domains_ct[c.get("source_domain")] += 1
        mean_tone = sum(tones) / n
        return {
            "article_count": n,
            "mean_tone": round(mean_tone, 3),
            "positive_ratio": round(sum(t > 0 for t in tones) / n, 3),
            "opportunity_events": opp,
            "risk_events": risk,
            "net_signal": "positive" if opp > risk else "negative" if risk > opp else "mixed",
            "top_themes": [t for t, _ in themes_ct.most_common(6)],
            "top_domains": [d for d, _ in domains_ct.most_common(5)],
        }

    @classmethod
    def _rank_events(cls, role: str, cands: list[dict], top_k: int,
                     direction: str | None) -> list[dict]:
        # query：角色名 + 别名 + top_skills
        info = cls._taxonomy().get(role, {})
        q = _tok(role)
        for a in info.get("aliases", []) or []:
            q += _tok(a)
        for s in info.get("top_skills", []) or []:
            q += _tok(s)

        corpus = [_tok(" ".join([" ".join(c.get("matched_terms") or []),
                                 c.get("themes", ""), c.get("source_domain", ""),
                                 _title_from_url(c.get("url", ""), c.get("source_domain", ""))]))
                  for c in cands]
        bm25 = BM25(corpus)
        raw = [bm25.score(q, i) for i in range(len(cands))]
        mx = max(raw) if raw else 0.0
        dates = [c.get("event_date") or "" for c in cands]
        dmin, dmax = min(dates), max(dates)

        scored = []
        for i, c in enumerate(cands):
            tone = float(c.get("avg_tone") or 0.0)
            etype = _classify(c.get("themes", ""))
            norm_bm25 = (raw[i] / mx) if mx > 0 else 0.0
            align = cls._direction_align(tone, etype, direction)
            salience = 0.5 * min(abs(tone) / 10.0, 1.0) + 0.5 * min(float(c.get("match_weight") or 0), 1.0)
            recency = ((dates[i] >= dmin) and dmax != dmin and
                       (int(dates[i] or 0) - int(dmin or 0)) / max(int(dmax or 1) - int(dmin or 0), 1)) or 0.0
            title = _title_from_url(c.get("url", ""), c.get("source_domain", ""))
            tq = _title_quality(title, c.get("source_domain", ""))   # 可解释性分
            role_aff = _role_title_affinity(role, info, title)
            composite = (0.25 * norm_bm25 + 0.20 * align + 0.10 * salience
                         + 0.05 * float(recency) + 0.20 * tq + 0.20 * role_aff)
            scored.append((c, composite, etype, tone, align, title, tq, role_aff))

        # 去重：url + 标题近重复
        seen_urls, seen_titles, deduped = set(), set(), []
        for c, sc, etype, tone, align, title, tq, role_aff in sorted(scored, key=lambda x: x[1], reverse=True):
            url = c.get("url")
            if url in seen_urls:
                continue
            tsig = _title_sig(title)
            if tsig and tsig in seen_titles:        # 近重复(同一新闻不同URL/日期) -> 跳过
                continue
            seen_urls.add(url)
            seen_titles.add(tsig)
            impact = "positive" if tone > 1 else "negative" if tone < -1 else "neutral"
            deduped.append((c, sc, etype, tone, align, title, impact, tq, role_aff))

        # 方向优先：与趋势方向一致的极性事件优先填 TopK（up->正面/绿, down->负面/红），
        # 不足再补其他极性。组内仍按复合分排序（稳定排序保持原次序）。
        want = {"up": "positive", "down": "negative"}.get(direction)
        if want:
            deduped.sort(key=lambda it: it[6] != want)
        role_filtered = [it for it in deduped if it[8] >= cls.ROLE_AFFINITY_DISPLAY_MIN]
        if role_filtered:
            picked = role_filtered[:top_k]
            weak_ids: set[str] = set()
        elif _role_anchor_terms(role, info):
            picked = [it for it in deduped if it[7] >= cls.WEAK_TITLE_QUALITY_MIN][:top_k]
            weak_ids = {it[0].get("url") for it in picked}
        else:
            picked = deduped[:top_k]
            weak_ids = set()

        # 诚实：方向单极性时(跌→全红/涨→全绿)，保留 1 条最强反向信号，
        # 避免选择性举证，并给 CoT 权衡材料。
        counter = {"positive": "negative", "negative": "positive"}.get(want)
        if want and top_k >= 3 and picked and all(it[6] != counter for it in picked):
            pool = role_filtered or deduped
            cev = next((it for it in pool if it[6] == counter), None)
            if cev and cev not in picked:
                picked[-1] = cev

        out = []
        for c, sc, etype, tone, align, title, impact, tq, role_aff in picked:
            out.append({
                "evidence_type": "news_event",
                "url": c.get("url"),
                "source_domain": c.get("source_domain"),
                "title": title,
                "published_at": _iso(c.get("event_date")),
                "tone": round(tone, 3),
                "themes": (c.get("themes") or "").split(";")[:6],
                "match_weight": c.get("match_weight"),
                "event_type": etype,
                "impact_direction": impact,
                "is_counter_signal": bool(counter and impact == counter),
                "direction_align": round(align, 3),
                "title_quality": round(tq, 3),
                "role_affinity": round(role_aff, 3),
                "evidence_strength": "weak" if c.get("url") in weak_ids else "strong",
                "retrieval_score": round(float(sc), 4),
            })
        return out


def _iso(yyyymmdd) -> str | None:
    s = str(yyyymmdd or "")
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None
