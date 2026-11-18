"""B. 岗位画像 v3:从 126k v3 JD + title→role 映射构建全岗真实画像。

输入:
  - data/silver/jd_role_assignments_v3.parquet(expand_roles_v3 产出,title_norm→role_id)
  - /data/shichaojian/JNIT/processed/jd_unified_v3_enriched(126,628 JD)
  - data/gold/fine_grained_roles_v3.json(99 岗)

每岗产出(data/gold/role_profiles_v3.json):
  - skill_freq       近期加权频率:指数衰减 half-life=12 个月(2026 的 JD 权重远高于 2024),
                     键为 v3 技能图 skill_id
  - core/required/optional 技能按加权频率阈值划分(阈值是模块顶部常量,可调):
      core     = 加权频率 top10 且 >= 0.10
      required = 加权频率 >= 0.15(top 25)
      optional = 0.05 <= 加权频率 < 0.15(top 25)
  - salary           median/p25/p75(USD 年薪,取 min/max 中点;样本量 < 10 不输出)
  - remote_ratio / seniority_distribution / employment_type_distribution
  - jd_count / jd_count_6m(近 6 个自然月)
  - monthly_jd_counts + monthly_shares(该岗 JD 数 / 当月全部已映射 JD 数)
  - trend_momentum   = mean(近 3 月 share) / mean(之前 3 月 share) - 1;
                     分母为 0 时 null(下游归一化按持平 0.5 处理)
  - low_confidence   = jd_count < 50

QC(data/gold/role_profiles_v3_qc.json):jd_count / 技能数 / 薪资非空率分布、
阈值说明、low_confidence 岗清单。

运行:python -m pipelines.taxonomy.build_role_profiles_v3
     # 默认:v3 输入/输出,行为与历史一致
     python -m pipelines.taxonomy.build_role_profiles_v3 \
       --jd-glob "/data/shichaojian/JNIT/processed/jd_unified_v4_enriched/posted_month=*/part-0.parquet" \
       --output data/gold/role_profiles_v4.json \
       --qc-output data/gold/role_profiles_v4_qc.json \
       --extra-vocab data/gold/skill_vocab_v4.json \
       --version v4 --generated-from jd_unified_v4_enriched
     # v4 增强数据集重建:--extra-vocab 传入 v4 补充词表后,v4 新抽的
     # 161 个工具/平台技能以 canonical skill_id 进入 skill_freq
     # (不做此指定时这些技能不在 v3 图/词表内,会被丢弃,与历史行为一致)
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
SILVER_DIR = ROOT / "data" / "silver"
JD_GLOB = "/data/shichaojian/JNIT/processed/jd_unified_v3_enriched/posted_month=*/part-0.parquet"

ASSIGN_PATH = SILVER_DIR / "jd_role_assignments_v3.parquet"
ROLES_V3_PATH = GOLD_DIR / "fine_grained_roles_v3.json"
SKILL_GRAPH_PATH = GOLD_DIR / "skill_prerequisite_v3.json"
VOCAB_V2_PATH = GOLD_DIR / "skill_vocab_v2.json"
OUTPUT_PATH = GOLD_DIR / "role_profiles_v3.json"
QC_PATH = GOLD_DIR / "role_profiles_v3_qc.json"

# --- 阈值(可调,QC 报告会记录实际值) ---
HALF_LIFE_MONTHS = 12.0
CORE_TOP_N = 10
CORE_MIN_FREQ = 0.10
REQUIRED_MIN_FREQ = 0.15
OPTIONAL_MIN_FREQ = 0.05
MAX_LISTED_SKILLS = 25
MAX_FREQ_SKILLS = 60
SALARY_MIN_SAMPLE = 10
LOW_CONFIDENCE_JD = 50
MOMENTUM_RECENT_MONTHS = 3


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jd-glob", default=JD_GLOB, help="JD parquet 分区 glob")
    p.add_argument("--output", default=str(OUTPUT_PATH), help="画像输出 json")
    p.add_argument("--qc-output", default=str(QC_PATH), help="QC 输出 json")
    p.add_argument("--extra-vocab", default=None,
                   help="可选补充技能词表(如 skill_vocab_v4.json):其 canonical "
                        "skill_id 与 alias 也会参与 JD 技能映射(历史上这些技能被丢弃)")
    p.add_argument("--version", default="v3", help="payload version 字段")
    p.add_argument("--generated-from", default="jd_unified_v3_enriched",
                   help="payload generated_from 字段")
    return p.parse_args(argv)


def month_key(ts) -> str | None:
    if ts is None:
        return None
    return f"{ts.year:04d}-{ts.month:02d}"


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float64), q * 100.0))


def main(argv: list[str] | None = None) -> dict:
    args = _parse_args(argv)
    output_path = Path(args.output)
    qc_path = Path(args.qc_output)

    print(">>> 加载岗位体系 / 映射表 / 技能图 ...")
    roles = json.loads(ROLES_V3_PATH.read_text(encoding="utf-8"))
    role_by_id = {r["role_id"]: r for r in roles}
    assign = pq.read_table(ASSIGN_PATH).to_pandas()
    title2role = dict(zip(assign["title_norm"], assign["role_id"]))
    graph = json.loads(SKILL_GRAPH_PATH.read_text(encoding="utf-8"))
    graph_ids = {s["skill_id"] for s in graph["skills"]}
    vocab = json.loads(VOCAB_V2_PATH.read_text(encoding="utf-8"))
    alias_to_id = {k.lower(): v for k, v in (vocab.get("alias_to_id") or {}).items()}
    id_to_name = dict(vocab.get("id_to_name") or {})

    # 可选补充词表(v4):canonical skill_id + alias 参与映射,展示名取首个 alias
    extra_ids: set[str] = set()
    extra_alias: dict[str, str] = {}
    if args.extra_vocab:
        extra_vocab = json.loads(Path(args.extra_vocab).read_text(encoding="utf-8"))
        extra_ids = {str(k).strip().lower() for k in (extra_vocab.get("skills") or {})}
        for alias, canonical in (extra_vocab.get("alias_to_canonical") or {}).items():
            canonical = str(canonical).strip().lower()
            if canonical in extra_ids:
                extra_alias[str(alias).strip().lower()] = canonical
        for canonical, info in (extra_vocab.get("skills") or {}).items():
            aliases = (info or {}).get("aliases") or []
            display = str(aliases[0]).strip() if aliases else str(canonical)
            id_to_name.setdefault(str(canonical).strip().lower(), display)
        print(f"    补充词表 {args.extra_vocab}: {len(extra_ids)} 技能, {len(extra_alias)} 别名")

    def to_graph_id(slug: str) -> str | None:
        slug = str(slug).strip().lower()
        if slug in extra_ids:
            return slug
        sid = slug if slug in graph_ids else alias_to_id.get(slug)
        if sid in graph_ids:
            return sid
        return extra_alias.get(slug)

    # ---- 单遍扫描 JD ----
    print(">>> 扫描 JD 数据集(单遍聚合) ...")
    stats: dict[str, dict] = {
        rid: {
            "jd_count": 0, "weighted_total": 0.0,
            "skill_w": Counter(), "months": Counter(),
            "salary_mid": [], "remote": 0, "seniority": Counter(),
            "employment": Counter(),
        }
        for rid in role_by_id
    }
    import glob as _glob
    all_month_totals: Counter[str] = Counter()
    total_rows = 0
    ref_month = (0, 0)  # (year, month) 数据里最新月份

    files = sorted(_glob.glob(args.jd_glob))
    # 参考月 = 分区名里最新月份(文件按月份排序,先定下来再做衰减,避免两遍口径)
    part_months = [
        m.group(1) for f in files
        if (m := re.search(r"posted_month=(\d{4}-\d{2})", f))
    ]
    ref_month = (max((int(p[:4]), int(p[5:7])) for p in part_months)
                 if part_months else (0, 0))
    for f in files:
        part_month = re.search(r"posted_month=(\d{4}-\d{2}|unknown)", f)
        part_month = part_month.group(1) if part_month else None
        tbl = pq.read_table(
            f,
            columns=["title", "posted_at", "skills", "salary_min_annual_usd",
                     "salary_max_annual_usd", "is_remote", "seniority", "employment_type"],
        )
        titles = tbl["title"].to_pylist()
        posted = tbl["posted_at"].to_pylist()
        skills_col = tbl["skills"].to_pylist()
        smin = tbl["salary_min_annual_usd"].to_pylist()
        smax = tbl["salary_max_annual_usd"].to_pylist()
        remote = tbl["is_remote"].to_pylist()
        seniority = tbl["seniority"].to_pylist()
        emp = tbl["employment_type"].to_pylist()
        for i in range(len(titles)):
            total_rows += 1
            t = str(titles[i] or "").lower().strip()
            t = re.sub(r"[\u2013\u2014]", "-", t)
            t = re.sub(r"\s+", " ", t)
            rid = title2role.get(t)
            m = month_key(posted[i]) or part_month
            if rid is None:
                if m and m != "unknown":
                    all_month_totals[m] += 1
                continue
            st = stats[rid]
            st["jd_count"] += 1
            if m and m != "unknown":
                st["months"][m] += 1
                all_month_totals[m] += 1
                y, mo = int(m[:4]), int(m[5:7])
                months_ago = (ref_month[0] - y) * 12 + (ref_month[1] - mo)
                w = 0.5 ** (max(months_ago, 0) / HALF_LIFE_MONTHS)
            else:
                w = 1.0
            st["weighted_total"] += w
            for s in {to_graph_id(x) for x in (skills_col[i] or [])}:
                if s:
                    st["skill_w"][s] += w
            lo, hi = smin[i], smax[i]
            if lo is not None or hi is not None:
                mid = ((lo or hi) + (hi or lo)) / 2.0
                if 5000 <= mid <= 500000:  # 防御异常值
                    st["salary_mid"].append(mid)
            if remote[i]:
                st["remote"] += 1
            if seniority[i]:
                st["seniority"][str(seniority[i])] += 1
            if emp[i]:
                st["employment"][str(emp[i])] += 1

    print(f"    数据最新月份: {ref_month[0]:04d}-{ref_month[1]:02d}")

    # ---- 组装画像 ----
    print(">>> 组装岗位画像 ...")
    all_months = sorted(all_month_totals)
    last6 = all_months[-6:]
    recent3 = all_months[-MOMENTUM_RECENT_MONTHS:]
    prev3 = all_months[-2 * MOMENTUM_RECENT_MONTHS:-MOMENTUM_RECENT_MONTHS]

    profiles = []
    for role in roles:
        rid = role["role_id"]
        st = stats[rid]
        n = st["jd_count"]
        wtot = st["weighted_total"] or 1e-9

        freq = {s: round(c / wtot, 4) for s, c in st["skill_w"].most_common(MAX_FREQ_SKILLS)}
        ordered = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        core_ids = [s for s, f in ordered[:CORE_TOP_N] if f >= CORE_MIN_FREQ]
        required_ids = [s for s, f in ordered if f >= REQUIRED_MIN_FREQ][:MAX_LISTED_SKILLS]
        optional_ids = [s for s, f in ordered
                        if OPTIONAL_MIN_FREQ <= f < REQUIRED_MIN_FREQ][:MAX_LISTED_SKILLS]

        monthly_counts = {m: st["months"].get(m, 0) for m in all_months}
        monthly_shares = {
            m: round(cnt / all_month_totals[m], 6)
            for m, cnt in monthly_counts.items() if all_month_totals[m]
        }
        r3 = [monthly_shares.get(m, 0.0) for m in recent3]
        p3 = [monthly_shares.get(m, 0.0) for m in prev3]
        momentum = None
        if p3 and sum(p3) > 0:
            momentum = round(sum(r3) / len(r3) / (sum(p3) / len(p3)) - 1.0, 4)

        salary_vals = st["salary_mid"]
        salary = None
        if len(salary_vals) >= SALARY_MIN_SAMPLE:
            salary = {
                "currency": "USD",
                "sample_size": len(salary_vals),
                "median": round(_quantile(salary_vals, 0.5), 0),
                "p25": round(_quantile(salary_vals, 0.25), 0),
                "p75": round(_quantile(salary_vals, 0.75), 0),
            }

        profiles.append({
            "role_id": rid,
            "role_name": role["role_name"],
            "fine_role": role.get("fine_role", role["role_name"]),
            "coarse_role": role.get("coarse_role", ""),
            "jd_count": n,
            "jd_count_6m": sum(monthly_counts.get(m, 0) for m in last6),
            "skill_freq": freq,
            "core_skills": [id_to_name.get(s, s) for s in core_ids],
            "core_skill_ids": core_ids,
            "required_skills": [id_to_name.get(s, s) for s in required_ids],
            "required_skill_ids": required_ids,
            "optional_skills": [id_to_name.get(s, s) for s in optional_ids],
            "optional_skill_ids": optional_ids,
            "salary": salary,
            "salary_nonnull_count": len(salary_vals),
            "remote_ratio": round(st["remote"] / n, 4) if n else None,
            "seniority_distribution": {
                k: round(v / n, 4) for k, v in st["seniority"].most_common()
            } if n else {},
            "employment_type_distribution": {
                k: round(v / n, 4) for k, v in st["employment"].most_common()
            } if n else {},
            "monthly_jd_counts": [
                {"month": m, "count": cnt} for m, cnt in monthly_counts.items()
            ],
            "monthly_shares": monthly_shares,
            "trend_momentum": momentum,
            "low_confidence": n < LOW_CONFIDENCE_JD,
        })

    payload = {
        "version": args.version,
        "generated_from": args.generated_from,
        "half_life_months": HALF_LIFE_MONTHS,
        "ref_month": f"{ref_month[0]:04d}-{ref_month[1]:02d}",
        "thresholds": {
            "core": f"top{CORE_TOP_N} & >= {CORE_MIN_FREQ}",
            "required": f">= {REQUIRED_MIN_FREQ}",
            "optional": f"[{OPTIONAL_MIN_FREQ}, {REQUIRED_MIN_FREQ})",
        },
        "total_jd": total_rows,
        "assigned_jd": sum(p["jd_count"] for p in profiles),
        "assignment_rate": round(
            sum(p["jd_count"] for p in profiles) / total_rows, 4
        ),
        "months": all_months,
        "roles": profiles,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    写出 {output_path}({len(profiles)} 岗)")

    # ---- QC ----
    counts = sorted(p["jd_count"] for p in profiles)
    n_skills = sorted(len(p["skill_freq"]) for p in profiles)
    salary_rates = [p["salary_nonnull_count"] / p["jd_count"] for p in profiles if p["jd_count"]]
    low_conf = [p["role_id"] for p in profiles if p["low_confidence"]]

    def _dist(vals: list[int]) -> dict:
        if not vals:
            return {}
        arr = np.asarray(vals, dtype=np.float64)
        return {
            "min": int(arr.min()), "p25": float(np.percentile(arr, 25)),
            "median": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)), "max": int(arr.max()),
            "mean": round(float(arr.mean()), 1),
        }

    qc = {
        "inputs": {"jd_total": payload["total_jd"],
                   "assigned_jd": payload["assigned_jd"],
                   "assignment_rate": round(payload["assigned_jd"] / payload["total_jd"], 4),
                   "roles": len(profiles)},
        "thresholds": payload["thresholds"],
        "half_life_months": HALF_LIFE_MONTHS,
        "ref_month": payload["ref_month"],
        "momentum_windows": {"recent": recent3, "previous": prev3},
        "jd_count_distribution": _dist(counts),
        "skill_count_distribution": _dist(n_skills),
        "salary_nonnull_rate": {
            "mean": round(float(np.mean(salary_rates)), 4) if salary_rates else None,
            "roles_with_salary": sum(1 for p in profiles if p["salary"]),
            "roles_without_salary": sum(1 for p in profiles if not p["salary"]),
        },
        "low_confidence_roles": low_conf,
        "n_low_confidence": len(low_conf),
        "momentum_stats": {
            "n_with_momentum": sum(1 for p in profiles if p["trend_momentum"] is not None),
            "n_null": sum(1 for p in profiles if p["trend_momentum"] is None),
            "top5_up": sorted(
                ((p["role_id"], p["role_name"], p["trend_momentum"])
                 for p in profiles if p["trend_momentum"] is not None),
                key=lambda x: -x[2])[:5],
            "top5_down": sorted(
                ((p["role_id"], p["role_name"], p["trend_momentum"])
                 for p in profiles if p["trend_momentum"] is not None),
                key=lambda x: x[2])[:5],
        },
    }
    qc_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    写出 {qc_path}")

    print("\n# QC 摘要")
    print(f"  映射 JD: {qc['inputs']['assigned_jd']}/{qc['inputs']['jd_total']}"
          f" = {qc['inputs']['assignment_rate']:.2%}")
    print(f"  jd_count 分布: {qc['jd_count_distribution']}")
    print(f"  技能数分布: {qc['skill_count_distribution']}")
    print(f"  薪资非空率(mean): {qc['salary_nonnull_rate']['mean']}"
          f"(有薪资画像 {qc['salary_nonnull_rate']['roles_with_salary']} 岗)")
    print(f"  low_confidence(<{LOW_CONFIDENCE_JD} JD): {qc['n_low_confidence']} 岗")
    print(f"  trend_momentum 非空: {qc['momentum_stats']['n_with_momentum']},"
          f" 为 0 prev: {qc['momentum_stats']['n_null']}")
    print("  top5 上升:", [(n, m) for _, n, m in qc['momentum_stats']['top5_up']])
    print("  top5 下降:", [(n, m) for _, n, m in qc['momentum_stats']['top5_down']])
    return qc


if __name__ == "__main__":
    main()
