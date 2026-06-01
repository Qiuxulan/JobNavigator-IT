"""
技能诊断 - 看岗位库里的技能有多"不统一"

输出:
  1. 技能总数 / 去重后数量
  2. 疑似重复组(归一化后相同,但原始写法不同的)—— 这是归一化的主要目标
  3. 带"(方向)"占位标记的技能(Djinni 残留,需处理)
运行:python -m pipelines.taxonomy.diagnose_skills
"""

import json
import re
from collections import defaultdict

ROLES_JSON = "data/gold/fine_grained_roles_v1.json"


def basic_key(s: str) -> str:
    """基础归一化键:小写、去多余空格、去尾部标点 —— 用来判断'本质上是不是同一个技能'"""
    s = s.replace("(方向)", "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,/-")
    return s


def main():
    with open(ROLES_JSON, encoding="utf-8") as f:
        roles = json.load(f)

    all_skills = []
    has_direction_tag = []
    for r in roles:
        for sk in r.get("required_skills", []):
            all_skills.append(sk)
            if "(方向)" in sk:
                has_direction_tag.append(sk)

    print("=" * 60)
    print("技能诊断")
    print("=" * 60)
    print(f"技能出现总次数(含重复): {len(all_skills)}")
    print(f"原始去重后(精确匹配): {len(set(all_skills))} 种")

    # 按基础归一化键分组,找"本质相同但写法不同"的
    groups = defaultdict(set)
    for sk in all_skills:
        groups[basic_key(sk)].add(sk)

    print(f"基础归一化后: {len(groups)} 种")
    print(f"  -> 说明仅靠大小写/空格统一,就能合并掉 {len(set(all_skills)) - len(groups)} 个重复写法\n")

    # 列出有多种写法的组(归一化的主要目标)
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f">>> 疑似重复组(同一技能多种写法),共 {len(multi)} 组:\n")
    for k, variants in sorted(multi.items()):
        print(f"  [{k}] <- {sorted(variants)}")

    # Djinni 残留的方向标记
    print(f"\n>>> 带'(方向)'占位标记的技能,共 {len(set(has_direction_tag))} 种(Djinni残留,需处理):")
    for sk in sorted(set(has_direction_tag)):
        print(f"  {sk}")

    # 出现频率最高的技能(建词表时优先处理这些高频的)
    from collections import Counter
    freq = Counter(basic_key(s) for s in all_skills)
    print(f"\n>>> 出现频率 Top20 技能(建标准词表时优先覆盖):")
    for sk, c in freq.most_common(20):
        print(f"  {c:>3}  {sk}")


if __name__ == "__main__":
    main()