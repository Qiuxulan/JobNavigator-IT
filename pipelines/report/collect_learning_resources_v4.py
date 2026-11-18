# -*- coding: utf-8 -*-
"""collect_learning_resources_v4.py — 学习资源库 v4 采集与质量评分管道。

颠覆性扩容 learning_resources_v3（原 94.6% 覆盖、单一路线来源）：
广泛采集中外学习资源，建立六维加权 quality_score，输出
data/gold/learning_resources_v4.json 及配套 QC 报告。

用法：
    /var/lib/jobnav-env/bin/python pipelines/report/collect_learning_resources_v4.py
    # 复用已有快照、不重新抓取外网（离线幂等重跑）：
    ... collect_learning_resources_v4.py --no-fetch

原始快照保存在 /data/shichaojian/JNIT/raw/courses/<source>/，每次运行更新；
链接可达性验证结果缓存在 raw/courses/_linkcheck/，避免重复验证。
"""

import argparse
import ast
import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import tarfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learning_resources_v4_curated import (  # noqa: E402
    BILIBILI_CURATED,
    CURATED_DOCS,
    CURATED_DOCS_EXTRA,
    FCC_SKILL_OVERRIDES,
    SOURCE_AUTHORITY,
    YOUTUBE_CURATED,
)

log = logging.getLogger("collect_lr_v4")

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VOCAB_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "skill_vocab_v2.json")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v4.json")
QC_PATH = os.path.join(PROJECT_ROOT, "data", "gold", "learning_resources_v4_qc.json")

RAW_BASE = "/data/shichaojian/JNIT/raw/courses"
ROADMAP_CLONE = "/data/shichaojian/JNIT/raw/roadmaps/developer-roadmap"
COURSERA_CSV = os.path.join(RAW_BASE, "coursera_azrai99", "coursera_course_2024.csv")
LINKCHECK_CACHE = os.path.join(RAW_BASE, "_linkcheck", "link_status.json")

# ---------------------------------------------------------------------------
# quality_score 六维权重（各项先归一化到 [0,1]，再加权求和）
# 设计理由：
#   来源权威性 0.30 —— 对学习者而言"该跟谁学"是最强先验：官方文档与知名
#       机构的错误率和体系化程度显著优于个人内容，故给最高权重。
#   社区验证 0.20 —— stars/播放量/评分是事后验证信号，能纠正"官方但过时/
#       晦涩"的资源，但易被营销操纵，权重次于权威性。
#   时效性 0.15 —— IT 技术迭代快（框架 API、云服务几乎年年变），近 2 年更
#       新的资源可显著降低"学到废弃用法"的风险；但经典教材/算法内容时效
#       敏感度低，故只给中等权重。
#   可实践性 0.15 —— 大学生就业导向：project/interactive 资源对动手能力
#       提升证据最充分，与 doc 类形成互补，故与时效性同权。
#   免费可得性 0.10 —— 目标用户为中国大学生，免费资源可及性重要，但付费
#       资源（可旁听/Coursera 助学金）并非不可获得，故权重较低。
#   技能对齐度 0.10 —— 防止"标题党"资源靠权威性挤占不匹配技能的坑位；
#       词表对齐是必要但非充分条件，权重最低。
# ---------------------------------------------------------------------------
W_AUTHORITY = 0.30
W_COMMUNITY = 0.20
W_FRESHNESS = 0.15
W_HANDS_ON = 0.15
W_FREE = 0.10
W_ALIGNMENT = 0.10

# 每技能保留上限：热门技能多留（满足不同学习风格），长尾技能少留控总量
MAX_PER_HOT_SKILL = 10
MAX_PER_COLD_SKILL = 5
COURSERA_PER_SKILL = 4      # Coursera 每技能上限（总量 4.3 万行，需节流）
ROADMAP_PER_SKILL = 6       # roadmap.sh 内容 MD 每技能上限
MIN_TOTAL_TARGET = 1500
COVERAGE_TARGET = 0.90

# 礼貌性限速（秒）：国内平台敏感，务必保守
SLEEP_BILIBILI = 1.5
SLEEP_YOUTUBE = 0.5
SLEEP_GENERAL = 0.3
HTTP_TIMEOUT = 25

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 官方/机构域名（curated 文档权威性判定的正例清单）
OFFICIAL_DOMAINS = {
    "python.org", "oracle.com", "microsoft.com", "go.dev", "golang.google.cn",
    "rust-lang.org", "ruby-lang.org", "php.net", "swift.org", "kotlinlang.org",
    "dart.dev", "gnu.org", "apache.org", "nginx.org", "mysql.com",
    "postgresql.org", "mongodb.com", "redis.io", "mariadb.com", "couchbase.com",
    "influxdata.com", "ibm.com", "elastic.co", "neo4j.com", "clickhouse.com",
    "cassandra.apache.org", "aws.amazon.com", "docs.aws.amazon.com",
    "learn.microsoft.com", "cloud.google.com", "alibabacloud.com",
    "help.aliyun.com", "cloud.tencent.com", "developers.cloudflare.com",
    "heroku.com", "digitalocean.com", "developer.android.com",
    "developer.android.google.cn", "developer.apple.com", "docs.flutter.dev",
    "flutter.cn", "reactnative.dev", "developer.mozilla.org", "w3.org",
    "json.org", "owasp.org", "oauth.net", "jwt.io", "istio.io", "kubernetes.io",
    "helm.sh", "prometheus.io", "grafana.com", "jenkins.io", "docs.ansible.com",
    "developer.hashicorp.com", "docs.github.com", "docs.gitlab.com",
    "selenium.dev", "docs.cypress.io", "playwright.dev", "jestjs.io",
    "junit.org", "appium.io", "jmeter.apache.org", "learning.postman.com",
    "docs.splunk.com", "cve.org", "scikit-learn.org", "pytorch.org",
    "tensorflow.org", "keras.io", "numpy.org", "pandas.pydata.org",
    "xgboost.readthedocs.io", "docs.nvidia.com", "jupyter.org",
    "huggingface.co", "platform.openai.com", "modelcontextprotocol.io",
    "milvus.io", "docs.weaviate.io", "docs.trychroma.com", "faiss.ai",
    "docs.pinecone.io", "docs.getdbt.com", "docs.snowflake.com",
    "docs.databricks.com", "docs.dagster.io", "spark.apache.org",
    "hadoop.apache.org", "kafka.apache.org", "nightlies.apache.org",
    "airflow.apache.org", "hive.apache.org", "rabbitmq.com", "sre.google",
    "trailhead.salesforce.com", "learning.sap.com", "support.microsoft.com",
    "agilemanifesto.org", "scrumguides.org", "atlassian.com",
    "support.atlassian.com", "visualgo.net", "html5rocks.com",
    "www.typescriptlang.org", "developer.chrome.com",
    "developers.google.com", "www.tensorflow.org", "vuejs.org", "cn.vuejs.org",
    "react.dev", "zh-hans.react.dev", "angular.dev", "svelte.dev", "nuxt.com",
    "nextjs.org", "redux.js.org", "api.jquery.com", "tailwindcss.com",
    "getbootstrap.com", "sass-lang.com", "webpack.js.org", "vite.dev",
    "cn.vite.dev", "electronjs.org", "threejs.org", "nodejs.org", "nodejs.cn",
    "expressjs.com", "docs.nestjs.com", "djangoproject.com", "flask.palletsprojects.com",
    "fastapi.tiangolo.com", "docs.spring.io", "spring.io", "laravel.com",
    "symfony.com", "guides.rubyonrails.org", "gin-gonic.com", "hibernate.org",
    "grpc.io", "graphql.org", "graphql.cn", "developer.android.com",
    "docs.docker.com", "docs.arduino.cc", "docs.ros.org", "docs.unity3d.com",
    "help.figma.com", "ethereum.org", "docs.soliditylang.org",
    "sqlite.org", "www.sqlite.org", "man7.org", "git-scm.com", "kubernetes.io",
}

# 从词表别名中剔除的高噪声别名（O*NET 词表混入的无关软件名/泛义词），
# 防止 alias 匹配把资源挂错技能
ALIAS_BLACKLIST = {
    "ocr", "space", "gps", "rs", "data", "stats", "motherboard", "processor",
    "colour", "texture", "shade", "proportion", "congruence",
    "security panel components", "security panels", "security system panels",
    "components of security panel", "scope of design principles",
    "sodipodi", "erdas imagine", "pixbuilder photo editor", "rawstudio",
    "darktable", "pixia", "apache openoffice draw", "model 204",
    "db.star", "adaptive server enterprise", "mysql enterprise edition",
    "mysql embedded (oem/isv)", "mysql classic edition", "mysql standard edition",
    "mysql cluster cge", "sql server standard edition", "sequoia",
    "sagent data flow", "relational junction etl manager",
    "centerprise data integrator", "cloveretl", "ibm infosphere warehoedition",
    "elixir repertoire for data etl", "pikt", "rudder", "caml", "ct",
    "dibol", "korn-shell", "squirrel-script", "tacl", "postscript",
    "pythia", "escript", "live script", "mocha", "csjs",
    "use of statistics", "symmetric-key algorithm", "asymmetric cryptography",
    "public-key cryptography", "principles of information privacy",
    "paradigms of data protection", "principles of data privacy",
    "principles of data protection", "paradigms of data privacy",
    "extreme project management", "ict project management methodologies",
    "software development methodologies", "critical chain project management",
    "management of customer relationship", "customers relationship management",
    "customer-oriented management", "search engine optimization",
    "search engine optimisation", "oracle webcenter", "use voip conference calling",
    "linoma software", "webex", "asana", "aspx",
    "tools for test automation", "tools for ict test automation",
    "test automation tools", "jenkins continuous integration server",
    "jenkins ci", "android",  # 'android' 别名归属 android 技能本身，保留见下
}
# 注意：上面集合里误伤的合法别名在此恢复（按技能显式补回）
ALIAS_WHITELIST = {
    ("android", "android"): True,  # android 技能的 android 别名合法
}

# 短别名要求大小写敏感精确匹配，避免 'go'/'ts'/'ml' 等误伤普通文本；
# 刻意不收 'it'/'hr'/'cn' 等会在英文正文中高频出现的两字母组合
SHORT_CASE_SENSITIVE = {
    "r", "c", "go", "ts", "js", "ml", "dl", "cv", "rl", "ai", "bi", "ha",
    "mq", "iam", "sem", "seo", "crm", "gis", "iot", "sre", "oop", "dsa",
    "jwt", "gpt",
}

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
FETCH_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")

SOURCE_STATUS = {}  # source -> {reachable, detail, fetched_at}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def http_get(url, **kw):
    kw.setdefault("timeout", HTTP_TIMEOUT)
    kw.setdefault("headers", {"User-Agent": UA})
    for attempt in range(3):
        try:
            r = requests.get(url, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410):
                return r
        except requests.RequestException as e:
            log.warning("GET %s failed (%s), attempt %d", url, e, attempt + 1)
        time.sleep(1.5 * (attempt + 1))
    return r if "r" in dir() else None


def save_snapshot(source, filename, content, mode="wb"):
    d = os.path.join(RAW_BASE, source)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    if isinstance(content, str):
        content = content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(content)
    return path


def write_manifest(source, extra=None):
    d = os.path.join(RAW_BASE, source)
    os.makedirs(d, exist_ok=True)
    m = {"fetched_at": FETCH_TS, "snapshots": sorted(os.listdir(d))}
    if extra:
        m.update(extra)
    with open(os.path.join(d, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)


def note_source(source, reachable, detail=""):
    SOURCE_STATUS[source] = {
        "reachable": reachable, "detail": detail, "fetched_at": FETCH_TS,
    }
    log.info("source %-22s reachable=%s %s", source, reachable, detail)


def load_linkcheck_cache():
    if os.path.exists(LINKCHECK_CACHE):
        try:
            with open(LINKCHECK_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_linkcheck_cache(cache):
    os.makedirs(os.path.dirname(LINKCHECK_CACHE), exist_ok=True)
    with open(LINKCHECK_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def check_url(url, cache, sleep=0.0, method="head"):
    """返回 (ok, status_code)。结果写入缓存，保证幂等重跑不重复打外网。"""
    if url in cache:
        return cache[url]["ok"], cache[url].get("status")
    ok, status = False, None
    try:
        if method == "head":
            r = requests.head(url, timeout=HTTP_TIMEOUT,
                              headers={"User-Agent": UA}, allow_redirects=True)
            if r.status_code in (403, 405):  # 某些站拒绝 HEAD，退回 GET
                r = requests.get(url, timeout=HTTP_TIMEOUT,
                                 headers={"User-Agent": UA}, stream=True)
        else:
            r = requests.get(url, timeout=HTTP_TIMEOUT,
                             headers={"User-Agent": UA}, stream=True)
        status = r.status_code
        ok = 200 <= status < 400
        r.close()
    except requests.RequestException:
        ok, status = False, None
    # 只缓存确定性结果；瞬时失败（限流/网络抖动）不缓存，下次重跑再验证
    if ok or status in (404, 410):
        cache[url] = {"ok": ok, "status": status,
                      "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if sleep:
        time.sleep(sleep)
    return ok, status

# ---------------------------------------------------------------------------
# 技能词表与别名匹配
# ---------------------------------------------------------------------------
class Vocab:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.skills = data["skills"]
        self.by_id = {s["id"]: s for s in self.skills}
        self.hot_ids = {s["id"] for s in self.skills if s.get("hot")}
        # 构建别名 -> skill_id 映射（应用黑名单）
        self.alias_map = {}
        for s in self.skills:
            for a in s.get("aliases", []):
                key = a.strip().lower()
                if not key or key in ALIAS_BLACKLIST:
                    if not ALIAS_WHITELIST.get((s["id"], key)):
                        continue
                # 多个技能共有别名时，优先归 hot 技能（歧义消解）
                if key in self.alias_map and s["id"] not in self.hot_ids:
                    continue
                self.alias_map[key] = s["id"]
        # name 本身也是别名
        for s in self.skills:
            key = s["name"].strip().lower()
            if key not in self.alias_map:
                self.alias_map[key] = s["id"]
        # 预编译两个"巨型 alternation"正则（按别名长度降序，长别名优先）：
        #   re_ci —— 普通别名，忽略大小写；
        #   re_cs —— 短别名（go/ts/ml...），大小写敏感；'c'/'r' 单独按大写
        # 匹配（C/R 语言通常大写书写）。单遍扫描替代逐别名循环，保证
        # Coursera 4.3 万行文本匹配在分钟级完成。
        ci, cs, upper = [], [], []
        for alias in self.alias_map:
            if alias in ("c", "r"):
                upper.append(re.escape(alias.upper()))
            elif alias in SHORT_CASE_SENSITIVE:
                cs.append(re.escape(alias))
            else:
                ci.append(re.escape(alias))
        def _mk(parts, flags):
            if not parts:
                return None
            body = "|".join(sorted(parts, key=len, reverse=True))
            return re.compile(r"(?<![\w])(" + body + r")(?![\w])", flags)
        self.re_ci = _mk(ci, re.IGNORECASE)
        self.re_cs = _mk(cs, 0)
        self.re_upper = _mk(upper, 0)

    def match(self, text):
        if not text:
            return []
        # 字母+数字相邻时（Bootstrap5/HTML5/CSS3/python3）在字母数字间插
        # 空格再匹配一轮，使 'bootstrap' 等别名能命中带版本号的写法
        texts = [text]
        spaced = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", text)
        if spaced != text:
            texts.append(spaced)
        found = []
        for t in texts:
            for rx in (self.re_ci, self.re_cs, self.re_upper):
                if rx is None:
                    continue
                for m in rx.finditer(t):
                    sid = self.alias_map.get(m.group(1).lower())
                    if sid:
                        found.append(sid)
        # 去重保持顺序
        seen = set()
        out = []
        for sid in found:
            if sid not in seen:
                seen.add(sid)
                out.append(sid)
        return out


# ---------------------------------------------------------------------------
# 资源模型与质量评分
# ---------------------------------------------------------------------------
def freshness_score(updated_at):
    """updated_at: ISO 日期字符串或 None。无日期给中性 0.6。"""
    if not updated_at:
        return 0.6
    try:
        dt = datetime.fromisoformat(str(updated_at)[:10])
    except ValueError:
        return 0.6
    age_y = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days / 365.0
    if age_y <= 0.5:
        return 1.0
    if age_y <= 1.0:
        return 0.9
    if age_y <= 2.0:
        return 0.75
    return 0.5


HANDS_ON_BY_TYPE = {"project": 1.0, "interactive": 1.0, "course": 0.7,
                    "video": 0.5, "book": 0.4, "tutorial": 0.6, "doc": 0.3,
                    "article": 0.3}


def make_resource(url, title, source, language, rtype, level=None,
                  is_free=None, rating=None, community=None,
                  community_kind=None, updated_at=None, duration_hours=None,
                  skill_ids=None, alignment=0.8, authority=None, note=None):
    return {
        "url": url.strip(),
        "title": (title or "").strip(),
        "source": source,
        "language": language,
        "type": rtype,
        "level": level,
        "is_free": is_free,
        "rating": rating,
        "community_signal": community,
        "community_kind": community_kind,  # stars/views/enrolled 等，便于解释
        "updated_at": updated_at,
        "duration_hours": duration_hours,
        "skill_ids": sorted(set(skill_ids or [])),
        "alignment": alignment,
        "authority": authority if authority is not None else SOURCE_AUTHORITY.get(source, 0.6),
        "note": note,
    }


def quality_score(res):
    auth = res["authority"]
    comm = res["community_signal"] if res["community_signal"] is not None else 0.5
    fresh = freshness_score(res["updated_at"])
    hands = HANDS_ON_BY_TYPE.get(res["type"], 0.4)
    if res["is_free"] is True:
        free = 1.0
    elif res["is_free"] is False:
        free = 0.2
    else:
        free = 0.5
    align = res["alignment"]
    score = (W_AUTHORITY * auth + W_COMMUNITY * comm + W_FRESHNESS * fresh
             + W_HANDS_ON * hands + W_FREE * free + W_ALIGNMENT * align)
    return round(min(1.0, max(0.0, score)), 4)


# ---------------------------------------------------------------------------
# 采集器 1：roadmap.sh 本地克隆（content MD 抽取 @type@ 标注资源链接）
# ---------------------------------------------------------------------------
MD_LINK_RE = re.compile(
    r"[-*]\s*\[(?:@(\w+)@)?([^\]]{2,200})\]\((https?://[^)\s]+)\)")
TYPE_MAP = {"course": "course", "video": "video", "article": "doc",
            "official": "doc", "roadmap": "doc", "opensource": "project",
            "tool": "doc", "podcast": "video"}


def collect_roadmap_local(vocab, no_fetch=False):
    source = "roadmap_local"
    content_root = os.path.join(ROADMAP_CLONE, "roadmaps")
    if not os.path.isdir(content_root):
        note_source(source, False, f"clone not found at {ROADMAP_CLONE}")
        return []
    # 克隆 HEAD 时间作为内容新鲜度依据
    head_date = None
    try:
        out = subprocess.run(
            ["git", "-C", ROADMAP_CLONE, "log", "-1", "--format=%cI"],
            capture_output=True, text=True, timeout=30)
        head_date = out.stdout.strip()[:10]
    except (subprocess.SubprocessError, OSError):
        pass

    resources = []
    parsed_rows = []
    n_md = 0
    for slug in sorted(os.listdir(content_root)):
        cdir = os.path.join(content_root, slug, "content")
        if not os.path.isdir(cdir):
            continue
        # 路线图 slug 本身也映射技能（如 python、vue）
        slug_skill = vocab.match(slug.replace("-", " "))
        for fn in sorted(os.listdir(cdir)):
            if not fn.endswith(".md"):
                continue
            n_md += 1
            try:
                text = open(os.path.join(cdir, fn), encoding="utf-8").read()
            except OSError:
                continue
            m_title = re.search(r"^#\s+(.+)$", text, re.M)
            md_title = m_title.group(1).strip() if m_title else fn.split("@")[0]
            links = []
            for m in MD_LINK_RE.finditer(text):
                tag, title, url = m.group(1), m.group(2), m.group(3)
                if "roadmap.sh" in url and "/questions/" in url:
                    continue
                links.append((tag, title, url))
            # 每文件去重 + 类型优先排序后截断
            seen = set()
            uniq = []
            for tag, title, url in links:
                if url in seen:
                    continue
                seen.add(url)
                uniq.append((tag, title, url))
            uniq.sort(key=lambda x: ({'official': 0, 'course': 1, 'video': 2,
                                      'article': 3}.get(x[0] or "", 4)))
            for tag, title, url in uniq[:ROADMAP_PER_SKILL]:
                skills = vocab.match(f"{md_title} {title}")
                if not skills:
                    skills = slug_skill
                if not skills:
                    continue
                rtype = TYPE_MAP.get((tag or "").lower(), "doc")
                rsource = f"roadmap_{(tag or 'unknown').lower()}"
                res = make_resource(
                    url, title, rsource, "en", rtype, level=None, is_free=None,
                    updated_at=head_date, skill_ids=skills,
                    alignment=1.0 if vocab.match(md_title) else 0.7,
                    authority=SOURCE_AUTHORITY.get(rsource, 0.55))
                resources.append(res)
                parsed_rows.append({"roadmap": slug, "file": fn,
                                    "tag": tag, "title": title, "url": url})
    save_snapshot(source, "roadmap_links_snapshot.json",
                  json.dumps({"fetched_at": FETCH_TS, "n_md_files": n_md,
                              "n_links": len(parsed_rows), "links": parsed_rows},
                             ensure_ascii=False, indent=1))
    write_manifest(source, {"n_md_files": n_md, "n_links": len(parsed_rows)})
    note_source(source, True, f"clone HEAD {head_date}, {n_md} md files, "
                              f"{len(parsed_rows)} links")
    return resources


# ---------------------------------------------------------------------------
# 采集器 2：Coursera 课程 CSV（本地快照，azrai99 HF 数据集）
# ---------------------------------------------------------------------------
def parse_hours(schedule):
    if not schedule:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*hours?", schedule)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def collect_coursera(vocab):
    source = "coursera"
    if not os.path.exists(COURSERA_CSV):
        note_source(source, False, f"csv not found at {COURSERA_CSV}")
        return []
    SNAPSHOT_DATE = "2024-11-01"  # HF 数据集快照月份
    per_skill = defaultdict(list)
    max_enrolled = 3_000_000.0  # 归一化上限（Coursera 顶流课程量级）
    n_rows = 0
    with open(COURSERA_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            skills_col = row.get("Skills") or "[]"
            try:
                sk_list = ast.literal_eval(skills_col)
            except (ValueError, SyntaxError):
                sk_list = []
            # 先精确解析 Skills 列（命中即跳过正文扫描，控制 4.3 万行耗时）
            skills = []
            for name in sk_list:
                sid = vocab.alias_map.get(str(name).strip().lower())
                if sid and sid not in skills:
                    skills.append(sid)
            if not skills:
                text = " ".join([row.get("title") or "",
                                 row.get("Organization") or ""])
                skills = vocab.match(text)
            if not skills and row.get("Description"):
                skills = vocab.match(row["Description"][:600])
            if not skills:
                continue
            if not row.get("URL"):
                continue
            try:
                enrolled = float((row.get("enrolled") or "0").replace(",", ""))
            except ValueError:
                enrolled = 0.0
            try:
                rating = float(row.get("rating") or 0) or None
            except ValueError:
                rating = None
            rating_norm = (rating or 0) / 5.0
            enrolled_norm = math.log1p(enrolled) / math.log1p(max_enrolled)
            community = round(0.6 * rating_norm + 0.4 * enrolled_norm, 4)
            level_raw = (row.get("Level") or "").lower()
            level = "beginner" if "beginner" in level_raw else (
                "intermediate" if "intermediate" in level_raw else (
                    "advanced" if "advanced" in level_raw else None))
            res = make_resource(
                row.get("URL") or "", row.get("title") or "", source, "en",
                "course", level=level, is_free=False, rating=rating,
                community=community, community_kind="rating*0.6+enrolled*0.4",
                updated_at=SNAPSHOT_DATE,
                duration_hours=parse_hours(row.get("Schedule")),
                skill_ids=skills,
                alignment=0.9 if sk_list else 0.6)
            for sid in skills:
                per_skill[sid].append(res)
    out = []
    for sid, lst in per_skill.items():
        lst.sort(key=lambda r: (r["community_signal"] or 0), reverse=True)
        out.extend(lst[:COURSERA_PER_SKILL])
    note_source(source, True, f"{n_rows} rows -> {len(out)} kept "
                              f"(cap {COURSERA_PER_SKILL}/skill)")
    return out


# ---------------------------------------------------------------------------
# 采集器 3：freeCodeCamp（官网认证目录 + curriculum 认证定义 yml，经 jsDelivr）
# ---------------------------------------------------------------------------
FCC_API_DIR = ("https://api.github.com/repos/freeCodeCamp/freeCodeCamp/"
               "contents/curriculum/challenges/english/certifications")
FCC_CDN = ("https://cdn.jsdelivr.net/gh/freeCodeCamp/freeCodeCamp@main/"
           "curriculum/challenges/english/certifications/{}")
FCC_LEARN_URL = "https://www.freecodecamp.org/learn/"

# freeCodeCamp 认证 slug 回退清单（API 限流时用；与 curriculum 仓库
# certifications 目录保持一致，yml 标题仍实时经 CDN 校验）
FCC_FALLBACK_CERT_SLUGS = [
    "responsive-web-design",
    "javascript-algorithms-and-data-structures",
    "javascript-algorithms-and-data-structures-v8",
    "front-end-development-libraries",
    "data-visualization",
    "relational-database",
    "back-end-development-and-apis",
    "quality-assurance",
    "scientific-computing-with-python",
    "data-analysis-with-python",
    "information-security",
    "machine-learning-with-python",
    "college-algebra-with-python",
    "foundational-c-sharp-with-microsoft",
    "full-stack-developer",
    "a2-english-for-developers",
    "b1-english-for-developers",
]


def _fcc_resources_from_certs(vocab, certs, note_suffix=""):
    resources = []
    for slug, title in sorted(certs.items()):
        skills = FCC_SKILL_OVERRIDES.get(slug)
        if skills is None:
            skills = vocab.match(title)
        skills = [s for s in (skills or []) if s]
        if not skills:
            continue
        resources.append(make_resource(
            f"https://www.freecodecamp.org/learn/{slug}/", title,
            "freecodecamp", "en", "course", level="beginner", is_free=True,
            updated_at=FETCH_TS[:10], skill_ids=skills, alignment=0.95,
            authority=SOURCE_AUTHORITY["freecodecamp"],
            note="freeCodeCamp 认证课程（含项目实战，完全免费）" + note_suffix))
    return resources


def collect_freecodecamp(vocab, no_fetch=False):
    source = "freecodecamp"
    certs = {}  # slug -> title
    if no_fetch:
        # 回放上次抓取的 yml 快照（幂等重跑与离线模式结果一致）
        sp = os.path.join(RAW_BASE, source, "fcc_certifications_yml.tar.gz")
        if os.path.exists(sp):
            try:
                tf = tarfile.open(sp, "r:gz")
                for member in tf:
                    if member.isfile() and member.name.endswith(".yml"):
                        text = tf.extractfile(member).read().decode("utf-8", "ignore")
                        m = re.search(r"^title:\s*(.+)$", text, re.M)
                        slug = os.path.basename(member.name)[:-4]
                        certs[slug] = m.group(1).strip() if m else slug
                tf.close()
            except tarfile.TarError:
                pass
        note_source(source, bool(certs),
                    f"no-fetch mode, {len(certs)} certs replayed from snapshot")
        return _fcc_resources_from_certs(vocab, certs)
    # 3a. 官网 /learn 页面快照（Gatsby 壳，仅作可达性证据）
    r = http_get(FCC_LEARN_URL)
    learn_ok = r is not None and r.status_code == 200 and len(r.content) > 10000
    if r is not None:
        save_snapshot(source, "fcc_learn_index.html", r.content)

    # 3b. GitHub contents API 拿认证 yml 清单（raw 域被墙，故走 API）
    r = http_get(FCC_API_DIR, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    listing = []
    if r is not None and r.status_code == 200:
        try:
            listing = r.json()
        except ValueError:
            listing = []
    yml_names = [e["name"] for e in listing
                 if e.get("type") == "file" and e["name"].endswith(".yml")]
    listing_from = "github_api"
    if not yml_names:
        # 降级：GitHub API 限流（共享出口 IP 60 次/小时）时，用维护良好的
        # 已知认证 slug 清单，yml 正文仍经 jsDelivr CDN 拉取（不受限流影响）
        listing_from = "fallback_slug_list"
        yml_names = [s + ".yml" for s in FCC_FALLBACK_CERT_SLUGS]
    save_snapshot(source, "fcc_certifications_listing.json",
                  json.dumps({"source": listing_from, "items": listing},
                             ensure_ascii=False, indent=1))

    # 3c. 逐个 yml 经 jsDelivr CDN 取标题（不计 GitHub 频率）
    yml_dump = {}
    for name in yml_names:
        rr = http_get(FCC_CDN.format(name))
        if rr is None or rr.status_code != 200:
            continue
        yml_dump[name] = rr.text
        m = re.search(r"^title:\s*(.+)$", rr.text, re.M)
        title = m.group(1).strip() if m else name[:-4]
        certs[name[:-4]] = title
        time.sleep(SLEEP_GENERAL)
    if yml_dump:
        save_snapshot(source, "fcc_certifications_yml.tar.gz",
                      _tar_gz({f"yml/{k}": v.encode() for k, v in yml_dump.items()}))

    if not learn_ok and not certs:
        note_source(source, False, "/learn empty and GitHub listing failed")
        return []

    resources = _fcc_resources_from_certs(vocab, certs)
    write_manifest(source, {"n_certifications": len(certs)})
    note_source(source, learn_ok or bool(certs),
                f"/learn html={learn_ok}, certifications={len(certs)}")
    return resources


def _tar_gz(name_to_bytes):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, b in name_to_bytes.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(b)
            tf.addfile(ti, io.BytesIO(b))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 采集器 4：GitHub 高质量 awesome/路径 README（ossu、system-design-primer）
# ---------------------------------------------------------------------------
GITHUB_READMES = [
    ("ossu/computer-science", "ossu",
     ["software-engineering", "data-structures", "algorithms"]),
    ("donnemartin/system-design-primer", "github_awesome", ["system-design"]),
]
# API 限流降级用的已知 stars 近似值（仅当 API 不可用时的保守估计，注明来源）
FALLBACK_STARS = {"ossu/computer-science": 170_000,
                  "donnemartin/system-design-primer": 280_000}


def _fetch_repo_readme(repo):
    """优先 GitHub API；限流时降级 codeload tarball（不受 API 限流影响）。
    返回 (text, stars, pushed_at, via)。"""
    meta = http_get(f"https://api.github.com/repos/{repo}",
                    headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    stars, pushed = 0, None
    if meta is not None and meta.status_code == 200:
        try:
            mj = meta.json()
            stars = mj.get("stargazers_count") or 0
            pushed = (mj.get("pushed_at") or "")[:10] or None
        except ValueError:
            pass
    r = http_get(f"https://api.github.com/repos/{repo}/readme",
                 headers={"User-Agent": UA, "Accept": "application/vnd.github.raw"})
    if r is not None and r.status_code == 200 and r.text:
        return r.text, stars or FALLBACK_STARS.get(repo, 0), pushed, "api"
    # 降级：codeload tarball 取 README.md
    r = http_get(f"https://codeload.github.com/{repo}/tar.gz/refs/heads/master")
    if r is None or r.status_code != 200:
        return None, 0, None, "failed"
    try:
        tf = tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz")
        for member in tf:
            if member.isfile() and member.name.lower().endswith("/readme.md"):
                text = tf.extractfile(member).read().decode("utf-8", errors="ignore")
                tf.close()
                return text, stars or FALLBACK_STARS.get(repo, 0), pushed, "codeload"
        tf.close()
    except tarfile.TarError:
        pass
    return None, 0, None, "failed"


def _parse_readme_links(vocab, text, repo, bucket, default_skills, star_norm, pushed):
    seen = set()
    n_links = 0
    resources = []
    for line in text.splitlines():
        for m in re.finditer(r"\[([^\]]{4,120})\]\((https?://[^)\s]+)\)", line):
            title, url = m.group(1).strip(), m.group(2)
            if url in seen:
                continue
            seen.add(url)
            # 过滤徽章/图标/锚点类链接
            if any(b in url for b in ("badge", "shield", "workflow", "#")):
                continue
            skills = vocab.match(f"{title} {line[:200]}")
            if not skills:
                skills = default_skills
                align = 0.6
            else:
                align = 0.75
            resources.append(make_resource(
                url, title, bucket, "en", "doc", level=None, is_free=True,
                community=star_norm, community_kind=f"github_stars_of_{repo.split('/')[0]}",
                updated_at=pushed, skill_ids=skills, alignment=align,
                authority=SOURCE_AUTHORITY[bucket],
                note=f"精选自 {repo}"))
            n_links += 1
            if n_links >= 60:
                break
        if n_links >= 60:
            break
    return resources, n_links


def collect_github_readmes(vocab, no_fetch=False):
    source = "github_readmes"
    resources = []
    for repo, bucket, default_skills in GITHUB_READMES:
        default_skills = [s for s in default_skills if s in vocab.by_id]
        if no_fetch:
            # 回放上次抓取的 readme 快照（幂等重跑与离线模式结果一致）
            base = os.path.join(RAW_BASE, source)
            rp = os.path.join(base, f"{repo.replace('/', '_')}_readme.md")
            mp = os.path.join(base, f"{repo.replace('/', '_')}_meta.json")
            if not os.path.exists(rp):
                note_source(f"{source}:{repo}", False, "no snapshot for replay")
                continue
            text = open(rp, encoding="utf-8").read()
            meta = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
            stars = meta.get("stars") or FALLBACK_STARS.get(repo, 0)
            pushed = meta.get("pushed_at")
            star_norm = round(math.log1p(stars) / math.log1p(280_000), 4)
            res, n_links = _parse_readme_links(
                vocab, text, repo, bucket, default_skills, star_norm, pushed)
            resources.extend(res)
            note_source(f"{source}:{repo}", True,
                        f"no-fetch replay, links={n_links}")
            continue
        text, stars, pushed, via = _fetch_repo_readme(repo)
        if not text:
            note_source(f"{source}:{repo}", False, "readme fetch failed")
            continue
        save_snapshot(source, f"{repo.replace('/', '_')}_readme.md", text)
        save_snapshot(source, f"{repo.replace('/', '_')}_meta.json",
                      json.dumps({"stars": stars, "pushed_at": pushed,
                                  "fetched_at": FETCH_TS, "via": via}))
        star_norm = round(math.log1p(stars) / math.log1p(280_000), 4)
        res, n_links = _parse_readme_links(
            vocab, text, repo, bucket, default_skills, star_norm, pushed)
        resources.extend(res)
        note_source(f"{source}:{repo}", True, f"stars={stars}, links={n_links}")
    write_manifest(source, {"repos": [r for r, _, _ in GITHUB_READMES]})
    return resources


# ---------------------------------------------------------------------------
# 采集器 5：CS 自学指南（PKUFlyingPig/cs-self-learning，codeload tarball）
# ---------------------------------------------------------------------------
CSDIY_TARBALL = "https://codeload.github.com/PKUFlyingPig/cs-self-learning/tar.gz/refs/heads/master"


def collect_cs_self_learning(vocab, no_fetch=False):
    source = "cs_self_learning"
    tpath = os.path.join(RAW_BASE, source, "cs-self-learning.tar.gz")
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    if not (no_fetch and os.path.exists(tpath)):
        r = http_get(CSDIY_TARBALL)
        if r is None or r.status_code != 200:
            note_source(source, False, "codeload tarball fetch failed")
            return []
        with open(tpath, "wb") as f:
            f.write(r.content)
    try:
        tf = tarfile.open(tpath, "r:gz")
    except tarfile.TarError:
        note_source(source, False, "tarball corrupt")
        return []
    resources = []
    seen_urls = set()
    per_skill_count = defaultdict(int)
    pushed = FETCH_TS[:10]
    for member in tf:
        if not member.isfile() or not member.name.endswith(".md"):
            continue
        f = tf.extractfile(member)
        if f is None:
            continue
        try:
            text = f.read().decode("utf-8", errors="ignore")
        except OSError:
            continue
        # 课程 md 典型格式: [课程名](url) 周围带难度标注
        for m in re.finditer(r"\[([^\]]{3,120})\]\((https?://[^)\s]+)\)", text):
            title, url = m.group(1).strip(), m.group(2)
            if url in seen_urls:
                continue
            if any(b in url for b in ("badge", "shield", "#")):
                continue
            # 标题未命中时用正文开头（课程简介通常含技能关键词）补充匹配
            skills = vocab.match(title) or vocab.match(text[:400].replace("\n", " "))
            if not skills:
                continue
            seen_urls.add(url)
            level = None
            ctx = text[max(0, m.start() - 80):m.end() + 80].lower()
            if "中等" in ctx or "进阶" in ctx:
                level = "intermediate"
            elif "较易" in ctx or "入门" in ctx:
                level = "beginner"
            elif "困难" in ctx or "硬核" in ctx:
                level = "advanced"
            for sid in skills:
                if per_skill_count[sid] >= 3:
                    continue
                per_skill_count[sid] += 1
                resources.append(make_resource(
                    url, title, source, "en", "course", level=level,
                    is_free=None, updated_at=pushed, skill_ids=[sid],
                    alignment=0.75, authority=SOURCE_AUTHORITY[source],
                    note="精选自 CS 自学指南（PKUFlyingPig，76k stars）"))
    tf.close()
    write_manifest(source, {"n_resources": len(resources)})
    note_source(source, True, f"{len(resources)} course links")
    return resources


# ---------------------------------------------------------------------------
# 采集器 6：菜鸟教程 runoob.com（首页教程目录，标题即技能名）
# ---------------------------------------------------------------------------
RUNOOB_HOME = "https://www.runoob.com/"


def collect_runoob(vocab, no_fetch=False, cache=None):
    source = "runoob"
    cache = cache if cache is not None else {}
    if no_fetch:
        p = os.path.join(RAW_BASE, source, "runoob_home.html")
        if not os.path.exists(p):
            note_source(source, False, "no-fetch but no cached snapshot")
            return []
        html = open(p, encoding="utf-8", errors="ignore").read()
    else:
        r = http_get(RUNOOB_HOME)
        if r is None or r.status_code != 200:
            note_source(source, False, "homepage fetch failed")
            return []
        save_snapshot(source, "runoob_home.html", r.content)
        html = r.text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    resources = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href, text = a["href"], a.get_text(strip=True)
        if "-tutorial.html" not in href or not text:
            continue
        if href.startswith("/"):
            href = "https://www.runoob.com" + href
        if href in seen:
            continue
        seen.add(href)
        # 标题形如 【学习 Python】说明文字 —— 取方括号内为教程名
        m = re.match(r"【([^】]{1,40})】", text)
        tname = m.group(1) if m else text.split("，")[0].split("。")[0][:20]
        tname = re.sub(r"^(学习|教程)", "", tname).strip() or tname
        skills = vocab.match(f"{tname} {href}")
        if not skills:
            continue
        resources.append(make_resource(
            href, f"菜鸟教程：{tname}", source, "zh", "tutorial",
            level="beginner", is_free=True, updated_at=None,
            skill_ids=skills, alignment=1.0,
            authority=SOURCE_AUTHORITY[source]))
    write_manifest(source, {"n_tutorials_matched": len(resources)})
    note_source(source, True, f"{len(resources)} tutorials matched to vocab")
    return resources


# ---------------------------------------------------------------------------
# 采集器 7：人工整理表（官方文档/中文文档/知名课程 + YouTube/B站精选）
# ---------------------------------------------------------------------------
def collect_curated(vocab, cache):
    resources = []
    dropped = []

    def domain_of(url):
        return urlparse(url).netloc.lower().lstrip("www.") or urlparse(url).netloc.lower()

    # 7a. 官方文档与权威教程
    n_doc = 0
    merged_docs = dict(CURATED_DOCS)
    for sid, entries in CURATED_DOCS_EXTRA.items():
        merged_docs.setdefault(sid, [])
        merged_docs[sid] = merged_docs[sid] + entries
    for sid, entries in merged_docs.items():
        if sid not in vocab.by_id:
            continue
        for e in entries:
            url = e["url"]
            ok, status = check_url(url, cache, sleep=SLEEP_GENERAL)
            if not ok:
                dropped.append({"url": url, "skill": sid, "status": status})
                continue
            dom = domain_of(url)
            dom = dom[4:] if dom.startswith("www.") else dom
            official = any(dom == d or dom.endswith("." + d) or d.endswith("." + dom)
                           for d in OFFICIAL_DOMAINS)
            authority = 0.95 if official else 0.78
            is_free = True  # 所列 curated 资源均可免费在线访问
            resources.append(make_resource(
                url, e.get("title") or f"{vocab.by_id[sid]['name']} 官方文档",
                "official_doc", e["language"], e["type"],
                level=e.get("level"), is_free=True, updated_at=FETCH_TS[:10],
                skill_ids=[sid], alignment=1.0, authority=authority,
                note=e.get("note", "curated official/educational doc")))
            n_doc += 1
    note_source("curated_docs", True, f"kept {n_doc}, dropped_unreachable "
                                      f"{len(dropped)}")

    # 7b. YouTube 精选（视频/频道落地页）
    n_yt = 0
    for e in YOUTUBE_CURATED:
        skills = [s for s in e["skill_ids"] if s in vocab.by_id]
        if not skills:
            continue
        ok, status = check_url(e["url"], cache, sleep=SLEEP_YOUTUBE)
        if not ok:
            dropped.append({"url": e["url"], "skills": skills, "status": status})
            continue
        resources.append(make_resource(
            e["url"], e["title"], "youtube_curated", e["language"], "video",
            level=None, is_free=True, updated_at=FETCH_TS[:10],
            skill_ids=skills, alignment=0.95,
            authority=SOURCE_AUTHORITY["youtube_curated"],
            note=e.get("community_hint")))
        n_yt += 1
    note_source("youtube_curated", True, f"kept {n_yt}, dropped {len(dropped)}")

    # 7c. B 站精选 UP 主（反爬敏感：仅验证空间页可达，严格限速）
    n_bili = 0
    for e in BILIBILI_CURATED:
        skills = [s for s in e["skill_ids"] if s in vocab.by_id]
        if not skills:
            continue
        ok, status = check_url(e["url"], cache, sleep=SLEEP_BILIBILI)
        if not ok:
            dropped.append({"url": e["url"], "skills": skills, "status": status})
            continue
        resources.append(make_resource(
            e["url"], e["title"], "bilibili_curated", "zh", "video",
            level=None, is_free=True, updated_at=FETCH_TS[:10],
            skill_ids=skills, alignment=0.95,
            authority=SOURCE_AUTHORITY["bilibili_curated"],
            note=e.get("community_hint")))
        n_bili += 1
    note_source("bilibili_curated", True, f"kept {n_bili}, dropped {len(dropped)}")
    if dropped:
        save_snapshot("curated", "dropped_unreachable.json",
                      json.dumps(dropped, ensure_ascii=False, indent=1))
    write_manifest("curated", {"dropped_unreachable": len(dropped)})
    return resources


# ---------------------------------------------------------------------------
# 汇总：去重、每技能配额选择、输出与 QC
# ---------------------------------------------------------------------------
def merge_by_url(resources):
    """同 URL 资源合并 skill_ids（扁平资源池）。"""
    by_url = {}
    for res in resources:
        u = res["url"].rstrip("/") if "youtube.com" not in res["url"] else res["url"]
        if u in by_url:
            old = by_url[u]
            old["skill_ids"] = sorted(set(old["skill_ids"]) | set(res["skill_ids"]))
            old["alignment"] = max(old["alignment"], res["alignment"])
            if old["community_signal"] is None:
                old["community_signal"] = res["community_signal"]
        else:
            by_url[u] = dict(res)
    return list(by_url.values())


def select_per_skill(pool, vocab):
    """每技能配额选择：保证 zh/en 多样性，再按质量分填充。"""
    by_skill = defaultdict(list)
    for res in pool:
        for sid in res["skill_ids"]:
            by_skill[sid].append(res)
    selected = {}  # url -> res
    for sid, lst in by_skill.items():
        cap = MAX_PER_HOT_SKILL if sid in vocab.hot_ids else MAX_PER_COLD_SKILL
        lst = sorted(lst, key=quality_score, reverse=True)
        picked = []
        zh = [r for r in lst if r["language"] == "zh"]
        en = [r for r in lst if r["language"] == "en"]
        if zh:
            picked.append(zh[0])
        if en:
            picked.append(en[0])
        # 其余按质量填充（去重 picked 内 url）
        for r in lst:
            if len(picked) >= cap:
                break
            if all(r["url"] != p["url"] for p in picked):
                picked.append(r)
        for r in picked:
            selected[r["url"]] = r
    return list(selected.values())


def build_qc(final, pool, vocab, args):
    by_skill = defaultdict(list)
    for res in final:
        for sid in res["skill_ids"]:
            by_skill[sid].append(res)
    all_ids = [s["id"] for s in vocab.skills]
    zero = [sid for sid in all_ids if sid not in by_skill]
    coverage = round(1 - len(zero) / len(all_ids), 4)

    hot = sorted(vocab.hot_ids)
    hot_under3 = []
    hot_no_zh = []
    hot_no_en = []
    for sid in hot:
        lst = by_skill.get(sid, [])
        if len(lst) < 3:
            hot_under3.append(sid)
        if not any(r["language"] == "zh" for r in lst):
            hot_no_zh.append(sid)
        if not any(r["language"] == "en" for r in lst):
            hot_no_en.append(sid)

    def dist(key):
        return dict(Counter(r.get(key) or "unknown" for r in final))

    src_counts = Counter(r["source"] for r in final)
    pool_counts = Counter(r["source"] for r in pool)
    qc = {
        "generated_at": FETCH_TS,
        "version": "v4",
        "inputs": {
            "vocab": VOCAB_PATH,
            "roadmap_clone": ROADMAP_CLONE,
            "coursera_csv": COURSERA_CSV,
            "curated_tables": "pipelines/report/learning_resources_v4_curated.py",
            "no_fetch_mode": bool(args.no_fetch),
        },
        "source_status": SOURCE_STATUS,
        "pool_counts_by_source": dict(pool_counts),
        "final_counts_by_source": dict(src_counts),
        "totals": {
            "pool_resources": len(pool),
            "final_resources": len(final),
            "unique_urls": len({r['url'] for r in final}),
            "target_total": MIN_TOTAL_TARGET,
            "target_met": len(final) >= MIN_TOTAL_TARGET,
        },
        "distribution": {
            "language": dist("language"),
            "type": dist("type"),
            "level": dist("level"),
            "is_free": dist("is_free"),
        },
        "coverage": {
            "vocab_size": len(all_ids),
            "covered": len(all_ids) - len(zero),
            "coverage": coverage,
            "target": COVERAGE_TARGET,
            "target_met": coverage >= COVERAGE_TARGET,
            "skills_without_resources": zero,
        },
        "hot_skill_quality": {
            "n_hot": len(hot),
            "hot_with_lt3_resources": hot_under3,
            "hot_without_zh": hot_no_zh,
            "hot_without_en": hot_no_en,
        },
        "quality_score": {
            "weights": {
                "source_authority": W_AUTHORITY,
                "community_signal": W_COMMUNITY,
                "freshness": W_FRESHNESS,
                "hands_on": W_HANDS_ON,
                "free_access": W_FREE,
                "vocab_alignment": W_ALIGNMENT,
            },
            "rationale": "见 collect_learning_resources_v4.py 顶部注释",
            "min": min((r["quality_score"] for r in final), default=None),
            "mean": round(sum(r["quality_score"] for r in final) / len(final), 4)
            if final else None,
        },
        "skipped_sources": {
            "edx": "无公开目录 API（api/discovery 均 404），页面 JS 渲染，跳过",
            "icourse163": "目录页 JS 渲染，无免登录公开 API，跳过（首页 200 仅壳页面）",
            "imooc": "course/list 返回 988B JS 壳，跳过",
            "csdn/juejin 教程栏目": "无稳定结构化目录接口，未采集",
            "bilibili_search": "无登录态搜索接口被风控（见调研笔记 §8），仅收录已确认 UP 主空间",
            "kaggle": "需 API key，未配置",
        },
    }
    return qc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="复用已有快照，不访问外网（离线幂等重跑）")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    vocab = Vocab(VOCAB_PATH)
    log.info("vocab: %d skills, %d hot, %d aliases", len(vocab.skills),
             len(vocab.hot_ids), len(vocab.alias_map))

    link_cache = load_linkcheck_cache()
    before_cache = len(link_cache)

    resources = []
    resources += collect_roadmap_local(vocab, args.no_fetch)
    resources += collect_coursera(vocab)
    resources += collect_freecodecamp(vocab, args.no_fetch)
    resources += collect_github_readmes(vocab, args.no_fetch)
    resources += collect_cs_self_learning(vocab, args.no_fetch)
    resources += collect_runoob(vocab, args.no_fetch)
    resources += collect_curated(vocab, link_cache)

    if len(link_cache) > before_cache:
        save_linkcheck_cache(link_cache)

    pool = merge_by_url(resources)
    for res in pool:
        res["quality_score"] = quality_score(res)
    final = select_per_skill(pool, vocab)
    final.sort(key=lambda r: (-len(r["skill_ids"]), -r["quality_score"]))

    # 兜底：总量不足时放宽每技能上限再选一次
    if len(final) < MIN_TOTAL_TARGET:
        log.warning("total %d < target %d, relaxing caps",
                    len(final), MIN_TOTAL_TARGET)
        global MAX_PER_HOT_SKILL, MAX_PER_COLD_SKILL  # noqa: PLW0603
        MAX_PER_HOT_SKILL, MAX_PER_COLD_SKILL = 20, 10
        final = select_per_skill(pool, vocab)
        final.sort(key=lambda r: (-len(r["skill_ids"]), -r["quality_score"]))

    out = {
        "version": "v4",
        "generated_at": FETCH_TS,
        "schema": {
            "skill_ids": "关联 skill_vocab_v2.json 的技能 id 列表",
            "title": "资源标题", "url": "落地链接",
            "source": "来源桶", "language": "zh/en",
            "type": "video/course/doc/book/interactive/project/tutorial/article",
            "level": "beginner/intermediate/advanced/null",
            "is_free": "true/false/null(部分免费或未知)",
            "rating": "平台评分(0-5)或 null",
            "community_signal": "归一化社区信号(星标/播放量/报名数)或 null",
            "updated_at": "资源更新日期或抓取日期", "duration_hours": "估算时长或 null",
            "quality_score": "六维加权质量分(0-1)",
        },
        "quality_weights": {
            "source_authority": W_AUTHORITY, "community_signal": W_COMMUNITY,
            "freshness": W_FRESHNESS, "hands_on": W_HANDS_ON,
            "free_access": W_FREE, "vocab_alignment": W_ALIGNMENT,
        },
        "resources": final,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    qc = build_qc(final, pool, vocab, args)
    with open(QC_PATH, "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=1)

    log.info("FINAL: %d resources -> %s", len(final), OUT_PATH)
    log.info("coverage: %.4f, hot<3: %d, hot no-zh: %d, QC -> %s",
             qc["coverage"]["coverage"],
             len(qc["hot_skill_quality"]["hot_with_lt3_resources"]),
             len(qc["hot_skill_quality"]["hot_without_zh"]), QC_PATH)


if __name__ == "__main__":
    main()
