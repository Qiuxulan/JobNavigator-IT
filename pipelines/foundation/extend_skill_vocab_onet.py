"""O*NET 31.0 + ESCO 技能词表候选扩展（人工/LLM 审核位，不并入主词表）。

从本地已下载的标准表（/data/shichaojian/JNIT/raw/standards/）中提取
「IT 相关且 skill_vocab_v2 缺失」的技能，输出候选清单
data/gold/skill_vocab_candidates_v3.json 供人工/LLM 审核后再进主词表。

候选来源与过滤规则：
  - O*NET software_skills.csv：Workplace Example（工具级技能名）出现在
    技术类 O*NET-SOC 职业（11-3021/15-12xx/15-2051/17-2061/49-2011）且
    带 Hot Technology 或 In Demand 标记，且未被现有词表别名覆盖；
    Element Name（如 "Development environment software"）作为类别上下文保留。
  - ESCO（tabiya v1.1.1 镜像）skills.csv：preferredLabel 命中 IT 关键词
    （编程语言/框架/工具/云/数据/AI 等）或 label 与 O*NET 热门工具名归一化
    一致，且未被现有词表别名覆盖；altLabels 作为建议别名带入。

去重：两个来源按归一化名称合并；与 skill_vocab_v2 已有别名做归一化
包含匹配（已有别名 >=3 字符且为候选名的子串/超串时视为已覆盖，跳过）。

用法：
  /var/lib/jobnav-env/bin/python pipelines/foundation/extend_skill_vocab_onet.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = Path("/data/shichaojian/JNIT/raw/standards")
VOCAB_PATH = ROOT / "data/gold/skill_vocab_v2.json"
DEFAULT_OUT = ROOT / "data/gold/skill_vocab_candidates_v3.json"

# 技术类 O*NET-SOC 前缀（计算机/信息系统/数据/硬件/网络支持）
ONET_TECH_SOC_PREFIXES = ("11-3021", "15-12", "15-2051", "17-2061", "49-2011")

# ESCO IT 相关技能关键词（标签匹配）
ESCO_IT_KEYWORDS = re.compile(
    r"programm|software|code|develop|script|framework|library|database|sql|"
    r"cloud|devops|kubernetes|docker|server|network|cybersecur|security|"
    r"artificial intelligence|machine learning|data |data-|analytics|big data|"
    r"python|java |javascript|typescript|react|angular|node|api |microservice|"
    r"linux|git|agile|scrum|ci/cd|pipeline|automation|infrastructure|platform|"
    r"algorithm|computing|ict|information technolog|web |frontend|back-?end|"
    r"full-?stack|mobile app|ios|android|testing|test |qa\b|etl|warehouse|"
    r"business intelligence|devsecops|sre\b|container|terraform|ansible|"
    r"nosql|mongodb|postgres|oracle|spark|hadoop|kafka|airflow|dbt|"
    r"computer vision|nlp|natural language|deep learning|neural|llm|"
    r"blockchain|cryptograph|sap|salesforce|excel|spreadsheet", re.I)


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", str(s).lower()).strip()


def load_existing_vocab(vocab_path: Path) -> tuple[set[str], dict[str, str]]:
    """返回 (归一化别名集合, 别名原样)。"""
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for skill in vocab.get("skills", []):
        aliases.setdefault(skill["name"].lower(), skill["id"])
        for a in skill.get("aliases") or []:
            aliases.setdefault(a.lower(), skill["id"])
    for a, sid in (vocab.get("alias_to_id") or {}).items():
        aliases.setdefault(a.lower(), sid)
    norm_set = {norm_name(a) for a in aliases if norm_name(a)}
    return norm_set, aliases


def covered_by_vocab(name: str, vocab_norm: set[str], vocab_aliases: dict[str, str]) -> bool:
    """候选名是否已被现有词表覆盖（归一化相等或互为子串，别名 >=3 字符）。"""
    n = norm_name(name)
    if not n:
        return True
    if n in vocab_norm:
        return True
    tokens = set(n.split())
    for alias, _sid in vocab_aliases.items():
        a = norm_name(alias)
        if len(a) < 3:
            continue
        if a and (a in n or (len(n) >= 3 and n in a)):
            return True
        # token 级：候选名全部由词表别名 token 组成且首个 token 匹配（防 "java developer" 误放）
    return False


# ---------------------------------------------------------------- O*NET

def onet_candidates(vocab_norm: set[str], vocab_aliases: dict[str, str]) -> dict[str, dict]:
    fp = STANDARDS / "onet31" / "software_skills.csv"
    df = pd.read_csv(fp, dtype=str).fillna("")
    df = df[df["O*NET-SOC Code"].str.startswith(ONET_TECH_SOC_PREFIXES)]
    df = df[(df["Hot Technology"] == "Y") | (df["In Demand"] == "Y")]
    # 剔除非工具名的元素级条目（Workplace Example 为空时退回 Element Name）
    df["candidate"] = df["Workplace Example"].where(
        df["Workplace Example"].str.strip().ne(""), df["Element Name"])
    df = df[df["candidate"].str.strip().ne("")]

    out: dict[str, dict] = {}
    for cand, g in df.groupby("candidate"):
        if covered_by_vocab(cand, vocab_norm, vocab_aliases):
            continue
        if not (3 <= len(cand) <= 60):
            continue
        n = norm_name(cand)
        entry = out.setdefault(n, {
            "name": cand, "source": "onet", "source_id": None,
            "suggested_zh": "", "aliases": [],
            "onet": {"hot_technology": False, "in_demand": False,
                     "element_name": sorted(set(g["Element Name"])),
                     "n_tech_occupations": 0},
        })
        entry["onet"]["hot_technology"] |= bool((g["Hot Technology"] == "Y").any())
        entry["onet"]["in_demand"] |= bool((g["In Demand"] == "Y").any())
        entry["onet"]["n_tech_occupations"] += int(g["O*NET-SOC Code"].nunique())
        eids = sorted(set(g["Element ID"]))
        if entry["source_id"] is None:
            entry["source_id"] = eids[0] if len(eids) == 1 else eids
    return out


# ---------------------------------------------------------------- ESCO

def esco_candidates(vocab_norm: set[str], vocab_aliases: dict[str, str],
                    onet_names: set[str]) -> dict[str, dict]:
    fp = STANDARDS / "tabiya_esco" / "tabiya-esco-v1.1.1" / "csv" / "skills.csv"
    df = pd.read_csv(fp, dtype=str).fillna("")
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        label = row["PREFERREDLABEL"].strip()
        if not (3 <= len(label) <= 60):
            continue
        n = norm_name(label)
        if n in onet_names:
            continue  # O*NET 侧已命中（合并逻辑在 main）
        if not ESCO_IT_KEYWORDS.search(label):
            continue
        if covered_by_vocab(label, vocab_norm, vocab_aliases):
            continue
        alt = [a.strip() for a in re.split(r"\n", row.get("ALTLABELS", ""))
               if a.strip() and 1 < len(a.strip()) <= 60][:8]
        out[n] = {
            "name": label, "source": "esco",
            "source_id": row.get("ORIGINURI") or row.get("ID"),
            "suggested_zh": "",
            "aliases": [a for a in alt
                        if not covered_by_vocab(a, vocab_norm, vocab_aliases)],
            "esco": {"skill_type": row.get("SKILLTYPE"),
                     "reuse_level": row.get("REUSELEVEL")},
        }
    return out


# ---------------------------------------------------------------- 主流程

def main() -> None:
    parser = argparse.ArgumentParser(description="O*NET/ESCO 词表候选扩展")
    parser.add_argument("--vocab", type=Path, default=VOCAB_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    vocab_norm, vocab_aliases = load_existing_vocab(args.vocab)
    print(f"现有词表别名（归一化）: {len(vocab_norm)}")

    onet = onet_candidates(vocab_norm, vocab_aliases)
    print(f"O*NET 候选: {len(onet)}")
    esco = esco_candidates(vocab_norm, vocab_aliases, set(onet))
    print(f"ESCO 候选: {len(esco)}")

    # 两源按归一化名合并
    merged: dict[str, dict] = {}
    for n, e in {**esco, **onet}.items():
        if n in merged and merged[n]["source"] != e["source"]:
            merged[n]["source"] = "onet+esco"
        merged[n] = e
    candidates = sorted(merged.values(),
                        key=lambda e: (not e.get("onet", {}).get("hot_technology", False),
                                       -e.get("onet", {}).get("n_tech_occupations", 0),
                                       e["name"].lower()))

    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": "candidates_pending_review",
        "review_note": "本清单未并入 skill_vocab_v2；需人工/LLM 审核后由 "
                       "pipelines/foundation/build_skill_vocab_v2.py 类流程合并。",
        "sources": {
            "onet": "db_31_0 software_skills.csv（Hot Technology / In Demand 标记）",
            "esco": "tabiya-open-dataset 镜像（ESCO v1.1.1）skills.csv",
        },
        "n_candidates": len(candidates),
        "candidates": candidates,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"-> {args.out} ({len(candidates)} candidates)")
    print("\nTop 20（按 hot/n_occupations 排序）:")
    for e in candidates[:20]:
        flags = []
        if e.get("onet", {}).get("hot_technology"):
            flags.append("HOT")
        if e.get("onet", {}).get("in_demand"):
            flags.append("IN-DEMAND")
        print(f"  [{e['source']:>9}] {e['name'][:50]:<52} {' '.join(flags)}")


if __name__ == "__main__":
    main()
