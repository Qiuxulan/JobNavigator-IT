"""把审核通过的候选合并为 v4 增量技能词典 data/gold/skill_vocab_v4.json。

输入：
  data/gold/skill_vocab_review_v1.json（review_skill_vocab_v3.py 产出，keep=true 为准）
  data/gold/skill_vocab_v2.json + enrich_skills_v3.py 内 EXTRA_SKILL_ALIASES（去重基准）
输出：
  data/gold/skill_vocab_v4.json
    {"version": "4", "generated_at", "num_skills", "num_aliases",
     "skills": {canonical: {"aliases": [...], "category": ...}},
     "alias_to_canonical": {alias: canonical}}   # 供 enrich_skills_v3.py --vocab-v4 加载

合并规则：
  - 只收 keep=true；canonical 归一化为 slugify 形式；
  - canonical 已存在于 v2 alias_to_id 的值 或 EXTRA_SKILL_ALIASES 键 中 → 整技能跳过
    （说明 v2 词典已覆盖，避免重复 canonical）；
  - 别名与 v2/EXTRA 已有映射冲突时丢弃该别名（先到先得，v2 优先）；
  - 别名过 FT_DROP_ALIASES 屏蔽表（go/c/r/data 等全文歧义短词）；
  - 过短（<2 字符）或纯通用英语词别名丢弃。

用法：
  /var/lib/jobnav-env/bin/python pipelines/foundation/build_skill_vocab_v4.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipelines.extract.enrich_skills_v3 import (  # noqa: E402
    EXTRA_SKILL_ALIASES, FT_DROP_ALIASES, slugify,
)

REVIEW_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_review_v1.json")
V2_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_v2.json")
OUTPUT_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_v4.json")

# 常见英语单词黑名单之外的放行由 LLM 审核负责；这里只拦明显非技能形态的别名
BAD_ALIAS = re.compile(r"^(a|an|the|it|is|are|as|at|be|by|do|go|no|or|so|to|up|us|we|on|of|in|if)$")

# 词边界正则仍挡不住的高频英语/歧义别名，整别名丢弃（参照 FT_DROP_ALIASES 的思路）：
# access(it 动词"访问")/ad(广告)/vs(对比)/word/teams(团队协作)/scratch(from scratch)
RISKY_V4_ALIASES = {"access", "ad", "vs", "word", "teams", "scratch"}

# LLM 审核放行但人工复核认定为非技能/垃圾的 canonical，整条丢弃
JUNK_CANONICAL = {
    "online-job-platforms",      # "online job platforms" 非技能
    "audio-editing-software",    # 宽泛伞词
    "authoring-software",        # 宽泛伞词
    "audio-reproduction-software",
    "news-analytics",            # 非 IT 技能
    "repair-ict-devices",        # 硬件维修，别名 it equipment 会误伤
    "ict-device-protection",     # 与 anti-virus software 重复且别名含 use anti-virus software
    "develop-animations",        # 动画制作能力，非 IT 技能词
}


def main() -> None:
    review = json.load(open(REVIEW_PATH, encoding="utf-8"))
    v2 = json.load(open(V2_PATH, encoding="utf-8"))

    existing_alias = {a.lower() for a in v2["alias_to_id"]}
    existing_canonical = {slugify(v) for v in v2["alias_to_id"].values()}
    existing_canonical |= set(EXTRA_SKILL_ALIASES.keys())

    skills: dict[str, dict] = {}
    skipped_dup_skill, dropped_alias = 0, 0
    claimed: set[str] = set()  # 本批内已认领的别名（先到先得）
    for rec in review["reviews"]:
        if not rec["keep"]:
            continue
        canonical = slugify(rec["canonical"])
        if not canonical or canonical in existing_canonical or canonical in JUNK_CANONICAL:
            skipped_dup_skill += 1
            continue
        aliases: list[str] = []
        for a in [rec["canonical"], *rec.get("aliases", [])]:
            a = re.sub(r"\s+", " ", str(a).lower()).strip()
            if (len(a) < 2 or a in FT_DROP_ALIASES or a in RISKY_V4_ALIASES
                    or BAD_ALIAS.match(a)):
                dropped_alias += 1
                continue
            if a in existing_alias or a in aliases or a in claimed:
                dropped_alias += 1
                continue
            aliases.append(a)
        if not aliases:
            skipped_dup_skill += 1
            continue
        claimed.update(aliases)
        if canonical in skills:
            skills[canonical]["aliases"] = list(dict.fromkeys(skills[canonical]["aliases"] + aliases))
        else:
            skills[canonical] = {"aliases": aliases, "category": rec.get("category", "other")}

    alias_to_canonical: dict[str, str] = {}
    for canonical, info in skills.items():
        for a in info["aliases"]:
            alias_to_canonical.setdefault(a, canonical)

    out = {
        "version": "4",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "skill_vocab_candidates_v3 LLM review (keep=true)",
        "num_skills": len(skills),
        "num_aliases": len(alias_to_canonical),
        "stats": {"skipped_already_covered_or_no_alias": skipped_dup_skill,
                  "dropped_aliases": dropped_alias},
        "skills": skills,
        "alias_to_canonical": alias_to_canonical,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"num_skills": len(skills), "num_aliases": len(alias_to_canonical),
                      "stats": out["stats"]}, ensure_ascii=False))
    cats: dict[str, int] = {}
    for info in skills.values():
        cats[info["category"]] = cats.get(info["category"], 0) + 1
    print("category 分布：", json.dumps(cats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
