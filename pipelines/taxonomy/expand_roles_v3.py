"""A. 岗位体系校验与扩充 v3:把 v3 JD 数据集映射进 91 岗并数据驱动扩充新岗。

流程:
  1. 读 /data/shichaojian/JNIT/processed/jd_unified_v3_enriched(126k+ 纯 IT JD)。
  2. 用 fine_grained_roles_v2.json 的 search_keywords + example_titles 映射 title:
     - 关键词跨岗重复时按"关键词 token 与 role_name 重叠度"确定唯一属主
       (修复 v2 的 'forward deployed engineer' 同时挂在 Prompt Engineer 和
       Forward Deployed AI Engineer 下导致全部错位到 Prompt Engineer 的问题)。
     - 泛化单词关键词(other/qa/security/c++ 等)进停用表,不参与匹配
       (v2 部分岗关键词被污染,如 Mobile C++ Engineer / Cloud Security Engineer)。
     - 最长关键词优先 + 词边界匹配;seniority 前缀不用处理(子串匹配天然覆盖)。
  3. 报告每岗 JD 数、未映射 top50 高频 title、映射覆盖率。
  4. 未映射 title 中 JD >= 150 的人工归簇新岗(NEW_ROLE_CLUSTERS),
     只从"仍未映射"的 title 里收 JD,不抢已有岗;校验达标才成岗。
  5. 新岗从归属 JD 统计 example_titles / skill_freq / required-core-optional,
     role_id 从 role_090 续号。
  6. 产出:
     - data/gold/fine_grained_roles_v3.json(91 岗原样保留 + 新岗追加)
     - data/silver/jd_role_assignments_v3.parquet(job_id -> role_id,供画像/趋势复用)
     - data/gold/expand_roles_v3_qc.json(映射覆盖率 QC)

运行:python -m pipelines.taxonomy.expand_roles_v3
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
SILVER_DIR = ROOT / "data" / "silver"
JD_GLOB = "/data/shichaojian/JNIT/processed/jd_unified_v3_enriched/posted_month=*/part-0.parquet"

ROLES_V2_PATH = GOLD_DIR / "fine_grained_roles_v2.json"
ROLES_V3_PATH = GOLD_DIR / "fine_grained_roles_v3.json"
TAXONOMY_V2_PATH = GOLD_DIR / "role_taxonomy_v2.json"
TAXONOMY_V3_PATH = GOLD_DIR / "role_taxonomy_v3.json"
ASSIGN_PATH = SILVER_DIR / "jd_role_assignments_v3.parquet"
QC_PATH = GOLD_DIR / "expand_roles_v3_qc.json"
VOCAB_V2_PATH = GOLD_DIR / "skill_vocab_v2.json"

MIN_NEW_ROLE_JD = 150

# v2 关键词里被污染的泛化单词(单词太短/跨半数以上岗,无区分度)
GENERIC_KEYWORD_STOPLIST = {
    "other", "others", "lead", "qa", "security", "sql", "sysadmin", "devops",
    "android", "ios", ".net", "c++", "c#", "c", "r", "go", "java", "python",
    "frontend", "backend", "fullstack", "testing", "automation", "manager",
}

# 非 IT/噪声 title 模式(数据标注众包、实地杂工、非 IT 工程/设计/销售),
# 永不成岗,也不计入未映射报告 top50 的"候选新岗"判断(但仍报告)。
NOISE_TITLE_RE = re.compile(
    r"(field technician|video recording|participant|data contributor|"
    r"photo (data )?collector|data entry|pharmacy technician|"
    r"graphic designer|mechanical engineer|electrical engineer|"
    r"manufacturing engineer|real estate|account executive|"
    r"sales development|business development|customer success|"
    r"outreach|coordinator roster|team coordinator)"
)

# ---------------------------------------------------------------------------
# 人工归簇的新岗候选:从未映射 title 里按关键词收 JD,>=MIN_NEW_ROLE_JD 才成岗
# (keywords 同样最长优先,且不抢已有 91 岗已映射的 title)
# ---------------------------------------------------------------------------
NEW_ROLE_CLUSTERS = [
    {
        "role_name": "Site Reliability Engineer",
        "coarse_role": "Cloud Native & DevOps",
        "search_keywords": [
            "site reliability engineer", "sre engineer", "sre",
            "reliability engineer", "sr site reliability engineer",
        ],
    },
    {
        "role_name": "Backend Engineer (General)",
        "coarse_role": "Backend Development",
        "search_keywords": [
            "backend engineer", "back end engineer", "backend developer",
            "back-end engineer", "server engineer",
        ],
    },
    {
        "role_name": "Software Architect",
        "coarse_role": "General Engineering",
        "search_keywords": [
            "software architect", "technical architect", "principal architect",
            "senior architect", "staff architect", "lead architect",
        ],
    },
    {
        "role_name": "Infrastructure Engineer",
        "coarse_role": "Cloud Native & DevOps",
        "search_keywords": [
            "infrastructure engineer", "cloud infrastructure engineer",
            "platform infrastructure engineer", "it infrastructure engineer",
            "infrastructure developer",
        ],
    },
    {
        "role_name": "Cloud Engineer",
        "coarse_role": "Cloud Native & DevOps",
        "search_keywords": [
            "cloud engineer", "cloud operations engineer",
            "cloud platform engineer",
        ],
    },
    {
        "role_name": "Research Engineer",
        "coarse_role": "Emerging AI",
        "search_keywords": [
            "research engineer", "applied research engineer",
            "ai research engineer", "research software engineer",
        ],
    },
    {
        "role_name": "Mobile Engineer (General)",
        "coarse_role": "Mobile Development",
        "search_keywords": [
            "mobile engineer", "mobile application developer",
            "mobile app developer", "mobile developer",
        ],
    },
    {
        "role_name": "Product Analyst",
        "coarse_role": "Product & Business Analysis",
        "search_keywords": [
            "product analyst", "senior product analyst",
        ],
    },
    {
        "role_name": "Data Architect",
        "coarse_role": "AI & Data",
        "search_keywords": [
            "data architect", "senior data architect", "lead data architect",
        ],
    },
]


def norm_title(t: str) -> str:
    t = str(t).lower().strip()
    t = re.sub(r"[\u2013\u2014]", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _word_bounded(title: str, kw: str) -> bool:
    idx = title.find(kw)
    while idx != -1:
        before = title[idx - 1] if idx > 0 else " "
        end = idx + len(kw)
        after = title[end] if end < len(title) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        idx = title.find(kw, idx + 1)
    return False


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9+#.]+", s.lower()) if t}


class TitleRoleMapper:
    """关键词 → 唯一岗的映射器(跨岗重复关键词按 role_name 重叠度定属主)。"""

    def __init__(self, roles: list[dict]):
        self.roles = roles
        # 关键词 → [(role_idx, priority)];example_titles 只能属于本岗
        kw_owners: dict[str, list[int]] = {}
        for i, role in enumerate(roles):
            for kw in role.get("search_keywords") or []:
                k = norm_title(kw)
                if not k or k in GENERIC_KEYWORD_STOPLIST:
                    continue
                kw_owners.setdefault(k, []).append(i)

        self.kw_owner: dict[str, int] = {}
        shared = 0
        for kw, idxs in kw_owners.items():
            if len(idxs) == 1:
                self.kw_owner[kw] = idxs[0]
                continue
            shared += 1
            kwt = _tokens(kw)
            best_i = max(
                idxs,
                key=lambda i: (len(kwt & _tokens(roles[i]["role_name"])), -i),
            )
            self.kw_owner[kw] = best_i
        self.shared_keywords = shared

        # example_titles:精确匹配,只能归本岗
        self.exact_owner: dict[str, int] = {}
        for i, role in enumerate(roles):
            for t in role.get("example_titles") or []:
                self.exact_owner.setdefault(norm_title(t), i)

        # 最长优先:按关键词长度降序扫描
        self.kws_by_len = sorted(self.kw_owner, key=len, reverse=True)

    def match(self, title: str) -> tuple[int, str] | None:
        """返回 (role_idx, matched_text);exact example_title > 最长关键词。"""
        if title in self.exact_owner:
            return self.exact_owner[title], title
        for kw in self.kws_by_len:
            if _word_bounded(title, kw):
                return self.kw_owner[kw], kw
        return None


def load_jd_titles() -> list[str]:
    import glob as _glob
    files = sorted(_glob.glob(JD_GLOB))
    titles: list[str] = []
    for f in files:
        titles.extend(pq.read_table(f, columns=["title"])["title"].to_pylist())
    return titles


def main() -> dict:
    print(">>> 加载 v2 岗位体系(91 岗) ...")
    roles_v2 = json.loads(ROLES_V2_PATH.read_text(encoding="utf-8"))

    print(">>> 加载 JD title ...")
    titles = load_jd_titles()
    title_counts = Counter(norm_title(t) for t in titles)
    print(f"    JD 总数: {len(titles)},唯一 title: {len(title_counts)}")

    mapper = TitleRoleMapper(roles_v2)
    print(f"    有效关键词: {len(mapper.kw_owner)}(跨岗共享按属主归一 {mapper.shared_keywords} 个)")

    # ---- 1. 映射到 91 岗 ----
    assigned: dict[str, str] = {}  # norm_title -> role_id
    role_counts: Counter[str] = Counter()
    for t, c in title_counts.items():
        m = mapper.match(t)
        if m:
            role_id = roles_v2[m[0]]["role_id"]
            assigned[t] = role_id
            role_counts[role_id] += c

    mapped_rows = sum(role_counts.values())
    coverage = mapped_rows / len(titles)
    print(f">>> 初始映射: {mapped_rows}/{len(titles)} = {coverage:.2%}")

    # ---- 2. 未映射分析 ----
    unmapped = {t: c for t, c in title_counts.items() if t not in assigned}
    unmapped_rows = sum(unmapped.values())
    noise_rows = sum(
        c for t, c in unmapped.items() if NOISE_TITLE_RE.search(t)
    )
    print(f"    未映射: {unmapped_rows} 行(其中噪声/非 IT 约 {noise_rows} 行)")

    # ---- 3. 新岗归簇(只收未映射 title) ----
    new_roles: list[dict] = []
    dropped_clusters = []
    next_idx = len(roles_v2)
    for cluster in NEW_ROLE_CLUSTERS:
        kws = sorted(
            (norm_title(k) for k in cluster["search_keywords"]),
            key=len, reverse=True,
        )
        got: dict[str, int] = {}
        for t, c in unmapped.items():
            if t in assigned:
                continue
            for kw in kws:
                if _word_bounded(t, kw):
                    got[t] = c
                    assigned[t] = f"role_new_{cluster['role_name']}"
                    break
        jd_count = sum(got.values())
        row = {**cluster, "jd_count": jd_count,
               "matched_titles": dict(Counter(got).most_common(30))}
        if jd_count >= MIN_NEW_ROLE_JD:
            row["role_idx"] = next_idx
            next_idx += 1
            new_roles.append(row)
            role_counts[f"role_new_{cluster['role_name']}"] += jd_count
            print(f"    [新岗] {cluster['role_name']}: {jd_count} JD ✓")
        else:
            dropped_clusters.append(row)
            # 回滚分配
            for t in got:
                assigned.pop(t, None)
            print(f"    [放弃] {cluster['role_name']}: {jd_count} JD < {MIN_NEW_ROLE_JD}")

    # ---- 4. 生成 v3 岗位 JSON ----
    print(">>> 生成 fine_grained_roles_v3.json ...")
    vocab = json.loads(VOCAB_V2_PATH.read_text(encoding="utf-8"))
    id_to_name = vocab.get("id_to_name", {})
    alias_to_id = {k.lower(): v for k, v in (vocab.get("alias_to_id") or {}).items()}

    def slug_to_name(slug: str) -> str:
        return id_to_name.get(slug) or id_to_name.get(
            alias_to_id.get(slug.lower(), ""), slug
        )

    # 新岗的归属 JD 需要 skills/source 统计:重扫一遍
    print(">>> 统计新岗 JD 技能分布(重扫数据) ...")
    new_role_by_title = {
        t: rid for t, rid in assigned.items() if rid.startswith("role_new_")
    }
    new_stats: dict[str, dict] = {
        f"role_new_{c['role_name']}": {
            "skill_hits": Counter(), "jd_count": 0,
            "titles": Counter(), "sources": Counter(),
        }
        for c in new_roles
    }
    import glob as _glob
    for f in sorted(_glob.glob(JD_GLOB)):
        tbl = pq.read_table(f, columns=["title", "skills", "source"])
        for title, skills, source in zip(
            tbl["title"].to_pylist(), tbl["skills"].to_pylist(), tbl["source"].to_pylist()
        ):
            rid = new_role_by_title.get(norm_title(title))
            if not rid:
                continue
            st = new_stats[rid]
            st["jd_count"] += 1
            st["titles"][norm_title(title)] += 1
            st["sources"][str(source)] += 1
            for s in skills or []:
                st["skill_hits"][str(s)] += 1

    roles_v3 = [dict(r) for r in roles_v2]  # 91 岗原样保留
    for c in new_roles:
        rid = f"role_new_{c['role_name']}"
        st = new_stats[rid]
        n = st["jd_count"] or 1
        freq = {s: round(cnt / n, 4) for s, cnt in st["skill_hits"].most_common(60)}
        ordered = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        core_ids = [s for s, f in ordered[:10] if f >= 0.10]
        required_ids = [s for s, f in ordered if 0.05 <= f < 0.10][:20]
        optional_ids = [s for s, f in ordered if 0.02 <= f < 0.05][:20]
        role_id = f"role_{c['role_idx']:03d}"
        for t in list(assigned):
            if assigned[t] == rid:
                assigned[t] = role_id
        role_counts[role_id] = role_counts.pop(rid, 0)
        role = {
            "role_id": role_id,
            "role_name": c["role_name"],
            "fine_role": c["role_name"],
            "coarse_role": c["coarse_role"],
            "coarse_key": re.sub(r"[^a-z0-9]+", "_", c["coarse_role"].lower()).strip("_"),
            "size": n,
            "source_mix": dict(st["sources"]),
            "search_keywords": c["search_keywords"],
            "example_titles": [t.title() for t, _ in st["titles"].most_common(12)],
            "keywords": sorted(_tokens(" ".join(c["search_keywords"])) - {"engineer"}),
            "required_skills": [slug_to_name(s) for s in required_ids],
            "required_skill_ids": required_ids,
            "core_skills": [slug_to_name(s) for s in core_ids],
            "core_skill_ids": core_ids,
            "optional_skills": [slug_to_name(s) for s in optional_ids],
            "optional_skill_ids": optional_ids,
            "skill_freq": {slug_to_name(s): f for s, f in freq.items()},
        }
        roles_v3.append(role)
        print(f"    {role_id} {c['role_name']}: core={len(core_ids)} required={len(required_ids)}")

    ROLES_V3_PATH.write_text(
        json.dumps(roles_v3, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"    写出 {ROLES_V3_PATH}({len(roles_v3)} 岗)")

    # ---- 3b. 岗位 taxonomy v3(91 原样保留 + 新岗追加,agent /v1/roles 用) ----
    if TAXONOMY_V2_PATH.exists():
        taxonomy_v3 = json.loads(TAXONOMY_V2_PATH.read_text(encoding="utf-8"))
        existing_ids = {r.get("role_id") for r in taxonomy_v3}
        for role in roles_v3:
            if role["role_id"] in existing_ids:
                continue
            taxonomy_v3.append({
                "role_id": role["role_id"],
                "category": role.get("coarse_role", "Other"),
                "canonical_role": role["role_name"],
                "aliases": [k.lower() for k in role.get("search_keywords") or []],
                "top_skills": list(role.get("core_skills") or [])[:10],
                "existing_jd_count": role.get("size", 0),
            })
        TAXONOMY_V3_PATH.write_text(
            json.dumps(taxonomy_v3, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"    写出 {TAXONOMY_V3_PATH}({len(taxonomy_v3)} 岗)")

    # ---- 5. 保存 title->role_id 映射表(画像/趋势复用) ----
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    tbl = pa.table(
        {
            "title_norm": list(assigned.keys()),
            "role_id": list(assigned.values()),
        }
    )
    pq.write_table(tbl, ASSIGN_PATH)
    print(f"    写出 {ASSIGN_PATH}({len(assigned)} 个 title)")

    # ---- 6. QC ----
    per_role = [
        {"role_id": r["role_id"], "role_name": r["role_name"], "jd_count": role_counts.get(r["role_id"], 0)}
        for r in roles_v3
    ]
    per_role.sort(key=lambda x: -x["jd_count"])
    unmapped_top50 = [
        {"title": t, "count": c, "noise": bool(NOISE_TITLE_RE.search(t))}
        for t, c in Counter(unmapped).most_common(50)
    ]
    qc = {
        "inputs": {"jd_total": len(titles), "unique_titles": len(title_counts),
                   "roles_v2": len(roles_v2)},
        "mapping": {
            "mapped_rows": sum(role_counts.values()),
            "coverage_initial": round(coverage, 4),
            "unmapped_rows": unmapped_rows,
            "noise_rows_in_unmapped": noise_rows,
            "coverage_after_new_roles": round(sum(role_counts.values()) / len(titles), 4),
            "shared_keywords_deduped": mapper.shared_keywords,
        },
        "summary": {"v2_roles": len(roles_v2), "new_roles": len(new_roles),
                    "v3_total": len(roles_v3),
                    "min_new_role_jd": MIN_NEW_ROLE_JD},
        "new_roles": [
            {k: c[k] for k in ("role_name", "coarse_role", "jd_count")} for c in new_roles
        ],
        "dropped_clusters": [
            {k: c[k] for k in ("role_name", "jd_count")} for c in dropped_clusters
        ],
        "per_role_jd_counts": per_role,
        "unmapped_top50": unmapped_top50,
    }
    qc["mapping"]["coverage_after_new_roles"] = round(
        sum(role_counts.values()) / len(titles), 4
    )
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    写出 {QC_PATH}")

    print("\n# 映射覆盖率")
    print(f"  初始(91 岗): {coverage:.2%}")
    print(f"  最终(含新岗): {qc['mapping']['coverage_after_new_roles']:.2%}")
    print("\n# 每岗 JD 数 top10 / bottom10")
    for r in per_role[:10]:
        print(f"  {r['jd_count']:6d}  {r['role_id']} {r['role_name']}")
    for r in per_role[-10:]:
        print(f"  {r['jd_count']:6d}  {r['role_id']} {r['role_name']}")
    print("\n# 未映射 top30(★=噪声/非 IT,永不入岗)")
    for r in unmapped_top50[:30]:
        flag = "★" if r["noise"] else " "
        print(f"  {flag} {r['count']:5d}  {r['title'][:80]}")
    return qc


if __name__ == "__main__":
    main()
