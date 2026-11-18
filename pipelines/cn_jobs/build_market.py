"""把官网采集的国内岗位加工成后端直接读取的“国内市场”产物。

    python -m pipelines.cn_jobs.build_market

输入：data/cn_jobs/jobs_ledger.jsonl.gz、company_daily.json（由 collect.py 生成）
输出：data/gold/cn_market_v1.json
  - summary        在招岗位数、公司/城市/职能分布、采集天数
  - skills         国内在招岗位的技能需求占比（与全球样本占比对照）
  - roles          99 个细粒度岗位在国内的在招数、主要公司/城市、核心技能、经验要求、示例岗位
  - companies      每家公司的在招数、近 7/30 天新增与下架、热门岗位方向
  - daily          每天的在招总数与新增数（随每日采集累积，形成真实的国内时间序列）
技能抽取：skill_vocab_v2 的中英文别名词典匹配 + 本文件补充的中文同义词。
岗位归类：按中文岗位名的规则表映射到 role_profiles_v3 的 99 个岗位，未命中再按技能重合度兜底。
"""
from __future__ import annotations

import collections
import datetime as dt
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CN_DIR = ROOT / "data" / "cn_jobs"
GOLD = ROOT / "data" / "gold"
OUT = GOLD / "cn_market_v1.json"

# 词表里缺的常见中文写法 -> skill_id
CN_SKILL_ALIASES = {
    "llm": ["大模型", "大语言模型", "语言模型", "基座模型", "预训练模型"],
    "agent": ["智能体", "agent"],
    "rag": ["检索增强"],
    "multimodal": ["多模态"],
    "aigc": ["aigc", "生成式ai", "生成式人工智能"],
    "fine-tuning": ["微调", "sft", "后训练", "指令微调"],
    "reinforcement-learning": ["强化学习", "rlhf"],
    "computer-vision": ["计算机视觉", "图像识别", "视觉算法", "图像处理"],
    "nlp": ["自然语言处理", "nlp"],
    "recommendation-system": ["推荐系统", "推荐算法", "推荐策略"],
    "distributed-systems": ["分布式系统", "分布式架构", "分布式计算", "分布式存储"],
    "microservices": ["微服务"],
    "high-availability": ["高可用", "高并发"],
    "performance-tuning": ["性能优化", "性能调优"],
    "data-warehouse": ["数据仓库", "数仓"],
    "data-analysis": ["数据分析"],
    "machine-learning": ["机器学习"],
    "deep-learning": ["深度学习", "神经网络"],
    "cloud-computing": ["云计算", "云原生"],
    "kubernetes": ["k8s"],
    "linux": ["linux"],
    "algorithms": ["数据结构与算法", "算法基础", "算法能力"],
    "data-structures": ["数据结构"],
    "embedded": ["嵌入式"],
    "cybersecurity": ["网络安全", "信息安全", "安全攻防"],
    "penetration-testing": ["渗透测试"],
    "qa-automation": ["自动化测试"],
    "product-management": ["产品规划", "需求分析", "产品设计"],
    "project-management": ["项目管理"],
    "statistics": ["统计学", "统计分析"],
    "cpp": ["c/c++", "c++"],
    "go": ["golang", "go语言"],
    "unity": ["unity"],
    "android": ["安卓"],
    "message-queue": ["消息队列"],
    "caching": ["缓存"],
    "search": [],
}

# 岗位归类规则：按顺序命中第一条（中文岗位名 + 职能类别）
ROLE_RULES: list[tuple[str, str]] = [
    (r"策划", "role_062"),
    (r"产品经理|产品策划|产品专家|产品负责人|策略产品", "role_066"),
    (r"推理(加速|引擎|优化|框架|系统)|推理部署|模型推理", "role_008"),
    (r"智能体|agent", "role_001"),
    (r"\brag\b|检索增强|知识库问答", "role_011"),
    (r"提示词|prompt", "role_009"),
    (r"(模型|大模型|ai|算法).{0,4}评测|评测.{0,4}(模型|算法)", "role_005"),
    (r"(ai|大模型|训练)数据|数据标注|语料", "role_003"),
    (r"(ai|机器学习|训练|大模型|异构|gpu|算力).{0,4}(平台|infra|基础设施|框架|系统)|ai ?infra|mlops", "role_016"),
    (r"视觉|图像|cv\b|多模态|视频理解|3d|感知算法|ocr", "role_012"),
    (r"研究员|科学家|research", "role_004"),
    (r"大模型|llm|aigc|生成式|ai应用|ai工程|人工智能", "role_002"),
    (r"推荐|搜索|广告算法|nlp|自然语言|语音|算法|机器学习|深度学习|策略模型", "role_000"),
    (r"数据架构", "role_098"),
    (r"数据仓库|数仓|数据开发|etl|大数据|数据平台|数据湖|实时计算|离线计算|数据工程", "role_017"),
    (r"数据科学", "role_019"),
    (r"数据分析|商业分析|经营分析|bi\b|数据产品分析|业务分析", "role_069"),
    (r"dba|数据库(运维|管理)", "role_020"),
    (r"测试开发|自动化测试|测试平台", "role_049"),
    (r"游戏测试|测试|质量保障|qa\b|质量", "role_072"),
    (r"渗透|攻防|红队|漏洞挖掘|安全研究", "role_057"),
    (r"安全运营|应急响应|soc\b|威胁情报", "role_056"),
    (r"云安全", "role_047"),
    (r"安全(研发|开发)", "role_058"),
    (r"(网络|信息|数据|系统|应用|终端|主机|业务|移动)安全|安全(工程|专家|开发|架构|合规|技术)|风控技术|反作弊", "role_084"),
    (r"sre|稳定性|可靠性|可观测", "role_091"),
    (r"运维开发|devops|效能|ci/?cd|研发工具", "role_041"),
    (r"网络(工程|运维|开发|研发|架构)|网络工程师", "role_078"),
    (r"运维|系统管理|系统工程", "role_043"),
    (r"it支持|桌面|it服务|it运营", "role_073"),
    (r"云原生|容器|kubernetes|k8s|基础架构|基础设施|存储|计算平台|虚拟化|操作系统|内核", "role_094"),
    (r"云(平台|计算|产品|服务)", "role_095"),
    (r"平台(研发|开发|工程)|中台", "role_079"),
    (r"react native|跨端", "role_033"),
    (r"flutter", "role_038"),
    (r"ios", "role_036"),
    (r"android|安卓", "role_037"),
    (r"鸿蒙|harmony|客户端|移动端|app开发", "role_097"),
    (r"虚幻|unreal|\bue\d?\b|游戏引擎|引擎开发|引擎研发|图形|渲染", "role_061"),
    (r"unity", "role_059"),
    (r"技术美术|\bta\b", "role_063"),
    (r"游戏(客户端|服务端|开发|研发|程序)", "role_060"),
    (r"vue", "role_032"),
    (r"前端|web开发|h5", "role_029"),
    (r"全栈", "role_031"),
    (r"嵌入式|驱动|固件|芯片|bsp|硬件|fpga|soc\b|单片机", "role_083"),
    (r"区块链|web3", "role_068"),
    (r"解决方案架构", "role_077"),
    (r"架构师", "role_093"),
    (r"解决方案|售前|技术支持|tam\b|客户成功|技术服务|交付工程", "role_076"),
    (r"技术项目经理|tpm|项目管理|pmo", "role_080"),
    (r"项目经理", "role_064"),
    (r"交互|视觉设计|ui|ux|设计师|体验设计", "role_040"),
    (r"研发经理|技术经理|技术负责人|技术专家|leader|总监", "role_075"),
    (r"产品(?!.*运营)", "role_066"),
    (r"java", "role_021"),
    (r"golang|go开发|go研发|\bgo\b", "role_027"),
    (r"c\+\+|c/c\+\+", "role_026"),
    (r"python", "role_025"),
    (r"php", "role_024"),
    (r"node", "role_023"),
    (r"后端|服务端|server", "role_092"),
    (r"工程师|开发|研发|程序", "role_071"),
]
_ROLE_RULES = [(re.compile(p, re.I), rid) for p, rid in ROLE_RULES]


def _read_jsonl_gz(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def build_matcher():
    vocab = json.loads((GOLD / "skill_vocab_v2.json").read_text(encoding="utf-8"))["skills"]
    items = vocab if isinstance(vocab, list) else list(vocab.values())
    names = {}
    alias_map: dict[str, set[str]] = collections.defaultdict(set)
    for s in items:
        sid = s.get("id") or s.get("skill_id")
        if not sid:
            continue
        names[sid] = s.get("name") or sid
        for a in [s.get("name") or "", *(s.get("aliases") or [])]:
            a = a.strip().lower()
            if len(a) >= 2 or _has_cjk(a):
                alias_map[sid].add(a)
    for sid, extra in CN_SKILL_ALIASES.items():
        if sid in names:
            alias_map[sid].update(e.lower() for e in extra)
    cjk_terms, latin_terms = [], []
    for sid, aliases in alias_map.items():
        for a in aliases:
            (cjk_terms if _has_cjk(a) else latin_terms).append((a, sid))
    # 英文别名要求两侧不是字母数字，避免 “go” 命中 “google”；中文别名直接子串匹配
    latin_terms.sort(key=lambda x: -len(x[0]))
    pattern = re.compile(r"(?<![a-z0-9+#.])(" + "|".join(re.escape(a) for a, _ in latin_terms) + r")(?![a-z0-9+#])")
    latin_lookup = {a: sid for a, sid in latin_terms}

    def match(text: str) -> list[str]:
        t = (text or "").lower()
        found = {latin_lookup[m.group(1)] for m in pattern.finditer(t)}
        found.update(sid for a, sid in cjk_terms if a in t)
        found.discard("search")
        return sorted(found)

    return match, names


def assign_role(title: str, category: str) -> str:
    text = f"{title} {category}"
    for rx, rid in _ROLE_RULES:
        if rx.search(title):
            return rid
    for rx, rid in _ROLE_RULES:
        if rx.search(text):
            return rid
    return "role_071"


_EXP = [("应届/1年以内", r"应届|不限|1年以下|一年以下|0-1|实习"), ("1-3年", r"1-3|1年|一年|2年|两年|二年"),
        ("3-5年", r"3-5|3年|三年|4年"), ("5-10年", r"5-10|5年|五年|6年|8年"), ("10年以上", r"10年|十年")]


def exp_bucket(job: dict) -> str:
    text = job.get("experience") or ""
    if not text:
        m = re.search(r"(\d+)\s*年(以上|及以上)?(的)?[^，。；\n]{0,12}(经验|工作)", job.get("requirement") or "")
        text = f"{m.group(1)}年" if m else ""
    for label, rx in _EXP:
        if re.search(rx, text):
            return label
    return "未注明"


def share(counter: collections.Counter, total: int, top: int) -> list[dict]:
    return [{"name": k, "count": v, "share": round(v / total, 4)} for k, v in counter.most_common(top)] if total else []


def main() -> None:
    ledger = _read_jsonl_gz(CN_DIR / "jobs_ledger.jsonl.gz")
    if not ledger:
        raise SystemExit("data/cn_jobs/jobs_ledger.jsonl.gz 不存在，先运行 python -m pipelines.cn_jobs.collect")
    days = sorted({json.loads(l)["date"] for l in (CN_DIR / "collect_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()})
    match, skill_names = build_matcher()
    roles_doc = json.loads((GOLD / "role_profiles_v3.json").read_text(encoding="utf-8"))
    roles = roles_doc["roles"] if isinstance(roles_doc["roles"], list) else list(roles_doc["roles"].values())
    role_by_id = {r["role_id"]: r for r in roles}
    from app.services.role_i18n import role_zh

    from pipelines.cn_jobs.collect import is_domestic, is_it_job
    # 过滤规则会迭代，台账里的旧记录在这里按最新规则再筛一遍
    ledger = [j for j in ledger if is_it_job(j["title"], j.get("category", ""))]
    for j in ledger:
        j["cities"] = [c for c in j["cities"] if is_domestic([c])] or j["cities"]
        j["city"] = j["cities"][0] if j["cities"] else ""
    ledger = [j for j in ledger if is_domestic(j["cities"])]
    active = [j for j in ledger if j.get("active")]
    for j in active:
        j["skills"] = match(" ".join([j["title"], j.get("description", ""), j.get("requirement", "")]))
        j["role_id"] = assign_role(j["title"], j.get("category", ""))
        j["exp"] = exp_bucket(j)
    # 规则兜底(role_071)的岗位再走 Qwen3 语义近邻：标题+职能+JD 开头向量 vs 99 个岗位锚点，
    # 相似度 >= 阈值才改派；结果按文本哈希缓存，每日只对没见过的岗位编码
    fb_jobs = [j for j in active if j["role_id"] == "role_071"]
    if fb_jobs:
        try:
            from pipelines.cn_jobs.role_semantic import SemanticRoleAssigner, job_key_text

            items = {}
            for j in fb_jobs:
                k, t = job_key_text(j)
                items[k] = t
                j["_sem_key"] = k
            sem = SemanticRoleAssigner(role_by_id).assign(items)
            n_re = 0
            for j in fb_jobs:
                hit = sem.get(j["_sem_key"])
                if hit:
                    j["role_id"] = hit[0]
                    n_re += 1
            print(f"[cn_market] 语义兜底改派 {n_re}/{len(fb_jobs)} 个岗位")
        except Exception as e:  # 模型不可用时保持规则兜底
            print(f"[cn_market] 语义兜底跳过: {e}")
    n = len(active)
    last_day = max(j["last_seen"] for j in ledger)

    def open_on(jobs, d):   # 第 d 天在招：首次出现 <= d <= 最后出现
        return sum(1 for j in jobs if j["first_seen"] <= d <= j["last_seen"])

    # ---- 技能需求（国内在招占比 vs 全球样本近 6 个月占比）
    skill_cnt = collections.Counter(s for j in active for s in j["skills"])
    global_share = {}
    try:
        panel = json.loads((GOLD / "skill_trend_panel_v3.json").read_text(encoding="utf-8"))
        for sid, v in panel["skills"].items():
            m = [x for x in v.get("monthly", []) if not x.get("low_coverage")][-6:]
            tot = sum(panel["total_jd_by_month"].get(x["month"], 0) for x in m)
            global_share[sid] = round(sum(x["count"] for x in m) / tot, 4) if tot else None
    except (OSError, KeyError, ValueError):
        pass
    fresh = [j for j in active if j["first_seen"] >= _shift(last_day, -6) and j["first_seen"] != days[0]]
    fresh_cnt = collections.Counter(s for j in fresh for s in j["skills"])
    skills = [{"skill_id": sid, "name": skill_names.get(sid, sid), "count": c, "share_cn": round(c / n, 4),
               "share_new_7d": round(fresh_cnt[sid] / len(fresh), 4) if len(fresh) >= 200 else None,
               "share_global": global_share.get(sid),
               "companies": dict(collections.Counter(j["company"] for j in active if sid in j["skills"]).most_common(6))}
              for sid, c in skill_cnt.most_common(120)]

    # ---- 岗位
    by_role = collections.defaultdict(list)
    for j in active:
        by_role[j["role_id"]].append(j)
    role_rows = []
    for rid, jobs in sorted(by_role.items(), key=lambda kv: -len(kv[1])):
        r = role_by_id.get(rid, {})
        sk = collections.Counter(s for j in jobs for s in j["skills"])
        recent = sorted(jobs, key=lambda j: j.get("posted_at") or "", reverse=True)
        role_rows.append({
            "role_id": rid, "role_name": r.get("role_name", rid), "role_zh": role_zh(r.get("role_name")),
            "coarse_role": r.get("coarse_role"), "open_roles": len(jobs), "share": round(len(jobs) / n, 4),
            "companies": share(collections.Counter(j["company"] for j in jobs), len(jobs), 8),
            "cities": share(collections.Counter(c for j in jobs for c in (j["cities"] or ["未注明"])), len(jobs), 10),
            "experience": share(collections.Counter(j["exp"] for j in jobs), len(jobs), 6),
            "top_skills": [{"skill_id": s, "name": skill_names.get(s, s), "share": round(c / len(jobs), 4)}
                           for s, c in sk.most_common(15)],
            "new_7d": sum(1 for j in jobs if j["first_seen"] >= _shift(last_day, -6) and j["first_seen"] != days[0]),
            "new_7d_note": "首日采集的岗位不计为新增",
            "samples": [{"title": j["title"], "company": j["company"], "city": j["city"], "posted_at": j.get("posted_at"),
                         "url": j["url"]} for j in recent[:8]],
        })

    # ---- 公司（按统一过滤口径，从台账重算每天的在招/新增/下架）
    from pipelines.cn_jobs.collect import COMPANIES
    AGGREGATOR_SOURCES = {"iguopin", "mohrss"}  # 聚合平台：company 字段是真实雇主名，不生成单一"公司卡片"
    companies = []
    for src, (cn_name, en_name) in COMPANIES.items():
        if src in AGGREGATOR_SOURCES:
            continue
        all_jobs = [j for j in ledger if j["source"] == src]
        if not all_jobs:
            continue
        series = []
        for i, d in enumerate(days):
            prev = days[i - 1] if i else None
            series.append({"date": d, "open_roles": open_on(all_jobs, d),
                           "new_roles": 0 if i == 0 else sum(1 for j in all_jobs if j["first_seen"] == d),
                           "closed_roles": 0 if i == 0 else sum(1 for j in all_jobs if j["last_seen"] == prev)})
        latest = series[-1]
        jobs = [j for j in active if j["source"] == src]

        def delta(k, series=series, latest=latest):
            past = [s for s in series if s["date"] <= _shift(latest["date"], -k)]
            return None if not past else latest["open_roles"] - past[-1]["open_roles"]

        companies.append({
            "source": src, "company": cn_name, "company_en": en_name,
            "open_roles": len(jobs), "momentum_7d": delta(7), "momentum_30d": delta(30),
            "new_7d": sum(s["new_roles"] for s in series[-7:]), "days_observed": len(series), "daily": series[-90:],
            "top_roles": [{"role_id": k, "role_zh": role_zh(role_by_id.get(k, {}).get("role_name")), "count": v}
                          for k, v in collections.Counter(j["role_id"] for j in jobs).most_common(6)],
            "top_cities": share(collections.Counter(j["city"] or "未注明" for j in jobs), len(jobs), 6),
        })
    companies.sort(key=lambda c: -c["open_roles"])

    daily = [{"date": d, "open_roles": open_on(ledger, d),
              "new_roles": 0 if i == 0 else sum(1 for j in ledger if j["first_seen"] == d)}
             for i, d in enumerate(days)]

    doc = {
        "version": "cn_market_v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "国内科技公司官网社招页面（" + "、".join(c["company"] for c in companies) + "）+ 国聘与中国公共招聘网两个聚合平台，每日采集",
        "as_of": last_day, "first_day": days[0] if days else last_day, "days_observed": len(days),
        "summary": {
            "open_roles": n, "n_companies": len(companies),
            "companies": share(collections.Counter(j["company"] for j in active), n, 20),
            "cities": share(collections.Counter(j["city"] or "未注明" for j in active), n, 20),
            "coarse_roles": share(collections.Counter(role_by_id.get(j["role_id"], {}).get("coarse_role", "其他") for j in active), n, 15),
            "experience": share(collections.Counter(j["exp"] for j in active), n, 6),
            "skill_coverage": round(sum(1 for j in active if j["skills"]) / n, 4) if n else 0,
        },
        "daily": daily,
        "skills": skills,
        "roles": role_rows,
        "companies": companies,
        "notes": [
            "open_roles 为官网当天在招的 IT 相关社招岗位数（按岗位名/职能类别过滤）；字节跳动接口单次最多返回 10000 条，实际在招数更高。",
            "官网不公开薪资，国内薪资另见公开数据集口径；时间序列从首次采集日开始逐日累积。",
            "岗位归类为规则映射，技能为词典匹配，二者都可能有少量误差。",
        ],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    unmatched = sum(1 for j in active if j["role_id"] == "role_071")
    print(f"[cn_market] {n} active jobs, {len(role_rows)} roles, {len(skills)} skills, "
          f"general-fallback={unmatched} ({unmatched / max(n, 1):.1%}), skill_coverage={doc['summary']['skill_coverage']}")
    print(f"[cn_market] -> {OUT}")


def _shift(day: str, delta_days: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=delta_days)).isoformat()


if __name__ == "__main__":
    main()
