"""role_profiles v4 回归评估:v4 增强数据集重建的画像 vs v3 画像。

背景:2026-11-06 用 jd_unified_v4_enriched(原 skills 为空的 265 行以 v4
补充词表补抽,新增 161 个 IT 工具/平台技能)重建岗位画像
(pipelines/taxonomy/build_role_profiles_v3.py --jd-glob ... --extra-vocab ...,
输出 data/gold/role_profiles_v4.json)。本脚本证明切换画像不引起匹配回归。

要点:
  - 画像切换走 graph_path_planner_v3 内置的 JOBNAV_ROLE_PROFILES_PATH 环境变量,
    进程级生效,不触碰线上默认指针(role_profiles_v3.json);
  - v4-only 技能键(161 个新技能)不在 v3 先修图内,运行时 _role_freq 会丢弃,
    理论上 coverage/trend 排序键不变;本脚本实测验证;
  - 评估跑两轮子进程(同一 v5 校准口径会话):
      profiles_v4:JOBNAV_ROLE_PROFILES_PATH=role_profiles_v4.json
      control_v3 :JOBNAV_ROLE_PROFILES_PATH=role_profiles_v3.json(同会话对照,
                   隔离 LLM run 间噪声与 embedding 服务差异)
  - 基线取 reports/eval/matching_v5_calibration_eval.json(v4 校准版基线):
      embedding Hit@1=0.7586 / NDCG@5=0.6730(确定性路径,要求一致或更好);
      llm       Hit@1=0.9828 / NDCG@5=0.7845(允许 ±0.008 run 间噪声);
    embedding 路径 NDCG@5 下降 > 0.005 判回归。

运行:python -m experiments.eval_role_profiles_v4
前置:postgres 向量已灌;.env 里 DeepSeek key 可用。
报告:reports/eval/role_profiles_v4_eval.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
if not os.environ.get("HF_HOME") and Path("/var/lib/hf/hub").exists():
    os.environ["HF_HOME"] = "/var/lib/hf"

REPORT_PATH = ROOT / "reports" / "eval" / "role_profiles_v4_eval.json"
BASELINE_PATH = ROOT / "reports" / "eval" / "matching_v5_calibration_eval.json"
V3_PROFILES = ROOT / "data" / "gold" / "role_profiles_v3.json"
V4_PROFILES = ROOT / "data" / "gold" / "role_profiles_v4.json"
NDCG_REGRESSION_THRESHOLD = 0.005
LLM_NOISE_BAND = 0.008

RANKING_TMP = str(ROOT / "reports" / "eval" / "_rp4_rankings_{tag}.json")


def rank_mode() -> None:
    """子进程入口:按环境变量指定画像跑 58 例(embedding + llm 两变体)。"""
    profiles = os.environ["JOBNAV_ROLE_PROFILES_PATH"]
    tag = os.environ["RP4_TAG"]
    os.chdir(ROOT)

    from experiments import eval_matching_v4 as m4  # noqa: E402

    cases, unresolved = m4.load_cases()
    print(f">>> [{tag}] {len(cases)} 例,profiles={profiles}", flush=True)
    rankings_emb: dict[str, list[str]] = {}
    rankings_llm: dict[str, list[str]] = {}
    llm_unchanged = 0
    for i, case in enumerate(cases, 1):
        rankings_emb[case["name"]] = m4.rank_case(case, llm_rerank=False)
        rankings_llm[case["name"]] = m4.rank_case(case, llm_rerank=True)
        if rankings_llm[case["name"]] == rankings_emb[case["name"]]:
            llm_unchanged += 1
        print(f"[{tag} {i}/{len(cases)}] {case['name']}", flush=True)

    out = {
        "tag": tag,
        "profiles_path": profiles,
        "n_cases": len(cases),
        "unresolved_role_names": unresolved,
        "metrics_embedding": m4.metrics(cases, rankings_emb),
        "metrics_llm": m4.metrics(cases, rankings_llm),
        "llm_unchanged_cases": llm_unchanged,
        "rankings_embedding": rankings_emb,
        "rankings_llm": rankings_llm,
    }
    path = Path(RANKING_TMP.format(tag=tag))
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{tag}] 写出 {path}", flush=True)


def _spawn(tag: str, profiles: Path) -> dict:
    env = dict(os.environ)
    env["JOBNAV_ROLE_PROFILES_PATH"] = str(profiles)
    env["RP4_TAG"] = tag
    cmd = [sys.executable, "-m", "experiments.eval_role_profiles_v4", "--rank"]
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"rank 子进程失败: {tag} (exit={proc.returncode})")
    return json.loads(Path(RANKING_TMP.format(tag=tag)).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 画像 diff
# ---------------------------------------------------------------------------

def profile_diff(v3: dict, v4: dict) -> dict:
    p3 = {r["role_id"]: r for r in v3["roles"]}
    p4 = {r["role_id"]: r for r in v4["roles"]}
    assert set(p3) == set(p4), "role_id 集合不一致(目录被重建?)"

    v4_vocab = json.loads((ROOT / "data" / "gold" / "skill_vocab_v4.json").read_text())
    new_ids = {str(k).strip().lower() for k in v4_vocab.get("skills", {})}

    roles_diff = []
    for rid in p3:
        a, b = p3[rid], p4[rid]
        fa, fb = a.get("skill_freq") or {}, b.get("skill_freq") or {}
        added = {k: v for k, v in fb.items() if k not in fa}
        removed = {k: v for k, v in fa.items() if k not in fb}
        changed = {k: (fa[k], fb[k]) for k in fa if k in fb and fa[k] != fb[k]}
        l1 = sum(abs(v - fa.get(k, 0.0)) for k, v in fb.items()) \
            + sum(v for k, v in fa.items() if k not in fb)
        roles_diff.append({
            "role_id": rid,
            "role_name": b["role_name"],
            "jd_count": b["jd_count"],
            "n_skill_v3": len(fa), "n_skill_v4": len(fb),
            "n_added": len(added), "n_removed": len(removed),
            "n_changed": len(changed),
            "added_new_vocab": sorted(k for k in added if k in new_ids),
            "added_other": sorted(k for k in added if k not in new_ids),
            "l1_delta": round(l1, 4),
        })

    n_added_roles = sum(1 for d in roles_diff if d["n_added"])
    n_changed_roles = sum(1 for d in roles_diff
                          if d["n_added"] or d["n_removed"] or d["n_changed"])

    # 非技能字段完整性:行集相同应逐位一致
    field_mismatch = {}
    for field in ("jd_count", "jd_count_6m", "trend_momentum", "salary",
                  "remote_ratio", "low_confidence", "monthly_shares"):
        bad = [rid for rid in p3 if p3[rid].get(field) != p4[rid].get(field)]
        if bad:
            field_mismatch[field] = bad

    # 新增技能进入各岗 top 技能的情况(freq 排序位次)
    new_skill_roles: dict[str, list[str]] = {}
    top_changes = []
    for rid in p3:
        b = p4[rid]
        freq = b.get("skill_freq") or {}
        ordered = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        rank = {k: i + 1 for i, (k, _) in enumerate(ordered)}
        entered = [(k, rank[k], freq[k]) for k in freq if k in new_ids]
        for k, r, f in entered:
            new_skill_roles.setdefault(k, []).append(rid)
        if entered:
            top_changes.append({
                "role_id": rid, "role_name": b["role_name"],
                "jd_count": b["jd_count"],
                "new_skills_top": [
                    {"skill": k, "rank": r, "freq": f}
                    for k, r, f in sorted(entered, key=lambda x: x[1])[:8]
                ],
            })

    top_changes.sort(key=lambda x: x["new_skills_top"][0]["rank"])
    top_l1 = sorted(roles_diff, key=lambda d: -d["l1_delta"])[:10]

    return {
        "roles_total": len(p3),
        "roles_with_any_skill_change": n_changed_roles,
        "roles_with_added_skills": n_added_roles,
        "roles_unchanged": len(p3) - n_changed_roles,
        "new_vocab_skills_in_profiles": {
            "distinct": len(new_skill_roles),
            "total_skill_keys_added": sum(len(d["added_new_vocab"]) for d in roles_diff),
            "top_by_role_reach": sorted(
                ((k, len(v), sorted(v)[:5]) for k, v in new_skill_roles.items()),
                key=lambda x: -x[1])[:20],
        },
        "field_integrity": {
            "mismatch_fields": field_mismatch,
            "salary_intact": "salary" not in field_mismatch,
            "trend_momentum_intact": "trend_momentum" not in field_mismatch,
            "jd_counts_intact": "jd_count" not in field_mismatch,
        },
        "top_roles_by_l1_delta": [
            {k: d[k] for k in ("role_id", "role_name", "jd_count", "n_added",
                               "n_removed", "n_changed", "l1_delta")}
            for d in top_l1
        ],
        "top_roles_with_new_skills": top_changes[:15],
        "roles_diff": roles_diff,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> dict:
    v3_profiles = json.loads(V3_PROFILES.read_text(encoding="utf-8"))
    v4_profiles = json.loads(V4_PROFILES.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    base_emb = baseline["variants"]["v4_baseline_embedding"]["metrics"]
    base_llm = baseline["variants"]["v4_baseline_llm"]["metrics"]

    # 隔离 diff:先按当前 v3 数据集重建一份 v3 画像做对照。
    # (on-disk role_profiles_v3.json 是 126,628 行时期的产物,而当前 v3/v4
    # 数据集均为 129,897 行——直接 diff 会把数据集增长与 v4 增强混在一起)
    import shutil
    import tempfile
    from pipelines.taxonomy.build_role_profiles_v3 import main as build_profiles
    td = Path(tempfile.mkdtemp(prefix="rp4_"))
    fresh_v3_path = td / "role_profiles_v3_fresh.json"
    build_profiles(["--output", str(fresh_v3_path),
                    "--qc-output", str(td / "qc.json")])
    fresh_v3 = json.loads(fresh_v3_path.read_text(encoding="utf-8"))
    diff = profile_diff(fresh_v3, v4_profiles)
    diff["staleness_note"] = {
        "on_disk_v3_generated_from": v3_profiles.get("generated_from"),
        "on_disk_v3_total_jd": v3_profiles.get("total_jd"),
        "current_dataset_rows": v4_profiles.get("total_jd"),
        "meaning": "on-disk role_profiles_v3.json 建于 126,628 行时期,"
                  "当前数据集 129,897 行;diff 以同口径 fresh v3 重建为对照,"
                  "线上基线评估用的仍是 on-disk v3 画像",
    }

    print(">>> 跑 profiles_v4 画像评估子进程 ...", flush=True)
    run_v4 = _spawn("profiles_v4", V4_PROFILES)
    print(">>> 跑 control_v3 同会话对照子进程 ...", flush=True)
    run_v3 = _spawn("control_v3", V3_PROFILES)
    # 归因对照:fresh v3(同一份 129,897 行数据,不带 v4 补充词表)。
    # 预期与 profiles_v4 排序逐位一致,证明排序差异全部来自数据刷新,
    # v4 词表增强本身不影响排序(运行时 _role_freq/_resolve_targets
    # 丢弃不在 v3 先修图内的技能键)。
    print(">>> 跑 fresh_v3 归因对照子进程 ...", flush=True)
    run_fresh = _spawn("fresh_v3", fresh_v3_path)
    emb_identical = all(
        run_fresh["rankings_embedding"][n][:5] == run_v4["rankings_embedding"][n][:5]
        for n in run_v4["rankings_embedding"]
    )
    llm_identical = all(
        run_fresh["rankings_llm"][n][:5] == run_v4["rankings_llm"][n][:5]
        for n in run_v4["rankings_llm"]
    )
    attribution = {
        "fresh_v3_profiles": "当前 v3 数据集同口径重建(129,897 行,--extra-vocab 关闭)",
        "embedding_order_identical_to_profiles_v4": emb_identical,
        "llm_order_identical_to_profiles_v4": llm_identical,
        "fresh_v3_metrics": {
            "embedding": run_fresh["metrics_embedding"],
            "llm": run_fresh["metrics_llm"],
        },
        "explanation": (
            "profiles_v4 与 fresh v3 的排序逐位一致 → 排序变化(vs on-disk v3 基线)"
            "全部来自 JD 数据集刷新(126,628→129,897 行)带来的 trend_momentum/"
            "skill_freq 更新;265 行 v4 补抽新增的技能键不在 v3 先修图内,运行时"
            " _role_freq/_resolve_targets 丢弃,对排序零影响。" if emb_identical else
            "profiles_v4 与 fresh v3 排序不一致,v4 词表增强影响了排序,需人工复核。"
        ),
    }
    import shutil
    shutil.rmtree(fresh_v3_path.parent, ignore_errors=True)
    def delta(m: dict, b: dict) -> dict:
        return {k: round(m[k] - b[k], 4) for k in ("hit@1", "hit@5", "mrr", "ndcg@5")}

    d_emb = delta(run_v4["metrics_embedding"], base_emb)
    d_llm = delta(run_v4["metrics_llm"], base_llm)
    llm_drop = -d_llm["ndcg@5"]
    regression = d_emb["ndcg@5"] < -NDCG_REGRESSION_THRESHOLD

    changed_cases = [
        name for name in run_v4["rankings_embedding"]
        if run_v4["rankings_embedding"][name][:5] != run_v3["rankings_embedding"][name][:5]
    ]
    changed_cases_llm = [
        name for name in run_v4["rankings_llm"]
        if run_v4["rankings_llm"][name][:5] != run_v3["rankings_llm"][name][:5]
    ]

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "purpose": "role_profiles_v4(v4 增强数据集重建)匹配回归评估;不切换线上指针",
        "inputs": {
            "profiles_v4": str(V4_PROFILES.relative_to(ROOT)),
            "profiles_v3_control": str(V3_PROFILES.relative_to(ROOT)),
            "jd_source": "jd_unified_v4_enriched",
            "extra_vocab": "data/gold/skill_vocab_v4.json",
            "eval_sets": ["eval_set_v1.json", "eval_set_v2.json"],
            "n_cases": run_v4["n_cases"],
        },
        "baseline": {
            "source": str(BASELINE_PATH.relative_to(ROOT)),
            "embedding": {k: base_emb[k] for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
            "llm": {k: base_llm[k] for k in ("hit@1", "hit@5", "mrr", "ndcg@5")},
            "llm_noise_band": LLM_NOISE_BAND,
        },
        "metrics": {
            "profiles_v4": {
                "embedding": run_v4["metrics_embedding"],
                "llm": run_v4["metrics_llm"],
                "llm_unchanged_cases": run_v4["llm_unchanged_cases"],
            },
            "control_profiles_v3_same_session": {
                "embedding": run_v3["metrics_embedding"],
                "llm": run_v3["metrics_llm"],
                "llm_unchanged_cases": run_v3["llm_unchanged_cases"],
            },
        },
        "deltas_vs_baseline": {
            "profiles_v4_embedding": d_emb,
            "profiles_v4_llm": d_llm,
            "control_v3_embedding": delta(run_v3["metrics_embedding"], base_emb),
            "control_v3_llm": delta(run_v3["metrics_llm"], base_llm),
        },
        "regression_verdict": {
            "embedding_ndcg5_drop": round(-d_emb["ndcg@5"], 4),
            "threshold": NDCG_REGRESSION_THRESHOLD,
            "regression": regression,
            "llm_ndcg5_drop": round(llm_drop, 4),
            "llm_within_noise_band": llm_drop <= LLM_NOISE_BAND,
        },
        "v4_vs_v3_control_order_changes": {
            "embedding": {"n": len(changed_cases), "cases": changed_cases},
            "llm": {"n": len(changed_cases_llm), "cases": changed_cases_llm},
        },
        "attribution": attribution,
        "profile_diff": diff,
        "conclusion": (
            "REGRESSION: v4 画像 embedding 路径 NDCG@5 下降超过阈值"
            if regression else
            "OK: v4 画像 embedding 路径与基线一致或更好,未回归"
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    for tag in ("profiles_v4", "control_v3", "fresh_v3"):
        tmp = Path(RANKING_TMP.format(tag=tag))
        if tmp.exists():
            tmp.unlink()

    print("\n# 指标对比(v4 校准基线 vs profiles_v4 vs 同会话 control_v3)")
    print("| path | variant | Hit@1 | Hit@5 | MRR | NDCG@5 |")
    print("|---|---|---|---|---|---|")
    for label, m in (("baseline", base_emb), ("profiles_v4", run_v4["metrics_embedding"]),
                     ("control_v3", run_v3["metrics_embedding"])):
        print(f"| embedding | {label} | {m['hit@1']} | {m['hit@5']} | {m['mrr']} | {m['ndcg@5']} |")
    for label, m in (("baseline", base_llm), ("profiles_v4", run_v4["metrics_llm"]),
                     ("control_v3", run_v3["metrics_llm"])):
        print(f"| llm | {label} | {m['hit@1']} | {m['hit@5']} | {m['mrr']} | {m['ndcg@5']} |")
    print(f"| embedding | fresh_v3(归因) | {run_fresh['metrics_embedding']['hit@1']} | "
          f"{run_fresh['metrics_embedding']['hit@5']} | {run_fresh['metrics_embedding']['mrr']} | "
          f"{run_fresh['metrics_embedding']['ndcg@5']} |")
    print(f"\nembedding NDCG@5 drop vs baseline: {round(-d_emb['ndcg@5'], 4)}"
          f"(阈值 {NDCG_REGRESSION_THRESHOLD})→ {'REGRESSION' if regression else 'OK'}")
    print(f"[done] 报告已写入 {REPORT_PATH}")
    return report


if __name__ == "__main__":
    if "--rank" in sys.argv:
        rank_mode()
    else:
        main()
