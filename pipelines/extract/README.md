# JD 技能抽取（B 模块输入层）

把多源 JD 数据统一过技能词表抽取技能，产出供下游分层聚类（`pipelines/taxonomy`）使用的统一 JSONL。技能归一化复用 `app/services/skill_norm.py` 的全队公共词表，保证 A/B/D 口径一致。

## 数据流

```
asaniczka / Djinni / emerging 三源原始 JD
        │  skill_norm 词表匹配 / 模型抽取
        ▼
   extract_all_skills.py  → data/silver/all_jd_skills_v1.jsonl (+ stats)
        ▼
   pipelines/taxonomy/cluster_roles.py
```

## 文件说明

| 文件 | 作用 | 运行 | 产出 |
|------|------|------|------|
| `extract_all_skills.py` | 统一抽取层：三源（asaniczka / Djinni / emerging）统一过 `skill_norm` 词表抽技能，输出统一 JSONL，并统计数据源规模、技能覆盖率、方向标签分布、高频未匹配候选词 | `python -m pipelines.extract.extract_all_skills` | `data/silver/all_jd_skills_v1.jsonl`、`data/silver/all_jd_skills_stats_v1.json` |
| `match_djinni_skills.py` | Djinni 全量词典匹配版：用 asaniczka 已有技能名组成词表，在 Djinni JD 正文里扫描匹配（无模型、快、风格统一） | `python -m pipelines.extract.match_djinni_skills` | `data/gold/djinni_skill_match_v1.json` |
| `extract_djinni_skills.py` | Djinni 探路版：用 jjzha 的 knowledge + skill 两个配套模型抽取，先在前 N 条样本看效果 | `python -m pipelines.extract.extract_djinni_skills` | 控制台预览 |
| `weak_labeling.md` | 弱标注思路说明文档 | — | — |

## 可选环境变量

- `EMERGING_JD_JSONL`：emerging 源 JD 的路径覆盖（`extract_all_skills.py`）。
- `SKILL_VOCAB_PATH`：技能词表路径（默认 `data/gold/skill_vocab.json`，见 `app/services/skill_norm.py`）。

## 注意

- Djinni 当前为抽样/探路，技能尚未全量抽取；定稿前需补全量再重跑 `extract_all_skills.py`，然后下游 `cluster_roles.py` / `build_job_vectors.py` 一并重跑。
