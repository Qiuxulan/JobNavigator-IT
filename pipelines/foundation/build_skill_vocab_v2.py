"""build_skill_vocab_v2: 技能词表重建（v1 基底 + O*NET/ESCO 权威 + JD 真实分布）.

以人工维护的 275 词 v1 词表为基底（id 全部保留），融合三个数据源：

1. ``data/gold/skill_vocab.json`` —— 现词表，向后兼容，275 技能全保留;
2. O*NET 31.0 ``software_skills.csv`` —— 权威技术名 + Hot Technology / In Demand 标记;
3. Tabiya ESCO v1.1.1 ``skills.csv`` —— preferredLabel / altLabels 用于别名扩充;
4. 统一 JD 库 ``jd_unified``（25 万行，skills 列 ATS 预抽取）—— 真实在用技能频次.

构建逻辑：
- JD skills 列全量频次统计（解析健壮：list / ndarray / str），归一化后先过 v1 别名映射;
- 未映射且频次 >=200 的词再过 O*NET Example 与 ESCO preferredLabel/altLabels 匹配，
  命中则吸收其别名并继承 O*NET 热度标记；
- 剩余词做 IT 相关性过滤（黑名单：软技能/商务职能/公司名噪声；白名单 + 词形规则），
  通过且 >=500 次的成为新技能（id 用 slug，category 规则分类）;
- 现有 275 技能用 O*NET Hot Technology 校准 hot、用 ESCO altLabels 补 aliases;
- 新技能总数控制在 400 以内（v1 275 + 新增 <=125，按频次截断），宁缺毋滥。

产出：
- ``data/gold/skill_vocab_v2.json`` —— 结构与 v1 完全一致，version="v2"，不覆盖 v1;
- ``data/gold/skill_vocab_v2_qc.json`` —— 覆盖率 / 新增清单 / 未映射 top50 / 旧 id 断言。

入口: ``python -m pipelines.foundation.build_skill_vocab_v2`` （幂等，重复运行覆盖输出）.
"""

from __future__ import annotations

import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
V1_JSON = ROOT / "data/gold/skill_vocab.json"
V2_JSON = ROOT / "data/gold/skill_vocab_v2.json"
QC_JSON = ROOT / "data/gold/skill_vocab_v2_qc.json"

ONET_CSV = Path("/data/shichaojian/JNIT/raw/standards/onet31/software_skills.csv")
ESCO_CSV = Path(
    "/data/shichaojian/JNIT/raw/standards/tabiya_esco/tabiya-esco-v1.1.1/csv/skills.csv"
)
JD_GLOB = "/data/shichaojian/JNIT/processed/jd_unified/posted_month=*/part-0.parquet"

MAX_TOTAL = 400              # 词表总规模上限（v1 275 + 新增 <=125）
CAND_MIN_FREQ = 200          # O*NET/ESCO 权威匹配的最低频次
NEW_SKILL_MIN_FREQ = 500     # 新增新技能的最低频次
MAX_ALIAS_LEN = 40           # 别名长度上限（剔除长尾）
MAX_ALIAS_WORDS = 6          # 别名词数上限
MAX_EXTRA_ALIASES_PER_SKILL = 8  # 每个旧技能最多补充的 ESCO 别名数

# O*NET 中视为 IT 相关的职业大类（15- = Computer and Mathematical Occupations）
ONET_IT_SOC_PREFIX = "15-"
ONET_IT_ELEMENT_KEYWORDS = (
    "development software", "database", "data base", "web", "programming",
    "network", "operating system", "data science", "machine learning",
    "artificial intelligence", "cloud", "devops", "security software",
    "business intelligence", "analytical or scientific software",
)

# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"\([^)]*\)")
_VER_TAIL_RE = re.compile(r"\s+\d+(\.\d+)*\.?[a-z]?$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9+#]+")


def norm_key(s: str) -> str:
    """技能名归一化：lower、去括号内容、去版本号尾巴、去标点、压缩空白.

    "Python 3.x" -> "python"；"React.js" -> "react.js"（保留 . 之外标点转空格，
    实际规则为除 a-z0-9+# 外全部转空格）。
    """
    s = str(s).strip().lower()
    if not s:
        return ""
    s = _PAREN_RE.sub(" ", s)
    prev = None
    while prev != s:  # 迭代去版本尾巴，"python 3.11 v2" 类情况
        prev = s
        s = _VER_TAIL_RE.sub("", s)
    s = _NON_ALNUM_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def slugify(s: str) -> str:
    """JD token（已是 slug 形态）-> 词表 id."""
    s = norm_key(s)
    s = s.replace(" ", "-").replace("+", "plus").replace("#", "sharp")
    s = re.sub(r"-{2,}", "-", s).strip("-")
    # c++ -> cplus 不好看，单独修正常见语言
    fix = {"cplus": "cpp", "cplusplus": "cpp", "csharp": "csharp"}
    return fix.get(s, s)


def display_name(token: str, onet_example: str | None) -> str:
    """新技能展示名：优先 O*NET 权威名（去尾部的 software 泛化词），否则 title-case."""
    if onet_example:
        name = onet_example.strip()
        name = re.sub(r"\s+(software|tech|technologies)$", "", name, flags=re.I)
        if 0 < len(name) <= MAX_ALIAS_LEN:
            return name
    words = str(token).replace("-", " ").split()
    small = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
    acronym = {
        "aws": "AWS", "gcp": "GCP", "golang": "Go", "html": "HTML", "css": "CSS",
        "ui": "UI", "ux": "UX", "qa": "QA", "crm": "CRM", "erp": "ERP", "sap": "SAP",
        "sem": "SEM", "seo": "SEO", "api": "API", "sql": "SQL", "ci": "CI", "cd": "CD",
        "it": "IT", "iot": "IoT", "gis": "GIS", "cad": "CAD", "cam": "CAM",
        "bi": "BI", "ml": "ML", "ai": "AI", "llm": "LLM", "rag": "RAG",
        "nosql": "NoSQL", "javascript": "JavaScript", "typescript": "TypeScript",
        "php": "PHP", "rest": "REST", "soap": "SOAP", "rpc": "RPC",
        "sdk": "SDK", "cli": "CLI", "ide": "IDE", "dns": "DNS", "cdn": "CDN",
        "vpn": "VPN", "ssl": "SSL", "tls": "TLS", "jwt": "JWT", "iam": "IAM",
        "siem": "SIEM", "c++": "C++", "c#": "C#", ".net": ".NET",
    }
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in acronym:
            out.append(acronym[low])
        elif low in {"c++", "c#", ".net"}:
            out.append(acronym[low])
        elif i > 0 and low in small:
            out.append(low)
        else:
            out.append(low[:1].upper() + low[1:])
    return " ".join(out)


# ---------------------------------------------------------------------------
# IT 相关性过滤：黑名单 + 白名单/词形规则
# ---------------------------------------------------------------------------

# 软技能 / 商务职能 / 非 IT 噪声（命中即剔除）
IT_BLACKLIST = re.compile(
    r"\b(?:"
    r"communication|communicat\w*|teamwork|collaborat\w*|leadership|leader|"
    r"management skill|people management|stakeholder\w*|negotiat\w*|"
    r"time management|problem solving|decision making|critical thinking|"
    r"attention to detail|adaptab\w*|organiz\w+|planning|scheduling|"
    r"recruit\w*|hiring|interviewing|onboarding|talent\w*|hr\b|human resources|"
    r"sales|selling|account executive|business development|prospecting|"
    r"marketing|advertis\w*|brand\w*|campaign|content marketing|"
    r"accounting|bookkeeping|payroll|invoicing|budgeting|tax\b|audit\w*|"
    r"finance|financial analysis|financial planning|banking|investment|"
    r"legal|compliance|regulatory|risk management|contract\w*|"
    r"customer service|customer success|customer support|customer experience|"
    r"customer satisfaction|client relations|client management|"
    r"vendor management|procurement|purchasing|supply chain|logistics|"
    r"inventory|warehouse|cash handling|billing|"
    r"patient care|nursing|clinical|medical|dental|pharmacy|"
    r"teaching|training|coaching|mentoring|tutoring|"
    r"safety|cleaning|cooking|food service|hospitality|retail|"
    r"equipment operation|equipment maintenance|mechanic\w*|plumbing|electric\w*|"
    r"carpentry|landscaping|janitorial|housekeeping|security guard|"
    r"driving|delivery|dispatch|forklift|"
    r"multitasking|self motivated|motivated|reliable|punctual|positive attitude|"
    r"work ethic|interpersonal|empathy|patience|conflict resolution|"
    r"presentation|public speaking|writing skill|documentation management"
    r")\b"
)

# IT 白名单子串（命中即视为 IT 相关；覆盖语言/框架/工具/平台）
TECH_SUBSTRINGS = [
    # 语言与运行时
    "python", "javascript", "typescript", "java", "golang", "kotlin", "scala",
    "ruby", "php", "swift", "dart", "lua", "perl", "matlab", "shell", "bash",
    "powershell", "rust", "solidity", "verilog", "vhdl", "assembly", "cobol",
    "fortran", "sas", "stata", "julia", "elm", "erlang", "ocaml", "fsharp",
    "html", "css", "sql", "nosql", "graphql", "wasm",
    # 框架/库
    "react", "vue", "angular", "svelte", "node", "deno", "bun", "django",
    "flask", "fastapi", "spring", "rails", "laravel", "symfony", "gin",
    "nestjs", "express", "nextjs", "next.js", "nuxt", "gatsby", "remix",
    "jquery", "redux", "tailwind", "bootstrap", "sass", "less", "webpack",
    "vite", "babel", "rollup", "parcel", "electron", "three", "d3",
    # 数据/数据库
    "mysql", "postgres", "mongodb", "redis", "oracle", "sqlserver", "mssql",
    "sqlite", "mariadb", "cassandra", "couchbase", "neo4j", "clickhouse",
    "influxdb", "elasticsearch", "solr", "dynamodb", "db2", "snowflake",
    "bigquery", "redshift", "synapse", "databricks", "teradata", "presto",
    "trino", "hive", "hbase", "impala", "etl", "elt", "spark", "hadoop",
    "flink", "kafka", "pulsar", "storm", "beam", "airflow", "dbt", "dagster",
    "prefect", "luigi", "nifi", "sqoop", "oozie", "data warehouse",
    "data lake", "data pipeline", "data modeling", "data governance",
    "data quality", "data engineering", "streaming", "iceberg", "hudi",
    "delta lake", "parquet", "avro", "protobuf", "thrift",
    # 云/DevOps
    "aws", "azure", "gcp", "alicloud", "aliyun", "tencent", "cloud",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins",
    "gitlab", "github", "bitbucket", "devops", "sre", "ci/cd", "cicd",
    "helm", "prometheus", "grafana", "datadog", "splunk", "newrelic",
    "new relic", "dynatrace", "pagerduty", "sonarqube", "nexus",
    "artifactory", "maven", "gradle", "npm", "yarn", "pip", "conda",
    "nginx", "apache", "tomcat", "haproxy", "envoy", "traefik", "kong",
    "istio", "linkerd", "consul", "vault", "nomad", "openshift", "rancher",
    "vmware", "vsphere", "hyperv", "kvm", "qemu", "vagrant", "packer",
    "pulumi", "crossplane", "argocd", "fluxcd", "spinnaker", "tekton",
    "linux", "unix", "ubuntu", "centos", "debian", "redhat", "windows server",
    "serverless", "microservice", "container", "observability", "monitoring",
    "logging", "firebase", "supabase", "vercel", "netlify", "heroku",
    "cloudflare", "cdn", "dns",
    # AI/ML
    "machine learning", "deep learning", "pytorch", "tensorflow", "keras",
    "scikit", "sklearn", "pandas", "numpy", "scipy", "cuda", "nlp",
    "computer vision", "opencv", "llm", "rag", "langchain", "llamaindex",
    "langgraph", "agent", "transformer", "bert", "gpt", "huggingface",
    "openai", "anthropic", "mlops", "vector", "embedding", "prompt",
    "fine tuning", "fine-tuning", "multimodal", "diffusion", "aigc",
    "generative ai", "neural", "xgboost", "lightgbm", "catboost",
    "reinforcement learning", "speech recognition", "tts", "asr", "ocr",
    # 测试
    "selenium", "cypress", "playwright", "jest", "pytest", "junit", "appium",
    "jmeter", "postman", "cucumber", "testing", "qa", "test automation",
    "unit test", "integration test", "e2e", "k6", "locust", "selenium",
    # 移动/前端
    "android", "ios", "flutter", "react native", "xamarin", "jetpack",
    "swiftui", "mobile", "figma", "sketch", "ux", "ui", "wireframe",
    "design system", "webflow", "prototyping",
    # 安全
    "security", "cyber", "penetration", "pentest", "oauth", "jwt", "ssl",
    "tls", "siem", "iam", "cryptography", "vulnerability", "firewall",
    "vpn", "owasp", "ldap", "kerberos", "saml", "sso", "mfa", "pki",
    "forensic", "malware", "zero trust", "incident response",
    # 企业软件 / SaaS / 工程工具
    "sap", "salesforce", "hubspot", "servicenow", "workday", "dynamics",
    "sharepoint", "power bi", "powerbi", "tableau", "looker", "qlik",
    "microstrategy", "excel", "word", "powerpoint", "outlook", "office 365",
    "microsoft office", "jira", "confluence", "notion", "slack", "teams",
    "zoom", "trello", "asana", "monday", "linear", "crm", "erp", "cms",
    "wordpress", "shopify", "magento", "drupal", "joomla", "seo", "sem",
    "google analytics", "autocad", "solidworks", "catia", "matlab", "cad",
    "cam", "plc", "scada", "fpga", "embedded", "firmware", "iot",
    "robot", "mechatronics", "gis", "bim", "revit", "unity", "unreal",
    "godot", "blender", "ar/vr", "vr", "ar ", "game", "blockchain", "web3",
    "ethereum", "bitcoin", "solidity", "nft",
    # 方法/协议/其他
    "agile", "scrum", "kanban", "devsecops", "gitops", "api", "rest",
    "soap", "grpc", "websocket", "mqtt", "amqp", "tcp", "udp", "ip",
    "ssh", "http", "json", "xml", "yaml", "graphql", "oauth", "sdk",
    "cli", "ide", "vim", "vscode", "intellij", "pycharm", "postman",
    "algorithm", "data structure", "design pattern", "system design",
    "distributed system", "microservice", "event driven", "domain driven",
    "oop", "functional programming", "tdd", "bdd", "ddd", "solid",
    "design system", "troubleshooting", "debugging", "scripting",
    "networking", "tcp/ip", "lan", "wan", "dhcp", "nat", "load balanc",
    "virtualization", "backup", "disaster recovery", "high availability",
    "big data", "data science", "analytics", "business intelligence",
    "data analyst", "data visualization", "statistics", "bi tool",
    # 管理/支持类硬技能（IT 语境下保留，归入 methods）
    "project management", "product management", "product development",
    "program management", "release management", "incident management",
    "change management", "configuration management", "database administration",
    "system administration", "network administration", "technical support",
    "it support", "helpdesk", "help desk", "business analysis",
    "technical documentation", "documentation", "technical writing",
    "application support", "ecommerce", "e commerce", "devsecops",
]

_TECH_RE = re.compile(
    "|".join(
        re.escape(t.strip().replace("/", " "))
        for t in TECH_SUBSTRINGS if t.strip()
    )
)

# 明确的别名合并覆盖（人工核对过的歧义项）
MERGE_OVERRIDES = {
    "security": "cybersecurity",  # JD 中泛指的 security 多数是 infosec
}


def is_it_relevant(token_key: str) -> tuple[bool, str]:
    """IT 相关性判断，返回 (是否通过, 命中规则).

    规则顺序：黑名单剔除 -> O*NET/ESCO 命中视为候选 -> 白名单子串 -> 词形规则。
    """
    if not token_key:
        return False, "empty"
    if IT_BLACKLIST.search(f" {token_key} "):
        return False, "blacklist"
    if _TECH_RE.search(token_key):
        return True, "tech_substring"
    # 词形规则：短缩写（2-6 字母纯词）或含数字混合词（css3 / vue3 / ipv6 等）
    if re.fullmatch(r"[a-z]{2,6}\d*", token_key):
        return True, "shape_short"
    if re.search(r"[a-z]+[0-9]+|[0-9]+[a-z]+", token_key):
        return True, "shape_alnum"
    return False, "no_signal"


# ---------------------------------------------------------------------------
# 分类规则（顺序匹配，先命中先得）
# ---------------------------------------------------------------------------

CATEGORY_RULES = [
    ("language", [
        "python", "java", "javascript", "typescript", "golang", "rust", "ruby",
        "php", "swift", "kotlin", "scala", "matlab", "perl", "dart", "lua",
        "haskell", "elixir", "clojure", "groovy", "solidity", "shell", "bash",
        "powershell", "r language", "objective c", "c++", "c#", "assembly",
        "verilog", "vhdl", "cobol", "fortran", "julia", "erlang", "programming language",
    ]),
    ("frontend", [
        "react", "vue", "angular", "svelte", "html", "css", "sass", "less",
        "tailwind", "bootstrap", "webpack", "vite", "electron", "three",
        "webgl", "nextjs", "next.js", "nuxt", "gatsby", "remix", "redux",
        "jquery", "figma", "ui ux", "frontend", "front end", "web design",
        "design system", "wireframe", "sketch", "webflow", "prototyping",
        "usability", "ux research",
    ]),
    ("backend", [
        "node", "express", "nest", "django", "flask", "fastapi", "spring",
        "rails", "laravel", "symfony", "gin", "dotnet", "net framework",
        "api", "graphql", "grpc", "rest", "soap", "backend", "back end",
        "microservice", "websocket", "middleware", "rpc",
    ]),
    ("database", [
        "sql", "mysql", "postgres", "mongodb", "redis", "oracle", "sqlite",
        "mariadb", "cassandra", "couchbase", "neo4j", "clickhouse", "influxdb",
        "elasticsearch", "dynamodb", "db2", "database", "nosql", "etcd",
        "cockroach", "tidb", "solr",
    ]),
    ("cloud", [
        "aws", "azure", "gcp", "cloud", "alicloud", "aliyun", "tencent",
        "heroku", "digitalocean", "s3", "ec2", "lambda", "serverless",
        "cloudflare", "firebase", "supabase", "vercel", "netlify", "cdn",
        "openshift", "vmware", "vsphere", "virtualization", "hyperv",
        "openshift", "rancher", "iaas", "paas", "saas",
    ]),
    ("bigdata", [
        "spark", "hadoop", "kafka", "flink", "airflow", "dbt", "hive", "hbase",
        "etl", "elt", "data warehouse", "data lake", "data pipeline", "streaming",
        "databricks", "snowflake", "bigquery", "redshift", "synapse", "storm",
        "pulsar", "beam", "dagster", "prefect", "sqoop", "nifi", "presto",
        "trino", "iceberg", "hudi", "delta lake", "data governance",
        "data modeling", "data quality", "data engineering", "data extraction",
        "parquet", "avro",
    ]),
    ("data_analysis", [
        "pandas", "numpy", "tableau", "power bi", "powerbi", "excel", "looker",
        "data analysis", "data analytics", "data visualization", "statistics",
        "business intelligence", "dashboard", "qlik", "microstrategy", "bi ",
        "data mining", "data cleaning", "spreadsheet", "spss",
    ]),
    ("ai_ml", [
        "machine learning", "deep learning", "pytorch", "tensorflow", "keras",
        "scikit", "sklearn", "nlp", "natural language", "computer vision",
        "opencv", "xgboost", "lightgbm", "reinforcement", "neural",
        "data science", "model", "classification", "regression", "clustering",
        "anomaly detection", "forecasting", "predictive", "ai ", "ml ",
        "speech recognition", "ocr", "tts", "asr", "recommendation",
        "feature engineering", "hyperparameter", "computer vision",
    ]),
    ("ai_emerging", [
        "llm", "large language model", "rag", "langchain", "llamaindex",
        "langgraph", "agent", "transformer", "bert", "gpt", "openai",
        "anthropic", "huggingface", "vector", "embedding", "prompt",
        "fine tuning", "fine-tuning", "multimodal", "diffusion", "aigc",
        "generative ai", "mcp", "ai agent", "ai coding", "copilot",
        "text generation", "image generation",
    ]),
    ("devops", [
        "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins",
        "gitlab", "github", "bitbucket", "devops", "sre", "ci/cd", "cicd",
        "helm", "prometheus", "grafana", "nginx", "linux", "unix", "git",
        "microservice", "istio", "consul", "vault", "nomad", "argocd",
        "observability", "monitoring", "logging", "datadog", "splunk",
        "maven", "gradle", "npm", "yarn", "pip", "conda", "pulumi",
        "server", "infrastructure", "iis", "tomcat", "haproxy", "envoy",
        "load balanc", "high availability", "disaster recovery", "backup",
        "networking", "tcp", "ip ", "dhcp", "dns", "vpn", "ssh", "http",
        "system administration",
    ]),
    ("testing", [
        "test", "qa", "selenium", "cypress", "playwright", "jest", "pytest",
        "junit", "appium", "jmeter", "postman", "cucumber", "e2e",
        "unit test", "integration test", "load test", "automation test",
        "quality assurance", "tdd", "bdd", "k6", "locust",
    ]),
    ("mobile", [
        "android", "ios", "flutter", "react native", "xamarin", "swiftui",
        "jetpack", "mobile", "kotlin", "swift",
    ]),
    ("security", [
        "security", "cyber", "penetration", "pentest", "oauth", "jwt", "ssl",
        "tls", "siem", "iam", "cryptography", "vulnerability", "firewall",
        "vpn", "owasp", "ldap", "kerberos", "saml", "sso", "mfa", "pki",
        "forensic", "malware", "zero trust", "incident response", "infosec",
    ]),
    ("methods", [
        "agile", "scrum", "kanban", "jira", "confluence", "design pattern",
        "system design", "distributed system", "algorithm", "data structure",
        "api design", "oop", "object oriented", "architecture", "documentation",
        "blockchain", "web3", "gis", "iot", "robot", "embedded", "hardware",
        "firmware", "project management", "product management", "itil",
        "it service", "technical support", "helpdesk", "troubleshooting",
        "debugging", "scripting", "regex", "json", "xml", "yaml",
        "event driven", "domain driven", "design system", "game",
        "ar/vr", "unity", "unreal", "cad", "autocad", "solidworks",
        "seo", "sem", "crm", "erp", "cms", "sap", "salesforce", "hubspot",
        "servicenow", "workday", "office", "excel", "sharepoint", "matlab",
        "data entry", "tableau", "power bi", "business analysis",
        "requirements analysis", "user story", "product owner",
    ]),
]

_CATEGORY_RE = [
    (cat, re.compile(r"\b(?:" + "|".join(re.escape(k.strip()) for k in keys) + r")\b"))
    for cat, keys in CATEGORY_RULES
]


def categorize(token_key: str) -> str:
    for cat, rex in _CATEGORY_RE:
        if rex.search(token_key):
            return cat
    return "methods"


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_v1() -> dict:
    with open(V1_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_jd_skill_freq() -> Counter:
    """扫描统一 JD 库 skills 列，返回归一化后的 token 频次 Counter."""
    freq: Counter = Counter()
    files = sorted(glob.glob(JD_GLOB))
    if not files:
        raise FileNotFoundError(f"JD 分区不存在: {JD_GLOB}")
    for path in files:
        table = pq.read_table(path, columns=["skills"])
        for chunk in table.column("skills").chunks:
            for value in chunk:
                tokens = _extract_tokens(value.as_py())
                for tok in tokens:
                    key = norm_key(tok)
                    if key:
                        freq[key] += 1
    return freq


def _extract_tokens(value) -> list[str]:
    """健壮解析 skills 单元格：list / ndarray / str 均可."""
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        v = value.strip()
        if not v or v in ("[]", "null", "None"):
            return []
        if v.startswith("["):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        return [p.strip() for p in re.split(r"[,;|]", v) if p.strip()]
    return []


def load_onet_index() -> dict[str, dict]:
    """O*NET Example -> {hot, in_demand, example, it_relevant}."""
    index: dict[str, dict] = {}
    with open(ONET_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            example = (row.get("Workplace Example") or "").strip()
            key = norm_key(example)
            if not key or len(key) > MAX_ALIAS_LEN:
                continue
            hot = (row.get("Hot Technology") or "").strip().upper() == "Y"
            demand = (row.get("In Demand") or "").strip().upper() == "Y"
            soc = (row.get("O*NET-SOC Code") or "")[:3]
            element = (row.get("Element Name") or "").lower()
            it_rel = soc == ONET_IT_SOC_PREFIX or any(
                kw in element for kw in ONET_IT_ELEMENT_KEYWORDS
            )
            rec = index.get(key)
            if rec is None:
                index[key] = {
                    "hot": hot, "in_demand": demand, "example": example,
                    "it_relevant": it_rel,
                }
            else:
                rec["hot"] = rec["hot"] or hot
                rec["in_demand"] = rec["in_demand"] or demand
                rec["it_relevant"] = rec["it_relevant"] or it_rel
    return index


def load_esco_index() -> dict[str, dict]:
    """ESCO label key -> {preferred, alts(list), skilltype}."""
    index: dict[str, dict] = {}
    with open(ESCO_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            preferred = (row.get("PREFERREDLABEL") or "").strip()
            if not preferred:
                continue
            alts = [
                a.strip()
                for a in (row.get("ALTLABELS") or "").split("\n")
                if a.strip()
            ]
            rec = {"preferred": preferred, "alts": alts,
                   "skilltype": (row.get("SKILLTYPE") or "").strip()}
            for label in [preferred, *alts]:
                key = norm_key(label)
                if not key or len(key) > MAX_ALIAS_LEN:
                    continue
                if key not in index:  # 首次命中优先保留 preferred 记录
                    index[key] = rec
    return index


# O*NET Example 通用尾部词：token + tail 视为同一技术（"salesforce" ~ "salesforce software"）
ONET_GENERIC_TAILS = {
    "software", "system", "systems", "tool", "tools", "suite", "platform",
    "app", "application", "crm", "erp", "cloud", "server", "client",
}


def onet_lookup(key: str, onet: dict[str, dict]) -> dict | None:
    """O*NET 匹配：先精确，再前缀+通用尾部（sap ~ sap software）."""
    hit = onet.get(key)
    if hit:
        return hit
    prefix = key + " "
    best = None
    for k in onet:
        if k.startswith(prefix) and k[len(prefix):] in ONET_GENERIC_TAILS:
            if best is None or len(k) < len(best):
                best = k
    return onet.get(best) if best else None


def _is_versionish(key: str) -> bool:
    """形如 python3 / py3k / es6 的版本号粘连词."""
    return bool(re.search(r"[a-z]+\d+|\d+[a-z]+", key))


def clean_aliases(labels: list[str]) -> list[str]:
    """别名清洗：长度/词数限制、去重（按 norm_key）、去版本尾巴."""
    seen, out = set(), []
    for lab in labels:
        lab = str(lab).strip()
        key = norm_key(lab)
        if not key or len(lab) > MAX_ALIAS_LEN or len(key.split()) > MAX_ALIAS_WORDS:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(lab)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    print(">>> 载入 v1 词表 ...")
    v1 = load_v1()
    v1_skills = [dict(s, aliases=list(s["aliases"])) for s in v1["skills"]]
    v1_ids = {s["id"] for s in v1_skills}
    print(f"    v1 技能数: {len(v1_skills)}")

    print(">>> 统计 JD skills 频次（25 万行全量扫描）...")
    freq = load_jd_skill_freq()
    total_tokens = sum(freq.values())
    print(f"    总 token 数: {total_tokens:,}；unique: {len(freq):,}")

    print(">>> 加载 O*NET / ESCO 索引 ...")
    onet = load_onet_index()
    esco = load_esco_index()
    print(f"    O*NET unique examples: {len(onet):,}；ESCO labels: {len(esco):,}")

    # -- 1) v1 别名映射 ------------------------------------------------------
    alias_owner: dict[str, str] = {}   # norm_key -> skill id
    for s in v1_skills:
        for lab in [s["id"], s["name"], *s["aliases"]]:
            alias_owner.setdefault(norm_key(lab), s["id"])

    mapped: dict[str, str] = {}        # token key -> skill id
    unmapped: Counter = Counter()
    for key, c in freq.items():
        owner = alias_owner.get(key)
        if owner:
            mapped[key] = owner
        else:
            unmapped[key] = c
    base_mapped = sum(freq[k] for k in mapped)
    print(f"    v1 直接映射: {base_mapped:,} token "
          f"({100 * base_mapped / total_tokens:.2f}%)")

    # -- 2) 未映射高频词 -> O*NET / ESCO 匹配 --------------------------------
    onet_hits: dict[str, dict] = {}
    esco_hits: dict[str, dict] = {}
    for key, c in unmapped.items():
        if c < CAND_MIN_FREQ:
            continue
        hit = onet_lookup(key, onet)
        if hit:
            onet_hits[key] = hit
        rec = esco.get(key)
        if rec:
            esco_hits[key] = rec

    # -- 3) 保守别名合并：未映射词是某唯一旧技能名的子串（如 security -> cybersecurity）
    alias_merges: dict[str, str] = {}
    for key in list(unmapped):
        if len(key) < 4 or unmapped[key] < CAND_MIN_FREQ:
            continue
        if key in MERGE_OVERRIDES:
            alias_merges[key] = MERGE_OVERRIDES[key]
            continue
        cands = [s for s in v1_skills if key in norm_key(s["name"])]
        if len(cands) == 1 and cands[0]["id"] not in alias_merges.values():
            alias_merges[key] = cands[0]["id"]

    # -- 4) IT 过滤 -> 新技能候选 -------------------------------------------
    candidates: dict[str, dict] = {}
    rejected: Counter = Counter()
    for key, c in unmapped.items():
        if key in alias_merges or c < NEW_SKILL_MIN_FREQ:
            continue
        onet_hit = onet_hits.get(key)
        esco_hit = esco_hits.get(key)
        ok, rule = is_it_relevant(key)
        if onet_hit and onet_hit["it_relevant"]:
            ok, rule = True, "onet_it"
        elif (onet_hit or esco_hit) and ok:
            rule = "standard+tech"
        if not ok:
            rejected[rule] += 1
            continue
        absorbed: list[str] = []
        if esco_hit:
            absorbed += esco_hit["alts"] + [esco_hit["preferred"]]
        if onet_hit:
            absorbed.append(onet_hit["example"])
        # 不抢旧技能已占用的别名
        absorbed = [a for a in clean_aliases(absorbed)
                    if norm_key(a) not in alias_owner]
        candidates[key] = {
            "freq": c,
            "rule": rule,
            "onet": onet_hit,
            "esco": esco_hit,
            "aliases": clean_aliases(absorbed),
        }

    # 按频次排序，截断到 400 上限
    budget = MAX_TOTAL - len(v1_skills)
    ranked = sorted(candidates.items(), key=lambda kv: -kv[1]["freq"])
    kept, dropped = ranked[:budget], ranked[budget:]
    print(f"    新技能候选: {len(candidates)}；保留: {len(kept)}；截断丢弃: {len(dropped)}")

    # -- 5) 组装 v2 skills ---------------------------------------------------
    used_ids = set(v1_ids)
    id_by_token: dict[str, str] = {}
    new_skill_rows: list[dict] = []
    new_skill_meta: dict[str, dict] = {}   # id -> {freq, rule}
    for key, info in kept:
        sid = slugify(key)
        if sid in used_ids:  # id 冲突则跳过，不覆盖旧技能
            continue
        used_ids.add(sid)
        id_by_token[key] = sid
        onet_hit = info["onet"]
        aliases = [key] + [a for a in info["aliases"] if norm_key(a) != key]
        row = {
            "id": sid,
            "name": display_name(key, onet_hit["example"] if onet_hit else None),
            "category": categorize(key),
            "hot": bool(onet_hit and onet_hit["hot"]),
            "aliases": clean_aliases(aliases),
        }
        new_skill_rows.append(row)
        new_skill_meta[sid] = {"freq": info["freq"], "rule": info["rule"]}
    new_skill_rows.sort(key=lambda r: r["id"])

    # 别名合并应用到旧技能
    merge_applied: dict[str, list[str]] = {}
    for key, sid in alias_merges.items():
        if unmapped[key] < NEW_SKILL_MIN_FREQ:
            # 低频也接受合并（只加别名，不新增技能）
            pass
        target = next(s for s in v1_skills if s["id"] == sid)
        if key not in [norm_key(a) for a in target["aliases"]]:
            target["aliases"].append(key)
            merge_applied.setdefault(sid, []).append(key)

    # -- 6) 旧技能校准：O*NET hot + ESCO 别名补充 -----------------------------
    hot_calibrated = 0
    esco_aliases_added = 0
    for s in v1_skills:
        keys = {norm_key(lab) for lab in [s["id"], s["name"], *s["aliases"]]}
        onet_matched = [onet[k] for k in sorted(keys) if k in onet]
        if onet_matched:
            onet_hot = any(m["hot"] for m in onet_matched)
            if onet_hot and not s["hot"]:
                s["hot"] = True
                hot_calibrated += 1
        # ESCO 别名补充
        existing = {norm_key(a) for a in s["aliases"]}
        extra: list[str] = []
        for k in sorted(keys):
            rec = esco.get(k)
            if not rec:
                continue
            for lab in clean_aliases(rec["alts"]):
                nk = norm_key(lab)
                if nk in existing or nk in alias_owner:
                    continue
                if not is_it_relevant(nk)[0]:
                    continue  # 剔除跨域同名技能的别名（如 finance 的 securities）
                if _is_versionish(nk):
                    continue  # python3 / py3k 类版本别名：匹配时归一化已兜底，不收
                # 新技能已占用的别名也不抢
                if any(nk == norm_key(a) for r in new_skill_rows for a in r["aliases"]):
                    continue
                extra.append(lab)
                existing.add(nk)
                if len(extra) >= MAX_EXTRA_ALIASES_PER_SKILL:
                    break
            if len(extra) >= MAX_EXTRA_ALIASES_PER_SKILL:
                break
        if extra:
            s["aliases"] = clean_aliases([*s["aliases"], *extra])
            esco_aliases_added += len(extra)

    # 新技能别名注册进 alias_owner 之前，先把映射表补全
    for key, sid in id_by_token.items():
        mapped[key] = sid
    for key, sid in alias_merges.items():
        mapped[key] = sid

    # -- 7) 汇总输出 ----------------------------------------------------------
    all_skills = v1_skills + sorted(new_skill_rows, key=lambda r: r["id"])
    by_category: dict[str, list[str]] = {}
    alias_to_id: dict[str, str] = {}
    id_to_name: dict[str, str] = {}
    all_aliases: list[str] = []
    for s in all_skills:
        by_category.setdefault(s["category"], []).append(s["id"])
        id_to_name[s["id"]] = s["name"]
        for lab in s["aliases"]:
            alias_to_id.setdefault(lab, s["id"])
            all_aliases.append(lab)

    final_mapped = sum(freq[k] for k in mapped if k in freq)
    coverage = final_mapped / total_tokens
    # 可寻址覆盖率：分母剔除黑名单命中的非 IT token（软技能/商务职能噪声）
    blacklist_tokens = sum(
        c for k, c in freq.items()
        if k not in mapped and IT_BLACKLIST.search(f" {k} ")
    )
    addressable = total_tokens - blacklist_tokens

    vocab = {
        "version": "v2",
        "total": len(all_skills),
        "hot_count": sum(1 for s in all_skills if s["hot"]),
        "categories": v1["categories"],
        "skills": all_skills,
        "alias_to_id": alias_to_id,
        "id_to_name": id_to_name,
        "by_category": by_category,
        "all_aliases": sorted(set(all_aliases)),
    }

    # 断言：275 个旧 id 全部存在
    missing = v1_ids - {s["id"] for s in all_skills}
    assert not missing, f"旧技能 id 丢失: {sorted(missing)}"
    assert len(all_skills) <= MAX_TOTAL

    V2_JSON.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> 写出 {V2_JSON}  total={vocab['total']} hot={vocab['hot_count']}")

    # -- 8) QC ----------------------------------------------------------------
    still_unmapped = [
        {"token": k, "count": c}
        for k, c in unmapped.items()
        if k not in mapped
    ]
    still_unmapped.sort(key=lambda r: -r["count"])
    qc = {
        "jd_total_tokens": total_tokens,
        "jd_unique_tokens": len(freq),
        "v1_base_coverage": round(base_mapped / total_tokens, 4),
        "mapped_tokens": final_mapped,
        "coverage": round(coverage, 4),
        "coverage_target": 0.80,
        "coverage_pass": bool(coverage > 0.80),
        "coverage_note": (
            "分母含全部 JD 技能 token；未映射部分大头是 spec 要求剔除的非 IT "
            "软技能/商务职能 token（见 blacklist_tokens），addressable_coverage "
            "为剔除这些噪声后的口径。"
        ),
        "blacklist_tokens": blacklist_tokens,
        "addressable_coverage": round(final_mapped / addressable, 4),
        "new_skills_count": len(new_skill_rows),
        "new_skills": [
            {
                "id": r["id"], "name": r["name"], "category": r["category"],
                "hot": r["hot"], "freq": new_skill_meta[r["id"]]["freq"],
                "rule": new_skill_meta[r["id"]]["rule"],
            }
            for r in sorted(new_skill_rows,
                            key=lambda r: -new_skill_meta[r["id"]]["freq"])
        ],
        "onet_hit_tokens": len(onet_hits),
        "esco_hit_tokens": len(esco_hits),
        "esco_aliases_added": esco_aliases_added,
        "hot_calibrated_up": hot_calibrated,
        "alias_merges": {sid: toks for sid, toks in sorted(merge_applied.items())},
        "rejected_rules": dict(rejected),
        "candidates_dropped_by_cap": [
            {"token": k, "count": v["freq"]} for k, v in dropped
        ],
        "top50_unmapped": still_unmapped[:50],
        "v1_ids_preserved": len(v1_ids),
        "assert_v1_ids_ok": True,
    }
    QC_JSON.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> 写出 {QC_JSON}")
    print(f"    覆盖率: {coverage:.2%}（v1 基线 {base_mapped / total_tokens:.2%}）；"
          f"新增技能: {len(new_skill_rows)}；O*NET 命中: {len(onet_hits)}；"
          f"ESCO 命中: {len(esco_hits)}；ESCO 别名补充: {esco_aliases_added}；"
          f"hot 校准上调: {hot_calibrated}")


if __name__ == "__main__":
    main()
