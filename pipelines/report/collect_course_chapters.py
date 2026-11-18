# -*- coding: utf-8 -*-
"""collect_course_chapters.py — 系列课程/教程的章节级结构采集。

为学习路径算法 v4 提供 (course, chapter_no, chapter_title, url) 序列，
覆盖 v4 资源库缺失的"课程内部顺序"信息。

源：
  - theodinproject   GitHub 仓库 TheOdinProject/curriculum（本地 tarball）
  - freecodecamp     GitHub 仓库 freeCodeCamp/freeCodeCamp（本地 tarball，
                     curriculum/structure + intro.json + challenges/english）
  - cs50             cs50.harvard.edu 各课首页的 Week 侧边栏
  - d2l              d2l.ai / zh.d2l.ai 首页章节目录（chapter 级）
  - liaoxuefeng      liaoxuefeng.com/books/<book>/ 页面内 TOC 链接
  - runoob           菜鸟教程首页教程列表 -> 各教程页左侧导航
  - mdn              MDN Learn_web_development 侧边栏（模块级）

输出（幂等，可被 v5 主采集器复用）：
  /data/shichaojian/JNIT/raw/courses/<source>/chapters/<source>.json
  结构：{"source": ..., "generated_at": ..., "courses": [
      {"course": 名称, "url": 课程落地页, "language": "zh/en",
       "chapters": [{"no": 1, "title": ..., "url": ...}] }] }

用法：
    /var/lib/jobnav-env/bin/python pipelines/report/collect_course_chapters.py
    ... --no-fetch        # 复用 raw 快照，不访问外网
    ... --only mdn,cs50   # 只跑指定源
"""

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("collect_chapters")

RAW_BASE = "/data/shichaojian/JNIT/raw/courses"
TARBALLS = os.path.join(RAW_BASE, "_tarballs")
ODIN_REPO = os.path.join(TARBALLS, "odin_extract/curriculum-main")
FCC_REPO = os.path.join(TARBALLS, "fcc_extract/freeCodeCamp-main")

HTTP_TIMEOUT = 25
SLEEP_GENERAL = 0.4
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA}

GENERATED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_get(url, snapshot_dir=None, name=None):
    r = requests.get(url, timeout=HTTP_TIMEOUT, headers=HEADERS)
    if r.status_code != 200:
        log.warning("GET %s -> %s", url, r.status_code)
        return None
    if snapshot_dir and name:
        os.makedirs(snapshot_dir, exist_ok=True)
        # HTML 页面统一按 utf-8 落盘（requests 对无 charset 的 text/html
        # 会默认 ISO-8859-1，中文教程页会乱码）
        r.encoding = "utf-8"
        with open(os.path.join(snapshot_dir, name), "w", encoding="utf-8") as f:
            f.write(r.text)
    return r.text


def load_snapshot(snapshot_dir, name):
    p = os.path.join(snapshot_dir, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="ignore") as f:
            return f.read()
    return None


def out_path(source):
    d = os.path.join(RAW_BASE, source, "chapters")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{source}.json")


def save(source, courses, extra=None):
    payload = {"source": source, "generated_at": GENERATED_AT,
               "n_courses": len(courses),
               "n_chapters": sum(len(c["chapters"]) for c in courses),
               "courses": courses}
    if extra:
        payload.update(extra)
    with open(out_path(source), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    log.info("%s: %d courses, %d chapters", source, len(courses),
             payload["n_chapters"])
    return payload


def humanize(name):
    s = re.sub(r"\.md$", "", name)
    s = s.replace("_", " ").strip()
    return s.title() if s.islower() else s


def dashed(title):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s


# ---------------------------------------------------------------------------
# 1. The Odin Project（官网课程页，含节标题与规范 lesson URL）
# ---------------------------------------------------------------------------
ODIN_COURSES = [
    ("/paths/foundations/courses/foundations", "The Odin Project: Foundations"),
    ("/paths/full-stack-javascript/courses/intermediate-html-and-css",
     "The Odin Project: Intermediate HTML and CSS"),
    ("/paths/full-stack-javascript/courses/advanced-html-and-css",
     "The Odin Project: Advanced HTML and CSS"),
    ("/paths/full-stack-javascript/courses/javascript",
     "The Odin Project: JavaScript"),
    ("/paths/full-stack-javascript/courses/nodejs",
     "The Odin Project: NodeJS"),
    ("/paths/full-stack-javascript/courses/react",
     "The Odin Project: React"),
    ("/paths/full-stack-javascript/courses/databases",
     "The Odin Project: Databases"),
    ("/paths/full-stack-javascript/courses/getting-hired",
     "The Odin Project: Getting Hired"),
    ("/paths/full-stack-ruby-on-rails/courses/ruby",
     "The Odin Project: Ruby"),
    ("/paths/full-stack-ruby-on-rails/courses/ruby-on-rails",
     "The Odin Project: Ruby on Rails"),
]


def collect_odin(no_fetch=False):
    courses = []
    snap = os.path.join(RAW_BASE, "theodinproject", "chapters")
    for path, name in ODIN_COURSES:
        slug = path.rstrip("/").split("/")[-1]
        html = None
        if not no_fetch:
            html = http_get(f"https://www.theodinproject.com{path}",
                            snap, f"{slug}.html")
            time.sleep(SLEEP_GENERAL)
        if html is None:
            html = load_snapshot(snap, f"{slug}.html")
        if not html:
            log.warning("odin %s unreachable", path)
            continue
        soup = BeautifulSoup(html, "html.parser")
        chapters, seen = [], set()
        section = None
        # 课程页按 <section> 组织，节标题是 h3/h4 + 内部 lesson 链接
        for sec in soup.select("section"):
            h = sec.find(["h2", "h3", "h4"])
            if h:
                section = h.get_text(" ", strip=True)
            for a in sec.select('a[href^="https://www.theodinproject.com/lessons/"]'):
                url = a["href"].split("?")[0]
                if url in seen:
                    continue
                seen.add(url)
                title = re.sub(r"^Lesson", "", a.get_text(" ", strip=True)).strip()
                chapters.append({"no": len(chapters) + 1, "title": title,
                                 "section": section, "url": url})
        if chapters:
            courses.append({"course": name,
                            "url": f"https://www.theodinproject.com{path}",
                            "language": "en", "chapters": chapters})
        else:
            log.warning("odin %s: no lessons parsed", path)
    return save("theodinproject", courses)


# ---------------------------------------------------------------------------
# 2. freeCodeCamp（本地仓库：intro.json + structure/blocks）
# ---------------------------------------------------------------------------
def collect_freecodecamp(no_fetch=False):
    intro_p = os.path.join(FCC_REPO, "client/i18n/locales/english/intro.json")
    struct_dir = os.path.join(FCC_REPO, "curriculum/structure/blocks")
    if not (os.path.exists(intro_p) and os.path.isdir(struct_dir)):
        log.error("freecodecamp repo files missing")
        return save("freecodecamp", [])
    intro = json.load(open(intro_p, encoding="utf-8"))
    courses = []
    for sb, data in intro.items():
        blocks = (data or {}).get("blocks")
        if not blocks:
            continue
        title = (data or {}).get("title") or humanize(sb)
        chapters = []
        no = 0
        for bname, binfo in blocks.items():
            sp = os.path.join(struct_dir, f"{bname}.json")
            if not os.path.exists(sp):
                continue
            order = json.load(open(sp, encoding="utf-8")).get("challengeOrder") or []
            if not order:
                continue
            no += 1
            btitle = (binfo or {}).get("title") or humanize(bname)
            first = order[0]
            chapters.append({
                "no": no,
                "title": btitle,
                "n_challenges": len(order),
                "url": f"https://www.freecodecamp.org/learn/{sb}/{bname}/",
                "challenges": [
                    {"no": i + 1, "title": c["title"],
                     "url": f"https://www.freecodecamp.org/learn/{sb}/"
                            f"{bname}/{dashed(c['title'])}"}
                    for i, c in enumerate(order)
                ][:50],
            })
        if chapters:
            courses.append({
                "course": f"freeCodeCamp: {title}",
                "url": f"https://www.freecodecamp.org/learn/{sb}/",
                "language": "en",
                "chapters": chapters,
            })
    return save("freecodecamp", courses)


# ---------------------------------------------------------------------------
# 3. CS50 各课周次结构
# ---------------------------------------------------------------------------
CS50_COURSES = {
    "x": "CS50's Introduction to Computer Science",
    "sql": "CS50's Introduction to Databases with SQL",
    "web": "CS50's Web Programming with Python and JavaScript",
    "python": "CS50's Introduction to Programming with Python (legacy page)",
    "r": "CS50's Introduction to Programming with R",
    "ai": "CS50's Introduction to Artificial Intelligence with Python",
    "cybersecurity": "CS50's Introduction to Cybersecurity",
    "business": "CS50's Computer Science for Business Professionals",
    "games": "CS50's Introduction to Game Development",
    "law": "CS50's Computer Science for Lawyers",
    "technology": "CS50's Understanding Technology",
}


def collect_cs50(no_fetch=False):
    snap = os.path.join(RAW_BASE, "cs50", "chapters")
    courses = []
    for slug, title in CS50_COURSES.items():
        home = f"https://cs50.harvard.edu/{slug}/"
        html = None
        if not no_fetch:
            html = http_get(home, snap, f"{slug}_home.html")
            time.sleep(SLEEP_GENERAL)
        if html is None:
            html = load_snapshot(snap, f"{slug}_home.html")
        if not html:
            log.warning("cs50 %s unreachable", slug)
            continue
        soup = BeautifulSoup(html, "html.parser")
        chapters, seen = [], set()
        for a in soup.select("aside a, .sidebar a, nav a"):
            href = a.get("href") or ""
            text = a.get_text(strip=True)
            m = re.match(r"^(weeks/)?(\d+|ai)/?$", href.strip("/").lower().replace("weeks/", ""))
            if not m:
                continue
            key = href.strip("/")
            if key in seen:
                continue
            seen.add(key)
            chapters.append({"no": len(chapters) + 1, "title": text,
                             "url": urljoin(home, href)})
        # cs50 主页的 week 链接都在 aside；找不到时尝试全文兜底
        if not chapters:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.fullmatch(r"weeks/(\d+|ai)/?", href.strip("/")):
                    chapters.append({"no": len(chapters) + 1,
                                     "title": a.get_text(strip=True),
                                     "url": urljoin(home, href)})
        if chapters:
            courses.append({"course": title, "url": home, "language": "en",
                            "chapters": chapters})
        else:
            log.warning("cs50 %s: no week links parsed", slug)
    return save("cs50", courses)


# ---------------------------------------------------------------------------
# 4. Dive into Deep Learning（d2l.ai / zh.d2l.ai，chapter 级）
# ---------------------------------------------------------------------------
def _d2l_one(base, label, language, no_fetch):
    snap = os.path.join(RAW_BASE, "d2l", "chapters")
    html = None
    if not no_fetch:
        html = http_get(base + "/", snap, f"home_{label}.html")
        time.sleep(SLEEP_GENERAL)
    if html is None:
        html = load_snapshot(snap, f"home_{label}.html")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    chapters, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not re.match(r"^\d+\.\s+\S", text):
            continue  # 只要章级（"1. Introduction"），不要 x.y 小节
        href = urljoin(base + "/", a["href"])
        if href in seen:
            continue
        seen.add(href)
        chapters.append({"no": len(chapters) + 1, "title": text, "url": href})
    if not chapters:
        return None
    return {"course": f"Dive into Deep Learning ({label})", "url": base + "/",
            "language": language, "chapters": chapters}


def collect_d2l(no_fetch=False):
    courses = []
    for c in (_d2l_one("https://d2l.ai", "en", "en", no_fetch),
              _d2l_one("https://zh.d2l.ai", "zh", "zh", no_fetch)):
        if c:
            courses.append(c)
    return save("d2l", courses)


# ---------------------------------------------------------------------------
# 5. 廖雪峰教程（liaoxuefeng.com/books/<book>/ TOC）
# ---------------------------------------------------------------------------
LXF_BOOKS = {
    "python": "廖雪峰 Python 教程",
    "git": "廖雪峰 Git 教程",
    "javascript": "廖雪峰 JavaScript 教程",
    "java": "廖雪峰 Java 教程",
    "sql": "廖雪峰 SQL 教程",
    "blockchain": "廖雪峰 区块链教程",
    "makefile": "廖雪峰 Makefile 教程",
    "summerframework": "廖雪峰 手写 Spring",
    "jerrymouse": "廖雪峰 手写 Tomcat",
}


def collect_liaoxuefeng(no_fetch=False):
    snap = os.path.join(RAW_BASE, "liaoxuefeng", "chapters")
    courses = []
    for book, title in LXF_BOOKS.items():
        html = None
        if not no_fetch:
            html = http_get(f"https://liaoxuefeng.com/books/{book}/index.html",
                            snap, f"{book}_index.html")
            # /books/<b>/index.html 是 meta-refresh 跳转壳，跟随到正文页
            if html:
                m = re.search(r"URL='?([^'\">]+)", html, re.IGNORECASE)
                if m:
                    html = http_get(urljoin("https://liaoxuefeng.com", m.group(1)),
                                    snap, f"{book}_index.html")
            time.sleep(SLEEP_GENERAL)
        if html is None:
            html = load_snapshot(snap, f"{book}_index.html")
        if not html:
            log.warning("liaoxuefeng %s unreachable", book)
            continue
        soup = BeautifulSoup(html, "html.parser")
        chapters, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if f"/books/{book}/" not in href:
                continue
            if not re.match(r"^\d+\.", text):
                continue  # 只要章级（"5.Python基础"），不要 x.y 小节
            url = urljoin("https://liaoxuefeng.com", href)
            if url in seen:
                continue
            seen.add(url)
            chapters.append({"no": len(chapters) + 1, "title": text, "url": url})
        if chapters:
            courses.append({"course": title,
                            "url": f"https://liaoxuefeng.com/books/{book}/index.html",
                            "language": "zh", "chapters": chapters})
        else:
            log.warning("liaoxuefeng %s: no chapters parsed", book)
    return save("liaoxuefeng", courses)


# ---------------------------------------------------------------------------
# 6. 菜鸟教程（首页教程目录 -> 各教程页左侧导航）
# ---------------------------------------------------------------------------
# 与技能词表对齐的教程页（v4 首页匹配逻辑的精选版，限制规模）
RUNOOB_TUTORIALS = {
    "html": "https://www.runoob.com/html/html-tutorial.html",
    "css": "https://www.runoob.com/css/css-tutorial.html",
    "javascript": "https://www.runoob.com/js/js-tutorial.html",
    "python": "https://www.runoob.com/python3/python3-tutorial.html",
    "java": "https://www.runoob.com/java/java-tutorial.html",
    "c": "https://www.runoob.com/cprogramming/c-tutorial.html",
    "cpp": "https://www.runoob.com/cplusplus/cpp-tutorial.html",
    "csharp": "https://www.runoob.com/csharp/csharp-tutorial.html",
    "go": "https://www.runoob.com/go/go-tutorial.html",
    "rust": "https://www.runoob.com/rust/rust-tutorial.html",
    "ruby": "https://www.runoob.com/ruby/ruby-tutorial.html",
    "php": "https://www.runoob.com/php/php-tutorial.html",
    "typescript": "https://www.runoob.com/typescript/ts-tutorial.html",
    "sql-lang": "https://www.runoob.com/sql/sql-tutorial.html",
    "mysql": "https://www.runoob.com/mysql/mysql-tutorial.html",
    "redis": "https://www.runoob.com/redis/redis-tutorial.html",
    "mongodb": "https://www.runoob.com/mongodb/mongodb-tutorial.html",
    "postgresql": "https://www.runoob.com/postgresql/postgresql-tutorial.html",
    "sqlite": "https://www.runoob.com/sqlite/sqlite-tutorial.html",
    "react": "https://www.runoob.com/react/react-tutorial.html",
    "vue": "https://www.runoob.com/vue2/vue-tutorial.html",
    "angular": "https://www.runoob.com/angularjs2/angularjs2-tutorial.html",
    "jquery": "https://www.runoob.com/jquery/jquery-tutorial.html",
    "nodejs": "https://www.runoob.com/nodejs/nodejs-tutorial.html",
    "django": "https://www.runoob.com/django/django-tutorial.html",
    "flask": "https://www.runoob.com/flask/flask-tutorial.html",
    "docker": "https://www.runoob.com/docker/docker-tutorial.html",
    "git": "https://www.runoob.com/git/git-tutorial.html",
    "linux": "https://www.runoob.com/linux/linux-tutorial.html",
    "regex": "https://www.runoob.com/regexp/regexp-tutorial.html",
    "xml": "https://www.runoob.com/xml/xml-tutorial.html",
    "json": "https://www.runoob.com/json/json-tutorial.html",
    "ajax": "https://www.runoob.com/ajax/ajax-tutorial.html",
    "bootstrap": "https://www.runoob.com/bootstrap/bootstrap-tutorial.html",
    "tailwind": "https://www.runoob.com/tailwindcss/tailwindcss-tutorial.html",
    "sass": "https://www.runoob.com/sass/sass-tutorial.html",
    "maven": "https://www.runoob.com/maven/maven-tutorial.html",
    "vue3": "https://www.runoob.com/vue3/vue3-tutorial.html",
    "svg": "https://www.runoob.com/svg/svg-tutorial.html",
    "rest": "https://www.runoob.com/http/http-tutorial.html",
    "network-security": "https://www.runoob.com/tcpip/tcpip-tutorial.html",
    "api-design": "https://www.runoob.com/webservices/webservices-tutorial.html",
    "xml": "https://www.runoob.com/xpath/xpath-tutorial.html",
    "jquery": "https://www.runoob.com/jqueryui/jqueryui-tutorial.html",
    "bootstrap": "https://www.runoob.com/bootstrap4/bootstrap4-tutorial.html",
    "lua": "https://www.runoob.com/lua/lua-tutorial.html",
    "documentation": "https://www.runoob.com/markdown/md-tutorial.html",
    "data-visualization": "https://www.runoob.com/highcharts/highcharts-tutorial.html",
    "dart": "https://www.runoob.com/dart/dart-tutorial.html",
    "electron": "https://www.runoob.com/electron/electron-tutorial.html",
    "ai": "https://www.runoob.com/ai/ai-tutorial.html",
    "perl": "https://www.runoob.com/perl/perl-tutorial.html",
    "swift": "https://www.runoob.com/swift/swift-tutorial.html",
    "kotlin": "https://www.runoob.com/kotlin/kotlin-tutorial.html",
    "scala": "https://www.runoob.com/scala/scala-tutorial.html",
    "r": "https://www.runoob.com/r/r-tutorial.html",
    "data-structures": "https://www.runoob.com/data-structures/data-structures-tutorial.html",
    "design-patterns": "https://www.runoob.com/design-pattern/design-pattern-tutorial.html",
    "numpy": "https://www.runoob.com/numpy/numpy-tutorial.html",
    "pandas": "https://www.runoob.com/pandas/pandas-tutorial.html",
    "matplotlib": "https://www.runoob.com/matplotlib/matplotlib-tutorial.html",
}


def collect_runoob(no_fetch=False):
    snap = os.path.join(RAW_BASE, "runoob", "chapters")
    courses = []
    for skill, url in RUNOOB_TUTORIALS.items():
        slug = url.rstrip("/").split("/")[-1].replace("-tutorial.html", "")
        html = None
        if not no_fetch:
            html = http_get(url, snap, f"{slug}.html")
            time.sleep(SLEEP_GENERAL)
        if html is None:
            html = load_snapshot(snap, f"{slug}.html")
        if not html:
            log.warning("runoob %s unreachable", url)
            continue
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select("div.left-column a") or soup.select(".left-column a")
        chapters, seen = [], set()
        for a in links:
            href = a.get("href") or ""
            text = a.get_text(strip=True)
            if not text or text.startswith("❮") or text.startswith("❯"):
                continue
            full = urljoin(url, href)
            if full in seen:
                continue
            seen.add(full)
            chapters.append({"no": len(chapters) + 1, "title": text, "url": full})
        if chapters:
            name = soup.title.get_text(strip=True) if soup.title else skill
            name = re.split(r"[|-]", name)[0].strip() or skill
            courses.append({"course": f"菜鸟教程：{name}", "url": url,
                            "language": "zh", "chapters": chapters})
        else:
            log.warning("runoob %s: no chapters parsed", url)
    return save("runoob", courses)


# ---------------------------------------------------------------------------
# 7. MDN Learn 区模块结构（en + zh-CN，模块级）
# ---------------------------------------------------------------------------
def _mdn_modules(prefix):
    home = f"{prefix}/docs/Learn_web_development"
    r = requests.get(home, timeout=HTTP_TIMEOUT, headers=HEADERS)
    if r.status_code != 200:
        log.warning("mdn %s -> %s", home, r.status_code)
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    chapters, seen = [], set()
    for a in soup.select("nav.sidebar a, aside a"):
        href = a.get("href") or ""
        if "/docs/Learn_web_development/" not in href:
            continue
        rel = href.split("/docs/Learn_web_development/", 1)[1].strip("/")
        depth = rel.count("/")
        if depth != 1:
            continue  # 模块级：Core/Scripting 这一层
        full = urljoin("https://developer.mozilla.org", href)
        if full in seen:
            continue
        seen.add(full)
        chapters.append({"no": len(chapters) + 1,
                         "title": a.get_text(strip=True), "url": full})
    if not chapters:
        return None
    lang = "zh" if "/zh-CN" in prefix else "en"
    return {"course": f"MDN Learn web development ({lang})",
            "url": home, "language": lang, "chapters": chapters}


def collect_mdn(no_fetch=False):
    snap = os.path.join(RAW_BASE, "mdn", "chapters")
    courses = []
    for prefix, name in (("https://developer.mozilla.org/en-US", "home_en.html"),
                         ("https://developer.mozilla.org/zh-CN", "home_zh.html")):
        if no_fetch:
            html = load_snapshot(snap, name)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                chapters, seen = [], set()
                for a in soup.select("nav.sidebar a, aside a"):
                    href = a.get("href") or ""
                    if "/docs/Learn_web_development/" not in href:
                        continue
                    rel = href.split("/docs/Learn_web_development/", 1)[1].strip("/")
                    if rel.count("/") != 1:
                        continue
                    full = urljoin("https://developer.mozilla.org", href)
                    if full not in seen:
                        seen.add(full)
                        chapters.append({"no": len(chapters) + 1,
                                         "title": a.get_text(strip=True),
                                         "url": full})
                if chapters:
                    lang = "zh" if "zh-CN" in prefix else "en"
                    courses.append({"course": f"MDN Learn web development ({lang})",
                                    "url": f"{prefix}/docs/Learn_web_development",
                                    "language": lang, "chapters": chapters})
            continue
        c = _mdn_modules(prefix)
        if c:
            courses.append(c)
        # 快照首页便于 --no-fetch 复用
        try:
            r = requests.get(f"{prefix}/docs/Learn_web_development",
                             timeout=HTTP_TIMEOUT, headers=HEADERS)
            if r.status_code == 200:
                os.makedirs(snap, exist_ok=True)
                with open(os.path.join(snap, name), "w", encoding="utf-8") as f:
                    f.write(r.text)
        except requests.RequestException:
            pass
        time.sleep(SLEEP_GENERAL)
    return save("mdn", courses)


COLLECTORS = {
    "theodinproject": collect_odin,
    "freecodecamp": collect_freecodecamp,
    "cs50": collect_cs50,
    "d2l": collect_d2l,
    "liaoxuefeng": collect_liaoxuefeng,
    "runoob": collect_runoob,
    "mdn": collect_mdn,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--only", default="",
                    help="逗号分隔的源子集，如 mdn,cs50")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    names = [s.strip() for s in args.only.split(",") if s.strip()] or list(COLLECTORS)
    for n in names:
        fn = COLLECTORS.get(n)
        if not fn:
            log.error("unknown source %s", n)
            continue
        fn(no_fetch=args.no_fetch)


if __name__ == "__main__":
    main()
