"""
构建标准技能词表 - 基于 O*NET Technology Skills

来源:O*NET 30.3 "Technology Skills" 表(全部 Example 技术名)
策略:方案A - 不按职业筛,取全部技术名去重;额外标记 Hot Technology
产出:data/gold/skill_vocab_onet.json
  {
    "skills": [ {"name": "...", "hot": true/false, "category": "..."} ... ],
    "hot_skills": [...],   # 仅热门技术名(高质量子集)
    "all_names": [...]     # 所有技术名(给词典匹配直接用)
  }
运行:python -m pipelines.taxonomy.build_skill_vocab_onet
"""

import json
import pandas as pd

ONET_TXT = "data/raw/onet/Technology skills.txt"
OUT_JSON = "data/gold/skill_vocab_onet.json"


def main():
    print(">>> 读取 O*NET Technology Skills ...")
    df = pd.read_csv(ONET_TXT, sep="\t")
    print(f"    原始记录(职业-技术对): {len(df)}")

    # 一个技术名可能挂在多个职业下,按 Example 去重
    # 聚合:同一个技术名,只要在任一职业下是 Hot 就算 Hot
    df["Hot Technology"] = df["Hot Technology"].fillna("N").str.strip().str.upper()

    agg = (
        df.groupby("Example")
        .agg(
            hot=("Hot Technology", lambda s: (s == "Y").any()),
            category=("Commodity Title", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        )
        .reset_index()
    )

    skills = []
    for _, row in agg.iterrows():
        name = str(row["Example"]).strip()
        if not name:
            continue
        skills.append({
            "name": name,
            "hot": bool(row["hot"]),
            "category": str(row["category"]).strip(),
        })

    all_names = sorted({s["name"] for s in skills})
    hot_skills = sorted({s["name"] for s in skills if s["hot"]})

    out = {
        "source": "O*NET 30.3 Technology Skills",
        "total": len(all_names),
        "hot_count": len(hot_skills),
        "skills": sorted(skills, key=lambda x: x["name"]),
        "hot_skills": hot_skills,
        "all_names": all_names,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n>>> 词表构建完成:")
    print(f"    技术名总数(去重): {len(all_names)}")
    print(f"    其中热门技术(Hot): {len(hot_skills)}")
    print(f"    已写出: {OUT_JSON}")

    print(f"\n>>> 热门技术示例(前30个):")
    for n in hot_skills[:30]:
        print(f"    {n}")


if __name__ == "__main__":
    main()