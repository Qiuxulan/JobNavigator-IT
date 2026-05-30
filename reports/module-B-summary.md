# 模块 B 总结文档：细粒度岗位库 + 推荐模型

> 对应分工：`docs/01-product-roadmap/03-overall-team-assignment-3-weeks.md` 中的 **B：细粒度岗位库 + 推荐模型负责人**。
> 本文档说明本轮更新了哪些文件、每个文件的处理逻辑、产出物、运行方式，以及其他模块（A/C/D）需要注意的事项。

## 1. 模块目标

构建细粒度岗位体系并实现双阶段推荐（不做学习路径本身）：

1. JD 标题粗粒度标准化（数据/后端/AI 应用等大类）。
2. 细粒度岗位构建（JD 向量化 → 聚类 → 簇命名）。
3. 岗位技能画像（每个岗位高频技能 TopN，形成 `job -> required_skills`）。
4. 双阶段推荐：阶段一向量召回 TopN，阶段二多维精排。
5. 可解释推荐结果：匹配分数、重合技能、缺口技能（给 C 用）、推荐理由。

## 2. 本轮更新/新增的文件

### 修改
| 文件 | 改动 |
|------|------|
| `app/schemas/domain.py` | `SkillGap` 新增字段 `optional_skills`（加分技能：命中可加分、不计缺口，仅展示/解释）。recommender 已在产出，此前 schema 缺字段。 |
| `app/services/recommender.py` | 重写为双阶段（pgvector ANN 召回 + 多维精排）；重依赖改函数内 import；产出 `overlap/missing/optional` 技能与可解释理由。 |
| `infra/db/migrations/001_init.sql` | `job_roles.embedding` 维度 `VECTOR(384) → VECTOR(1024)`（对齐 JobBERT-v3 输出；旧 384 是 SBERT 维度，是 bug）。 |
| `requirements.txt` / `environment.yml` | 补 `pgvector`、`sentence-transformers`、`transformers`、`scikit-learn` 等推荐链依赖。 |
| `.github/workflows/ci.yml` | 增加 `pgvector/pgvector:pg16` 的 postgres service，CI 中执行 `001_init.sql` 建库建扩展，并设 `JOBNAV_POSTGRES_DSN`，使依赖 pgvector 的代码路径可在 CI 连库。 |

### 新增
| 文件 | 作用 |
|------|------|
| `app/services/skill_norm.py` | 全队公共技能归一化工具（词表与代码分离）。 |
| `pipelines/extract/extract_all_skills.py` | 三源统一抽取层 → 统一 JSONL。 |
| `pipelines/extract/match_djinni_skills.py` | Djinni 全量词典匹配抽取。 |
| `pipelines/extract/extract_djinni_skills.py` | Djinni 模型抽取探路版。 |
| `pipelines/taxonomy/build_skill_vocab.py` | 完整 IT 标准技能词表（全队共用，`skill_norm` 实际使用）。 |
| `pipelines/taxonomy/build_skill_vocab_onet.py` | O*NET 辅助/参考词表（当前不被代码消费）。 |
| `pipelines/taxonomy/cluster_roles.py` | 细粒度岗位分层聚类。 |
| `pipelines/taxonomy/postprocess_roles.py` | 人工审定合并/改名 → 最终岗位库。 |
| `pipelines/taxonomy/build_job_vectors.py` | 岗位向量化并写入 pgvector。 |
| `pipelines/taxonomy/recall.py` | pgvector ANN 召回。 |
| `pipelines/taxonomy/rank.py` | 精排原型。 |
| `pipelines/taxonomy/evaluate.py` | 评估（Hit@1/Hit@K/MRR/NDCG@K）。 |
| `pipelines/taxonomy/diagnose_skills.py` | 技能统一性诊断。 |
| `pipelines/taxonomy/role_decisions.json` | 人工审定决策表（91→70）。 |
| `reports/module-B-summary.md` | 本文档。 |

各文件夹另有 README：`pipelines/taxonomy/README.md`、`pipelines/extract/README.md`、`app/services/README.md`。

## 3. 每个文件的详细处理逻辑

### 抽取层 `pipelines/extract`
- **extract_all_skills.py**：读 asaniczka / Djinni / emerging 三源 JD，统一过 `skill_norm` 词表抽技能，输出统一 JSONL；同时统计数据源规模、技能覆盖率、方向标签分布、高频未匹配候选词（用于扩词表）。
- **match_djinni_skills.py**：用 asaniczka 已有技能名构建词表，在 Djinni JD 正文做词典扫描匹配。设了最小词频/最小长度/单条上限三个阈值去长尾噪声。
- **extract_djinni_skills.py**：探路版，用 jjzha 的 knowledge + skill 两个模型在样本上抽取、句子级输入，先验证效果。

### 词表 / 归一化
- **build_skill_vocab.py**：构建全队统一标准词表（id/name/aliases/category/hot）→ `skill_vocab.json`，含 `alias_to_id`、`id_to_name`、`all_aliases`、`by_category`。这是 `skill_norm` 实际加载的词表。
- **build_skill_vocab_onet.py**：O*NET Technology Skills 全部技术名去重 + 标 Hot → `skill_vocab_onet.json`。辅助/参考用，当前不被任何代码消费。
- **app/services/skill_norm.py**：基于 `skill_vocab.json` 做归一化（任意写法→标准名/id）与文本词典匹配（长别名优先、词边界正则、分块编译）。

### 岗位库
- **cluster_roles.py**：读统一 JSONL，做向量化 + 分层 KMeans；emerging 单独聚类避免被 14 万 Djinni 大类淹没；聚类文本用 title + search_keyword + skills + JD 摘要；命名优先看 search_keyword 与技能画像。产出原始簇岗位库 + 技能画像。
- **postprocess_roles.py**：按 `role_decisions.json` 把 91 个原始簇合并/改名为最终 70 个独立岗位；自动备份原文件；产出最终岗位库、配套技能画像、91→70 映射表（答辩可追溯）。
- **diagnose_skills.py**：统计技能总数/去重数、疑似重复组、`(方向)` 残留，评估归一化收益。

### 召回 / 精排 / 评估
- **build_job_vectors.py**：读最终岗位库，用 JobBERT-v3 编码（文本拼法见“关键约束”），UPSERT 进 postgres `job_roles`（含 1024 维 embedding）。
- **recall.py**：线上把 query 向量与 `job_roles.embedding` 用 `<=>` 余弦 ANN 召回 TopN。
- **app/services/recommender.py**：召回 TopN → 精排 `Final = ALPHA·语义 + BETA·约束 − GAMMA·缺口 + DELTA·趋势`；缺口只针对核心技能（`core_skills`，无则退回 `required_skills`），`optional_skills` 仅展示；输出可解释理由与 `SkillGap`。
- **rank.py**：精排逻辑的独立原型/对照实现。
- **evaluate.py**：用 `eval_set_v1.json`（按岗位名标 ground truth，运行时解析成 role_id，重编号不失效）算 Hit@1/Hit@K/MRR/NDCG@K。

## 4. 产出物

| 产出 | 生成者 |
|------|--------|
| `data/silver/all_jd_skills_v1.jsonl`（+ stats） | extract_all_skills.py |
| `data/gold/djinni_skill_match_v1.json` | match_djinni_skills.py |
| `data/gold/skill_vocab_onet.json` | build_skill_vocab.py |
| `data/gold/skill_vocab.json` | Build skill vocab.py |
| `data/gold/fine_grained_roles_v1.json`（交付物①） | cluster_roles.py → postprocess_roles.py |
| `data/gold/job_skill_profile_v1.json`（交付物②） | postprocess_roles.py |
| `data/gold/role_name_mapping_v1.json` | postprocess_roles.py |
| postgres `job_roles` 表（含 embedding） | build_job_vectors.py |
| 推荐结果（`RecommendationItem` 列表，含 `SkillGap`） | recommender.py（交付物③对应 `app/services`） |
| `reports/recommend_eval_v1.md`（交付物④） | evaluate.py + 人工整理 |

## 5. 怎么运行

### 依赖与数据库
```bash
pip install -r requirements.txt          # 或 conda env create -f environment.yml
# 起带 pgvector 的 postgres（本地用 docker compose 或 pgvector/pgvector 镜像）
psql "$JOBNAV_POSTGRES_DSN" -f infra/db/migrations/001_init.sql
export JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@localhost:5432/jobnavigator
```

### 离线全链路（按顺序）
```bash
python -m pipelines.taxonomy.build_skill_vocab        # 全队标准词表(skill_norm 使用)
python -m pipelines.taxonomy.build_skill_vocab_onet    # O*NET 辅助词表(可选,不被代码消费)
python -m pipelines.extract.extract_all_skills         # 统一抽取
python -m pipelines.taxonomy.cluster_roles             # 聚类 → 原始簇
python -m pipelines.taxonomy.postprocess_roles         # 合并 → 最终岗位库
python -m pipelines.taxonomy.build_job_vectors         # 写 pgvector
python -m pipelines.taxonomy.recall                    # 召回冒烟
python -m pipelines.taxonomy.evaluate                  # 评估
```

### 线上调用
通过 `app/api/routes.py` → `RecommenderService.recommend(profile, preference, top_k)`，前提是已跑过 `build_job_vectors.py` 且 postgres 在线。

## 6. 其他模块需要注意

- **A（抽取/画像）**：推荐输入是 `UserProfile`（`skills` 用标准技能名）。技能归一化请统一用 `app/services/skill_norm.py`，词表更新只改 `data/gold/skill_vocab.json`，勿各自造词表。
- **C（学习路径）**：缺口技能从推荐结果 `RecommendationItem.skill_gap.missing_skills` 取；新增的 `optional_skills` 是加分技能，不属于必学缺口。`path_cost_score` 目前是缺口惩罚的占位，待 C 的 `path_planner` 接入后替换（recommender 里 TODO-1）。
- **D（趋势）**：`trend_reward_score` 现用关键词占位表（TODO-3），接入真实热度后替换；岗位库 `city/salary/degree` 字段补齐后，recommender 的 `constraint_score`（现固定 0.8，TODO-2）才能真算。
- **全员（DB / 向量一致性）**：`job_roles.embedding` 必须是 1024 维（JobBERT-v3）。query 与岗位向量的模型、文本拼法、`normalize_embeddings=True` 必须完全一致，否则 ANN 召回错位。改任一处需同步 `build_job_vectors.py` / `recall.py` / `recommender._load_engine`。
- **数据规模**：岗位库基于全量约 17 万条 JD（asaniczka 1.2 万 + Djinni 14.2 万 + emerging 1.7 万，Djinni 技能已全量抽取，见 `data/silver/all_jd_skills_stats_v1.json`）。聚类阶段为控制 KMeans 规模按粗粒度桶分层抽样（传统类每桶 5000、emerging 20000），技能画像基于全量统计。
- **CI**：`ci.yml` 已挂 pgvector postgres service 并执行迁移；依赖 DB 的测试需读 `JOBNAV_POSTGRES_DSN`。涉及模型下载/全量向量的端到端用例不在 CI 冒烟覆盖范围内。
