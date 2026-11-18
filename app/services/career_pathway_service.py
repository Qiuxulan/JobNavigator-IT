from __future__ import annotations

import os
from functools import lru_cache
from importlib.util import find_spec
from typing import Any

from app.core.config import settings
from app.schemas.domain import RecommendationItem, SkillGap, UserPreference, UserProfile
from app.services.career_catalog import jobrole_from_role, load_roles, role_top_skills
from app.services.graph_path_planner_v3 import (
    ROLE_SCORE_WEIGHT_COVERAGE,
    ROLE_SCORE_WEIGHT_FEASIBILITY,
    ROLE_SCORE_WEIGHT_SEMANTIC,
    ROLE_SCORE_WEIGHT_TREND,
    GraphPathPlannerV3,
)
from app.services.skill_norm import normalize_skill_id
from app.services import score_calibration

# matching v4(2026-11-05):JobBERT-v3 → Qwen3-Embedding-4B。
# 2560 维,需配套 migration 006(VECTOR(1024)→VECTOR(2560))与重跑
# pipelines.taxonomy.build_job_vectors。模型常驻 CPU 内存(bf16 ~8GB),
# 共享 GPU 显存紧张(每卡仅 ~7.6GB 空闲)且单条 query 编码 CPU 足够快。
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"
EMBEDDING_DIM = 2560  # 与 infra/db/migrations/006_job_embedding_qwen3.sql 对齐
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


class RecallSetupError(RuntimeError):
    pass


def _sanitize_runtime_env() -> None:
    ssl_keylog = os.environ.get("SSLKEYLOGFILE")
    if ssl_keylog and not os.path.exists(ssl_keylog):
        os.environ.pop("SSLKEYLOGFILE", None)


@lru_cache(maxsize=1)
def _load_engine():
    _sanitize_runtime_env()
    from sentence_transformers import SentenceTransformer

    # 常驻 CPU(bf16 ~8GB 内存):共享 GPU 每卡仅 ~7.6GB 空闲,放不下 4B 权重,
    # 且单条 query 编码在 CPU 上是秒级,不值得冒险上卡。
    return SentenceTransformer(
        MODEL_NAME,
        device="cpu",
        model_kwargs={"dtype": "bfloat16"},
        local_files_only=True,
    )


def _recall_topn(user_vec: Any, top_n: int, dsn: str) -> list[dict[str, Any]]:
    from pipelines.taxonomy.recall import recall_topn

    return recall_topn(user_vec, top_n, dsn)


def _profile_to_query_text(profile: UserProfile) -> str:
    """用户画像 → query 文本(与 build_job_vectors v3 岗位文本同一 JD 语义风格)。

    v3 升级:不再只是 "Target role + skills" 干拼,带上经验年限/学历,
    用 JD 语言描述,贴近岗位 embedding 的语义空间。
    """
    parts: list[str] = []
    if profile.target_role:
        parts.append(f"Job seeker targeting the role of {profile.target_role}")
    if profile.skills:
        parts.append(f"Skills: {', '.join(profile.skills)}")
    if profile.years_experience and profile.years_experience > 0:
        yrs = int(profile.years_experience) if float(profile.years_experience).is_integer() else profile.years_experience
        parts.append(f"Professional experience: {yrs} years")
    if profile.education:
        parts.append(f"Education: {profile.education}")
    if not parts:
        parts.append("Job seeker profile")
    return ". ".join(parts) + "."


def recall_preflight() -> dict[str, Any]:
    status: dict[str, Any] = {
        "model_name": MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "dsn": DSN,
        "sentence_transformers": find_spec("sentence_transformers") is not None,
        "psycopg": find_spec("psycopg") is not None,
        "pgvector": find_spec("pgvector") is not None,
        "model_ready": False,
        "db_ready": False,
        "embedding_count": 0,
    }
    if not status["sentence_transformers"]:
        raise RecallSetupError("Missing dependency: sentence-transformers")
    if not status["psycopg"] or not status["pgvector"]:
        raise RecallSetupError("Missing dependency: psycopg and/or pgvector")

    try:
        _load_engine()
        status["model_ready"] = True
    except Exception as exc:
        raise RecallSetupError(f"{MODEL_NAME} is not available in local cache: {exc}") from exc

    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=3, options="-c statement_timeout=2000") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM job_roles
                    WHERE embedding IS NOT NULL
                    """
                )
                count = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT atttypmod FROM pg_attribute
                    WHERE attrelid = 'job_roles'::regclass AND attname = 'embedding'
                    """
                )
                dim_row = cur.fetchone()
        status["embedding_count"] = count
        status["db_ready"] = count > 0
        db_dim = dim_row[0] if dim_row else None
        status["embedding_dim_db"] = db_dim
        if db_dim is not None and db_dim != EMBEDDING_DIM:
            raise RecallSetupError(
                f"job_roles.embedding 列维度是 {db_dim},模型输出 {EMBEDDING_DIM} 维。"
                "请先跑 infra/db/migrations/006_job_embedding_qwen3.sql 并重灌向量。"
            )
    except RecallSetupError:
        raise
    except Exception as exc:
        raise RecallSetupError(f"Vector database is unavailable: {exc}") from exc

    if status["embedding_count"] <= 0:
        raise RecallSetupError("job_roles.embedding is empty. Run pipelines.taxonomy.build_job_vectors first.")
    return status


def coarse_recall(profile: UserProfile, top_n: int = 10) -> list[dict[str, Any]]:
    roles_by_id = load_roles()
    recall_preflight()
    model = _load_engine()
    vector = model.encode(_profile_to_query_text(profile), normalize_embeddings=True)
    rows = _recall_topn(vector, top_n, DSN)
    return [
        {
            "job_id": row["job_id"],
            # matching v5(2026-11-06):对外 semantic_score 统一为校准后分数,
            # 单调映射不改变召回列表内部排序;原始分保留在 semantic_score_raw
            # 供 explanation 可追溯。
            "semantic_score": round(score_calibration.calibrate_semantic(raw), 4),
            "semantic_score_raw": raw,
            "job": jobrole_from_role(roles_by_id[row["job_id"]]),
        }
        for row in rows
        if row["job_id"] in roles_by_id
        for raw in [round(float(row["score"]), 4)]
    ]


def _raw_role_score(breakdown: dict[str, Any], sem_raw: float) -> float:
    """校准前的 role_score(与 GraphPathPlannerV3.analyze_role 同公式同舍入)。

    只作排序键:语义分用原始 cosine,其余分量(coverage/trend/feasibility)
    与语义分口径无关,直接取 analyze_role 的 breakdown。权重全部从
    graph_path_planner_v3 导入,保持与线上 v3.1 公式逐位一致。
    """
    score = (
        ROLE_SCORE_WEIGHT_COVERAGE * breakdown["coverage_weighted"]
        + ROLE_SCORE_WEIGHT_SEMANTIC * float(sem_raw)
        + ROLE_SCORE_WEIGHT_TREND * breakdown["trend_momentum_norm"]
        + ROLE_SCORE_WEIGHT_FEASIBILITY * breakdown["learning_feasibility"]
    )
    return max(0.0, min(1.0, round(score, 4)))


def rank_careers(profile: UserProfile, preference: UserPreference, top_n: int = 10) -> list[dict[str, Any]]:
    roles_by_id = load_roles()
    ranked = []
    for coarse in coarse_recall(profile, top_n=top_n):
        role = roles_by_id[coarse["job_id"]]
        try:
            analysis = GraphPathPlannerV3.analyze_role(
                profile=profile,
                target_job_id=coarse["job_id"],
                semantic_score=coarse["semantic_score"],
            )
        except ValueError:
            continue  # 该岗技能无法映射到先修图,跳过不阻塞整体推荐
        breakdown = analysis.score_breakdown
        # v3.1 四维评分公式:coverage + semantic + trend_momentum_norm + learning_feasibility
        # (权重见 graph_path_planner_v3 模块 docstring;2026-10-19 调参)
        # matching v5(2026-11-06):analyze_role 收到的 semantic_score 是校准后
        # 分数(单调映射,展示/解释/置信度统一走校准口径);explanation 里 sem_raw=
        # 保留原始 cosine 分可追溯。
        # 重要:排序键必须用原始分重算(_raw_role_score)。分段线性校准在召回列表内
        # 单调(列表内部顺序不变),但 role_score 是 0.15*cov + 0.70*sem + 0.15*trend
        # 的加法组合,非仿射的 sem 变换会改变跨岗排序(探针实测 Hit@1/NDCG@5 会动,
        # 见 experiments/fit_score_calibration.py anchor_report)。为守住"排序结果不许变"
        # 的核心约束,排序键保持校准前口径,与 v4 基线逐位一致;权重全部从
        # graph_path_planner_v3 导入,此处不改任何权重常量。
        # RecommendationItem 的三段展示分由 v3 breakdown 派生,保持前端契约不变:
        # trend_reward_score 用真趋势分(修复原先误填 learning_feasibility 的张冠李戴)。
        constraint_score = breakdown["coverage_weighted"]
        path_cost_score = round(1.0 - breakdown["learning_feasibility"], 4)
        trend_reward_score = breakdown["trend_momentum_norm"]
        item = RecommendationItem(
            job=jobrole_from_role(role),
            final_score=analysis.role_score,
            semantic_score=analysis.semantic_score,
            constraint_score=constraint_score,
            path_cost_score=path_cost_score,
            trend_reward_score=trend_reward_score,
            explanation=(
                f"covered={len(analysis.skill_gap.overlap_skills)} "
                f"missing={len(analysis.skill_gap.missing_skills)} "
                f"hours={analysis.path.total_estimated_hours} "
                f"semantic={analysis.semantic_score:.2f} "
                f"sem_raw={coarse.get('semantic_score_raw', coarse['semantic_score']):.4f}"
            ),
            skill_gap=SkillGap(
                missing_skills=analysis.skill_gap.missing_skills,
                overlap_skills=analysis.skill_gap.overlap_skills,
                optional_skills=analysis.skill_gap.optional_skills or [],
                transferable=analysis.skill_gap.transferable,
            ),
            confidence=score_calibration.confidence_label(
                breakdown["coverage_weighted"],
                analysis.semantic_score,
                len(analysis.skill_gap.overlap_skills),
            ),
        )
        ranked.append(
            {
                "job_id": coarse["job_id"],
                "job": item.job,
                "semantic_score": analysis.semantic_score,
                "semantic_score_raw": coarse.get("semantic_score_raw", coarse["semantic_score"]),
                "role_score": analysis.role_score,
                # 排序键:与 analyze_role 同公式同舍入,但语义分用原始口径,
                # 保证排序与校准前(v4 基线)逐位一致。见函数上方注释。
                "_sort_key": _raw_role_score(
                    breakdown, coarse.get("semantic_score_raw", coarse["semantic_score"])
                ),
                "recommendation": item,
                "score_breakdown": analysis.score_breakdown,
                "skill_gap": analysis.skill_gap,
                "path": analysis.path,
            }
        )
    ranked.sort(key=lambda row: row["_sort_key"], reverse=True)

    # matching v6(2026-11-08):精排策略由 JOBNAV_RANKER 决定,默认本地 LTR
    # (app/services/ltr_ranker.py,DeepSeek 蒸馏的 LightGBM LambdaRank,
    # 摆脱线上对 LLM API 的实时依赖);模型缺失/预测失败自动回退公式排序。
    # "llm" 保留 DeepSeek 全局精排(matching v4,LLM 不可达/输出非法时
    # llm_rerank 返回 None,同样保持原公式排序,不阻塞推荐);
    # "formula" 为纯公式(兜底/评估基线)。
    from app.services import ltr_ranker

    mode = ltr_ranker.rank_mode()
    if mode == "llm":
        if settings.llm_rerank_enabled and ranked:
            from app.services.llm_reranker import apply_rerank, llm_rerank

            # matching v5(2026-11-06):传给 LLM 的候选视图保持校准前口径(原始
            # semantic / raw role_score,候选顺序也是 raw 排序)。排序不许变是核心
            # 约束:LLM prompt 里的分数若用校准口径,会因果性改变精排输出(实测
            # Hit@1 0.9828→1.0,reports/eval/matching_v5_calibration_eval.json)。
            # 展示层分数(行对象本身)仍是校准口径,此处只构造 prompt 视图,
            # llm_reranker 模块本身不改动。
            rerank = llm_rerank(profile, [_llm_prompt_view(r) for r in ranked], roles_by_id)
            if rerank is not None:
                ranked = apply_rerank(ranked, rerank)
    elif mode in ("ltr", "ltr_fallback_llm") and ranked:
        rescored = ltr_ranker.apply_ltr(ranked, profile)
        if rescored is not None:
            ranked = rescored
        # rescored 为 None = 模型文件缺失/损坏/预测失败:保持公式排序(降级)。
    for row in ranked:
        row.pop("_sort_key", None)
    return ranked


def _llm_prompt_view(row: dict[str, Any]) -> dict[str, Any]:
    """ranked 行的 LLM prompt 视图:分数回退到校准前口径,内容与 v4 基线逐位一致。

    llm_reranker 只读 job_id / score_breakdown(coverage/semantic/trend) /
    role_score / 岗位画像,浅拷贝替换这三个字段即可,不影响展示层行对象。
    """
    view = dict(row)
    view["role_score"] = row["_sort_key"]
    view["score_breakdown"] = {**row["score_breakdown"], "semantic": row["semantic_score_raw"]}
    return view
