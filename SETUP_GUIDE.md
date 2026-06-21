# JobNavigator-IT 本地部署与使用指南

## 1. 环境要求

- Python 3.11（推荐，模型依赖兼容性更稳定）
- Node.js 18+
- npm 9+
- 可选：Docker Desktop
- 可选：PostgreSQL + pgvector、Redis

项目的趋势、图谱、学习路径和本地 Agent fallback 可以直接读取仓库数据运行。JobBERT 数据库召回需要 PostgreSQL、pgvector、岗位向量和本地模型缓存。

## 2. 本地开发方式

### 2.1 安装依赖

在项目根目录执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

### 2.2 配置 Agent

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

使用阿里云百炼兼容接口时，配置：

```dotenv
JOBNAV_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
JOBNAV_LLM_API_KEY=your_api_key
JOBNAV_LLM_MODEL=qwen-plus
JOBNAV_LLM_TIMEOUT_SEC=60
```

不要提交 `.env`。未配置 API Key 时，`/v1/agent/chat` 会使用项目本地数据和规则 fallback；外部 LLM 总结不可用，但趋势、图谱、路径和基础问答仍可运行。

### 2.3 启动后端

终端 1，在项目根目录执行：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/v1/health
```

FastAPI 文档：

```text
http://127.0.0.1:8000/docs
```

### 2.4 启动前端

终端 2：

```bash
cd frontend
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

Vite 会将浏览器请求的 `/api/*` 重写并代理到 `http://127.0.0.1:8000/*`。

## 3. Docker Compose 部署

先在项目根目录设置环境变量，或使用 `--env-file .env`：

```bash
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

生产前端通过 Nginx 将 `/api/*` 转发给 `api:8000/*`，并为 React Router 提供 SPA fallback。

停止服务：

```bash
docker compose down
```

## 4. 页面与使用方法

| 页面 | 路径 | 用法 |
|---|---|---|
| 项目入口 | `/` | 进入各功能模块 |
| 趋势仪表盘 | `/dashboard` | 浏览 69 个岗位、需求排序和方向分布 |
| 岗位详情 | `/role/:roleName` | 查看未来 24 个月趋势、证据摘要和解释上下文 |
| 角色对比 | `/compare` | 横向比较多个岗位需求指数与方向 |
| 知识图谱 | `/graph` | 浏览岗位、技能、行业事件关系 |
| 学习路径 | `/path` | 输入已有技能并选择目标岗位，生成步骤与资源 |
| AI 助手 | `/chat` | 查询趋势、岗位比较、技能缺口和学习路径 |

推荐 Agent 测试问题：

```text
我会 Python、SQL、Docker 和 LangChain，请比较 AI Engineer 和 Backend Python Engineer 的 24 个月趋势、技能差距和学习成本，并给出推荐。
```

该类结构化对比会优先走项目内受控工具链，避免不必要的外部 LLM 多轮等待。

## 5. 运行依赖数据

前端核心接口依赖以下仓库文件：

```text
data/gold/role_taxonomy.json
data/gold/fine_grained_roles_v1.json
data/gold/skill_prerequisite_v2.json
data/gold/learning_resources_v1.json
data/gold/learning_resources_v2.json
data/gold/major_industry_events_v1.json
data/gold/trend_evidence_v1.jsonl
data/gold/patchtst_predictions_24m.json
data/gold/patchtst_prediction_milestones_24m.json
```

完整 GDELT/JD evidence index 未随仓库发布时，后端会自动降级读取 `trend_evidence_v1.jsonl`。

## 6. 验证命令

```bash
cd frontend
npm run build
```

```bash
python -m pytest tests/integration/test_api_contract.py
```

```bash
python -m py_compile app/api/routes.py app/main.py app/services/agent.py app/services/trend.py
```

## 7. 常见问题

### 后端启动时报 `ModuleNotFoundError`

确认在项目根目录运行，并且虚拟环境已激活、`requirements.txt` 已安装。

### 前端显示 API 请求失败

本地开发时确认 8000 和 5173 端口均已启动。Docker 模式确认 8000 和 80 端口可访问。

### Agent 外部模型超时

先用单岗位趋势或双岗位对比问题测试。复杂开放问题可能触发多轮工具调用；受控岗位比较会优先使用本地工具链生成结果。

### JobBERT 召回不可用

语义召回依赖本地 JobBERT 模型缓存、PostgreSQL/pgvector 和已写入的岗位向量。缺失时 Agent 会降级使用本地岗位技能匹配和 GraphPathPlannerV2。

### 证据列表为空

确认 `data/gold/trend_evidence_v1.jsonl` 存在。完整 evidence index 不在仓库时，系统会使用预计算证据降级，不会扫描原始 2.6GB GDELT 数据。
