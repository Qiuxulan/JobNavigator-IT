# JobNavigator-IT

JobNavigator-IT 是一个面向 IT 职业决策的原型系统，围绕“简历技能抽取 → 岗位匹配 → 技能缺口 → 学习路径 → 行业趋势 → 报告生成”构建完整链路。项目当前重点覆盖 69 个细粒度 IT 岗位，并把职业图谱、GraphSAGE、PatchTST 趋势预测和证据检索整合到 FastAPI + React 原型中。

## 当前能力

- **技能抽取**：`ExtractorService` 默认尝试本地微调模型 `models/extractor_v1`，失败或空输出时使用规则抽取兜底，输出统一 `UserProfile`。
- **岗位推荐**：使用 `TechWolf/JobBERT-v3` 编码用户画像，并通过 PostgreSQL/pgvector 中的 `job_roles.embedding` 做 TopK 粗召回。
- **图谱精排**：基于 `fine_grained_roles_v1.json`、`skill_vocab.json`、`skill_prerequisite_v2.json` 和学习资源构建职业图谱，对候选岗位做技能覆盖、缺口成本、资源覆盖和 GraphSAGE 可达性评分。
- **学习路径**：对目标岗位前 30 个关键技能中的缺失技能做先修链搜索，合并共享先修，并挂载学习资源。
- **行业趋势**：整合 JD、GDELT GKG/事件冲击、GitHub/arXiv 技术热度，生成 `role_month_features` 和 PatchTST 预测结果。
- **趋势证据与报告**：趋势接口、证据检索、CoT 上下文和报告生成服务读取真实数据产物，不再依赖硬编码 mock。
- **前端原型**：提供趋势仪表盘、岗位详情、岗位对比、知识图谱、学习路径和 AI 助手页面。

## 目录结构

```text
app/                    FastAPI 接口、schema、业务服务
frontend/               React + TypeScript + Vite 前端
pipelines/extract/      技能抽取、弱监督数据、模型训练与评估
pipelines/taxonomy/     岗位库、技能词表、JobBERT 向量库构建
pipelines/graph/        职业图谱、GraphSAGE、路径样例和可视化
pipelines/trend/        JD/GDELT/技术热度、趋势评分、PatchTST 数据链路
infra/db/migrations/    PostgreSQL、pgvector 和业务表初始化 SQL
infra/docker/           API 与前端 Dockerfile
models/                 本地抽取模型、GraphSAGE、PatchTST 等模型产物
data/raw/               本地原始数据入口，通常不提交大文件
data/silver/            抽取和评估中间数据
data/gold/              当前主链路使用的标准数据和模型输入输出
reports/                实验报告、模块说明、行业数据处理说明
```

## 关键数据产物

- `data/gold/fine_grained_roles_v1.json`：69 个细粒度岗位主库。
- `data/gold/skill_vocab.json`：技能标准化词表，供抽取、图谱和路径统一映射。
- `data/gold/skill_prerequisite_v2.json`：技能先修、难度、学时估计。
- `data/gold/learning_resources_v1.json` / `data/gold/learning_resources_v2.json`：学习资源。
- `data/gold/role_taxonomy.json`：趋势侧岗位标准库。
- `data/gold/jd_role_month_features.json`：JD 月度特征。
- `data/gold/gdelt_gkg_role_month_features.json`：GDELT GKG 月度特征。
- `data/gold/gdelt_impact_role_month_features.json`：GDELT 事件冲击特征。
- `data/gold/tech_role_month_features.json`：GitHub/arXiv 技术热度岗位月特征。
- `data/gold/role_month_features.json`：行业趋势统一合并特征。
- `data/gold/patchtst_role_month_features.json`：PatchTST 输入面板。
- `data/gold/patchtst_predictions_36m.json`：36 个月趋势预测结果。

大体量原始数据，如 `data/GDELT/`、完整 JD 原始文件和部分证据索引，默认通过 `.gitignore` 排除。运行全量趋势链路前需要确认本地数据已经放在对应路径。

## 环境要求

- Python 3.11，推荐使用项目 conda 环境 `jobnavigator-it`。
- Node.js 18+ 与 npm。
- Docker Desktop，用于 PostgreSQL/pgvector、Redis 和可选的一键部署。
- 可选：本地已缓存 `TechWolf/JobBERT-v3`，否则首次构建岗位向量会尝试联网下载。
- 可选：LLM API Key，用于 AI 助手和报告生成；没有 Key 时部分报告能力不可用。

## 从零启动

### 1. 安装 Python 依赖

如果已经有 conda 环境：

```powershell
conda activate jobnavigator-it
pip install -r requirements.txt
```

如果需要新建环境，可按项目环境文件创建或手动创建 Python 3.11 环境后安装依赖：

```powershell
conda create -n jobnavigator-it python=3.11
conda activate jobnavigator-it
pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

常用配置：

```dotenv
JOBNAV_APP_ENV=dev
JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@localhost:5432/jobnavigator
JOBNAV_REDIS_URL=redis://localhost:6379/0
JOBNAV_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
JOBNAV_LLM_API_KEY=
JOBNAV_LLM_MODEL=qwen-plus
```

本地直接运行 Python 脚本时，数据库主机使用 `localhost`；在 Docker 容器内部运行时，数据库主机使用 compose 服务名 `postgres`。

### 3. 启动数据库和 Redis

仅启动基础设施：

```powershell
docker compose up -d postgres redis
```

初始化 SQL 位于 `infra/db/migrations/`，PostgreSQL 容器首次创建数据卷时会自动执行。若你复用旧 volume，表结构不会自动重跑，需要手动确认迁移状态或重建 volume。

### 4. 构建岗位向量库

粗召回依赖 `job_roles.embedding`，因此需要先写入岗位向量：

```powershell
python -m pipelines.taxonomy.build_job_vectors
```

也可以用 Docker 的一次性 seed profile：

```powershell
docker compose --profile seed up vector-seed
```

如果缺少 JobBERT 缓存、pgvector 或 `job_roles.embedding`，相关召回脚本会快速失败并提示缺项，不应长时间阻塞。

### 5. 启动后端

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

检查：

```text
http://127.0.0.1:8000/v1/health
http://127.0.0.1:8000/docs
```

### 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api/*` 代理到 `http://127.0.0.1:8000/*`。

### 7. Docker 一键运行

如果希望前后端和基础设施一起运行：

```powershell
docker compose --env-file .env up --build
```

服务地址：

| 服务 | 地址 |
|---|---|
| 前端 | `http://127.0.0.1` |
| 后端健康检查 | `http://127.0.0.1:8000/v1/health` |
| API 文档 | `http://127.0.0.1:8000/docs` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

停止：

```powershell
docker compose down
```

## 主要 API

| 接口 | 作用 |
|---|---|
| `GET /v1/health` | 健康检查 |
| `GET /v1/roles` / `GET /v1/roles/catalog` | 岗位列表与岗位目录 |
| `GET /v1/graph` | 职业图谱数据 |
| `POST /v1/profile/extract` | 简历/文本抽取为 `UserProfile` |
| `POST /v1/jobs/recommend` | 岗位推荐 |
| `POST /v1/careers/rank` | D 模块端到端：抽取、召回、图谱精排、学习路径 |
| `POST /v1/careers/report` | 基于职业匹配结果生成报告 |
| `POST /v1/paths/generate` | 学习路径生成 |
| `GET /v1/trends/batch` | 批量趋势结果 |
| `GET /v1/trends/{job_role}` | 单岗位趋势结果 |
| `GET /v1/evidence/{job_role}` | 趋势证据 |
| `GET /v1/cot/{job_role}` | 趋势解释上下文 |
| `POST /v1/chat/decision` | 决策问答 |
| `POST /v1/agent/chat` | Agent 聊天入口 |

## 常用离线流水线

职业部分：

```powershell
python -m pipelines.extract.diagnose_extractor_v1
python -m pipelines.taxonomy.build_skill_vocab
python -m pipelines.taxonomy.build_job_vectors
python -m pipelines.graph.build_career_graph_v2
python -m pipelines.graph.train_graphsage_v2
python -m pipelines.graph.run_sample_rankings_v2
```

行业趋势部分：

```powershell
python -m pipelines.trend.build_role_taxonomy
python -m pipelines.trend.collect_hf_recruitment_jobs
python -m pipelines.trend.collect_ai_job_dataset_jobs
python -m pipelines.trend.standardize_jd_roles
python -m pipelines.trend.build_jd_role_month_features
python -m pipelines.trend.process_gdelt_gkg_local
python -m pipelines.trend.collect_tech_heat
python -m pipelines.trend.build_role_month_features
python -m pipelines.trend.prepare_trend_model_dataset
python -m pipelines.trend.train_patchtst_predictor
python -m pipelines.trend.generate_patchtst_predictions
python -m pipelines.trend.build_trend_evidence
```

全量 JD、GDELT 和 arXiv/GitHub 采集会比较慢，建议先用 `.env` 中的 sample/limit 参数跑小样本，再切全量。

## 前端页面

| 页面 | 路径 | 说明 |
|---|---|---|
| 首页 | `/` | 项目入口 |
| 趋势仪表盘 | `/dashboard` | 69 岗位趋势、排名和分布 |
| 岗位详情 | `/role/:roleName` | PatchTST 预测、证据摘要和解释上下文 |
| 岗位对比 | `/compare` | 多岗位需求指数和趋势方向对比 |
| 知识图谱 | `/graph` | 岗位、技能、资源、趋势事件关系图 |
| 学习路径 | `/path` | 根据已有技能和目标岗位生成路径 |
| AI 助手 | `/chat` | 调用 Agent 查询趋势、岗位、技能缺口和学习建议 |

## 验证命令

后端接口契约：

```powershell
python -m pytest tests/integration/test_api_contract.py
```

前端构建：

```powershell
cd frontend
npm run build
```

Python 语法快速检查可按需运行，但在受限目录中可能因为无法写 `__pycache__` 报权限问题。遇到这种情况优先使用具体单测或设置可写缓存目录。

## 常见问题

### 粗召回不可用

检查三项：本地是否能加载 `TechWolf/JobBERT-v3`，PostgreSQL/pgvector 是否可用，`job_roles.embedding` 是否已有数据。缺任一项时需要先补模型缓存、启动数据库或重跑 `pipelines.taxonomy.build_job_vectors`。

### 本地脚本连接不上数据库

本地 PowerShell/conda 运行脚本时使用：

```dotenv
JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@localhost:5432/jobnavigator
```

Docker 容器内部运行时使用：

```dotenv
JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@postgres:5432/jobnavigator
```

### 抽取模型不可用

`ExtractorService` 会先尝试 `models/extractor_v1`，失败时规则抽取继续生效。若需要诊断模型加载、模型空输出和规则兜底情况，运行：

```powershell
python -m pipelines.extract.diagnose_extractor_v1
```

### 趋势或证据为空

确认 `data/gold/role_month_features.json`、`data/gold/patchtst_predictions_36m.json`、`data/gold/trend_evidence_v1.jsonl` 等文件存在。GDELT 原始压缩数据通常不提交，需要本地放在 `data/GDELT/` 后再运行处理脚本。

## 文档入口

- 总体分工：`03-overall-team-assignment-3-weeks.md`
- 行业部分分工：`reports/trend/02_队友任务分工.md`
- 行业数据处理：`reports/trend/01_行业数据处理说明.md`
- 行业数据修正：`reports/trend/04_行业数据处理修正说明.md`
- D 模块总结：`reports/module_d_implementation_summary.md`
- 抽取、岗位、图谱、趋势流水线说明：`pipelines/*/README.md`
