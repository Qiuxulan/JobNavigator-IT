"""分数校准服务(matching v5,2026-11-06)。

背景:Qwen3-Embedding-4B 原始余弦相似度挤在 0.5~0.65 窄带,用户无法
区分匹配强弱。本服务消费 experiments/fit_score_calibration.py 拟合出的
参数文件 data/gold/score_calibration_v1.json,把原始分单调映射到 [0,1]:

    sem_cal = clip((raw - p_low) / (p_high - p_low), 0, 1)

单调性(clip 与正斜率线性段都是单调映射)保证:
  - 粗召回列表内部排序不变;
  - NDCG/Hit@1 等排序指标不变(回归评估见 reports/eval/matching_v5_calibration_eval.json)。

缓存与降级(参照 app/api/trends_v3.py 的 mtime 缓存模式):
  - 参数文件按 mtime 热重载,流水线重拟合后无需重启;
  - 文件缺失/损坏/锚点非法时 calibrate_semantic 恒等返回原始分(优雅降级),
    线上行为回退到校准前,绝不阻塞推荐。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).parents[2]
CALIBRATION_PATH = Path(
    os.environ.get(
        "JOBNAV_SCORE_CALIBRATION_PATH",
        str(ROOT / "data" / "gold" / "score_calibration_v1.json"),
    )
)

_params_cache: dict[str, Any] = {"mtime": None, "data": None}


def _load_params() -> Optional[dict[str, Any]]:
    """读校准参数;mtime 变化才重新读盘。缺失/损坏返回 None(降级)。"""
    try:
        mtime = CALIBRATION_PATH.stat().st_mtime
    except OSError:
        return None
    if _params_cache["mtime"] != mtime or _params_cache["data"] is None:
        try:
            data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        _params_cache["mtime"] = mtime
        _params_cache["data"] = data
    return _params_cache["data"]


def calibrate_semantic(raw: float) -> float:
    """原始 cosine 相似度 → 校准分 [0,1](单调,分段线性,头尾饱和)。

    参数文件缺失/锚点非法(p_high <= p_low)时恒等返回 raw,保证优雅降级。
    """
    params = _load_params()
    if not params:
        return raw
    try:
        p_low = float(params["p_low"])
        p_high = float(params["p_high"])
    except (KeyError, TypeError, ValueError):
        return raw
    span = p_high - p_low
    if span <= 0:
        return raw
    calibrated = (float(raw) - p_low) / span
    return max(0.0, min(1.0, calibrated))


def confidence_label(coverage: float, sem_cal: float, n_overlap: int) -> str:
    """置信度三档标签,供前端展示与用户决策。

    规则(按序匹配,先 high 后 medium,其余 low):
      - high  : coverage >= 0.5 且 sem_cal >= 0.6 且 n_overlap >= 3
                (技能覆盖与语义匹配双高,且至少有 3 个技能直接命中)
      - medium: coverage >= 0.25 且 sem_cal >= 0.4
                (覆盖和语义有一项站得住,可信但不强)
      - low   : 其余(覆盖或语义明显偏弱,仅供参考)
    """
    cov = float(coverage)
    sem = float(sem_cal)
    if cov >= 0.5 and sem >= 0.6 and n_overlap >= 3:
        return "high"
    if cov >= 0.25 and sem >= 0.4:
        return "medium"
    return "low"
