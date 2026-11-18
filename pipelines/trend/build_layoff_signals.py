"""WARN Act 裁员信号构建（APProjects WARN 数据集 -> data/gold/layoff_signals.json）。

输入：/data/shichaojian/JNIT/raw/events/warn_act/us_tech_warn/
      （HF APProjects/us-tech-company-layoffs-warn-act-notices-daily，CC-BY-4.0；
      美国 WARN 备案口径：100+ 人大裁员，作者已按 tech 公司预筛）
处理：
  - tech 复核：雇主归一化名命中 jd_unified_v3 公司集合或 IT 雇主关键词
    记 tech_verified=True（数据集本身已按 tech 预筛，复核用于下游信任度加权）
  - 裁员类型分类：layoff / closure / other（保留全部行，聚合榜只计 layoff 类）
  - 按月（notice_date）+ 公司 汇总 employees_affected
输出：data/gold/layoff_signals.json
幂等：全量重算覆盖输出。

用法：
  /var/lib/jobnav-env/bin/python pipelines/trend/build_layoff_signals.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path("/data/shichaojian/JNIT/raw/events/warn_act")
UNIFIED_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3")
DEFAULT_OUT = ROOT / "data/gold/layoff_signals.json"

IT_EMPLOYER_KEYWORDS = re.compile(
    r"software|tech|data|cloud| ai\b|artificial intelligence|digital|"
    r"cyber|network|systems?|solutions?|labs|analytics|robot|"
    r"computer|internet|platform|app\b|semiconductor|electronic", re.I)

LAYOFF_TYPE_RULES = [
    ("closure", r"clos|shut"),
    ("layoff", r"layoff|lay off|reduction|downsize|rif\b|workforce|"
               r"mass|warn|elimina|restructur|furlough|termination"),
]
DEFAULT_TYPE = "other"


def norm_company(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def load_jd_companies() -> set[str]:
    """jd_unified_v3 全量分区的公司名归一化集合（去重信任锚）。"""
    out: set[str] = set()
    for fp in sorted(UNIFIED_DIR.glob("posted_month=*/part-0.parquet")):
        df = pd.read_parquet(fp, columns=["company"])
        out.update(norm_company(c) for c in df["company"].dropna().unique())
    return out


def classify_type(notice_type: str) -> str:
    t = str(notice_type or "").lower()
    for label, pat in LAYOFF_TYPE_RULES:
        if re.search(pat, t):
            return label
    return DEFAULT_TYPE


def main() -> None:
    parser = argparse.ArgumentParser(description="WARN 裁员信号构建")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    fps = sorted(args.raw_dir.glob("**/tech_layoff_notices.csv"))
    if not fps:
        raise SystemExit(f"未找到 tech_layoff_notices.csv: {args.raw_dir}")
    df = pd.concat([pd.read_csv(f) for f in fps], ignore_index=True)
    df = df.drop_duplicates(subset=["id"])
    df["notice_month"] = pd.to_datetime(df["notice_date"], errors="coerce").dt.strftime("%Y-%m")
    df["event_type"] = df["notice_type"].map(classify_type)

    jd_companies = load_jd_companies()

    def tech_verified(employer: str) -> bool:
        n = norm_company(employer)
        if not n:
            return False
        if n in jd_companies:
            return True
        # 别名包含匹配（jd 公司名常为雇主名片段或反之）
        for jc in jd_companies:
            if len(jc) >= 5 and (jc in n or n in jc):
                return True
        return bool(IT_EMPLOYER_KEYWORDS.search(str(employer)))

    df["tech_verified"] = df["employer"].map(tech_verified)
    df = df.sort_values(["notice_month", "employer"])

    # 按月+公司 汇总
    records = []
    for (month, employer), g in df.groupby(["notice_month", "employer"], dropna=False):
        records.append({
            "month": month if pd.notna(month) else "unknown",
            "employer": employer,
            "employees_affected": int(g["employees_affected"].sum()),
            "n_notices": int(len(g)),
            "states": sorted(set(g["state"].dropna())),
            "event_types": sorted(set(g["event_type"])),
            "notice_type": sorted(set(g["notice_type"].dropna()))[:5],
            "tech_verified": bool(g["tech_verified"].any()),
            "latest_effective_date": str(g["effective_date"].dropna().max() or ""),
        })

    monthly = {}
    for r in records:
        m = monthly.setdefault(r["month"], {"notices": 0, "employees_affected": 0,
                                            "companies": set(), "layoff_employees": 0})
        m["notices"] += r["n_notices"]
        m["employees_affected"] += r["employees_affected"]
        m["companies"].add(r["employer"])
        if "layoff" in r["event_types"]:
            m["layoff_employees"] += r["employees_affected"]
    monthly_table = {m: {"notices": v["notices"],
                         "employees_affected": v["employees_affected"],
                         "layoff_employees_affected": v["layoff_employees"],
                         "n_companies": len(v["companies"])}
                     for m, v in sorted(monthly.items())}

    layoff_records = [r for r in records if "layoff" in r["event_types"]]
    top_companies = sorted(layoff_records,
                           key=lambda r: -r["employees_affected"])[:20]

    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "APProjects/us-tech-company-layoffs-warn-act-notices-daily "
                  "(CC-BY-4.0；美国 WARN 备案口径，100+ 人大裁员)",
        "raw_files": [str(f) for f in fps],
        "window": [str(df["notice_date"].min())[:10], str(df["notice_date"].max())[:10]],
        "n_notices": int(len(df)),
        "n_employers": int(df["employer"].nunique()),
        "tech_verified_ratio": round(float(df["tech_verified"].mean()), 4),
        "event_type_dist": df["event_type"].value_counts().to_dict(),
        "monthly_table": monthly_table,
        "top_companies_by_employees": top_companies,
        "records": records,
        "notes": [
            "month 按 notice_date（备案日期）归月；employees_affected 为该公司当月"
            "全部备案人数合计（同公司多月备案分散在各月）。",
            "tech_verified：雇主名归一化后命中 jd_unified_v3 公司集合（含片段互含）"
            "或 IT 雇主关键词；数据集本身已按 tech 公司预筛，此标记供下游加权。",
            "event_type 分类：closure=关厂/关停类，layoff=裁员/缩编类，other=其余；"
            "top 榜与 layoff_employees 只计 layoff 类。",
            "WARN 口径只覆盖美国 100+ 人大裁员备案，漏掉小裁员与非备案情形，"
            "与 layoffs.fyi / SEC EDGAR 8-K 源互补而非替代。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"-> {args.out}")
    print(f"notices={len(df)} employers={df['employer'].nunique()} "
          f"window={payload['window']} tech_verified={payload['tech_verified_ratio']}")
    recent = {m: v for m, v in monthly_table.items()
              if m >= "2026-01" and m != "unknown"}
    print("\n2026 月度汇总:")
    for m, v in recent.items():
        print(f"  {m}: {v['notices']} notices / {v['employees_affected']} affected")


if __name__ == "__main__":
    main()
