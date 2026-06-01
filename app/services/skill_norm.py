"""
技能归一化工具(全队公共)

职责:
  1. normalize_skill(raw)      : 任意技能写法 -> 标准名(归一化),不在词表中返回 None
  2. normalize_skill_id(raw)   : 任意技能写法 -> skill_id
  3. normalize_list(skills)    : 批量归一化一个技能列表,去重、丢弃无法识别项
  4. match_skills_in_text(text): 从一段文本(如 JD 正文)中词典匹配出标准技能

数据来源:data/gold/skill_vocab.json(由 pipelines/taxonomy/build_skill_vocab.py 生成)

用法:
    from app.services.skill_norm import normalize_list, match_skills_in_text
    clean = normalize_list(["JAVA", "Postgresql", "Trust"])   # -> ["Java", "PostgreSQL"]
    skills = match_skills_in_text(jd_text)                     # -> ["Python", "Docker", ...]

设计:词表与代码分离 —— A 的技能词表、新技能只需合并进 skill_vocab.json,本模块不改。
"""

import json
import re
import os
from functools import lru_cache

VOCAB_PATH = os.environ.get("SKILL_VOCAB_PATH", "data/gold/skill_vocab.json")


@lru_cache(maxsize=1)
def _load_vocab():
    with open(VOCAB_PATH, encoding="utf-8") as f:
        vocab = json.load(f)
    alias_to_id = vocab["alias_to_id"]
    id_to_name = vocab["id_to_name"]
    # 预编译分块正则用于文本匹配(长别名优先,避免子串误伤)
    aliases = sorted(vocab["all_aliases"], key=lambda s: (-len(s), s))
    chunks = []
    CHUNK = 300
    for i in range(0, len(aliases), CHUNK):
        part = aliases[i:i + CHUNK]
        pat = re.compile(
            r"(?<![A-Za-z0-9])(" + "|".join(re.escape(a) for a in part) + r")(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        chunks.append(pat)
    return alias_to_id, id_to_name, chunks


def _key(raw: str) -> str:
    return re.sub(r"\s+", " ", str(raw).strip().lower()).strip(" .*-")


def normalize_skill_id(raw: str):
    """任意写法 -> skill_id;无法识别返回 None"""
    alias_to_id, _, _ = _load_vocab()
    return alias_to_id.get(_key(raw))


def normalize_skill(raw: str):
    """任意写法 -> 标准显示名;无法识别返回 None"""
    alias_to_id, id_to_name, _ = _load_vocab()
    sid = alias_to_id.get(_key(raw))
    return id_to_name.get(sid) if sid else None


def normalize_list(skills):
    """批量归一化:去重、丢弃无法识别项,返回标准名列表(保持出现顺序)"""
    seen, out = set(), []
    for s in skills:
        name = normalize_skill(s)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def match_skills_in_text(text: str, max_skills: int = 40):
    """从一段文本中词典匹配出标准技能(用于 JD/简历正文抽取)"""
    alias_to_id, id_to_name, chunks = _load_vocab()
    text = str(text)
    found_ids = []
    seen = set()
    for pat in chunks:
        for m in pat.finditer(text):
            sid = alias_to_id.get(m.group(1).lower())
            if sid and sid not in seen:
                seen.add(sid)
                found_ids.append(sid)
                if len(found_ids) >= max_skills:
                    break
        if len(found_ids) >= max_skills:
            break
    return [id_to_name[i] for i in found_ids]


if __name__ == "__main__":
    # 自检
    print(normalize_list(["JAVA", "Postgresql", "k8s", "ML", "Trust", "rag"]))
    print(match_skills_in_text(
        "We need a backend engineer with Python, Docker, Kubernetes and RAG / LangChain experience."
    ))