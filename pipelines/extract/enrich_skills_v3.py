"""jd_unified_v3 技能补全后处理：对 skills 为空但 description_text 非空的行做规则技能抽取。

输入（不可变）：/data/shichaojian/JNIT/processed/jd_unified_v3/
输出（全量复制 + 更新 skills 列 + 新增 skills_enriched 布尔列）：
  /data/shichaojian/JNIT/processed/jd_unified_v3_enriched/
QC：/data/shichaojian/JNIT/processed/jd_unified_v3_enriched/_qc_report.json

技能来源：
  1. data/gold/skill_vocab_v2.json（295 技能，取 alias_to_id 全部别名）
  2. 代码内 EXTRA_SKILL_ALIASES：2024-2026 新词显式映射表
  3. （可选）--vocab-v4 显式传入 data/gold/skill_vocab_v4.json 时合并其增量别名；
     默认不传则行为与 v3 完全一致。v2/EXTRA 映射冲突时以既有映射优先（setdefault）。

匹配：大小写不敏感、词边界正则（非词字符别名用前后非字母数字边界，避免 c 误匹配 abc、
c++ 误匹配 c++17）。description 截断前 8000 字符。

用法：
  /var/lib/jobnav-env/bin/python pipelines/extract/enrich_skills_v3.py
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import pandas as pd
import numpy as np

VOCAB_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_v2.json")
DEFAULT_INPUT_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3")
DEFAULT_OUTPUT_DIR = Path("/data/shichaojian/JNIT/processed/jd_unified_v3_enriched")

MIN_DESCRIPTION_CHARS = 200
MAX_DESCRIPTION_CHARS = 8000

# ---------------------------------------------------------------------------
# 2024-2026 新词显式映射表：canonical slug -> 别名列表（小写）
EXTRA_SKILL_ALIASES: dict[str, list[str]] = {
    "llm": ["llm", "large language model"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "langchain": ["langchain"],
    "langgraph": ["langgraph"],
    "llama-index": ["llama-index", "llamaindex", "llama index"],
    "vector-database": ["vector database", "vector db", "vectordb", "pinecone",
                        "weaviate", "qdrant", "milvus", "faiss"],
    "prompt-engineering": ["prompt engineering"],
    "mcp": ["mcp", "model context protocol"],
    "vllm": ["vllm"],
    "lora": ["lora"],
    "fine-tuning": ["fine-tuning", "fine tuning", "finetuning", "fine-tune"],
    "ai-agents": ["ai agent", "ai agents", "agentic", "agentic ai", "autonomous agent"],
    "cursor": ["cursor"],
    "copilot": ["copilot", "github copilot", "microsoft copilot"],
    "hugging-face": ["hugging face", "huggingface", "hugging-face"],
    "generative-ai": ["generative ai", "genai", "gen ai"],
    "openai-api": ["openai", "chatgpt", "gpt-4", "gpt-5", "gpt4", "gpt5"],
    "mistral": ["mistral"],
    "ollama": ["ollama"],
    "n8n": ["n8n"],
    "crewai": ["crewai"],
    "autogen": ["autogen"],
    "diffusion-model": ["stable diffusion", "midjourney", "diffusion model"],
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", "-", str(value).lower()).strip("-")


# 全文描述匹配下歧义过高的别名（词边界仍挡不住常见英语词/字母），显式屏蔽；
# 各技能的更具体别名（golang/c语言/r语言/rest api 等）不受影响。
FT_DROP_ALIASES = {
    "c", "r", "go", "data", "form", "rest", "cv", "ct", "unity",
    "space", "light", "scale", "shade", "balance", "symmetry", "texture",
    "colour", "congruence", "proportion", "scope of design principles",
    "basis of design principles", "range of design principles",
}


def build_patterns(
    vocab_path: Path,
    vocab_v4_path: Path | None = None,
) -> list[tuple[str, str, "re.Pattern[str]"]]:
    """返回 [(canonical_slug, 小写别名, 编译正则)]，别名已去重。"""
    vocab = json.load(open(vocab_path, encoding="utf-8"))
    alias_to_canonical: dict[str, str] = {}
    for alias, skill_id in vocab["alias_to_id"].items():
        a = alias.lower()
        if a not in FT_DROP_ALIASES:
            alias_to_canonical.setdefault(a, slugify(skill_id))
    for slug, aliases in EXTRA_SKILL_ALIASES.items():
        for alias in aliases:
            alias_to_canonical.setdefault(alias.lower(), slug)
    if vocab_v4_path is not None and Path(vocab_v4_path).exists():
        v4 = json.load(open(vocab_v4_path, encoding="utf-8"))
        n_before = len(alias_to_canonical)
        for alias, slug in v4["alias_to_canonical"].items():
            a = alias.lower()
            if a not in FT_DROP_ALIASES:
                alias_to_canonical.setdefault(a, slugify(slug))
        print(f"v4 增量词典：{Path(vocab_v4_path).name}，"
              f"合并别名 +{len(alias_to_canonical) - n_before}")

    # 长别名优先，避免 "ai" 抢先于 "artificial intelligence"（ containment 预筛已缓解，双保险）
    patterns = []
    for alias, canonical in sorted(alias_to_canonical.items(), key=lambda kv: -len(kv[0])):
        escaped = re.escape(alias)
        if re.fullmatch(r"[a-z0-9_ ]+", alias):
            pattern = re.compile(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", re.IGNORECASE)
        else:
            # 含特殊字符（c++/c#/.net/node.js 等）：边界放宽为"非字母数字"即可
            pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
        patterns.append((canonical, alias, pattern))
    return patterns


def extract_skills(text: str, patterns: list[tuple[str, str, "re.Pattern[str]"]]) -> list[str]:
    """规则抽取：返回命中的 canonical slug，保序去重。"""
    haystack = text[:MAX_DESCRIPTION_CHARS]
    lowered = haystack.lower()
    out, seen = [], set()
    for canonical, alias, pattern in patterns:
        if alias not in lowered:
            continue
        if pattern.search(haystack) and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="jd_unified_v3 技能规则抽取补全")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--vocab", type=Path, default=VOCAB_PATH)
    parser.add_argument("--vocab-v4", type=Path, default=None,
                        help="可选 v4 增量词典（如 data/gold/skill_vocab_v4.json）；"
                             "不传则与 v3 行为完全一致")
    args = parser.parse_args()

    patterns = build_patterns(args.vocab, args.vocab_v4)
    print(f"技能模式数：{len(patterns)}")

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    month_index = [str(m) for m in pd.period_range("2023-10", "2026-10", freq="M")] + ["unknown"]
    before_ratio: dict[str, dict] = {}
    after_ratio: dict[str, dict] = {}
    extracted_counter: dict[str, int] = {}
    samples: list[dict] = []

    for month in month_index:
        part_dir = args.input_dir / f"posted_month={month}"
        fp = part_dir / "part-0.parquet"
        if not fp.exists():
            continue
        df = pd.read_parquet(fp)

        # parquet round-trip 后 skills 单元格为 numpy.ndarray，需还原为 list
        skills = df["skills"].apply(
            lambda s: list(s) if isinstance(s, (list, tuple, np.ndarray)) else [])
        desc = df["description_text"].fillna("").astype(str)
        eligible = skills.apply(len).eq(0) & desc.str.len().ge(MIN_DESCRIPTION_CHARS)

        enriched_flag = pd.Series(False, index=df.index)
        new_skills = skills.copy()
        for idx in df.index[eligible]:
            found = extract_skills(desc.loc[idx], patterns)
            if found:
                new_skills.loc[idx] = found
                enriched_flag.loc[idx] = True
                for s in found:
                    extracted_counter[s] = extracted_counter.get(s, 0) + 1

        df["skills"] = new_skills
        df["skills_enriched"] = enriched_flag.astype(bool)

        n = len(df)
        before = skills.apply(len).gt(0).mean() if n else 0.0
        after = df["skills"].apply(len).gt(0).mean() if n else 0.0
        before_ratio[month] = {"rows": int(n), "skills_nonempty_ratio": round(float(before), 4)}
        after_ratio[month] = {"rows": int(n), "skills_nonempty_ratio": round(float(after), 4)}

        out_part = args.output_dir / f"posted_month={month}"
        out_part.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_part / "part-0.parquet", index=False)

        # 近三月抽取样本（title + 抽取技能）
        if month in ("2026-08", "2026-09", "2026-10"):
            picked = df[df["skills_enriched"]].head(4 if month == "2026-08" else 3)
            for _, row in picked.iterrows():
                samples.append({"month": month, "title": str(row["title"]),
                                "source": str(row["source"]),
                                "extracted_skills": list(row["skills"])})

    total_before = pd.DataFrame(before_ratio).T
    total_after = pd.DataFrame(after_ratio).T
    overall_before = (total_before["rows"] * total_before["skills_nonempty_ratio"]).sum() / total_before["rows"].sum()
    overall_after = (total_after["rows"] * total_after["skills_nonempty_ratio"]).sum() / total_after["rows"].sum()

    qc = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "input_dir": str(args.input_dir),
        "output_dir": str(args.output_dir),
        "min_description_chars": MIN_DESCRIPTION_CHARS,
        "max_description_chars_matched": MAX_DESCRIPTION_CHARS,
        "num_skill_patterns": len(patterns),
        "overall_skills_nonempty_ratio": {"before": round(float(overall_before), 4),
                                          "after": round(float(overall_after), 4)},
        "monthly_skills_nonempty": {m: {"before": before_ratio[m], "after": after_ratio[m]}
                                    for m in before_ratio},
        "extracted_skill_top30": sorted(extracted_counter.items(), key=lambda kv: -kv[1])[:30],
        "recent_month_samples": samples,
        "notes": [
            "仅处理 skills 为空且 description_text >= 200 字符的行；description 截断前 8000 字符匹配。",
            "skills_enriched=True 表示该行技能来自本脚本规则抽取（非源数据自带）。",
            "技能词典：data/gold/skill_vocab_v2.json 全部别名 + 脚本内 EXTRA_SKILL_ALIASES（2024-2026 新词显式映射表）。",
            *(["v4 增量词典：" + str(args.vocab_v4)] if args.vocab_v4 else []),
            "匹配为大小写不敏感词边界正则；含特殊字符别名（c++/c#/.net/node.js 等）用非字母数字边界，避免 c 误匹配、c++ 误匹配 c++17。",
        ],
    }
    with open(args.output_dir / "_qc_report.json", "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=2)

    print(json.dumps({"overall": qc["overall_skills_nonempty_ratio"],
                      "extracted_top10": qc["extracted_skill_top30"][:10]}, ensure_ascii=False, indent=2))
    print("\n按月 skills 非空率（前 -> 后）：")
    for m in before_ratio:
        b, a = before_ratio[m], after_ratio[m]
        print(f"  {m}: {b['skills_nonempty_ratio']:.3f} -> {a['skills_nonempty_ratio']:.3f} (rows={b['rows']})")


if __name__ == "__main__":
    main()
