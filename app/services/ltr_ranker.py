"""本地 LTR 排序器(matching v6,2026-11-08)。

背景:matching v4 的全局精排依赖 DeepSeek API(黑盒、有延迟、有可用性
风险)。本模块用 DeepSeek 当教师给合成 (画像, 岗位) 样本打 0-3 相关度分
(experiments/collect_ltr_labels.py),蒸馏出一个本地 LightGBM LambdaRank
模型(models/ltr_ranker_v1.txt),让线上精排摆脱对 LLM API 的实时依赖:
黑盒 → 本地可解释模型(特征重要性可见、行为可复现)。

集成开关(环境变量 JOBNAV_RANKER,默认 "ltr"):
  - "ltr"            :本地模型排序(线上默认);模型文件缺失时回退纯公式;
  - "llm"            :DeepSeek 全局精排(matching v4 现状);
  - "formula"        :纯公式排序(兜底/评估基线);
  - "ltr_fallback_llm":同 "ltr"(LTR 主用,模型缺失回退公式)。

展示口径:LTR 预测分按当次请求的候选集合做 min-max 归一化到 [0,1]
(全部候选同分时退化为 0.5),写进 RecommendationItem.final_score;
置信度标签仍走 score_calibration.confidence_label(coverage/sem_cal/overlap),
与排序器无关,保持不变。

特征清单 FEATURE_NAMES 是训练(experiments/train_ltr.py)、采集
(experiments/collect_ltr_labels.py)与线上推理三方共享的唯一事实来源,
模型文件旁的特征清单 json(models/ltr_ranker_v1_features.json)必须与之一致。
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).parents[2]
MODEL_PATH = Path(os.environ.get("JOBNAV_LTR_MODEL_PATH", str(ROOT / "models" / "ltr_ranker_v1.txt")))
FEATURES_PATH = Path(os.environ.get("JOBNAV_LTR_FEATURES_PATH", str(ROOT / "models" / "ltr_ranker_v1_features.json")))

# 特征清单(固定顺序):岗位匹配 breakdown + 技能缺口 + 路径 + 岗位画像
# + 画像侧上下文。NaN 表示该候选缺该画像字段(如薪资缺失),LightGBM 原生支持。
FEATURE_NAMES: list[str] = [
    "coverage_weighted",        # analyze_role:JD 频率加权技能覆盖
    "semantic_cal",             # 校准后语义分(展示口径)
    "semantic_raw",             # 原始 cosine(排序键口径)
    "trend_momentum_norm",      # sigmoid 归一化趋势动量奖励
    "learning_feasibility",     # 1 - min(1, total_hours/600)
    "role_score_raw",           # v3.1 公式分(校准前口径,即线上 _sort_key)
    "n_overlap",                # 已覆盖目标技能数
    "n_missing",                # 缺失目标技能数
    "n_optional",               # 缺失 optional 技能数
    "n_transferable",           # 可迁移技能数
    "overlap_ratio",            # n_overlap / (n_overlap + n_missing)
    "total_hours_norm",         # min(1, total_hours / 600)
    "trend_momentum_clip",      # clip(raw, -2, 5) / 5
    "salary_median_log",        # log1p(salary_median) / log1p(400000)
    "jd_count_6m_log",          # log1p(jd_count_6m) / log1p(max_6m)
    "n_role_skills",            # len(required + core)
    "profile_n_skills",         # 画像技能数
    "profile_years_norm",       # min(years, 15) / 15
    "has_target_role",          # 画像是否给了目标岗位
    "target_role_name_match",   # 目标岗位名 == 候选岗名(精确,小写)
    "target_role_coarse_match", # 目标岗大类 == 候选岗大类
]

_model_cache: dict[str, Any] = {"mtime": None, "booster": None}


def rank_mode() -> str:
    """排序策略开关:JOBNAV_RANKER ∈ {ltr, llm, formula, ltr_fallback_llm}。"""
    mode = os.environ.get("JOBNAV_RANKER", "ltr").strip().lower()
    return mode if mode in {"ltr", "llm", "formula", "ltr_fallback_llm"} else "ltr"


def load_model() -> Optional[Any]:
    """加载 LightGBM 模型;mtime 变化才重读盘(热更新)。

    模型文件缺失/损坏返回 None,调用方降级为公式排序,绝不阻塞推荐。
    """
    try:
        mtime = MODEL_PATH.stat().st_mtime
    except OSError:
        return None
    if _model_cache["mtime"] != mtime or _model_cache["booster"] is None:
        try:
            import lightgbm as lgb

            booster = lgb.Booster(model_file=str(MODEL_PATH))
        except Exception:
            return None
        _model_cache["mtime"] = mtime
        _model_cache["booster"] = booster
    return _model_cache["booster"]


def _clip(value: Any, lo: float, hi: float, default: float = float("nan")) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v):
        return default
    return max(lo, min(hi, v))


def _log_scale(value: Any, ref: float, default: float = float("nan")) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or v < 0:
        return default
    return math.log1p(v) / math.log1p(ref)


def extract_features(
    row: dict[str, Any],
    profile: Any,
    role_profile: Optional[dict[str, Any]] = None,
    target_coarse: Optional[str] = None,
    max_jd_6m: float = 2000.0,
) -> dict[str, float]:
    """rank_careers 的行对象 + 用户画像 → 特征 dict(键与 FEATURE_NAMES 一一对应)。

    row 需含:job_id / score_breakdown / semantic_score / semantic_score_raw /
    role_score(原始口径) / skill_gap / path。role_profile 为 role_profiles_v3
    画像(薪资/动量/jd_count_6m),缺失时对应特征记 NaN。
    """
    breakdown = row.get("score_breakdown") or {}
    gap = row.get("skill_gap")
    path = row.get("path")
    n_overlap = len(getattr(gap, "overlap_skills", None) or [])
    n_missing = len(getattr(gap, "missing_skills", None) or [])
    n_optional = len(getattr(gap, "optional_skills", None) or [])
    n_transferable = len(getattr(gap, "transferable", None) or [])

    sem_raw = row.get("semantic_score_raw", row.get("semantic_score"))
    target_role = (getattr(profile, "target_role", None) or "").strip().lower()
    job = row.get("job") or {}
    # job 可能是 JobRole(pydantic)或 dict,两种都兼容
    role_name = str(
        job.get("title") if isinstance(job, dict) else getattr(job, "title", "")
    ).strip().lower()
    job_coarse = (
        job.get("coarse_role") if isinstance(job, dict) else getattr(job, "coarse_role", None)
    )

    role_profile = role_profile or {}
    trend_raw = role_profile.get("trend_momentum")
    jd_6m = role_profile.get("jd_count_6m")
    salary = (role_profile.get("salary") or {}).get("median")
    required = role_profile.get("required_skill_ids") or []
    core = role_profile.get("core_skill_ids") or []

    return {
        "coverage_weighted": float(breakdown.get("coverage_weighted", 0.0)),
        "semantic_cal": float(row.get("semantic_score", breakdown.get("semantic", 0.0))),
        "semantic_raw": float(sem_raw if sem_raw is not None else 0.0),
        "trend_momentum_norm": float(breakdown.get("trend_momentum_norm", 0.5)),
        "learning_feasibility": float(breakdown.get("learning_feasibility", 0.0)),
        "role_score_raw": float(row.get("role_score", 0.0)),
        "n_overlap": float(n_overlap),
        "n_missing": float(n_missing),
        "n_optional": float(n_optional),
        "n_transferable": float(n_transferable),
        "overlap_ratio": n_overlap / (n_overlap + n_missing) if (n_overlap + n_missing) else 0.0,
        "total_hours_norm": min(1.0, float(getattr(path, "total_estimated_hours", 0.0) or 0.0) / 600.0),
        "trend_momentum_clip": _clip(trend_raw, -2.0, 5.0) / 5.0 if trend_raw is not None else float("nan"),
        "salary_median_log": _log_scale(salary, 400000.0),
        "jd_count_6m_log": _log_scale(jd_6m, max_jd_6m),
        "n_role_skills": float(len(set(required) | set(core))),
        "profile_n_skills": float(len(getattr(profile, "skills", None) or [])),
        "profile_years_norm": min(float(getattr(profile, "years_experience", 0.0) or 0.0), 15.0) / 15.0,
        "has_target_role": 1.0 if target_role else 0.0,
        "target_role_name_match": 1.0 if target_role and target_role == role_name else 0.0,
        "target_role_coarse_match": 1.0 if target_coarse and target_coarse == job_coarse else 0.0,
    }


def vectorize(feature_dicts: list[dict[str, float]]) -> list[list[float]]:
    """特征 dict → 模型输入矩阵,顺序严格按 FEATURE_NAMES(与特征清单一致)。"""
    return [[float(f.get(name, float("nan"))) for name in FEATURE_NAMES] for f in feature_dicts]


def _normalize_display(scores: list[float]) -> list[float]:
    """当次候选集合内 min-max 归一化到 [0,1];全部同分时退化为 0.5。"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-12:
        return [0.5 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def apply_ltr(ranked_rows: list[dict[str, Any]], profile: Any) -> Optional[list[dict[str, Any]]]:
    """用本地 LTR 模型对 rank_careers 的公式排序结果重排。

    返回新列表(按 LTR 预测分降序),行上补:
      - row["ltr_score"]       :原始预测分(未归一化);
      - row["recommendation"].final_score/explanation :展示分替换为 min-max
        归一化到 [0,1] 的 LTR 分(pydantic model_copy 浅拷贝,不动原对象),
        explanation 追加 "ltr=<score>" 便于追溯。
    模型缺失/预测失败返回 None,调用方保持公式排序(降级)。
    """
    booster = load_model()
    if booster is None or not ranked_rows:
        return None
    try:
        from app.services.graph_path_planner_v3 import load_role_profiles

        profiles = load_role_profiles()
    except Exception:
        profiles = {}
    from app.services.career_catalog import load_roles

    name2id: dict[str, str] = {}
    try:
        name2id = {r["role_name"]: rid for rid, r in load_roles().items()}
    except Exception:
        pass
    target_coarse: Optional[str] = None
    target = (getattr(profile, "target_role", None) or "").strip()
    if target and target in name2id:
        target_coarse = (profiles.get(name2id[target]) or {}).get("coarse_role")

    max_jd = max(
        [float(p.get("jd_count_6m") or 0.0) for p in profiles.values()] or [2000.0]
    ) or 2000.0
    feature_dicts = [
        extract_features(row, profile, profiles.get(row["job_id"]), target_coarse, max_jd)
        for row in ranked_rows
    ]
    try:
        preds = booster.predict(vectorize(feature_dicts)).tolist()
    except Exception:
        return None

    display = _normalize_display([float(p) for p in preds])
    rescored: list[dict[str, Any]] = []
    for row, pred, disp in zip(ranked_rows, preds, display):
        new_row = dict(row)
        new_row["ltr_score"] = round(float(pred), 6)
        rec = row.get("recommendation")
        if rec is not None:
            new_row["recommendation"] = rec.model_copy(
                update={
                    "final_score": round(disp, 4),
                    "explanation": f"{rec.explanation} ltr={float(pred):.4f}",
                }
            )
        rescored.append(new_row)
    rescored.sort(key=lambda r: r["ltr_score"], reverse=True)
    return rescored
