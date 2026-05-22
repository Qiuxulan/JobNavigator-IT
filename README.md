# JobNavigator-IT

**环境在docs\04-deployment-ops\03-setup-on-new-machine.md！！**

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
3. Agent：当前阶段不实现，`/v1/chat/decision` 仅预留（501）

## 2. 总体架构

系统采用“单机服务化”部署，便于比赛阶段快速落地并保留后续扩展能力。

1. `api-service`（FastAPI）
   : 提供统一 REST API，对接前端/调用方
2. `worker-service`（Celery + Redis）
   : 承担异步任务（数据处理、训练、批量计算）
3. `data-service`（PostgreSQL + pgvector）
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

先用稳定基线确保可落地，再保留升级位：

1. 基线
   : ARIMA/线性方案
2. 输入
   : 岗位时序、技能热度、事件证据
3. 输出
   : 短期/长期趋势方向 + 证据摘要

## 5. API 冻结范围（V1）

1. `POST /v1/profile/extract`
2. `POST /v1/jobs/recommend`
3. `POST /v1/paths/generate`
4. `GET /v1/trends/{job_role}`
5. `POST /v1/chat/decision`（预留）

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

环境安装、Conda 启动、Docker 启动、常见问题等统一放在：

- `docs/04-deployment-ops/03-setup-on-new-machine.md`

## 8. 文档导航

1. 产品与路线：`docs/01-product-roadmap/`
2. 系统与数据：`docs/02-system-data/`
3. 接口与测试：`docs/03-api-testing/`
4. 部署与运维：`docs/04-deployment-ops/`
