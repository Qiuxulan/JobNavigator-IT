# app/services

各业务模块的服务层实现，被 `app/api/routes.py` 调用。下面重点说明 B 模块涉及的文件。

| 文件 | 模块 | 说明 |
|------|------|------|
| `recommender.py` | **B** | 职业推荐服务（双阶段：pgvector ANN 召回 + 多维精排），见下 |
| `skill_norm.py` | **B / 公共** | 技能归一化工具（全队公共），见下 |
| `extractor.py` | A | 简历/文本 → `UserProfile` 抽取 |
| `path_planner.py` | C | 缺口技能 → 学习路径 |
| `trend.py` | D | 趋势信号 |

## recommender.py（B 模块核心）

对外签名 `RecommenderService.recommend(profile, preference, top_k) -> list[RecommendationItem]`，返回结构保持稳定。

流程：

1. 用户画像拼成文本 → JobBERT-v3 编码 query 向量（`normalize_embeddings=True`）。
2. **阶段一召回**：`pipelines.taxonomy.recall.recall_topn` 用 pgvector `<=>` 余弦 ANN 取 Top-`RECALL_N`。
3. **阶段二精排**：`Final = ALPHA·语义 + BETA·约束 − GAMMA·缺口 + DELTA·趋势`，并算重合/缺口/加分技能与可解释理由。

数据依赖：

- postgres `job_roles` 表（向量由 `pipelines.taxonomy.build_job_vectors` 离线写入；DSN 用环境变量 `JOBNAV_POSTGRES_DSN`）。
- `data/gold/fine_grained_roles_v1.json`（补 `core_skills` / `optional_skills` / `skill_freq` 等精排字段）。
- 重依赖（`sentence-transformers`、`recall`）均为**函数内 import**，未装时不影响模块导入与其他测试。

精排会填充 `SkillGap.optional_skills`（加分技能：命中可加分但不计缺口）—— 该字段已在 `app/schemas/domain.py` 的 `SkillGap` 中补齐。

仍在用的临时占位（全局搜 `TODO` 定位）：`path_cost_score` 用缺口惩罚近似（待 C 接入）、`constraint_score` 固定 0.8（待岗位库补 city/salary/degree）、`trend_reward_score` 用关键词占位表（待 D 接入）、`JobRole.city/salary` 填 None、打分权重待评估集校准。

## skill_norm.py（全队公共）

技能写法归一化与文本词典匹配，词表与代码分离（词表更新只改 `data/gold/skill_vocab.json`，本模块不动）。

主要接口：`normalize_skill(raw)` / `normalize_skill_id(raw)` / `normalize_list(skills)` / `match_skills_in_text(text)`。词表路径可用 `SKILL_VOCAB_PATH` 覆盖。
