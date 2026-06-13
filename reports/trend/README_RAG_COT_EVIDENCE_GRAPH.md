# C 模块 README：RAG 证据检索、CoT 解释上下文与事件图谱

> 负责人：组员 2（行业趋势解释 / RAG 证据链）。
> 本文档面向答辩、交付和队友接入，详细说明本模块做了什么、用了哪些数据、写了哪些文件、实现逻辑是什么、有哪些约束、如何调用接口、如何使用 CoT 和图谱。

---

## 1. 模块目标

本模块解决的问题是：**趋势预测给出“某岗位未来上升/下降/持平”后，系统如何给出可追溯、可解释、可展示的证据链**。

上游 B 模块（PatchTST）负责预测方向和需求指数。本模块不重新训练预测模型，而是在预测结果上增加三类能力：

1. **RAG 证据检索**
   - 从 GDELT 新闻事件索引和 JD 岗位数据中，为某个岗位、某个时间窗口检索证据。
   - 输出聚合信号、代表性事件、JD 存在性证据。

2. **CoT 解释上下文**
   - 将预测结果、聚合信号、TopK 事件、重大行业事件、JD 证据组装为带引用编号的推理上下文。
   - 本模块只生成 grounded prompt/context，不直接调用 LLM。
   - 组员 3 的 Agent 或前端可把该 prompt 交给 LLM 做“分步骤解释”。

3. **事件入图与可视化**
   - 将代表性事件作为 `event` 节点接入职业图谱。
   - 用 `AFFECTS(event -> job)` 边表示事件与岗位趋势之间的关系。
   - 输出可双击打开的 HTML 图谱。

---

## 2. 总体数据流

```text
原始数据
  ├─ data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl
  │    GDELT 岗位级事件候选，约 2.6GB
  ├─ data/raw/processed_jd_jobs.json
  │    标准化 JD，约 170MB
  ├─ data/gold/patchtst_prediction_milestones.json
  │    PatchTST 里程碑预测，69 角色 × 5 个视野 = 345 条
  ├─ data/gold/patchtst_predictions_36m.json
  │    PatchTST 逐月预测，69 角色 × 36 月 = 2484 条
  ├─ data/gold/role_taxonomy.json
  │    role_id / canonical_role / category / aliases / top_skills
  └─ data/gold/major_industry_events_v1.json
       人工整理的重大行业事件目录，101 条

        │
        ▼

① 离线索引
  pipelines/trend/build_evidence_index.py
  -> data/processed/evidence_index/events/<role>/<month>.jsonl
  -> data/processed/evidence_index/jobs/<role>.jsonl
  -> data/processed/evidence_index/manifest.json

        │
        ▼

② 在线/批量 RAG 检索核心
  app/services/evidence.py
  EvidenceService.retrieve_evidence(role, months, top_k, direction)
  -> aggregate + events + jobs + note

        │
        ├─ GET /v1/evidence/{job_role}
        ├─ GET /v1/trends/{job_role}  自动带 evidence
        ├─ pipelines/trend/build_trend_evidence.py
        │    -> data/gold/trend_evidence_v1.jsonl
        │    -> data/gold/trend_evidence_monthly_v1.jsonl
        │    -> reports/trend_explanation_eval_v1.md
        ├─ app/services/trend_explanation.py
        │    -> CoT 上下文 / grounded prompt
        └─ pipelines/graph/build_event_graph.py
             -> data/processed/event_graph_v1.json
             -> reports/full_unified_graph.html
```

---

## 3. 输入数据

### 3.1 GDELT 事件候选

文件：

```text
data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl
```

特点：

- 体量约 2.6GB。
- 全量索引后共有 **1,726,284 条事件候选**。
- 覆盖 **67 个有事件候选的角色**。
- 当前真实新闻窗口为 **2026-01 到 2026-06**。
- 原始 GDELT 数据没有完整正文，因此检索必须依赖 URL slug、source_domain、themes、tone、matched_terms 等字段。

索引保留字段：

```text
canonical_role
month
url
source_domain
themes
bucket_name
match_weight
matched_terms
matched_term_count
avg_tone
event_date
```

其中 `tone` 是 GDELT 的逗号分隔字段，代码中取第一个值作为综合情绪：

```python
parse_first_tone(tone)
```

### 3.2 JD 岗位数据

文件：

```text
data/raw/processed_jd_jobs.json
```

索引后共有 **70,826 条 JD**，覆盖 **62 个角色**。

索引保留字段：

```text
canonical_role
role_id
month
post_date
company_name
raw_job_title
salary_mid
job_url
role_match_score
```

注意：

- `job_url` 在当前源数据中大多为空。
- 因此 JD 证据不作为可点击新闻证据，而是作为“岗位存在性证据”。
- 输出中会保留公司名、岗位标题、发布时间、薪资中位数。

### 3.3 PatchTST 预测结果

默认优先读取：

```text
data/gold/patchtst_prediction_milestones.json
```

规模：

- 69 个角色。
- 每个角色 5 个里程碑视野。
- 共 **345 条趋势结论**。

逐月版本：

```text
data/gold/patchtst_predictions_36m.json
```

规模：

- 69 个角色。
- 每个角色未来 36 个月。
- 共 **2484 条逐月预测**。

适配器：

```text
pipelines/trend/_trend_source.py
```

关键逻辑：

- 优先读 PatchTST。
- 缺失时回退到 `data/gold/role_trend_scores.json`。
- 由于 PatchTST 预测未来月份，而未来没有新闻，所以证据统一从最近真实事件窗口取：

```python
EVENT_WINDOW = ("2026-01", "2026-06")
```

### 3.4 重大行业事件目录

文件：

```text
data/gold/major_industry_events_v1.json
```

规模：

- `event_catalog` 共 **101 条重大行业事件**。

用途：

- 弥补 GDELT 无正文、低质量新闻较多的问题。
- 提供公开来源、高可信的行业背景事件。
- 在批量证据、CoT 上下文和事件图谱中都可以使用。

---

## 4. 输出数据

### 4.0 模块级数据留存总览

| 阶段 | 输入规模 | 处理逻辑 | 输出规模 |
|---|---:|---|---:|
| 原始 GDELT 事件 | 约 2.6GB | 逐行流式读取，按岗位/月分片 | 1,726,284 条事件候选 |
| 原始 JD | 约 170MB | 字段瘦身，按岗位分片 | 70,826 条 JD |
| Evidence Index | 1,726,284 事件 + 70,826 JD | 只保留检索必要字段 | events 覆盖 67 角色，jobs 覆盖 62 角色 |
| PatchTST 里程碑 | 69 角色 × 5 视野 | 统一趋势结论格式 | 345 条趋势结论 |
| 批量 RAG 证据 | 345 条趋势结论 | 每条调用 EvidenceService，TopK=5 | 345 行 trend_evidence，其中 335 行有事件 |
| 逐月 RAG 证据 | 69 角色 × 36 月 | 复用同一检索核心，按月输出 | 2484 行 trend_evidence_monthly |
| 事件入图候选 | 69 条最近视野趋势 | 每岗位 RAG Top3 + 重大事件 Top5 | 380 条候选边 |
| 最终事件图谱 | 380 条候选边 | RAG 边按 P60 + 0.35 地板过滤，重大事件保留 | 321 条边，108 个事件节点 |
| HTML 可视化 | event_graph_v1.json + career graph | Canvas / vis-network 渲染 | 纯事件图 + 全量融合图 + 单岗位图 |

### 4.1 证据索引

生成脚本：

```bash
python pipelines/trend/build_evidence_index.py
```

输出：

```text
data/processed/evidence_index/
  events/<role>/<month>.jsonl
  jobs/<role>.jsonl
  manifest.json
```

当前索引统计：

```text
events: 1,726,284 条
jobs:   70,826 条
事件窗口: 2026-01~2026-06
```

### 4.2 趋势证据文件

生成脚本：

```bash
python -m pipelines.trend.build_trend_evidence
```

输出：

```text
data/gold/trend_evidence_v1.jsonl
reports/trend_explanation_eval_v1.md
```

当前 `trend_evidence_v1.jsonl` 有 **345 行**，每行对应一个趋势结论。

当前 345 条趋势证据的覆盖情况：

```text
有 aggregate 聚合信号: 335 / 345
有事件证据 TopK:      335 / 345
有 JD 证据:           310 / 345
无事件证据:            10 / 345
无 JD 证据:             35 / 345
```

每条趋势结论的事件证据数量分布：

```text
0 条事件证据:  10 条趋势结论
1 条事件证据:  30 条趋势结论
2 条事件证据:  30 条趋势结论
3 条事件证据:  20 条趋势结论
4 条事件证据:  30 条趋势结论
5 条事件证据: 225 条趋势结论
```

也就是说，绝大多数趋势结论可以拿到满额 TopK=5 的事件证据；少数角色因为候选较少或约束过滤较严，只保留 1~4 条。

每条趋势结论的 JD 证据数量分布：

```text
0 条 JD 证据:  35 条趋势结论
1 条 JD 证据:   5 条趋势结论
2 条 JD 证据:   5 条趋势结论
3 条 JD 证据:   5 条趋势结论
5 条 JD 证据: 295 条趋势结论
```

事件证据强弱分布：

```text
strong: 915 条
weak:   480 条
```

说明：

- `strong` 表示通过岗位相关性等更严格约束的事件样本。
- `weak` 表示强相关样本不足时，用标题质量较好的补充事件兜底。
- weak 不等于不能用，但在解释时要配合 `risk_notes`，不要把它当作强因果证据。

批量证据中的事件类型分布：

```text
market_report:          604
security_incident:      357
research_breakthrough:  228
policy:                 102
funding:                 85
layoff:                  19
```

趋势方向分布：

```text
stable: 143
down:   125
up:      77
```

逐月版本：

```bash
python -m pipelines.trend.build_trend_evidence --monthly
```

输出：

```text
data/gold/trend_evidence_monthly_v1.jsonl
```

当前逐月文件有 **2484 行**。

### 4.3 事件图谱文件

生成脚本：

```bash
python -m pipelines.graph.build_event_graph
```

输出：

```text
data/processed/event_graph_v1.json
```

当前图谱统计：

```text
candidate_edges: 380
threshold: 0.7065
pctl: 60
weight_floor: 0.35
kept_edges: 321
kept_rag_edges: 41
kept_major_edges: 280
kept_event_nodes: 108
distinct_jobs_affected: 69
```

解释：

- 候选边 380 条。
- 使用 P60 分位数和绝对地板过滤后，保留 321 条边。
- 其中 RAG 检索事件边 41 条。
- 重大行业事件边 280 条。
- 共 108 个事件节点。
- 覆盖 69 个岗位。

### 4.3.1 为什么图谱里只有这么多事件

图谱不是把所有 RAG 证据都画出来。原因有三个：

1. 全量 GDELT 候选有 172 万条，噪音很高，如果全挂到图上，图谱会不可读。
2. `trend_evidence_v1.jsonl` 是给报告/接口用的，每条趋势最多 TopK=5；图谱是给肉眼看的，所以更严格。
3. 图谱只取每个岗位最近视野的一条趋势结论，而不是把 3/6/12/24/36 个月全部画进图，否则同一岗位会重复挂很多边。

事件入图的数据漏斗是：

```text
原始 GDELT 事件候选
  1,726,284 条
        │
        ▼
按角色 + 月份建立 evidence_index
  events: 1,726,284 条 / 67 个有事件候选的角色
  jobs:      70,826 条 / 62 个有 JD 的角色
        │
        ▼
PatchTST 里程碑趋势结论
  345 条 = 69 个角色 × 5 个预测视野
        │
        ▼
批量 RAG 证据文件
  trend_evidence_v1.jsonl: 345 行
  其中 335 行有 aggregate，335 行有事件证据
        │
        ▼
事件入图只取每个岗位最近预测视野
  69 条岗位趋势结论
        │
        ▼
每个岗位最多取 TOPK_GRAPH=3 条 RAG 事件
  同时挂重大行业事件，最多 5 条/岗位方向
        │
        ▼
图谱候选边 raw_edges
  380 条
  ├─ RAG 候选边约 100 条
  └─ 重大行业事件候选边 280 条
        │
        ▼
阈值过滤
  RAG 边按 retrieval_score 取 P60 阈值，且要求 >= 0.35
  当前阈值 = 0.7065
        │
        ▼
最终 event_graph_v1.json
  321 条 AFFECTS 边
  ├─ RAG 边 41 条
  └─ 重大行业事件边 280 条
  108 个 event 节点
  覆盖 69 个岗位
```

所以图谱里只有 108 个事件节点、321 条边，是刻意筛选后的结果，不是数据不足。

### 4.3.2 “17 条下降边”不是筛选起点

图谱统计里有一个容易误解的数字：

```text
graph_edges_by_trend:
  neutral: 301
  negative: 17
  positive: 3
```

这里的 **17 条 negative** 指的是最终图谱边里，`trend_impact_direction=negative` 的边，也就是“预测方向明确下降”的边数。

它不是原始数据量，也不是“从 17 条里筛出图谱事件”。真实筛选起点是：

```text
1,726,284 条 GDELT 候选事件
-> 345 条趋势结论的 RAG 证据
-> 380 条图谱候选边
-> 321 条最终图谱边
```

17 条只是在最终图谱里按预测方向统计出来的下降边。

### 4.3.3 每个岗位图谱里会有多少证据边

最终图谱覆盖 69 个岗位，每个岗位保留的 `AFFECTS` 边数量分布如下：

```text
每岗位 3 条边:  9 个岗位
每岗位 4 条边: 31 个岗位
每岗位 5 条边: 13 个岗位
每岗位 6 条边:  9 个岗位
每岗位 7 条边:  5 个岗位
每岗位 8 条边:  2 个岗位
```

为什么不是每个岗位都一样？

- RAG 部分每个岗位最多取 3 条候选事件。
- 但严格过滤后，有的岗位 RAG 事件少于 3 条。
- 重大行业事件最多挂 5 条，但取决于该岗位和趋势方向是否在 `major_industry_events_v1.json` 中有映射。
- 同一个重大事件可连接多个岗位，因此 event 节点数少于边数。

因此，单岗位图谱里通常会看到 **3 到 8 条事件证据边**。

### 4.3.4 图谱边按来源分类

最终 321 条边按来源分：

```text
public_major_event: 280
rag_event:           41
```

解释：

- `rag_event` 是从 GDELT 事件检索里筛出的岗位相关事件。
- `public_major_event` 是人工整理的公开来源重大行业事件，更适合图谱展示和答辩解释。
- 图谱里重大行业事件边多，是因为它们可解释性更强、来源更稳，且会被复用到多个岗位。

### 4.3.5 图谱边按事件类型分类

最终图谱边的主要事件类型：

```text
ai_coding_agent:              61
model_release:                48
market_report:                15
ai_infrastructure:            14
language_release:             13
research_breakthrough:        13
enterprise_ai_platform:       11
game_engine_release:          10
security_incident:            10
regulation:                    8
security_standard:             7
frontend_framework_release:    7
testing_tool_release:          6
mobile_platform_release:       5
outage:                        5
ml_framework_release:          5
runtime_release:               5
market_research:               5
quality_risk:                  4
funding:                       4
```

这说明图谱里的事件主要分为四类：

1. AI/模型/Agent 平台类事件。
2. 编程语言、框架、运行时、工具发布类事件。
3. 安全、监管、风险类事件。
4. 市场研究和行业报告类事件。

### 4.4 图谱 HTML

纯事件图：

```bash
python -m pipelines.graph.build_event_graph_view
```

输出：

```text
reports/event_graph_view.html
```

融合图：

```bash
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

输出：

```text
reports/full_unified_graph.html
```

单岗位图：

```bash
python -m pipelines.graph.build_unified_graph_view --role "RAG Engineer" --top-n 12
```

输出示例：

```text
reports/role_011_unified_graph.html
```

---

## 5. 文件清单与职责

### 5.1 RAG 检索核心

文件：

```text
app/services/evidence.py
```

职责：

- 实现 `EvidenceService.retrieve_evidence()`。
- 从 evidence_index 中读取岗位 + 月份命中的小分片。
- 做相关性过滤、BM25 排序、方向归因排序、聚合统计、JD 混入。
- 是运行时接口、批量证据、CoT、图谱入图共用的唯一检索核心。

对外主函数：

```python
EvidenceService.retrieve_evidence(
    role: str,
    months: tuple[str, str],
    top_k: int = 5,
    direction: str | None = None,
) -> dict
```

返回结构：

```json
{
  "role": "RAG Engineer",
  "months": ["2026-01", "2026-06"],
  "direction": "flat",
  "aggregate": {},
  "events": [],
  "jobs": [],
  "candidates_total": 259,
  "candidates_kept": 5,
  "note": "..."
}
```

### 5.2 离线索引

文件：

```text
pipelines/trend/build_evidence_index.py
```

职责：

- 把 2.6GB GDELT jsonl 和 170MB JD 数据转成轻量分片。
- 纯标准库实现，不依赖 DuckDB/ES/向量数据库。
- 查询时只读命中岗位和月份的小文件，避免每次扫描全量。

设计选择：

- 没有使用 Elasticsearch，因为查询是结构化过滤 + 排序，不是开放全文搜索。
- 没有使用向量库，因为 GDELT 缺正文，且 172 万条全量 embedding 成本过高。
- 采用文件分区方案：简单、稳定、便于比赛环境复现。

### 5.3 趋势结论适配器

文件：

```text
pipelines/trend/_trend_source.py
```

职责：

- 统一读取 PatchTST 或基线趋势结论。
- 屏蔽上游文件差异。
- 让 `build_trend_evidence.py` 和 `build_event_graph.py` 不依赖具体模型输出格式。

### 5.4 批量证据生成

文件：

```text
pipelines/trend/build_trend_evidence.py
```

职责：

- 对 345 条 PatchTST 里程碑趋势结论批量调用 `EvidenceService`。
- 输出 `trend_evidence_v1.jsonl`。
- 输出评估报告 `reports/trend_explanation_eval_v1.md`。
- 支持 `--monthly` 生成 2484 行逐月版本。

### 5.5 CoT 上下文

文件：

```text
app/services/trend_explanation.py
```

职责：

- 组装 CoT 使用的 grounded context。
- 不直接调用 LLM。
- 只负责把事实组织成可引用、可约束的 prompt。

核心函数：

```python
assemble_cot_context(role: str, horizon: int = 3) -> dict
build_cot_prompt(ctx: dict) -> str
```

### 5.6 TrendService 接入

文件：

```text
app/services/trend.py
```

职责：

- `TrendService.get_signal()` 优先调用 PatchTST。
- 若 PatchTST 不可用，回退到基线 `role_trend_scores.json`。
- 自动调用 EvidenceService，将 evidence 填入趋势接口返回。

### 5.7 API 路由

文件：

```text
app/api/routes.py
```

新增/相关接口：

```text
GET /v1/trends/{job_role}
GET /v1/evidence/{job_role}
```

### 5.8 事件入图

文件：

```text
pipelines/graph/build_event_graph.py
```

职责：

- 复用 EvidenceService 的选择结果。
- 将事件写成 `event` 节点。
- 将事件和岗位之间写成 `AFFECTS` 边。
- 输出 `data/processed/event_graph_v1.json`。
- 可选 `--write-db` 写入 Postgres 图谱表。

### 5.9 图谱可视化

文件：

```text
pipelines/graph/build_event_graph_view.py
pipelines/graph/build_unified_graph_view.py
pipelines/graph/export_graph_interactive_v2.py
app/services/evidence_color.py
```

职责：

- `build_event_graph_view.py`：生成纯事件 → 岗位图。
- `build_unified_graph_view.py`：融合岗位-技能图谱和事件证据图。
- `export_graph_interactive_v2.py`：Canvas 交互式渲染器。
- `evidence_color.py`：统一事件边颜色逻辑，避免不同图里颜色规则不一致。

---

## 6. RAG 检索逻辑

### 6.1 不是普通文本 RAG

本模块不是“把文档塞进向量库然后相似度检索”的 RAG。

原因：

- GDELT 数据没有可靠正文。
- 大量候选来自 URL slug、主题、关键词。
- 直接 embedding 会把噪音一起向量化，且 172 万条成本较高。

因此本模块采用：

```text
结构化分片过滤 + 规则约束 + BM25 主题相关 + 趋势方向归因排序 + 聚合统计兜底
```

### 6.2 检索流程

给定：

```text
role = "RAG Engineer"
months = ("2026-01", "2026-06")
top_k = 5
direction = "flat"
```

流程：

1. 定位分片目录：

```text
data/processed/evidence_index/events/RAG_Engineer/*.jsonl
```

2. 按月份读取候选事件。

3. 计算 aggregate 聚合信号。

4. 通过相关性闸门过滤噪音。

5. 构造 BM25 query：
   - 角色名
   - role aliases
   - top_skills

6. 对候选事件计算复合分。

7. 去重。

8. 按方向偏好选择 TopK。

9. 混入 JD 存在性证据。

10. 返回证据链。

### 6.2.1 单岗位证据链例子：RAG Engineer

以 `RAG Engineer`、窗口 `2026-01~2026-06`、方向 `flat` 为例：

```text
输入角色: RAG Engineer
输入窗口: 2026-01 ~ 2026-06
输入方向: flat

原始候选事件 candidates_total: 259
通过相关性闸门 candidates_kept: 40
最终返回事件 TopK: 5
最终返回 JD: 0
```

该岗位的 TopK 事件样例统计：

```text
security_incident / negative / weak / score=0.3695 / title_quality=0.6 / role_affinity=0.0
market_report      / positive / weak / score=0.5886 / title_quality=1.0 / role_affinity=0.0
market_report      / positive / weak / score=0.5543 / title_quality=1.0 / role_affinity=0.0
market_report      / neutral  / weak / score=0.3473 / title_quality=0.6 / role_affinity=0.0
research_breakthrough / positive / weak / score=0.3043 / title_quality=0.7 / role_affinity=0.0
```

解释：

- `259 -> 40` 是 RAG 相关性闸门筛选结果。
- `40 -> 5` 是排序后取 TopK。
- 这 5 条虽然可作为补充样本，但 `role_affinity=0.0`，所以标注为 `weak`。
- 因此系统 note 会提示：`强相关事件不足，补充 5 条弱相关事件；趋势佐证以 aggregate/JD 为准`。
- 这也是我们为什么设计“两层证据”的原因：单条事件不强时，用 aggregate 聚合信号作为主力。

### 6.3 聚合信号 aggregate

聚合信号是本模块的主力证据，因为单条 GDELT 事件噪音较多。

输出字段：

```json
{
  "article_count": 259,
  "mean_tone": -0.43,
  "positive_ratio": 0.421,
  "opportunity_events": 38,
  "risk_events": 102,
  "net_signal": "negative",
  "top_themes": [],
  "top_domains": []
}
```

含义：

- `article_count`：候选相关新闻数。
- `mean_tone`：平均情绪。
- `positive_ratio`：tone > 0 的比例。
- `opportunity_events`：经济/就业语境下 tone > 0 的事件数。
- `risk_events`：经济/就业语境下 tone < 0 的事件数。
- `net_signal`：机会多于风险为 positive，风险多于机会为 negative，否则 mixed。

### 6.4 单条事件证据

输出字段：

```json
{
  "evidence_type": "news_event",
  "url": "...",
  "source_domain": "...",
  "title": "...",
  "published_at": "2026-03-20",
  "tone": -4.479,
  "themes": [],
  "match_weight": 0.2,
  "event_type": "security_incident",
  "impact_direction": "negative",
  "is_counter_signal": false,
  "direction_align": 0.83,
  "title_quality": 0.7,
  "role_affinity": 0.6,
  "evidence_strength": "weak",
  "retrieval_score": 0.46
}
```

### 6.5 JD 证据

输出字段：

```json
{
  "evidence_type": "job_posting",
  "company_name": "...",
  "title": "...",
  "post_date": "2025-04-30",
  "salary_mid": 130809,
  "job_url": null,
  "role_match_score": 0.91,
  "out_of_range": true
}
```

`out_of_range=true` 表示当前新闻窗口内没有 JD，回退到该角色全部 JD 作为存在性证据。

---

## 7. RAG 约束设计

由于 GDELT 没有正文，且 URL/主题/关键词噪音很强，本模块加入了多层约束。

### 7.1 约束总览

当前至少包含以下约束：

1. 技能词白名单约束。
2. URL/后缀伪词过滤。
3. 歧义技能词约束。
4. 科技主题约束。
5. 经济/劳动力主题共现约束。
6. 垃圾域名黑名单。
7. 弱可信域名降权。
8. 坏标题短语过滤。
9. 坏标题词过滤。
10. 岗位上下文词约束。
11. 强科技主题约束。
12. 角色锚词扩展。
13. 角色必需词约束。
14. 标题质量分。
15. 岗位相关性分。
16. URL 去重。
17. 标题近重复去重。
18. 趋势方向对齐。
19. 反向信号保留。
20. 图谱入图阈值约束。
21. 图谱颜色层招聘噪音约束。

### 7.2 技能词白名单

文件：

```text
data/gold/skill_vocab.json
```

代码：

```python
_load_skill_vocab()
_SKILL_VOCAB
```

作用：

- 只有命中技能词表的术语才更可能被认为是技术相关。
- 避免把普通英文词误判为技能。

### 7.3 URL/后缀伪词过滤

代码常量：

```python
ARTIFACT_TERMS = {
    "html", "htm", "php", "aspx", ".net", "www", "amp", "com", "org", "co", "io"
}
```

作用：

- URL 里常见后缀和域名片段不能当作技术证据。
- 例如 `.net` 可能只是域名后缀，不一定是 .NET 技术。

### 7.4 歧义技能词约束

代码常量：

```python
AMBIGUOUS_TERMS = {
    "react", "go", "swift", "rust", "java", "python",
    "ruby", "scala", "spring", "node", "next", "dart",
    "shell", "pandas", "spark", "agent"
}
```

作用：

- `react` 可能是“作出反应”。
- `go` 是普通动词。
- `swift` 可指快速。
- `python` 也可能是动物或非技术语境。

这些词不能单独作为强证据，必须配合标题上下文、强技能词或科技经济主题共现。

### 7.5 科技主题与经济主题共现

科技主题：

```python
TECH_THEMES = (
    "SOFTWARE", "COMPUTER", "CYBER", "ARTIFICIAL_INTELLIGENCE",
    "MACHINE_LEARNING", "WB_652_ICT_APPLICATIONS", "TECHNOLOGY",
)
```

经济/劳动力主题：

```python
ECON_THEMES = (
    "ECON_", "LAYOFF", "UNEMPLOY", "WB_855_LABOR", "ENTREPRENEUR",
    "EPU_ECONOMY", "HIRING", "RECRUIT", "WB_2024",
)
```

作用：

- 对歧义技能词，要求技术主题和经济/劳动力主题共现。
- 例如只有 `python` 不够；如果同时出现科技主题和招聘/经济主题，才更可信。

### 7.6 域名黑名单

代码常量：

```python
JUNK_DOMAIN_SUBSTR = (
    "ticker", "marketsdaily", "dailypolitical", "defenseworld",
    "prokerala", "starmagazine", "newsbusters", "ghanamma",
    "wyomingnewsnow", "dailymail", "insidermonkey", "finanznachrichten",
)
```

作用：

- 过滤股票自动聚合站、小报、低质量站点。
- 这些站点会制造大量关键词噪音。

### 7.7 弱可信域名降权

代码常量：

```python
WEAK_DOMAIN_SUBSTR = (
    "manilatimes", "webindia", "calcuttanews", "moneycontrol",
    "tickerreport", "livemint"
)
```

作用：

- 不直接删除。
- 在标题质量分里降权。

### 7.8 坏标题过滤

坏标题短语：

```python
BAD_TITLE_PHRASES = (
    "reacts to", "readers react", "doctor reacts",
    "python eggs", "bridge cracks", "amid crisis", ...
)
```

坏标题词：

```python
BAD_TITLE_WORDS = {
    "war", "iran", "trump", "shooting", "murder",
    "gaza", "ukraine", "flood", "earthquake", ...
}
```

作用：

- 过滤政治、灾害、社会新闻等非 IT 趋势内容。
- 避免 `react`、`python` 等词造成误命中。

### 7.9 岗位上下文词

代码常量：

```python
ROLE_CONTEXT_WORDS = {
    "frontend", "backend", "fullstack", "developer",
    "engineer", "architect", "software", "qa", "sre",
    "cloud", "data", "mobile", "web", "api", "hiring", "job"
}
```

作用：

- 标题或 URL slug 中出现岗位上下文词，说明更可能是 IT 岗位相关。

### 7.10 角色锚词与必需词

角色锚词扩展：

```python
ROLE_ANCHOR_EXPANSIONS = {
    "ai": {"ai", "artificial", "intelligence", "machine", "learning", "llm", "openai", "agent"},
    "frontend": {"frontend", "react", "vue", "angular", "javascript", "typescript"},
    "backend": {"backend", "server", "api", "java", "python", "node", "microservices"},
    ...
}
```

角色必需词：

```python
ROLE_REQUIRED_TERMS = {
    "backend go engineer": {"go", "golang"},
    "backend java engineer": {"java", "spring"},
    "frontend react engineer": {"react", "reactjs", "javascript", "typescript", "frontend"},
    ...
}
```

作用：

- 限制“这个事件到底是不是这个岗位的证据”。
- 例如 Backend Go Engineer 至少要命中 `go/golang`。
- Frontend React Engineer 不能只因为普通英文 react 就入选。

### 7.11 标题质量分

函数：

```python
_title_quality(title, domain) -> float
```

逻辑：

- 坏标题直接 0。
- 标题太短或纯数字低分。
- 有岗位上下文词加分。
- 有明确技能词加分。
- 弱可信域名降权。

用途：

- RAG 排序时参与复合分。
- 图谱入图时要求最低标题质量。

### 7.12 岗位相关性分

函数：

```python
_role_title_affinity(role, info, title) -> float
```

逻辑：

- 标题必须命中该岗位的 role anchor。
- 特定岗位必须满足 required terms。
- 如果只命中歧义词，而且没有强技术上下文，则判 0。
- 命中多个锚词、岗位词、强技能词会加分。

用途：

- RAG 排序。
- 图谱入图。
- 展示强弱相关。

### 7.13 去重

两层去重：

1. URL 去重。
2. 标题近重复去重。

标题近重复签名：

```python
_title_sig(title)
```

做法：

- 取标题前 7 个实词作为签名。
- 避免同一新闻不同 URL 或转载版本重复入选。

### 7.14 方向对齐

函数：

```python
_direction_align(tone, etype, direction)
```

逻辑：

- 如果预测方向是 `flat/stable`，方向对齐默认 0.5。
- 如果预测 `up`，偏好正 tone 和机会类事件。
- 如果预测 `down`，偏好负 tone 和风险类事件。
- 机会类：

```python
OPPORTUNITY_TYPES = {"funding", "product_release", "research_breakthrough"}
```

- 风险类：

```python
RISK_TYPES = {"layoff", "policy", "security_incident"}
```

### 7.15 反向信号保留

RAG 不只选择支持预测的证据。

当方向明确时，如果 TopK 全部是同向证据，代码会尝试保留一条反向信号：

```text
上涨结论里保留一条负向风险
下降结论里保留一条正向机会
```

目的：

- 避免选择性举证。
- 给 CoT 提供“权衡反向证据”的材料。

### 7.16 图谱入图约束

文件：

```text
pipelines/graph/build_event_graph.py
```

核心阈值：

```python
TOPK_GRAPH = 3
WEIGHT_FLOOR = 0.35
PCTL = 60
TITLE_QUALITY_MIN = 0.5
ROLE_AFFINITY_MIN = 0.5
```

含义：

- 图谱比普通 RAG 更严格。
- 每个岗位只挂少量事件。
- 入图事件要求标题质量 >= 0.5。
- 入图事件要求岗位相关性 >= 0.5。
- 检索分数用 P60 动态阈值 + 绝对地板过滤。

---

## 8. 复合排序公式

代码注释中最初设计为：

```text
composite = 0.4·主题相关(BM25)
          + 0.3·方向对齐
          + 0.2·事件重要性
          + 0.1·时间近度
```

实际代码在加入质量约束后使用更稳的版本：

```text
composite =
  0.25 * BM25主题相关
+ 0.20 * 方向对齐
+ 0.10 * salience
+ 0.05 * 时间近度
+ 0.20 * 标题质量
+ 0.20 * 岗位相关性
```

其中：

- BM25：角色名、别名、top_skills 与事件主题/匹配词/标题的相关度。
- 方向对齐：事件情绪与预测方向是否一致。
- salience：tone 强度和 match_weight。
- 时间近度：同窗口内越新的事件略优先。
- 标题质量：标题是否像真实 IT/行业事件。
- 岗位相关性：标题是否和该岗位确实相关。

---

## 9. CoT 部分怎么用

### 9.1 CoT 的边界

本模块加入的是 **grounded CoT context**，不是在后端直接调用 LLM 生成最终回答。

边界：

- 本模块负责把事实、证据和引用编号整理好。
- Agent 或 LLM 层负责生成自然语言链式解释。
- LLM 必须被约束为只能依据给定证据推理。

### 9.2 代码位置

```text
app/services/trend_explanation.py
```

### 9.3 上下文结构

调用：

```python
from app.services.trend_explanation import assemble_cot_context

ctx = assemble_cot_context("RAG Engineer", horizon=3)
```

返回：

```json
{
  "canonical_role": "RAG Engineer",
  "horizon_months": 3,
  "prediction": {
    "trend_direction": "flat",
    "predicted_demand_index": 0.016,
    "confidence": 0.72
  },
  "aggregate": {},
  "events": [
    {
      "cite": "E1",
      "title": "...",
      "impact": "negative",
      "event_type": "security_incident",
      "tone": -4.479,
      "is_counter_signal": false,
      "evidence_strength": "weak",
      "url": "..."
    }
  ],
  "major_events": [
    {
      "cite": "M1",
      "title": "...",
      "date": "2025-04-14",
      "impact": "positive",
      "source_url": "..."
    }
  ],
  "jobs": [
    {
      "cite": "J1",
      "company": "...",
      "title": "...",
      "salary_mid": 130000
    }
  ],
  "note": "..."
}
```

引用编号约定：

```text
E# = GDELT / 新闻事件证据
M# = 重大行业事件
J# = JD 在招证据
```

### 9.4 构造 CoT Prompt

调用：

```python
from app.services.trend_explanation import assemble_cot_context, build_cot_prompt

ctx = assemble_cot_context("RAG Engineer", horizon=3)
prompt = build_cot_prompt(ctx)
```

Prompt 要求 LLM 按以下步骤回答：

```text
Step1 模型预测说了什么
Step2 新闻面整体情绪如何
Step3 关键事件怎样支撑或反驳该预测
Step4 在招 JD 反映的短期需求
Step5 综合判断该岗位趋势及主因
```

### 9.5 系统提示

代码中提供：

```python
COT_SYSTEM_PROMPT
```

核心约束：

1. 只能依据给定证据推理。
2. 每个判断后必须标注引用编号，如 `[E1]`、`[M1]`、`[J1]`。
3. 如果存在反向信号，必须明确指出并权衡。

### 9.6 命令行自检

```bash
python -m app.services.trend_explanation "RAG Engineer"
```

输出：

- 角色预测。
- 聚合新闻信号。
- 编号事件证据。
- 重大行业事件。
- JD 证据。
- 分步骤推理任务。

---

## 10. API 怎么用

### 10.1 获取趋势和证据

接口：

```http
GET /v1/trends/{job_role}?horizon_months=3
```

示例：

```bash
curl "http://localhost:8000/v1/trends/RAG%20Engineer?horizon_months=3"
```

返回：

- canonical_role
- horizon_months
- trend_direction
- predicted_demand_index
- confidence
- main_factors
- evidence

该接口内部调用：

```python
TrendService.get_signal()
```

然后自动走：

```python
EvidenceService.retrieve_evidence()
```

### 10.2 只获取证据

接口：

```http
GET /v1/evidence/{job_role}
```

参数：

```text
start_month: 默认 2026-01
end_month:   默认 2026-06
top_k:       默认 5
direction:   可选 up / flat / down
```

示例：

```bash
curl "http://localhost:8000/v1/evidence/RAG%20Engineer?start_month=2026-01&end_month=2026-06&top_k=5&direction=flat"
```

返回：

```json
{
  "role": "RAG Engineer",
  "months": ["2026-01", "2026-06"],
  "direction": "flat",
  "aggregate": {},
  "events": [],
  "jobs": [],
  "candidates_total": 259,
  "candidates_kept": 5,
  "note": "..."
}
```

---

## 11. 图谱怎么用

### 11.1 事件图谱语义

节点：

```text
event
job
skill
resource
```

新增关系：

```text
AFFECTS(event -> job)
```

事件节点字段：

```json
{
  "title": "...",
  "url": "...",
  "source_domain": "...",
  "published_at": "...",
  "tone": -3.1,
  "event_type": "security_incident",
  "role_affinity": 0.7,
  "title_quality": 0.8,
  "themes": [],
  "source_layer": "rag_event"
}
```

边字段：

```json
{
  "src_type": "event",
  "src_id": "evt_xxx",
  "dst_type": "job",
  "dst_id": "role_011",
  "relation": "AFFECTS",
  "weight": 0.7167,
  "confidence": 0.85,
  "meta_json": {
    "impact_direction": "positive",
    "trend_impact_direction": "neutral",
    "event_type": "model_release",
    "month": "2026-08-01",
    "trend_direction": "flat",
    "role_family": "Emerging AI",
    "source_layer": "public_major_event"
  }
}
```

### 11.2 颜色规则

文件：

```text
app/services/evidence_color.py
```

当前设计：

- 事件节点统一灰色。
- 边颜色表达趋势/证据方向。

颜色：

```text
绿色边 = 上升预测，或持平预测下的明确正向技术事件
红色边 = 下降预测，或持平预测下的明确风险事件
蓝色边 = 持平/混合/不明确证据
```

为什么这样设计：

- 如果用事件节点红绿，会出现“绿色事件很多，但下降岗位更多”的误读。
- 事件本身是证据，不直接代表岗位预测方向。
- AFFECTS 边才表示“这个事件如何影响这个岗位趋势”。

持平预测下的二级约束：

- 不直接相信所有 `impact_direction=positive`。
- `market_report` 不自动染绿。
- 标题含 `engineer/developer/job/hiring/senior/junior/remote/on site` 等招聘痕迹，不染绿。
- 只有明确技术事件类型才染绿。
- 安全事故、监管、风险事件才染红。

当前颜色统计：

```text
positive/绿: 138
negative/红: 25
neutral/蓝: 158
```

### 11.3 生成图谱

生成事件图谱数据：

```bash
python -m pipelines.graph.build_event_graph
```

生成纯事件图：

```bash
python -m pipelines.graph.build_event_graph_view
```

生成全量融合图：

```bash
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

生成单角色融合图：

```bash
python -m pipelines.graph.build_unified_graph_view --role "RAG Engineer" --top-n 12
```

打开：

```text
reports/event_graph_view.html
reports/full_unified_graph.html
reports/role_011_unified_graph.html
```

全量融合图默认隐藏标签，因为节点太多。需要看名称时点击“显示标签”。

---

## 12. 演示命令

### 12.1 查看某角色完整证据链

```bash
python -m pipelines.trend.show_evidence_demo --role "RAG Engineer"
```

输出包括：

- PatchTST 里程碑预测。
- 聚合新闻信号。
- TopK 事件证据。
- JD 在招证据。
- 重大行业事件。
- note 风险说明。

### 12.2 重建索引

```bash
python -m pipelines.trend.build_evidence_index
```

样本调试：

```bash
python -m pipelines.trend.build_evidence_index --sample
```

### 12.3 重建趋势证据

```bash
python -m pipelines.trend.build_trend_evidence
```

逐月版本：

```bash
python -m pipelines.trend.build_trend_evidence --monthly
```

### 12.4 重建图谱和 HTML

```bash
python -m pipelines.graph.build_event_graph
python -m pipelines.graph.build_event_graph_view
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

---

## 13. 当前评估结果

评估文件：

```text
reports/trend_explanation_eval_v1.md
```

当前核心指标：

```text
趋势结论总数: 345
含聚合信号覆盖率: 97.1% (335/345)
含干净事件样本覆盖率: 97.1% (335/345)
平均干净事件数/条: 4.16 (TopK=5)
覆盖角色: 69
```

解释：

- 聚合信号覆盖率高，说明大部分趋势结论都有统计支撑。
- 干净事件覆盖率高，但其中仍有 weak 事件，需要结合 risk_notes 说明。
- 由于 GDELT 无正文，不能声称所有单条新闻都完全准确，只能说“相关性近似”。

---

## 14. 已知限制

1. **GDELT 无正文**
   - 单条事件只能依赖 URL slug、themes、tone、matched_terms。
   - 所以单条事件解释力有限。

2. **关键词噪音**
   - `react/go/python/rust/swift` 等词容易误匹配。
   - 已通过歧义词约束、坏标题过滤、角色锚词等方式缓解。

3. **英文来源偏多**
   - 当前证据多来自英文新闻源。
   - 中文本土市场仍需补充。

4. **JD URL 缺失**
   - JD 证据无法提供可点击岗位链接。
   - 目前只作为存在性证据。

5. **趋势预测与新闻窗口不一致**
   - PatchTST 预测未来 3/6/12/24/36 个月。
   - 新闻只覆盖 2026-01~06。
   - 因此证据窗口固定为最近真实事件窗口，而不是预测月份。

6. **颜色只是可视化辅助**
   - 图谱边颜色不是模型训练标签。
   - 颜色规则用于展示，不能替代 trend_direction、impact_direction 原始字段。

---

## 15. 向队友/老师解释时可以这样说

我们这个模块不是简单地把几条新闻贴到趋势后面，而是做了一条完整的“预测解释链”：

1. 上游 PatchTST 给出岗位未来趋势。
2. 我们从 GDELT 和 JD 数据中按岗位、月份构建证据索引。
3. 检索时先用结构化分片召回候选，再通过技能词白名单、主题共现、域名黑名单、坏标题过滤、角色锚词、岗位相关性等多重约束过滤噪音。
4. 对候选事件做 BM25 主题相关、方向对齐、标题质量、岗位相关性等复合排序。
5. 输出两层证据：聚合信号作为主力，TopK 事件作为代表性佐证，JD 作为存在性证据。
6. 对 LLM/Agent，我们不让它自由编造，而是提供带引用编号的 grounded CoT prompt，要求每一步推理都引用证据。
7. 对可视化，我们把事件接入职业图谱，用 AFFECTS 边表示事件对岗位趋势的影响，并通过边颜色展示上升、下降、持平或混合影响。

一句话总结：

```text
本模块完成了行业趋势预测之后的 RAG 证据检索、受约束 CoT 解释上下文、事件入图和可视化展示闭环。
```
