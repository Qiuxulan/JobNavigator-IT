"""趋势面板 v2：role × month 月度面板重建（抗抓取量偏差版）。

现版病灶：原始 JD 计数月度波动被数据源抓取量主导（2026-06 ~5万 → 2026-07 ~8.1万
→ 2026-08 掉到 2.6k），不是真实需求变化。本模块用 jd_share（岗位 JD 数 / 当月全库
IT JD 总量）作为主信号——份额对抓取总量缩放不敏感。

输入（跟随 monthly v3 链路，2026-11-06 重接线）：
  - data/silver/jd_role_assignments_v3.parquet  (expand_roles_v3 产出，title_norm→role_id，
    v3 目录 99 岗空间；缺文件回退旧版 /processed/jd_role_assignments.parquet，v2 91 岗空间)
  - /data/shichaojian/JNIT/processed/jd_unified_v3_enriched/posted_month=*/part-0.parquet
    (unify_jd_v3 + enrich_skills_v3 的真实产出；posted_month 只在分区目录名里，
    salary 已折 USD 年化：salary_min/max_annual_usd)
  - data/gold/fine_grained_roles_v3.json  (岗位目录，缺文件回退 v2→v1)

输出：
  - /data/shichaojian/JNIT/processed/trend_panel_v2.parquet
  - data/gold/trend_panel_v2.json        (按岗位嵌套，供 API 直接读)
  - data/gold/trend_panel_v2_qc.json     (QC：每岗位有效月数、稀疏岗位、demand_index 分布)

红线：不用未来数据填历史（不做跨越观测缺口的 ffill）；无数据月份保持 NaN 并标
low_confidence，由下游 forecast 自行决定如何处理。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ASSIGN_V3_PATH = Path("data/silver/jd_role_assignments_v3.parquet")
ASSIGN_LEGACY_PATH = Path("/data/shichaojian/JNIT/processed/jd_role_assignments.parquet")
UNIFIED_GLOB = "/data/shichaojian/JNIT/processed/jd_unified_v3_enriched/posted_month=*/part-0.parquet"


def _roles_path() -> Path:
    for v in ("v3", "v2", "v1"):
        p = Path(f"data/gold/fine_grained_roles_{v}.json")
        if p.exists():
            return p
    raise FileNotFoundError("data/gold/fine_grained_roles_v3/v2/v1.json 均不存在")


ROLES_PATH = _roles_path()

PANEL_OUT_PATH = Path("/data/shichaojian/JNIT/processed/trend_panel_v2.parquet")
PANEL_JSON_PATH = Path("data/gold/trend_panel_v2.json")
QC_PATH = Path("data/gold/trend_panel_v2_qc.json")

MONTH_START = "2020-01"  # 月末由数据决定：统一 JD 里观测到的最大 posted_month

# low_confidence 阈值：当月全库总量过低（抓取覆盖不足）或该岗 JD 数过少（份额噪声大）
TOTAL_MIN = 500
ROLE_COUNT_MIN = 10

SENIORITY_LEVELS = ["internship", "junior", "mid", "senior", "lead"]


def month_range(start: str, end: str) -> list[str]:
    """闭区间 [start, end] 的连续 YYYY-MM 列表。"""
    months = pd.period_range(start=start, end=end, freq="M")
    return [str(m) for m in months]


def norm_title(t: str) -> str:
    """与 expand_roles_v3 同口径的 title 归一化（小写、统一破折号、压缩空白）。"""
    import re
    t = str(t).lower().strip()
    t = re.sub(r"[\u2013\u2014]", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t


def load_unified() -> pd.DataFrame:
    files = sorted(Path("/").glob(UNIFIED_GLOB.lstrip("/")))
    cols = ["job_id", "title", "salary_min_annual_usd", "salary_max_annual_usd",
            "is_remote", "seniority"]
    frames = []
    for f in files:
        part = pd.read_parquet(f, columns=cols)
        # posted_month 只在 hive 分区目录名里（posted_month=YYYY-MM），从路径补
        pm = next((seg.split("=", 1)[1] for seg in f.parts
                   if seg.startswith("posted_month=")), None)
        if pm is None:
            raise ValueError(f"{f}: 无 posted_month 分区信息")
        part["posted_month"] = pm
        frames.append(part)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["posted_month"].str.fullmatch(r"\d{4}-\d{2}")]  # 排除 unknown 分区
    return df


def usd_mid(df: pd.DataFrame) -> pd.Series:
    """(min+max)/2 年化 USD 中点；jd_unified_v3_enriched 薪资已折 USD 年化。"""
    mid = (pd.to_numeric(df["salary_min_annual_usd"], errors="coerce")
           + pd.to_numeric(df["salary_max_annual_usd"], errors="coerce")) / 2.0
    return mid.astype("float64")


def load_assignments(unified: pd.DataFrame) -> pd.DataFrame:
    """job_id/role_id/posted_month 岗位归属。

    优先用 expand_roles_v3 的 title_norm→role_id 映射（v3 目录 99 岗空间）从
    unified title 现场展开；映射文件缺失时回退旧版
    /processed/jd_role_assignments.parquet（v2 91 岗空间，job_id 已就绪）。
    """
    if ASSIGN_V3_PATH.exists():
        title2role = pd.read_parquet(ASSIGN_V3_PATH)
        col_t, col_r = title2role.columns[:2]
        mapping = dict(zip(title2role[col_t].astype(str), title2role[col_r].astype(str)))
        assign = unified[["job_id", "title", "posted_month"]].copy()
        assign["role_id"] = assign["title"].map(lambda t: mapping.get(norm_title(t)))
        assign = assign.dropna(subset=["role_id"])
        print(f"[build_panel] assignments 来自 {ASSIGN_V3_PATH} "
              f"({len(mapping)} 个 title → {assign['role_id'].nunique()} 岗)")
    else:
        print(f"[build_panel] 警告: {ASSIGN_V3_PATH} 不存在，"
              f"回退旧版 {ASSIGN_LEGACY_PATH}")
        assign = pd.read_parquet(ASSIGN_LEGACY_PATH)
    return assign


def build_panel() -> tuple[pd.DataFrame, dict]:
    roles = json.loads(ROLES_PATH.read_text(encoding="utf-8"))
    role_meta = {r["role_id"]: r["role_name"] for r in roles}

    unified = load_unified()
    unified["usd_mid"] = usd_mid(unified)

    # 当月全库 IT JD 总量（jd_share 的分母；这就是抗抓取量偏差的关键）
    total_month = unified.groupby("posted_month")["job_id"].size().rename("total_month")

    month_end = str(unified["posted_month"].max())  # 数据观测到的最新月份
    assign = load_assignments(unified)
    # 关联统一 JD 的薪资/远程/级别字段（title 映射展开的 job_id 天然落在 unified 内）
    keep = ["job_id", "usd_mid", "is_remote", "seniority"]
    merged = assign[["job_id", "role_id", "posted_month"]].merge(
        unified[keep].drop_duplicates("job_id"), on="job_id", how="left")
    merged["is_remote"] = merged["is_remote"].astype("float64")  # NA 保持 NaN，不计入分母

    months = month_range(MONTH_START, month_end)

    def agg_role(g: pd.DataFrame) -> pd.DataFrame:
        grp = g.groupby("posted_month")
        out = pd.DataFrame({
            "jd_count": grp.size(),
            "salary_mid": grp["usd_mid"].median(),
            "remote_ratio": grp["is_remote"].mean(),
        })
        for lv in SENIORITY_LEVELS:
            out[f"seniority_{lv}"] = grp["seniority"].apply(lambda s: (s == lv).mean())
        out = out.reindex(months)  # 无观测月份保持 NaN（红线：不做跨缺口 ffill）
        out["jd_count"] = out["jd_count"].fillna(0)  # 全库有数据而岗位无匹配 = 观测到的 0
        return out

    parts = []
    for role_id in sorted(role_meta):
        g = merged[merged["role_id"] == role_id]
        p = agg_role(g)
        p["role_id"] = role_id
        parts.append(p.reset_index(names="month"))

    panel = pd.concat(parts, ignore_index=True)
    panel = panel.merge(total_month, left_on="month", right_index=True, how="left")
    panel["jd_share"] = panel["jd_count"] / panel["total_month"]
    panel["low_confidence"] = (
        (panel["total_month"] < TOTAL_MIN) | (panel["jd_count"] < ROLE_COUNT_MIN)
    )

    # demand_index：岗位内 jd_share 的 min-max 归一化（0-1），基于全部观测到的份额
    share_min = panel.groupby("role_id")["jd_share"].transform("min")
    share_max = panel.groupby("role_id")["jd_share"].transform("max")
    span = (share_max - share_min).replace(0, np.nan)
    panel["demand_index"] = ((panel["jd_share"] - share_min) / span).clip(0, 1)

    panel = panel[["role_id", "month", "jd_count", "total_month", "jd_share",
                   "demand_index", "salary_mid", "remote_ratio", "low_confidence"]
                  + [f"seniority_{lv}" for lv in SENIORITY_LEVELS]]
    qc = build_qc(panel, role_meta, total_month, month_end)
    return panel, qc


def build_qc(panel: pd.DataFrame, role_meta: dict, total_month: pd.Series,
             month_end: str) -> dict:
    qc_roles = {}
    sparse_roles = []
    di_samples = []
    for role_id, g in panel.groupby("role_id"):
        g = g.sort_values("month")
        valid = g[~g["low_confidence"]]
        di = g["demand_index"].dropna()
        di_samples.extend(di.tolist())
        total_cnt = int(g["jd_count"].sum())
        entry = {
            "role_name": role_meta[role_id],
            "total_jd_count": total_cnt,
            "reliable_months": int(len(valid)),
            "low_confidence_months": int(g["low_confidence"].sum()),
            "salary_coverage_months": int(g["salary_mid"].notna().sum()),
            "demand_index_mean": round(float(di.mean()), 4) if len(di) else None,
        }
        if total_cnt < 50:
            entry["sparse"] = True
            sparse_roles.append({"role_id": role_id, "role_name": role_meta[role_id],
                                 "total_jd_count": total_cnt})
        qc_roles[role_id] = entry

    di_arr = np.array(di_samples)
    return {
        "panel": {
            "n_roles": panel["role_id"].nunique(),
            "n_months": panel["month"].nunique(),
            "n_rows": int(len(panel)),
            "month_range": [MONTH_START, month_end],
            "signal": "jd_share = role jd_count / total_month (抗抓取量偏差主信号)",
            "low_confidence_rule": f"total_month < {TOTAL_MIN} OR jd_count < {ROLE_COUNT_MIN}",
            "salary_note": "salary_mid 为 USD 年化 (min+max)/2 的月中位数；"
                           "jd_unified_v3_enriched 薪资列已折 USD 年化，无需汇率折算",
        },
        "total_month": {m: int(c) for m, c in total_month.items()},
        "sparse_roles": sparse_roles,
        "demand_index_distribution": {
            "n": int(len(di_arr)),
            "mean": round(float(di_arr.mean()), 4),
            "std": round(float(di_arr.std()), 4),
            "p05": round(float(np.percentile(di_arr, 5)), 4),
            "p25": round(float(np.percentile(di_arr, 25)), 4),
            "p50": round(float(np.percentile(di_arr, 50)), 4),
            "p75": round(float(np.percentile(di_arr, 75)), 4),
            "p95": round(float(np.percentile(di_arr, 95)), 4),
        },
        "roles": qc_roles,
    }


def write_outputs(panel: pd.DataFrame, qc: dict) -> None:
    PANEL_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(PANEL_OUT_PATH, index=False)

    roles = json.loads(ROLES_PATH.read_text(encoding="utf-8"))
    name_of = {r["role_id"]: r["role_name"] for r in roles}

    def rnd(x, nd=6):
        try:
            return round(float(x), nd)
        except (TypeError, ValueError):
            return None

    nested = {}
    for role_id, g in panel.groupby("role_id"):
        g = g.sort_values("month")
        nested[role_id] = {
            "role_id": role_id,
            "role_name": name_of[role_id],
            "months": g["month"].tolist(),
            "jd_count": [int(x) for x in g["jd_count"]],
            "total_month": [None if pd.isna(x) else int(x) for x in g["total_month"]],
            "jd_share": [rnd(x) for x in g["jd_share"]],
            "demand_index": [rnd(x, 4) for x in g["demand_index"]],
            "salary_mid": [rnd(x, 0) for x in g["salary_mid"]],
            "remote_ratio": [rnd(x, 4) for x in g["remote_ratio"]],
            "low_confidence": [bool(x) for x in g["low_confidence"]],
            "seniority": {
                lv: [rnd(x, 4) for x in g[f"seniority_{lv}"]] for lv in SENIORITY_LEVELS
            },
        }
    PANEL_JSON_PATH.write_text(json.dumps(nested, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    panel, qc = build_panel()
    write_outputs(panel, qc)
    p = qc["panel"]
    print(f"panel: {p['n_roles']} roles × {p['n_months']} months = {p['n_rows']} rows")
    print(f"sparse roles (<50 JD total): {len(qc['sparse_roles'])}")
    print(f"demand_index mean={qc['demand_index_distribution']['mean']} "
          f"p50={qc['demand_index_distribution']['p50']}")
    print(f"reliable months per role: min={min(r['reliable_months'] for r in qc['roles'].values())} "
          f"max={max(r['reliable_months'] for r in qc['roles'].values())}")


if __name__ == "__main__":
    main()
