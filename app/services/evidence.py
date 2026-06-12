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
)


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


def _is_relevant(c: dict) -> bool:
    """四重约束：黑名单域名直接丢；明确技能词放行；歧义技能词需 科技∧经济 主题共现。"""
    if _is_junk_domain(c.get("source_domain")):
        return False
    terms = [str(t).lower() for t in (c.get("matched_terms") or [])]
    if not terms:
        return False
    if _strong_skill_terms(terms):
        return True
    amb_skill = [t for t in terms if t in _SKILL_VOCAB and t in AMBIGUOUS_TERMS]
    if amb_skill:
        themes = (c.get("themes") or "").upper()
        if any(t in themes for t in TECH_THEMES) and any(t in themes for t in ECON_THEMES):
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
        events = cls._rank_events(role, cands, top_k, direction) if cands else []  # 干净样本：佐证
        jobs = cls._load_jobs(role, months, top_k)
        if events:
            note = "事件为代表性样本，相关性近似；趋势佐证以 aggregate 为准"
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
                                 c.get("themes", ""), c.get("source_domain", "")]))
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
            composite = 0.4 * norm_bm25 + 0.3 * align + 0.2 * salience + 0.1 * float(recency)
            scored.append((c, composite, etype, tone, align))

        seen, out = set(), []
        for c, sc, etype, tone, align in sorted(scored, key=lambda x: x[1], reverse=True):
            url = c.get("url")
            if url in seen:
                continue
            seen.add(url)
            impact = "positive" if tone > 1 else "negative" if tone < -1 else "neutral"
            out.append({
                "evidence_type": "news_event",
                "url": url,
                "source_domain": c.get("source_domain"),
                "title": _title_from_url(url, c.get("source_domain", "")),
                "published_at": _iso(c.get("event_date")),
                "tone": round(tone, 3),
                "themes": (c.get("themes") or "").split(";")[:6],
                "match_weight": c.get("match_weight"),
                "event_type": etype,
                "impact_direction": impact,
                "direction_align": round(align, 3),
                "retrieval_score": round(float(sc), 4),
            })
            if len(out) >= top_k:
                break
        return out


def _iso(yyyymmdd) -> str | None:
    s = str(yyyymmdd or "")
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None
