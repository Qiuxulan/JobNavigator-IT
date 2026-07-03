# 岗位体系与向量召回流水线

`pipelines/taxonomy` 负责维护细粒度岗位库、技能词表和 JobBERT 向量召回链路。当前线上粗召回依赖 PostgreSQL/pgvector 中的 `job_roles.embedding`，不再把 JSON 岗位匹配作为主路径。

## 数据流

```text
岗位/技能原始数据
  -> build_skill_vocab.py
  -> data/gold/skill_vocab.json
  -> cluster_roles.py / postprocess_roles.py
  -> data/gold/fine_grained_roles_v1.json
  -> build_job_vectors.py
  -> PostgreSQL job_roles.embedding
  -> recall.py / app.services.recommender
```

## 当前主数据

- `data/gold/fine_grained_roles_v1.json`：69 个细粒度岗位及岗位技能画像。
- `data/gold/skill_vocab.json`：全项目统一技能标准化词表。
- `data/gold/eval_set_v1.json`：岗位召回/推荐评估样本。
- PostgreSQL `job_roles.embedding`：JobBERT-v3 编码后的岗位向量。

`job_skill_profile_v1.json` 和 `role_name_mapping_v1.json` 属于旧版中间产物，当前运行链路不再保留为主数据。

## 主要脚本

| 脚本 | 作用 |
|---|---|
| `build_skill_vocab.py` | 构建当前统一技能词表 |
| `cluster_roles.py` | 从岗位技能文本聚类生成岗位草稿 |
| `postprocess_roles.py` | 根据人工规则合并、改名并生成最终岗位库 |
| `build_job_vectors.py` | 使用 `TechWolf/JobBERT-v3` 编码岗位文本并写入 pgvector |
| `recall.py` | 从 pgvector 召回 TopN 岗位候选 |
| `rank.py` | 早期精排原型，当前线上主要由服务层和 D 图谱精排接管 |
| `evaluate.py` | 计算 Hit@K、MRR、NDCG 等推荐评估指标 |
| `diagnose_skills.py` | 检查岗位技能命名和标准化问题 |

## 向量召回约束

- 角色向量和用户 query 必须使用同一模型：`TechWolf/JobBERT-v3`。
- 向量维度为 1024，对齐 `infra/db/migrations/001_init.sql` 中的 `VECTOR(1024)`。
- 本地脚本连接数据库时使用 `localhost`；Docker 容器内使用 `postgres`。
- 缺模型缓存、缺 pgvector 或缺 `job_roles.embedding` 时应快速失败，而不是隐式降级。

## 常用命令

```powershell
python -m pipelines.taxonomy.build_skill_vocab
python -m pipelines.taxonomy.build_job_vectors
python -m pipelines.taxonomy.recall
python -m pipelines.taxonomy.evaluate
```
