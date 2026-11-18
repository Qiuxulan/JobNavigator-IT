"""LLM 精排层(matching v4,2026-11-05)。

背景:embedding 粗排 + GraphPathPlannerV3 公式评分后,用 DeepSeek 对候选岗
做一次"全局重排":把用户画像 + 每个候选岗的画像摘要(核心技能/薪资/趋势动量/
公式分)一次性给 LLM,让它输出重排后的 job_id 顺序和每岗一句理由。

设计约束:
  - 一次调用搞定(不逐岗调用),延迟可控;
  - LLM 不可达/输出非法/返回非候选全集的排列时,返回 None,
    调用方降级为原公式排序(不阻塞推荐);
  - 只依赖 app.core.config.settings 的 LLM 配置,与 agent.py 同一套
    OpenAI 兼容 chat/completions 协议。
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from app.core.config import settings

RERANK_TOP_N = 10  # 参与精排的候选数(与粗排 top_n 一致)

SYSTEM_PROMPT = (
    "You are a career-matching expert. You reorder job candidate lists so that "
    "the most suitable roles for the job seeker rank first. "
    "Respond with strict JSON only."
)


def _profile_summary(profile: Any) -> str:
    parts: list[str] = []
    if getattr(profile, "target_role", None):
        parts.append(f"Target role: {profile.target_role}")
    if getattr(profile, "skills", None):
        parts.append(f"Skills: {', '.join(profile.skills)}")
    yrs = getattr(profile, "years_experience", None)
    if yrs:
        parts.append(f"Experience: {yrs} years")
    if getattr(profile, "education", None):
        parts.append(f"Education: {profile.education}")
    return "; ".join(parts) or "General job seeker"


def _candidate_summary(row: dict[str, Any], role: dict[str, Any]) -> dict[str, Any]:
    """从 rank_careers 的 ranked 行 + 岗位画像拼 LLM 可读的候选摘要。"""
    salary = role.get("salary") or {}
    breakdown = row.get("score_breakdown") or {}
    return {
        "job_id": row["job_id"],
        "title": role.get("role_name", row["job_id"]),
        "core_skills": (role.get("core_skills") or [])[:6],
        "salary_median_usd": salary.get("median"),
        "trend_momentum": role.get("trend_momentum"),
        "match_scores": {
            "coverage": breakdown.get("coverage_weighted"),
            "semantic": breakdown.get("semantic"),
            "trend": breakdown.get("trend_momentum_norm"),
            "role_score": row.get("role_score"),
        },
    }


def _build_prompt(profile_summary: str, candidates: list[dict[str, Any]]) -> str:
    cand_lines = []
    for i, c in enumerate(candidates, 1):
        cand_lines.append(f"{i}. " + json.dumps(c, ensure_ascii=False))
    return (
        f"Job seeker profile: {profile_summary}\n\n"
        f"Candidate roles (current order is a heuristic baseline):\n"
        + "\n".join(cand_lines)
        + "\n\nReorder the candidates from most to least suitable for this job seeker. "
        "Consider skill fit, seniority/experience alignment, salary level, and market trend. "
        "Return JSON of the form:\n"
        '{"ranking": ["job_id", ...], "reasons": {"job_id": "one short sentence", ...}}\n'
        "The ranking must contain every candidate job_id exactly once."
    )


def _parse_ranking(content: str, valid_ids: list[str]) -> Optional[dict[str, Any]]:
    """校验 LLM 输出:必须是覆盖全部候选 id 的排列;否则返回 None 走降级。"""
    try:
        payload = json.loads(content)
        ranking = payload.get("ranking")
        reasons = payload.get("reasons") or {}
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(ranking, list) or set(ranking) != set(valid_ids) or len(ranking) != len(valid_ids):
        return None
    return {"ranking": ranking, "reasons": reasons}


def llm_rerank(profile: Any, ranked_rows: list[dict[str, Any]], roles_by_id: dict[str, dict]) -> Optional[dict[str, Any]]:
    """对 rank_careers 的已排序结果做 LLM 全局重排。

    参数 ranked_rows: rank_careers 返回的 list(已按 role_score 降序),
    取前 RERANK_TOP_N 参与精排。
    返回 {"ranking": [job_id...], "reasons": {job_id: str}} 或 None(降级)。
    """
    if not settings.llm_api_key:
        return None
    rows = ranked_rows[:RERANK_TOP_N]
    candidates = [
        _candidate_summary(row, roles_by_id[row["job_id"]])
        for row in rows
        if row["job_id"] in roles_by_id
    ]
    if len(candidates) < 2:
        return None
    valid_ids = [c["job_id"] for c in candidates]
    prompt = _build_prompt(_profile_summary(profile), candidates)

    try:
        import httpx

        url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        timeout = float(os.environ.get("JOBNAV_LLM_RERANK_TIMEOUT_SEC", settings.llm_timeout_sec))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
    return _parse_ranking(content, valid_ids)


def apply_rerank(ranked_rows: list[dict[str, Any]], rerank: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 LLM 排名重排 ranked_rows(头部重排,尾部保持原顺序),并把理由挂到行上。"""
    if not rerank:
        return ranked_rows
    reasons = rerank.get("reasons") or {}
    by_id = {row["job_id"]: row for row in ranked_rows}
    head, seen = [], set()
    for job_id in rerank["ranking"]:
        if job_id in by_id:
            row = dict(by_id[job_id])
            row["llm_reason"] = reasons.get(job_id)
            head.append(row)
            seen.add(job_id)
    tail = [row for row in ranked_rows if row["job_id"] not in seen]
    return head + tail
