# JobNavigator-IT

**快速启动见 `SETUP_GUIDE.md`；完整环境说明见 `docs/04-deployment-ops/03-setup-on-new-machine.md`。**

**分工在docs\01-product-roadmap\03-overall-team-assignment-3-weeks.md！！**

面向 IT 细粒度岗位的职业决策系统（V1）。本项目以 `JobNavigator-IT_26双创立项_文字提取.txt` 作为需求基线，重点解决“岗位推荐-能力缺口-学习路径-趋势判断”的闭环问题。

## 1. 项目目标与边界

### 1.1 目标

构建一个可部署的职业决策系统，支持：

1. 用户画像抽取（简历/GitHub 文本）
2. 细粒度岗位推荐（TopK + 可解释打分）
3. 技能缺口识别与学习路径生成
4. 行业趋势分析与证据提示

### 1.2 当前边界

1. 领域：仅 IT 岗位
2. 语言：中文优先，中英混合可支持
3. Agent：已实现 Orchestrator 风格工具调用 Agent；外部 LLM、数据库或完整证据索引缺失时支持本地降级

## 2. 总体架构

系统采用“单机服务化”部署，便于比赛阶段快速落地并保留后续扩展能力。

1. `api-service`（FastAPI）
   : 提供统一 REST API，对接前端/调用方
2. `frontend`（React + TypeScript + ECharts）
   : 提供趋势、岗位对比、图谱、学习路径和 Agent 交互页面
3. `data-service`（PostgreSQL + pgvector，可选）
   : 管理结构化数据、关系边、向量索引
4. `model-service`（脚本层）
   : 承担抽取模型训练与推理封装

## 3. 项目目录结构（当前实现）

```text
app/
  api/                  # 路由与接口层
  core/                 # 配置管理
  schemas/              # 领域模型与请求响应模型
  services/             # 业务服务（抽取/推荐/路径/趋势）
frontend/               # React + TypeScript 前端
services/
  worker/               # Celery worker
  model/                # 本地模型脚本占位（训练/推理）
pipelines/
  extract/              # 弱监督与标注流水线说明
  taxonomy/             # 细粒度岗位体系构建说明
  graph/                # 图谱构建流程说明
  trend/                # 趋势建模流程说明
infra/
  docker/               # Dockerfile 与 compose
  db/
    migrations/         # 初始化 SQL（含 pgvector）
    seed/               # 种子数据
data/
  raw/ silver/ gold/ metadata/
tests/
  unit/ integration/
docs/
  01-product-roadmap/
  02-system-data/
  03-api-testing/
  04-deployment-ops/
```

## 4. 核心模块划分与技术栈

### 4.1 数据层（Data Pipeline）

目标：把多源异构数据变成可训练、可检索、可追溯的数据资产。

1. 数据来源
   : 招聘 JD、公开技能体系（ESCO/O*NET）、学习资源、趋势事件
2. 分层
   : `raw -> silver -> gold`
3. 关键约束
   : 每条记录必须保留来源、时间、许可、采集方式

技术：

- Python ETL
- PostgreSQL

### 4.2 抽取层（Extraction）

你提出的关键问题是“结构化字段与非结构化文本如何统一抽取”。当前方案：

1. 结构化来源（JD 页面字段）
   : 直接字段抽取 + 标准化映射
2. 非结构化来源（简历/GitHub 文本）
   : 先规则+弱监督，后 LoRA/QLoRA 微调
3. 目标标签
   : 技能、岗位、学历、年限、薪资、城市、项目证据

技术：

- 正则与模板规则
- 弱监督标注
- 本地微调（阶段二）

### 4.3 岗位体系层（粗细粒度）

你关注“细粒度岗位怎么构建”。本项目采用：

1. 粗粒度锚点
   : 直接使用 ESCO/O*NET 职业类目
2. 细粒度岗位树
   : 岗位文本向量化 -> 聚类 -> 专家规则合并 -> LLM 命名

这能兼顾标准兼容性与岗位时效性。

### 4.4 图谱层（Graph）

你提出“岗位涉及技能是全挂载还是筛选挂载”。本项目采用加权挂载，不是出现即挂载：

1. 节点
   : `JobRole / Skill / Resource / TrendEvent`
2. 关系
   : `REQUIRES / PREREQ / TEACHES / AFFECTS`
3. 关系属性
   : `weight / confidence / source_time`

只有分数高于阈值的关系才入图。

### 4.5 推荐层（Two-Stage Matching）

你担心“全量相似度计算算力爆炸”。本项目采用双阶段：

1. 召回阶段
   : pgvector ANN 从岗位向量中检索 TopN
2. 精排阶段
   : 融合语义相似、硬约束（学历/薪资/城市）、路径代价、趋势奖励

输出：

- TopK 细粒度岗位
- 技能重合/缺口
- 分数分解与解释

### 4.6 学习路径层（Path Planning）

你关注“路径顺序如何得到”。本项目采用：

1. 缺口识别
   : `gap = target_skills - user_skills`
2. 子图排序
   : 在 `PREREQ` 子图中进行 DAG/近似 DAG 排序
3. 多候选路径打分
   : `Score = Gain - Cost - Difficulty + MarketReward`
4. 资源挂载
   : 每步技能挂载 TopK 学习资源

### 4.7 趋势层（Trend）

以 PatchTST 逐月预测为主，并提供基线降级：

1. 主模型
   : PatchTST 24 个月岗位需求预测
2. 输入
   : 岗位时序、技能热度、事件证据
3. 输出
   : 逐月需求指数、趋势方向、证据摘要和解释上下文

## 5. API 冻结范围（V1）

1. `GET /v1/roles`、`GET /v1/roles/catalog`
2. `POST /v1/profile/extract`
3. `POST /v1/jobs/recommend`、`POST /v1/careers/rank`
4. `POST /v1/paths/generate`
5. `GET /v1/trends/batch`、`GET /v1/trends/{job_role}`
6. `GET /v1/evidence/{job_role}`、`GET /v1/cot/{job_role}`
7. `GET /v1/graph`
8. `POST /v1/chat/decision`、`POST /v1/agent/chat`

## 6. 测试与验收

### 6.1 当前已接入

1. 单测：服务层基础逻辑
2. 集成测：核心接口契约

### 6.2 目标指标（阶段二）

1. 抽取：实体 F1、归一化准确率、OOV 技能召回
2. 推荐：TopK 命中率、NDCG@5、约束违规率
3. 路径：先修冲突率、路径可执行性
4. 趋势：方向准确率、证据覆盖率

## 7. 环境安装与运行

前后端本地启动、Docker Compose、Agent 环境变量和常见问题见：

- `SETUP_GUIDE.md`
- `docs/04-deployment-ops/03-setup-on-new-machine.md`

## 8. 文档导航

1. 产品与路线：`docs/01-product-roadmap/`
2. 系统与数据：`docs/02-system-data/`
3. 接口与测试：`docs/03-api-testing/`
4. 部署与运维：`docs/04-deployment-ops/`
5. D 模块全链路与 Agent：`reports/04_full_chain_agent_integration.md`

## 9. A 模块：英文简历 / JD 技能抽取

A 模块已合并到项目根目录，不再使用独立的 `A_module_extract/` 文件夹。

- 抽取与训练脚本：`pipelines/extract/`
- 训练与评测数据：`data/silver/`
- 下游结构化输出：`data/processed/`
- 本地技能抽取模型：`models/extractor_v1/`
- 评测报告：`reports/extractor_eval_v1.md`

最终模型基于 `jjzha/jobbert_skill_extraction`，使用 1000 条 SkillSpan 人工 BIO 标注和 989 条 JD 弱标注继续训练。模型权重通过 Git LFS 管理。
