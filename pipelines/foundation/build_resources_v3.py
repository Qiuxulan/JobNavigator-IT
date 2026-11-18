"""build_resources_v3: 学习资源库重建.

用真实、结构化、带质量分的资源替换 v1/v2 中的大量占位链接：

1. Coursera 2024 课程集（6645 门）—— Skills 列归一化走 alias_to_id 直配；
   Skills 为空的用 title+Description 关键词（词边界）回退，一门课最多 3 个技能；
   质量分 = rating(40%) + log(num_reviews)(30%) + log(enrolled)(30%) 分量归一化；
2. roadmap.sh 中间产物 —— 优先读
   ``/data/shichaojian/JNIT/processed/roadmap_skill_resources.json``，
   缺省回落到解析 raw 仓库 content MD 里的 @course@/@video@/@official@/@article@ 链接；
3. freeCodeCamp 固定认证条目（质量分 0.85）；
4. 继承 v1/v2 中的真实 github 资源（按 url 去重）。

产出：
- ``data/gold/learning_resources_v3.json`` —— resources 按技能分组，quality_score 降序封顶 8 条；
- ``data/gold/learning_resources_v3_qc.json`` —— 覆盖率 / provider 分布 / Coursera 匹配率 /
  python/react/kubernetes/rag/docker 抽查 / url 与 resource_id 断言。

入口: ``python -m pipelines.foundation.build_resources_v3`` （幂等，重复运行覆盖输出）.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = ROOT / "data/gold/skill_vocab_v2.json"
V1_PATH = ROOT / "data/gold/learning_resources_v1.json"
V2_PATH = ROOT / "data/gold/learning_resources_v2.json"
OUT_PATH = ROOT / "data/gold/learning_resources_v3.json"
QC_PATH = ROOT / "data/gold/learning_resources_v3_qc.json"

COURSERA_CSV = Path("/data/shichaojian/JNIT/raw/courses/coursera_azrai99/coursera_course_2024.csv")
ROADMAP_PROCESSED = Path("/data/shichaojian/JNIT/processed/roadmap_skill_resources.json")
ROADMAP_RAW_DIR = Path("/data/shichaojian/JNIT/raw/roadmaps/developer-roadmap/roadmaps")

MAX_RESOURCES_PER_SKILL = 8
MAX_SKILLS_PER_COURSE = 3
COVERAGE_TARGET = 0.85

# roadmap / github 资源的固定质量分（Coursera/freecodecamp 有明确口径）
PROVIDER_QUALITY = {
    "github": 0.7,
    "roadmap_course": 0.75,
    "roadmap_official": 0.75,
    "roadmap_video": 0.65,
    "roadmap_article": 0.6,
}

LEVEL_MAP = {
    "Beginner level": "beginner",
    "Intermediate level": "intermediate",
    "Advanced level": "advanced",
}

LINK_RE = re.compile(r"\[@(?P<type>\w+)@(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)")
HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*hours?", re.IGNORECASE)
MONTHS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*months?\s*\(\s*at\s*(\d+(?:\.\d+)?)\s*hours?\s*a\s*week",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^https?://")

# freeCodeCamp 固定认证条目: (title, url, difficulty, hours, [skill_id ...])
FREECODECAMP_ITEMS = [
    ("Responsive Web Design Certification",
     "https://www.freecodecamp.org/learn/2022/responsive-web-design/", "beginner", 300,
     ["html-css", "css", "html", "web-development"]),
    ("JavaScript Algorithms and Data Structures Certification",
     "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures/", "beginner", 300,
     ["javascript", "algorithms", "data-structures"]),
    ("Front End Development Libraries Certification",
     "https://www.freecodecamp.org/learn/front-end-development-libraries/", "intermediate", 300,
     ["react", "redux", "bootstrap", "jquery"]),
    ("Data Visualization Certification",
     "https://www.freecodecamp.org/learn/data-visualization-with-d3/", "intermediate", 300,
     ["data-visualization", "d3js", "json"]),
    ("Data Analysis with Python Certification",
     "https://www.freecodecamp.org/learn/data-analysis-with-python/", "intermediate", 300,
     ["data-analysis", "python", "pandas", "numpy"]),
    ("Machine Learning with Python Certification",
     "https://www.freecodecamp.org/learn/machine-learning-with-python/", "advanced", 300,
     ["machine-learning", "python", "tensorflow", "scikit-learn"]),
    ("Scientific Computing with Python Certification",
     "https://www.freecodecamp.org/learn/scientific-computing-with-python/", "beginner", 300,
     ["python"]),
    ("College Algebra with Python Certification",
     "https://www.freecodecamp.org/learn/college-algebra-with-python/", "beginner", 300,
     ["python", "mathematics"]),
    ("Foundational C# with FreeCodeCamp",
     "https://www.freecodecamp.org/learn/foundational-c-sharp-with-microsoft/", "beginner", 300,
     ["csharp", "dotnet"]),
    ("Relational Database Certification",
     "https://www.freecodecamp.org/learn/relational-database/", "intermediate", 300,
     ["sql-lang", "sql", "postgresql", "mysql", "database-fundamentals"]),
    ("Back End Development and APIs Certification",
     "https://www.freecodecamp.org/learn/back-end-development-and-apis/", "intermediate", 300,
     ["nodejs", "express", "mongodb", "rest-api"]),
    ("Quality Assurance Certification",
     "https://www.freecodecamp.org/learn/quality-assurance/", "intermediate", 300,
     ["qa", "qa-automation", "testing", "unit-testing"]),
    ("Information Security Certification",
     "https://www.freecodecamp.org/learn/information-security/", "advanced", 300,
     ["cybersecurity", "information-security", "encryption"]),
    ("Legacy Full Stack Certification",
     "https://www.freecodecamp.org/learn/", "advanced", 1200,
     ["fullstack", "web-development"]),
]

# roadmap 链接类型 -> provider（@roadmap@ 类站内链接跳过）
ROADMAP_TYPE_MAP = {
    "course": "roadmap_course",
    "video": "roadmap_video",
    "official": "roadmap_official",
    "article": "roadmap_article",
}

SAMPLE_SKILLS = ["python", "react", "kubernetes", "rag", "docker"]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_vocab():
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    skills = {s["id"]: s for s in vocab["skills"]}
    # 别名 -> skill_id（小写化索引，同时保留 skill 本名）
    alias_to_id = {}
    for alias, sid in vocab["alias_to_id"].items():
        alias_to_id.setdefault(alias.lower(), sid)
    for sid, s in skills.items():
        alias_to_id.setdefault(s["name"].lower(), sid)
    return skills, alias_to_id


def norm_range(series: pd.Series) -> pd.Series:
    """min-max 归一化到 0-1，缺失填中位数。"""
    lo, hi = series.min(), series.max()
    out = (series - lo) / (hi - lo) if hi > lo else pd.Series(0.5, index=series.index)
    return out.fillna(out.median()).clip(0, 1)


# ---------------------------------------------------------------------------
# Coursera
# ---------------------------------------------------------------------------

def clean_coursera() -> pd.DataFrame:
    df = pd.read_csv(COURSERA_CSV)
    df = df.drop_duplicates(subset=["URL"]).reset_index(drop=True)

    def parse_int(x):
        if not isinstance(x, str):
            return None
        x = x.replace(",", "").strip()
        return int(x) if x.isdigit() else None

    def parse_float(x):
        try:
            v = float(x)
            return v if math.isfinite(v) else None
        except (TypeError, ValueError):
            return None

    df["enrolled_n"] = df["enrolled"].map(parse_int)
    df["rating_f"] = df["rating"].map(parse_float)
    df["reviews_n"] = df["num_reviews"].map(parse_float)
    return df


def parse_schedule_hours(text) -> float | None:
    if not isinstance(text, str):
        return None
    m = MONTHS_RE.search(text)
    if m:
        return round(float(m.group(1)) * 4 * float(m.group(2)), 1)
    m = HOURS_RE.search(text)
    if m:
        return float(m.group(1))
    return None


def build_alias_patterns(skills, alias_to_id):
    """为每个 skill 构造 (skill_id, compiled pattern)，词边界匹配。

    长度 >=3 的别名大小写不敏感；短别名（c/r/go 等）强制大小写敏感避免误命中。
    """
    by_skill = defaultdict(set)
    for alias, sid in alias_to_id.items():
        by_skill[sid].add(alias)
    patterns = {}
    for sid, aliases in by_skill.items():
        parts = []
        for a in sorted(aliases, key=len, reverse=True):
            a = a.strip()
            if len(a) < 2:
                continue
            esc = re.escape(a)
            if len(a) >= 3:
                parts.append(f"(?i:{esc})")
            else:
                parts.append(esc)
        if parts:
            patterns[sid] = re.compile(r"(?<![A-Za-z0-9+#.])(" + "|".join(parts) + r")(?![A-Za-z0-9+#])")
    return patterns


def match_coursera(df, skills, alias_to_id):
    """Coursera 课程 -> 技能。返回 {skill_id: [course rows]} 与匹配统计。"""
    patterns = build_alias_patterns(skills, alias_to_id)
    by_skill = defaultdict(list)
    stat = {"skills_col_hit": 0, "text_fallback": 0, "unmatched": 0}

    for row in df.itertuples():
        matched = []

        # 1) Skills 列直配
        raw_skills = getattr(row, "Skills")
        if isinstance(raw_skills, str) and raw_skills.strip() not in ("", "[]"):
            try:
                entries = ast.literal_eval(raw_skills)
            except (SyntaxError, ValueError):
                entries = []
            for e in entries:
                sid = alias_to_id.get(str(e).strip().lower())
                if sid and sid not in [m for m, _ in matched]:
                    matched.append((sid, "skills_col"))
            if matched:
                stat["skills_col_hit"] += 1

        # 2) title+Description 词边界回退
        if not matched:
            title = str(getattr(row, "title") or "")
            desc = str(getattr(row, "Description") or "")
            scored = []
            for sid, pat in patterns.items():
                t_hits = len(pat.findall(title))
                d_hits = len(pat.findall(desc))
                if t_hits + d_hits > 0:
                    scored.append((t_hits, t_hits + d_hits, sid))
            scored.sort(reverse=True)
            matched = [(sid, "text_fallback") for _, _, sid in scored[:MAX_SKILLS_PER_COURSE]]
            if matched:
                stat["text_fallback"] += 1
            else:
                stat["unmatched"] += 1

        for sid, _how in matched:
            by_skill[sid].append(row)

    return by_skill, stat


def coursera_quality(df: pd.DataFrame) -> pd.Series:
    rating_n = norm_range(df["rating_f"])
    reviews_n = norm_range(df["reviews_n"].map(lambda v: math.log1p(v) if v else None))
    enrolled_n = norm_range(df["enrolled_n"].map(lambda v: math.log1p(v) if v else None))
    return (0.4 * rating_n + 0.3 * reviews_n + 0.3 * enrolled_n).round(4)


def coursera_resources(df, by_skill):
    q = coursera_quality(df)
    q_index = q.to_dict()
    out = defaultdict(list)
    for sid, rows in by_skill.items():
        for row in rows:
            idx = row.Index
            hours = parse_schedule_hours(getattr(row, "Schedule"))
            out[sid].append({
                "resource_id": f"coursera_{idx:05d}",
                "title": str(getattr(row, "title")),
                "provider": "coursera",
                "url": str(getattr(row, "URL")),
                "difficulty": LEVEL_MAP.get(str(getattr(row, "Level")), "beginner"),
                "hours_estimate": hours,
                "language": "en",
                "quality_score": float(q_index.get(idx, 0.5)),
                "source": "coursera",
            })
    return out


# ---------------------------------------------------------------------------
# roadmap.sh
# ---------------------------------------------------------------------------

def node_to_skill(node_name: str, alias_to_id) -> str | None:
    """content 文件名节点名 -> skill_id（'javascript--typescript' 分段尝试）。"""
    name = re.sub(r"@\w+$", "", node_name)
    for part in name.split("--"):
        sid = alias_to_id.get(part.strip().lower())
        if sid:
            return sid
    return None


def url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def load_roadmap_resources(skills, alias_to_id):
    """返回 {skill_id: [{title, provider, url, source}]}, 来源标记。"""
    by_skill = defaultdict(dict)  # sid -> {url: resource}

    def absorb(items, origin):
        for skill_name, resources in items:
            sid = skill_name if skill_name in skills else alias_to_id.get(str(skill_name).strip().lower())
            if not sid:
                continue
            for r in resources:
                url = str(r.get("url", "")).strip()
                provider = ROADMAP_TYPE_MAP.get(str(r.get("type", "")).lower())
                if not url or not provider or not URL_RE.match(url):
                    continue
                title = str(r.get("title", url)).strip() or url
                by_skill[sid].setdefault(url, {
                    "resource_id": f"roadmap_{slug(skill_name)}_{url_hash(url)}",
                    "title": title,
                    "provider": provider,
                    "url": url,
                    "difficulty": None,
                    "hours_estimate": None,
                    "language": "en",
                    "quality_score": PROVIDER_QUALITY[provider],
                    "source": f"roadmap_{origin}",
                })

    if ROADMAP_PROCESSED.exists():
        data = json.loads(ROADMAP_PROCESSED.read_text(encoding="utf-8"))
        pairs = []
        for skill_name, entry in data.items():
            if not skill_name or not isinstance(entry, dict):
                continue
            pairs.append((skill_name, entry.get("links", [])))
        absorb(pairs, "processed")
        origin = "processed"
    else:
        files = list(ROADMAP_RAW_DIR.rglob("*.md"))
        parsed = defaultdict(list)
        for f in files:
            sid = node_to_skill(f.stem, alias_to_id)
            if not sid:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in LINK_RE.finditer(text):
                provider = ROADMAP_TYPE_MAP.get(m.group("type").lower())
                if provider:
                    parsed[sid].append(
                        {"title": m.group("title").strip(), "url": m.group("url").strip(), "type": m.group("type")}
                    )
        absorb(parsed.items(), "raw")
        origin = f"raw({len(files)} md)"

    return {sid: list(urls.values()) for sid, urls in by_skill.items()}, origin


# ---------------------------------------------------------------------------
# freeCodeCamp / github 继承
# ---------------------------------------------------------------------------

def freecodecamp_resources(skills):
    out = defaultdict(list)
    for title, url, difficulty, hours, sids in FREECODECAMP_ITEMS:
        for sid in sids:
            if sid not in skills:
                continue
            out[sid].append({
                "resource_id": f"fcc_{slug(title)[:48]}",
                "title": title,
                "provider": "freecodecamp",
                "url": url,
                "difficulty": difficulty,
                "hours_estimate": float(hours),
                "language": "en",
                "quality_score": 0.85,
                "source": "freecodecamp_curated",
            })
    return out


def inherit_github(skills):
    out = defaultdict(dict)  # sid -> {url: resource}
    for path in (V1_PATH, V2_PATH):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sid, s in (data.get("skills") or {}).items():
            if sid not in skills:
                continue
            for r in s.get("resources", []):
                if r.get("source") != "github":
                    continue
                url = str(r.get("url", "")).strip()
                if not URL_RE.match(url) or url in out[sid]:
                    continue
                out[sid][url] = {
                    "resource_id": r.get("resource_id") or f"github_{slug(sid)}_{url_hash(url)}",
                    "title": r.get("title") or url,
                    "provider": "github",
                    "url": url,
                    "difficulty": r.get("difficulty") or "intermediate",
                    "hours_estimate": r.get("hours_estimate"),
                    "language": r.get("language") or "en",
                    "quality_score": PROVIDER_QUALITY["github"],
                    "source": "inherited_github",
                }
    return {sid: list(v.values()) for sid, v in out.items()}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    skills, alias_to_id = load_vocab()
    print(f"[1/5] 词表: {len(skills)} 技能, {len(alias_to_id)} 别名")

    df = clean_coursera()
    print(f"[2/5] Coursera: {len(df)} 门课程（去重后）")

    by_skill, match_stat = match_coursera(df, skills, alias_to_id)
    coursera = coursera_resources(df, by_skill)
    n_pairs = sum(len(v) for v in coursera.values())
    print(f"      匹配: Skills列命中 {match_stat['skills_col_hit']}, "
          f"文本回退 {match_stat['text_fallback']}, 未匹配 {match_stat['unmatched']}, "
          f"课程-技能对 {n_pairs}")

    roadmap, roadmap_origin = load_roadmap_resources(skills, alias_to_id)
    print(f"[3/5] roadmap.sh ({roadmap_origin}): {sum(len(v) for v in roadmap.values())} 条")

    fcc = freecodecamp_resources(skills)
    github = inherit_github(skills)
    print(f"[4/5] freeCodeCamp: {sum(len(v) for v in fcc.values())} 条; "
          f"继承 github: {sum(len(v) for v in github.values())} 条")

    # 合并、按质量分排序、封顶（同一课程可关联多技能，复用时追加技能后缀保证 id 全局唯一）
    resources = {}
    used_ids = set()
    for sid in skills:
        pool = coursera.get(sid, []) + fcc.get(sid, []) + roadmap.get(sid, []) + github.get(sid, [])
        seen_url, kept = set(), []
        for r in sorted(pool, key=lambda x: -x["quality_score"]):
            if r["url"] in seen_url:
                continue
            rid = r["resource_id"]
            if rid in used_ids:
                rid = f"{rid}__{sid}"
                if rid in used_ids:
                    continue
            r["resource_id"] = rid
            used_ids.add(rid)
            seen_url.add(r["url"])
            kept.append(r)
            if len(kept) >= MAX_RESOURCES_PER_SKILL:
                break
        if kept:
            resources[sid] = kept

    covered = len(resources)
    provider_counts = Counter()
    for rs in resources.values():
        provider_counts.update(r["provider"] for r in rs)
    total_resources = sum(len(v) for v in resources.values())

    out = {
        "version": "v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "skill_count": len(skills),
            "covered_count": covered,
            "coverage": round(covered / len(skills), 4),
            "coverage_target": COVERAGE_TARGET,
            "total_resources": total_resources,
            "max_per_skill": MAX_RESOURCES_PER_SKILL,
            "quality_formula": "0.4*norm(rating)+0.3*norm(log1p(num_reviews))+0.3*norm(log1p(enrolled))",
            "provider_quality_default": PROVIDER_QUALITY,
            "provider_counts": dict(provider_counts.most_common()),
            "coursera_match": match_stat,
            "sources": {
                "coursera": str(COURSERA_CSV),
                "roadmap": roadmap_origin,
                "vocab": str(VOCAB_PATH),
            },
        },
        "resources": resources,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- QC ----------------
    uncovered = sorted(set(skills) - set(resources))
    all_urls = [r["url"] for rs in resources.values() for r in rs]
    all_ids = [r["resource_id"] for rs in resources.values() for r in rs]
    assert all(URL_RE.match(u) for u in all_urls), "存在非法 url"
    assert len(all_ids) == len(set(all_ids)), "resource_id 重复"
    coverage = covered / len(skills)
    assert coverage >= COVERAGE_TARGET, f"覆盖率 {coverage:.2%} < {COVERAGE_TARGET:.0%}"

    qc = {
        "coverage": round(coverage, 4),
        "coverage_target": COVERAGE_TARGET,
        "target_met": coverage >= COVERAGE_TARGET,
        "covered_count": covered,
        "skill_count": len(skills),
        "total_resources": total_resources,
        "uncovered_skills": uncovered,
        "provider_counts": dict(provider_counts.most_common()),
        "coursera_match": {
            **match_stat,
            "skills_col_ratio": round(match_stat["skills_col_hit"] / len(df), 4),
            "text_fallback_ratio": round(match_stat["text_fallback"] / len(df), 4),
        },
        "assertions": {
            "all_urls_http": True,
            "resource_ids_unique": True,
        },
        "samples": {sid: resources.get(sid, [])[:5] for sid in SAMPLE_SKILLS},
    }
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[5/5] 输出: {OUT_PATH.name} 覆盖 {covered}/{len(skills)} ({coverage:.1%}), "
          f"共 {total_resources} 条资源")
    print(f"      provider 分布: {dict(provider_counts.most_common())}")
    print(f"      未覆盖技能 {len(uncovered)} 个: {uncovered}")
    for sid in SAMPLE_SKILLS:
        print(f"      抽查 {sid}:")
        for r in resources.get(sid, [])[:4]:
            print(f"        [{r['provider']:16s}] q={r['quality_score']:.3f} {r['title'][:60]}")


if __name__ == "__main__":
    main()
