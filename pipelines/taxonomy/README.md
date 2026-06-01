# 岗位体系流水线（B 模块）

细粒度岗位库 + 双阶段推荐的离线流水线。负责：从统一抽取产物出发，做岗位文本向量化、聚类、专家规则合并、簇命名，产出岗位库与岗位技能画像，并把岗位向量写入 pgvector 供线上召回。

> 不做学习路径本身（C 模块），不做趋势热度真实计算（D 模块）。本流水线只产出岗位库、技能画像和召回所需的向量。

## 数据流总览

```
data/silver/all_jd_skills_v1.jsonl   (来自 pipelines/extract)
        │  build_skill_vocab → data/gold/skill_vocab.json (skill_norm 实际使用)
        ▼
   cluster_roles.py        分层聚类 → 原始簇 fine_grained_roles_v1.json
        ▼
   postprocess_roles.py    人工审定合并(role_decisions.json) → 最终岗位库 + 技能画像 + 91→70 映射
        ▼
   build_job_vectors.py    JobBERT-v3 编码 → UPSERT 进 postgres job_roles.embedding (VECTOR 1024)
        ▼
   recall.py               线上召回:query 向量 ⨯ pgvector ANN(<=> 余弦) → TopN
        ▼
   rank.py / app.services.recommender   精排 + 缺口分析 + 可解释输出
        ▼
   evaluate.py             Hit@1 / Hit@K / MRR / NDCG@K
```

## 文件说明

| 文件 | 作用 | 运行 | 产出 |
|------|------|------|------|
| `build_skill_vocab.py` | 全队统一的完整 IT 技能标准词表（id/name/aliases/category/hot），供 `app.services.skill_norm` 归一化使用 —— **实际被消费的词表** | `python -m pipelines.taxonomy.build_skill_vocab` | `data/gold/skill_vocab.json` |
| `build_skill_vocab_onet.py` | 由 O*NET Technology Skills 生成的辅助/参考词表（方案 A：取全部技术名去重，标记 Hot）。当前不被任何代码消费 | `python -m pipelines.taxonomy.build_skill_vocab_onet` | `data/gold/skill_vocab_onet.json` |
| `cluster_roles.py` | 分层 KMeans 聚类；emerging 单独聚类避免被 Djinni 大类淹没；簇命名优先看 search_keyword + 技能画像 | `python -m pipelines.taxonomy.cluster_roles` | `data/gold/fine_grained_roles_v1.json`（原始簇）、`job_skill_profile_v1.json` |
| `postprocess_roles.py` | 按人工审定决策表 `role_decisions.json` 合并/改名原始簇 → 最终岗位库；自动备份原文件 | `python -m pipelines.taxonomy.postprocess_roles` | `fine_grained_roles_v1.json`（最终 70 岗）、`job_skill_profile_v1.json`、`role_name_mapping_v1.json` |
| `build_job_vectors.py` | 用 JobBERT-v3 编码岗位文本，UPSERT 进 postgres `job_roles`（含 1024 维 embedding） | `python -m pipelines.taxonomy.build_job_vectors` | postgres `job_roles` 表 |
| `recall.py` | 线上召回（pgvector ANN）。冒烟：需先起 postgres 且跑过 build_job_vectors | `python -m pipelines.taxonomy.recall` | TopN 候选（内存返回） |
| `rank.py` | 精排原型：`Final = α·语义 + β·约束 − γ·缺口 + δ·趋势`，输出重合/缺口技能与理由 | `python pipelines/taxonomy/rank.py` | 控制台 |
| `evaluate.py` | 评估：Hit@1 / Hit@K / MRR / NDCG@K（评测集 `data/gold/eval_set_v1.json`） | `python -m pipelines.taxonomy.evaluate` | 控制台 / 报告数据 |
| `diagnose_skills.py` | 诊断岗位库技能不统一程度（疑似重复组、`(方向)` 残留） | `python -m pipelines.taxonomy.diagnose_skills` | 控制台 |
| `role_decisions.json` | 人工审定决策表（91→70 的合并/改名依据），`postprocess_roles.py` 的输入 | — | — |

## 关键约束（务必一致）

线上 query 向量与离线岗位向量必须在同一语义空间，否则 ANN 召回错位：

- 模型：`TechWolf/JobBERT-v3`
- 文本拼法：`f"{role_name}. Required skills: {required_skills 去(方向)}"`（用 15 个宽画像 `required_skills`，不是 `core_skills`）
- `normalize_embeddings=True`（余弦口径）
- 向量维度 1024，与 `infra/db/migrations/001_init.sql` 的 `VECTOR(1024)` 对齐

## 当前状态 / 待办

- 岗位库当前基于 6000 条抽样，Djinni 部分技能尚未全量抽取；定稿时需用全量数据重跑 `cluster_roles.py` + `build_job_vectors.py`。
- 打分权重 ALPHA/BETA/GAMMA/DELTA 为经验值，已用评估集初步校准（GAMMA=0.02），详见 `reports/recommend_eval_v1.md`。
