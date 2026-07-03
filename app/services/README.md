# app/services

`app/services` 是 FastAPI 的业务服务层，由 `app/api/routes.py` 调用。当前服务按“抽取、职业推荐、图谱路径、行业趋势、证据与报告”划分。

## 服务说明

| 文件 | 作用 |
|---|---|
| `extractor.py` | 统一简历抽取入口：微调模型优先，规则兜底 |
| `skill_norm.py` | 技能标准化和文本技能匹配，读取 `data/gold/skill_vocab.json` |
| `career_catalog.py` | 岗位目录读取与岗位名解析 |
| `recommender.py` | 岗位推荐服务，复用 JobBERT/pgvector 粗召回与 D 图谱精排结果 |
| `career_pathway_service.py` | D 模块端到端编排：抽取、标准化、召回、精排、路径生成 |
| `graph_path_planner_v2.py` | 基于职业图谱和 GraphSAGE 的学习路径搜索 |
| `path_planner.py` | 学习路径兼容编排层，优先调用新版图谱路径逻辑 |
| `trend.py` | 趋势查询服务，优先读取 PatchTST 预测和真实趋势特征 |
| `trend_predictor.py` | PatchTST 预测结果读取、平滑和 horizon 聚合 |
| `evidence.py` | 趋势证据检索与证据排序 |
| `trend_explanation.py` | 趋势解释上下文组装 |
| `agent.py` | Agent 工具调用与问答编排 |
| `report_generator.py` | 职业匹配和学习路径报告生成 |

## 运行依赖

- 职业推荐粗召回依赖 PostgreSQL/pgvector 中的 `job_roles.embedding`。
- 技能标准化依赖 `data/gold/skill_vocab.json`。
- D 图谱路径依赖 `fine_grained_roles_v1.json`、`skill_prerequisite_v2.json`、学习资源和 GraphSAGE 产物。
- 趋势接口依赖 `role_month_features.json`、`patchtst_predictions_36m.json` 和证据文件。
- LLM 报告和 Agent 总结依赖 `.env` 中的 `JOBNAV_LLM_*` 配置；无 Key 时应保留本地数据能力，不伪造外部模型回答。
