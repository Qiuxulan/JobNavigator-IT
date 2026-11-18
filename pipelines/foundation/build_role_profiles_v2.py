"""Build per-role skill profiles from the unified real-world JD corpus (v2).

Assigns each of the ~250k unified JDs to one of the fine-grained roles (v2 岗位库：
69 旧岗 + expand_roles 发现的新岗) using multi-signal title matching (exact canonical > alias regex > token overlap, with
skill co-occurrence as corroboration), then aggregates per-role profiles:
skill frequencies, core/required/optional skills, salary stats (USD), remote
ratio, seniority distribution and a continuous monthly JD-count series.

Inputs:
  data/gold/fine_grained_roles_v2.json   (默认；69 旧岗 + expand_roles 发现的新岗；
                                          缺文件回退 fine_grained_roles_v1.json)
  data/gold/role_taxonomy_v2.json        (默认；缺文件回退 role_taxonomy.json)
  data/gold/skill_vocab_v2.json          (295 skills, alias_to_id)
  /data/shichaojian/JNIT/processed/jd_unified/posted_month=*/part-0.parquet

Outputs:
  /data/shichaojian/JNIT/processed/jd_role_assignments.parquet
  data/gold/role_profiles_v2.json
  data/gold/role_profiles_v2_qc.json

Idempotent: outputs are overwritten on every run.

Usage:
  python -m pipelines.foundation.build_role_profiles_v2 [--threshold 0.45]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).parents[2]
DATA_GOLD_DIR = ROOT / "data" / "gold"
FINE_ROLES_JSON_V1 = DATA_GOLD_DIR / "fine_grained_roles_v1.json"
FINE_ROLES_JSON_V2 = DATA_GOLD_DIR / "fine_grained_roles_v2.json"
ROLE_TAXONOMY_JSON_V1 = DATA_GOLD_DIR / "role_taxonomy.json"
ROLE_TAXONOMY_JSON_V2 = DATA_GOLD_DIR / "role_taxonomy_v2.json"
SKILL_VOCAB_JSON = DATA_GOLD_DIR / "skill_vocab_v2.json"
PROFILES_V2_JSON = DATA_GOLD_DIR / "role_profiles_v2.json"
PROFILES_V2_QC_JSON = DATA_GOLD_DIR / "role_profiles_v2_qc.json"


def resolve_gold_json(v2_path: Path, v1_path: Path) -> Path:
    """v2 优先，缺文件回退 v1。"""
    return v2_path if v2_path.exists() else v1_path

DEFAULT_JD_ROOT = Path("/data/shichaojian/JNIT/processed/jd_unified")
DEFAULT_ASSIGNMENTS_PARQUET = DEFAULT_JD_ROOT.parent / "jd_role_assignments.parquet"

MONTH_START = "2020-01"
MONTH_END = "2026-10"

# Tokens that are too generic to identify a role on their own.
ROLE_STOPWORDS = {
    "engineer", "developer", "architect", "specialist", "administrator", "admin",
    "consultant", "manager", "lead", "senior", "junior", "middle", "staff",
    "principal", "sr", "jr", "software", "analyst", "developerengineer",
}
# Single tokens that are ambiguous as skill/role evidence.
AMBIGUOUS_TOKENS = {"r", "c", "ai", "ml", "qa", "it", "ux", "ui", "bi"}
# Generic roles that need independent IT evidence before they may match.
GENERIC_IT_ROLES = {"Project Manager", "Product Manager", "Delivery Manager", "Business Analyst"}
# Single-word search facet keywords (languages/levels) that must not become aliases.
FACET_WORDS = {
    "python", "java", "javascript", "typescript", "golang", "go", "ruby", "php", "scala", "sql",
    "c++", "c#", ".net", "rust", "kotlin", "swift", "html", "css", "r", "node.js", "react", "angular",
    "vue", "lead", "other", "senior", "junior", "mid", "remote", "security", "design", "qa", "ml",
    "android", "ios", "unity", "flutter", "model", "biologist", "mathematician", "geophysicist",
    "chemist", "tier", "stand-in", "starter",
}
# Single-word search keywords that are legitimate standalone aliases, and the
# role that owns them (search facet data repeats them across unrelated roles).
SINGLE_WORD_ALIAS_OWNER = {"sysadmin": "System Administrator", "devops": "DevOps Engineer"}
# Tokens too generic to identify a role from a single-token overlap.
GENERIC_FAMILY_TOKENS = {
    "backend", "frontend", "fullstack", "full-stack", "cloud", "data", "mobile", "web",
    "designer", "artist", "product", "project", "operations", "support", "delivery",
    "coordinator", "associate", "supervisor", "sales", "marketing", "success", "business",
    "executive", "administrative", "recruiter", "account", "finance",
}
# Extra aliases that are well-known synonyms but absent from the gold inputs.
EXTRA_ROLE_ALIASES = {
    "DevOps Engineer": ["site reliability engineer", "sre"],
}
# Informal title tokens mapped to the canonical token used by role names.
TOKEN_EQUIV = {
    "golang": "go", "node": "node.js", "js": "javascript", "reactjs": "react",
    "angularjs": "angular", "vuejs": "vue", "ts": "typescript", "postgres": "postgresql",
    "k8s": "kubernetes", "kubernettes": "kubernetes",
}

WORD_RE = re.compile(r"[a-z0-9+#.]+")


def month_range(start: str, end: str) -> list[str]:
    months: list[str] = []
    year, month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def title_tokens(text: str) -> set[str]:
    tokens = {tok for tok in WORD_RE.findall(str(text).lower()) if tok}
    for token in list(tokens):
        equiv = TOKEN_EQUIV.get(token)
        if equiv:
            tokens.add(equiv)
    return tokens


def role_tokens(text: str) -> set[str]:
    return {tok for tok in title_tokens(text) if tok not in ROLE_STOPWORDS and tok not in AMBIGUOUS_TOKENS}


def index_tokens(text: str) -> set[str]:
    return {tok for tok in title_tokens(text) if tok not in ROLE_STOPWORDS}


def term_pattern(value: str) -> re.Pattern[str] | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if len(normalized) < 3 and normalized not in {"c++", "c#", "go"}:
        return None
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])")


def load_inputs(jd_root: Path) -> tuple[list[dict[str, Any]], dict[str, str], pd.DataFrame, list[str]]:
    fine_roles_path = resolve_gold_json(FINE_ROLES_JSON_V2, FINE_ROLES_JSON_V1)
    taxonomy_path = resolve_gold_json(ROLE_TAXONOMY_JSON_V2, ROLE_TAXONOMY_JSON_V1)
    fine_roles = json.loads(fine_roles_path.read_text(encoding="utf-8"))
    taxonomy = {row["role_id"]: row for row in json.loads(taxonomy_path.read_text(encoding="utf-8"))}
    vocab = json.loads(SKILL_VOCAB_JSON.read_text(encoding="utf-8"))

    # skill alias -> id, lowercased for case-insensitive JD skill lookup.
    alias_to_id: dict[str, str] = {}
    for alias, skill_id in vocab.get("alias_to_id", {}).items():
        key = str(alias).strip().lower()
        if key:
            alias_to_id.setdefault(key, skill_id)
    for skill_id, name in vocab.get("id_to_name", {}).items():
        alias_to_id.setdefault(str(name).strip().lower(), skill_id)

    files = sorted(glob.glob(str(jd_root / "posted_month=*" / "part-0.parquet")))
    if not files:
        raise FileNotFoundError(f"no unified JD parquet files under {jd_root}")
    frame = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    frame["posted_month"] = frame["posted_month"].astype(str)
    months = month_range(MONTH_START, MONTH_END)

    roles: list[dict[str, Any]] = []
    for role in fine_roles:
        role_id = role["role_id"]
        tax = taxonomy.get(role_id, {})
        canonical = role.get("role_name") or tax.get("canonical_role") or role_id
        raw_aliases = list(tax.get("aliases") or [])
        for keyword in role.get("search_keywords") or []:
            key = str(keyword).strip().lower()
            words = key.split()
            if len(words) >= 2:
                raw_aliases.append(key)  # multi-word search phrases are real aliases
            elif key in SINGLE_WORD_ALIAS_OWNER and SINGLE_WORD_ALIAS_OWNER[key] == canonical:
                raw_aliases.append(key)
        canonical_index_tokens = index_tokens(canonical)
        if "designer" in canonical_index_tokens and ({"ui", "ux"} & canonical_index_tokens):
            raw_aliases += ["ui designer", "ux designer"]
        if "data base" in canonical.lower():
            raw_aliases.append(canonical.lower().replace("data base", "database"))
        raw_aliases += EXTRA_ROLE_ALIASES.get(canonical, [])
        seen: set[str] = set()
        aliases: list[str] = []
        for alias in raw_aliases:
            key = str(alias).strip().lower()
            if key and key != canonical.lower() and key not in seen:
                seen.add(key)
                aliases.append(key)

        alias_patterns: list[tuple[str, re.Pattern[str]]] = []
        for alias in aliases:
            pattern = term_pattern(alias)
            if pattern is not None:
                alias_patterns.append((alias, pattern))
        # Prefer the most specific (longest) alias on multi-match.
        alias_patterns.sort(key=lambda item: -len(item[0]))

        canonical_pattern = term_pattern(canonical)

        # Role skill id set: v1 core/required/optional ids + taxonomy top_skills mapped via vocab.
        vocab_ids = set(vocab.get("id_to_name", {}))
        skill_ids: set[str] = set()
        for field in ("core_skill_ids", "required_skill_ids", "optional_skill_ids"):
            for skill_id in role.get(field) or []:
                if skill_id and skill_id in vocab_ids:
                    skill_ids.add(skill_id)
        for name in tax.get("top_skills") or []:
            skill_id = alias_to_id.get(str(name).strip().lower())
            if skill_id:
                skill_ids.add(skill_id)

        all_tokens: set[str] = set()
        canonical_token_set = role_tokens(canonical)
        all_tokens |= index_tokens(canonical)
        for alias in aliases:
            all_tokens |= index_tokens(alias)

        # v2 新岗（如 Software Engineer (General)）的"裸头衔"护栏：只允许
        # 全匹配 guard 正则的 title 参与打分，防止抢走修饰头衔（如
        # "software engineer, machine learning"）的 JD。
        guard_raw = role.get("matcher_guard")
        guard_pattern = re.compile(guard_raw) if guard_raw else None

        roles.append(
            {
                "role_id": role_id,
                "role_name": canonical,
                "fine_role": role.get("fine_role", canonical),
                "coarse_role": role.get("coarse_role", tax.get("category", "unknown")),
                "canonical_lower": canonical.lower(),
                "canonical_pattern": canonical_pattern,
                "canonical_tokens": canonical_token_set,
                "alias_patterns": alias_patterns,
                "all_tokens": all_tokens,
                "skill_ids": skill_ids,
                "is_generic_it_role": canonical in GENERIC_IT_ROLES,
                "v1_top_skills": [str(s) for s in tax.get("top_skills") or []],
                "matcher_guard": guard_pattern,
            }
        )

    token_index: dict[str, list[int]] = {}
    for idx, role in enumerate(roles):
        for token in role["all_tokens"]:
            token_index.setdefault(token, []).append(idx)
    return roles, token_index, alias_to_id, frame, months


def normalize_jd_skills(raw_skills: Any, alias_to_id: dict[str, str]) -> set[str]:
    if raw_skills is None:
        return set()
    try:
        values = list(raw_skills)
    except TypeError:
        return set()
    found: set[str] = set()
    for value in values:
        key = str(value).strip().lower()
        if not key:
            continue
        skill_id = alias_to_id.get(key)
        if skill_id:
            found.add(skill_id)
    return found


def score_role(title_lower: str, title_token_set: set[str], jd_skill_ids: set[str], role: dict[str, Any]) -> tuple[float, str, int]:
    guard = role.get("matcher_guard")
    if guard is not None:
        cleaned = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.\s]", " ", title_lower)).strip()
        if not guard.fullmatch(cleaned):
            return 0.0, "none", 0

    score = 0.0
    matched_by = "none"

    canonical_pattern = role["canonical_pattern"]
    if canonical_pattern is not None and canonical_pattern.search(title_lower):
        score = 1.0
        matched_by = "title"
    else:
        for alias, pattern in role["alias_patterns"]:
            if pattern.search(title_lower):
                score = max(score, min(0.98, 0.86 + 0.04 * len(alias.split())))
                matched_by = "alias"
                break

    canonical_tokens = role["canonical_tokens"]
    role_skills = role["skill_ids"]
    skill_hits = len(jd_skill_ids & role_skills)

    if matched_by == "none" and canonical_tokens:
        matched = canonical_tokens & title_token_set
        overlap = len(matched) / len(canonical_tokens)
        if len(matched) >= 2 and overlap >= 0.5:
            score = max(score, round(0.5 + 0.3 * overlap, 6))
            matched_by = "tokens"
        elif len(matched) == 1 and overlap >= 0.5:
            if matched.isdisjoint(GENERIC_FAMILY_TOKENS):
                # A single highly-specific token (e.g. "java", "rust", "golang")
                # is weak but valid evidence on its own.
                score = max(score, 0.5)
                matched_by = "tokens"
            elif skill_hits >= 2:
                # Generic family tokens (backend/data/cloud...) only count when
                # skills corroborate; on their own they must not trigger a match.
                score = max(score, 0.3)
                matched_by = "tokens"

    if role_skills and skill_hits:
        hit_fraction = skill_hits / min(len(role_skills), 10)
        if matched_by != "none":
            score = min(1.2, score + 0.1 + 0.3 * hit_fraction)
            matched_by = f"{matched_by}+skill"
        elif skill_hits >= 3 and hit_fraction >= 0.3:
            score = max(score, min(0.6, 0.2 + 0.4 * hit_fraction))
            matched_by = "skill"

    if role["is_generic_it_role"]:
        if matched_by in {"title", "alias"} and skill_hits == 0:
            # Without skill evidence, require extra IT-context tokens in the title
            # (e.g. "IT Business Analyst"), otherwise a bare generic title like
            # "Business Analyst" is not necessarily an IT role.
            extra_tokens = title_token_set - canonical_tokens
            if len(extra_tokens) < 2:
                return 0.0, "none", 0
        if matched_by == "skill" and not (role["canonical_tokens"] & title_token_set):
            return 0.0, "none", 0

    return round(score, 6), matched_by, skill_hits


def assign_roles(
    frame: pd.DataFrame, roles: list[dict[str, Any]], token_index: dict[str, list[int]],
    alias_to_id: dict[str, str], threshold: float,
) -> tuple[pd.DataFrame, Counter]:
    records: list[dict[str, Any]] = []
    unassigned_titles: list[str] = []
    for job_id, row_idx, title, skills, month in zip(
        frame["job_id"], frame.index, frame["title"], frame["skills"], frame["posted_month"]
    ):
        title_lower = str(title or "").strip().lower()
        title_token_set = role_tokens(title_lower)
        jd_skill_ids = normalize_jd_skills(skills, alias_to_id)

        candidates: dict[int, None] = {}
        for token in title_tokens(title_lower):
            for idx in token_index.get(token, ()):
                candidates[idx] = None
        if not candidates:
            unassigned_titles.append(title_lower)
            continue

        best_idx, best_score, best_by, best_hits = -1, 0.0, "none", -1
        for idx in candidates:
            score, matched_by, skill_hits = score_role(title_lower, title_token_set, jd_skill_ids, roles[idx])
            if (
                best_idx < 0
                or score > best_score
                or (score == best_score and score > 0 and skill_hits > best_hits)
            ):
                best_idx, best_score, best_by, best_hits = idx, score, matched_by, skill_hits

        if best_idx < 0 or best_score < threshold:
            unassigned_titles.append(title_lower)
            continue
        records.append(
            {
                "job_id": job_id,
                "row_idx": row_idx,
                "role_id": roles[best_idx]["role_id"],
                "match_score": best_score,
                "match_type": best_by,
                "posted_month": month,
            }
        )

    assigned = pd.DataFrame(records, columns=["job_id", "row_idx", "role_id", "match_score", "match_type", "posted_month"])
    return assigned, Counter(unassigned_titles)


def build_profiles(
    frame: pd.DataFrame, assigned: pd.DataFrame, roles: list[dict[str, Any]],
    months: list[str], vocab: dict[str, Any],
) -> list[dict[str, Any]]:
    id_to_name = vocab.get("id_to_name", {})
    total_jd = len(frame)
    assigned_total = len(assigned)
    month_set = set(months)

    profiles: list[dict[str, Any]] = []
    for role in roles:
        role_id = role["role_id"]
        sub = assigned[assigned["role_id"] == role_id]
        jd_count = len(sub)
        frame_sub = frame.loc[sub["row_idx"]] if jd_count else frame.iloc[0:0]

        # Skill frequencies over the JDs assigned to this role.
        skill_counter: Counter[str] = Counter()
        for skills in frame_sub["skills"]:
            skill_counter.update(normalize_jd_skills(skills, GLOBAL_ALIAS_TO_ID))
        skill_freq = {
            skill_id: round(count / jd_count, 6)
            for skill_id, count in skill_counter.most_common()
            if jd_count
        }

        ordered = sorted(skill_freq.items(), key=lambda kv: (-kv[1], kv[0]))
        core = [(sid, f) for sid, f in ordered if f >= 0.20][:5]
        required = [(sid, f) for sid, f in ordered if f >= 0.08][:15]
        required_ids = {sid for sid, _ in required}
        optional = [(sid, f) for sid, f in ordered if f >= 0.03 and sid not in required_ids][:10]

        def names(pairs: list[tuple[str, float]]) -> list[str]:
            return [id_to_name.get(sid, sid) for sid, _ in pairs]

        # Salary stats on USD rows with both bounds present.
        usd = frame_sub[frame_sub["salary_currency"] == "USD"]
        mid = (pd.to_numeric(usd["salary_min_annual"], errors="coerce")
               + pd.to_numeric(usd["salary_max_annual"], errors="coerce")) / 2.0
        mid = mid.dropna()
        salary_stats = {
            "currency": "USD",
            "sample_size": int(len(mid)),
            "median": round(float(mid.median()), 2) if len(mid) else None,
            "p25": round(float(mid.quantile(0.25)), 2) if len(mid) else None,
            "p75": round(float(mid.quantile(0.75)), 2) if len(mid) else None,
        }

        remote = frame_sub["is_remote"]
        remote_known = remote.dropna()
        remote_ratio = round(float((remote_known == True).mean()), 6) if len(remote_known) else None  # noqa: E712

        seniority_known = frame_sub["seniority"].dropna().astype(str)
        seniority_dist = {
            key: round(value / len(seniority_known), 6)
            for key, value in Counter(seniority_known).most_common()
        } if len(seniority_known) else {}

        month_counts = Counter(sub["posted_month"]) if len(sub) else {}
        monthly = [
            {"month": m, "count": int(month_counts.get(m, 0))}
            for m in months
        ]
        assert len(monthly) == len(months) == 82, f"{role_id}: monthly series length {len(monthly)} != 82"
        assert all(entry["month"] in month_set for entry in monthly)

        profiles.append(
            {
                "role_id": role_id,
                "role_name": role["role_name"],
                "fine_role": role["fine_role"],
                "coarse_role": role["coarse_role"],
                "jd_count": jd_count,
                "assigned_ratio": round(jd_count / total_jd, 6) if total_jd else 0.0,
                "share_of_assigned": round(jd_count / assigned_total, 6) if assigned_total else 0.0,
                "mean_match_score": round(float(sub["match_score"].mean()), 6) if jd_count else None,
                "skill_freq": skill_freq,
                "core_skills": names(core),
                "core_skill_ids": [sid for sid, _ in core],
                "required_skills": names(required),
                "required_skill_ids": [sid for sid, _ in required],
                "optional_skills": names(optional),
                "optional_skill_ids": [sid for sid, _ in optional],
                "salary": salary_stats,
                "remote_ratio": remote_ratio,
                "seniority_distribution": seniority_dist,
                "monthly_jd_counts": monthly,
            }
        )
    return profiles


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def build_qc(
    frame: pd.DataFrame, assigned: pd.DataFrame, unassigned: Counter, roles: list[dict[str, Any]],
    profiles: list[dict[str, Any]], months: list[str], threshold: float,
) -> dict[str, Any]:
    total = len(frame)
    assigned_total = len(assigned)
    counts = sorted((p["jd_count"] for p in profiles))
    sparse = [p for p in profiles if p["jd_count"] < 50]

    unassigned_top = [
        {"title": title, "count": count}
        for title, count in unassigned.most_common(20)
    ]

    skill_drift: list[dict[str, Any]] = []
    profile_by_id = {p["role_id"]: p for p in profiles}
    for role in roles:
        profile = profile_by_id[role["role_id"]]
        new_top = set(profile["core_skills"] + profile["required_skills"][:10])
        old_top = set(role["v1_top_skills"])
        sim = jaccard(new_top, old_top)
        if sim < 0.3:
            skill_drift.append(
                {
                    "role_id": role["role_id"],
                    "role_name": role["role_name"],
                    "jd_count": profile["jd_count"],
                    "jaccard": round(sim, 4),
                    "v1_top_skills": sorted(old_top),
                    "v2_top_skills": sorted(new_top),
                }
            )
    skill_drift.sort(key=lambda row: row["jaccard"])

    monthly_ok = all(len(p["monthly_jd_counts"]) == len(months) for p in profiles)
    return {
        "threshold": threshold,
        "total_jd": total,
        "assigned_jd": assigned_total,
        "assignment_rate": round(assigned_total / total, 6) if total else 0.0,
        "jd_count_distribution": {
            "min": counts[0] if counts else 0,
            "p25": counts[len(counts) // 4] if counts else 0,
            "median": counts[len(counts) // 2] if counts else 0,
            "p75": counts[3 * len(counts) // 4] if counts else 0,
            "max": counts[-1] if counts else 0,
        },
        "sparse_roles_warning": [
            {"role_id": p["role_id"], "role_name": p["role_name"], "jd_count": p["jd_count"]}
            for p in sorted(sparse, key=lambda p: p["jd_count"])
        ],
        "unassigned_top_titles": unassigned_top,
        "skill_drift_warning": skill_drift,
        "monthly_series_complete": monthly_ok,
        "months": len(months),
    }


GLOBAL_ALIAS_TO_ID: dict[str, str] = {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v2 role profiles from the unified JD corpus")
    parser.add_argument("--threshold", type=float, default=0.45, help="min match score for JD assignment")
    parser.add_argument("--jd-root", type=Path, default=DEFAULT_JD_ROOT)
    parser.add_argument("--assignments-out", type=Path, default=DEFAULT_ASSIGNMENTS_PARQUET)
    args = parser.parse_args()

    global GLOBAL_ALIAS_TO_ID
    roles, token_index, alias_to_id, frame, months = load_inputs(args.jd_root)
    GLOBAL_ALIAS_TO_ID = alias_to_id
    vocab = json.loads(SKILL_VOCAB_JSON.read_text(encoding="utf-8"))
    print(f"loaded {len(frame)} JDs, {len(roles)} roles, month range {months[0]}..{months[-1]} ({len(months)} months)")

    assigned, unassigned = assign_roles(frame, roles, token_index, alias_to_id, args.threshold)
    print(f"assigned {len(assigned)}/{len(frame)} JDs ({len(assigned)/max(len(frame),1):.2%})")

    profiles = build_profiles(frame, assigned, roles, months, vocab)
    qc = build_qc(frame, assigned, unassigned, roles, profiles, months, args.threshold)

    args.assignments_out.parent.mkdir(parents=True, exist_ok=True)
    assigned_out = assigned[["job_id", "role_id", "match_score", "posted_month"]].copy()
    assigned_out.to_parquet(args.assignments_out, index=False)

    payload = {
        "version": "v2",
        "threshold": args.threshold,
        "total_jd": len(frame),
        "assigned_jd": len(assigned),
        "assignment_rate": qc["assignment_rate"],
        "months": months,
        "roles": profiles,
    }
    PROFILES_V2_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    PROFILES_V2_QC_JSON.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {args.assignments_out}")
    print(f"wrote {PROFILES_V2_JSON}")
    print(f"wrote {PROFILES_V2_QC_JSON}")


if __name__ == "__main__":
    main()
