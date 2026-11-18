# -*- coding: utf-8 -*-
"""collect_learning_resources_v5.py — 学习资源库 v5 第二轮扩充管道。

在 learning_resources_v4 基础上增量升级（不修改 v4 文件）：
  1. 章节结构：读取 collect_course_chapters.py 产出的
     /data/shichaojian/JNIT/raw/courses/<source>/chapters/*.json，
     为系列课程资源附加 chapters 列表（course->chapter_no/title/url）。
  2. 新源：GitHub 实战项目合集（project-based-learning / build-your-own-x /
     realworld）、云厂商官方认证学习路径、免费合法在线书籍、
     hot_without_zh 技能中文资源定向补充。
  3. 质量：v4 全部资源链接重检（_linkcheck_v5.py 产出），失效剔除并记录；
     新源收录前同样逐一验证。
  4. 输出：v4 schema + chapters / last_verified_at / link_status，
     data/gold/learning_resources_v5.json + learning_resources_v5_qc.json。

用法：
    /var/lib/jobnav-env/bin/python pipelines/report/collect_learning_resources_v5.py
    # 跳过新源链接验证（离线幂等重跑，复用缓存）：
    ... collect_learning_resources_v5.py --no-linkcheck
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_learning_resources_v4 import (  # noqa: E402
    SOURCE_AUTHORITY,
    Vocab,
    freshness_score,
    quality_score,
)
from learning_resources_v4_curated import FCC_SKILL_OVERRIDES  # noqa: E402
from learning_resources_v5_curated import (  # noqa: E402
    CERT_PATHS,
    FREE_BOOKS,
    MISC_FREE,
    OPEN_SOURCE_COLLECTIONS,
    PROJECT_REPOS,
    UNIVERSITY_COURSES,
    ZH_HOT_SUPPLEMENT,
)

log = logging.getLogger("collect_lr_v5")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VOCAB_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "skill_vocab_v2.json")
V4_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v4.json")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v5.json")
QC_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v5_qc.json")
V4_QC_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v4_qc.json")

RAW_BASE = "/data/shichaojian/JNIT/raw/courses"
LINKCHECK_CACHE_V5 = os.path.join(RAW_BASE, "_linkcheck", "link_status_v5.json")
LINKCHECK_CACHE_V4 = os.path.join(RAW_BASE, "_linkcheck", "link_status.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HTTP_TIMEOUT = 25
LINK_WORKERS = 8
MIN_TOTAL_TARGET = 2000

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
FETCH_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")

# v5 新增源的权威性基线（quality_score 来源维度输入）
V5_SOURCE_AUTHORITY = {
    "odin_course": 0.93,
    "cs50_course": 0.95,
    "d2l_course": 0.93,
    "liaoxuefeng_course": 0.80,
    "runoob_course": 0.72,
    "mdn_course": 0.98,
    "freecodecamp_cert": 0.93,
    "github_project": 0.90,
    "cert_path": 0.90,
    "free_book": 0.90,
    "zh_hot": 0.78,
}

# 章节课程 -> 技能映射（章节标题词表匹配之外的精确覆盖）
COURSE_SKILL_MAP = {
    "theodinproject": {
        "foundations": ["html", "css", "javascript", "git", "html-css"],
        "intermediate-html-and-css": ["html", "css"],
        "advanced-html-and-css": ["html", "css"],
        "javascript": ["javascript"],
        "nodejs": ["nodejs", "express", "api-design"],
        "react": ["react", "javascript"],
        "databases": ["sql-lang", "postgresql"],
        "ruby": ["ruby"],
        "ruby-on-rails": ["ruby", "rails"],
        "getting-hired": [],
    },
    "cs50": {
        "x": ["c", "python", "sql-lang", "data-structures", "algorithms"],
        "python": ["python"],
        "sql": ["sql-lang"],
        "web": ["javascript", "python", "html", "css", "sql-lang", "django",
                "react"],
        "r": ["r"],
        "ai": ["machine-learning", "python"],
        "cybersecurity": ["cybersecurity"],
        "games": ["csharp"],
        "business": [],
        "law": [],
        "technology": [],
    },
    "d2l": {"__all__": ["machine-learning", "deep-learning", "pytorch"]},
    "mdn": {"__all__": ["html", "css", "javascript", "html-css"]},
    "liaoxuefeng": {
        "python": ["python"],
        "git": ["git"],
        "javascript": ["javascript"],
        "java": ["java"],
        "sql": ["sql-lang"],
        "blockchain": ["blockchain"],
        "makefile": ["linux"],
        "summerframework": ["spring"],
        "jerrymouse": ["java"],
    },
    "runoob": "__from_tutorial_dict__",
}

MDN_MODULE_SKILLS = {
    "Getting started": ["html", "css", "html-css"],
    "Structuring content with HTML": ["html"],
    "CSS styling basics": ["css"],
    "CSS text styling": ["css"],
    "CSS layout": ["css"],
    "Dynamic scripting with JavaScript": ["javascript"],
    "JavaScript frameworks and libraries": ["react", "javascript"],
    "Accessibility": ["css", "javascript"],
    "Design for developers": ["ui-ux", "css"],
    "Version control": ["git"],
    "Advanced JavaScript objects": ["javascript"],
    "Client-side web APIs": ["javascript"],
    "Asynchronous JavaScript": ["javascript"],
    "Web forms": ["html", "css", "javascript"],
    "Understanding client-side tools": ["webpack", "vite", "javascript"],
    "Server-side websites": ["django", "express", "nodejs"],
    "Web performance": ["performance-tuning"],
    "Testing": ["qa-testing", "qa-automation", "selenium"],
}

# runoob 章节 json 不含技能，反查 collect_course_chapters 的教程表
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_course_chapters import RUNOOB_TUTORIALS  # noqa: E402


def norm_url(u):
    return u.strip().rstrip("/").lower()


# ---------------------------------------------------------------------------
# 链接检查（新源；v4 全量重检由 _linkcheck_v5.py 预先完成）
# ---------------------------------------------------------------------------
def load_linkcheck():
    cache = {}
    for p in (LINKCHECK_CACHE_V4, LINKCHECK_CACHE_V5):
        if os.path.exists(p):
            try:
                cache.update(json.load(open(p, encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
    return cache


def _check_one(url):
    try:
        r = requests.head(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": UA},
                          allow_redirects=True)
        # 部分站点（如 kaggle.com）不支持 HEAD，会返回 404/403，
        # 这些状态码需要 GET 复核才能定论
        if r.status_code in (403, 405, 400, 404):
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": UA},
                             stream=True)
        status = r.status_code
        ok = 200 <= status < 400
        r.close()
    except requests.RequestException:
        ok, status = False, None
    return url, ok, status


def verify_urls(urls, cache, no_linkcheck=False):
    """返回 {url: {"ok","status","checked_at"}}。确定性结果写缓存。"""
    todo = []
    for u in urls:
        if u in cache and (cache[u].get("ok") or cache[u].get("status") in (404, 410)):
            continue
        if u not in cache and no_linkcheck:
            cache[u] = {"ok": True, "status": None, "checked_at": FETCH_TS,
                        "assumed": True}
            continue
        todo.append(u)
    if todo:
        log.info("linkcheck: %d new urls", len(todo))
        done = 0
        with ThreadPoolExecutor(max_workers=LINK_WORKERS) as ex:
            for url, ok, status in ex.map(_check_one, todo):
                done += 1
                if ok or status in (404, 410):
                    cache[url] = {"ok": ok, "status": status,
                                  "checked_at": FETCH_TS}
                else:
                    # transient：不缓存，标 unknown
                    cache.setdefault(url, {"ok": None, "status": status,
                                           "checked_at": FETCH_TS})
                if done % 50 == 0:
                    log.info("linkcheck %d/%d", done, len(todo))
        save_linkcheck(cache)
    return cache


def save_linkcheck(cache):
    os.makedirs(os.path.dirname(LINKCHECK_CACHE_V5), exist_ok=True)
    with open(LINKCHECK_CACHE_V5, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def link_status_of(url, cache):
    rec = cache.get(url)
    if not rec:
        return "unknown", None
    if rec.get("ok"):
        return "alive", rec.get("checked_at")
    if rec.get("status") in (404, 410) or rec.get("ok") is False:
        return "dead", rec.get("checked_at")
    return "unknown", rec.get("checked_at")


# ---------------------------------------------------------------------------
# 资源构造（沿用 v4 字段 + v5 扩展字段）
# ---------------------------------------------------------------------------
def make_v5_resource(url, title, source, language, rtype, level=None,
                     is_free=None, rating=None, community=None,
                     community_kind=None, updated_at=None, duration_hours=None,
                     skill_ids=None, alignment=0.8, authority=None, note=None,
                     chapters=None):
    res = {
        "url": url.strip(),
        "title": (title or "").strip(),
        "source": source,
        "language": language,
        "type": rtype,
        "level": level,
        "is_free": is_free,
        "rating": rating,
        "community_signal": community,
        "community_kind": community_kind,
        "updated_at": updated_at,
        "duration_hours": duration_hours,
        "skill_ids": sorted(set(skill_ids or [])),
        "alignment": alignment,
        "authority": authority if authority is not None
        else V5_SOURCE_AUTHORITY.get(source, SOURCE_AUTHORITY.get(source, 0.6)),
        "note": note,
        # ---- v5 扩展 ----
        "chapters": chapters or None,
        "last_verified_at": None,
        "link_status": "unknown",
    }
    res["quality_score"] = round(quality_score(res), 4)
    return res


def attach_link_info(res, cache):
    st, at = link_status_of(res["url"], cache)
    res["link_status"] = st
    res["last_verified_at"] = at
    return res


def valid_skills(skill_ids, vocab):
    return [s for s in skill_ids or [] if s in vocab.by_id]


# ---------------------------------------------------------------------------
# 1. v4 载入 + 链接重检结论
# ---------------------------------------------------------------------------
def load_v4_resources(cache):
    data = json.load(open(V4_PATH, encoding="utf-8"))
    kept, dropped = [], []
    for r in data["resources"]:
        res = dict(r)
        res["chapters"] = None
        attach_link_info(res, cache)
        if res["link_status"] == "dead":
            dropped.append(res)
        else:
            res["quality_score"] = round(quality_score(res), 4)
            kept.append(res)
    log.info("v4: kept %d, dead-dropped %d", len(kept), len(dropped))
    return kept, dropped


# ---------------------------------------------------------------------------
# 2. 章节课程 -> 资源
# ---------------------------------------------------------------------------
CHAPTER_SOURCES = {
    "theodinproject": ("odin_course", "course", "en", 0.93),
    "cs50": ("cs50_course", "course", "en", 0.95),
    "d2l": ("d2l_course", "book", None, 0.93),
    "liaoxuefeng": ("liaoxuefeng_course", "tutorial", "zh", 0.80),
    "runoob": ("runoob_course", "tutorial", "zh", 0.72),
    "mdn": ("mdn_course", "doc", None, 0.98),
    "freecodecamp": ("freecodecamp_cert", "course", "en", 0.93),
}


def course_skills(source, course, vocab):
    mapping = COURSE_SKILL_MAP.get(source, {})
    if mapping == "__from_tutorial_dict__":
        rev = {norm_url(u): [sk] for sk, u in RUNOOB_TUTORIALS.items()}
        return rev.get(norm_url(course["url"]), [])
    if "__all__" in mapping:
        return mapping["__all__"]
    if source == "freecodecamp":
        sb = course["url"].rstrip("/").split("/learn/")[-1]
        sb2 = sb.split("/")[-1]
        for cand in (sb2, sb2.removesuffix("-v9"), sb2.removesuffix("-v8")):
            if cand in FCC_SKILL_OVERRIDES:
                return list(FCC_SKILL_OVERRIDES[cand])
            if cand in FCC_EXTRA_SKILLS:
                return list(FCC_EXTRA_SKILLS[cand])
        return []
    if source == "liaoxuefeng":
        key = course["url"].split("/books/")[-1].split("/")[0]
    elif source == "cs50":
        key = course["url"].rstrip("/").rsplit("/", 1)[-1]
    else:
        key = course["url"].rstrip("/").rsplit("/", 1)[-1]
    if key in mapping:
        return mapping[key]
    return vocab.match(course["course"])


# freeCodeCamp 非认证但有技能价值的免费课程（v4 未覆盖）
FCC_EXTRA_SKILLS = {
    "coding-interview-prep": ["algorithms", "data-structures"],
    "project-euler": ["algorithms", "python"],
    "the-odin-project": ["html", "css", "javascript", "html-css"],
    "rosetta-code": ["programming-languages", "algorithms"],
    "python-for-everybody": ["python"],
    "full-stack-open": ["javascript", "react", "nodejs", "mongodb"],
    "learn-rag-mcp-fundamentals": ["rag", "mcp", "llm"],
    "introduction-to-git-and-github": ["git", "github-actions"],
    "introduction-to-sql-and-postgresql": ["sql-lang", "postgresql"],
    "learn-bash-scripting": ["shell", "linux"],
    "front-end-development": ["html", "css", "javascript"],
    "design-for-developers": ["ui-ux", "css"],
    "algorithms-and-data-structures": ["algorithms", "data-structures"],
    "python-programming-fundamentals": ["python"],
    "learn-python-for-beginners": ["python"],
    "learn-javascript-debugging": ["javascript", "devtools"],
    "learn-dom-manipulation-and-events-with-javascript": ["javascript", "dom"],
    "introduction-to-asynchronous-javascript": ["javascript"],
    "learn-data-visualization-with-d3": ["data-visualization", "javascript"],
    "introduction-to-algorithms-and-data-structures": ["algorithms",
                                                       "data-structures"],
    "learn-sql-and-bash": ["sql-lang", "shell"],
    "learn-oop-with-python": ["python", "oop"],
    "introduction-to-python-basics": ["python"],
    "learn-python-loops-and-sequences": ["python"],
    "learn-python-dictionaries-and-sets": ["python"],
    "learn-python-classes-and-objects": ["python", "oop"],
    "introduction-to-linear-data-structures-in-python": ["python",
                                                         "data-structures"],
    "learn-algorithms-in-python": ["python", "algorithms"],
    "learn-graphs-and-trees-in-python": ["python", "data-structures"],
    "learn-dynamic-programming-in-python": ["python", "algorithms"],
    "learn-error-handling-in-python": ["python"],
    "introduction-to-variables-and-strings-in-javascript": ["javascript"],
    "introduction-to-arrays-in-javascript": ["javascript", "data-structures"],
    "introduction-to-objects-in-javascript": ["javascript", "oop"],
    "introduction-to-loops-in-javascript": ["javascript"],
    "javascript-fundamentals-review": ["javascript"],
    "introduction-to-higher-order-functions-and-callbacks": ["javascript"],
    "learn-recursion-with-javascript": ["javascript", "algorithms"],
    "introduction-to-javascript-classes": ["javascript", "oop"],
    "introduction-to-functional-programming-in-javascript": ["javascript"],
    "introduction-to-maps-and-sets-in-javascript": ["javascript",
                                                    "data-structures"],
    "learn-localstorage-and-crud-operations-with-javascript": ["javascript"],
    "learn-basic-regex-with-javascript": ["regex", "javascript"],
    "introduction-to-dates-in-javascript": ["javascript"],
    "basic-html": ["html"],
    "semantic-html": ["html"],
    "html-forms-and-tables": ["html"],
    "html-and-accessibility": ["html"],
    "basic-css": ["css"],
    "css-box-model": ["css"],
    "css-flexbox": ["css"],
    "css-grid": ["css"],
    "css-animations": ["css"],
    "css-positioning": ["css"],
    "responsive-design": ["css"],
    "css-variables": ["css"],
    "styling-forms": ["css"],
    "css-colors": ["css"],
    "css-typography": ["css"],
    "pseudo-classes-and-elements": ["css"],
    "absolute-and-relative-units": ["css"],
    "attribute-selectors": ["css"],
    "design-for-developers-v9": ["ui-ux", "css"],
    "computer-basics": [],
    "introduction-to-bash": ["shell"],
    "introduction-to-sql-and-postgresql": ["sql-lang", "postgresql"],
    "learn-bash-scripting": ["shell", "linux"],
    "introduction-to-git-and-github": ["git", "github-actions"],
}


def collect_chapter_courses(vocab, cache):
    resources = []
    per_source = {}
    for source, (bucket, rtype, lang_default, _auth) in CHAPTER_SOURCES.items():
        p = os.path.join(RAW_BASE, source, "chapters", f"{source}.json")
        if not os.path.exists(p):
            log.warning("chapters json missing for %s", source)
            continue
        data = json.load(open(p, encoding="utf-8"))
        n = 0
        for c in data.get("courses", []):
            skills = valid_skills(course_skills(source, c, vocab), vocab)
            if not skills:
                continue  # 无技能归属的课程不进资源库
            if source == "freecodecamp":
                # 只收认证课程（FCC_SKILL_OVERRIDES）与精选免费课程
                # （FCC_EXTRA_SKILLS），映射由 course_skills 完成
                if not skills:
                    continue
            chapters = [{"no": ch["no"], "title": ch["title"], "url": ch["url"]}
                        for ch in c["chapters"]]
            res = make_v5_resource(
                c["url"], c["course"], bucket, c.get("language") or lang_default,
                rtype, level=None, is_free=True, updated_at=TODAY,
                skill_ids=skills, alignment=1.0,
                chapters=chapters,
                note=f"章节结构化课程（{len(chapters)} 章，"
                     f"源快照 {data.get('generated_at', '')[:10]}）",
            )
            attach_link_info(res, cache)
            if res["link_status"] == "dead":
                log.warning("chapter course dead, skipped: %s", res["url"])
                continue
            resources.append(res)
            n += 1
            if source == "mdn":
                # MDN 每个学习模块同时作为独立资源（技能映射更精确）
                for ch in c["chapters"]:
                    mskills = valid_skills(MDN_MODULE_SKILLS.get(ch["title"], []),
                                           vocab)
                    if not mskills:
                        continue
                    mres = make_v5_resource(
                        ch["url"], f"MDN Learn：{ch['title']}", bucket,
                        c.get("language") or lang_default, "doc",
                        level="beginner", is_free=True, updated_at=TODAY,
                        skill_ids=mskills, alignment=1.0,
                        note="MDN Learn web development 模块")
                    attach_link_info(mres, cache)
                    if mres["link_status"] != "dead":
                        resources.append(mres)
        per_source[source] = n
    log.info("chapter courses: %s", per_source)
    return resources, per_source


# ---------------------------------------------------------------------------
# 3. GitHub 实战项目合集（README 解析）
# ---------------------------------------------------------------------------
def parse_project_repos(vocab):
    pool = []
    for cfg in PROJECT_REPOS:
        if cfg.get("single"):
            skills = valid_skills(cfg.get("skill_ids"), vocab)
            if skills:
                pool.append(make_v5_resource(
                    f"https://github.com/{cfg['repo']}", cfg["single_title"],
                    cfg["bucket"], cfg.get("language", "en"), "project",
                    level=cfg.get("level"), is_free=cfg.get("is_free", True),
                    updated_at=TODAY, skill_ids=skills, alignment=1.0,
                    community=0.95, community_kind="repo_stars",
                    note=f"GitHub {cfg['repo']} 合集入口"))
            continue
        path = cfg["readme"]
        if not os.path.exists(path):
            log.warning("readme missing: %s", path)
            continue
        text = open(path, encoding="utf-8").read()
        # 解析 ## 节 -> 顶层列表项链接
        section, count = None, 0
        for line in text.splitlines():
            m = re.match(r"^##\s+(.+?)\s*:?\s*$", line)
            if m:
                section = m.group(1).strip().lower()
                count = 0
                continue
            if not section:
                continue
            lm = re.match(r"^\s*[-*]\s+\[([^\]]+)\]\((https?://[^)]+)\)", line)
            if not lm:
                continue
            title, url = lm.group(1).strip(), lm.group(2).strip()
            if count >= cfg.get("max_per_section", 8):
                continue
            count += 1
            base = cfg.get("section_skills", {}).get(section, [])
            skills = valid_skills(list(base) + vocab.match(f"{section} {title}"),
                                  vocab)
            if not skills:
                continue
            pool.append(make_v5_resource(
                url, f"[实战] {title}", cfg["bucket"],
                cfg.get("language", "en"), "project", level="intermediate",
                is_free=True, updated_at=TODAY, skill_ids=skills,
                alignment=0.9, community=0.9, community_kind="repo_stars",
                note=f"来自 GitHub {cfg['repo']}#{section}"))
    log.info("github project pool: %d", len(pool))
    return pool


# ---------------------------------------------------------------------------
# 4. curated 新源（认证路径 / 免费书 / 中文定向补充）
# ---------------------------------------------------------------------------
def collect_curated_v5(vocab):
    pool = []
    for e in CERT_PATHS:
        pool.append(make_v5_resource(
            e["url"], e["title"], "cert_path", e["language"], e["type"],
            level=e.get("level"), is_free=e.get("is_free"), updated_at=TODAY,
            skill_ids=valid_skills(e.get("skill_ids"), vocab), alignment=1.0,
            note="官方认证/学习路径"))
    for e in FREE_BOOKS:
        pool.append(make_v5_resource(
            e["url"], e["title"], "free_book", e["language"], e["type"],
            level=e.get("level"), is_free=e.get("is_free", True),
            updated_at=TODAY,
            skill_ids=valid_skills(e.get("skill_ids"), vocab), alignment=1.0,
            note="免费合法在线书籍/教材"))
    for group, gname in ((UNIVERSITY_COURSES, "高校公开课程"),
                         (OPEN_SOURCE_COLLECTIONS, "知名开源合集"),
                         (MISC_FREE, "权威免费资源")):
        for e in group:
            pool.append(make_v5_resource(
                e["url"], e["title"], "free_book", e["language"], e["type"],
                level=e.get("level"), is_free=e.get("is_free", True),
                updated_at=TODAY,
                skill_ids=valid_skills(e.get("skill_ids"), vocab), alignment=1.0,
                note=gname))
    for skill, entries in ZH_HOT_SUPPLEMENT.items():
        for e in entries:
            pool.append(make_v5_resource(
                e["url"], e["title"], "zh_hot", "zh", e["type"],
                level=e.get("level"), is_free=True, updated_at=TODAY,
                skill_ids=[skill] if skill in vocab.by_id else [],
                alignment=1.0, note="v4 hot_without_zh 中文定向补充"))
    pool = [r for r in pool if r["skill_ids"]]
    log.info("curated v5 pool: %d", len(pool))
    return pool


# ---------------------------------------------------------------------------
# 5. 合并 / QC / 输出
# ---------------------------------------------------------------------------
def build_v5(v4_kept, v4_dropped, new_resources, vocab, stats):
    by_url = {}
    for r in v4_kept:
        by_url.setdefault(norm_url(r["url"]), r)
    dup = 0
    for r in new_resources:
        key = norm_url(r["url"])
        if key in by_url:
            old = by_url[key]
            # 技能并集：同一资源服务多个技能（如 DataWhale 教程同时覆盖
            # fine-tuning 与 huggingface），v4 条目需吸收新源的技能标注
            old["skill_ids"] = sorted(set(old["skill_ids"]) | set(r["skill_ids"]))
            if r.get("chapters") and not old.get("chapters"):
                old["chapters"] = r["chapters"]
                old["note"] = (old.get("note") or "") + \
                    " [v5 附加章节结构]" if old.get("note") else "[v5 附加章节结构]"
            dup += 1
            continue
        by_url[key] = r
    resources = sorted(by_url.values(),
                       key=lambda r: (-r["quality_score"], r["url"]))
    log.info("merged: %d unique (new-source dups merged: %d)",
             len(resources), dup)

    # ---- QC ----
    hot_ids = vocab.hot_ids
    zh_hot = []
    cov = {"covered": 0, "skills_without_resources": []}
    per_skill = {}
    for r in resources:
        for s in r["skill_ids"]:
            per_skill.setdefault(s, []).append(r)
    for s in vocab.skills:
        if s["id"] not in per_skill:
            cov["skills_without_resources"].append(s["id"])
    cov["covered"] = (len(vocab.by_id) - len(cov["skills_without_resources"]))
    cov["vocab_size"] = len(vocab.by_id)
    cov["coverage"] = round(cov["covered"] / max(1, cov["vocab_size"]), 4)

    for s in vocab.skills:
        sid = s["id"]
        if not s.get("hot") or sid not in per_skill:
            continue
        if not any(r["language"] == "zh" for r in per_skill[sid]):
            zh_hot.append(sid)
    lt3 = [s["id"] for s in vocab.skills
           if s.get("hot") and len(per_skill.get(s["id"], [])) < 3]

    by_source = Counter(r["source"] for r in resources)
    by_type = Counter(r["type"] for r in resources)
    by_lang = Counter(r["language"] for r in resources)
    by_link = Counter(r["link_status"] for r in resources)
    n_chaptered = sum(1 for r in resources if r.get("chapters"))

    qc = {
        "version": "v5",
        "generated_at": FETCH_TS,
        "inputs": {
            "v4": V4_PATH,
            "vocab": VOCAB_PATH,
            "chapters_dir": os.path.join(RAW_BASE, "<source>", "chapters"),
            "curated_tables": "pipelines/report/learning_resources_v5_curated.py",
            "linkcheck_cache": LINKCHECK_CACHE_V5,
        },
        "totals": {
            "v4_resources": len(v4_kept) + len(v4_dropped),
            "v4_dead_dropped": len(v4_dropped),
            "v5_resources": len(resources),
            "target_total": MIN_TOTAL_TARGET,
            "target_met": len(resources) >= MIN_TOTAL_TARGET,
            "chapter_structured_courses": n_chaptered,
            "new_source_dups_merged": dup,
        },
        "counts_by_source": dict(by_source.most_common()),
        "distribution": {"language": dict(by_lang),
                         "type": dict(by_type),
                         "link_status": dict(by_link)},
        "new_sources": stats,
        "coverage": cov,
        "hot_skill_quality": {
            "n_hot": len(hot_ids),
            "hot_with_lt3_resources": sorted(lt3),
            "hot_without_zh": sorted(zh_hot),
        },
        "quality_score": {
            "min": min(r["quality_score"] for r in resources),
            "mean": round(sum(r["quality_score"] for r in resources)
                          / len(resources), 4),
        },
        "dead_links_dropped": [
            {"url": r["url"], "title": r["title"], "source": r["source"],
             "status": r["link_status"], "checked_at": r["last_verified_at"]}
            for r in v4_dropped
        ],
    }
    schema = {
        "skill_ids": "关联 skill_vocab_v2.json 的技能 id 列表（已过滤词表外 id）",
        "title": "资源标题", "url": "落地链接",
        "source": "来源桶（v4 桶 + odin_course/cs50_course/d2l_course/"
                  "liaoxuefeng_course/runoob_course/mdn_course/"
                  "freecodecamp_cert/github_project/cert_path/free_book/zh_hot）",
        "language": "zh/en", "type": "同 v4",
        "chapters": "可选：章节结构 [{no,title,url}]，供学习路径算法推断顺序",
        "last_verified_at": "最近一次链接可达性验证时间 ISO",
        "link_status": "alive / dead / unknown（dead 已剔除，unknown=检查时被限流或超时）",
    }
    out = {"version": "v5", "generated_at": FETCH_TS, "schema": schema,
           "quality_weights": {"source_authority": 0.3, "community_signal": 0.2,
                               "freshness": 0.15, "hands_on": 0.15,
                               "free_access": 0.1, "vocab_alignment": 0.1},
           "resources": resources}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(QC_PATH, "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=1)
    log.info("v5: %d resources -> %s", len(resources), OUT_PATH)
    log.info("coverage %.4f, chapter-structured %d, dead dropped %d, QC -> %s",
             qc["coverage"]["coverage"], n_chaptered, len(v4_dropped), QC_PATH)
    return out, qc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-linkcheck", action="store_true",
                    help="跳过新源链接验证，复用缓存（离线幂等重跑）")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    vocab = Vocab(VOCAB_PATH)
    cache = load_linkcheck()

    v4_kept, v4_dropped = load_v4_resources(cache)

    chapter_res, chapter_stats = collect_chapter_courses(vocab, cache)

    repo_pool = parse_project_repos(vocab)
    curated_pool = collect_curated_v5(vocab)
    new_pool = chapter_res + repo_pool + curated_pool

    # 链接验证：新源全部 URL（含章节内章节链接抽检——只验证课程落地页，
    # 章节链接来自源站目录解析，信任源结构；oddn 章节 URL 已抽样 200）
    if not args.no_linkcheck:
        verify_urls([r["url"] for r in new_pool], cache)
        save_linkcheck(cache)

    alive_new, dead_new = [], []
    for r in new_pool:
        attach_link_info(r, cache)
        (dead_new if r["link_status"] == "dead" else alive_new).append(r)
    log.info("new sources: alive %d, dead-dropped %d", len(alive_new),
             len(dead_new))

    stats = {
        "chapter_courses": chapter_stats,
        "chapter_courses_total": len(chapter_res),
        "github_project_pool": len(repo_pool),
        "curated_v5_pool": len(curated_pool),
        "new_dead_dropped": [
            {"url": r["url"], "title": r["title"], "source": r["source"]}
            for r in dead_new
        ],
    }
    build_v5(v4_kept, v4_dropped, alive_new, vocab, stats)


if __name__ == "__main__":
    main()
