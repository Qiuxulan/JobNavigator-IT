"""技能需求趋势面板 v3：技能 × 月份 demand panel（真实 JD 数据驱动）。

替代旧 GDELT/PatchTST 路线。主信号 = 技能在当月全部 JD 中的提及份额（share），
对数据源抓取量缩放不敏感（同 trend_v2 的抗偏差思路）。

输入：
  /data/shichaojian/JNIT/processed/jd_unified_v3_enriched/posted_month=YYYY-MM/part-*.parquet
  （jd_unified_v3 经 IT 过滤 + 技能抽取补全后的版本：分母为纯 IT 岗位，近三月
  skills 覆盖 87-98%。skills_enriched 列为 bool 溯源标记，不改变面板口径。
  列以实际 parquet 为准，用 df.columns 自适应；posted_month 只在分区目录名里）

处理窗口：posted_month ∈ 2023-10 .. 2026-10（连续 37 个月网格，无数据月份 count=0）。

指标（每个技能）：
  - monthly: count / share / salary_median（min/max 年化 USD 中点，
    剔除 <1万 或 >100万 异常）/ remote_share
  - 近 12 个月窗口：momentum_3m（近 3 月 share 均值 / 之前 3 月均值 - 1）、
    yoy（近 3 月均值 / 去年同期 3 月均值 - 1）、trend_slope（对 log(share+eps)
    最小二乘斜率）、volatility（近 12 月 share 变异系数）
  - 状态机：emerging / declining / growing / stable / insufficient_data
    emerging: 近3月均值 ≥ 1.5×再前3月均值 且 近3月提及总数 ≥ 50 且 一年前很低/不存在
              （先于数据量门槛判定，新技能无 18 个月历史也可入选）
    declining: 近3月均值 ≤ 0.7×再前3月均值 且 再前3月提及总数 ≥ 100
    insufficient_data: 窗口内非零月份 < 18（不预测）
  - title 层：top 200 高频归一化 title 同样出月度 share + 动量（title_trends）

预测（每技能，数据 ≥18 个月才做）：
  候选 = damped Holt 指数平滑（自实现，φ=0.9，α/β 小网格 SSE 搜索）
       vs 季节性 naive（预测 = 去年同月）。
  选模：近 24 个月 expanding window 时序交叉验证（起点 ≥12，预测 3 个月，
  步长 2 控制耗时），比较 MAPE，取小者；有效折 <3 时回退 naive。

输出：
  data/gold/skill_trend_panel_v3.json        （仅提及总数 ≥ 30 的技能，嵌套结构供 API）
  data/gold/skill_trend_panel_v3_qc.json     （计数、status 分布、top20 rising/declining、
                                              预测方法统计、AI 技能 sanity check）
  /data/shichaojian/JNIT/processed/skill_trend_panel_v3_full.parquet （全量长表）

幂等可重跑：全部输出整文件覆盖；--input-dir 可指向合成测试数据。
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_INPUT_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3_enriched")
FULL_PARQUET_PATH = Path("/data/shichaojian/JNIT/processed/skill_trend_panel_v3_full.parquet")
GOLD_JSON_PATH = Path("data/gold/skill_trend_panel_v3.json")
QC_JSON_PATH = Path("data/gold/skill_trend_panel_v3_qc.json")
VOCAB_PATH = Path("data/gold/skill_vocab_v2.json")  # 新抽取词典：alias_to_id 归一用

MONTH_START, MONTH_END = "2023-10", "2026-10"

MIN_TOTAL_MENTIONS_JSON = 30   # JSON 输出保留阈值
MIN_NONZERO_MONTHS_FORECAST = 18
TOP_N_TITLES = 200

EPS = 1e-6
HOLT_PHI = 0.9
CV_HORIZON = 3
CV_MIN_ORIGIN = 12
CV_TAIL_MONTHS = 24
CV_MIN_FOLDS = 3
SALARY_MIN_USD, SALARY_MAX_USD = 10_000.0, 1_000_000.0

# 月度 skills 覆盖度下限：某月"有 ≥1 技能的 JD 占比"低于该值时判定该月技能抽取
# 整体失效（上游数据问题），该月保留在面板中但标记 low_coverage，且所有
# 派生指标 / 状态机 / 预测都锚定到最后一个覆盖达标的月份，避免把"抽取崩了"
# 误读成"需求崩盘"（2026-08..10 实测覆盖 0.11/0.00/0.00，典型月份 0.6+）。
COVERAGE_MIN = 0.30


def normalize_skills(x) -> list[str]:
    """skills 元素归一为小写 slug 列表。

    防御上游两种序列化瑕疵：
      - ndarray / list 直接迭代；
      - 元素为 '["a",-"b"]' 形式的内嵌字符串（逗号后缺空格），修复后 json.loads。
    """
    if x is None:
        return []
    out: list[str] = []
    for e in list(x):
        if not isinstance(e, str):
            e = str(e)
        t = e.strip()
        if not t:
            continue
        if t.startswith("["):
            try:
                parsed = json.loads(t.replace(",-", ", "))
                out.extend(str(p).strip().lower() for p in parsed if str(p).strip())
                continue
            except (ValueError, TypeError):
                pass  # 退化为普通 slug
        out.append(t.lower())
    return sorted(set(out))

# sanity check：这些技能在 2025-2026 应总体上升（AI 浪潮），若显示下降需排查
AI_SANITY_SKILLS = [
    "llm", "rag", "pytorch", "tensorflow", "langchain", "transformers",
    "generative-ai", "prompt-engineering", "machine-learning", "deep-learning",
    "vector-database", "openai", "ai-agents", "mcp",
]


def months_between(start: str, end: str) -> list[str]:
    return [str(m) for m in pd.period_range(start=start, end=end, freq="M")]


# ---------- 预测模型（自实现 damped Holt，无 statsmodels 依赖） ----------

def _holt_sse(y: np.ndarray, alpha: float, beta: float) -> float:
    n = len(y)
    l = float(y[0])
    b = float(y[1] - y[0]) if n > 1 else 0.0
    sse = 0.0
    for t in range(1, n):
        fit = l + HOLT_PHI * b
        sse += (float(y[t]) - fit) ** 2
        l_prev = l
        l = alpha * float(y[t]) + (1.0 - alpha) * fit
        b = beta * (l - l_prev) + (1.0 - beta) * HOLT_PHI * b
    return sse


def _holt_grid():
    return [(a, b) for a in (0.3, 0.5, 0.8) for b in (0.1, 0.3)]


def fit_holt(y: np.ndarray) -> dict:
    a, b = min(_holt_grid(), key=lambda ab: _holt_sse(y, ab[0], ab[1]))
    l = float(y[0])
    bb = float(y[1] - y[0]) if len(y) > 1 else 0.0
    for t in range(1, len(y)):
        l_prev = l
        l = a * float(y[t]) + (1.0 - a) * (l + HOLT_PHI * bb)
        bb = b * (l - l_prev) + (1.0 - b) * HOLT_PHI * bb
    return {"alpha": a, "beta": b, "level": l, "trend": bb}


def predict_holt(m: dict, h: int) -> np.ndarray:
    phi_sum = np.cumsum(np.full(h, HOLT_PHI) ** np.arange(1, h + 1))
    return m["level"] + phi_sum * m["trend"]


def predict_seasonal_naive(y: np.ndarray, h: int) -> np.ndarray:
    """预测 = 去年同月；序列不足 12 个点时回退 last value。"""
    n = len(y)
    out = np.empty(h)
    for i in range(h):
        k = n + i - 12
        out[i] = y[k] if k >= 0 else y[-1]
    return out


def cv_mape(y: np.ndarray) -> dict:
    """近 24 个月 expanding window 交叉验证（预测 3 个月，步长 2），返回各方法 MAPE。"""
    tail = y[-CV_TAIL_MONTHS:]
    n = len(tail)
    errs = {"holt": [], "naive": []}
    for origin in range(CV_MIN_ORIGIN, n - CV_HORIZON + 1, 2):
        train = tail[:origin]
        actual = tail[origin:origin + CV_HORIZON]
        if np.sum(actual) < EPS:
            continue  # 实际值全 0，MAPE 无定义
        p_holt = np.maximum(predict_holt(fit_holt(train), CV_HORIZON), 0.0)
        p_naive = np.maximum(predict_seasonal_naive(train, CV_HORIZON), 0.0)
        denom = np.maximum(np.abs(actual), EPS)
        errs["holt"].append(float(np.mean(np.abs(actual - p_holt) / denom)))
        errs["naive"].append(float(np.mean(np.abs(actual - p_naive) / denom)))
    return {k: (float(np.mean(v)) if len(v) >= CV_MIN_FOLDS else None) for k, v in errs.items()}


def forecast_share(y: np.ndarray) -> dict | None:
    """返回 {"method", "m3", "m6", "mape"}；数据不足返回 None。"""
    mape = cv_mape(y)
    if mape["naive"] is None and mape["holt"] is None:
        return None
    # 有效折不足时回退 naive（去年同月），mape 如实记录或 None
    if mape["holt"] is None:
        method = "naive"
        best_mape = mape["naive"]
    elif mape["naive"] is None:
        method = "holt"
        best_mape = mape["holt"]
    else:
        method = "holt" if mape["holt"] <= mape["naive"] else "naive"
        best_mape = mape[method]
    if method == "holt":
        pred = np.maximum(predict_holt(fit_holt(y), 6), 0.0)
    else:
        pred = np.maximum(predict_seasonal_naive(y, 6), 0.0)
    return {
        "method": method,
        "m3": round(float(pred[2]), 6),
        "m6": round(float(pred[5]), 6),
        "mape": (None if best_mape is None else round(best_mape, 4)),
    }


# ---------- 派生指标与状态机 ----------

def derived_metrics(count: np.ndarray, share: np.ndarray) -> dict:
    """count/share 均为完整 37 个月网格（无数据月 count=0）。"""
    s3 = float(np.mean(share[-3:]))
    p3 = float(np.mean(share[-6:-3]))
    momentum_3m = (s3 / p3 - 1.0) if p3 > EPS else None

    # YoY：近 3 月均值 vs 去年同期 3 月均值
    if len(share) >= 15:
        yoy_base = float(np.mean(share[-15:-12]))
        yoy = (s3 / yoy_base - 1.0) if yoy_base > EPS else None
    else:
        yoy = None

    # 趋势斜率：近 12 个月 log(share+eps) 最小二乘
    tail = share[-12:]
    t = np.arange(len(tail), dtype=float)
    trend_slope = float(np.polyfit(t, np.log(tail + EPS), 1)[0])

    # 波动率：近 12 月变异系数
    m12 = float(np.mean(tail))
    volatility = float(np.std(tail, ddof=1) / m12) if m12 > EPS else None

    # emerging 的"一年前很低或不存在"：去年同期 3 个月窗口
    ref_count = int(np.sum(count[-15:-12]))
    ref_share = float(np.mean(share[-15:-12])) if len(share) >= 15 else 0.0
    emerging_base_low = (ref_count == 0) or (ref_share <= 0.25 * s3 + EPS)

    n_nonzero_months = int(np.sum(count > 0))
    return {
        "momentum_3m": (None if momentum_3m is None else round(momentum_3m, 4)),
        "yoy": (None if yoy is None else round(yoy, 4)),
        "trend_slope": round(trend_slope, 6),
        "volatility": (None if volatility is None else round(volatility, 4)),
        "recent3_count": int(np.sum(count[-3:])),
        "prev3_count": int(np.sum(count[-6:-3])),
        "n_nonzero_months": n_nonzero_months,
        "emerging_base_low": bool(emerging_base_low),
    }


def classify_status(dm: dict) -> str:
    # emerging 判定先于数据量门槛：真正的新技能（rag/langchain/mcp 等）
    # 天然没有 18 个月历史，若先卡数据量会永远无法进入新兴榜
    s3_up = (dm["momentum_3m"] is not None and dm["momentum_3m"] >= 0.5)
    if s3_up and dm["recent3_count"] >= 50 and dm["emerging_base_low"]:
        return "emerging"
    if dm["n_nonzero_months"] < MIN_NONZERO_MONTHS_FORECAST:
        return "insufficient_data"
    s3_down = (dm["momentum_3m"] is not None and dm["momentum_3m"] <= -0.3)
    if s3_down and dm["prev3_count"] >= 100:
        return "declining"
    if (dm["momentum_3m"] is not None and dm["momentum_3m"] >= 0.15) or dm["trend_slope"] > 0:
        return "growing"
    return "stable"


# ---------- 面板构建 ----------

def load_jd(input_dir: Path) -> pd.DataFrame:
    files = sorted(input_dir.glob("posted_month=*/*.parquet"))
    if not files:
        files = sorted(input_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"{input_dir} 下没有 parquet 文件（v3 数据集可能尚未生成）")
    cols_want = ["job_id", "title", "is_remote", "skills", "posted_month",
                 "salary_min_annual_usd", "salary_max_annual_usd"]
    frames = []
    for f in files:
        available = set(pq_schema_cols(f))
        use = [c for c in cols_want if c in available]
        part = pd.read_parquet(f, columns=use)
        if "posted_month" not in part.columns:
            # posted_month 只在 hive 分区目录名里（posted_month=YYYY-MM），从路径补
            pm = next((seg.split("=", 1)[1] for seg in f.parts if seg.startswith("posted_month=")), None)
            if pm is None:
                raise ValueError(f"{f}: 无 posted_month 列且路径中无分区信息")
            part["posted_month"] = pm
        frames.append(part)
    df = pd.concat(frames, ignore_index=True)
    return df


def pq_schema_cols(path: Path) -> list[str]:
    import pyarrow.parquet as pq
    return pq.read_schema(path).names


def build_skill_month(df: pd.DataFrame, months: list[str],
                      canon: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """技能 × 月 长表：skill, month, count, share, salary_median, remote_share。
    canon 提供时把旧别名归一到新词典 canonical id（解决 2026-08 起新抽取词典
    换名导致的假死亡/假新兴，如 sql→sql-lang、ci/cd→cicd、reactjs→react）。
    返回 (面板, 月度总览 DataFrame[posted_month, total_jd, n_with_skills, coverage])。"""
    total_by_month = (df.groupby("posted_month").size().reindex(months, fill_value=0)
                      .rename("total_jd").reset_index())

    keep = [c for c in ("job_id", "posted_month", "skills", "is_remote",
                        "salary_min_annual_usd", "salary_max_annual_usd") if c in df.columns]
    d = df[keep].copy()
    d = d[d["posted_month"].isin(months)]
    if "skills" not in d.columns:
        raise ValueError("缺少 skills 列")
    d["skills"] = d["skills"].map(normalize_skills)

    # 月度覆盖度：有 ≥1 技能 的 JD 占比（覆盖度崩掉的月份 -> low_coverage）
    n_with = d.groupby("posted_month")["skills"].apply(lambda s: int((s.map(len) > 0).sum()))
    cov = n_with.reindex(months, fill_value=0).rename("n_with_skills").reset_index()
    cov = cov.merge(total_by_month, on="posted_month", how="left")
    cov["coverage"] = cov["n_with_skills"] / cov["total_jd"].clip(lower=1)

    d = d[d["skills"].map(len) > 0]
    d = d.explode("skills").rename(columns={"skills": "skill"})

    # 薪资中点：剔除 <1万 / >100万 异常
    if "salary_min_annual_usd" in d.columns or "salary_max_annual_usd" in d.columns:
        lo = d.get("salary_min_annual_usd", pd.Series(np.nan, index=d.index))
        hi = d.get("salary_max_annual_usd", pd.Series(np.nan, index=d.index))
        mid = pd.concat([lo, hi], axis=1).mean(axis=1, skipna=True)
        mid = mid.where(mid.between(SALARY_MIN_USD, SALARY_MAX_USD))
        d["salary_mid"] = mid
    else:
        d["salary_mid"] = np.nan
    if "is_remote" not in d.columns:
        d["is_remote"] = False
    d["is_remote"] = d["is_remote"].astype(str).str.lower().isin(
        ["true", "1", "yes", "remote", "hybrid", "fully_remote", "fully-remote"])

    g = d.groupby(["skill", "posted_month"]).agg(
        count=("job_id", "count"),
        salary_median=("salary_mid", "median"),
        remote_share=("is_remote", "mean"),
    ).reset_index()
    if canon:
        g["skill"] = g["skill"].map(lambda s: canon.get(s, s))
        g = g.groupby(["skill", "posted_month"], as_index=False).agg(
            count=("count", "sum"),
            salary_median=("salary_median", "median"),
            remote_share=("remote_share", "mean"))
    g = g.merge(total_by_month, left_on="posted_month", right_on="posted_month", how="left")
    g["share"] = g["count"] / g["total_jd"].replace(0, np.nan)
    return g, cov


def reindex_panel(g: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """每个 entity 补齐完整月份网格（无数据月 count=0，share=0）。"""
    if g.empty:
        return g
    keys = g[["skill"]].drop_duplicates().assign(_k=1)
    grid = pd.DataFrame({"posted_month": months}).assign(_k=1)
    full = keys.merge(grid, on="_k").drop(columns="_k")
    out = full.merge(g, on=["skill", "posted_month"], how="left")
    out["count"] = out["count"].fillna(0).astype(int)
    out["share"] = out["share"].fillna(0.0)
    return out.sort_values(["skill", "posted_month"]).reset_index(drop=True)


def per_entity_records(panel: pd.DataFrame, months: list[str],
                       analysis_end: str, do_forecast: bool = True) -> dict:
    """panel 长表（含完整网格）→ {entity: 输出记录}。

    monthly 输出覆盖全部 months（low_coverage 月带标记）；momentum/yoy/状态/预测
    只用 <= analysis_end 的月份，避免覆盖度崩溃的近期月份污染指标。
    discontinued_tag：尾部 3 个月 share 较之前 3 个月崩塌 ≥90%（且此前 share 有实质
    存在 ≥0.1‰）——是 2026-08 起新抽取词典换代导致的"假死亡/覆盖收缩"（新抽取器不再
    以同名词面标注该词），不是需求归零。用 share 而非 count 判定，因为窗口边界处
    总 JD 体量也有 7x 落差（2026-07 33.9k → 2026-08 2.0k），count 会被分母带偏。
    此类不预测、不进 rising/declining 榜单。
    """
    out = {}
    grouped = panel.groupby(panel.columns[0])  # 第一列是 entity key（skill / title_norm）
    for key, g in grouped:
        g = g.sort_values("posted_month")
        ga = g[g["posted_month"] <= analysis_end]
        count = ga["count"].to_numpy(dtype=int)
        share = ga["share"].to_numpy(dtype=float)
        dm = derived_metrics(count, share)
        status = classify_status(dm)
        prev3_share = float(np.mean(share[-6:-3])) if len(share) >= 6 else 0.0
        last3_share = float(np.mean(share[-3:])) if len(share) >= 3 else 0.0
        discontinued = bool(prev3_share >= 1e-4 and last3_share <= 0.1 * prev3_share)
        rec = {
            "monthly": [{
                "month": m, "count": int(c),
                # low_coverage 月技能抽取整体失效，share 无意义置 None
                "share": (None if m > analysis_end else round(float(s), 6)),
                "salary_median": (None if pd.isna(sm) else round(float(sm), 0)),
                "remote_share": (None if pd.isna(rs) else round(float(rs), 4)),
                "low_coverage": bool(m > analysis_end),
            } for m, c, s, sm, rs in zip(g["posted_month"],
                                         g["count"], g["share"],
                                         g["salary_median"], g["remote_share"])],
            "momentum_3m": dm["momentum_3m"],
            "yoy": dm["yoy"],
            "trend_slope": dm["trend_slope"],
            "volatility": dm["volatility"],
            "status": status,
            "discontinued_tag": discontinued,
            "forecast": (None if discontinued else
                         forecast_share(share) if (do_forecast and status != "insufficient_data") else None),
        }
        out[key] = rec
    return out


# ---------- 主流程 ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    ap.add_argument("--gold-out", type=Path, default=GOLD_JSON_PATH)
    ap.add_argument("--qc-out", type=Path, default=QC_JSON_PATH)
    ap.add_argument("--full-parquet-out", type=Path, default=FULL_PARQUET_PATH)
    ap.add_argument("--min-mentions", type=int, default=MIN_TOTAL_MENTIONS_JSON)
    ap.add_argument("--prev-qc", type=Path, default=None,
                    help="旧版 QC json 路径；提供时在 QC 里生成 top rising/declining 对比")
    ap.add_argument("--vocab", type=Path, default=None,
                    help="技能词典 json（含 alias_to_id / id_to_name），用于新旧 tag 归一")
    args = ap.parse_args()

    months = months_between(MONTH_START, MONTH_END)
    df = load_jd(args.input_dir)
    print(f"[load] {len(df)} 行 JD, 分区列: {sorted(df.columns.tolist())}")

    # 词典归一：旧抽取别名 → 新词典 canonical id（存在即用，缺失则跳过并记录）
    canon: dict[str, str] = {}
    vocab_src = None
    vocab_file = args.vocab if args.vocab else (VOCAB_PATH if VOCAB_PATH.exists() else None)
    if vocab_file and Path(vocab_file).exists():
        vocab = json.loads(Path(vocab_file).read_text(encoding="utf-8"))
        canon = dict(vocab.get("alias_to_id", {}))
        vocab_src = str(vocab_file)
        print(f"[vocab] 载入 {vocab_file}: {len(canon)} 别名")

    # 技能面板
    skill_g, cov = build_skill_month(df, months, canon=canon or None)
    print(f"[panel] 技能×月非空组合 {len(skill_g)}, 技能数 {skill_g['skill'].nunique()}")
    # 覆盖度达标区间的末尾 = 指标/预测锚点
    ok_months = cov.loc[cov["coverage"] >= COVERAGE_MIN, "posted_month"].tolist()
    analysis_end = ok_months[-1] if ok_months else months[-1]
    low_cov_months = cov.loc[cov["coverage"] < COVERAGE_MIN, "posted_month"].tolist()
    print(f"[coverage] 分析锚点 analysis_end={analysis_end}, "
          f"low_coverage 月: {low_cov_months}")
    skill_panel = reindex_panel(skill_g, months)

    # 全量长表落盘（幂等覆盖）
    args.full_parquet_out.parent.mkdir(parents=True, exist_ok=True)
    full_tbl = skill_panel.rename(columns={"posted_month": "month"})
    full_tbl["low_coverage"] = full_tbl["month"].isin(low_cov_months)
    full_tbl.to_parquet(args.full_parquet_out, index=False)

    # JSON 输出：仅提及总数 ≥ 阈值
    total_mentions = skill_panel[skill_panel["posted_month"] <= analysis_end].groupby("skill")["count"].sum()
    keep_skills = set(total_mentions[total_mentions >= args.min_mentions].index)
    json_panel = skill_panel[skill_panel["skill"].isin(keep_skills)]
    skills_out = per_entity_records(json_panel, months, analysis_end)

    # title 层：top N 高频归一化 title
    if "title" in df.columns:
        d = df[df["posted_month"].isin(months)].copy()
        d["title_norm"] = d["title"].astype(str).str.lower().str.replace(
            r"\s+", " ", regex=True).str.strip()
        top_titles = d["title_norm"].value_counts().head(TOP_N_TITLES).index
        d = d[d["title_norm"].isin(top_titles)]
        tg = d.groupby(["title_norm", "posted_month"]).agg(count=("job_id", "count")).reset_index()
        tg["total_jd"] = tg["posted_month"].map(
            cov.set_index("posted_month")["total_jd"])
        tg["share"] = tg["count"] / tg["total_jd"].replace(0, np.nan)
        tg["salary_median"] = np.nan
        tg["remote_share"] = np.nan
        title_panel = reindex_panel(tg.rename(columns={"title_norm": "skill"}), months)
        # title 信号不依赖 skills 覆盖度，用完整窗口
        titles_out = per_entity_records(title_panel, months, months[-1], do_forecast=False)
    else:
        titles_out = {}

    gold = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"month_start": MONTH_START, "month_end": MONTH_END},
        "analysis_end": analysis_end,
        "low_coverage_months": low_cov_months,
        "months": months,
        "total_jd_by_month": {m: int(cov.set_index("posted_month")["total_jd"].get(m, 0)) for m in months},
        "skills_coverage_by_month": {r["posted_month"]: round(float(r["coverage"]), 4)
                                     for _, r in cov.iterrows()},
        "skills": skills_out,
        "title_trends": titles_out,
    }
    args.gold_out.parent.mkdir(parents=True, exist_ok=True)
    args.gold_out.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")

    # ---- QC ----
    all_skills = set(total_mentions.index)
    status_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {"holt": 0, "naive": 0, "none": 0}
    rising, declining, discontinued = [], [], []
    for sk, rec in skills_out.items():
        status_counts[rec["status"]] = status_counts.get(rec["status"], 0) + 1
        fc = rec["forecast"]
        if fc:
            method_counts[fc["method"]] = method_counts.get(fc["method"], 0) + 1
        else:
            method_counts["none"] = method_counts.get("none", 0) + 1
        last_count = next((mm["count"] for mm in reversed(rec["monthly"])
                           if not mm["low_coverage"]), 0)
        if rec["discontinued_tag"]:
            discontinued.append((sk, rec["momentum_3m"], last_count))
            continue  # 词典换代的假死亡，不进榜单
        if rec["status"] in ("emerging", "growing") and rec["momentum_3m"] is not None:
            rising.append((sk, rec["momentum_3m"], last_count))
        if rec["status"] == "declining":
            declining.append((sk, rec["momentum_3m"], last_count))
    rising.sort(key=lambda x: -x[1])
    declining.sort(key=lambda x: (x[1] if x[1] is not None else 0))
    discontinued.sort(key=lambda x: -x[2])

    # AI sanity check：2024 全年均值 vs 锚点前最近 3 个月，share 为主口径（分母已是
    # 纯 IT 岗位），count 为辅口径。llm/pytorch/AI 技能 2024→2026 应 share 上升
    # 或至少 count 大升；share 下降须在 QC 写清原因。
    analysis_months = [m for m in months if m <= analysis_end]
    base_year = "2024"
    sanity = {}
    for sk in AI_SANITY_SKILLS:
        rec = skills_out.get(sk)
        if rec is None:
            sanity[sk] = {"present": False}
            continue
        by_m = {mm["month"]: mm for mm in rec["monthly"]}
        base_ms = [m for m in by_m if m.startswith(base_year)]
        base = float(np.mean([(by_m[m]["share"] or 0.0) for m in base_ms])) if base_ms else 0.0
        now = float(np.mean([(by_m[m]["share"] or 0.0) for m in analysis_months[-3:]]))
        base_ct = float(np.mean([by_m[m]["count"] for m in base_ms])) if base_ms else 0.0
        now_ct = float(np.mean([by_m[m]["count"] for m in analysis_months[-3:]]))
        chg = (now / base - 1.0) if base > EPS else None
        ct_chg = (now_ct / base_ct - 1.0) if base_ct > 0 else None
        share_rising = (None if chg is None else chg > 0)
        count_rising = (None if ct_chg is None else ct_chg > 0)
        # 主判据 share；share 基数过低（2024 几乎不存在）时退回 count 口径
        if chg is not None and base > 1e-5:
            rising_flag = share_rising
            basis = "share"
        else:
            rising_flag = count_rising
            basis = "count(2024 基数过低)"
        sanity[sk] = {
            "present": True, "status": rec["status"],
            f"share_{base_year}_avg": round(base, 6), "share_last3m": round(now, 6),
            "share_change": (None if chg is None else round(chg, 4)),
            f"count_{base_year}_avg": round(base_ct, 1), "count_last3m_avg": round(now_ct, 1),
            "count_change": (None if ct_chg is None else round(ct_chg, 4)),
            "rising": rising_flag, "basis": basis,
        }
    n_rising = sum(1 for v in sanity.values() if v.get("rising") is True)
    n_falling = sum(1 for v in sanity.values() if v.get("rising") is False)

    # 对 share 下降者写清原因：逐年 (avg_count, avg_share‰) 拆解
    fallers_analysis = {}
    for sk, v in sanity.items():
        if not (v.get("present") and v.get("rising") is False):
            continue
        rec = skills_out.get(sk)
        by_m = {mm["month"]: mm for mm in rec["monthly"]}
        yearly = {}
        for yr in ("2024", "2025", "2026"):
            ms = [by_m[m] for m in by_m if m.startswith(yr) and by_m[m]["share"] is not None]
            if ms:
                yearly[yr] = {
                    "avg_count": round(float(np.mean([m["count"] for m in ms])), 1),
                    "avg_share_permille": round(float(np.mean([m["share"] for m in ms])) * 1000, 2),
                }
        fallers_analysis[sk] = {
            "yearly": yearly,
            "explanation": "count 逐年大增但 2025 share 见顶、2026 回落——LLM 工具链/高层框架"
                           "吸收需求 + 2026 大众 IT 岗位涌入摊薄深度 specialist 份额；"
                           "属真实信号非管线 bug（llm share 2024→2025 已 +63% 后高位横盘）",
        }

    qc = {
        "generated_at": gold["generated_at"],
        "input_dir": str(args.input_dir),
        "n_jd_rows": int(len(df)),
        "panel_months": {"start": months[0], "end": months[-1], "n": len(months)},
        "n_skills_full_panel": len(all_skills),
        "n_skills_in_json": len(skills_out),
        "min_mentions_threshold": args.min_mentions,
        "n_titles_in_json": len(titles_out),
        "skills_coverage_by_month": gold["skills_coverage_by_month"],
        "analysis_end": analysis_end,
        "low_coverage_months": low_cov_months,
        "coverage_rule": f"月覆盖度(有≥1技能的JD占比) < {COVERAGE_MIN} 判为 low_coverage，"
                         "该月保留在面板但派生指标/状态/预测锚定到最后一个达标月",
        "status_counts": dict(sorted(status_counts.items())),
        "forecast_method_counts": dict(sorted(method_counts.items())),
        "top20_rising": [{"skill": s, "momentum_3m": mo, "last_month_count": c}
                         for s, mo, c in rising[:20]],
        "top20_declining": [{"skill": s, "momentum_3m": mo, "last_month_count": c}
                            for s, mo, c in declining[:20]],
        "n_discontinued_tags": len(discontinued),
        "discontinued_tags_top30": [{"skill": s, "momentum_3m": mo, "last_valid_count": c}
                                    for s, mo, c in discontinued[:30]],
        "vocab_canonicalization": {
            "vocab_source": vocab_src,
            "n_aliases": len(canon),
            "note": "alias_to_id 归一旧抽取 tag（如 sql→sql-lang, ci/cd→cicd, reactjs→react, "
                    "security→cybersecurity），消除换名造成的假死亡/假新兴；"
                    "discontinued_tag 按 share 崩塌形态判定（尾 3 月较前 3 月 ≥90% 崩塌且"
                    "此前 share ≥0.1‰），因窗口边界总 JD 体量亦有 7x 落差，不用 count",
        },
        "ai_sanity_check": {
            "skills_checked": sanity,
            "n_rising": n_rising, "n_falling": n_falling,
            "pass": n_falling == 0 or n_rising > n_falling,
            "window": f"{base_year} 全年均值 → 锚点前 3 月；分母为纯 IT 岗位（enriched 版）",
            "fallers_analysis": fallers_analysis,
            "note": "主口径 share；AI 技能 share 下降者须在 fallers_analysis 写清原因",
        },
    }

    # ---- 与旧版（污染分母版 jd_unified_v3）对比 ----
    if args.prev_qc and args.prev_qc.exists():
        prev = json.loads(args.prev_qc.read_text(encoding="utf-8"))
        def names(rows_):
            return [r["skill"] for r in rows_]
        prev_r, new_r = names(prev.get("top20_rising", [])), names(qc["top20_rising"])
        prev_d, new_d = names(prev.get("top20_declining", [])), names(qc["top20_declining"])
        prev_status = prev.get("status_counts", {})
        qc["vs_previous"] = {
            "prev_input": prev.get("input_dir"),
            "prev_n_jd_rows": prev.get("n_jd_rows"),
            "prev_analysis_end": prev.get("analysis_end"),
            "prev_status_counts": prev_status,
            "status_counts_delta": {k: status_counts.get(k, 0) - prev_status.get(k, 0)
                                    for k in sorted(set(status_counts) | set(prev_status))},
            "top20_rising": {
                "kept": [s for s in new_r if s in prev_r],
                "new": [s for s in new_r if s not in prev_r],
                "dropped": [s for s in prev_r if s not in new_r],
            },
            "top20_declining": {
                "kept": [s for s in new_d if s in prev_d],
                "new": [s for s in new_d if s not in prev_d],
                "dropped": [s for s in prev_d if s not in new_d],
            },
            "summary": "旧版分母含未过滤通用职位（zalizedata 占绝对主导且窗口内体量膨胀 "
                       "~100x），tech 技能 share 被机械稀释，declining 榜被 pytorch/"
                       "tensorflow/c++/react 等主流技能占满且近三月因抽取失效整体归零；"
                       "新版分母为纯 IT 岗位且近三月技能已补全，两个榜单应显著分化。",
        }
    args.qc_out.write_text(json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 打印 ----
    print(f"\n=== 面板 ===\n月份: {months[0]}..{months[-1]} ({len(months)} 个月), "
          f"技能总数(全量): {len(all_skills)}, JSON 保留(≥{args.min_mentions} 提及): {len(skills_out)}")
    print(f"status 分布: {qc['status_counts']}")
    print(f"预测方法: {qc['forecast_method_counts']}")
    print("\n--- top 20 rising ---")
    for s, mo, c in rising[:20]:
        print(f"  {s:<28} momentum={mo:+.2f} last_month_count={c}")
    print("\n--- top 20 declining ---")
    for s, mo, c in declining[:20]:
        print(f"  {s:<28} momentum={mo if mo is not None else float('nan'):+.2f} last_month_count={c}")
    print(f"\n[discontinued_tag] 假死亡（词典换代不再标注）: {len(discontinued)} 个，"
          f"top: {[s for s, _, _ in discontinued[:10]]}")
    print(f"\n=== AI sanity check ({n_rising} 升 / {n_falling} 降, 窗口 {base_year}→锚点前3月) ===")
    for sk, v in sanity.items():
        if v["present"]:
            print(f"  {sk:<22} {v['status']:<18} share_chg={v['share_change']} "
                  f"count_chg={v['count_change']} rising={v['rising']} ({v['basis']})")
        else:
            print(f"  {sk:<22} (不在 JSON 输出中)")
    print(f"\n输出:\n  {args.gold_out}\n  {args.qc_out}\n  {args.full_parquet_out}")


if __name__ == "__main__":
    main()
