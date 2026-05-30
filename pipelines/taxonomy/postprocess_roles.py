"""
岗位库后处理 V2 - 基于人工审定决策生成最终岗位库

输入:
  data/gold/fine_grained_roles_v1.json (cluster_roles.py 的 91 个原始簇产物)
  pipelines/taxonomy/role_decisions.json (人工审定决策表)

输出:
  data/gold/fine_grained_roles_v1.json   (最终 70 个独立岗位,覆盖输入)
  data/gold/job_skill_profile_v1.json    (配套技能画像,给推荐器用)
  data/gold/role_name_mapping_v1.json    (91->70 映射,答辩材料 + 可追溯)

并自动备份原 fine_grained_roles_v1.json 为 fine_grained_roles_RAW_{ts}.json

运行:
  python -m pipelines.taxonomy.postprocess_roles
可选:
  POSTPROCESS_DRY_RUN=1   只打印不写文件
  POSTPROCESS_BACKUP=0    不备份
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path

RAW_JSON = Path("data/gold/fine_grained_roles_RAW.json")   # 输入:91 个原始簇(只读)
ROLES_JSON = Path("data/gold/fine_grained_roles_v1.json")  # 输出:最终岗位库
PROFILE_JSON = Path("data/gold/job_skill_profile_v1.json")
MAPPING_JSON = Path("data/gold/role_name_mapping_v1.json")
DECISIONS_JSON = Path("pipelines/taxonomy/role_decisions.json")

DRY_RUN = os.environ.get("POSTPROCESS_DRY_RUN") == "1"
BACKUP = os.environ.get("POSTPROCESS_BACKUP", "1") == "1"

TOP_SKILLS = 15
TOP_TITLES = 8
TOP_KEYWORDS = 8
CORE_THRESHOLD = 0.30      # 频率 >= 0.30 算核心技能(算缺口)
OPTIONAL_THRESHOLD = 0.15  # 0.15 <= 频率 < 0.30 算加分技能(展示不算缺口)

COARSE_ORDER = [
    "Emerging AI", "AI & Data", "Backend Development", "Frontend Development",
    "Mobile Development", "Cloud Native & DevOps", "QA & Testing", "Security",
    "Game Development", "Product & Business Analysis", "Other IT",
]


def _final_name(decision):
    """decision 可能是 [name, conf, note] 或 {'final_name':...}。"""
    if isinstance(decision, list):
        return decision[0]
    if isinstance(decision, dict):
        return decision.get("final_name")
    return decision


def load_inputs():
    if not RAW_JSON.exists():
        raise FileNotFoundError(f"未找到 {ROLES_JSON},请先运行 cluster_roles")
    if not DECISIONS_JSON.exists():
        raise FileNotFoundError(f"未找到 {DECISIONS_JSON},请把 role_decisions.json 放到 pipelines/taxonomy/ 下")
    with RAW_JSON.open(encoding="utf-8") as f:
        roles = json.load(f)
    with DECISIONS_JSON.open(encoding="utf-8") as f:
        decisions = json.load(f)
    return roles, decisions


def validate_decisions(roles, decisions):
    role_ids = {r["role_id"] for r in roles}
    decided = set(decisions.keys())
    missing = role_ids - decided
    extra = decided - role_ids
    if missing:
        raise ValueError(f"decisions 缺少这些原始簇: {missing}")
    if extra:
        print(f"  WARN decisions 里有多余 id(忽略): {extra}")


def merge_roles(source_roles, final_name):
    skill_counter = Counter()
    skill_id_by_name = {}
    skill_freq_weighted = defaultdict(float)  # 技能 -> 加权频率累加(频率 × size)
    skill_id_full = {}                          # 全量技能 id 映射(不止 top15)
    title_counter = Counter()
    keyword_counter = Counter()
    search_kw_counter = Counter()
    source_mix = Counter()
    total_size = 0
    coarse_role = source_roles[0].get("coarse_role", "")
    coarse_key = source_roles[0].get("coarse_key", "")

    for r in source_roles:
        total_size += r.get("size", 0)
        source_mix.update(r.get("source_mix", {}))
        weight = r.get("size", 1)

        for name, sid in zip(r.get("required_skills", []), r.get("required_skill_ids", [])):
            skill_counter[name] += weight
            skill_id_by_name.setdefault(name, sid)

        # 用簇内频率按 size 加权,合并后还原成加权平均频率
        freq_map = r.get("skill_freq", {})
        for name, freq in freq_map.items():
            skill_freq_weighted[name] += freq * weight

        # 记录全量技能的 id(skill_freq 里有 top15 之外的技能)
        for name, sid in zip(r.get("required_skills", []), r.get("required_skill_ids", [])):
            skill_id_full.setdefault(name, sid)

        for t in r.get("example_titles", []):
            if t:
                title_counter[t] += r.get("size", 1)
        for kw in r.get("keywords", []):
            if kw:
                keyword_counter[kw] += r.get("size", 1)
        for skw in r.get("search_keywords", []):
            if skw:
                search_kw_counter[skw] += r.get("size", 1)

    top_skill_names = [n for n, _ in skill_counter.most_common(TOP_SKILLS)]
    top_skill_ids = [skill_id_by_name.get(n) for n in top_skill_names]
    
    # 还原加权平均频率(除以总 size)
    merged_freq = {
        name: round(w / total_size, 4)
        for name, w in skill_freq_weighted.items()
    } if total_size else {}

    # 按频率分 core / optional(阈值 + 保底 + 封顶,适配"泛技能高频+具体技能分散"的真实分布)
    CORE_MIN, CORE_FALLBACK, CORE_MAX = 0.20, 0.12, 5
    OPT_MIN, OPT_MAX = 0.08, 5

    ranked = sorted(merged_freq.items(), key=lambda x: -x[1])  # 按频率降序
    core_skills = [name for name, freq in ranked if freq >= CORE_MIN]
    # 不足 3 个 → 放宽到 CORE_FALLBACK 补够 3 个
    if len(core_skills) < 3:
        for name, freq in ranked:
            if name not in core_skills and freq >= CORE_FALLBACK:
                core_skills.append(name)
            if len(core_skills) >= 3:
                break
    core_skills = core_skills[:CORE_MAX]  # 封顶 5 个

    # optional:core 之外、频率 >= OPT_MIN,最多 5 个
    optional_skills = [
        name for name, freq in ranked
        if name not in core_skills and freq >= OPT_MIN
    ][:OPT_MAX]

    core_skill_ids = [skill_id_full.get(n) for n in core_skills]
    optional_skill_ids = [skill_id_full.get(n) for n in optional_skills]

    return {
        "role_name": final_name,
        "fine_role": final_name,
        "coarse_role": coarse_role,
        "coarse_key": coarse_key,
        "size": total_size,
        "source_mix": dict(source_mix),
        "search_keywords": [k for k, _ in search_kw_counter.most_common(TOP_KEYWORDS)],
        "example_titles": [t for t, _ in title_counter.most_common(TOP_TITLES)],
        "keywords": [k for k, _ in keyword_counter.most_common(TOP_KEYWORDS)],
        "required_skills": top_skill_names,        # 保留:兼容旧逻辑,top15 画像
        "required_skill_ids": top_skill_ids,
        "core_skills": core_skills,                # 新增:核心技能(算缺口)
        "core_skill_ids": core_skill_ids,
        "optional_skills": optional_skills,        # 新增:加分技能(展示不算缺口)
        "optional_skill_ids": optional_skill_ids,
        "skill_freq": merged_freq,                 # 新增:合并后的技能频率
        "_source_role_ids": [r["role_id"] for r in source_roles],
    }


def build_final_roles(roles, decisions):
    name_to_sources = defaultdict(list)
    dropped = []
    for r in roles:
        decision = decisions.get(r["role_id"])
        if not decision:
            continue
        fname = _final_name(decision)
        if fname == "DROP":
            dropped.append(r["role_id"])
            continue
        name_to_sources[fname].append(r)

    merged = [merge_roles(src, name) for name, src in name_to_sources.items()]

    def sort_key(role):
        try:
            order = COARSE_ORDER.index(role.get("coarse_role", "Other IT"))
        except ValueError:
            order = 99
        return (order, -role.get("size", 0), role.get("role_name", ""))

    merged.sort(key=sort_key)
    for idx, role in enumerate(merged):
        role["role_id"] = f"role_{idx:03d}"
    return merged, dropped


def build_mapping(final_roles, decisions, original_roles):
    original_by_id = {r["role_id"]: r for r in original_roles}
    mapping = {
        "summary": {
            "original_clusters": len(original_roles),
            "final_roles": len(final_roles),
            "dropped_clusters": sum(1 for d in decisions.values() if _final_name(d) == "DROP"),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "final_roles": {},
        "dropped_clusters": {},
    }
    for role in final_roles:
        sources_info = []
        for sid in role.get("_source_role_ids", []):
            orig = original_by_id.get(sid, {})
            d = decisions.get(sid)
            conf = d[1] if isinstance(d, list) and len(d) > 1 else None
            note = d[2] if isinstance(d, list) and len(d) > 2 else None
            sources_info.append({
                "original_role_id": sid,
                "original_name": orig.get("role_name", ""),
                "original_size": orig.get("size", 0),
                "confidence": conf,
                "note": note,
            })
        mapping["final_roles"][role["role_id"]] = {
            "final_name": role["role_name"],
            "coarse_role": role["coarse_role"],
            "total_size": role["size"],
            "merged_count": len(role.get("_source_role_ids", [])),
            "merged_from": sources_info,
        }
    for sid, d in decisions.items():
        if _final_name(d) != "DROP":
            continue
        orig = original_by_id.get(sid, {})
        conf = d[1] if isinstance(d, list) and len(d) > 1 else None
        note = d[2] if isinstance(d, list) and len(d) > 2 else None
        mapping["dropped_clusters"][sid] = {
            "original_name": orig.get("role_name", ""),
            "coarse_role": orig.get("coarse_role", ""),
            "original_size": orig.get("size", 0),
            "confidence": conf,
            "drop_reason": note,
        }
    return mapping


def write_outputs(final_roles, mapping):
    output_roles = [{k: v for k, v in r.items() if not k.startswith("_")} for r in final_roles]
    profile = {}
    for role in output_roles:
        profile[role["role_id"]] = {
            "role_name": role["role_name"],
            "fine_role": role["fine_role"],
            "coarse_role": role["coarse_role"],
            "required_skills": role["required_skills"],
            "required_skill_ids": role["required_skill_ids"],
            "core_skills": role.get("core_skills", []),
            "core_skill_ids": role.get("core_skill_ids", []),
            "optional_skills": role.get("optional_skills", []),
        }
    ROLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with ROLES_JSON.open("w", encoding="utf-8") as f:
        json.dump(output_roles, f, ensure_ascii=False, indent=2)
    with PROFILE_JSON.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    with MAPPING_JSON.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def backup_raw():
    if not BACKUP or not ROLES_JSON.exists():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    bp = ROLES_JSON.with_name(f"fine_grained_roles_RAW_{ts}.json")
    shutil.copy2(ROLES_JSON, bp)
    return bp


def _print_roles(final_roles):
    cur = None
    for role in final_roles:
        if role["coarse_role"] != cur:
            cur = role["coarse_role"]
            print(f"\n  -- {cur} --")
        merged = len(role.get("_source_role_ids", []))
        tag = f"  (合并自 {merged} 簇)" if merged > 1 else ""
        print(f"  [{role['role_id']}] {role['role_name']:45s} n={role['size']}{tag}")


def main():
    print(">>> 1/4 读取输入 ...")
    roles, decisions = load_inputs()
    print(f"    原始簇: {len(roles)} 个 | 决策: {len(decisions)} 条")
    validate_decisions(roles, decisions)

    print(">>> 2/4 按决策合并 ...")
    final_roles, dropped = build_final_roles(roles, decisions)
    print(f"    DROP: {len(dropped)} | 最终岗位: {len(final_roles)}")
    print(f"    大类分布: {dict(Counter(r['coarse_role'] for r in final_roles))}")

    print(">>> 3/4 构造映射 ...")
    mapping = build_mapping(final_roles, decisions, roles)

    print(">>> 4/4 写出 ...")
    if DRY_RUN:
        print("    [DRY_RUN] 未写文件")
        _print_roles(final_roles)
        return
    if BACKUP:
        bp = backup_raw()
        if bp:
            print(f"    已备份: {bp}")
    write_outputs(final_roles, mapping)
    print(f"    已写: {ROLES_JSON}")
    print(f"    已写: {PROFILE_JSON}")
    print(f"    已写: {MAPPING_JSON}")
    _print_roles(final_roles)


if __name__ == "__main__":
    main()