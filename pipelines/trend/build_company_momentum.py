"""公司级在招 momentum 构建（roletrends 公司日度在招数）。

输入：/data/shichaojian/JNIT/raw/trend/roletrends_company_daily/
      roletrends-company-days-sample.csv（HF roletrends/company-job-postings-
      daily-sample，公司×日 在招岗位数，CC-BY-NC-4.0 内部使用）
输出：data/gold/company_hiring_momentum.json
  - companies: 公司×日 在招数序列 + 最新值 + 7/30 日动量（绝对变化与环比）
  - by_sector: 行业分组 top 榜（按最新在招数 / 30 日动量排序）
  - cohort_daily: 样本整体每日在招总量（momentum 曲线）
幂等：全量重算覆盖输出。

用法：
  /var/lib/jobnav-env/bin/python pipelines/trend/build_company_momentum.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path("/data/shichaojian/JNIT/raw/trend/roletrends_company_daily")
DEFAULT_OUT = ROOT / "data/gold/company_hiring_momentum.json"

# 25 家样本公司的行业分组（人工标注，用于 top 榜聚合）
SECTOR_BY_DOMAIN = {
    "anthropic.com": "AI", "perplexity.ai": "AI",
    "databricks.com": "数据/云", "snowflake.com": "数据/云", "confluent.io": "数据/云",
    "neon.tech": "数据/云", "gitlab.com": "开发者工具", "datadog.com": "开发者工具",
    "railway.app": "开发者工具", "duffel.com": "开发者工具",
    "stripe.com": "金融科技", "plaid.com": "金融科技", "ramp.com": "金融科技",
    "robinhood.com": "金融科技", "increase.com": "金融科技", "wealthfront.com": "金融科技",
    "airbnb.com": "消费/平台", "instacart.com": "消费/平台", "pinterest.com": "消费/平台",
    "roblox.com": "消费/平台",
    "okta.com": "安全/企业软件", "lattice.com": "安全/企业软件", "miro.com": "安全/企业软件",
    "airtable.com": "安全/企业软件", "palantir.com": "安全/企业软件",
}


def momentum(series: pd.Series, days: int) -> dict | None:
    """近 N 日动量：最新值 - N 日前值。

    序列不足 N+1 个点时用可用窗口首末对比（样本初期口径，
    后续月份滚动满 N 天后自动变为标准口径）。
    """
    s = series.dropna()
    if len(s) < 2:
        return None
    win = s.tail(days + 1)
    before = float(win.iloc[0])
    now = float(s.iloc[-1])
    span = int((win.index[-1] - win.index[0]).days)
    return {
        "delta": round(now - before, 1),
        "pct": round((now - before) / before, 4) if before else None,
        "window_days": span,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="公司级在招 momentum 构建")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    fps = sorted(args.raw_dir.glob("*.csv"))
    if not fps:
        raise SystemExit(f"未找到 roletrends csv: {args.raw_dir}")
    df = pd.concat([pd.read_csv(f) for f in fps], ignore_index=True)
    df = df[df["status"] == "ok"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["domain", "date"], keep="last")
    df = df.sort_values(["domain", "date"])

    # 公司×日 序列
    companies: dict[str, dict] = {}
    for domain, g in df.groupby("domain"):
        g = g.sort_values("date")
        series = [{"date": d.strftime("%Y-%m-%d"), "open_roles": int(r)}
                  for d, r in zip(g["date"], g["open_roles"])]
        s = g.set_index("date")["open_roles"]
        companies[domain] = {
            "company": g["company"].iloc[-1],
            "domain": domain,
            "ats": sorted(set(g["ats"].dropna())),
            "sector": SECTOR_BY_DOMAIN.get(domain, "未分组"),
            "n_days": len(series),
            "latest": series[-1],
            "open_roles_avg_30d": round(float(s.tail(30).mean()), 1),
            "momentum_7d": momentum(s, 7),
            "momentum_30d": momentum(s, 30),
            "daily": series,
        }

    # 行业分组 top 榜
    by_sector: dict[str, dict] = {}
    for d, c in companies.items():
        sec = c["sector"]
        bucket = by_sector.setdefault(sec, {"companies": [], "total_latest_open_roles": 0})
        bucket["companies"].append({
            "domain": d, "company": c["company"], "latest_open_roles": c["latest"]["open_roles"],
            "momentum_7d": c["momentum_7d"], "momentum_30d": c["momentum_30d"],
        })
        bucket["total_latest_open_roles"] += c["latest"]["open_roles"]
    for sec, bucket in by_sector.items():
        bucket["companies"].sort(key=lambda x: -x["latest_open_roles"])
        bucket["n_companies"] = len(bucket["companies"])
    top_by_momentum_30d = sorted(
        ({"domain": d, "company": c["company"], "sector": c["sector"],
          "momentum_30d": c["momentum_30d"]}
         for d, c in companies.items() if c["momentum_30d"]),
        key=lambda x: -(x["momentum_30d"]["delta"] or 0))[:10]

    # 样本整体每日总量
    cohort = df.groupby("date")["open_roles"].sum().sort_index()
    cohort_daily = [{"date": d.strftime("%Y-%m-%d"), "total_open_roles": int(v)}
                    for d, v in cohort.items()]

    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "roletrends/company-job-postings-daily-sample (CC-BY-NC-4.0, 内部使用)",
        "raw_files": [f.name for f in fps],
        "window": [str(df["date"].min().date()), str(df["date"].max().date())],
        "n_companies": len(companies),
        "n_days": len(cohort_daily),
        "companies": companies,
        "by_sector": dict(sorted(by_sector.items(),
                                 key=lambda kv: -kv[1]["total_latest_open_roles"])),
        "top_momentum_30d": top_by_momentum_30d,
        "cohort_daily_total": cohort_daily,
        "notes": [
            "open_roles 为该公司当日在招岗位数（ATS 公开页口径），"
            "open_roles_capped=True 表示真实值被截断到上限。",
            "momentum_Nd = 最新值 - N 个观测日前值（window_days 为实际对比跨度）；"
            "样本窗口不足 N+1 天时用可用窗口首末对比，滚动满 N 天后口径自动归一。",
            "行业分组为本文件内人工标注（SECTOR_BY_DOMAIN），新增公司需补标。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"-> {args.out}")
    print(f"companies={len(companies)} days={len(cohort_daily)} "
          f"window={payload['window']}")
    print("\nTop 5 by 30d momentum:")
    for e in top_by_momentum_30d[:5]:
        print(f"  {e['company']:<16} {e['sector']:<10} "
              f"Δ30d={e['momentum_30d']['delta']:+.0f}")


if __name__ == "__main__":
    main()
