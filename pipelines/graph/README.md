# 职业图谱与学习路径流水线

`pipelines/graph` 是 D 模块离线构建入口，负责把岗位、技能、先修关系和学习资源组织成职业图谱，并训练 GraphSAGE 结构表示。线上路径生成由 `app.services.graph_path_planner_v2` 和 `PathPlannerService` 调用这些产物。

## 当前图谱定义

节点类型：

- `job`：来自 `data/gold/fine_grained_roles_v1.json`。
- `skill`：来自 `data/gold/skill_vocab.json`。
- `resource`：来自 `data/gold/learning_resources_v1.json` 和 `learning_resources_v2.json`。

边类型：

- `JOB_REQUIRES(job -> skill)`：岗位需要技能，权重为 `importance_score`。
- `SKILL_PREREQ(skill -> skill)`：技能先修关系，权重为先修成本。
- `SKILL_HAS_RESOURCE(skill -> resource)`：技能对应学习资源，权重为资源质量。

每个岗位只取 `skill_freq` 最高的前 30 个技能入图。趋势事件不参与 D 模块路径评分，只在行业趋势和证据图谱中使用。

## 主要脚本

| 脚本 | 作用 |
|---|---|
| `build_career_graph_v2.py` | 构建岗位-技能-资源图并写入数据库/审计报告 |
| `train_graphsage_v2.py` | 训练 GraphSAGE，导出模型、节点索引和 embedding |
| `run_sample_rankings_v2.py` | 样例验证：Top10 粗召回、图谱精排、学习路径 |
| `export_graph_interactive_v2.py` | 导出可交互职业图谱 HTML |
| `build_resources_json.py` | 从资源 CSV 构建学习资源 JSON |
| `rebuild_skill_graph.py` | 旧技能图重建辅助脚本，非当前主入口 |

## 主要产物

- `models/graphsage_v2/model.pt`
- `models/graphsage_v2/node_index.json`
- `models/graphsage_v2/embeddings.npy`
- `reports/graphsage_metrics_v2.json`
- `reports/full_career_graph_v2.html`
- `reports/module_d_implementation_summary.md`

## 路径搜索口径

路径搜索对象是目标岗位前 30 个关键技能中用户缺失的技能集合，而不是岗位节点本身。搜索会沿 `SKILL_PREREQ` 展开，限制深度，合并共享先修，并优先挂载已有学习资源。GraphSAGE embedding 只用于结构可达性奖励和启发式距离，不替代显式评分规则。
