"""LTR 训练数据采集(matching v6,2026-11-08)。

用 DeepSeek 当教师蒸馏本地排序器:
  1. 从技能图 + role_profiles_v3 分层采样合成 ~250 个用户画像
     (按岗位大类 coarse_role 轮转分层;2~8 个技能,主要来自种子岗高频技能,
     掺入跨域技能保证多样性;随机有无目标岗位/年限/学历);
  2. 每个画像走线上同一条召回+公式打分路径(rank_careers,关闭 LLM 精排,
     JOBNAV_RANKER=formula),拿 top10 候选与完整特征向量(ltr_ranker.extract_features);
  3. 调 DeepSeek 给每个 (画像, 岗位) 打 0-3 相关度分(JSON mode,一次调用
     打满一个画像的全部候选,最多 4 次重试;参考 llm_reranker 的 prompt
     风格但输出打分制而非排列制 —— 打分可直接当 LambdaRank 的 label_gain);
  4. 落盘 data/silver/ltr_train_v1.jsonl(画像 + 候选特征 + label),
     统计写 data/silver/ltr_train_v1_stats.json(DeepSeek 调用量/失败率/label 分布)。

运行:python -m experiments.collect_ltr_labels
前置:postgres + 岗位向量已就绪;.env 里 DeepSeek key 可用。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"
os.chdir(ROOT)
# 采集阶段禁掉 LLM 精排与 LTR(LTR 模型此刻还不存在),只取公式排序 + 特征。
os.environ["JOBNAV_RANKER"] = "formula"

from app.core.config import settings  # noqa: E402

OUT_PATH = ROOT / "data" / "silver" / "ltr_train_v1.jsonl"
STATS_PATH = ROOT / "data" / "silver" / "ltr_train_v1_stats.json"

GRADE_SYSTEM = (
    "You are a career-matching expert. You grade how relevant each candidate "
    "role is for the job seeker. Respond with strict JSON only."
)

EDUCATIONS = ["Bachelor", "Master", "PhD", "Associate", "Bootcamp", None]
YEAR_CHOICES = [0, 1, 2, 3, 4, 6, 8, 10, 12]
YEAR_WEIGHTS = [2, 3, 4, 4, 3, 2, 2, 1, 1]


def sample_profiles(n: int, seed: int) -> list[dict]:
    """分层合成画像:按 coarse_role 轮转选种子岗,技能以种子岗高频技能为主。"""
    from app.services.graph_path_planner_v3 import (
        load_role_profiles,
        load_skill_graph,
        skill_display_name,
    )

    roles = list(load_role_profiles().values())
    by_coarse: dict[str, list[dict]] = {}
    for role in roles:
        by_coarse.setdefault(role.get("coarse_role") or "Other", []).append(role)
    graph = load_skill_graph()
    all_skill_names = [skill_display_name(sid) for sid in graph]
    coarse_classes = sorted(by_coarse)

    rng = random.Random(seed)
    profiles: list[dict] = []
    for i in range(n):
        seed_role = rng.choice(by_coarse[coarse_classes[i % len(coarse_classes)]])
        freq = seed_role.get("skill_freq") or {}
        seed_skill_ids = sorted(freq, key=lambda s: -freq[s])[:12]
        seed_names = [skill_display_name(s) for s in seed_skill_ids]

        k = rng.randint(2, 8)
        skills: list[str] = []
        while len(skills) < k:
            if seed_names and rng.random() < 0.65:
                name = rng.choice(seed_names[:6] if rng.random() < 0.7 else seed_names)
            else:
                name = rng.choice(all_skill_names)
            if name not in skills:
                skills.append(name)

        r = rng.random()
        if r < 0.5:
            target = seed_role["role_name"]
        elif r < 0.7:
            target = rng.choice(roles)["role_name"]
        else:
            target = None
        profiles.append(
            {
                "profile_id": f"syn_{i:04d}",
                "skills": skills,
                "target_role": target,
                "years_experience": rng.choice(YEAR_CHOICES),
                "education": rng.choice(EDUCATIONS),
                "seed_role_id": seed_role["role_id"],
                "seed_coarse_role": seed_role.get("coarse_role"),
            }
        )
    return profiles


def grade_candidates(profile: dict, candidates: list[dict]) -> dict[str, int]:
    """一次 DeepSeek 调用给全部候选打 0-3 分;失败抛异常(由调用方重试)。"""
    import httpx

    parts = [f"Skills: {', '.join(profile['skills'])}"]
    if profile.get("target_role"):
        parts.append(f"Target role: {profile['target_role']}")
    if profile.get("years_experience"):
        parts.append(f"Experience: {profile['years_experience']} years")
    if profile.get("education"):
        parts.append(f"Education: {profile['education']}")
    profile_summary = "; ".join(parts)

    lines = [f"{i}. " + json.dumps(c, ensure_ascii=False) for i, c in enumerate(candidates, 1)]
    prompt = (
        f"Job seeker profile: {profile_summary}\n\n"
        "Candidate roles (current order is a heuristic baseline):\n"
        + "\n".join(lines)
        + "\n\nGrade each candidate's relevance to this job seeker with an integer "
        "score 0-3:\n"
        "  0 = irrelevant (wrong domain or far beyond/below seniority)\n"
        "  1 = weakly related (some transferable overlap, but a stretch)\n"
        "  2 = strong match (solid skill fit, plausible next role)\n"
        "  3 = ideal match (core skills align, seniority and direction fit)\n"
        "Consider skill overlap, seniority/experience alignment, salary level and "
        "market trend. Be discriminating: not every candidate deserves 2 or 3.\n"
        'Return JSON of the form:\n{"scores": {"job_id": 0-3, ...}}\n'
        "The scores object must contain every candidate job_id exactly once, "
        "integer values only."
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": GRADE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    timeout = float(os.environ.get("JOBNAV_LLM_RERANK_TIMEOUT_SEC", settings.llm_timeout_sec))
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    data = json.loads(content)
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("missing scores object")
    out: dict[str, int] = {}
    for jid, raw in scores.items():
        value = int(round(float(raw)))
        if value < 0 or value > 3:
            raise ValueError(f"label out of range: {jid}={raw}")
        out[str(jid)] = value
    expected = {c["job_id"] for c in candidates}
    if set(out) != expected:
        raise ValueError(f"scores keys mismatch: got {sorted(out)}, want {sorted(expected)}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=str(OUT_PATH))
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args()

    from app.schemas.domain import UserPreference, UserProfile
    from app.services import ltr_ranker
    from app.services.career_pathway_service import rank_careers
    from app.services.graph_path_planner_v3 import load_role_profiles
    from app.services import score_calibration

    settings.llm_rerank_enabled = False
    assert settings.llm_api_key, "JOBNAV_LLM_API_KEY 未配置,无法调用 DeepSeek 打标"

    profiles = sample_profiles(args.n, args.seed)
    role_profiles = load_role_profiles()
    name2id = {r["role_name"]: r["role_id"] for r in role_profiles.values()}
    max_jd = max(float(p.get("jd_count_6m") or 0.0) for p in role_profiles.values())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = {
        "n_profiles_target": len(profiles),
        "n_profiles_written": 0,
        "n_candidates": 0,
        "deepseek_calls": 0,
        "deepseek_call_failures": 0,
        "profile_failures": 0,
        "label_distribution": {},
        "seconds": 0.0,
        "seed": args.seed,
        "teacher_model": settings.llm_model,
    }
    label_counter: Counter[str] = Counter()
    started = time.time()

    with out_path.open("w", encoding="utf-8") as fout:
        for i, prof in enumerate(profiles, 1):
            profile = UserProfile(
                user_id=prof["profile_id"],
                skills=prof["skills"],
                target_role=prof.get("target_role"),
                years_experience=float(prof.get("years_experience") or 0),
                education=prof.get("education"),
            )
            try:
                rows = rank_careers(profile, UserPreference(), top_n=10)
            except Exception as exc:
                print(f"[{i}/{len(profiles)}] {prof['profile_id']}: rank_careers 失败 {exc}", flush=True)
                stats["profile_failures"] += 1
                continue
            if len(rows) < 2:
                stats["profile_failures"] += 1
                continue

            target_coarse = None
            if prof.get("target_role") and prof["target_role"] in name2id:
                target_coarse = (role_profiles.get(name2id[prof["target_role"]]) or {}).get("coarse_role")

            candidates = []
            feature_rows = []
            for row in rows:
                rp = role_profiles.get(row["job_id"]) or {}
                salary = rp.get("salary") or {}
                breakdown = row["score_breakdown"]
                candidates.append(
                    {
                        "job_id": row["job_id"],
                        "title": rp.get("role_name", row["job_id"]),
                        "core_skills": (rp.get("core_skills") or list((rp.get("skill_freq") or {}).keys()))[:6],
                        "salary_median_usd": salary.get("median"),
                        "trend_momentum": rp.get("trend_momentum"),
                        "match_scores": {
                            "coverage": breakdown.get("coverage_weighted"),
                            "semantic": score_calibration.calibrate_semantic(
                                float(row.get("semantic_score_raw", row["semantic_score"]))
                            ),
                            "trend": breakdown.get("trend_momentum_norm"),
                            "role_score": row.get("role_score"),
                        },
                    }
                )
                feature_rows.append(
                    ltr_ranker.extract_features(row, profile, rp or None, target_coarse, max_jd)
                )

            labeled = None
            for attempt in range(args.retries):
                stats["deepseek_calls"] += 1
                try:
                    labeled = grade_candidates(prof, candidates)
                    break
                except Exception as exc:
                    stats["deepseek_call_failures"] += 1
                    wait = 2 ** attempt
                    print(f"  [{prof['profile_id']}] DeepSeek 第 {attempt + 1} 次失败: {exc};{wait}s 后重试", flush=True)
                    time.sleep(wait)
            if labeled is None:
                stats["profile_failures"] += 1
                print(f"[{i}/{len(profiles)}] {prof['profile_id']}: 打标失败,跳过", flush=True)
                continue

            record = {
                "profile_id": prof["profile_id"],
                "profile": {
                    "skills": prof["skills"],
                    "target_role": prof.get("target_role"),
                    "years_experience": prof.get("years_experience"),
                    "education": prof.get("education"),
                    "seed_role_id": prof.get("seed_role_id"),
                    "seed_coarse_role": prof.get("seed_coarse_role"),
                },
                "candidates": [
                    {
                        "job_id": c["job_id"],
                        "label": labeled[c["job_id"]],
                        "features": f,
                        "summary": c,
                    }
                    for c, f in zip(candidates, feature_rows)
                ],
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["n_profiles_written"] += 1
            stats["n_candidates"] += len(candidates)
            for v in labeled.values():
                label_counter[str(v)] += 1
            if i % 10 == 0 or i == len(profiles):
                print(
                    f"[{i}/{len(profiles)}] written={stats['n_profiles_written']} "
                    f"failed={stats['profile_failures']} calls={stats['deepseek_calls']} "
                    f"call_fail={stats['deepseek_call_failures']}",
                    flush=True,
                )
            time.sleep(args.sleep)

    stats["label_distribution"] = dict(sorted(label_counter.items()))
    stats["seconds"] = round(time.time() - started, 1)
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    print(f"[done] {out_path} / {STATS_PATH}", flush=True)


if __name__ == "__main__":
    main()
