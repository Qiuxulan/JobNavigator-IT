# D 模块 README：全链路整合、前端系统与 Agent 接入

> 本文档面向答辩、交付和队友接入，说明 D 模块如何把岗位体系、趋势预测、证据检索、职业推荐、学习路径和知识图谱整合为可运行的 Web 系统，并通过 Agent API 提供自然语言职业决策入口。

---

## 1. 模块目标与边界

本模块解决的问题是：**前面各模块已经产生岗位、预测、证据、图谱和路径结果后，如何把它们组合成一个用户可以直接操作的完整产品。**

主要交付包括：

1. React + TypeScript 前端，覆盖趋势总览、岗位详情、岗位对比、知识图谱、学习路径和 AI 助手。
2. FastAPI 聚合接口，将前面模块的本地数据和服务统一暴露给前端。
3. Orchestrator 风格工具调用 Agent，根据用户问题选择趋势、证据、推荐、技能差距和路径工具。
4. 本地与 Docker 部署链路，支持 Vite 开发代理和 Nginx 生产代理。
5. 可降级运行：数据库、完整 evidence index 或 LLM Key 缺失时，尽量使用仓库内预计算数据和本地规则继续工作。

本模块不重新训练 PatchTST、JobBERT 或 GraphSAGE，也不重新构建上游证据索引；它负责运行时编排、接口适配、产品交互和降级策略。

---

## 2. 整体链路

```text
用户输入
  ├─ 浏览岗位趋势
  ├─ 选择目标岗位
  ├─ 输入已有技能/简历
  └─ 自然语言提问
        │
        ▼
React 前端
  Dashboard / Role Detail / Compare / Graph / Learning Path / Chat
        │  /api/v1/*
        ▼
FastAPI 聚合层
  roles / trends / evidence / graph / paths / careers / agent
        │
        ├─ PatchTST 24 个月预测结果
        ├─ EvidenceService + 预计算证据 fallback
        ├─ JobBERT + pgvector（可选）
        ├─ GraphPathPlannerV2 + 本地图谱
        ├─ 岗位-技能-事件图谱
        └─ LLM Agent / 本地规则 fallback
        │
        ▼
趋势判断 + 证据解释 + 岗位推荐 + 技能缺口 + 学习路径
```

用户闭环为：

```text
看趋势 → 查证据 → 比岗位 → 看技能关系 → 生成学习路径 → 向 Agent 追问
```

---

## 3. 当前交付数据

| 数据 | 当前规模 | 用途 |
|---|---:|---|
| 标准岗位体系 | 69 个岗位 | Dashboard、岗位详情、Agent 角色解析 |
| 标准技能图谱 | 275 个技能节点 | 技能差距与学习路径 |
| 24 个月趋势预测 | 1,656 行（69 × 24） | 趋势曲线和批量排名 |
| 趋势里程碑 | 69 个岗位 | 预测摘要 |
| V2 学习资源覆盖 | 231 个技能 | 路径资源补充 |
| V2 学习资源条目 | 267 条 | Coursera、Bilibili、GitHub 等资源链接 |
| 预计算趋势证据 | `trend_evidence_v1.jsonl` | 完整 evidence index 缺失时降级使用 |

这些规模来自当前仓库交付文件，不代表实时互联网统计。

---

## 4. 前端页面

### 4.1 项目入口 `/`

- 展示产品入口和核心能力。
- 跳转到趋势、图谱、路径和 Agent 页面。

### 4.2 趋势仪表盘 `/dashboard`

- 批量请求 69 个岗位的趋势信号。
- 展示岗位类别平均需求指数。
- 展示上升、平稳、下降方向分布。
- 支持按需求排序、按名称排序和关键词搜索。
- 点击岗位进入详情页。

### 4.3 岗位详情 `/role/:roleName`

- 展示未来 24 个月预测曲线。
- 展示需求指数和趋势判断。
- 展示新闻、JD、GitHub、论文等补充信号摘要。
- 展示证据检索概览和重大行业事件。
- 提供 CoT 证据链上下文入口。

### 4.4 角色对比 `/compare`

- 同时查询多个岗位。
- 按预测需求指数排序。
- 用图表和表格比较趋势方向、需求指数和置信度。

### 4.5 知识图谱 `/graph`

- 展示岗位、技能和行业事件节点。
- 展示 `REQUIRES`、`CORE_SKILL`、`PREREQ`、`AFFECTS` 关系。
- 支持岗位大类筛选和视图切换。

### 4.6 学习路径 `/path`

- 输入当前技能并选择目标岗位。
- 调用 GraphPathPlannerV2 生成技能补齐顺序。
- 展示步骤、预计时长、路径分数和学习资源。

### 4.7 AI 助手 `/chat`

- 支持趋势查询、岗位比较、简历/技能解析、职业推荐、技能缺口和学习路径问题。
- 使用 Markdown 展示表格、标题、列表和代码片段。
- Agent 请求单独设置较长超时，复杂结构化比较优先走本地受控工具链。

---

## 5. API 聚合层

| 方法 | 接口 | 作用 |
|---|---|---|
| GET | `/v1/health` | 后端健康检查 |
| GET | `/v1/roles` | 按类别返回岗位列表 |
| GET | `/v1/roles/catalog` | 返回前端路径规划需要的岗位目录 |
| GET | `/v1/trends/batch` | 批量返回 69 个岗位趋势 |
| GET | `/v1/trends/{job_role}` | 返回单岗位趋势和逐月预测 |
| GET | `/v1/evidence/{job_role}` | 返回新闻/JD/重大事件证据 |
| GET | `/v1/cot/{job_role}` | 返回带引用编号的 grounded context |
| GET | `/v1/graph` | 返回岗位-技能-事件图谱 |
| POST | `/v1/profile/extract` | 抽取用户技能画像 |
| POST | `/v1/jobs/recommend` | 返回岗位推荐结果 |
| POST | `/v1/careers/rank` | 返回职业排序、技能差距和路径 |
| POST | `/v1/paths/generate` | 生成目标岗位学习路径 |
| POST | `/v1/agent/chat` | Agent 多轮对话入口 |

趋势示例：

```bash
curl "http://127.0.0.1:8000/v1/trends/AI%20Engineer?horizon_months=24"
```

Agent 示例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"比较 AI Engineer 和 Backend Python Engineer 的趋势"}]}'
```

---

## 6. Agent 实现

### 6.1 实现方式

当前代码实现是一个 **Orchestrator 风格的工具调用 Agent**：一个对话入口根据模型返回的 `tool_calls` 调用项目工具，再把结构化结果交给模型总结。

它不是四个独立部署、独立通信的 Agent 服务。答辩中可以表述为“Agent 统一调度多个职业与趋势专家工具”。

### 6.2 工具清单

| 工具 | 数据来源/服务 | 作用 |
|---|---|---|
| `query_trend` | TrendService / PatchTST | 查询岗位趋势 |
| `retrieve_evidence` | EvidenceService | 检索趋势证据 |
| `get_evidence_backtrack` | trend_predictor | 查询历史特征和关键因素 |
| `compare_roles` | TrendService | 比较多个岗位 |
| `get_role_list` | role taxonomy | 返回岗位目录 |
| `analyze_resume` | ExtractorService | 抽取技能和目标岗位 |
| `recommend_jobs` | JobBERT/本地匹配 | 推荐岗位 |
| `get_skill_gap` | GraphPathPlannerV2/本地匹配 | 分析技能差距 |
| `plan_learning_path` | GraphPathPlannerV2 | 生成学习路径 |
| `get_cot_explanation` | trend_explanation | 生成受约束证据上下文 |

### 6.3 三层降级策略

职业推荐和路径模块按以下优先级运行：

```text
Tier 1：JobBERT + PostgreSQL/pgvector
Tier 2：GraphPathPlannerV2 + 本地 embeddings
Tier 3：本地岗位技能重合度 + 技能图谱
```

证据模块按以下方式运行：

```text
完整 evidence index 可用 → 在线分片检索
完整 evidence index 缺失 → 读取 trend_evidence_v1.jsonl
```

Agent 按以下方式运行：

```text
结构化多岗位决策问题 → 受控本地工具链快速回答
配置 LLM Key → OpenAI-compatible function calling
未配置 LLM Key → 本地关键词路由和格式化 fallback
```

### 6.4 受控回答边界

- 只使用项目岗位、趋势、证据、技能和路径数据。
- 无法匹配岗位时明确返回错误或最接近的已收录岗位。
- 趋势解释使用 `[E#]`、`[M#]`、`[J#]` 引用编号。
- 不输出隐藏思维链，只输出可审计的证据链摘要。

---

## 7. 前后端代理关系

本地开发：

```text
Browser /api/v1/*
  → Vite rewrite /api
  → http://127.0.0.1:8000/v1/*
```

Docker：

```text
Browser /api/v1/*
  → Nginx location /api/
  → api:8000/v1/*
```

前端 API 客户端统一使用 `/api/v1`，因此页面代码不需要区分本地和容器环境。

---

## 8. 部署

完整步骤见根目录：

```text
SETUP_GUIDE.md
```

本地开发：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm ci
npm run dev
```

Docker：

```bash
docker compose --env-file .env up --build
```

---

## 9. 关键文件与职责

### 后端

```text
app/main.py                         FastAPI 与本地前端 CORS
app/api/routes.py                   前端/Agent 聚合 API
app/services/agent.py               Agent 编排、工具调用、降级策略
app/services/trend.py               统一趋势响应和证据拼装
app/services/trend_predictor.py     24 个月预测读取与长周期输出
app/services/evidence.py            在线证据检索与预计算 fallback
app/services/trend_explanation.py   grounded 证据链上下文
app/services/career_catalog.py      岗位、技能、V1/V2 资源加载
app/services/role_i18n.py           岗位中文名映射
app/schemas/domain.py               前后端趋势响应契约
```

### 前端

```text
frontend/src/api.ts                 API 类型和请求封装
frontend/src/App.tsx                页面路由
frontend/src/pages/Dashboard.tsx    趋势总览
frontend/src/pages/RoleDetail.tsx   岗位详情与证据
frontend/src/pages/Compare.tsx      岗位比较
frontend/src/pages/Graph.tsx        图谱可视化
frontend/src/pages/LearningPath.tsx 学习路径
frontend/src/pages/Chat.tsx         Agent 对话
frontend/nginx.conf                 容器 API 反向代理和 SPA fallback
```

### 数据与部署

```text
data/gold/patchtst_predictions_24m.json
data/gold/patchtst_prediction_milestones_24m.json
data/gold/learning_resources_v2.json
infra/docker/Dockerfile.api
infra/docker/Dockerfile.frontend
infra/docker/docker-compose.yml
.env.example
SETUP_GUIDE.md
```

---

## 10. 验证方式

前端构建：

```bash
cd frontend
npm run build
```

后端语法：

```bash
python -m py_compile app/main.py app/api/routes.py app/services/agent.py app/services/trend.py
```

接口测试：

```bash
python -m pytest tests/integration/test_api_contract.py
```

人工验收建议：

1. `/v1/health` 返回 `ok`。
2. Dashboard 能加载 69 个岗位。
3. AI Engineer 详情页能加载 24 个预测点。
4. 图谱能加载岗位、技能和事件关系。
5. 学习路径能返回步骤和资源。
6. Agent 在无 Key 时能 fallback，在有 Key 时能执行 tool calling。

---

## 11. 已知限制

1. PatchTST 输出是项目模型预测，不是实时招聘平台统计。
2. 完整 GDELT/JD evidence index 体量较大，仓库部署默认依赖预计算证据降级。
3. JobBERT 语义召回需要本地模型缓存、PostgreSQL/pgvector 和岗位向量；缺失时会降级。
4. 外部 LLM 响应时间受网络和供应商服务影响，开放问题可能较慢。
5. 证据中的新闻与 JD 用于趋势解释，不应表述为严格因果关系。
6. 当前 Agent 是单 Orchestrator + 多工具架构，不是分布式多 Agent 系统。

---

## 12. 答辩说明口径

可以这样概括：

> D 模块将 69 个岗位的趋势预测、证据检索、职业推荐、知识图谱和学习路径统一接入 FastAPI，再通过 React 前端和工具调用 Agent 提供完整职业决策流程。用户可以从趋势总览进入岗位详情，查看证据与技能关系，生成学习路径，并继续通过 Agent 比较岗位和追问原因。系统对数据库、证据索引和外部 LLM 都设计了本地降级路径，因此不仅能展示，也具备可移植运行能力。

一句话总结：

```text
本模块完成了“模型结果 → 后端服务 → 前端交互 → Agent 决策”的产品化闭环。
```
