"""
统一 JD 技能抽取 - B 模块细粒度岗位库输入层

目标:
  1. asaniczka / Djinni / emerging 三源统一过 skill_norm 词表抽技能
  2. 输出统一 JSONL,供后续分层聚类使用
  3. 统计数据源规模、技能覆盖率、方向标签分布和高频未匹配候选词

输出:
  data/silver/all_jd_skills_v1.jsonl
  data/silver/all_jd_skills_stats_v1.json

运行:
  python -m pipelines.extract.extract_all_skills

可选:
  set EMERGING_JD_JSONL=D:\\path\\to\\emerging_it_jd.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.services.skill_norm import match_skills_in_text, normalize_list, normalize_skill_id

ASANICZKA_DIR = Path("data/raw/asaniczka")
DJINNI_CSV = Path("data/raw/djinni/djinni_jd.csv")
OUT_JSONL = Path("data/silver/all_jd_skills_v1.jsonl")
OUT_STATS = Path("data/silver/all_jd_skills_stats_v1.json")

MAX_TEXT_CHARS = 2500
MIN_TEXT_LEN = 40
PROGRESS_EVERY = 10000

EMERGING_CANDIDATES = [
    Path(os.environ["EMERGING_JD_JSONL"]) if os.environ.get("EMERGING_JD_JSONL") else None,
    Path("data/raw/emerging/emerging_it_jd.jsonl"),
    Path("data/raw/emerging_it_jd.jsonl"),
    Path("../../emerging_it_jd.jsonl"),
]

TECH_TOKEN_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9.+#/-]{1,30})(?:\s+[A-Za-z][A-Za-z0-9.+#/-]{1,30}){0,2}\b"
)

GENERIC_UNMATCHED = {
    "about", "ability", "able", "according", "across", "advanced", "also", "and",
    "are", "based", "benefits", "best", "business", "candidate", "career", "client",
    "collaborate", "communication", "company", "competitive", "customer", "design",
    "develop", "development", "english", "environment", "experience", "good", "great",
    "high", "including", "join", "knowledge", "looking", "management", "more", "new",
    "opportunity", "people", "product", "project", "requirements", "responsibilities",
    "role", "salary", "skills", "software", "strong", "team", "technical", "technology",
    "the", "their", "this", "using", "with", "work", "working", "years", "you", "your",
}


def _clean_text(text: object) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:MAX_TEXT_CHARS]


def _split_skills(raw: object) -> list[str]:
    if raw is None or pd.isna(raw):
        return []
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _stable_id(source: str, *parts: object) -> str:
    payload = "|".join(str(p or "") for p in parts)
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]
    return f"{source}_{digest}"


def _merge_skills(*skill_lists: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for skills in skill_lists:
        for skill in skills:
            if skill not in seen:
                seen.add(skill)
                out.append(skill)
    return out


def _record(
    *,
    source: str,
    source_id: object,
    title: object,
    text: object,
    search_keyword: object = None,
    raw_skills: object = None,
) -> dict:
    title_text = _clean_text(title)
    body_text = _clean_text(text)
    combined = f"{title_text}. {body_text}"
    normalized_raw = normalize_list(_split_skills(raw_skills))
    matched_text = match_skills_in_text(combined)
    skills = _merge_skills(normalized_raw, matched_text)
    skill_ids = [normalize_skill_id(skill) for skill in skills]

    return {
        "source": source,
        "id": str(source_id or _stable_id(source, title_text, body_text)),
        "title": title_text,
        "text": body_text,
        "skills": skills,
        "skill_ids": skill_ids,
        "skill_count": len(skills),
        "search_keyword": None if search_keyword is None or pd.isna(search_keyword) else str(search_keyword),
    }


def load_asaniczka() -> list[dict]:
    postings = pd.read_csv(ASANICZKA_DIR / "job_postings.csv")
    summary = pd.read_csv(ASANICZKA_DIR / "job_summary.csv")
    skills = pd.read_csv(ASANICZKA_DIR / "job_skills.csv")

    df = postings.merge(summary, on="job_link", how="inner")
    df = df.merge(skills, on="job_link", how="left")
    df = df.dropna(subset=["job_summary"])
    df = df[df["job_summary"].astype(str).str.len() >= MIN_TEXT_LEN]

    records = []
    total = len(df)
    for pos, row in enumerate(df.itertuples(index=False), start=1):
        records.append(
            _record(
                source="asaniczka",
                source_id=getattr(row, "job_link"),
                title=getattr(row, "job_title"),
                text=getattr(row, "job_summary"),
                search_keyword=getattr(row, "search_position", None),
                raw_skills=getattr(row, "job_skills", None),
            )
        )
        if pos % PROGRESS_EVERY == 0:
            print(f"    asaniczka 进度: {pos}/{total} ({pos / total:.1%})")
    return records


def load_djinni() -> list[dict]:
    usecols = ["id", "Position", "Long Description", "Primary Keyword"]
    df = pd.read_csv(DJINNI_CSV, usecols=usecols)
    df = df.dropna(subset=["Long Description"])
    df = df[df["Long Description"].astype(str).str.len() >= MIN_TEXT_LEN]

    records = []
    total = len(df)
    for pos, row in enumerate(df.itertuples(index=False), start=1):
        records.append(
            _record(
                source="djinni",
                source_id=getattr(row, "id"),
                title=getattr(row, "Position"),
                text=getattr(row, "_1"),  # "Long Description" is renamed by itertuples
                search_keyword=getattr(row, "_2"),
            )
        )
        if pos % PROGRESS_EVERY == 0:
            print(f"    Djinni 进度: {pos}/{total} ({pos / total:.1%})")
    return records


def find_emerging_path() -> Path | None:
    for path in EMERGING_CANDIDATES:
        if path and path.exists():
            return path
    return None


def load_emerging() -> list[dict]:
    path = find_emerging_path()
    if not path:
        print("    未找到 emerging_it_jd.jsonl,跳过 emerging 数据源")
        return []

    records = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            text = item.get("description") or item.get("text") or ""
            if len(str(text)) < MIN_TEXT_LEN:
                continue
            source_id = item.get("id") or item.get("url") or item.get("redirect_url") or line_no
            records.append(
                _record(
                    source="emerging",
                    source_id=source_id,
                    title=item.get("title", ""),
                    text=text,
                    search_keyword=item.get("search_keyword"),
                )
            )
            if len(records) % PROGRESS_EVERY == 0:
                print(f"    emerging 进度: {len(records)}")
    print(f"    emerging 文件: {path}")
    return records


def collect_unmatched_terms(records: list[dict], top_n: int = 100) -> list[dict]:
    matched = {skill.lower() for r in records for skill in r["skills"]}
    counter = Counter()

    for r in records:
        text = f"{r['title']} {r['text']}"
        for token in TECH_TOKEN_RE.findall(text):
            key = re.sub(r"\s+", " ", token.strip(" .,*-").lower())
            if len(key) < 3 or key in matched or key in GENERIC_UNMATCHED:
                continue
            if key.isdigit():
                continue
            counter[key] += 1

    return [{"term": term, "count": count} for term, count in counter.most_common(top_n)]


def build_stats(records: list[dict]) -> dict:
    by_source = defaultdict(lambda: {"total": 0, "with_skills": 0, "skill_mentions": 0})
    keyword_counter = Counter()
    skill_counter = Counter()

    for r in records:
        stat = by_source[r["source"]]
        stat["total"] += 1
        stat["skill_mentions"] += r["skill_count"]
        if r["skill_count"] > 0:
            stat["with_skills"] += 1
        if r.get("search_keyword"):
            keyword_counter[(r["source"], r["search_keyword"])] += 1
        skill_counter.update(r["skills"])

    source_stats = {}
    for source, stat in by_source.items():
        total = stat["total"]
        source_stats[source] = {
            **stat,
            "coverage": round(stat["with_skills"] / total, 4) if total else 0,
            "avg_skill_count": round(stat["skill_mentions"] / total, 2) if total else 0,
        }

    keyword_distribution = [
        {"source": source, "search_keyword": keyword, "count": count}
        for (source, keyword), count in keyword_counter.most_common(200)
    ]

    return {
        "total_records": len(records),
        "by_source": source_stats,
        "top_skills": [{"skill": skill, "count": count} for skill, count in skill_counter.most_common(100)],
        "search_keyword_distribution": keyword_distribution,
        "high_freq_unmatched_terms": collect_unmatched_terms(records),
    }


def write_jsonl(records: list[dict]) -> None:
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    print(">>> 1/5 抽取 asaniczka 技能 ...")
    asaniczka = load_asaniczka()
    print(f"    asaniczka: {len(asaniczka)}")

    print(">>> 2/5 抽取 Djinni 技能 ...")
    djinni = load_djinni()
    print(f"    djinni: {len(djinni)}")

    print(">>> 3/5 抽取 emerging 技能 ...")
    emerging = load_emerging()
    print(f"    emerging: {len(emerging)}")

    print(">>> 4/5 写出统一 JSONL ...")
    records = asaniczka + djinni + emerging
    write_jsonl(records)
    print(f"    已写出: {OUT_JSONL}")

    print(">>> 5/5 写出统计 ...")
    stats = build_stats(records)
    with OUT_STATS.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"    已写出: {OUT_STATS}")
    print(json.dumps(stats["by_source"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
