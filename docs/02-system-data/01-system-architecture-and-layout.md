# 系统架构与目录（工程视角）

## 1. 运行架构

### api-service（FastAPI）

职责：

1. 提供统一 REST 接口
2. 参数校验与响应序列化
3. 聚合服务层输出

### worker-service（Celery）

职责：

1. 异步任务调度（数据处理、训练、批处理）
2. 长任务与重试机制

### data-service（PostgreSQL + pgvector）

职责：

1. 结构化存储（岗位、技能、关系、用户画像）
2. 向量索引（岗位召回）

### redis

职责：

1. Celery broker/result backend
2. 轻量缓存

## 2. 模块边界

`app/services` 中按业务能力拆分：

1. `extractor.py`
2. `recommender.py`
3. `path_planner.py`
4. `trend.py`

接口层只调用服务层，不直接拼业务逻辑。

## 3. 当前数据库结构（V1）

已初始化表：

1. `job_roles`
2. `skills`
3. `user_profiles`
4. `learning_resources`
5. `trend_events`
6. `graph_edges`

其中 `job_roles.embedding` 使用 pgvector，支持 ANN 召回。

## 4. 目录分层原则

1. `app/`：在线推理与 API
2. `services/`：后台任务与模型脚本
3. `pipelines/`：离线流程说明与后续脚本
4. `infra/`：部署与数据库初始化

