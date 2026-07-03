# 推荐模型评估报告 v1

## 1. 模块目标

本报告对应项目职业部分的 B 模块：细粒度岗位库 + 推荐模型。

模块目标是构建可用于职业推荐的细粒度岗位体系，并实现双阶段推荐流程：

1. 基于 JD 文本构建细粒度岗位库。
2. 为每个岗位簇生成岗位技能画像。
3. 根据用户画像召回候选岗位。
4. 对候选岗位进行多维精排。
5. 输出可解释推荐结果，包括匹配分数、重合技能、缺口技能和推荐理由。

当前版本定位为可运行 baseline，用于打通职业推荐主链路，并为 C 模块学习路径生成提供 `missing_skills` 输入。

## 2. 数据来源

当前使用的数据包括：

1. asaniczka JD 数据集
   - `data/raw/asaniczka/job_postings.csv`
   - `data/raw/asaniczka/job_summary.csv`
   - `data/raw/asaniczka/job_skills.csv`
   - 主要提供岗位标题、岗位描述和结构化技能字段。

2. Djinni JD 数据集
   - `data/raw/djinni/djinni_jd.csv`
   - 主要提供岗位标题、长文本 JD 和岗位方向关键词。

3. O\*NET Technology Skills
   - `data/raw/onet/Technology skills.txt`
   - 用于构建标准技术技能词表，辅助后续技能标准化。

当前已生成的数据产物：

1. `data/gold/fine_grained_roles_v1.json`
2. `data/gold/job_skill_profile_v1.json`
3. `data/gold/skill_vocab_onet.json`
4. `data/gold/djinni_skill_match_v1.json`

## 3. 岗位库构建方法

岗位库构建脚本为：

```bash
python pipelines/taxonomy/cluster_roles.py
```

主要流程如下：

1. 读取 asaniczka 与 Djinni 两个数据源。
2. 将不同来源的字段统一为 `title`、`text`、`skills_raw`、`keyword`、`source`。
3. 过滤明显非 IT 岗位噪声，例如医疗、销售、市场、施工等方向。
4. 从合并数据中抽样 6000 条 JD。
5. 使用 `TechWolf/JobBERT-v3` 对岗位文本进行向量化。
6. 使用 KMeans 聚类，当前设置为 40 个细粒度岗位簇。
7. 根据簇内高频岗位标题和关键词生成岗位名称。
8. 统计每个簇的 Top 技能，形成岗位技能画像。

输出格式示例：

```json
{
  "role_id": "role_12",
  "role_name": "Data Engineer",
  "size": 167,
  "source_mix": {
    "djinni": 112,
    "asaniczka": 55
  },
  "example_titles": ["Senior Data Engineer", "Data Engineer"],
  "keywords": ["data", "development", "engineering"],
  "required_skills": ["Python", "SQL", "Java", "Spark", "Hadoop"]
}
```

## 4. 推荐模型方法

推荐模型采用双阶段结构：

### 4.1 阶段一：向量召回

脚本：

```bash
python pipelines/taxonomy/recall.py
```

召回逻辑：

1. 将岗位名称和岗位技能拼接为岗位文本。
2. 将用户目标岗位和用户已有技能拼接为用户文本。
3. 使用 `TechWolf/JobBERT-v3` 分别编码岗位文本和用户文本。
4. 使用余弦相似度召回 TopN 候选岗位。

该阶段主要保证候选岗位与用户目标方向在语义上相关。

### 4.2 阶段二：多维精排

脚本：

```bash
python pipelines/taxonomy/rank.py
```

服务实现：

```text
app/services/recommender.py
```

当前精排公式为：

```text
FinalScore = α * semantic_score
           + β * constraint_score
           - γ * skill_gap_count
           + δ * trend_reward_score
```

当前参数：

```text
α = 0.50
β = 0.20
γ = 0.04
δ = 0.15
```

各项含义：

1. `semantic_score`：用户画像与岗位画像的语义相似度。
2. `constraint_score`：城市、薪资、学历等硬约束匹配分。当前岗位库暂未包含完整字段，因此使用 0.8 作为中性占位。
3. `skill_gap_count`：岗位所需技能中用户尚未掌握的技能数量。
4. `trend_reward_score`：岗位趋势奖励。当前使用关键词表占位，后续应接入行业趋势模块。

推荐结果输出包括：

1. `final_score`
2. `semantic_score`
3. `constraint_score`
4. `path_cost_score`
5. `trend_reward_score`
6. `skill_gap.missing_skills`
7. `skill_gap.overlap_skills`
8. `explanation`

其中 `missing_skills` 是 C 模块生成学习路径的关键输入。

## 5. 评估方法

当前项目尚无真实的“用户画像 -> 标准推荐岗位”标注集，因此本版本采用半人工评估。

评估脚本：

```bash
python pipelines/taxonomy/evaluate.py
```

评估集构造方式：

1. 人工构造若干典型用户画像。
2. 为每个用户画像设置期望命中的岗位关键词。
3. 调用推荐服务输出 TopK 推荐结果。
4. 判断 TopK 中是否出现符合预期关键词的岗位。

当前评估用户包括：

1. 机器学习方向求职者
   - 技能：Python、SQL、Machine Learning
   - 目标：Machine Learning Engineer

2. 数据分析方向求职者
   - 技能：SQL、Excel、Tableau、Power BI
   - 目标：Data Analyst

3. 数据工程方向求职者
   - 技能：Python、SQL、Spark、Hadoop
   - 目标：Data Engineer

4. 深度学习 / AI 方向求职者
   - 技能：Python、PyTorch、Deep Learning
   - 目标：AI Engineer

使用指标：

1. Hit@5
   - 判断 Top5 推荐中是否出现期望方向岗位。

2. NDCG@5
   - 在命中基础上考虑排序位置，命中越靠前分数越高。

3. GAMMA 敏感性分析
   - 扫描不同技能缺口惩罚权重，观察排序质量变化。

## 6. 当前产出观察

从当前 `fine_grained_roles_v1.json` 和 `job_skill_profile_v1.json` 看，系统已经能形成一批较合理的 IT 岗位簇，例如：

1. `Data Engineer`
   - 代表技能：Python、SQL、Java、Spark、Scala、Hadoop、Snowflake、AWS、ETL

2. `Data Analyst`
   - 代表技能：SQL、Python、Data Analysis、Tableau、Data Visualization、Power BI、Statistics

3. `Data Scientist`
   - 代表技能：Machine Learning、Python、Data Science、SQL、PyTorch、TensorFlow、Statistics

4. `DevOps Engineer`
   - 代表技能：Ansible、Terraform、CloudFormation、Python、PowerShell、Shell Scripting

5. `Frontend Developer`
   - 代表技能：JavaScript、Node.js、Design、QA Automation 等

推荐服务已经能够输出面向用户的解释文本，例如：

```text
某岗位与你的技能重合 N 项，缺口 M 项；语义匹配 x.xx，趋势热度 y.y。
```

这说明当前版本已经满足“可解释推荐结果”的基本要求。

## 7. 当前问题与限制

当前版本仍存在以下限制：

1. Djinni 技能画像仍不完整
   - 部分岗位技能来自 Djinni 的方向关键词，表现为 `Python(方向)`、`JavaScript(方向)` 等。
   - 这些字段更接近岗位方向标签，不是严格意义上的技能要求。
   - 后续应将 `match_djinni_skills.py` 扩展为全量匹配，并接入聚类脚本。

2. 部分岗位簇仍有噪声
   - 当前岗位库中仍出现 Copywriter、HR Manager、Media Buyer、MLB Gameday Compliance Monitor 等非核心 IT 岗位。
   - 后续需要继续扩展 `NOISE_TITLE` 或增加基于技能密度的过滤规则。

3. 部分簇命名不够稳定
   - 目前簇名主要来自簇内最高频岗位标题。
   - 当簇内混入多类岗位时，可能出现岗位名与技能画像不完全一致的问题。
   - 后续可结合高频标题、关键词和技能共同命名。

4. 约束匹配暂为占位
   - 当前岗位库缺少城市、薪资、学历等结构化字段。
   - `constraint_score` 暂固定为 0.8。
   - 后续需要补齐岗位字段后计算真实匹配分。

5. 趋势奖励暂为占位
   - 当前使用关键词表估计岗位趋势热度。
   - 后续应接入行业趋势模块输出的真实趋势信号。

6. 路径成本暂为近似
   - 当前 `path_cost_score` 使用技能缺口数量近似。
   - 后续应由 C 模块学习路径结果提供真实学习成本。

7. 依赖尚需补充
   - 当前新增脚本依赖 `pandas`、`numpy`、`scikit-learn`、`sentence-transformers`、`transformers`。
   - 这些依赖应补充到 `requirements.txt` 和 `environment.yml`，保证新环境可复现。

## 8. 下一步改进计划

优先级建议如下：

1. 全量处理 Djinni 技能
   - 将 `match_djinni_skills.py` 从预览版改为全量输出。
   - 将匹配出的技能并入 `cluster_roles.py`。
   - 去除 `xxx(方向)` 占位技能。

2. 清洗岗位簇
   - 扩展非 IT 岗位过滤词。
   - 删除或合并低质量簇。
   - 对重复岗位簇进行人工合并。

3. 补充依赖文件
   - 更新 `requirements.txt`。
   - 更新 `environment.yml`。

4. 校准精排权重
   - 使用 `evaluate.py` 跑 Hit@5 和 NDCG@5。
   - 根据评估结果选择更合适的 `GAMMA`。

5. 接入真实约束字段
   - 从 JD 中补充城市、薪资、学历要求。
   - 替换当前固定的 `constraint_score = 0.8`。

6. 与 C/D 模块联调
   - 将 `missing_skills` 输入 C 模块生成学习路径。
   - 将路径成本和行业趋势信号回传到最终推荐排序。

## 9. 结论

当前 B 模块已经完成可运行的第一版职业推荐链路：

1. 已构建细粒度岗位库。
2. 已生成岗位技能画像。
3. 已实现向量召回。
4. 已实现多维精排。
5. 已输出可解释推荐结果和技能缺口。
6. 已提供半人工评估脚本。

当前版本可以作为职业推荐 baseline 支撑后续联调。后续重点应放在数据质量提升，尤其是 Djinni 技能抽取、岗位簇清洗和评估指标补全。
